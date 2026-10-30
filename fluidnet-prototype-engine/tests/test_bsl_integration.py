"""L3 联网集成测试：7 个已交付倍思鹿模块包走真实 compile_project + solve_steady/solve_dynamic。

每个用例都构造最小网络：压力边界 source → 目标模块 → 压力边界 sink，然后：

* 校验收敛诊断无 error、质量守恒（边界流量代数和 ≈ 0）；
* 校验模块自身变量可读；
* 用解析式或引擎内置的同一摩擦律做独立对照，不照抄历史快照：

  - 阀门 / 管件：Δp = 100000·(ρ/1000)·Q|Q|/Kv²，管件 K 折算后等价于 Δp = K·ρ·v²/2；
  - 管侧设备：``fn_engine.solver.pipe_drop``（与模块内摩擦律相同）；
  - 换热设备：ε-NTU，Q = ε·C_min·(T_热源,in − T_冷源,in)；
  - 风机 / 水泵：H(Q,s) = s²·H_nominal(Q/s)，Δp = ρ·g·H。

本文件没有 xfail：7 个模块在最小联网下都收敛，且都能给出独立解析对照。需要说明的是
``fan.pressure_rise_pa`` 与 ``pump_variable_speed.pump_head_m`` 的 steady 帧值来自
evaluate 的额定点（evaluate 拿不到流量），实际工作点由 commit_step 在动态帧中给出；
这是模块既有的 evaluate/commit 两阶段契约，不是本测试要掩盖的数值误差。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project
from fn_engine.packages import load_module_package
from fn_engine.solver import MU_WATER, RHO_WATER, pipe_drop, solve_dynamic, solve_steady

ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "modules"
GRAVITY = 9.80665

# 水用引擎的参考物性；风机按需求显式使用 Air 气相工质。
WATER = FluidConfig()
AIR = FluidConfig(fluid="Air", phase_policy="gas")

# 内置风机曲线 / 水泵曲线（与模块 manifest 默认值一致，用于独立插值）。
FAN_CURVE = ((0.0, 300.0), (2000.0, 250.0), (4000.0, 120.0), (5000.0, 0.0))
PUMP_CURVE = ((0.0, 20.0), (10.0, 18.0), (20.0, 12.0), (30.0, 0.0))


def minimal_project(module_id, parameters=None, *, fluid=None, inlet_pressure=250000.0,
                    outlet_pressure=120000.0, inlet_temperature=293.15, outlet_temperature=None):
    """source → D1(target) → sink 的最小可编译项目。"""
    catalog = catalog_map()
    definition = load_module_package(MODULE_ROOT / module_id / "history" / "v1" if module_id == "fan" else MODULE_ROOT / module_id)
    outlet_temperature = inlet_temperature if outlet_temperature is None else outlet_temperature
    return Project(
        id=f"l3-{module_id}",
        name=f"{module_id} 联网集成",
        fluid=fluid if fluid is not None else WATER,
        modules=[catalog["source"], definition],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="入口边界",
                           parameters={"pressure_pa": inlet_pressure, "temperature_k": inlet_temperature}),
            ModuleInstance(id="D1", module_id=module_id, name="被测设备", parameters=dict(parameters or {})),
            ModuleInstance(id="B2", module_id="source", name="出口边界",
                           parameters={"pressure_pa": outlet_pressure, "temperature_k": outlet_temperature}),
        ],
        connections=[
            Connection(id="e1", source=Endpoint(instance_id="B1", port_id="out0"),
                       target=Endpoint(instance_id="D1", port_id="in0")),
            Connection(id="e2", source=Endpoint(instance_id="D1", port_id="out0"),
                       target=Endpoint(instance_id="B2", port_id="out0")),
        ],
    )


def assert_converged(frame, project, *, energy_scale=1.0):
    """收敛、残差容差、无 error 诊断与边界质量守恒。"""
    assert frame.valid, frame.diagnostics
    assert [item for item in frame.diagnostics if item.severity == "error"] == []
    assert frame.metrics["pressure_residual_pa"] <= project.solver.pressure_tolerance_pa
    assert frame.metrics["mass_residual_kg_s"] <= project.solver.mass_tolerance_kg_s
    supply = frame.variables["B1.out0.mass_flow_kg_s"]
    absorbed = frame.variables["B2.out0.mass_flow_kg_s"]
    assert supply + absorbed == pytest.approx(0.0, abs=project.solver.mass_tolerance_kg_s)
    if "energy_residual_w" in frame.metrics:
        assert abs(frame.metrics["energy_residual_w"]) < 1e-6 * max(energy_scale, 1.0)


def valve_mass_flow(pressure_drop_pa, kv_m3_h):
    """阀门 Kv 解析式：Q[m³/h] = Kv·sqrt(Δp/(100000·ρ/1000))。"""
    volume_flow_m3_h = kv_m3_h * math.sqrt(pressure_drop_pa / (1e5 * RHO_WATER / 1000.0))
    return volume_flow_m3_h / 3600.0 * RHO_WATER


def flow_for_pipe_drop(pressure_drop_pa, length_m, diameter_m, roughness_m):
    """用引擎内置 pipe_drop 反解流量，作为模块内同一摩擦律的独立对照。"""
    params = {"length_m": length_m, "diameter_m": diameter_m, "roughness_m": roughness_m}
    low, high = 0.0, 1.0
    while pipe_drop(params, high, RHO_WATER, MU_WATER) < pressure_drop_pa:
        high *= 2.0
    for _ in range(200):
        middle = 0.5 * (low + high)
        if pipe_drop(params, middle, RHO_WATER, MU_WATER) < pressure_drop_pa:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def effectiveness_ntu(c_water_w_k, c_air_w_k, ua_w_k):
    """逆流 ε-NTU（C_r = 1 时退化为 ε = NTU/(1+NTU)）。"""
    c_min, c_max = sorted((c_water_w_k, c_air_w_k))
    ratio = c_min / c_max
    ntu = ua_w_k / c_min
    if ratio < 1.0 - 1e-9:
        exponential = math.exp(-ntu * (1.0 - ratio))
        return (1.0 - exponential) / (1.0 - ratio * exponential)
    return ntu / (1.0 + ntu)


def curve_flow_for_pressure(curve, target_pressure, speed_ratio=1.0):
    """曲线由 (流量 m³/h, 压力/扬程) 点组成；按 Q∝n、p∝n² 反插值工作流量。"""
    target = target_pressure / speed_ratio ** 2
    for (q0, p0), (q1, p1) in zip(curve, curve[1:]):
        if p1 <= target <= p0:
            folded_flow = q0 + (p0 - target) / (p0 - p1) * (q1 - q0)
            return folded_flow * speed_ratio
    raise AssertionError(f"目标压力 {target_pressure} Pa 不在曲线范围内")


def test_pipe_fitting_elbow_loss_matches_analytic():
    """管件模块把 K 折算成等效 Kv；压降与 Δp=K·ρ·v²/2 解析式一致。"""
    project = minimal_project("pipe_fitting", {"fitting_type": "elbow_90"})
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project)

    loss_coefficient = 0.9
    diameter_m = 0.05
    delta_p = 250000.0 - 120000.0
    area_m2 = math.pi * diameter_m ** 2 / 4.0
    expected_velocity = math.sqrt(2.0 * delta_p / (loss_coefficient * RHO_WATER))
    expected_mass_flow = area_m2 * math.sqrt(2.0 * delta_p * RHO_WATER / loss_coefficient)

    assert frame.variables["D1.loss_coefficient"] == pytest.approx(loss_coefficient)
    assert frame.variables["D1.velocity_m_s"] == pytest.approx(expected_velocity, rel=1e-6)
    assert frame.variables["D1.mass_flow_kg_s"] == pytest.approx(expected_mass_flow, rel=1e-5)
    assert frame.variables["D1.pressure_drop_pa"] == pytest.approx(delta_p, rel=1e-12)


def test_check_valve_forward_opening_matches_kv():
    """正向压差下止回阀全开，流量由 Kv 解析式决定。"""
    project = minimal_project("check_valve", {"kv_m3_h": 50.0},
                              inlet_pressure=300000.0, outlet_pressure=100000.0)
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project)

    assert frame.variables["D1.direction"] == 1
    assert frame.variables["D1.opening_ratio"] == pytest.approx(1.0)
    assert frame.variables["D1.pressure_drop_pa"] == pytest.approx(200000.0, rel=1e-12)
    assert frame.variables["D1.mass_flow_kg_s"] == pytest.approx(
        valve_mass_flow(200000.0, 50.0), rel=1e-5)


def test_check_valve_reverse_pressure_closes_flow():
    """反向：高压接在 out0 侧，模块输出 opening_ratio=0，求解器把支路压成零流量。"""
    project = minimal_project("check_valve", {"kv_m3_h": 50.0},
                              inlet_pressure=100000.0, outlet_pressure=300000.0)
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project)

    assert frame.variables["D1.in0.pressure_pa"] == pytest.approx(100000.0, rel=1e-12)
    assert frame.variables["D1.out0.pressure_pa"] == pytest.approx(300000.0, rel=1e-12)
    assert frame.variables["D1.direction"] == -1
    assert frame.variables["D1.opening_ratio"] == pytest.approx(0.0)
    # 关闭支路是零流量约束：支路和两个边界的流量都必须压到 0。
    assert abs(frame.variables["D1.mass_flow_kg_s"]) < 1e-10
    assert abs(frame.variables["B1.out0.mass_flow_kg_s"]) < 1e-10
    assert abs(frame.variables["B2.out0.mass_flow_kg_s"]) < 1e-10


def test_fan_coil_unit_epsilon_ntu_heat_and_hydraulics():
    """风机盘管水侧阻力与 ε-NTU 换热量、出风温度一致。"""
    project = minimal_project("fan_coil_unit", {"ua_w_k": 2000.0},
                              inlet_pressure=250000.0, outlet_pressure=200000.0,
                              inlet_temperature=285.15)
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project, energy_scale=4000.0)

    values = frame.variables
    mass_flow = values["D1.mass_flow_kg_s"]
    assert mass_flow == pytest.approx(flow_for_pipe_drop(50000.0, 5.0, 0.02, 1.5e-6), rel=1e-4)

    water_cp = values["D1.in0.specific_heat_j_kg_k"]
    air_capacity = 0.2 * 1.2 * 1006.0
    effectiveness = effectiveness_ntu(mass_flow * water_cp, air_capacity, 2000.0)
    expected_heat = effectiveness * min(mass_flow * water_cp, air_capacity) * (300.15 - 285.15)

    assert values["D1.effectiveness"] == pytest.approx(effectiveness, rel=1e-9)
    assert values["D1.heat_flow_w"] == pytest.approx(expected_heat, rel=1e-9)
    assert values["D1.heat_w"] == pytest.approx(expected_heat, rel=1e-9)
    assert values["D1.air_outlet_temperature_k"] == pytest.approx(
        300.15 - expected_heat / air_capacity, abs=1e-6)
    # 水吸热，出口温度上升；热力层按 heat_w 施加的热量等于 m·Δh。
    assert values["D1.outlet_temperature_k"] > values["D1.inlet_temperature_k"]
    enthalpy_rise = values["D1.out0.enthalpy_j_kg"] - values["D1.in0.enthalpy_j_kg"]
    assert mass_flow * enthalpy_rise == pytest.approx(expected_heat, rel=1e-9)


def test_cooling_tower_heat_rejection_and_approach():
    """冷却塔以湿球温度为冷源放热；换热量、出水温度和逼近度按 ε-NTU 对照。"""
    project = minimal_project("cooling_tower", {"ua_w_k": 20000.0},
                              inlet_pressure=250000.0, outlet_pressure=249000.0,
                              inlet_temperature=320.15)
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project, energy_scale=70000.0)

    values = frame.variables
    mass_flow = values["D1.mass_flow_kg_s"]
    assert mass_flow == pytest.approx(flow_for_pipe_drop(1000.0, 2.0, 0.1, 1.5e-6), rel=1e-3)

    water_cp = values["D1.in0.specific_heat_j_kg_k"]
    air_capacity = 3.0 * 1.15 * 1006.0
    effectiveness = effectiveness_ntu(mass_flow * water_cp, air_capacity, 20000.0)
    rejected_heat = effectiveness * min(mass_flow * water_cp, air_capacity) * (320.15 - 300.15)
    expected_outlet = 320.15 - rejected_heat / (mass_flow * water_cp)

    assert values["D1.effectiveness"] == pytest.approx(effectiveness, rel=1e-9)
    assert values["D1.heat_flow_w"] == pytest.approx(-rejected_heat, rel=1e-9)
    assert values["D1.heat_w"] == pytest.approx(-rejected_heat, rel=1e-9)
    assert values["D1.water_outlet_temperature_k"] == pytest.approx(expected_outlet, abs=1e-6)
    assert values["D1.approach_k"] == pytest.approx(expected_outlet - 300.15, rel=1e-9)
    assert values["D1.approach_k"] > 0.0
    assert values["D1.air_outlet_temperature_k"] == pytest.approx(
        300.15 + rejected_heat / air_capacity, rel=1e-9)
    # 热力层算出的出口温度与模块自己的出水温度一致（reference 模式热耦合成立）。
    assert values["D1.outlet_temperature_k"] == pytest.approx(expected_outlet, abs=1e-3)


def test_fan_air_single_phase_network_operating_point():
    """Air 气相单相网络可算：工作点落在风压-风量曲线上，水力功率进入流体焓。"""
    project = minimal_project("fan", {"speed_ratio": 1.0}, fluid=AIR,
                              inlet_pressure=101325.0, outlet_pressure=101475.0)
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project, energy_scale=150.0)

    values = frame.variables
    working_flow_m3_h = curve_flow_for_pressure(FAN_CURVE, 150.0)
    expected_mass_flow = working_flow_m3_h / 3600.0 * 1.2
    assert 0.0 < working_flow_m3_h < FAN_CURVE[-1][0]
    assert values["D1.mass_flow_kg_s"] == pytest.approx(expected_mass_flow, rel=1e-4)
    assert values["D1.pressure_drop_pa"] == pytest.approx(-150.0, abs=1e-6)
    # evaluate 拿不到流量，steady 帧的 pressure_rise_pa 是额定点 2000 m³/h 对应的 250 Pa；
    # 实际 150 Pa 工作点由下面的动态 commit 用例验证。
    assert values["D1.pressure_rise_pa"] == pytest.approx(250.0, abs=1e-6)
    assert values["D1.shaft_power_w"] == 0.0
    assert values["D1.electric_power_w"] == 0.0

    hydraulic_power = 150.0 * expected_mass_flow / 1.2
    assert values["D1.heat_w"] == pytest.approx(hydraulic_power, rel=1e-9)
    air_cp = values["D1.in0.specific_heat_j_kg_k"]
    temperature_rise = values["D1.outlet_temperature_k"] - values["D1.inlet_temperature_k"]
    assert temperature_rise == pytest.approx(
        hydraulic_power / (expected_mass_flow * air_cp), abs=0.01)


def test_fan_dynamic_commit_reports_operating_point_power():
    """动态帧 commit_step 用收敛流量/压差给出风机实际风压升、轴功率与电功率。"""
    project = minimal_project("fan", {"speed_ratio": 1.0}, fluid=AIR,
                              inlet_pressure=101325.0, outlet_pressure=101475.0)
    frames = solve_dynamic(compile_project(project), duration_s=0.2, dt_s=0.1)
    assert len(frames) == 3
    frame = frames[-1]
    assert_converged(frame, project, energy_scale=150.0)
    assert any(item.code == "DYNAMIC_QUASI_STEADY" for item in frame.diagnostics)

    values = frame.variables
    expected_mass_flow = curve_flow_for_pressure(FAN_CURVE, 150.0) / 3600.0 * 1.2
    shaft_power = 150.0 * expected_mass_flow / 1.2 / 0.6
    electric_power = shaft_power / 0.9

    assert values["D1.mass_flow_kg_s"] == pytest.approx(expected_mass_flow, rel=1e-4)
    assert values["D1.pressure_rise_pa"] == pytest.approx(150.0, rel=1e-9)
    assert values["D1.shaft_power_w"] == pytest.approx(shaft_power, rel=1e-9)
    assert values["D1.electric_power_w"] == pytest.approx(electric_power, rel=1e-9)
    # 最后帧 t=0.2 s，两个 0.1 s 的 accepted step。
    assert values["D1.state.shaft_energy_j"] == pytest.approx(shaft_power * 0.2, rel=1e-9)
    assert values["D1.state.electric_energy_j"] == pytest.approx(electric_power * 0.2, rel=1e-9)
    # 热力层只把水力功率（不带效率）计入流体焓。
    assert values["D1.heat_w"] == pytest.approx(150.0 * expected_mass_flow / 1.2, rel=1e-9)


def test_pump_variable_speed_curve_and_dynamic_power():
    """变速水泵工作点由扬程曲线决定；稳态为额定扬程，动态 commit 给出实际扬程与功率。"""
    project = minimal_project("pump_variable_speed", {"speed_ratio": 1.0},
                              inlet_pressure=230000.0, outlet_pressure=250000.0)
    steady = solve_steady(compile_project(project))
    assert_converged(steady, project, energy_scale=200.0)

    steady_values = steady.variables
    mass_flow = steady_values["D1.mass_flow_kg_s"]
    expected_flow_m3_h = curve_flow_for_pressure(PUMP_CURVE, 20000.0 / (998.2 * GRAVITY))
    assert mass_flow == pytest.approx(expected_flow_m3_h / 3600.0 * 998.2, rel=1e-5)
    assert steady_values["D1.pump_head_m"] == pytest.approx(18.0)
    assert steady_values["D1.pressure_drop_pa"] == pytest.approx(-20000.0, rel=1e-12)
    assert steady_values["D1.heat_w"] == pytest.approx(20000.0 * mass_flow / 998.2, rel=1e-9)

    frames = solve_dynamic(compile_project(project), duration_s=0.2, dt_s=0.1)
    frame = frames[-1]
    assert_converged(frame, project, energy_scale=200.0)
    values = frame.variables
    actual_head_m = 20000.0 / (998.2 * GRAVITY)
    shaft_power = 20000.0 * mass_flow / 998.2 / 0.7
    electric_power = shaft_power / 0.9

    assert values["D1.pump_head_m"] == pytest.approx(actual_head_m, rel=1e-9)
    assert values["D1.shaft_power_w"] == pytest.approx(shaft_power, rel=1e-9)
    assert values["D1.electric_power_w"] == pytest.approx(electric_power, rel=1e-9)
    assert values["D1.state.shaft_energy_j"] == pytest.approx(shaft_power * 0.2, rel=1e-9)
    assert values["D1.state.electric_energy_j"] == pytest.approx(electric_power * 0.2, rel=1e-9)
    assert values["D1.heat_w"] == pytest.approx(20000.0 * mass_flow / 998.2, rel=1e-9)


def test_capillary_tube_laminar_poiseuille_velocity():
    """毛细管取层流工况，用圆管 Poiseuille 解析解对照流量与平均流速。"""
    project = minimal_project("capillary_tube", {},
                              inlet_pressure=200000.0, outlet_pressure=180000.0)
    frame = solve_steady(compile_project(project))
    assert_converged(frame, project)

    diameter_m = 0.0015
    length_m = 1.5
    delta_p = 20000.0
    area_m2 = math.pi * diameter_m ** 2 / 4.0
    expected_velocity = delta_p * diameter_m ** 2 / (32.0 * MU_WATER * length_m)
    expected_mass_flow = expected_velocity * RHO_WATER * area_m2
    reynolds = expected_mass_flow * diameter_m / (MU_WATER * area_m2)

    assert reynolds < 2300.0
    assert frame.variables["D1.mass_flow_kg_s"] == pytest.approx(expected_mass_flow, rel=1e-6)
    assert frame.variables["D1.mean_velocity_m_s"] == pytest.approx(expected_velocity, rel=1e-6)
    assert frame.variables["D1.flow_area_m2"] == pytest.approx(area_m2, rel=1e-12)
    assert frame.variables["D1.pressure_drop_pa"] == pytest.approx(delta_p, rel=1e-12)
    # 绝热毛细管是等焓节流，温升很小；只做 0.1 K 量级检查。
    assert frame.variables["D1.outlet_temperature_k"] == pytest.approx(293.15, abs=0.1)
    codes = {item.code for item in frame.diagnostics}
    assert "CAP_TWO_PHASE_UNSUPPORTED" in codes  # 模块主动声明单相近似
    assert "CAP_PRESSURE_UNKNOWN" not in codes
