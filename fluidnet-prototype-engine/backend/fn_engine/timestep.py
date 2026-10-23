"""Euler 时间步误差控制（计划 §12.1）：纯试算、step-doubling、接受/拒绝与诊断计数。

本模块只处理与物理无关的部分：按类别的误差归一化、步长建议、计数与停止条件。整步与
两个半步的试算由调用方在 **accepted state** 上完成；本模块不持有、也不提交任何 PID、
脚本、设备累计量或缓存状态。

关键约定（A0 冻结，A1–A4 共同遵守）：

- 从同一 accepted state 计算整步 ``x_full(h)`` 与两个半步 ``x_fine(h/2, h/2)``，
  局部误差取 ``|x_fine − x_full|`` 的量级，**不做** Richardson 外推。
- 每一类实际积分状态用 ``atol_i + rtol·max(|x_old_i|,|x_fine_i|)`` 归一化，取最大范数；
  质量 kg、能量 J、温度 K 各有独立 atol，不用一个裸数混合单位。
- 能量状态先相对冻结参考态中心化：取 ``u' = u − u_ref``，参考态在会话初始化时冻结。
  改变物性内能零点时 u 与 u_ref 同步平移，误差接受结果不变。
- ``error_norm <= 1`` 才按细步路径接受；建议步长 ``h_next = h·safety·error_norm^(-1/2)``，
  增长/收缩倍率、零误差与最小/最大步长均有界。
- 最小步长仍不满足误差、或边界截断的细小步仍不满足误差时明确抛出
  :class:`TimeStepExhausted`，由会话转成带已接受历史的 `SolveFailed`，不静默放宽容差。

RunFrame.metrics 的稳定键名（A0 冻结，A4 报告使用；均指 **局部** 时间离散误差估计）：

``timestep_adaptive``
    1 表示本帧使用误差接受控制，0 表示旧固定步长路径。
``internal_step_s``
    本帧最后一个被接受内部步的步长（s）。
``internal_steps`` / ``internal_steps_total``
    本帧 / 自会话开始被接受的内部细步数。
``internal_rejections`` / ``internal_rejections_total``
    本帧 / 自会话开始因 ``error_norm > 1`` 被拒绝的试算数。
``solver_retries``
    本帧因隐式步求解失败（设备/物性/收敛）而缩短重试的次试算数。
``boundary_truncations``
    本帧因输出、控制采样、日程或启停边界被截断的内部步数。
``local_error_norm_max``
    本帧所有被接受内部步的局部误差范数最大值；只描述局部时间离散误差，不是全程误差，
    也不是模型准确度保证。
``accepted_step_min_s`` / ``accepted_step_max_s``
    本帧被接受内部步长的最小/最大值。
"""
from dataclasses import dataclass, field

import numpy as np

from .compiler import CompilationError
from .models import SolverOptions

# 首轮支持的执行域：理想热模型（A1）与冷库 B 集总制冷站（A2/A3）。
SUPPORTED_DOMAINS = frozenset({'thermal', 'refrigeration'})

# 误差类别的规范单位；配置字段名即单位，避免 kg/J/K 混用。
CATEGORY_UNITS = {'mass': 'kg', 'energy': 'J', 'temperature': 'K', 'pressure': 'Pa'}


class TimeStepExhausted(RuntimeError):
    """最小步长（或边界截断的细小步）仍不满足误差；保留已接受历史后停止。"""

    BOUNDARY = 'TIME_STEP_BOUNDARY_EXCEEDED'
    MINIMUM = 'TIME_STEP_MIN_EXCEEDED'

    def __init__(self, message, *, time, h, error_norm, boundary=False, cause=None):
        super().__init__(message)
        self.code = self.BOUNDARY if boundary else self.MINIMUM
        self.time = time
        self.h = h
        self.error_norm = error_norm
        self.cause = cause


class TrialFailure(Exception):
    """一次整步/半步试算在求解层面失败（不收敛、离两相区、液位越界）；由接受循环缩步重试。"""

    def __init__(self, cause=None):
        super().__init__(str(cause) if cause is not None else '试算失败')
        self.cause = cause


@dataclass(frozen=True)
class TimeStepConfig:
    """校验后的有效配置；`max_step_s` 已按 `SolverOptions.dynamic_step_s` 解析。"""

    enabled: bool
    mass_atol_kg: float
    energy_atol_j: float
    temperature_atol_k: float
    rtol: float
    min_step_s: float
    max_step_s: float
    safety: float
    growth: float
    shrink: float

    @classmethod
    def from_solver(cls, solver):
        if not isinstance(solver, SolverOptions):
            raise TypeError('时间误差控制配置必须来自 SolverOptions')
        options = solver.time_step
        max_step = options.max_internal_step_s if options.max_internal_step_s is not None else solver.dynamic_step_s
        if options.enabled and options.min_internal_step_s >= max_step:
            raise ValueError(f'内部最小步长 {options.min_internal_step_s:g}s 必须小于有效最大步长 {max_step:g}s')
        return cls(enabled=options.enabled, mass_atol_kg=options.mass_atol_kg, energy_atol_j=options.energy_atol_j,
                   temperature_atol_k=options.temperature_atol_k, rtol=options.rtol,
                   min_step_s=options.min_internal_step_s, max_step_s=max_step, safety=options.safety,
                   growth=options.growth_factor, shrink=options.shrink_factor)

    def atol(self, category):
        try:
            return {'mass': self.mass_atol_kg, 'energy': self.energy_atol_j,
                    'temperature': self.temperature_atol_k}[category]
        except KeyError:
            raise ValueError(f'未知误差类别 {category!r}；只有 mass/energy/temperature 有独立 atol') from None


def ensure_supported(domain):
    """首轮只支持理想热模型与冷库 B；其他执行域开启后明确拒绝，不静默忽略。"""
    if domain not in SUPPORTED_DOMAINS:
        raise CompilationError('TIMESTEP_DOMAIN_UNSUPPORTED',
                               f'时间步误差控制首轮只支持理想热模型与冷库 B 集总制冷站；'
                               f'执行域 {domain or "未知"} 尚未接入')


@dataclass
class ErrorEstimate:
    """一次 step-doubling 的局部误差估计；`norm > 1` 表示应拒绝。"""

    norm: float
    by_category: dict[str, float] = field(default_factory=dict)
    extra: dict[str, float] = field(default_factory=dict)

    @property
    def worst(self):
        return max(self.by_category, key=self.by_category.get) if self.by_category else None


def normalized_error(x_old, x_full, x_fine, *, categories, atol, rtol, references=None, extra=None):
    """按类别归一化的最大范数误差估计。

    ``x_old`` 是 accepted state，``x_full`` 是整步解，``x_fine`` 是细步解；三者等长。
    ``categories[i]`` 是第 i 个状态的类别（mass/energy/temperature/...），``atol`` 为类别→atol 映射。
    ``references`` 给出中心化参考（能量的冻结参考态）；``extra`` 是额外派生检查，形如
    ``{名称: (full, fine, atol)}``，例如容器压力。派生量不是积分状态，只比较整步与细步，
    并以 atol 与两解的量级归一化。
    """
    old = np.asarray(x_old, dtype=float)
    full = np.asarray(x_full, dtype=float)
    fine = np.asarray(x_fine, dtype=float)
    if old.shape != full.shape or old.shape != fine.shape:
        raise ValueError('整步、细步与 accepted state 长度不一致')
    categories = list(categories)
    if len(categories) != old.size:
        raise ValueError('误差类别数量与状态向量长度不一致')
    reference = np.zeros_like(old) if references is None else np.asarray(references, dtype=float)
    if reference.shape != old.shape:
        raise ValueError('能量中心化参考长度与状态向量不一致')
    scale = np.empty_like(old)
    for i, category in enumerate(categories):
        scale[i] = atol[category] + rtol * max(abs(old[i] - reference[i]), abs(fine[i] - reference[i]))
    ratio = np.abs(fine - full) / scale
    by_category = {}
    for category in set(categories):
        mask = np.array([c == category for c in categories])
        by_category[category] = float(np.max(ratio[mask])) if mask.any() else 0.
    extras = {}
    for name, (extra_full, extra_fine, extra_atol) in (extra or {}).items():
        extras[name] = float(abs(extra_fine - extra_full) /
                             (extra_atol + rtol * max(abs(extra_full), abs(extra_fine))))
    norm = max([float(np.max(ratio)) if ratio.size else 0., *extras.values()])
    return ErrorEstimate(norm=norm, by_category=by_category, extra=extras)


class StepController:
    """建议下一步长；只在建议层面有界，不接触任何物理状态。"""

    def __init__(self, config):
        self.config = config

    def clamp(self, h):
        return min(self.config.max_step_s, max(self.config.min_step_s, h))

    def next(self, h, error_norm):
        if not np.isfinite(error_norm) or error_norm < 0:
            raise ValueError('误差范数必须为有限非负数')
        factor = self.config.growth if error_norm == 0 else self.config.safety * error_norm ** -0.5
        factor = min(self.config.growth, max(self.config.shrink, factor))
        return self.clamp(h * factor)

    def shrink(self, h):
        return self.clamp(h * self.config.shrink)


@dataclass
class StepStatistics:
    """接受/拒绝计数与步长序列；`sequence` 用于复现性与证据，不进入运行快照。"""

    accepted: int = 0
    rejected: int = 0
    solver_failures: int = 0
    boundary_truncations: int = 0
    min_step_hits: int = 0
    max_error_norm: float = 0.
    last_h: float = 0.
    sequence: list[float] = field(default_factory=list)
    frame_accepted: int = 0
    frame_rejected: int = 0
    frame_solver_failures: int = 0
    frame_boundary: int = 0
    frame_max_error: float = 0.
    frame_min_h: float = float('inf')
    frame_max_h: float = 0.

    def accept(self, h, error_norm, *, boundary):
        self.accepted += 1
        self.max_error_norm = max(self.max_error_norm, error_norm)
        self.last_h = h
        self.sequence.append(h)
        self.frame_accepted += 1
        if boundary:
            self.boundary_truncations += 1
            self.frame_boundary += 1
        self.frame_max_error = max(self.frame_max_error, error_norm)
        self.frame_min_h = min(self.frame_min_h, h)
        self.frame_max_h = max(self.frame_max_h, h)

    def reject(self, error_norm):
        self.rejected += 1
        self.max_error_norm = max(self.max_error_norm, error_norm)
        self.frame_rejected += 1
        self.frame_max_error = max(self.frame_max_error, error_norm)

    def fixed_step(self, h):
        """旧固定步长路径的计数；只记录，不改变任何数值结果。"""
        self.accepted += 1
        self.last_h = h
        self.frame_accepted += 1
        self.frame_min_h = min(self.frame_min_h, h)
        self.frame_max_h = max(self.frame_max_h, h)

    def solver_failure(self):
        self.solver_failures += 1
        self.frame_solver_failures += 1

    def min_step_hit(self):
        self.min_step_hits += 1

    def frame_metrics(self, *, adaptive, fixed_step):
        """本帧的稳定指标键（见模块 docstring）；固定步长路径用记录到的实际步长。"""
        if not adaptive:
            return {'timestep_adaptive': 0,
                    'internal_step_s': self.last_h if self.last_h else fixed_step,
                    'internal_steps': self.frame_accepted,
                    'internal_rejections': 0, 'solver_retries': self.frame_solver_failures,
                    'boundary_truncations': 0, 'local_error_norm_max': 0.,
                    'internal_steps_total': self.accepted, 'internal_rejections_total': 0,
                    'accepted_step_min_s': self.frame_min_h if self.frame_min_h != float('inf') else 0.,
                    'accepted_step_max_s': self.frame_max_h}
        return {'timestep_adaptive': 1, 'internal_step_s': self.last_h, 'internal_steps': self.frame_accepted,
                'internal_rejections': self.frame_rejected, 'solver_retries': self.frame_solver_failures,
                'boundary_truncations': self.frame_boundary, 'local_error_norm_max': self.frame_max_error,
                'internal_steps_total': self.accepted, 'internal_rejections_total': self.rejected,
                'accepted_step_min_s': self.frame_min_h if self.frame_min_h != float('inf') else 0.,
                'accepted_step_max_s': self.frame_max_h}

    def end_frame(self):
        self.frame_accepted = self.frame_rejected = self.frame_solver_failures = 0
        self.frame_boundary = 0
        self.frame_max_error = 0.
        self.frame_min_h = float('inf')
        self.frame_max_h = 0.


class AdaptiveMarch:
    """把一个外部分段（已被输出/控制/边界截断）推进完的接受/拒绝循环。

    ``trial(h)`` 必须在 accepted state 上做整步与两个半步试算，返回 ``(payload, ErrorEstimate)``；
    ``accept(payload, h, error)`` 才允许提交细步路径。``trial`` 抛 :class:`TrialFailure` 表示
    求解失败（与误差拒绝分开计数）。
    """

    def __init__(self, config, stats=None):
        self.config = config
        self.controller = StepController(config)
        self.stats = stats if stats is not None else StepStatistics()
        self._next_h = config.max_step_s

    def reset(self):
        self._next_h = self.config.max_step_s

    def _epsilon(self, segment):
        return 1e-12 * max(1., abs(segment))

    def march(self, segment, trial, accept, *, time=0.):
        if not (np.isfinite(segment) and segment > 0):
            raise ValueError('内部推进分段必须为有限正数')
        remaining = float(segment)
        intent = self._next_h
        while remaining > self._epsilon(segment):
            h = min(intent, remaining)
            # 边界截断：本步终点落在输出/控制/日程/启停边界上，或剩余不足一个内部步。
            boundary = h < intent - self._epsilon(intent)
            try:
                payload, error = trial(h)
            except TrialFailure as failure:
                self.stats.solver_failure()
                intent = self.controller.shrink(h)
                if intent >= h or h <= self.config.min_step_s * (1 + 1e-12):
                    self.stats.min_step_hit()
                    raise TimeStepExhausted(
                        f't={time + (segment - remaining):g}s 内部步 {h:g}s 求解失败，'
                        f'已缩小到最小步长 {self.config.min_step_s:g}s：{failure}',
                        time=time + (segment - remaining), h=h, error_norm=float('inf'),
                        boundary=boundary, cause=failure) from failure
                continue
            if error.norm <= 1.:
                accept(payload, h, error)
                remaining -= h
                self.stats.accept(h, error.norm, boundary=boundary)
                # 被边界截断的步不代表精度允许的步长上限，用截断前的意图步长做建议基准。
                self._next_h = self.controller.next(intent if boundary else h, error.norm)
                intent = self._next_h
            else:
                self.stats.reject(error.norm)
                intent = self.controller.shrink(h)
                if intent >= h or h <= self.config.min_step_s * (1 + 1e-12):
                    self.stats.min_step_hit()
                    raise TimeStepExhausted(
                        f't={time + (segment - remaining):g}s 内部步 {h:g}s 的局部误差范数 '
                        f'{error.norm:.3g} > 1，且已到最小步长 {self.config.min_step_s:g}s；'
                        '不放宽 atol/rtol，保留已接受历史后停止',
                        time=time + (segment - remaining), h=h, error_norm=error.norm, boundary=boundary)
