from __future__ import annotations

from .models import Connection, Element, MediumDefinition, Position, Project, Scenario


def element(eid, kind, x, y, name="", **parameters):
    return Element(id=eid, type=kind, name=name or eid,
                   position=Position(x=x, y=y), parameters=parameters)


def connect(source, source_port, target, target_port):
    return Connection(id=f"{source}_{source_port}__{target}_{target_port}",
                      source=source, source_port=source_port, target=target, target_port=target_port)


def single_pipe():
    return Project(id="example_single", name="01 · 单管与静压", description="两个压力边界与有高差的管道，检查压降和静压关系。", elements=[
        element("source", "pressure", 80, 220, "上游水源", pressure_pa=301325),
        element("pipe", "pipe", 380, 220, "输水管", length_m=100, diameter_m=0.05, height_change_m=5),
        element("sink", "pressure", 700, 220, "下游水源", pressure_pa=101325),
    ], connections=[connect("source", "p2", "pipe", "in"), connect("pipe", "out", "sink", "p1")],
        selected_variables=["pipe.mass_flow_kg_s", "pipe.pressure_drop_pa"])


def parallel_network():
    return Project(id="example_parallel", name="02 · 泵阀并联管网",
        description="调节任一支路阀门，全网重新分配压力和流量。", elements=[
            element("source", "pressure", 20, 270, "循环水源", pressure_pa=201325),
            element("pump", "pump", 240, 270, "循环泵"),
            element("trunk", "pipe", 450, 270, "主管", length_m=20, diameter_m=0.065),
            element("split", "junction", 670, 280, "分流节点"),
            element("valve_a", "valve", 820, 120, "A 路调节阀", opening=0.8, kv_m3_h=16),
            element("pipe_a", "pipe", 1050, 120, "A 路管道", length_m=30, diameter_m=0.04),
            element("valve_b", "valve", 820, 460, "B 路调节阀", opening=0.55, kv_m3_h=16),
            element("pipe_b", "pipe", 1050, 460, "B 路管道", length_m=40, diameter_m=0.04),
            element("merge", "junction", 1300, 280, "汇流节点"),
            element("sink", "pressure", 1450, 270, "回水边界", pressure_pa=201325),
        ], connections=[
            connect("source", "p2", "pump", "in"), connect("pump", "out", "trunk", "in"),
            connect("trunk", "out", "split", "p1"), connect("split", "p2", "valve_a", "in"),
            connect("valve_a", "out", "pipe_a", "in"), connect("pipe_a", "out", "merge", "p1"),
            connect("split", "p3", "valve_b", "in"), connect("valve_b", "out", "pipe_b", "in"),
            connect("pipe_b", "out", "merge", "p3"), connect("merge", "p2", "sink", "p1"),
        ], selected_variables=["trunk.mass_flow_kg_s", "pipe_a.mass_flow_kg_s", "pipe_b.mass_flow_kg_s"],
        scenarios=[Scenario(id="design", name="设计工况"),
                   Scenario(id="throttled", name="B 路节流", overrides={"valve_b": {"opening": 0.2}}),
                   Scenario(id="low_speed", name="低转速", overrides={"pump": {"speed_ratio": 0.7}})])


def closed_loop():
    p = parallel_network()
    p.id, p.name = "example_loop", "03 · 闭式多环路"
    p.description = "具有温度边界、循环泵与两条支路的闭式循环。"
    p.elements = [e for e in p.elements if e.id != "sink"]
    p.connections = [c for c in p.connections if c.target != "sink"]
    p.elements += [element("return", "pipe", 950, 720, "回水管", length_m=50, diameter_m=0.065),
                   element("heater", "heater", 460, 60, "热负荷", power_w=3000)]
    p.connections = [c for c in p.connections if c.source != "pump"]
    p.connections += [connect("pump", "out", "heater", "in"), connect("heater", "out", "trunk", "in"),
                      connect("merge", "p2", "return", "in"), connect("return", "out", "source", "p1")]
    p.selected_variables += ["heater.outlet_temperature_k"]
    return p


def tanks():
    return Project(id="example_tanks", name="04 · 水箱充排水", description="液位差驱动两水箱交换水，动态积分保持总质量和总焓守恒。", elements=[
        element("tank_a", "tank_open", 100, 220, "上游水箱", area_m2=0.5, capacity_m3=2, initial_level_m=2.5, temperature_k=303.15),
        element("valve", "valve", 400, 220, "联通阀", kv_m3_h=4, opening=0.6),
        element("pipe", "pipe", 680, 220, "联通管", diameter_m=0.025, length_m=10),
        element("tank_b", "tank_open", 950, 220, "下游水箱", area_m2=0.7, capacity_m3=2, initial_level_m=0.5),
    ], connections=[connect("tank_a", "p2", "valve", "in"), connect("valve", "out", "pipe", "in"),
                     connect("pipe", "out", "tank_b", "p1")],
        selected_variables=["tank_a.level_m", "tank_b.level_m", "tank_a.mass_kg", "tank_b.mass_kg", "tank_b.temperature_k", "pipe.mass_flow_kg_s"])


def exchanger():
    p = Project(id="example_exchanger", name="05 · 双回路换热", description="换热器两侧分别引用介质配置；首版均为液态水，温度独立。",
        default_medium_id="hot_water", media=[MediumDefinition(id="hot_water", name="热侧水"), MediumDefinition(id="cold_water", name="冷侧水")], elements=[
            element("hot", "pressure", 80, 100, "热侧入口", pressure_pa=251325, temperature_k=333.15),
            element("hot_pipe", "pipe", 350, 100, "热侧管道", length_m=30, diameter_m=0.025),
            element("hx", "heat_exchanger", 670, 270, "水—水换热器", ua_w_k=2000, diameter_m=0.025, loss_coefficient=5),
            element("hot_out", "pressure", 1040, 100, "热侧出口", pressure_pa=201325, temperature_k=303.15),
            element("cold", "pressure", 80, 460, "冷侧入口", pressure_pa=251325, temperature_k=293.15),
            element("cold_pipe", "pipe", 350, 460, "冷侧管道", length_m=30, diameter_m=0.025),
            element("cold_out", "pressure", 1040, 460, "冷侧出口", pressure_pa=201325, temperature_k=303.15),
        ], connections=[connect("hot", "p2", "hot_pipe", "in"), connect("hot_pipe", "out", "hx", "a_in"),
                        connect("hx", "a_out", "hot_out", "p1"), connect("cold", "p2", "cold_pipe", "in"),
                        connect("cold_pipe", "out", "hx", "b_in"), connect("hx", "b_out", "cold_out", "p1")],
        selected_variables=["hx.a.outlet_temperature_k", "hx.b.outlet_temperature_k", "hx.a.heat_w", "hx.b.heat_w"])
    next(e for e in p.elements if e.id == "hx").media = {"a": "hot_water", "b": "cold_water"}
    return p


def controlled():
    p = parallel_network()
    p.id, p.name = "example_pid", "06 · PID 流量控制"
    p.description = "PID 调节循环泵转速，使主管质量流量追踪目标。"
    p.elements.append(element("controller", "pid", 240, 600, "流量 PID", measurement="trunk.mass_flow_kg_s", target_element="pump", target_parameter="speed_ratio", setpoint=1.5, kp=0.15, ki=0.08, output_min=0.2, output_max=1.3, period_s=0.1))
    p.selected_variables = ["trunk.mass_flow_kg_s", "pump.speed_ratio", "controller.output", "controller.error"]
    return p


EXAMPLES = [single_pipe, parallel_network, closed_loop, tanks, exchanger, controlled]


def example_projects():
    return [make() for make in EXAMPLES]


def example_templates():
    from .catalog import CATALOG
    from .models import ModuleInterface
    from .modules import infer_interface, normalize_template
    pump = Project(name="泵阀组合", elements=[
        element("pump", "pump", 0, 80, "循环泵"),
        element("valve", "valve", 230, 80, "调节阀", opening=0.7, kv_m3_h=16),
        element("pipe", "pipe", 460, 80, "出水管", length_m=20, diameter_m=0.05),
    ], connections=[connect("pump", "out", "valve", "in"), connect("valve", "out", "pipe", "in")],
        selected_variables=["pipe.mass_flow_kg_s", "pump.head_m"])
    hx = exchanger()
    chosen = {"hot_pipe", "hx", "cold_pipe"}
    hx.elements = [e for e in hx.elements if e.id in chosen]
    hx.connections = [c for c in hx.connections if c.source in chosen and c.target in chosen]
    hx.name = "双侧换热机组"
    for e in hx.elements:
        e.media = ({"a": "hot_water", "b": "cold_water"} if e.type == "heat_exchanger" else
                   {"fluid": "cold_water" if e.id == "cold_pipe" else "hot_water"})
    tank = tanks()
    tank.name = "水箱调节单元"
    definitions = []
    for key, graph in (("builtin_pump_group", pump), ("builtin_exchanger_group", hx), ("builtin_tank_group", tank)):
        interface = infer_interface(graph.elements, graph.connections)
        if key == "builtin_tank_group":
            interface = ModuleInterface(exposed_parameters={"opening": "valve.opening", "level_a": "tank_a.initial_level_m", "level_b": "tank_b.initial_level_m"},
                                        parameter_labels={"opening": "联通阀开度", "level_a": "上游初始液位", "level_b": "下游初始液位"})
        for e in graph.elements:
            for p in CATALOG[e.type]["ports"]:
                e.media.setdefault(p["group"], graph.default_medium_id)
        conditions = {}
        for alias, target in interface.exposed_ports.items():
            if key == "builtin_exchanger_group":
                inlet = target.endswith(":in")
                conditions[alias] = {"pressure_pa": 251325 if inlet else 201325,
                                     "temperature_k": 333.15 if target.startswith("hot_pipe:") else 293.15}
            else:
                conditions[alias] = {"pressure_pa": 201325, "temperature_k": 293.15}
        result = normalize_template({"name": graph.name, "kind": "group", "body": graph.model_dump(),
                                     "interface": interface.model_dump(), "test_conditions": conditions})
        definitions.append({**result, "id": key})
    return definitions
