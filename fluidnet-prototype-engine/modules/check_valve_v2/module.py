import math

# V2 冻结语义（docs/MODULES_P0.md §5.1–§5.3）：
#   Δp = p_in − p_out；正向开启压差 p_crack_pa；
#   Δp ≤ p_crack 时 opening_ratio 精确返回 0.0（求解器把它变成 flow == 0 约束），
#   反向因此是精确零流；Δp > p_crack 时
#   opening = opening_max·sqrt(1 − p_crack/Δp)，等价于物理曲线
#   q_vol = Kv·opening_max·sqrt((Δp − p_crack)/(1e5·ρ/1000))。
# 本文件自包含（只 import math），与 backend/fn_engine/check_valve.py 的独立解析参考
# 逐点对照由 tests/test_check_valve_numerics.py 负责，不靠人工同步。


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("is_open", False)
        ctx.state.setdefault("closed_steps", 0)
        ctx.state.setdefault("open_steps", 0)
        ctx.state.setdefault("throughput_kg", 0.0)
        ctx.state.setdefault("reverse_throughput_kg", 0.0)
        ctx.state.setdefault("last_direction", 0)
        ctx.state.setdefault("deprecation_warned", False)

    # ---- 参数与判据（纯函数式；只用参数、端口与只读 state） --------------------
    @staticmethod
    def _number(ctx, name, default):
        value = ctx.parameter(name, default)
        try:
            number = default if value is None else float(value)
        except (TypeError, ValueError):
            raise ValueError(f"止回阀参数 {name} 必须是数值：{value!r}") from None
        if not math.isfinite(number):
            raise ValueError(f"止回阀参数 {name} 必须是有限数值：{value!r}")
        return number

    def _delta_p(self, ctx):
        """进出口压差 p_in − p_out；端口压力未知时返回 None。"""
        inlet = ctx.port("in0").pressure_pa
        outlet = ctx.port("out0").pressure_pa
        if inlet is None or outlet is None:
            return None
        return float(inlet) - float(outlet)

    @staticmethod
    def _opening_max(ctx):
        return min(1.0, max(0.0, Module._number(ctx, "opening_ratio", 1.0)))

    @staticmethod
    def _crack(ctx):
        return max(0.0, Module._number(ctx, "p_crack_pa", 0.0))

    @staticmethod
    def _hysteresis(ctx):
        return max(0.0, Module._number(ctx, "hysteresis_pa", 0.0))

    @classmethod
    def _is_open(cls, ctx, delta_p, was_open):
        """Δp ≤ 0 恒关（保证反向精确零流）；h=0 时与 accepted state 无关。"""
        if delta_p is None or delta_p <= 0.0:
            return False
        crack, band = cls._crack(ctx), cls._hysteresis(ctx)
        if band <= 0.0:
            return delta_p > crack
        if not was_open:
            return delta_p > crack + band
        return delta_p > max(0.0, crack - band)

    @classmethod
    def _opening(cls, ctx, delta_p, was_open):
        """evaluate/commit 共用：返回精确 0.0（关闭）或 (0, opening_max] 的开度。"""
        opening_max = cls._opening_max(ctx)
        if opening_max <= 0.0 or not cls._is_open(ctx, delta_p, was_open):
            return 0.0
        crack = cls._crack(ctx)
        if delta_p <= crack:  # 迟滞保持开启的亚开启压差段：滑阀已抬起，按全开处理
            return opening_max
        gate = math.sqrt(max(0.0, 1.0 - crack / delta_p))
        opening = min(1.0, max(0.0, opening_max * gate))
        return 0.0 if opening <= 0.0 else opening

    @staticmethod
    def _warn_legacy_parameter(ctx):
        """v1 的 cracking_pressure_pa 在 v2 中不参与计算，值非零时提示一次。"""
        legacy = Module._number(ctx, "cracking_pressure_pa", 0.0)
        if legacy != 0.0 and not ctx.state.get("deprecation_warned", False):
            ctx.diagnostic(
                "CHECK_VALVE_LEGACY_PARAMETER",
                f"cracking_pressure_pa={legacy:g} Pa 是 v1 的“容许反向流”参数，v2 不再使用；"
                "正向开启压差请改用 p_crack_pa，反向截止在 v2 中是精确零流。",
                severity="info",
            )

    def evaluate(self, ctx):
        self._warn_legacy_parameter(ctx)
        inlet = ctx.port("in0")
        density_kg_m3 = inlet.density_kg_m3 or self._number(ctx, "density_kg_m3", 998.2)
        delta_p = self._delta_p(ctx)
        was_open = bool(ctx.state.get("is_open", False))
        opening = self._opening(ctx, delta_p, was_open)

        # opening == 0 让求解器把支路当作零流量等式约束（精确截止，不做 1e-9 近似）。
        ctx.net.valve(
            channel="main",
            kv=self._number(ctx, "kv_m3_h", 50.0),
            opening=opening,
            density_kg_m3=density_kg_m3,
        )
        ctx.var("opening_ratio", opening)
        ctx.var("is_open", 1.0 if opening > 0.0 else 0.0)
        ctx.var("direction", 1.0 if (delta_p is not None and delta_p > 0.0) else -1.0)

    def commit_step(self, ctx, dt_s):
        """状态只在被接受的子步更新；迟滞状态机同样是纯转移函数。"""
        was_open = bool(ctx.state.get("is_open", False))
        delta_p = self._delta_p(ctx)
        is_open = self._is_open(ctx, delta_p, was_open)
        ctx.state["is_open"] = is_open
        if is_open:
            ctx.state["open_steps"] = int(ctx.state.get("open_steps", 0)) + 1
        else:
            ctx.state["closed_steps"] = int(ctx.state.get("closed_steps", 0)) + 1
        ctx.state["last_direction"] = 1 if (delta_p is not None and delta_p > 0.0) else -1
        ctx.state["deprecation_warned"] = True
        mass_flow_kg_s = ctx.channel("main").mass_flow_kg_s or 0.0
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + abs(mass_flow_kg_s) * dt_s
        ctx.state["reverse_throughput_kg"] = (
            float(ctx.state.get("reverse_throughput_kg", 0.0)) + min(0.0, mass_flow_kg_s) * dt_s
        )
        # 用收敛状态回写派生变量，保证动态帧与 accepted state 一致。
        ctx.var("opening_ratio", self._opening(ctx, delta_p, was_open))
        ctx.var("is_open", 1.0 if is_open else 0.0)
        ctx.var("direction", 1.0 if (delta_p is not None and delta_p > 0.0) else -1.0)

    def finalize(self, ctx):
        pass
