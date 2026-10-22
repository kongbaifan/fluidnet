"""第 2 批（P1）倍思鹿参考模块包测试：冷却塔 / 风机 / 变速水泵。

与 test_bsl_modules.py 同一写法：直接用 ``InProcessModuleRunner`` 跑 L2 逻辑，
端口状态用普通 ``PortState`` 传入，因此不依赖 CoolProp 或 scipy。
"""
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
        run_id="bsl-p1-test",
        instance_id="M1",
        iteration_id=0,
        time_s=0.0,
        trial_ports={port_id: PortState(**state) for port_id, state in ports.items()},
    )
    return runner.evaluate(request)


def commit(runner, dt_s, ports, channels):
    channel_states = {}
    for name, value in channels.items():
        if isinstance(value, ChannelState):
            channel_states[name] = value
        elif isinstance(value, dict):
            channel_states[name] = ChannelState(**value)
        else:
            channel_states[name] = ChannelState(mass_flow_kg_s=float(value))
    request = CommitStepRequest(
        run_id="bsl-p1-test",
        instance_id="M1",
        time_s=dt_s,
        dt_s=dt_s,
        converged_ports={port_id: PortState(**state) for port_id, state in ports.items()},
        converged_channels=channel_states,
    )
    return runner.commit_step(request)


def assert_python_package(definition, module_id):
    assert definition.id == module_id
    assert definition.version == 1
    assert definition.runtime == "python"
    assert definition.entrypoint == "module:Module"
    assert definition.source_format == "python-v1"
    assert definition.solver_model == "generic"
    assert definition.category == "倍思鹿参考模块"
    assert len(definition.content_hash) == 64 and len(definition.definition_hash) == 64
    assert [port.id for port in definition.ports] == ["in0", "out0"]
    assert all(
        port.domain.value == "fluid" and port.required and port.circuit == "fluid"
        for port in definition.ports
    )


def test_cooling_tower_package_contract():
    definition = load("cooling_tower")
    assert_python_package(definition, "cooling_tower")

    assert [
        (channel.id, channel.input_port, channel.output_port, channel.relation, channel.solver_model)
        for channel in definition.channels
    ] == [("main", "in0", "out0", "resistance", "pipe")]
    assert defaults(definition) == {
        "ua_w_k": 20000.0,
        "water_side_diameter_m": 0.1,
        "water_side_length_m": 2.0,
        "roughness_m": 1.5e-06,
        "air_flow_m3_s": 3.0,
        "air_inlet_temperature_k": 300.15,
        "air_inlet_relative_humidity": 0.5,
        "air_wet_bulb_temperature_k": 300.15,
        "air_density_kg_m3": 1.15,
        "air_cp_j_kg_k": 1006.0,
        "water_cp_j_kg_k": 4180.0,
        "density_kg_m3": 998.2,
        "viscosity_pa_s": 0.001,
    }
    ua = next(parameter for parameter in definition.parameters if parameter.id == "ua_w_k")
    assert ua.unit.canonical_unit == "W/K"
    assert ua.unit.display_unit == "kW/K"
    assert ua.unit.display_scale == pytest.approx(0.001)
    diameter = next(parameter for parameter in definition.parameters if parameter.id == "water_side_diameter_m")
    assert diameter.unit.display_unit == "mm"
    assert diameter.unit.display_scale == pytest.approx(0.001)
    wet_bulb = next(
        parameter for parameter in definition.parameters if parameter.id == "air_wet_bulb_temperature_k"
    )
    assert wet_bulb.unit.display_unit == "°C"
    assert wet_bulb.unit.display_offset == pytest.approx(-273.15)
    assert {variable.id for variable in definition.variables} == {
        "heat_flow_w",
        "water_outlet_temperature_k",
        "air_outlet_temperature_k",
        "effectiveness",
        "approach_k",
        "state.thermal_energy_j",
    }


def test_cooling_tower_epsilon_ntu_heat_and_approach():
    definition = load("cooling_tower")
    runner = runner_for(definition)
    ports = {
        "in0": {"pressure_pa": 200000.0, "temperature_k": 310.15, "mass_flow_kg_s": 3.0},
        "out0": {"pressure_pa": 200000.0},
    }
    response = evaluate(runner, ports)

    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "pipe"
    assert relation.channel == "main"
    heat_flow_w = response.variables["heat_flow_w"]
    assert "heat_w" not in response.variables  # 避免覆盖平台生成的单通路别名
    assert heat_flow_w < 0.0  # 水放热
    assert heat_flow_w == pytest.approx(-34316.0, rel=0.01)
    assert relation.parameters["heat_w"] == pytest.approx(heat_flow_w, rel=1e-12)

    water_outlet = response.variables["water_outlet_temperature_k"]
    assert water_outlet < 310.15
    assert response.variables["approach_k"] == pytest.approx(water_outlet - 300.15, rel=1e-12)
    assert 0.0 < response.variables["effectiveness"] < 1.0
    assert response.variables["air_outlet_temperature_k"] > 300.15

    committed = commit(runner, 2.0, ports=ports, channels={"main": 3.0})
    assert committed.state["thermal_energy_j"] == pytest.approx(heat_flow_w * 2.0, rel=1e-12)
    assert committed.variables["heat_flow_w"] == pytest.approx(heat_flow_w, rel=1e-12)


def test_cooling_tower_zero_flow_keeps_pipe_relation():
    definition = load("cooling_tower")
    runner = runner_for(definition)
    ports = {
        "in0": {"pressure_pa": 200000.0, "temperature_k": 310.15, "mass_flow_kg_s": 0.0},
        "out0": {"pressure_pa": 200000.0},
    }
    response = evaluate(runner, ports)

    assert len(response.relations) == 1
    assert response.relations[0].kind == "pipe"
    assert response.relations[0].parameters["heat_w"] == 0.0
    assert response.variables["heat_flow_w"] == 0.0
    assert response.variables["effectiveness"] == 0.0
    assert response.variables["water_outlet_temperature_k"] == pytest.approx(310.15)
    assert response.variables["approach_k"] == pytest.approx(10.0)


def test_fan_package_contract():
    definition = load("fan")
    assert_python_package(definition, "fan")

    assert [
        (channel.id, channel.input_port, channel.output_port, channel.relation, channel.solver_model)
        for channel in definition.channels
    ] == [("main", "in0", "out0", "pump_curve", "pump")]
    assert defaults(definition) == {
        "pressure_curve": [[0, 300], [2000, 250], [4000, 120], [5000, 0]],
        "nominal_flow_m3_h": 2000.0,
        "speed_ratio": 1.0,
        "efficiency": 0.6,
        "motor_efficiency": 0.9,
        "air_density_kg_m3": 1.2,
        "air_viscosity_pa_s": 1.8e-05,
    }
    assert {variable.id for variable in definition.variables} == {
        "pressure_rise_pa",
        "shaft_power_w",
        "electric_power_w",
        "state.shaft_energy_j",
        "state.electric_energy_j",
    }


def test_fan_pump_relation_and_committed_energy():
    definition = load("fan")
    runner = runner_for(definition)
    response = evaluate(runner, {
        "in0": {"pressure_pa": 101325.0},
        "out0": {"pressure_pa": 101025.0},
    })

    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "pump"
    assert relation.channel == "main"
    assert relation.parameters["speed_ratio"] == pytest.approx(1.0)
    curve = relation.parameters["head_curve"]
    assert curve[0][0] == 0.0
    assert curve[-1][1] == pytest.approx(0.0)
    assert all(later[0] > earlier[0] for earlier, later in zip(curve, curve[1:]))
    assert all(later[1] < earlier[1] for earlier, later in zip(curve, curve[1:]))
    # 默认额定风量 2000 m³/h 落在曲线第二点，风压升 250 Pa。
    assert response.variables["pressure_rise_pa"] == pytest.approx(250.0)
    assert response.variables["shaft_power_w"] == 0.0
    assert response.variables["electric_power_w"] == 0.0

    committed = commit(
        runner,
        2.0,
        ports={},
        channels={"main": {"mass_flow_kg_s": 1.0, "pressure_drop_pa": 300.0}},
    )
    hydraulic_power_w = 300.0 * 1.0 / 1.2
    expected_shaft_w = hydraulic_power_w / 0.6
    expected_electric_w = expected_shaft_w / 0.9
    assert committed.variables["shaft_power_w"] == pytest.approx(expected_shaft_w, rel=1e-12)
    assert committed.variables["electric_power_w"] == pytest.approx(expected_electric_w, rel=1e-12)
    assert committed.state["shaft_energy_j"] == pytest.approx(expected_shaft_w * 2.0, rel=1e-12)
    assert committed.state["electric_energy_j"] == pytest.approx(expected_electric_w * 2.0, rel=1e-12)
    assert committed.state["electric_energy_j"] > committed.state["shaft_energy_j"] > 0.0


def test_pump_variable_speed_package_contract():
    definition = load("pump_variable_speed")
    assert_python_package(definition, "pump_variable_speed")

    assert [
        (channel.id, channel.input_port, channel.output_port, channel.relation, channel.solver_model)
        for channel in definition.channels
    ] == [("main", "in0", "out0", "pump_curve", "pump")]
    assert defaults(definition) == {
        "head_curve": [[0, 20], [10, 18], [20, 12], [30, 0]],
        "nominal_flow_m3_h": 10.0,
        "speed_ratio": 1.0,
        "efficiency": 0.7,
        "motor_efficiency": 0.9,
        "density_kg_m3": 998.2,
        "viscosity_pa_s": 0.001,
    }
    assert {variable.id for variable in definition.variables} == {
        "pump_head_m",
        "shaft_power_w",
        "electric_power_w",
        "state.shaft_energy_j",
        "state.electric_energy_j",
    }


def test_pump_variable_speed_curve_and_committed_energy():
    definition = load("pump_variable_speed")
    runner = runner_for(definition)
    response = evaluate(runner, {
        "in0": {"pressure_pa": 300000.0},
        "out0": {"pressure_pa": 150000.0},
    })

    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "pump"
    assert relation.channel == "main"
    assert relation.parameters["head_curve"] == [[0, 20], [10, 18], [20, 12], [30, 0]]
    assert relation.parameters["speed_ratio"] == pytest.approx(1.0)
    # 默认额定流量 10 m³/h 对应扬程 18 m。
    assert response.variables["pump_head_m"] == pytest.approx(18.0)
    assert response.variables["shaft_power_w"] == 0.0
    assert response.variables["electric_power_w"] == 0.0

    committed = commit(
        runner,
        2.0,
        ports={},
        channels={"main": {"mass_flow_kg_s": 2.0, "pressure_drop_pa": 150000.0}},
    )
    hydraulic_power_w = 150000.0 * 2.0 / 998.2
    expected_shaft_w = hydraulic_power_w / 0.7
    expected_electric_w = expected_shaft_w / 0.9
    assert committed.state["shaft_energy_j"] > 0.0
    assert committed.state["electric_energy_j"] > committed.state["shaft_energy_j"]
    assert committed.variables["shaft_power_w"] == pytest.approx(expected_shaft_w, rel=1e-12)
    assert committed.variables["electric_power_w"] == pytest.approx(expected_electric_w, rel=1e-12)
    assert committed.state["shaft_energy_j"] == pytest.approx(expected_shaft_w * 2.0, rel=1e-12)
    assert committed.state["electric_energy_j"] == pytest.approx(expected_electric_w * 2.0, rel=1e-12)
