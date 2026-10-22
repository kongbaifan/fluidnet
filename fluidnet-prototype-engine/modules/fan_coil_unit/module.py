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


def _dew_point_k(temperature_k, relative_humidity):
    """Magnus 式露点估计（干工况提示用）。"""
    relative_humidity = min(max(relative_humidity, 1e-6), 1.0)
    celsius = temperature_k - 273.15
    gamma = math.log(relative_humidity) + 17.625 * celsius / (243.04 + celsius)
    return 243.04 * gamma / (17.625 - gamma) + 273.15


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("thermal_energy_j", 0.0)

    def _thermal_state(self, ctx):
        """Return (heat_w, effectiveness, air_outlet_temperature_k, density_kg_m3)."""
        inlet = ctx.port("in0")
        diameter_m = max(float(ctx.parameter("water_side_diameter_m", 0.02)), 1e-4)
        length_m = max(float(ctx.parameter("water_side_length_m", 5.0)), 1e-6)
        roughness_m = max(float(ctx.parameter("roughness_m", 1.5e-06)), 0.0)
        density_kg_m3 = max(float(inlet.density_kg_m3 or ctx.parameter("density_kg_m3", 998.2)), 1e-3)
        viscosity_pa_s = max(float(inlet.viscosity_pa_s or ctx.parameter("viscosity_pa_s", 0.001)), 1e-6)
        water_cp = float(inlet.specific_heat_j_kg_k or ctx.parameter("water_cp_j_kg_k", 4180.0))
        water_temperature = (
            inlet.temperature_k
            if inlet.temperature_k is not None
            else float(ctx.parameter("water_inlet_temperature_k", 285.15))
        )

        mass_flow_kg_s = inlet.mass_flow_kg_s
        if mass_flow_kg_s is None:
            pressure_in = inlet.pressure_pa
            pressure_out = ctx.port("out0").pressure_pa
            if pressure_in is None or pressure_out is None:
                mass_flow_kg_s = 0.0
                ctx.diagnostic("FC_PRESSURE_UNKNOWN", "试算端口压力缺失，水侧流量按 0 处理，本帧不换热")
            else:
                mass_flow_kg_s = _flow_from_pressure_drop(
                    pressure_in - pressure_out, length_m, diameter_m, roughness_m,
                    density_kg_m3, viscosity_pa_s,
                )
        mass_flow_kg_s = abs(float(mass_flow_kg_s))

        air_flow_m3_s = float(ctx.parameter("air_flow_m3_s", 0.2))
        air_density = float(ctx.parameter("air_density_kg_m3", 1.2))
        air_cp = float(ctx.parameter("air_cp_j_kg_k", 1006.0))
        air_inlet_temperature = float(ctx.parameter("air_inlet_temperature_k", 300.15))
        ua_w_k = float(ctx.parameter("ua_w_k", 2000.0))

        c_water = mass_flow_kg_s * water_cp
        c_air = air_flow_m3_s * air_density * air_cp
        if mass_flow_kg_s <= 1e-6:
            ctx.diagnostic("FC_ZERO_WATER_FLOW", "水侧流量不大于 1e-6 kg/s，本帧不换热")
            return 0.0, 0.0, air_inlet_temperature, density_kg_m3
        if ua_w_k <= 0.0:
            ctx.diagnostic("FC_UA_DISABLED", "UA 不大于 0，仅水力阻力，不换热")
            return 0.0, 0.0, air_inlet_temperature, density_kg_m3
        if c_air <= 0.0:
            ctx.diagnostic("FC_AIR_FLOW_ZERO", "风量或空气密度不大于 0，风侧无热容，本帧不换热")
            return 0.0, 0.0, air_inlet_temperature, density_kg_m3

        relative_humidity = float(ctx.parameter("air_inlet_relative_humidity", 0.5))
        if water_temperature < _dew_point_k(air_inlet_temperature, relative_humidity) - 0.5:
            ctx.diagnostic("FC_CONDENSATION_RISK", "进水温度低于进风露点，干工况模型未计冷凝潜热，Q 可能偏小")

        c_min = min(c_water, c_air)
        c_max = max(c_water, c_air)
        ratio = c_min / c_max
        ntu = ua_w_k / c_min
        if ratio < 1.0 - 1e-9:
            exponential = math.exp(-ntu * (1.0 - ratio))
            effectiveness = (1.0 - exponential) / (1.0 - ratio * exponential)
        else:
            effectiveness = ntu / (1.0 + ntu)
        heat_w = effectiveness * c_min * (air_inlet_temperature - water_temperature)
        air_outlet_temperature = air_inlet_temperature - heat_w / c_air
        return heat_w, effectiveness, air_outlet_temperature, density_kg_m3

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        heat_w, effectiveness, air_outlet_temperature, density_kg_m3 = self._thermal_state(ctx)
        viscosity_pa_s = max(float(inlet.viscosity_pa_s or ctx.parameter("viscosity_pa_s", 0.001)), 1e-6)
        length_m = max(float(ctx.parameter("water_side_length_m", 5.0)), 1e-6)
        diameter_m = max(float(ctx.parameter("water_side_diameter_m", 0.02)), 1e-4)
        roughness_m = max(float(ctx.parameter("roughness_m", 1.5e-06)), 0.0)

        # 水侧始终注册，零流量时仍保留支路；heat_w 由热力层施加到出口焓。
        ctx.net.pipe(
            channel="main",
            length_m=length_m,
            diameter_m=diameter_m,
            roughness_m=roughness_m,
            density_kg_m3=density_kg_m3,
            viscosity_pa_s=viscosity_pa_s,
            heat_w=heat_w,
        )
        # 平台会为单通路实例生成 <I>.heat_w 别名；模块自身输出用 heat_flow_w 避免覆盖求解变量。
        ctx.var("heat_flow_w", heat_w)
        ctx.var("air_outlet_temperature_k", air_outlet_temperature)
        ctx.var("effectiveness", effectiveness)

    def commit_step(self, ctx, dt_s):
        heat_w, _, _, _ = self._thermal_state(ctx)
        ctx.state["thermal_energy_j"] = float(ctx.state.get("thermal_energy_j", 0.0)) + heat_w * dt_s

    def finalize(self, ctx):
        pass
