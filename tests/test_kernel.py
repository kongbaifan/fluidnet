import math

import numpy as np
import pytest

from fluidnet.compiler import compile_project, validate_project
from fluidnet.errors import ModelError
from fluidnet.examples import EXAMPLES, connect, element, exchanger, parallel_network, single_pipe
from fluidnet.hydraulics import friction_factor
from fluidnet.media import MediumRegistry, media_catalog
from fluidnet.models import MediumDefinition, Project
from fluidnet.solver import solve_steady
from fluidnet.units import mass_to_volume_m3_h, pressure_from_gauge_kpa, pressure_to_gauge_kpa


def test_laminar_pipe_against_hagen_poiseuille():
    p = single_pipe()
    p.options.thermal = False
    p.elements[0].parameters["pressure_pa"] = 101335
    p.elements[1].parameters.update(length_m=2, diameter_m=0.005, height_change_m=0, roughness_m=0)
    result = solve_steady(p)
    fluid = MediumRegistry(p.media).get("water").state_pt(101330, 293.15)
    expected = fluid.density_kg_m3 * math.pi * 0.005 ** 4 * 10 / (128 * fluid.viscosity_pa_s * 2)
    assert result["elements"]["pipe"]["mass_flow_kg_s"] == pytest.approx(expected, rel=2e-6)
    assert result["elements"]["pipe"]["reynolds"] < 2300


def test_colebrook_known_reference():
    # Moody/Colebrook reference for Re=100000 and epsilon/D=0.0002.
    f, derivative = friction_factor(100000, 0.0002)
    assert f == pytest.approx(0.0190054352, rel=1e-7)
    assert derivative < 0


def test_parallel_mass_balance_and_throttling():
    p = parallel_network()
    a = solve_steady(p)
    v = a["elements"]
    assert v["trunk"]["mass_flow_kg_s"] == pytest.approx(v["pipe_a"]["mass_flow_kg_s"] + v["pipe_b"]["mass_flow_kg_s"], abs=1e-8)
    b = solve_steady(p.with_scenario("throttled"))
    assert b["elements"]["pipe_b"]["mass_flow_kg_s"] < v["pipe_b"]["mass_flow_kg_s"]
    assert b["elements"]["pipe_a"]["mass_flow_kg_s"] > v["pipe_a"]["mass_flow_kg_s"]
    assert a["metrics"]["mass_residual_kg_s"] < 1e-7


def test_reverse_port_orientation_preserves_solution():
    p = single_pipe()
    p.options.thermal = False
    p.elements[1].parameters["height_change_m"] = 0
    positive = solve_steady(p)["elements"]["pipe"]["mass_flow_kg_s"]
    p.connections = [connect("source", "p2", "pipe", "out"), connect("pipe", "in", "sink", "p1")]
    negative = solve_steady(p)["elements"]["pipe"]["mass_flow_kg_s"]
    assert negative == pytest.approx(-positive, rel=1e-8)


def test_zero_pressure_difference_is_zero_flow():
    p = single_pipe()
    p.options.thermal = False
    p.elements[0].parameters["pressure_pa"] = 101325
    p.elements[1].parameters["height_change_m"] = 0
    result = solve_steady(p)
    assert abs(result["elements"]["pipe"]["mass_flow_kg_s"]) < 1e-8


def test_closed_parallel_valve():
    p = parallel_network()
    next(e for e in p.elements if e.id == "valve_b").parameters["opening"] = 0
    result = solve_steady(p)
    assert abs(result["elements"]["pipe_b"]["mass_flow_kg_s"]) < 1e-8
    assert result["elements"]["valve_b"]["closed"] == 1


def test_no_pressure_reference_is_diagnostic():
    p = single_pipe()
    p.elements[0].type = "flow_boundary"
    p.elements[0].parameters = {"mass_flow_kg_s": 0.1}
    p.elements[2].type = "demand"
    p.elements[2].parameters = {"demand_kg_s": 0.1}
    p.connections = [connect("source", "p", "pipe", "in"), connect("pipe", "out", "sink", "p")]
    assert validate_project(p)["diagnostics"][0]["code"] == "PRESSURE_REFERENCE_MISSING"


def test_cross_media_connection_rejected():
    p = single_pipe()
    p.media.append(MediumDefinition(id="another", name="另一配置"))
    p.elements[0].media = {"fluid": "water"}
    p.elements[1].media = {"fluid": "another"}
    with pytest.raises(ModelError, match="多个介质"):
        compile_project(p)


def test_reserved_medium_cannot_silently_use_water():
    p = single_pipe()
    p.media[0] = MediumDefinition(id="water", kind="air", name="空气", components=["Air"])
    with pytest.raises(ModelError) as exc:
        solve_steady(p)
    assert exc.value.diagnostic.code == "FLOW_MODEL_UNSUPPORTED"
    assert all(not item["enabled"] for item in media_catalog() if item["kind"] != "water")


def test_media_instances_and_exchanger_circuits_are_isolated():
    p = exchanger()
    net = compile_project(p)
    assert len(net.circuits) == 2
    assert net.registry.get("hot_water") is not net.registry.get("cold_water")
    assert net.registry.get("hot_water").fingerprint != net.registry.get("cold_water").fingerprint
    result = solve_steady(p)
    values = result["elements"]["hx"]
    assert values["a.heat_w"] < 0 < values["b.heat_w"]
    assert values["a.heat_w"] + values["b.heat_w"] == pytest.approx(0, abs=0.1)
    assert 293.15 < values["b.outlet_temperature_k"] < 333.15


def test_heater_actual_enthalpy_gain():
    p = Project(elements=[
        element("s", "pressure", 0, 0, pressure_pa=251325),
        element("heater", "heater", 1, 0, power_w=1000),
        element("t", "pressure", 2, 0, pressure_pa=201325),
    ], connections=[connect("s", "p2", "heater", "in"), connect("heater", "out", "t", "p1")])
    result = solve_steady(p)
    assert result["elements"]["heater"]["heat_w"] == pytest.approx(1000, abs=0.05)


@pytest.mark.parametrize("make", EXAMPLES)
def test_supplied_examples_converge(make):
    result = solve_steady(make())
    assert result["valid"]
    assert result["metrics"]["mass_residual_kg_s"] < 1e-7
    assert result["metrics"]["pressure_residual_pa"] < 1


def test_unit_conversions():
    assert pressure_to_gauge_kpa(pressure_from_gauge_kpa(300)) == 300
    assert mass_to_volume_m3_h(1, 1000) == 3.6


def test_negative_geometry_rejected_not_clamped():
    p = single_pipe()
    p.elements[1].parameters["diameter_m"] = -1
    assert validate_project(p)["diagnostics"][0]["code"] == "PARAMETER_INVALID"
