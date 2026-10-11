from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .catalog import CATALOG, get_parameters
from .errors import Diagnostic, ModelError
from .media import MediumRegistry
from .models import Project


class UnionFind:
    def __init__(self, items):
        self.parents = {key: key for key in items}

    def find(self, key):
        if self.parents[key] != key:
            self.parents[key] = self.find(self.parents[key])
        return self.parents[key]

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parents[max(a, b)] = min(a, b)


@dataclass
class Branch:
    id: str
    element_id: str
    kind: str
    start: int
    end: int
    medium_id: str
    parameters: dict
    path: str = "fluid"


@dataclass
class Network:
    project: Project
    registry: MediumRegistry
    node_ids: list[str]
    port_nodes: dict[str, int]
    node_media: list[str]
    branches: list[Branch]
    boundaries: dict[int, list[str]]
    parameters: dict[str, dict]
    circuits: list[dict]
    warnings: list[Diagnostic] = field(default_factory=list)


def compile_project(project: Project) -> Network:
    if not project.elements:
        raise ModelError("EMPTY_PROJECT", "请先添加流体元件并连接网络")
    elements = {element.id: element for element in project.elements}
    parameters = {e.id: get_parameters(e) for e in project.elements}
    ports = {}
    for e in project.elements:
        for p in CATALOG[e.type]["ports"]:
            ports[f"{e.id}:{p['id']}"] = (e.id, p)
    if not ports:
        raise ModelError("EMPTY_NETWORK", "项目只有控制器，没有流体网络")
    physical = UnionFind(ports)
    medium_graph = UnionFind(ports)
    usage = {key: 0 for key in ports}
    seen_links = set()
    for c in project.connections:
        start, end = f"{c.source}:{c.source_port}", f"{c.target}:{c.target_port}"
        if start not in ports or end not in ports:
            raise ModelError("PORT_MISSING", f"连接 {c.id} 引用了不存在的端口", c.source)
        if start == end:
            raise ModelError("SELF_CONNECTION", "不能把端口连接到自身", c.source)
        key = tuple(sorted([start, end]))
        if key in seen_links:
            raise ModelError("DUPLICATE_CONNECTION", "两个端口之间存在重复连接", c.source)
        seen_links.add(key)
        for p in (start, end):
            usage[p] += 1
            if usage[p] > 1:
                raise ModelError("PORT_MULTIPLE_CONNECTIONS", "一个端口只允许一条外部连接，请添加连接节点分支", ports[p][0])
        physical.union(start, end)
        medium_graph.union(start, end)
    for eid, e in elements.items():
        ps = CATALOG[e.type]["ports"]
        for p in ps:
            if p["required"] and not usage[f"{eid}:{p['id']}"]:
                raise ModelError("PORT_UNCONNECTED", f"{e.name or eid} 的 {p['label']} 尚未连接", eid, p["id"])
        if ps and not any(usage[f"{eid}:{p['id']}"] for p in ps):
            raise ModelError("ELEMENT_UNCONNECTED", f"{e.name or eid} 未连接到网络", eid)
        groups = {}
        for p in ps:
            groups.setdefault(p["group"], []).append(f"{eid}:{p['id']}")
        for group_ports in groups.values():
            for other in group_ports[1:]:
                medium_graph.union(group_ports[0], other)
            if e.type in {"junction", "pressure", "tank_open", "tank_gas"}:
                for other in group_ports[1:]:
                    physical.union(group_ports[0], other)
        if set(e.media) - set(groups):
            raise ModelError("MEDIUM_PATH_UNKNOWN", "介质配置引用了不存在的内部通路", eid)
    registry = MediumRegistry(project.media)
    circuit_ports = {}
    for key in ports:
        circuit_ports.setdefault(medium_graph.find(key), []).append(key)
    port_medium = {}
    circuits = []
    for members in circuit_ports.values():
        assigned = set()
        for key in members:
            eid, p = ports[key]
            assigned_id = elements[eid].media.get(p["group"])
            if assigned_id:
                assigned.add(assigned_id)
        if len(assigned) > 1:
            raise ModelError("MEDIUM_CONFLICT", f"同一流体回路配置了多个介质：{', '.join(sorted(assigned))}", ports[members[0]][0])
        mid = next(iter(assigned), project.default_medium_id)
        try:
            registry.get(mid)
        except ModelError as exc:
            exc.diagnostic.element_id = ports[members[0]][0]
            raise
        for key in members:
            port_medium[key] = mid
        circuits.append({"id": hashlib.sha1("|".join(sorted(members)).encode()).hexdigest()[:12],
                         "medium_id": mid, "ports": sorted(members)})
    node_ids = sorted({physical.find(key) for key in ports})
    index = {key: i for i, key in enumerate(node_ids)}
    port_nodes = {key: index[physical.find(key)] for key in ports}
    node_media = [port_medium[key] for key in node_ids]
    branches, boundaries = [], {}
    def branch(e, start, end, kind=None, path="fluid"):
        a, b = port_nodes[f"{e.id}:{start}"], port_nodes[f"{e.id}:{end}"]
        if a == b:
            raise ModelError("SHORT_CIRCUIT", "元件两端被理想连接短接，支路流量可能不唯一", e.id)
        branches.append(Branch(f"{e.id}:{path}", e.id, kind or e.type, a, b,
                               port_medium[f"{e.id}:{start}"], parameters[e.id], path))
    for e in project.elements:
        definition = CATALOG[e.type]
        if definition.get("boundary"):
            node = port_nodes[f"{e.id}:{definition['ports'][0]['id']}"]
            boundaries.setdefault(node, []).append(e.id)
        elif e.type == "heat_exchanger":
            branch(e, "a_in", "a_out", path="a")
            branch(e, "b_in", "b_out", path="b")
        elif e.type == "three_way":
            branch(e, "common", "a", "valve", path="a")
            branch(e, "common", "b", "valve", path="b")
        elif e.type not in {"junction", "pid", "timer"}:
            branch(e, "in", "out")
    if not branches:
        raise ModelError("NO_BRANCHES", "请添加至少一条具有设备关系的支路")
    for e in project.elements:
        if CATALOG[e.type].get("control"):
            p = parameters[e.id]
            target = elements.get(p["target_element"])
            if target is None:
                raise ModelError("CONTROL_TARGET_MISSING", "控制器的受控元件不存在", e.id)
            field = next((f for f in CATALOG[target.type]["parameters"]
                          if f["key"] == p["target_parameter"] and f.get("runtime")), None)
            if field is None:
                raise ModelError("CONTROL_TARGET_INVALID", "目标参数不能在运行中修改", e.id)
            if e.type == "pid":
                measurement_id, _, variable = p["measurement"].partition(".")
                if measurement_id not in elements or not variable:
                    raise ModelError("CONTROL_MEASUREMENT_MISSING", "测量变量引用无效", e.id)
    return Network(project, registry, node_ids, port_nodes, node_media, branches,
                   boundaries, parameters, circuits)


def validate_project(project: Project):
    try:
        net = compile_project(project)
        from .hydraulics import boundary_values, check_anchors
        fixed, _, _ = boundary_values(net)
        check_anchors(net, fixed, set())
        return {"valid": True, "diagnostics": [x.to_dict() for x in net.warnings],
                "circuits": net.circuits, "node_count": len(net.node_ids),
                "branch_count": len(net.branches)}
    except ModelError as exc:
        return {"valid": False, "diagnostics": [exc.diagnostic.to_dict()], "circuits": []}
