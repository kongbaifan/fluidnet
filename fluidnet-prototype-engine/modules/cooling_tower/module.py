"""冷却塔：逆流 ε-NTU 干工况换热 + 水侧圆管阻力。

参数已是规范单位（K/Pa/W/m³·s⁻¹/kg·s⁻¹）；evaluate 无副作用，状态只在 commit_step 更新。
"""

import math

# 与 backend/fn_engine/solver.py::pipe_drop 保持同一摩擦律；改动求解器时必须同步本函数。
def _pipe_drop(length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s, flow_kg_s):
    area = math.pi * diameter_m ** 2 / 4.0
    reynolds = abs(flow_kg_s) * diameter_m / (viscosity_pa_s * area)
    laminar = 32.0 * viscosity_pa_s * length_m * flow_kg_s / (density_kg_m3 * area * diameter_m ** 2)
    if reynolds <= 2300:
        return laminar
    friction = (-1.8 * math.log10((roughness_m / diameter_m / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2
    turbulent = friction * length_m / diameter_m * flow_kg_s * abs(flow_kg_s) / (2.0 * density_kg_m3 * area ** 2)
    blend = min(1.0, (reynolds - 2300.0) / 1700.0)
    return laminar * (1.0 - blend) + turbulent * blend


def _flow_from_pressure_drop(pressure_drop_pa, length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s):
    """二分反解与 pipe_drop 同一关系的 |m|；evaluate 阶段拿不到流量时使用。"""
    target = abs(pressure_drop_pa)
    if target <= 0.0:
        return 0.0
    low, high = 0.0, 1.0e4  # 覆盖常规水侧流量；越界按端点取值。
    for _ in range(80):
        middle = 0.5 * (low + high)
        drop = _pipe_drop(length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s, middle)
        if drop < target:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("thermal_energy_j", 0.0)

    def _mass_flow_kg_s(self, ctx):
        inlet = ctx.port("in0")
        if inlet.mass_flow_kg_s is not None:
            return abs(float(inlet.mass_flow_kg_s))
        pressure_in = inlet.pressure_pa
        pressure_out = ctx.port("out0").pressure_pa
        if pressure_in is None or pressure_out is None:
            ctx.diagnostic("CT_PRESSURE_UNKNOWN", "试算端口压力缺失，水侧流量按 0 处理，本帧不换热")
            return 0.0
        diameter_m = max(float(ctx.parameter("water_side_diameter_m", 0.1)), 1e-4)
        length_m = max(float(ctx.parameter("water_side_length_m", 2.0)), 1e-6)
        roughness_m = max(float(ctx.parameter("roughness_m", 1.5e-06)), 0.0)
        density_kg_m3 = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 998.2)), 1e-3)
        viscosity_pa_s = max(float(inlet.viscosity_pa_s or ctx.parameter("viscosity_pa_s", 0.001)), 1e-6)
        return abs(_flow_from_pressure_drop(
            pressure_in - pressure_out, length_m, diameter_m, roughness_m, density_kg_m3, viscosity_pa_s,
        ))

    @staticmethod
    def _idle_state(water_inlet_temperature_k, air_inlet_temperature_k, wet_bulb_temperature_k):
        """不换热时仍返回完整的温度/效能/逼近度，保证变量键齐全。"""
        return (
            0.0,
            water_inlet_temperature_k,
            air_inlet_temperature_k,
            0.0,
            water_inlet_temperature_k - wet_bulb_temperature_k,
        )

    def _thermal_state(self, ctx, mass_flow_kg_s=None):
        """Return (heat_flow_w, water_outlet_temperature_k, air_outlet_temperature_k, effectiveness, approach_k)."""
        inlet = ctx.port("in0")
        water_inlet_temperature_k = (
            inlet.temperature_k
            if inlet.temperature_k is not None
            else float(ctx.parameter("air_inlet_temperature_k", 300.15))
        )
        water_cp = float(inlet.specific_heat_j_kg_k or ctx.parameter("water_cp_j_kg_k", 4180.0))
        air_inlet_temperature_k = float(ctx.parameter("air_inlet_temperature_k", 300.15))
        wet_bulb_temperature_k = float(ctx.parameter("air_wet_bulb_temperature_k", 300.15))
        air_flow_m3_s = max(float(ctx.parameter("air_flow_m3_s", 3.0)), 0.0)
        air_density_kg_m3 = max(float(ctx.parameter("air_density_kg_m3", 1.15)), 1e-3)
        air_cp = float(ctx.parameter("air_cp_j_kg_k", 1006.0))
        ua_w_k = float(ctx.parameter("ua_w_k", 20000.0))

        if mass_flow_kg_s is None:
            mass_flow_kg_s = self._mass_flow_kg_s(ctx)
        mass_flow_kg_s = abs(float(mass_flow_kg_s))

        if mass_flow_kg_s <= 1e-6:
            ctx.diagnostic("CT_ZERO_WATER_FLOW", "水侧流量不大于 1e-6 kg/s，本帧不换热")
            return self._idle_state(water_inlet_temperature_k, air_inlet_temperature_k, wet_bulb_temperature_k)
        if ua_w_k <= 0.0:
            ctx.diagnostic("CT_UA_DISABLED", "UA 不大于 0，仅保留水力阻力，不换热")
            return self._idle_state(water_inlet_temperature_k, air_inlet_temperature_k, wet_bulb_temperature_k)

        c_water = mass_flow_kg_s * water_cp
        c_air = air_flow_m3_s * air_density_kg_m3 * air_cp
        if c_air <= 0.0:
            ctx.diagnostic("CT_AIR_FLOW_ZERO", "风量或空气密度不大于 0，风侧无热容，本帧不换热")
            return self._idle_state(water_inlet_temperature_k, air_inlet_temperature_k, wet_bulb_temperature_k)

        c_min = min(c_water, c_air)
        c_max = max(c_water, c_air)
        ratio = c_min / c_max
        ntu = ua_w_k / c_min
        if ratio < 1.0 - 1e-9:
            exponential = math.exp(-ntu * (1.0 - ratio))
            effectiveness = (1.0 - exponential) / (1.0 - ratio * exponential)
        else:
            effectiveness = ntu / (1.0 + ntu)

        # 以湿球温度为冷源；干模型只计显热，蒸发潜热未计。
        heat_transfer_w = effectiveness * c_min * (water_inlet_temperature_k - wet_bulb_temperature_k)
        heat_flow_w = -heat_transfer_w
        water_outlet_temperature_k = water_inlet_temperature_k - heat_transfer_w / c_water
        air_outlet_temperature_k = air_inlet_temperature_k + heat_transfer_w / c_air
        approach_k = water_outlet_temperature_k - wet_bulb_temperature_k
        ctx.diagnostic(
            "CT_LATENT_IGNORED",
            "冷却塔按干空气显热模型计算，未计蒸发潜热，出水温度估算偏保守",
            "info",
        )
        return heat_flow_w, water_outlet_temperature_k, air_outlet_temperature_k, effectiveness, approach_k

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        diameter_m = max(float(ctx.parameter("water_side_diameter_m", 0.1)), 1e-4)
        length_m = max(float(ctx.parameter("water_side_length_m", 2.0)), 1e-6)
        roughness_m = max(float(ctx.parameter("roughness_m", 1.5e-06)), 0.0)
        density_kg_m3 = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 998.2)), 1e-3)
        viscosity_pa_s = max(float(inlet.viscosity_pa_s or ctx.parameter("viscosity_pa_s", 0.001)), 1e-6)
        heat_flow_w, water_outlet_temperature_k, air_outlet_temperature_k, effectiveness, approach_k = (
            self._thermal_state(ctx)
        )

        # 水侧始终注册，零流量时仍保留支路；heat_flow_w 为负表示水放热。
        ctx.net.pipe(
            channel="main",
            length_m=length_m,
            diameter_m=diameter_m,
            roughness_m=roughness_m,
            density_kg_m3=density_kg_m3,
            viscosity_pa_s=viscosity_pa_s,
            heat_w=heat_flow_w,
        )
        # 平台会为单通路实例生成 <I>.heat_w 别名；模块自身输出用 heat_flow_w 避免覆盖求解变量。
        ctx.var("heat_flow_w", heat_flow_w)
        ctx.var("water_outlet_temperature_k", water_outlet_temperature_k)
        ctx.var("air_outlet_temperature_k", air_outlet_temperature_k)
        ctx.var("effectiveness", effectiveness)
        ctx.var("approach_k", approach_k)

    def commit_step(self, ctx, dt_s):
        # 收敛通路流量优先；没有通路结果时回退端口流量或压差反解。
        if "main" in ctx.channels:
            mass_flow_kg_s = abs(float(ctx.channels["main"].mass_flow_kg_s or 0.0))
        else:
            mass_flow_kg_s = None
        heat_flow_w, water_outlet_temperature_k, air_outlet_temperature_k, effectiveness, approach_k = (
            self._thermal_state(ctx, mass_flow_kg_s)
        )
        ctx.state["thermal_energy_j"] = float(ctx.state.get("thermal_energy_j", 0.0)) + heat_flow_w * dt_s
        ctx.var("heat_flow_w", heat_flow_w)
        ctx.var("water_outlet_temperature_k", water_outlet_temperature_k)
        ctx.var("air_outlet_temperature_k", air_outlet_temperature_k)
        ctx.var("effectiveness", effectiveness)
        ctx.var("approach_k", approach_k)

    def finalize(self, ctx):
        pass
