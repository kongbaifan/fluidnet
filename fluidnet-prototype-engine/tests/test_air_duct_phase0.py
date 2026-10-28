"""Phase 0（WP0-Air-0）：Air 单相风管网络可行性验证。

目的：在进入风管元件/风系统开发前，用现有内置管道 + 官方 `fan` 模块搭出
「送风边界 → 风机 → 风管 → 回风边界」网络，独立核对：

* 风管压降与 Darcy–Weisbach + Haaland 手算对照（计划门槛 ≤5%）；
* 风机曲线与风管阻力的工作点（分段线性联立）；
* 风机水力功率进入流体焓、能量账闭合；
* `reference` 与 `node` 两种物性耦合的差异（决定风管工况默认口径）；
* 只有单侧压力边界时的行为（决定静压参考规则）。

本文件只验证可行性，不引入新模型；所有对照公式在测试内独立实现。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project, SolverOptions
from fn_engine.packages import load_module_package
from fn_engine.solver import solve_dynamic, solve_steady

ROOT = Path(__file__).resolve().parents[1]
# 与 modules/fan 的默认风压-风量曲线一致：(m³/h, Pa)，曲线按额定密度折算。
FAN_CURVE = ((0.0, 300.0), (2000.0, 250.0), (4000.0, 120.0), (5000.0, 0.0))
FAN_DENSITY = 1.2
LENGTH_M, DIAMETER_M, ROUGHNESS_M = 30.0, 0.3, 0.00015
AIR = FluidConfig(fluid="Air", phase_policy="gas")


def build_project(*, coupling: str = "reference", with_return: bool = True,
                  fan_parameters: dict | None = None) -> Project:
    catalog = catalog_map()
    fan = load_module_package(ROOT / "modules" / "fan")
    parameters = {"speed_ratio": 1.0}
    parameters.update(fan_parameters or {})
    instances = [
        ModuleInstance(id="B1", module_id="source", name="送风边界",
                       parameters={"pressure_pa": 101325.0, "temperature_k": 293.15}),
        ModuleInstance(id="F1", module_id="fan", name="送风机", parameters=parameters),
        ModuleInstance(id="D1", module_id="pipe", name="送风管",
                       parameters={"length_m": LENGTH_M, "diameter_m": DIAMETER_M,
                                   "roughness_m": ROUGHNESS_M}),
    ]
    connections = [
        Connection(id="c1", source=Endpoint(instance_id="B1", port_id="out0"),
                   target=Endpoint(instance_id="F1", port_id="in0")),
        Connection(id="c2", source=Endpoint(instance_id="F1", port_id="out0"),
                   target=Endpoint(instance_id="D1", port_id="in0")),
    ]
    if with_return:
        instances.append(ModuleInstance(id="B2", module_id="source", name="回风边界",
                                        parameters={"pressure_pa": 101325.0, "temperature_k": 293.15}))
        connections.append(Connection(id="c3", source=Endpoint(instance_id="D1", port_id="out0"),
                                      target=Endpoint(instance_id="B2", port_id="out0")))
    return Project(id="air-duct-phase0", name="风管-风机工作点", fluid=AIR,
                   modules=[catalog["source"], catalog["pipe"], fan], instances=instances,
                   connections=connections, solver=SolverOptions(property_coupling=coupling))


def fan_pressure(flow_m3_h: float) -> float:
    """风压曲线分段线性插值（曲线外按端点取值，与模块一致）。"""
    points = FAN_CURVE
    if flow_m3_h <= points[0][0]:
        return points[0][1]
    if flow_m3_h >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if flow_m3_h <= x1:
            return y0 + (y1 - y0) * (flow_m3_h - x0) / (x1 - x0)
    return points[-1][1]


def duct_drop(mass_flow_kg_s: float, density: float, viscosity: float) -> tuple[float, float]:
    """手算圆管压降：Darcy–Weisbach + Haaland 湍流摩擦；返回 (Δp, Re)。"""
    area = math.pi * DIAMETER_M ** 2 / 4
    velocity = mass_flow_kg_s / (density * area)
    reynolds = density * velocity * DIAMETER_M / viscosity
    if mass_flow_kg_s <= 0.0:
        return 0.0, 0.0
    relative = ROUGHNESS_M / DIAMETER_M
    friction = (-1.8 * math.log10((relative / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2
    return friction * LENGTH_M / DIAMETER_M * density * velocity ** 2 / 2, reynolds


def operating_point(density: float, viscosity: float) -> float:
    """风机曲线与风管阻力的交点（质量流量，kg/s）。"""
    low, high = 0.0, FAN_CURVE[-1][0] / 3600 * FAN_DENSITY

    def balance(flow: float) -> float:
        return fan_pressure(flow / FAN_DENSITY * 3600) - duct_drop(flow, density, viscosity)[0]

    assert balance(low) > 0 > balance(high)
    for _ in range(120):
        middle = (low + high) / 2
        if balance(middle) > 0:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def test_duct_drop_and_fan_operating_point_match_hand_calculation():
    frame = solve_steady(compile_project(build_project()))
    values = frame.variables
    density = values["D1.in0.density_kg_m3"]
    viscosity = values["D1.in0.viscosity_pa_s"]
    mass_flow = values["D1.mass_flow_kg_s"]

    expected_flow = operating_point(density, viscosity)
    expected_drop, reynolds = duct_drop(mass_flow, density, viscosity)

    print(f"\n[Phase0] rho={density:.6f} kg/m3, mu={viscosity:.3e} Pa.s, Re={reynolds:.0f}")
    print(f"[Phase0] flow={mass_flow:.6f} kg/s (hand {expected_flow:.6f}), "
          f"duct drop={values['D1.pressure_drop_pa']:.4f} Pa (hand {expected_drop:.4f})")

    assert mass_flow == pytest.approx(expected_flow, rel=1e-3)
    assert values["D1.pressure_drop_pa"] == pytest.approx(expected_drop, rel=0.05)
    # 两端同为 101325 Pa：风机压升必须等于风管压降。
    assert -values["F1.pressure_drop_pa"] == pytest.approx(values["D1.pressure_drop_pa"], rel=1e-6)
    assert abs(values["F1.pressure_drop_pa"]) >= 0.0
    # 能量账与风机水力功率进焓。
    assert abs(frame.metrics["energy_residual_w"]) <= 1e-6 * max(1.0, abs(values["F1.heat_w"]))
    hydraulic_power = abs(values["F1.pressure_drop_pa"]) * mass_flow / FAN_DENSITY
    assert values["F1.heat_w"] == pytest.approx(hydraulic_power, rel=1e-6)


def test_reference_and_node_property_coupling_agree_within_one_percent():
    reference = solve_steady(compile_project(build_project(coupling="reference")))
    node = solve_steady(compile_project(build_project(coupling="node")))
    reference_flow = reference.variables["D1.mass_flow_kg_s"]
    node_flow = node.variables["D1.mass_flow_kg_s"]
    reference_drop = reference.variables["D1.pressure_drop_pa"]
    node_drop = node.variables["D1.pressure_drop_pa"]
    print(f"\n[Phase0] reference: flow={reference_flow:.6f} kg/s, drop={reference_drop:.4f} Pa")
    print(f"[Phase0] node:      flow={node_flow:.6f} kg/s, drop={node_drop:.4f} Pa")
    # 风管压降只有百 Pa 级，密度变化 <0.2%，两种耦合必须给出同一工程结论。
    assert node_flow == pytest.approx(reference_flow, rel=0.01)
    assert node_drop == pytest.approx(reference_drop, rel=0.01)


def test_dynamic_frame_reports_operating_point_and_fan_power():
    frames = solve_dynamic(compile_project(build_project()), duration_s=1.0, dt_s=1.0)
    frame = frames[-1]
    values = frame.variables
    mass_flow = values["D1.mass_flow_kg_s"]
    duct_drop = values["D1.pressure_drop_pa"]
    hydraulic_power = duct_drop * mass_flow / FAN_DENSITY
    shaft_power = hydraulic_power / 0.6
    electric_power = shaft_power / 0.9

    assert values["F1.pressure_rise_pa"] == pytest.approx(duct_drop, rel=1e-6)
    assert values["F1.shaft_power_w"] == pytest.approx(shaft_power, rel=1e-6)
    assert values["F1.electric_power_w"] == pytest.approx(electric_power, rel=1e-6)
    assert values["F1.state.shaft_energy_j"] == pytest.approx(shaft_power * 1.0, rel=1e-6)
    assert values["F1.state.electric_energy_j"] == pytest.approx(electric_power * 1.0, rel=1e-6)


def test_single_supply_boundary_is_a_dead_end_with_zero_flow():
    """只有送风边界、末端经节点封死时流量为零。

    这说明风管网络需要送/回两侧压力参考（或闭环），否则不存在确定的送风量。
    """
    catalog = catalog_map()
    project = build_project(with_return=False)
    project.modules = [*project.modules, catalog["junction"]]
    project.instances.append(ModuleInstance(id="J1", module_id="junction", name="末端节点"))
    project.connections.append(Connection(id="c3", source=Endpoint(instance_id="D1", port_id="out0"),
                                          target=Endpoint(instance_id="J1", port_id="in0")))
    frame = solve_steady(compile_project(project))
    assert abs(frame.variables["D1.mass_flow_kg_s"]) < 1e-9
