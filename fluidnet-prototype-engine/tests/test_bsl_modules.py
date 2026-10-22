"""Focused unit tests for the three 倍思鹿 reference Python module packages.

The tests use ``InProcessModuleRunner`` directly so they need neither CoolProp nor
scipy: port states are supplied as plain ``PortState`` values and only the
module-level contracts, evaluate relations and committed state are asserted.
"""
import math
from pathlib import Path

import pytest

from fn_engine.models import (
    ChannelState,
    CommitStepRequest,
    EvaluateRequest,
    FluidConfig,
    PortState,
)
from fn_engine.packages import load_module_package
from fn_engine.runtime import InProcessModuleRunner

ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = ROOT / "modules"


def load(name):
    return load_module_package(MODULE_ROOT / name)


def defaults(definition):
    return {parameter.id: parameter.default for parameter in definition.parameters}


def runner_for(definition, **overrides):
    parameters = defaults(definition)
    parameters.update(overrides)
    runner = InProcessModuleRunner(definition, parameters, FluidConfig())
    runner.initialize()
    return runner


def evaluate(runner, ports):
    request = EvaluateRequest(
        run_id="bsl-test",
        instance_id="M1",
        iteration_id=0,
        time_s=0.0,
        trial_ports={port_id: PortState(**state) for port_id, state in ports.items()},
    )
    return runner.evaluate(request)


def commit(runner, dt_s, ports, channels):
    request = CommitStepRequest(
        run_id="bsl-test",
        instance_id="M1",
        time_s=dt_s,
        dt_s=dt_s,
        converged_ports={port_id: PortState(**state) for port_id, state in ports.items()},
        converged_channels={channel: ChannelState(mass_flow_kg_s=flow) for channel, flow in channels.items()},
    )
    return runner.commit_step(request)


def test_pipe_fitting_package_contract():
    definition = load("pipe_fitting")

    assert definition.id == "pipe_fitting"
    assert definition.version == 1
    assert definition.runtime == "python"
    assert definition.entrypoint == "module:Module"
    assert definition.source_format == "python-v1"
    assert definition.solver_model == "generic"
    assert definition.category == "倍思鹿参考模块"
    assert definition.content_hash and definition.definition_hash

    assert [port.id for port in definition.ports] == ["in0", "out0"]
    assert all(port.domain.value == "fluid" and port.required and port.circuit == "fluid"
               for port in definition.ports)
    assert [(channel.id, channel.input_port, channel.output_port,
             channel.relation, channel.solver_model) for channel in definition.channels] == [
        ("main", "in0", "out0", "resistance", "valve")
    ]
    assert defaults(definition) == {
        "fitting_type": "elbow_90",
        "loss_coefficient": 0.9,
        "diameter_m": 0.05,
        "density_kg_m3": 998.2,
    }
    diameter = next(parameter for parameter in definition.parameters if parameter.id == "diameter_m")
    assert diameter.unit.canonical_unit == "m"
    assert diameter.unit.display_unit == "mm"
    assert diameter.unit.display_scale == pytest.approx(0.001)
    assert {variable.id for variable in definition.variables} == {
        "loss_coefficient", "velocity_m_s", "state.throughput_kg",
    }


def test_pipe_fitting_uses_valve_equivalent_kv_and_commits_throughput():
    definition = load("pipe_fitting")
    runner = runner_for(definition)
    response = evaluate(runner, {
        "in0": {"mass_flow_kg_s": 0.5, "pressure_pa": 101000.0},
        "out0": {"pressure_pa": 100000.0},
    })

    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "valve"
    assert relation.channel == "main"
    assert relation.parameters["opening_ratio"] == pytest.approx(1.0)

    area_m2 = math.pi * 0.05 ** 2 / 4
    expected_kv = 50912.0 * area_m2 / math.sqrt(0.9)
    assert relation.parameters["kv_m3_h"] == pytest.approx(expected_kv, rel=1e-6)
    assert relation.parameters["kv_m3_h"] == pytest.approx(105.37, abs=0.01)
    assert response.variables["loss_coefficient"] == pytest.approx(0.9)
    # evaluate 看不到流量，流速由试算压差 Δp=K·ρv²/2 折算。
    assert response.variables["velocity_m_s"] == pytest.approx(
        math.sqrt(2.0 * 1000.0 / (0.9 * 998.2)), rel=1e-12
    )

    committed = commit(runner, 2.0, ports={}, channels={"main": 0.5})
    assert committed.state["throughput_kg"] == pytest.approx(1.0, rel=1e-12)
    committed_again = commit(runner, 1.0, ports={}, channels={"main": 0.25})
    assert committed_again.state["throughput_kg"] == pytest.approx(1.25, rel=1e-12)


def test_check_valve_package_contract():
    definition = load("check_valve")

    assert definition.id == "check_valve"
    assert definition.version == 1
    assert definition.runtime == "python"
    assert definition.entrypoint == "module:Module"
    assert definition.source_format == "python-v1"
    assert definition.solver_model == "generic"
    assert definition.category == "倍思鹿参考模块"
    assert definition.content_hash and definition.definition_hash

    assert [port.id for port in definition.ports] == ["in0", "out0"]
    assert all(port.domain.value == "fluid" and port.required and port.circuit == "fluid"
               for port in definition.ports)
    assert [(channel.id, channel.input_port, channel.output_port,
             channel.relation, channel.solver_model) for channel in definition.channels] == [
        ("main", "in0", "out0", "resistance", "valve")
    ]
    assert defaults(definition) == {
        "kv_m3_h": 50.0,
        "opening_ratio": 1.0,
        "cracking_pressure_pa": 0.0,
        "density_kg_m3": 998.2,
    }
    assert {variable.id for variable in definition.variables} == {
        "opening_ratio", "direction", "state.closed_steps", "state.throughput_kg",
    }


def test_check_valve_reverse_flow_closes_and_counts_steps():
    definition = load("check_valve")
    runner = runner_for(definition)

    forward_ports = {
        "in0": {"pressure_pa": 200000.0},
        "out0": {"pressure_pa": 100000.0},
    }
    forward = evaluate(runner, forward_ports)
    assert forward.variables["opening_ratio"] == pytest.approx(1.0)
    assert forward.variables["direction"] == 1
    assert forward.relations[0].parameters["opening_ratio"] == pytest.approx(1.0)

    reverse_ports = {
        "in0": {"pressure_pa": 100000.0},
        "out0": {"pressure_pa": 200000.0},
    }
    reverse = evaluate(runner, reverse_ports)
    assert reverse.variables["opening_ratio"] == pytest.approx(0.0)
    assert reverse.variables["direction"] == -1
    assert reverse.relations[0].parameters["opening_ratio"] == pytest.approx(0.0)

    forward_commit = commit(runner, 2.0, ports=forward_ports, channels={"main": 0.3})
    assert forward_commit.state["closed_steps"] == 0
    assert forward_commit.state["throughput_kg"] == pytest.approx(0.6, rel=1e-12)
    assert forward_commit.state["last_direction"] == 1

    reverse_commit = commit(runner, 1.0, ports=reverse_ports, channels={"main": 0.0})
    assert reverse_commit.state["closed_steps"] == 1
    assert reverse_commit.state["last_direction"] == -1
    assert reverse_commit.state["throughput_kg"] == pytest.approx(0.6, rel=1e-12)

    reverse_commit_again = commit(runner, 1.0, ports=reverse_ports, channels={"main": 0.0})
    assert reverse_commit_again.state["closed_steps"] == 2


def test_fan_coil_unit_package_contract():
    definition = load("fan_coil_unit")

    assert definition.id == "fan_coil_unit"
    assert definition.version == 1
    assert definition.runtime == "python"
    assert definition.entrypoint == "module:Module"
    assert definition.source_format == "python-v1"
    assert definition.solver_model == "generic"
    assert definition.category == "倍思鹿参考模块"
    assert definition.content_hash and definition.definition_hash

    assert [port.id for port in definition.ports] == ["in0", "out0"]
    assert all(port.domain.value == "fluid" and port.required and port.circuit == "fluid"
               for port in definition.ports)
    assert [(channel.id, channel.input_port, channel.output_port,
             channel.relation, channel.solver_model) for channel in definition.channels] == [
        ("main", "in0", "out0", "resistance", "pipe")
    ]
    assert defaults(definition) == {
        "ua_w_k": 2000.0,
        "water_side_diameter_m": 0.02,
        "water_side_length_m": 5.0,
        "roughness_m": 1.5e-06,
        "air_flow_m3_s": 0.2,
        "air_inlet_temperature_k": 300.15,
        "air_inlet_relative_humidity": 0.5,
        "air_density_kg_m3": 1.2,
        "air_cp_j_kg_k": 1006.0,
        "water_cp_j_kg_k": 4180.0,
        "water_inlet_temperature_k": 285.15,
        "density_kg_m3": 998.2,
        "viscosity_pa_s": 0.001,
    }
    ua = next(parameter for parameter in definition.parameters if parameter.id == "ua_w_k")
    assert ua.unit.canonical_unit == "W/K"
    assert ua.unit.display_unit == "kW/K"
    assert ua.unit.display_scale == pytest.approx(0.001)
    air_temperature = next(
        parameter for parameter in definition.parameters if parameter.id == "air_inlet_temperature_k"
    )
    assert air_temperature.unit.display_unit == "°C"
    assert air_temperature.unit.display_offset == pytest.approx(-273.15)
    assert {variable.id for variable in definition.variables} == {
        "heat_flow_w", "air_outlet_temperature_k", "effectiveness", "state.thermal_energy_j",
    }


def test_fan_coil_unit_epsilon_ntu_heat_and_zero_flow():
    definition = load("fan_coil_unit")
    runner = runner_for(definition)
    ports = {
        "in0": {
            "pressure_pa": 200000.0,
            "temperature_k": 285.15,
            "density_kg_m3": 998.2,
            "specific_heat_j_kg_k": 4180.0,
            "mass_flow_kg_s": 0.1,
        },
        "out0": {"pressure_pa": 200000.0},
    }
    response = evaluate(runner, ports)

    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "pipe"
    assert relation.channel == "main"
    heat_w = response.variables["heat_flow_w"]
    assert heat_w > 0
    assert relation.parameters["heat_w"] == pytest.approx(heat_w, rel=1e-12)
    assert 0.0 < response.variables["effectiveness"] < 1.0
    assert response.variables["air_outlet_temperature_k"] < 300.15

    committed = commit(runner, 2.0, ports=ports, channels={"main": 0.1})
    assert committed.state["thermal_energy_j"] == pytest.approx(heat_w * 2.0, rel=1e-12)

    zero_runner = runner_for(definition)
    zero_ports = {
        "in0": {
            "pressure_pa": 200000.0,
            "temperature_k": 285.15,
            "density_kg_m3": 998.2,
            "specific_heat_j_kg_k": 4180.0,
            "mass_flow_kg_s": 0.0,
        },
        "out0": {"pressure_pa": 200000.0},
    }
    zero = evaluate(zero_runner, zero_ports)
    assert len(zero.relations) == 1
    assert zero.relations[0].kind == "pipe"
    assert zero.relations[0].parameters["heat_w"] == 0.0
    assert zero.variables["heat_flow_w"] == 0.0
    assert zero.variables["air_outlet_temperature_k"] == pytest.approx(300.15)


def test_fan_coil_unit_infers_water_flow_from_pressure_drop():
    """evaluate 阶段端口流量为 None 时，用试算压差按同一 pipe_drop 摩擦律反解流量。"""
    definition = load("fan_coil_unit")
    runner = runner_for(definition)
    response = evaluate(runner, {
        "in0": {"pressure_pa": 200000.0, "temperature_k": 285.15,
                "density_kg_m3": 998.2, "specific_heat_j_kg_k": 4180.0},
        "out0": {"pressure_pa": 199550.0},
    })

    heat_w = response.variables["heat_flow_w"]
    assert 3500.0 < heat_w < 3650.0  # 文档 MODULES_P0 §3.5：约 3575 W
    assert 0.98 < response.variables["effectiveness"] < 0.995
    assert 285.0 < response.variables["air_outlet_temperature_k"] < 286.0
    assert response.relations[0].parameters["heat_w"] == pytest.approx(heat_w, rel=1e-12)
