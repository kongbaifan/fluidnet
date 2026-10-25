from __future__ import annotations

from contextlib import nullcontext
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
from functools import lru_cache

import CoolProp.CoolProp as CP
from CoolProp import AbstractState

from .models import FluidConfig, FluidState


class PropertyError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


# CoolProp phase indices -> the lowercase names PhaseSI reports: "liquid", "gas",
# "supercritical_gas", "twophase", ... The phase policy matches on these substrings.
_PHASE_NAMES = {getattr(CP, name): name[len("iphase_"):] for name in dir(CP) if name.startswith("iphase_")}
_TWO_PHASE = "twophase"

# Fluid strings: "Water" (HEOS), "HEOS::R134a", "IF97::Water", "INCOMP::MEG[0.3]" (mass fraction),
# "REFPROP::WATER", "REFPROP::R407C.MIX", "REFPROP::AMMONIA[0.3]&WATER[0.7]" (FluidConfig.reference).
_BACKENDS = ("HEOS", "INCOMP", "IF97", "REFPROP")

# NIST REFPROP 是按用户许可的商业软件，不随仓库提交：REFPRP64.DLL 必须与同版本 fluids/、
# mixtures/ 配套（DLL 读到另一版本的工质文件会在 Fortran 里直接终止整个进程）。
# 查找顺序：FLUIDNET_REFPROP_PATH 显式覆盖 → 项目/仓库内捆绑目录 → Windows 默认安装目录。
# 仅在持有合法 NIST 许可时使用/随包分发 vendor/ 捆绑目录。
REFPROP_DEFAULT = Path(r'C:\Program Files (x86)\REFPROP')
REFPROP_LIBRARY = 'REFPRP64.DLL'
# 捆绑目录布局：项目根 vendor/refprop9.1/（REFPRP64.DLL + fluids/ + mixtures/ + refprop-manifest.json）。
REFPROP_ENV = 'FLUIDNET_REFPROP_PATH'
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIRNAME = 'vendor'
BUNDLE_REFPROP_NAME = 'refprop9.1'
BUNDLE_MANIFEST = 'refprop-manifest.json'
# 每个 base 下的捆绑目录，按优先级排列：契约布局在前，兼容旧版/别名目录在后。
BUNDLE_LAYOUTS = (f'{BUNDLE_DIRNAME}/{BUNDLE_REFPROP_NAME}', BUNDLE_REFPROP_NAME, 'refprop', 'NISTRefprop9.1')
# The DLL keeps one global fluid setup: every REFPROP call is serialized.
_refprop_lock = threading.RLock()
# Fluids already loaded once in a throw-away process (see _probe_refprop). Worker processes are
# started only after the API process compiled the project, so they skip the probe.
PROBE_REFPROP = True
_probed: dict[tuple, str | None] = {}
_configured: list[Path] = []

# AbstractState holds the last flash internally, so each thread keeps its own
# instance per fluid; the solver runs on a 2-thread executor.
_thread_states = threading.local()

FluidKey = tuple[str, str, tuple[float, ...], str]  # (backend, fluid name(s), fractions, "mass" | "mole")


def _label(key: FluidKey) -> str:
    backend, name, fractions, _ = key
    if "&" in name:
        text = "&".join(f"{part}[{x:g}]" for part, x in zip(name.split("&"), fractions))
    else:
        text = f"{name}[{','.join(f'{x:g}' for x in fractions)}]" if fractions else name
    return text if backend == "HEOS" else f"{backend}::{text}"


def _absolute(path: Path | str) -> Path:
    """绝对路径；目录不存在也返回（resolve 不要求路径存在）。"""
    try:
        return Path(path).resolve()
    except (OSError, RuntimeError):  # pragma: no cover - 悬空符号链接等极端情况
        return Path(os.path.abspath(path))


def _dedupe(paths) -> list[Path]:
    """去重保序。Windows 大小写不敏感，用 normcase 后的绝对路径当键。"""
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = os.path.normcase(str(_absolute(path)))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _is_refprop_installation(root: Path) -> bool:
    """可用安装的判定：有 REFPRP64.DLL，且有 fluids/ 或 FLUIDS/ 工质目录。"""
    return (root / REFPROP_LIBRARY).is_file() and any((root / name).is_dir() for name in ('fluids', 'FLUIDS'))


def _bundle_bases() -> list[Path]:
    """可能存放捆绑 REFPROP 的基目录：项目根、仓库根、当前工作目录、解释器目录；去重保序。"""
    return _dedupe([PROJECT_ROOT, PROJECT_ROOT.parent, Path.cwd(), Path(sys.executable).parent])


def refprop_candidates() -> list[Path]:
    """按发现优先级列出 REFPROP 候选目录（去重保序），供诊断与测试使用。

    顺序即契约：FLUIDNET_REFPROP_PATH（显式覆盖）→ 各 base 下的捆绑布局 → Windows 默认安装。
    """
    env_root = os.environ.get(REFPROP_ENV)
    candidates = [Path(env_root)] if env_root else []
    candidates.extend(base / layout for base in _bundle_bases() for layout in BUNDLE_LAYOUTS)
    candidates.append(REFPROP_DEFAULT)
    return _dedupe(candidates)


def refprop_root() -> Path | None:
    """可用 REFPROP 目录；没有则 None。候选顺序见 refprop_candidates()。

    FLUIDNET_REFPROP_PATH 是显式覆盖：指向无效目录时视为未安装、不回退到捆绑或系统目录，
    否则用户以为在用自己的安装，实际却静默加载了另一套 DLL 与工质文件。
    """
    candidates = refprop_candidates()
    if os.environ.get(REFPROP_ENV):
        candidates = candidates[:1]
    return next((root for root in candidates if _is_refprop_installation(root)), None)


def _refprop_source(root: Path) -> str | None:
    """来源分类：env（环境变量显式覆盖）/ bundled（捆绑目录）/ system（默认安装）。"""
    target = _absolute(root)
    env_root = os.environ.get(REFPROP_ENV)
    if env_root and target == _absolute(env_root):
        return 'env'
    if target in {_absolute(base / layout) for base in _bundle_bases() for layout in BUNDLE_LAYOUTS}:
        return 'bundled'
    if target == _absolute(REFPROP_DEFAULT):
        return 'system'
    return None


def _bundle_version(root: Path) -> str | None:
    """捆绑目录 refprop-manifest.json 的版本；清单缺失或损坏时 None（不影响 installed）。"""
    try:
        manifest = json.loads((root / BUNDLE_MANIFEST).read_text(encoding='utf-8'))
        version = manifest.get('version') if isinstance(manifest, dict) else None
    except Exception:
        return None
    return str(version) if version not in (None, '') else None


def refprop_info() -> dict[str, object]:
    """运行时 REFPROP 发现结果，供 /api/v1/health 上报；此函数不加载 DLL。"""
    root = refprop_root()
    if root is None:
        return {'installed': False, 'source': None, 'path': None, 'version': None}
    return {'installed': True, 'source': _refprop_source(root), 'path': str(_absolute(root)), 'version': _bundle_version(root)}


def _configure_refprop() -> Path:
    root = refprop_root()
    if root is None:
        raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", "未找到 REFPROP：需要用户自备 NIST 许可的 REFPRP64.DLL 及同版本 fluids、"
                            f"mixtures 目录，可放在项目根 {BUNDLE_DIRNAME}/{BUNDLE_REFPROP_NAME}（仅在持有合法 NIST 许可时随包分发）、"
                            f"用环境变量 {REFPROP_ENV} 指定，或安装到默认目录 {REFPROP_DEFAULT}")
    if _configured and _configured[0] != root:
        raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"REFPROP 已从 {_configured[0]} 加载，同一进程不能切换目录")
    if not _configured:
        CP.set_config_string(CP.ALTERNATIVE_REFPROP_PATH, str(root) + os.sep)
        CP.set_config_string(CP.ALTERNATIVE_REFPROP_LIBRARY_PATH, str(root / REFPROP_LIBRARY))
        _configured.append(root)
    return root


_PROBE = r"""
import sys, CoolProp.CoolProp as CP
root, name, basis, fractions = sys.argv[1], sys.argv[2], sys.argv[3], [float(x) for x in sys.argv[4:]]
CP.set_config_string(CP.ALTERNATIVE_REFPROP_PATH, root)
CP.set_config_string(CP.ALTERNATIVE_REFPROP_LIBRARY_PATH, root + 'REFPRP64.DLL')
state = CP.AbstractState('REFPROP', name)
if fractions:
    (state.set_mass_fractions if basis == 'mass' else state.set_mole_fractions)(fractions)
print(CP.get_global_param_string('REFPROP_version'))
"""


def _probe_refprop(key: FluidKey) -> None:
    """Load the fluid once in a child process first; a version mismatch kills that process, not ours."""
    if not PROBE_REFPROP or key in _probed:
        return
    root = _configure_refprop()
    _, name, fractions, basis = key
    try:
        done = subprocess.run([sys.executable, "-c", _PROBE, str(root) + os.sep, name, basis, *map(repr, fractions)],
                              capture_output=True, text=True, timeout=60, env=os.environ.copy())
    except subprocess.TimeoutExpired as exc:
        raise PropertyError("PROPERTY_FAILURE", f"REFPROP 加载 {_label(key)} 超时") from exc
    if done.returncode != 0:
        tail = (done.stderr or done.stdout).strip().splitlines()
        reason = next((line for line in tail if "forrtl" in line or "rror" in line), tail[-1] if tail else "")
        if "Could not load these fluids" in reason or "not found" in reason or "file" in reason.lower() and "open" in reason.lower():
            raise PropertyError("FLUID_UNKNOWN", f"REFPROP 找不到工质 {_label(key)}：{reason}")
        raise PropertyError("PROPERTY_FAILURE", f"REFPROP 无法加载 {_label(key)}（DLL 与 fluids 目录版本不一致时会这样）：{reason}")
    _probed[key] = done.stdout.strip() or None


def _lock(key: FluidKey):
    return _refprop_lock if key[0] == "REFPROP" else nullcontext()


def _abstract_state(key: FluidKey) -> AbstractState:
    states = getattr(_thread_states, "states", None)
    if states is None:
        states = _thread_states.states = {}
    state = states.get(key)
    if state is None:
        backend, name, fractions, basis = key
        if backend == "REFPROP":
            _probe_refprop(key)
            _configure_refprop()
        try:
            with _lock(key):
                state = AbstractState(backend, name)
                if fractions:
                    (state.set_mole_fractions if basis == "mole" else state.set_mass_fractions)(list(fractions))
        except Exception as exc:
            if "not found" in str(exc) or "could not be found" in str(exc) or "unable to open" in str(exc).lower():
                raise PropertyError("FLUID_UNKNOWN", f"未知工质 {_label(key)}：{exc}") from exc
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法加载工质 {_label(key)}：{exc}") from exc
        states[key] = state
    return state


def _phase_of(key: FluidKey, state: AbstractState) -> str:
    # INCOMP solutions do not implement calc_phase; they are liquids by construction.
    if key[0] == "INCOMP":
        return "liquid"
    if key[0] == "REFPROP" and _is_mixture(key):
        # The REFPROP backend has no calc_phase for mixtures; its quality is < 0 (subcooled),
        # within [0, 1] (two-phase or saturated) or > 1 (superheated) and decides the phase.
        quality = float(state.Q())
        if state.T() > state.T_critical() and state.p() > state.p_critical():
            return "supercritical"
        if 0.0 <= quality <= 1.0:
            return _TWO_PHASE
        return "liquid" if quality < 0 else "gas"
    return _PHASE_NAMES.get(state.phase(), "unknown")


def _is_mixture(key: FluidKey) -> bool:
    return "&" in key[1] or key[1].upper().endswith(".MIX")


def _optional(read):
    """A property CoolProp may not define for this backend/state (speed of sound in two-phase, INCOMP)."""
    try:
        value = float(read())
    except Exception:
        return None
    return value if math.isfinite(value) else None


# (CoolProp input pair, argument order) for each supported query. `first`/`second` follow the
# method signatures: PT -> (p, T), PH -> (p, h), PS -> (p, s), PQ -> (p, Q), TQ -> (T, Q), DU -> (rho, u).
_INPUTS = {
    "PT": (CP.PT_INPUTS, lambda a, b: (a, b)),
    "PH": (CP.HmassP_INPUTS, lambda a, b: (b, a)),
    "PS": (CP.PSmass_INPUTS, lambda a, b: (a, b)),
    "PQ": (CP.PQ_INPUTS, lambda a, b: (a, b)),
    "TQ": (CP.QT_INPUTS, lambda a, b: (b, a)),
    "DU": (CP.DmassUmass_INPUTS, lambda a, b: (a, b)),
}


@lru_cache(maxsize=32768)
def _flash(key: FluidKey, inputs: str, first: float, second: float) -> FluidState:
    """One CoolProp flash per distinct input, shared by every phase policy of this fluid."""
    if key[0] == "INCOMP" and inputs in ("PQ", "TQ"):
        raise PropertyError("PROPERTY_FAILURE", f"{_label(key)} 是不可压溶液，没有饱和（汽液）状态")
    pair, order = _INPUTS[inputs]
    with _lock(key):
        return _flash_locked(key, inputs, pair, order, first, second)


def _flash_locked(key: FluidKey, inputs: str, pair, order, first: float, second: float) -> FluidState:
    try:
        state = _abstract_state(key)
        state.update(pair, *order(first, second))
        phase = _phase_of(key, state)
        quality = float(state.Q()) if phase == _TWO_PHASE else None
        # Strictly inside the dome there is no single viscosity, conductivity, cp or cv;
        # CoolProp would return one-sided values, so they are reported as missing. On the
        # saturation lines (Q = 0 or 1) they exist and are read when CoolProp provides them.
        inside_dome = quality is not None and 0.0 < quality < 1.0
        on_line = quality is not None and not inside_dome

        def transport(read):
            if inside_dome:
                return None
            # REFPROP has no transport equations for some fluids and mixtures (e.g. ammonia–water):
            # missing, not a failed state. Hydraulics reject a fluid without viscosity separately.
            return _optional(read) if on_line or key[0] == "REFPROP" else float(read())

        values = {
            "pressure_pa": float(state.p()) if inputs in ("TQ", "DU") else first,
            "temperature_k": second if inputs == "PT" else first if inputs == "TQ" else float(state.T()),
            "enthalpy_j_kg": second if inputs == "PH" else float(state.hmass()),
            "density_kg_m3": first if inputs == "DU" else float(state.rhomass()),
            "viscosity_pa_s": transport(state.viscosity),
            "specific_heat_j_kg_k": transport(state.cpmass),
            "thermal_conductivity_w_m_k": transport(state.conductivity),
            "entropy_j_kg_k": second if inputs == "PS" else _optional(state.smass),
            "internal_energy_j_kg": _optional(state.umass),
            "cv_j_kg_k": None if inside_dome else _optional(state.cvmass),
            "speed_of_sound_m_s": None if inside_dome else _optional(state.speed_sound),
        }
    except Exception as exc:
        if inputs == "PH":
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法从压力/焓计算状态：{exc}") from exc
        raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法计算 {_label(key)} 的状态：{exc}") from exc
    numbers = [value for value in values.values() if value is not None] + ([quality] if quality is not None else [])
    if not all(math.isfinite(value) for value in numbers):
        raise PropertyError("PROPERTY_FAILURE", "CoolProp 返回了非有限物性值")
    return FluidState(phase=phase, quality=quality, **values)


def _check_phase(policy: str, state: FluidState) -> None:
    phase = state.phase
    if policy == "liquid" and ("gas" in phase or phase == _TWO_PHASE):
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相液体约束")
    if policy == "gas" and ("liquid" in phase or phase == _TWO_PHASE):
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相气体约束")
    if policy == "single_phase" and phase == _TWO_PHASE:
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相约束")


def _fractions(text: str, raw: str, what: str) -> tuple[float, ...]:
    try:
        values = tuple(float(part) for part in raw.split(","))
    except ValueError as exc:
        raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的{what}不是数值") from exc
    if not all(math.isfinite(x) and 0.0 < x < 1.0 for x in values):
        raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的{what}必须在 (0, 1) 内")
    return values


def _parse_fluid(config: FluidConfig) -> FluidKey:
    """'Water' / 'HEOS::R134a' / 'IF97::Water' / 'INCOMP::MEG[0.3]' (mass fraction) /
    'REFPROP::R407C.MIX' / 'REFPROP::AMMONIA[0.3]&WATER[0.7]' (fractions on `config.reference`)
    -> (backend, name, fractions, basis)."""
    if config.composition:
        # Arbitrary component fractions need a mixture setup (mole fractions, fragile
        # two-phase flashes). Keep this explicit instead of silently ignoring them.
        raise PropertyError("COMPOSITION_UNSUPPORTED", "组分请写在工质字符串里，如 REFPROP::AMMONIA[0.3]&WATER[0.7]；composition 字段尚未使用")
    text = config.fluid.strip()
    backend, name = ("HEOS", text)
    if "::" in text:
        prefix, name = text.split("::", 1)
        backend = prefix.strip().upper()
        if backend not in _BACKENDS:
            raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {prefix} 尚未启用；可用 {'、'.join(_BACKENDS)}")
    name = name.strip()
    if backend == "REFPROP":
        if refprop_root() is None:
            _configure_refprop()  # raises PROPERTY_BACKEND_UNSUPPORTED with the install hint
        if "&" in name:
            parts: list[str] = []
            component_fractions: list[float] = []
            for part in name.split("&"):
                part = part.strip()
                if not part.endswith("]") or part.count("[") != 1:
                    raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的混合物写法应为 A[0.3]&B[0.7]")
                component, raw = part[:-1].split("[", 1)
                parts.append(component.strip())
                component_fractions.extend(_fractions(text, raw, "组分比例"))
            if len(component_fractions) != len(parts) or not all(parts) or abs(sum(component_fractions) - 1.0) > 1e-6:
                raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的组分比例之和必须为 1")
            return backend, "&".join(parts), tuple(component_fractions), config.reference
        if "[" in name:
            raise PropertyError("COMPOSITION_UNSUPPORTED", f"{text}：REFPROP 纯质不写比例；混合物写 A[0.3]&B[0.7] 或预定义的 名称.MIX")
        if not name:
            raise PropertyError("FLUID_UNKNOWN", "工质名称为空")
        return backend, name, (), "mass"
    if "&" in name:
        raise PropertyError("COMPOSITION_UNSUPPORTED", f"{text}：HEOS 混合物尚未接入；混合物请用 REFPROP::A[0.3]&B[0.7]，INCOMP 溶液可写质量分数")
    fractions: tuple[float, ...] = ()
    if "[" in name:
        if not name.endswith("]") or name.count("[") != 1:
            raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的质量分数写法应为 名称[0.3]")
        name, raw = name[:-1].split("[", 1)
        name = name.strip()
        fractions = _fractions(text, raw, "质量分数")
    if fractions and backend != "INCOMP":
        raise PropertyError("COMPOSITION_UNSUPPORTED", f"{text}：只有 INCOMP 溶液可以写质量分数；HEOS 混合物尚未接入")
    if not name:
        raise PropertyError("FLUID_UNKNOWN", "工质名称为空")
    return backend, name, fractions, "mass"


def _freezing_point(key: FluidKey, state: AbstractState, t_min: float, t_max: float) -> float:
    """INCOMP solutions reject temperatures below their concentration-dependent freezing point
    without exposing it; locate it by bisection at atmospheric pressure."""
    last_error: list[str] = []

    def accepts(temperature):
        try:
            state.update(CP.PT_INPUTS, 101325.0, temperature)
            return True
        except Exception as exc:
            last_error[:] = [str(exc)]
            return False
    if accepts(t_min):
        return t_min
    if not accepts(t_max):
        # Usually a mass fraction outside the correlation's range; CoolProp's message says which.
        reason = last_error[0] if last_error else ''
        raise PropertyError("PROPERTY_RANGE", f"{_label(key)} 在其温度范围内没有有效状态，请检查质量分数（CoolProp：{reason}）")
    low, high = t_min, t_max
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (low, middle) if accepts(middle) else (middle, high)
        if high - low < 1e-7:
            break
    return high


@lru_cache(maxsize=256)
def _limits(key: FluidKey) -> tuple[float, float, float | None]:
    with _lock(key):
        return _limits_locked(key)


def _limits_locked(key: FluidKey) -> tuple[float, float, float | None]:
    state = _abstract_state(key)
    try:
        t_min, t_max = float(state.Tmin()), float(state.Tmax())
        if key[0] == "INCOMP":
            # A water-glycol mixture freezes well above the correlation's Tmin.
            return _freezing_point(key, state, t_min, t_max), t_max, None
        return t_min, t_max, _optional(state.pmax)
    except PropertyError:
        raise
    except Exception as exc:
        raise PropertyError("PROPERTY_FAILURE", f"无法读取 {_label(key)} 的适用范围：{exc}") from exc


def _finite(*values: float, message: str = "物性输入必须是有限数") -> None:
    if not all(math.isfinite(value) for value in values):
        raise PropertyError("PROPERTY_RANGE", message)


def humid_air(temperature: float, pressure: float, relative_humidity: float) -> dict[str, float]:
    """Moist-air psychrometrics (CoolProp HAPropsSI) for module code; not part of the network solve.

    Returns humidity ratio (kg water / kg dry air), dew point, wet bulb (K) and enthalpy per kg dry air.
    """
    temperature, pressure, relative_humidity = float(temperature), float(pressure), float(relative_humidity)
    _finite(temperature, pressure, relative_humidity)
    if temperature <= 0 or pressure <= 0 or not 0.0 < relative_humidity <= 1.0:
        raise PropertyError("PROPERTY_RANGE", "湿空气输入要求温度、压力为正，相对湿度在 (0, 1] 内")
    inputs = ("T", temperature, "P", pressure, "R", relative_humidity)
    try:
        return {
            "humidity_ratio_kg_kg": float(CP.HAPropsSI("W", *inputs)),
            "dew_point_k": float(CP.HAPropsSI("D", *inputs)),
            "wet_bulb_k": float(CP.HAPropsSI("B", *inputs)),
            "enthalpy_j_kg_dry_air": float(CP.HAPropsSI("H", *inputs)),
            "relative_humidity": relative_humidity,
        }
    except Exception as exc:
        raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法计算湿空气状态：{exc}") from exc


class CoolPropPropertyService:
    """CoolProp adapter used by the solver and by module contexts (`ctx.fluid`).

    The service deliberately exposes a small stable surface. Modules do not
    import CoolProp directly, so a REFPROP or project-specific backend can be
    added later without changing module code.
    """

    backend = "coolprop"

    def __init__(self, config: FluidConfig):
        if config.backend != "coolprop":
            raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {config.backend} 尚未启用")
        self.config = config
        self.key = _parse_fluid(config)
        self.fluid = config.fluid
        backend, name, fractions, _ = self.key
        # Components on the configured basis; a predefined REFPROP .MIX file reports itself.
        self.composition = dict(zip(name.split("&"), fractions)) if "&" in name else {self.fluid: 1.0}
        self.phase_policy = config.phase_policy

    def _result(self, state: FluidState, check_phase: bool = True) -> FluidState:
        if check_phase:
            _check_phase(self.phase_policy, state)
        # The flash cache is shared; hand out a copy so callers cannot alter it.
        return state.model_copy(update={"composition": dict(self.composition)})

    def state_pt(self, pressure: float, temperature: float) -> FluidState:
        pressure, temperature = float(pressure), float(temperature)
        _finite(pressure, temperature)
        if pressure <= 0 or temperature <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力和温度必须为正数")
        return self._result(_flash(self.key, "PT", pressure, temperature))

    def state_ph(self, pressure: float, enthalpy: float) -> FluidState:
        pressure, enthalpy = float(pressure), float(enthalpy)
        _finite(pressure, enthalpy)
        if pressure <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数")
        return self._result(_flash(self.key, "PH", pressure, enthalpy))

    def state_ps(self, pressure: float, entropy: float) -> FluidState:
        """State from pressure and specific entropy, e.g. an isentropic compressor outlet."""
        pressure, entropy = float(pressure), float(entropy)
        _finite(pressure, entropy)
        if pressure <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数")
        return self._result(_flash(self.key, "PS", pressure, entropy))

    # Saturation queries are explicit two-phase requests, so the phase policy does not apply.
    def state_pq(self, pressure: float, quality: float) -> FluidState:
        pressure, quality = float(pressure), float(quality)
        _finite(pressure, quality)
        if pressure <= 0 or not 0.0 <= quality <= 1.0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数，干度在 [0, 1] 内")
        return self._result(_flash(self.key, "PQ", pressure, quality), check_phase=False)

    def state_tq(self, temperature: float, quality: float) -> FluidState:
        temperature, quality = float(temperature), float(quality)
        _finite(temperature, quality)
        if temperature <= 0 or not 0.0 <= quality <= 1.0:
            raise PropertyError("PROPERTY_RANGE", "温度必须为正数，干度在 [0, 1] 内")
        return self._result(_flash(self.key, "TQ", temperature, quality), check_phase=False)

    def state_du(self, density: float, internal_energy: float) -> FluidState:
        """State of a closed volume from mean density and specific internal energy (lumped vessels).

        The result may be two-phase; callers decide which phases they accept, so the policy does not apply."""
        density, internal_energy = float(density), float(internal_energy)
        _finite(density, internal_energy)
        if density <= 0:
            raise PropertyError("PROPERTY_RANGE", "密度必须为正数")
        return self._result(_flash(self.key, "DU", density, internal_energy), check_phase=False)

    def saturation_t(self, pressure: float) -> float:
        """Saturation temperature (K) at the given pressure; the bubble point for a mixture
        (zeotropic mixtures glide: state_pq(p, 1).temperature_k is the dew point)."""
        return self.state_pq(pressure, 0.0).temperature_k

    def saturation_p(self, temperature: float) -> float:
        """Saturation pressure (Pa) at the given temperature; the bubble pressure for a mixture."""
        return self.state_tq(temperature, 0.0).pressure_pa

    def limits(self) -> dict[str, float | None]:
        """Validity range of this fluid: t_min_k (INCOMP: freezing point), t_max_k, p_max_pa (None if unknown)."""
        t_min, t_max, p_max = _limits(self.key)
        return {"t_min_k": t_min, "t_max_k": t_max, "p_max_pa": p_max}

    def humid_air(self, temperature: float, pressure: float, relative_humidity: float) -> dict[str, float]:
        return humid_air(temperature, pressure, relative_humidity)


_services: dict[tuple[str, FluidKey, str], CoolPropPropertyService] = {}
_services_lock = threading.Lock()


def is_pure_water(config: FluidConfig) -> bool:
    """True for every spelling of pure water (Water, water, HEOS::Water, IF97::Water).

    The hydraulics use fixed reference water properties for these, so all spellings must
    give identical results. An unparseable fluid string is simply "not water" here.
    """
    try:
        backend, name, fractions, _ = _parse_fluid(config)
    except PropertyError:
        return False
    return backend in ("HEOS", "IF97") and name.lower() == "water" and not fractions


def property_service(config: FluidConfig) -> CoolPropPropertyService:
    # Same check order as before: backend, then composition / fluid string.
    if config.backend != "coolprop":
        raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {config.backend} 尚未启用")
    key = (config.backend, _parse_fluid(config), config.phase_policy)
    with _services_lock:
        service = _services.get(key)
        if service is None:
            service = _services[key] = CoolPropPropertyService(config)
    return service
