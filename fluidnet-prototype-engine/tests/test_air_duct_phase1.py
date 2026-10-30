"""Phase 1（WP1.1–WP1.4）：干工况风管网络、风机工作点、局部阻力件与风阀。

独立对照全部在测试内实现：Darcy–Weisbach + Haaland（矩形断面用水力直径）、
K→Kv 折算与风阀开度特性。对照门槛沿用 Phase 0 的 5%，实际多数项 <1%。
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project
from fn_engine.packages import load_module_package
from fn_engine.solver import solve_dynamic, solve_steady

ROOT = Path(__file__).resolve().parents[1]
FAN_CURVE = ((0.0, 300.0), (2000.0, 250.0), (4000.0, 120.0), (5000.0, 0.0))
FAN_DENSITY = 1.2
AIR = FluidConfig(fluid="Air", phase_policy="gas")
KV_CONSTANT = 50912.0


def module(name: str):
    return load_module_package(ROOT / "modules" / name / "history" / "v1") if name == "fan" else load_module_package(ROOT / "modules" / name)


def link(identifier, a, b):
    return Connection(id=identifier, source=Endpoint(instance_id=a[0], port_id=a[1]),
                      target=Endpoint(instance_id=b[0], port_id=b[1]))


def fan_pressure(flow_m3_h: float) -> float:
    points = FAN_CURVE
    if flow_m3_h <= points[0][0]:
        return points[0][1]
    if flow_m3_h >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if flow_m3_h <= x1:
            return y0 + (y1 - y0) * (flow_m3_h - x0) / (x1 - x0)
    return points[-1][1]


def rectangular_duct(params: dict, mass_flow: float, density: float, viscosity: float) -> tuple[float, float]:
    """矩形风管手算压降（水力直径 + Haaland）；返回 (Δp, Re)。"""
    width, height = params["duct_width_m"], params["duct_height_m"]
    area = width * height
    diameter = 2 * width * height / (width + height)
    velocity = mass_flow / (density * area)
    reynolds = density * velocity * diameter / viscosity
    if mass_flow <= 0:
        return 0.0, 0.0
    relative = params["roughness_m"] / diameter
    friction = (-1.8 * math.log10((relative / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2
    drop = friction * params["length_m"] / diameter * density * velocity ** 2 / 2
    return drop, reynolds


def duct_flow_for_drop(params: dict, drop_pa: float, density: float, viscosity: float) -> float:
    """给定压差求风管流量（与风机工作点使用同一手算阻力）。"""
    low, high = 0.0, 10.0
    for _ in range(120):
        middle = (low + high) / 2
        if rectangular_duct(params, middle, density, viscosity)[0] < drop_pa:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def duct_project(duct_parameters: dict | None = None, *, fan: bool = True) -> Project:
    catalog = catalog_map()
    duct = dict({"length_m": 30.0, "duct_width_m": 0.4, "duct_height_m": 0.4,
                 "roughness_m": 0.00015}, **(duct_parameters or {}))
    instances = [
        ModuleInstance(id="B1", module_id="source", name="送风边界",
                       parameters={"pressure_pa": 101325.0, "temperature_k": 293.15}),
    ]
    connections = []
    modules = [catalog["source"], catalog["duct"]]
    last = ("B1", "out0")
    if fan:
        modules.append(module("fan"))
        instances.append(ModuleInstance(id="F1", module_id="fan", name="送风机", parameters={"speed_ratio": 1.0}))
        connections.append(link("c1", last, ("F1", "in0")))
        last = ("F1", "out0")
    instances.append(ModuleInstance(id="D1", module_id="duct", name="风管", parameters=duct))
    connections.append(link("c2", last, ("D1", "in0")))
    instances.append(ModuleInstance(id="B2", module_id="source", name="回风边界",
                                    parameters={"pressure_pa": 101325.0, "temperature_k": 293.15}))
    connections.append(link("c3", ("D1", "out0"), ("B2", "out0")))
    return Project(id="duct-phase1", name="风管 Phase 1", fluid=AIR, modules=modules,
                   instances=instances, connections=connections)


def fitting_project(package: str, parameters: dict, drop_pa: float = 200.0) -> Project:
    catalog = catalog_map()
    return Project(id=f"fitting-{package}", name=package, fluid=AIR,
                   modules=[catalog["source"], module(package)],
                   instances=[
                       ModuleInstance(id="B1", module_id="source", name="入口",
                                      parameters={"pressure_pa": 101325.0 + drop_pa, "temperature_k": 293.15}),
                       ModuleInstance(id="D1", module_id=package, name="被测件", parameters=parameters),
                       ModuleInstance(id="B2", module_id="source", name="出口",
                                      parameters={"pressure_pa": 101325.0, "temperature_k": 293.15})],
                   connections=[link("e1", ("B1", "out0"), ("D1", "in0")),
                                link("e2", ("D1", "out0"), ("B2", "out0"))])


def test_duct_friction_matches_hand_calculation_and_fan_operating_point():
    frame = solve_steady(compile_project(duct_project()))
    values = frame.variables
    density = values["D1.in0.density_kg_m3"]
    viscosity = values["D1.in0.viscosity_pa_s"]
    mass_flow = values["D1.mass_flow_kg_s"]
    parameters = {"length_m": 30.0, "duct_width_m": 0.4, "duct_height_m": 0.4, "roughness_m": 0.00015}

    expected_drop, reynolds = rectangular_duct(parameters, mass_flow, density, viscosity)
    # 风机曲线与风管阻力的交点（手算）。
    low, high = 0.0, FAN_CURVE[-1][0] / 3600 * FAN_DENSITY
    for _ in range(120):
        middle = (low + high) / 2
        if fan_pressure(middle / FAN_DENSITY * 3600) - rectangular_duct(parameters, middle, density, viscosity)[0] > 0:
            low = middle
        else:
            high = middle
    expected_flow = (low + high) / 2

    print(f"\n[Phase1] rho={density:.6f}, Re={reynolds:.0f}, flow={mass_flow:.6f} kg/s "
          f"(hand {expected_flow:.6f}), drop={values['D1.pressure_drop_pa']:.4f} Pa (hand {expected_drop:.4f})")
    assert mass_flow == pytest.approx(expected_flow, rel=1e-3)
    assert values["D1.pressure_drop_pa"] == pytest.approx(expected_drop, rel=0.05)
    assert -values["F1.pressure_drop_pa"] == pytest.approx(values["D1.pressure_drop_pa"], rel=1e-6)
    assert abs(frame.metrics["energy_residual_w"]) <= 1e-6 * max(1.0, abs(values["D1.heat_w"]))


def test_duct_heat_loss_warms_air_towards_ambient():
    frame = solve_steady(compile_project(duct_project({"heat_loss_ua_w_k": 60.0,
                                                      "ambient_temperature_k": 303.15})))
    values = frame.variables
    inlet = values["D1.inlet_temperature_k"]
    outlet = values["D1.outlet_temperature_k"]
    assert inlet < outlet <= 303.15
    heat = values["D1.heat_w"]
    enthalpy_rise = values["D1.mass_flow_kg_s"] * values["D1.in0.specific_heat_j_kg_k"] * (outlet - inlet)
    # 空气 cp 随温度略有变化，用入口 cp 的对照保留 0.2% 容差。
    assert heat == pytest.approx(enthalpy_rise, rel=0.002)


def test_duct_fitting_kv_conversion_matches_hand_calculation():
    width = height = 0.5
    area = width * height
    coefficient = 0.3
    parameters = {"fitting_type": "elbow_90", "duct_width_m": width, "duct_height_m": height}
    frame = solve_steady(compile_project(fitting_project("duct_fitting", parameters)))
    values = frame.variables
    density = values["D1.in0.density_kg_m3"]
    drop = 200.0
    kv = KV_CONSTANT * area / math.sqrt(coefficient)
    volume_m3_h = kv * math.sqrt(drop / (1e5 * density / 1000.0))
    expected_mass = volume_m3_h * density / 3600.0
    print(f"\n[Phase1] fitting flow={values['D1.mass_flow_kg_s']:.6f} kg/s (hand {expected_mass:.6f})")
    assert values["D1.mass_flow_kg_s"] == pytest.approx(expected_mass, rel=0.01)
    assert values["D1.loss_coefficient"] == pytest.approx(coefficient)


@pytest.mark.parametrize("characteristic,expected_ratio", [
    ("linear", 0.5),
    ("equal_percentage", 30.0 ** -0.5),
    ("quick_open", 0.5 ** 0.2),
])
def test_damper_characteristics_scale_flow_as_declared(characteristic, expected_ratio):
    def run(opening):
        parameters = {"characteristic": characteristic, "opening_ratio": opening,
                      "rangeability_alf": 30.0, "kv_m3_h": 500.0}
        return solve_steady(compile_project(fitting_project("duct_damper", parameters)))

    full = run(1.0)
    part = run(0.5)
    closed = run(0.0)
    ratio = part.variables["D1.mass_flow_kg_s"] / full.variables["D1.mass_flow_kg_s"]
    print(f"\n[Phase1] damper {characteristic}: ratio={ratio:.6f} (expected {expected_ratio:.6f})")
    assert ratio == pytest.approx(expected_ratio, rel=1e-6)
    assert abs(closed.variables["D1.mass_flow_kg_s"]) < 1e-12


def test_air_vent_nominal_point_is_reproduced():
    parameters = {"nominal_flow_m3_h": 1000.0, "nominal_pressure_drop_pa": 50.0}
    frame = solve_steady(compile_project(fitting_project("air_vent", parameters, drop_pa=50.0)))
    values = frame.variables
    density = values["D1.in0.density_kg_m3"]
    expected_mass = 1000.0 / 3600.0 * density
    print(f"\n[Phase1] vent flow={values['D1.mass_flow_kg_s']:.6f} kg/s (hand {expected_mass:.6f})")
    assert values["D1.mass_flow_kg_s"] == pytest.approx(expected_mass, rel=1e-3)


def test_parallel_ducts_split_flow_by_resistance():
    catalog = catalog_map()
    # junction 的 in0/out0/out1 都并入同一节点：p0 接边界，其余接两支路。
    junction = catalog["junction"]
    duct_a = {"length_m": 10.0, "duct_width_m": 0.4, "duct_height_m": 0.4, "roughness_m": 0.00015}
    duct_b = {"length_m": 10.0, "duct_width_m": 0.3, "duct_height_m": 0.3, "roughness_m": 0.00015}
    project = Project(id="parallel-ducts", name="并联风管", fluid=AIR,
        modules=[catalog["source"], catalog["duct"], junction],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="送风", parameters={"pressure_pa": 101500.0, "temperature_k": 293.15}),
            ModuleInstance(id="J1", module_id="junction", name="分风"),
            ModuleInstance(id="D1", module_id="duct", name="支路 A", parameters=duct_a),
            ModuleInstance(id="D2", module_id="duct", name="支路 B", parameters=duct_b),
            ModuleInstance(id="J2", module_id="junction", name="汇风"),
            ModuleInstance(id="B2", module_id="source", name="回风", parameters={"pressure_pa": 101325.0, "temperature_k": 293.15})],
        connections=[
            link("b1", ("B1", "out0"), ("J1", "in0")),
            link("a1", ("J1", "out0"), ("D1", "in0")),
            link("a2", ("D1", "out0"), ("J2", "out0")),
            link("b2", ("J1", "out1"), ("D2", "in0")),
            link("b3", ("D2", "out0"), ("J2", "out1")),
            link("j2", ("J2", "in0"), ("B2", "out0"))])
    frame = solve_steady(compile_project(project))
    values = frame.variables
    density = values["D1.in0.density_kg_m3"]
    viscosity = values["D1.in0.viscosity_pa_s"]
    drop = 175.0
    hand_a = duct_flow_for_drop(duct_a, drop, density, viscosity)
    hand_b = duct_flow_for_drop(duct_b, drop, density, viscosity)
    engine_a = values["D1.mass_flow_kg_s"]
    engine_b = values["D2.mass_flow_kg_s"]
    print(f"\n[Phase1] parallel: engine A/B={engine_a:.6f}/{engine_b:.6f}, "
          f"hand A/B={hand_a:.6f}/{hand_b:.6f}")
    assert engine_a == pytest.approx(hand_a, rel=0.02)
    assert engine_b == pytest.approx(hand_b, rel=0.02)


def test_duct_aspect_ratio_and_parameter_validation():
    project = duct_project({"duct_width_m": 1.0, "duct_height_m": 0.05}, fan=False)
    network = compile_project(project)
    assert any(item.code == "DUCT_ASPECT_RATIO" for item in network.diagnostics)
    with pytest.raises(CompilationError):
        compile_project(duct_project({"duct_width_m": 0.001}, fan=False))


def test_dynamic_run_publishes_duct_and_fitting_variables():
    project = duct_project({"heat_loss_ua_w_k": 20.0})
    frames = solve_dynamic(compile_project(project), duration_s=1.0, dt_s=1.0)
    values = frames[-1].variables
    for key in ("D1.mass_flow_kg_s", "D1.pressure_drop_pa", "D1.inlet_temperature_k",
                "D1.outlet_temperature_k", "D1.heat_w", "F1.pressure_rise_pa", "F1.shaft_power_w"):
        assert key in values
    assert values["D1.mass_flow_kg_s"] > 0
