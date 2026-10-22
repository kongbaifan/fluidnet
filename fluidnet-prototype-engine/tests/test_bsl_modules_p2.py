"""第 3 批（P2）倍思鹿参考模块包测试：毛细管（单相液体近似）。

与 test_bsl_modules*.py 同一写法：直接用 ``InProcessModuleRunner`` 跑 L2 逻辑，
端口状态用普通 ``PortState`` 传入，因此不依赖 CoolProp 或 scipy。
"""
import hashlib
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
PACKAGE = MODULE_ROOT / "capillary_tube"

# 默认几何与物性，与 manifest 保持一致。
DIAMETER_M = 0.0015
LENGTH_M = 1.5
ROUGHNESS_M = 1.5e-06
DENSITY_KG_M3 = 998.2
VISCOSITY_PA_S = 0.001
AREA_M2 = math.pi * DIAMETER_M ** 2 / 4.0


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
        run_id="bsl-p2-test",
        instance_id="M1",
        iteration_id=0,
        time_s=0.0,
        trial_ports={port_id: PortState(**state) for port_id, state in ports.items()},
    )
    return runner.evaluate(request)


def commit(runner, dt_s, channels):
    request = CommitStepRequest(
        run_id="bsl-p2-test",
        instance_id="M1",
        time_s=dt_s,
        dt_s=dt_s,
        converged_ports={},
        converged_channels={name: ChannelState(mass_flow_kg_s=flow) for name, flow in channels.items()},
    )
    return runner.commit_step(request)


def diagnostic_codes(response):
    return {diagnostic.code for diagnostic in response.diagnostics}


def test_capillary_tube_package_contract():
    definition = load("capillary_tube")

    assert definition.id == "capillary_tube"
    assert definition.name == "毛细管"
    assert definition.version == 1
    assert definition.runtime == "python"
    assert definition.entrypoint == "module:Module"
    assert definition.source_format == "python-v1"
    assert definition.solver_model == "generic"
    assert definition.category == "倍思鹿参考模块"

    # 双哈希：content_hash = sha256(module.py)，definition_hash 覆盖整份合同 + 源码。
    source = (PACKAGE / "module.py").read_text(encoding="utf-8")
    assert definition.content_hash == hashlib.sha256(source.encode("utf-8")).hexdigest()
    assert len(definition.content_hash) == 64
    assert len(definition.definition_hash) == 64
    int(definition.content_hash, 16)
    int(definition.definition_hash, 16)
    assert definition.definition_hash != definition.content_hash
    assert load("capillary_tube").definition_hash == definition.definition_hash

    assert [port.id for port in definition.ports] == ["in0", "out0"]
    assert all(
        port.domain.value == "fluid" and port.required and port.circuit == "fluid"
        for port in definition.ports
    )
    assert [
        (channel.id, channel.input_port, channel.output_port, channel.relation, channel.solver_model)
        for channel in definition.channels
    ] == [("main", "in0", "out0", "resistance", "pipe")]

    assert defaults(definition) == {
        "diameter_m": 0.0015,
        "length_m": 1.5,
        "roughness_m": 1.5e-06,
        "density_kg_m3": 998.2,
        "viscosity_pa_s": 0.001,
    }
    diameter = next(parameter for parameter in definition.parameters if parameter.id == "diameter_m")
    assert diameter.unit.canonical_unit == "m"
    assert diameter.unit.display_unit == "mm"
    assert diameter.unit.display_scale == pytest.approx(0.001)
    roughness = next(parameter for parameter in definition.parameters if parameter.id == "roughness_m")
    assert roughness.unit.display_unit == "mm"
    assert roughness.unit.display_scale == pytest.approx(0.001)
    viscosity = next(parameter for parameter in definition.parameters if parameter.id == "viscosity_pa_s")
    assert viscosity.unit.canonical_unit == "Pa·s"
    assert viscosity.unit.display_unit == "mPa·s"
    assert viscosity.unit.display_scale == pytest.approx(0.001)

    assert {variable.id for variable in definition.variables} == {
        "flow_area_m2",
        "mean_velocity_m_s",
        "state.throughput_kg",
    }


def test_capillary_tube_pipe_relation_and_velocity():
    definition = load("capillary_tube")
    runner = runner_for(definition)
    response = evaluate(
        runner,
        {
            "in0": {"mass_flow_kg_s": 0.02, "pressure_pa": 300000.0},
            "out0": {"pressure_pa": 250000.0},
        },
    )

    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "pipe"
    assert relation.channel == "main"
    assert relation.parameters["length_m"] == pytest.approx(LENGTH_M)
    assert relation.parameters["diameter_m"] == pytest.approx(DIAMETER_M)
    assert relation.parameters["roughness_m"] == pytest.approx(ROUGHNESS_M)
    assert relation.parameters["heat_w"] == 0.0

    assert response.variables["flow_area_m2"] == pytest.approx(AREA_M2, rel=1e-12)
    expected_velocity = 0.02 / (DENSITY_KG_M3 * AREA_M2)
    assert response.variables["mean_velocity_m_s"] == pytest.approx(expected_velocity, rel=1e-12)
    assert response.variables["mean_velocity_m_s"] > 0.0

    codes = diagnostic_codes(response)
    assert "CAP_TWO_PHASE_UNSUPPORTED" in codes
    two_phase = next(item for item in response.diagnostics if item.code == "CAP_TWO_PHASE_UNSUPPORTED")
    assert two_phase.severity == "info"
    assert "CAP_PRESSURE_UNKNOWN" not in codes  # 端口已给流量，不走压差反解


def test_capillary_tube_infers_velocity_from_pressure_drop():
    """evaluate 无端口流量时，用试算压差按同一 pipe_drop 摩擦律反解流速。"""
    definition = load("capillary_tube")
    runner = runner_for(definition)
    flow_kg_s = 0.0005  # Re ≈ 424，层流解析解可直接对照
    pressure_drop_pa = (
        32.0 * VISCOSITY_PA_S * LENGTH_M * flow_kg_s / (DENSITY_KG_M3 * AREA_M2 * DIAMETER_M ** 2)
    )
    reynolds = flow_kg_s * DIAMETER_M / (VISCOSITY_PA_S * AREA_M2)
    assert reynolds < 2300.0

    response = evaluate(
        runner,
        {
            "in0": {"pressure_pa": 200000.0},
            "out0": {"pressure_pa": 200000.0 - pressure_drop_pa},
        },
    )

    assert response.relations[0].kind == "pipe"
    expected_velocity = flow_kg_s / (DENSITY_KG_M3 * AREA_M2)
    assert response.variables["mean_velocity_m_s"] == pytest.approx(expected_velocity, rel=1e-6)
    assert "CAP_PRESSURE_UNKNOWN" not in diagnostic_codes(response)


def test_capillary_tube_zero_length_clamps_and_commits_throughput():
    definition = load("capillary_tube")
    runner = runner_for(definition, length_m=0.0)
    response = evaluate(
        runner,
        {
            "in0": {"mass_flow_kg_s": 0.02, "pressure_pa": 300000.0},
            "out0": {"pressure_pa": 250000.0},
        },
    )

    # 长度 0 先诊断再截断，仍返回合法的 pipe 关系（length_m > 0）。
    assert len(response.relations) == 1
    relation = response.relations[0]
    assert relation.kind == "pipe"
    assert relation.parameters["length_m"] == pytest.approx(1e-6)
    assert "CAP_LENGTH_CLAMPED" in diagnostic_codes(response)

    committed = commit(runner, 2.0, {"main": 0.02})
    assert committed.state["throughput_kg"] == pytest.approx(0.04, rel=1e-12)


def test_capillary_tube_viscosity_fallback_and_missing_pressure():
    definition = load("capillary_tube")

    fallback_runner = runner_for(definition, viscosity_pa_s=0.0)
    fallback = evaluate(
        fallback_runner,
        {
            "in0": {"mass_flow_kg_s": 0.02, "pressure_pa": 300000.0},
            "out0": {"pressure_pa": 250000.0},
        },
    )
    assert "CAP_VISCOSITY_FALLBACK" in diagnostic_codes(fallback)
    assert fallback.relations[0].parameters["viscosity_pa_s"] == pytest.approx(1e-6)

    unknown_runner = runner_for(definition)
    unknown = evaluate(unknown_runner, {"in0": {}, "out0": {}})
    assert "CAP_PRESSURE_UNKNOWN" in diagnostic_codes(unknown)
    assert unknown.variables["mean_velocity_m_s"] == 0.0
    assert unknown.relations[0].kind == "pipe"
