"""M2-L3 可执行验收：等百分比阀模块 + P-4 / V-4 / M-4 标定与守恒测试。

四个测试组：

* 契约：``modules/valve_equal_percentage`` 的 manifest/端口/通路/参数/变量/双哈希；
* V-4：倍思鹿等百分比特性点（CVF）与 50%/100% 流量比，并对照内置线性 ``valve``；
* P-4：管道 ``thermal_cells=4`` + 壁面热容的动态热容瞬态与 N 段稳态解析式；
* M-4：泵曲线 ``CURVE_A`` 的 MPa / bar 两种单位假设下的工作点。

所有数值都走真实 ``compile_project`` + ``solve_steady`` / ``solve_dynamic``；只有
V-4 特性点和关系种类用 ``InProcessModuleRunner`` 直接读取模块提交的变量/关系。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import (
    Connection,
    ControlScript,
    Endpoint,
    EvaluateRequest,
    FluidConfig,
    ModuleInstance,
    PortState,
    Project,
)
from fn_engine.packages import load_module_package
from fn_engine.properties import property_service
from fn_engine.runtime import InProcessModuleRunner, module_content_hash, module_definition_hash
from fn_engine.solver import GRAVITY, RHO_WATER, pump_head, solve_dynamic, solve_steady

ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "modules" / "valve_equal_percentage"
WATER = property_service(FluidConfig())

# 倍思鹿 截止阀_Run.cpp:69-72 的硬编码值（ALF=100、LF=0）。
ALF_DEFAULT = 100.0


def load_definition():
    return load_module_package(MODULE_DIR)


def defaults(definition):
    return {parameter.id: parameter.default for parameter in definition.parameters}


def link(connection_id, source, target):
    source_instance, source_port = source.split(":")
    target_instance, target_port = target.split(":")
    return Connection(
        id=connection_id,
        source=Endpoint(instance_id=source_instance, port_id=source_port),
        target=Endpoint(instance_id=target_instance, port_id=target_port),
    )


def runner_for(definition, **overrides):
    parameters = defaults(definition)
    parameters.update(overrides)
    runner = InProcessModuleRunner(definition, parameters, FluidConfig())
    runner.initialize()
    return runner


def evaluate(runner, density_kg_m3=None):
    inlet = PortState(pressure_pa=200000.0, density_kg_m3=density_kg_m3)
    request = EvaluateRequest(
        run_id="bsl-calibration",
        instance_id="V1",
        iteration_id=0,
        time_s=0.0,
        trial_ports={"in0": inlet, "out0": PortState(pressure_pa=100000.0)},
    )
    return runner.evaluate(request)


# --- 1. 契约 -------------------------------------------------------------------


def test_v4_valve_equal_percentage_package_contract():
    manifest = json.loads((MODULE_DIR / "manifest.json").read_text(encoding="utf-8"))
    # 包哈希由 load_module_package 计算，manifest 本身不写哈希或 runtime。
    for forbidden in ("content_hash", "definition_hash", "runtime"):
        assert forbidden not in manifest

    definition = load_definition()
    assert definition.id == "valve_equal_percentage"
    assert definition.name == "等百分比调节阀"
    assert definition.version == 1
    assert definition.category == "倍思鹿参考模块"
    assert definition.entrypoint == "module:Module"
    assert definition.source_format == "python-v1"
    assert definition.solver_model == "generic"
    assert definition.runtime == "python"

    assert [(port.id, port.direction.value, port.domain.value, port.required, port.circuit)
            for port in definition.ports] == [
        ("in0", "in", "fluid", True, "fluid"),
        ("out0", "out", "fluid", True, "fluid"),
    ]
    assert [(channel.id, channel.input_port, channel.output_port, channel.relation, channel.solver_model)
            for channel in definition.channels] == [("main", "in0", "out0", "resistance", "valve")]

    assert defaults(definition) == {
        "kv_m3_h": 16.0,
        "opening_ratio": 0.5,
        "rangeability_alf": 100.0,
        "leakage_fraction": 0.0,
        "density_kg_m3": 998.2,
    }
    ranges = {parameter.id: (parameter.minimum, parameter.maximum) for parameter in definition.parameters}
    assert ranges == {
        "kv_m3_h": (0.001, None),
        "opening_ratio": (0.0, 1.0),
        "rangeability_alf": (1.0, 1000.0),
        "leakage_fraction": (0.0, 0.5),
        "density_kg_m3": (1.0, None),
    }
    assert {variable.id: variable.source for variable in definition.variables} == {
        "cvf": "derived",
        "effective_kv_m3_h": "derived",
        "state.throughput_kg": "state",
    }

    # 双哈希：包加载时计算的两个摘要必须能由定义/源码重新算出。
    assert definition.content_hash == module_content_hash(definition)
    assert definition.definition_hash == module_definition_hash(definition)
    assert definition.content_hash and definition.definition_hash


# --- 2. V-4 特性点 --------------------------------------------------------------


def test_v4_equal_percentage_characteristic_points():
    definition = load_definition()

    full = evaluate(runner_for(definition, opening_ratio=1.0))
    assert full.variables["cvf"] == pytest.approx(0.99, abs=1e-12)
    assert full.variables["effective_kv_m3_h"] == pytest.approx(15.84, abs=1e-12)
    assert full.relations[0].parameters["kv_m3_h"] == pytest.approx(15.84, rel=1e-12)
    assert full.relations[0].parameters["opening_ratio"] == pytest.approx(1.0)

    half = evaluate(runner_for(definition, opening_ratio=0.5))
    assert half.variables["cvf"] == pytest.approx(0.09, abs=1e-12)
    assert half.variables["effective_kv_m3_h"] == pytest.approx(1.44, abs=1e-12)
    assert half.relations[0].parameters["kv_m3_h"] == pytest.approx(1.44, rel=1e-12)

    low = evaluate(runner_for(definition, opening_ratio=0.1))
    assert low.variables["cvf"] == pytest.approx(0.005849, abs=1e-6)
    expected_low = 16.0 * (ALF_DEFAULT ** -0.9 - 1.0 / ALF_DEFAULT)
    assert low.variables["effective_kv_m3_h"] == pytest.approx(expected_low, rel=1e-12)

    # 0% 开度走精确关断分支：opening_ratio=0，额定 Kv 仍 >0（关系参数校验要求）。
    closed = evaluate(runner_for(definition, opening_ratio=0.0))
    assert closed.variables["cvf"] == 0.0
    assert closed.variables["effective_kv_m3_h"] == 0.0
    assert closed.relations[0].parameters["opening_ratio"] == 0.0
    assert closed.relations[0].parameters["kv_m3_h"] == pytest.approx(16.0)

    # 密度优先取端口值，缺失时回退参数 998.2。
    port_density = evaluate(runner_for(definition, opening_ratio=1.0), density_kg_m3=950.0)
    assert port_density.relations[0].parameters["density_kg_m3"] == pytest.approx(950.0)
    fallback = evaluate(runner_for(definition, opening_ratio=1.0))
    assert fallback.relations[0].parameters["density_kg_m3"] == pytest.approx(998.2)


# --- 3. V-4 联网集成：50%/100% 流量比 -------------------------------------------


def valve_line(kind, opening):
    """B1(200 kPa) → V1 → L1 → B2(100 kPa)，阀门可以是 Python 模块或内置线性阀。"""
    catalog = catalog_map()
    modules = [catalog["source"]]
    instances = [ModuleInstance(id="B1", module_id="source", name="入口",
                                parameters={"pressure_pa": 200000.0, "temperature_k": 293.15})]
    if kind == "valve_equal_percentage":
        definition = load_definition()
        modules.append(definition)
        instances.append(ModuleInstance(id="V1", module_id=definition.id, name="等百分比阀",
                                        parameters={"opening_ratio": opening}))
    else:
        modules.append(catalog["valve"])
        instances.append(ModuleInstance(id="V1", module_id="valve", name="线性阀",
                                        parameters={"opening_ratio": opening, "kv_m3_h": 16.0}))

    modules.append(catalog["pipe"])
    instances.append(ModuleInstance(id="L1", module_id="pipe", name="串联管段",
                                    parameters={"length_m": 1.0, "diameter_m": 0.05,
                                                "roughness_m": 0.000045}))
    instances.append(ModuleInstance(id="B2", module_id="source", name="出口",
                                    parameters={"pressure_pa": 100000.0, "temperature_k": 293.15}))
    return Project(id=f"v4-{kind}", name=f"V-4 {kind}", modules=modules, instances=instances,
                   connections=[link("e1", "B1:out0", "V1:in0"), link("e2", "V1:out0", "L1:in0"),
                                link("e3", "L1:out0", "B2:out0")])


def test_v4_equal_percentage_flow_ratio_versus_linear_valve():
    full = solve_steady(compile_project(valve_line("valve_equal_percentage", 1.0)))
    half = solve_steady(compile_project(valve_line("valve_equal_percentage", 0.5)))
    equal_percentage_ratio = (half.variables["V1.volume_flow_m3_h"]
                              / full.variables["V1.volume_flow_m3_h"])

    # CVF(1)=0.99、CVF(0.5)=0.09；两者都乘额定 Kv，故理论流量比 0.09/0.99≈0.0909。
    # 串联短管的附加阻力把比值抬高到约 0.0914，仍在 ±10% 内。
    assert equal_percentage_ratio == pytest.approx(0.09, rel=0.10)
    assert 0.081 < equal_percentage_ratio < 0.099
    assert half.variables["V1.cvf"] == pytest.approx(0.09, abs=1e-12)
    assert half.variables["V1.effective_kv_m3_h"] == pytest.approx(1.44, abs=1e-12)
    # 阀门与串联管段分担同一 100 kPa 压差。
    for frame in (full, half):
        assert (frame.variables["V1.pressure_drop_pa"] + frame.variables["L1.pressure_drop_pa"]
                == pytest.approx(100000.0, rel=1e-9))

    linear_full = solve_steady(compile_project(valve_line("valve", 1.0)))
    linear_half = solve_steady(compile_project(valve_line("valve", 0.5)))
    linear_ratio = (linear_half.variables["V1.volume_flow_m3_h"]
                    / linear_full.variables["V1.volume_flow_m3_h"])
    # 内置阀 Kv_eff=Kv·opening，50% 开度流量约为全开的 0.50。
    assert linear_ratio == pytest.approx(0.5, rel=0.05)
    # 等百分比曲线在 50% 开度只有线性阀的约 18%，这是 MAPPING_A V-4 的量化缺口。
    assert linear_ratio / equal_percentage_ratio > 5.0


# --- 4. P-4 动态热容 ------------------------------------------------------------


def thermal_capacity_project():
    """B1 → V1(初始关闭) → L1(4 段热容) → B2；控制脚本在第一步把阀门开到 1.0。

    常边界下的 ``solve_dynamic`` 第 0 帧已经取到 cell 稳态剖面，看不到热惯性；
    因此让 t=0 保持关阀：管内静止，4 段 cell 初温等于入口 353.15 K。流量阶跃后
    cell 向带散热的稳态剖面冷却，出口温度单调下降并衰减到稳态。
    """
    catalog = catalog_map()
    pipe = {
        "length_m": 30.0,
        "diameter_m": 0.06,
        "roughness_m": 0.000045,
        "thermal_cells": 4,
        "wall_heat_capacity_j_k": 5.0e5,
        "heat_loss_ua_w_k": 3000.0,
        "ambient_temperature_k": 293.15,
    }
    source = """
def initialize(ctx):
    pass

def step(ctx, dt_s):
    ctx.write('V1.param.opening_ratio', 1.0)

def finalize(ctx):
    pass
"""
    script = ControlScript(id="p4_open", source=source, enabled=True, sample_s=60.0,
                           inputs=[], outputs=["V1.param.opening_ratio"])
    return Project(
        id="p4-thermal-capacity",
        name="P-4 动态热容",
        fluid=FluidConfig(),
        modules=[catalog["source"], catalog["valve"], catalog["pipe"]],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="入口",
                           parameters={"pressure_pa": 200000.0, "temperature_k": 353.15}),
            ModuleInstance(id="V1", module_id="valve", name="开关阀",
                           parameters={"opening_ratio": 0.0, "kv_m3_h": 6.0}),
            ModuleInstance(id="L1", module_id="pipe", name="热容管段", parameters=pipe),
            ModuleInstance(id="B2", module_id="source", name="出口",
                           parameters={"pressure_pa": 100000.0, "temperature_k": 353.15}),
        ],
        connections=[link("e1", "B1:out0", "V1:in0"), link("e2", "V1:out0", "L1:in0"),
                     link("e3", "L1:out0", "B2:out0")],
        control_scripts=[script],
    )


def test_p4_pipe_thermal_cells_dynamic_transient():
    frames = solve_dynamic(compile_project(thermal_capacity_project()), duration_s=600.0, dt_s=1.0)
    assert len(frames) == 601
    outlet = [frame.variables["L1.out0.temperature_k"] for frame in frames]

    # t=0 关阀、管段静止在入口温度；之后出口温度单调逼近稳态。
    assert outlet[0] == pytest.approx(353.15, abs=1e-6)
    assert all(after <= before + 1e-9 for before, after in zip(outlet, outlet[1:]))
    assert outlet[-1] < outlet[0] - 10.0

    # 末段变化率趋于 0（dt=1 s）：单步变化远小于初始阶跃段，最后 10 s 也几乎不动。
    assert abs(outlet[-1] - outlet[-2]) < 1e-3
    assert abs(outlet[-1] - outlet[-10]) < 1e-2

    # 壁面 + 流体热容先吸收/释放热量，|stored_power_w| 随时间衰减。
    stored = [abs(frame.variables["L1.state.stored_power_w"]) for frame in frames]
    assert stored[1] > 1.0e5  # t=1 s 时冷却放热约 177 kW
    assert stored[-1] < 1e-3 * max(stored)
    assert stored[-1] < 10.0

    # 稳态对照：N 个 well-mixed cell 串联，g=UA/(N·cp)，h_out=h_env+(h_in−h_env)(w/(w+g))^N。
    # 求解器把 5e5 J/K 壁面热容均分到 4 段（每段并入 cell 质量），与 docs/ALGORITHM 的
    # N 段稳态式一致；温度由同一物性服务反算，这里同时断言焓与温度两个口径。
    last = frames[-1]
    mass_flow = abs(last.variables["L1.mass_flow_kg_s"])
    cp = last.variables["L1.in0.specific_heat_j_kg_k"]
    pressure_out = last.variables["L1.out0.pressure_pa"]
    h_in = last.variables["L1.in0.enthalpy_j_kg"]
    h_env = WATER.state_pt(pressure_out, 293.15).enthalpy_j_kg
    g = 3000.0 / (4 * cp)
    expected_h = h_env + (h_in - h_env) * (mass_flow / (mass_flow + g)) ** 4
    assert last.variables["L1.out0.enthalpy_j_kg"] == pytest.approx(expected_h, rel=1e-6, abs=1e-3)

    expected_t = WATER.state_ph(pressure_out, expected_h).temperature_k
    assert last.variables["L1.out0.temperature_k"] == pytest.approx(expected_t, abs=0.01)
    # 文档的纯温度式在常 cp 下才严格成立；CoolProp 的 cp 随温度变化 ~0.1%，故这里
    # 只用 0.1 K 复核量级，严格判据用上面的焓式。
    simple_t = 293.15 + (353.15 - 293.15) * (mass_flow / (mass_flow + g)) ** 4
    assert outlet[-1] == pytest.approx(simple_t, abs=0.1)

    # 时间常数（到达 63.2% 变化量的时刻）用于标定记录，量级由 cell 质量/(w+g) 决定。
    target = outlet[0] + 0.632 * (outlet[-1] - outlet[0])
    tau63_s = next(frame.time_s for frame, value in zip(frames, outlet) if value <= target)
    assert 20.0 < tau63_s < 300.0


# --- 5. M-4 泵曲线单位 ----------------------------------------------------------


def pump_line(h0, pressure_rise_pa):
    curve = [[0.0, h0], [5.0, 0.75 * h0], [10.0, 0.0]]
    catalog = catalog_map()
    return Project(
        id=f"m4-{pressure_rise_pa:.0f}-{h0:.3f}",
        name="M-4 泵曲线单位",
        modules=[catalog["source"], catalog["pump"]],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="入口",
                           parameters={"pressure_pa": 100000.0, "temperature_k": 293.15}),
            ModuleInstance(id="P1", module_id="pump", name="水泵",
                           parameters={"head_curve": curve, "speed_ratio": 1.0,
                                       "efficiency_ratio": 0.75}),
            ModuleInstance(id="B2", module_id="source", name="出口",
                           parameters={"pressure_pa": 100000.0 + pressure_rise_pa,
                                       "temperature_k": 293.15}),
        ],
        connections=[link("e1", "B1:out0", "P1:in0"), link("e2", "P1:out0", "B2:out0")],
    )


def test_m4_pump_curve_mpa_and_bar_unit_assumptions():
    # 倍思鹿 CURVE_A=0.1：若单位是 MPa，则 H0=0.1e6/(998.275·g)=10.2148 m。
    h0_mpa = 0.1e6 / (998.275 * GRAVITY)
    h0_bar = 0.1e5 / (998.275 * GRAVITY)
    assert h0_mpa == pytest.approx(10.214, abs=1e-3)
    assert h0_bar == pytest.approx(1.021, abs=1e-3)

    # MPa 假设：50 kPa 需求 → 工作点 H=5.107 m、Q≈6.67 m³/h。
    mpa_frame = solve_steady(compile_project(pump_line(h0_mpa, 50000.0)))
    mpa_flow = mpa_frame.variables["P1.volume_flow_m3_h"]
    mpa_head = pump_head([[0.0, h0_mpa], [5.0, 0.75 * h0_mpa], [10.0, 0.0]], mpa_flow, 1.0)
    assert 0.0 < mpa_flow < 10.0
    assert mpa_frame.variables["P1.out0.pressure_pa"] > mpa_frame.variables["P1.in0.pressure_pa"]
    assert mpa_head == pytest.approx(-mpa_frame.variables["P1.pressure_drop_pa"] / (RHO_WATER * GRAVITY),
                                     rel=1e-6)
    assert mpa_frame.variables["P1.mass_flow_kg_s"] > 0.0
    assert [item for item in mpa_frame.diagnostics if item.severity == "error"] == []

    # bar 假设：同一 50 kPa 需求已超过 1.021 m（约 10 kPa）的关死扬程，没有正流量工作点；
    # 因此改用 5 kPa 需求跑通，工作点同为 Q≈6.67 m³/h。CURVE_A 的单位仍未定，需倍思鹿
    # 在同泵同流量下读 EX0_PRE−IM0_PRE 标定后才能定论（MAPPING_A M-4）。
    bar_frame = solve_steady(compile_project(pump_line(h0_bar, 5000.0)))
    bar_flow = bar_frame.variables["P1.volume_flow_m3_h"]
    bar_head = pump_head([[0.0, h0_bar], [5.0, 0.75 * h0_bar], [10.0, 0.0]], bar_flow, 1.0)
    assert 0.0 < bar_flow < 10.0
    assert bar_frame.variables["P1.out0.pressure_pa"] > bar_frame.variables["P1.in0.pressure_pa"]
    assert bar_head == pytest.approx(-bar_frame.variables["P1.pressure_drop_pa"] / (RHO_WATER * GRAVITY),
                                     rel=1e-6)
    # 曲线整体按 H0 缩放：同比例需求下两者流量相同，说明单位假设只改变扬程标尺。
    assert bar_flow == pytest.approx(mpa_flow, rel=1e-6)


# --- 6. 汇总 / 守恒 --------------------------------------------------------------


def test_v4_network_balances_mass_and_registers_valve_relation():
    project = valve_line("valve_equal_percentage", 0.5)
    frame = solve_steady(compile_project(project))

    assert frame.valid
    assert [item for item in frame.diagnostics if item.severity == "error"] == []
    # 两个压力边界的质量流量代数和为零；求解器质量残差容差本身就是 1e-8 kg/s。
    boundary_sum = frame.variables["B1.out0.mass_flow_kg_s"] + frame.variables["B2.out0.mass_flow_kg_s"]
    assert abs(boundary_sum) < 1e-8
    assert frame.metrics["mass_residual_kg_s"] <= project.solver.mass_tolerance_kg_s
    assert frame.variables["V1.mass_flow_kg_s"] > 0.0

    # 模块提交的是 kind="valve" 的 NetworkRelation，而不是 pipe/resistance 近似。
    definition = load_definition()
    response = evaluate(runner_for(definition, opening_ratio=0.5), density_kg_m3=998.2)
    assert [(relation.kind, relation.channel) for relation in response.relations] == [("valve", "main")]
    assert response.relations[0].parameters["opening_ratio"] == pytest.approx(1.0)
    assert frame.variables["V1.cvf"] == pytest.approx(0.09, abs=1e-12)
