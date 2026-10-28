"""Phase 2a：湿空气输运、湿工况表冷器与加湿器（教学级湿空气模型）。

独立对照：CoolProp `HAPropsSI`（湿空气焓/含湿量）与水分/能量守恒关系。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from CoolProp.CoolProp import HAPropsSI

from fn_engine import moist_air
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project, SolverOptions
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]
PA = 101325.0
AIR_MOIST = FluidConfig(fluid="Air", phase_policy="gas")


def link(identifier, a, b):
    return Connection(id=identifier, source=Endpoint(instance_id=a[0], port_id=a[1]),
                      target=Endpoint(instance_id=b[0], port_id=b[1]))


def boundary(identifier, pressure=PA, temperature=293.15, humidity=0.008):
    return ModuleInstance(id=identifier, module_id="source", name=identifier,
                          parameters={"pressure_pa": pressure, "temperature_k": temperature,
                                      "humidity_ratio_kg_kg": humidity})


def air_project(instances, connections, modules, *, moist=True):
    return Project(id="moist-air", name="湿空气 Phase 2a", fluid=AIR_MOIST,
                   modules=modules, instances=instances, connections=connections,
                   solver=SolverOptions(moist_air=moist))


def coil_project(coil_parameters, temperature=303.15, humidity=0.015):
    catalog = catalog_map()
    return air_project(
        [boundary("B1", PA + 200.0, temperature, humidity),
         ModuleInstance(id="V1", module_id="valve", name="调节阀",
                        parameters={"opening_ratio": 0.8, "kv_m3_h": 30.0}),
         ModuleInstance(id="C1", module_id="cooling_coil", name="表冷器", parameters=coil_parameters),
         boundary("B2", PA, temperature, humidity)],
        [link("e1", ("B1", "out0"), ("V1", "in0")),
         link("e2", ("V1", "out0"), ("C1", "in0")),
         link("e3", ("C1", "out0"), ("B2", "out0"))],
        [catalog["source"], catalog["valve"], catalog["cooling_coil"]])


def humidifier_project(parameters, temperature=293.15, humidity=0.006):
    catalog = catalog_map()
    return air_project(
        [boundary("B1", PA + 200.0, temperature, humidity),
         ModuleInstance(id="V1", module_id="valve", name="调节阀",
                        parameters={"opening_ratio": 0.8, "kv_m3_h": 30.0}),
         ModuleInstance(id="H1", module_id="humidifier", name="加湿器", parameters=parameters),
         boundary("B2", PA, temperature, humidity)],
        [link("e1", ("B1", "out0"), ("V1", "in0")),
         link("e2", ("V1", "out0"), ("H1", "in0")),
         link("e3", ("H1", "out0"), ("B2", "out0"))],
        [catalog["source"], catalog["valve"], catalog["humidifier"]])


def test_psychrometrics_match_coolprop_humid_air():
    temperature, humidity = 293.15, 0.008
    reference = HAPropsSI("H", "T", temperature, "P", PA, "W", humidity) / 1000.0  # kJ/kg_da
    ours = moist_air.enthalpy_j_kg_da(temperature, humidity) / 1000.0
    assert ours == pytest.approx(reference, rel=0.02)
    w_reference = HAPropsSI("W", "T", temperature, "P", PA, "R", 0.5)
    assert moist_air.humidity_ratio_from_relative(temperature, PA, 0.5) == pytest.approx(w_reference, rel=0.02)
    dew = moist_air.dew_point_k(temperature, PA, humidity)
    dew_reference = HAPropsSI("D", "T", temperature, "P", PA, "W", humidity)
    assert dew == pytest.approx(dew_reference, abs=1.0)
    assert moist_air.relative_humidity(temperature, PA, humidity) == pytest.approx(
        HAPropsSI("R", "T", temperature, "P", PA, "W", humidity), abs=0.02)


def test_humidity_is_conserved_through_an_adiabatic_duct():
    catalog = catalog_map()
    fan_module = __import__("fn_engine.packages", fromlist=["load_module_package"]).load_module_package(
        ROOT / "modules" / "fan")
    project = air_project(
        [boundary("B1", PA, 293.15, 0.010),
         ModuleInstance(id="F1", module_id="fan", name="风机", parameters={"speed_ratio": 1.0}),
         ModuleInstance(id="D1", module_id="duct", name="风管",
                        parameters={"length_m": 20.0, "duct_width_m": 0.4, "duct_height_m": 0.4}),
         boundary("B2", PA, 293.15, 0.010)],
        [link("e1", ("B1", "out0"), ("F1", "in0")),
         link("e2", ("F1", "out0"), ("D1", "in0")),
         link("e3", ("D1", "out0"), ("B2", "out0"))],
        [catalog["source"], catalog["duct"], fan_module])
    values = solve_steady(compile_project(project)).variables
    assert values["D1.in0.humidity_ratio_kg_kg"] == pytest.approx(0.010, rel=1e-9)
    assert values["D1.out0.humidity_ratio_kg_kg"] == pytest.approx(0.010, rel=1e-9)
    assert 0.0 < values["D1.out0.relative_humidity"] < 1.0


def test_wet_coil_cools_dehumidifies_and_reports_latent_load():
    frame = solve_steady(compile_project(coil_project(
        {"coil_surface_temperature_k": 285.15, "bypass_factor": 0.15, "loss_coefficient": 5.0})))
    values = frame.variables
    mass_flow = values["C1.mass_flow_kg_s"]
    w_in, w_out = values["C1.in0.humidity_ratio_kg_kg"], values["C1.out0.humidity_ratio_kg_kg"]
    t_in, t_out = values["C1.in0.temperature_k"], values["C1.out0.temperature_k"]

    expected_t_out = 285.15 + 0.15 * (t_in - 285.15)
    expected_w_sat = moist_air.saturation_humidity_ratio(285.15, PA)
    expected_w_out = expected_w_sat + 0.15 * (w_in - expected_w_sat)
    assert t_out == pytest.approx(expected_t_out, abs=1e-6)
    assert w_out == pytest.approx(expected_w_out, rel=1e-6)
    assert 0.0 < w_out < w_in

    condensate = values["C1.condensate_kg_s"]
    assert condensate == pytest.approx(mass_flow * (w_in - w_out), rel=1e-6)
    assert values["C1.sensible_heat_w"] > 0 and values["C1.latent_heat_w"] > 0
    assert values["C1.shr"] == pytest.approx(
        values["C1.sensible_heat_w"] / (values["C1.sensible_heat_w"] + values["C1.latent_heat_w"]), rel=1e-6)
    assert abs(frame.metrics["moisture_residual_kg_s"]) < 1e-6 * max(mass_flow, 1.0)
    # 潜热与凝水量应符合 h_fg 量级。
    h_fg = 2.501e6
    assert values["C1.latent_heat_w"] == pytest.approx(mass_flow * (w_in - w_out) * h_fg, rel=0.1)


def test_dry_coil_does_not_condense():
    frame = solve_steady(compile_project(coil_project(
        {"coil_surface_temperature_k": 285.15, "bypass_factor": 0.15, "loss_coefficient": 5.0},
        temperature=293.15, humidity=0.004)))
    values = frame.variables
    assert values["C1.in0.humidity_ratio_kg_kg"] == pytest.approx(
        values["C1.out0.humidity_ratio_kg_kg"], rel=1e-9)
    assert values["C1.condensate_kg_s"] == pytest.approx(0.0, abs=1e-12)
    assert values["C1.latent_heat_w"] == pytest.approx(0.0, abs=1e-9)


def test_adiabatic_humidifier_keeps_enthalpy_and_lowers_temperature():
    frame = solve_steady(compile_project(humidifier_project(
        {"mode": "adiabatic", "moisture_addition_kg_kg": 0.003, "loss_coefficient": 5.0})))
    values = frame.variables
    assert values["H1.in0.humidity_ratio_kg_kg"] + 0.003 == pytest.approx(
        values["H1.out0.humidity_ratio_kg_kg"], rel=1e-9)
    assert values["H1.out0.temperature_k"] < values["H1.in0.temperature_k"]
    assert values["H1.in0.enthalpy_j_kg"] == pytest.approx(values["H1.out0.enthalpy_j_kg"], rel=1e-6)
    assert values["H1.moisture_addition_kg_s"] == pytest.approx(
        values["H1.mass_flow_kg_s"] * 0.003, rel=1e-9)


def test_isothermal_humidifier_keeps_temperature_and_adds_enthalpy():
    frame = solve_steady(compile_project(humidifier_project(
        {"mode": "isothermal", "moisture_addition_kg_kg": 0.003, "loss_coefficient": 5.0})))
    values = frame.variables
    assert values["H1.out0.temperature_k"] == pytest.approx(values["H1.in0.temperature_k"], rel=1e-9)
    assert values["H1.out0.enthalpy_j_kg"] > values["H1.in0.enthalpy_j_kg"]


def test_mixing_two_airstreams_mixes_humidity_by_mass():
    catalog = catalog_map()
    # 两股空气先经各自风管到达混合节点；边界位于不同节点，温度/含湿量可不同。
    project = air_project(
        [boundary("B1", PA + 300.0, 305.15, 0.012),
         boundary("B2", PA + 200.0, 295.15, 0.006),
         ModuleInstance(id="D1", module_id="duct", name="新风管",
                        parameters={"length_m": 5.0, "duct_width_m": 0.3, "duct_height_m": 0.3}),
         ModuleInstance(id="D2", module_id="duct", name="回风管",
                        parameters={"length_m": 5.0, "duct_width_m": 0.5, "duct_height_m": 0.5}),
         ModuleInstance(id="J1", module_id="junction", name="混合节点"),
         ModuleInstance(id="D3", module_id="duct", name="混合后风管",
                        parameters={"length_m": 5.0, "duct_width_m": 0.5, "duct_height_m": 0.5}),
         boundary("B3", PA, 295.15, 0.006)],
        [link("e1", ("B1", "out0"), ("D1", "in0")),
         link("e2", ("D1", "out0"), ("J1", "in0")),
         link("e3", ("B2", "out0"), ("D2", "in0")),
         link("e4", ("D2", "out0"), ("J1", "out0")),
         link("e5", ("J1", "out1"), ("D3", "in0")),
         link("e6", ("D3", "out0"), ("B3", "out0"))],
        [catalog["source"], catalog["junction"], catalog["duct"]])
    values = solve_steady(compile_project(project)).variables
    flow_fresh = values["B1.out0.mass_flow_kg_s"]
    flow_return = values["B2.out0.mass_flow_kg_s"]
    mixed = (flow_fresh * 0.012 + flow_return * 0.006) / (flow_fresh + flow_return)
    assert values["J1.in0.humidity_ratio_kg_kg"] == pytest.approx(mixed, rel=1e-6)


def test_moist_air_mode_is_explicit_and_validated():
    catalog = catalog_map()
    with pytest.raises(CompilationError, match='moist_air'):
        compile_project(Project(id="no-moist", name="x", fluid=AIR_MOIST,
                                modules=[catalog["source"], catalog["cooling_coil"]],
                                instances=[boundary("B1"), ModuleInstance(id="C1", module_id="cooling_coil", name="c"),
                                           boundary("B2")],
                                connections=[link("e1", ("B1", "out0"), ("C1", "in0")),
                                             link("e2", ("C1", "out0"), ("B2", "out0"))]))
    with pytest.raises(CompilationError, match='湿空气模式'):
        compile_project(Project(id="wet-water", name="x", fluid=FluidConfig(),
                                modules=[catalog["source"]],
                                instances=[boundary("B1")],
                                solver=SolverOptions(moist_air=True)))
    with pytest.raises(CompilationError, match='饱和'):
        compile_project(air_project(
            [boundary("B1", PA, 293.15, 0.05), boundary("B2", PA, 293.15, 0.008)],
            [link("e1", ("B1", "out0"), ("B2", "out0"))], [catalog["source"]]))
