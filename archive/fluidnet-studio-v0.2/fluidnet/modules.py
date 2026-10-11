"""Reusable equipment definitions and flat, independently owned group instances."""
from __future__ import annotations

import re
from copy import deepcopy

from .catalog import CATALOG, VARIABLES, get_parameters
from .errors import ModelError
from .models import (Element, Group, ModuleInterface, Position, Project, TemplateRequest,
                     TestBoundary, new_id)


def _address(address, ids, separator):
    eid, mark, field = address.partition(separator)
    if not mark or eid not in ids:
        raise ValueError(f"引用不存在的内部元件：{address}")
    return eid, field


def _remap(address, ids, separator):
    eid, field = _address(address, ids, separator)
    return ids[eid] + separator + field


def infer_interface(elements, connections):
    internal = {f"{c.source}:{c.source_port}" for c in connections}
    internal.update(f"{c.target}:{c.target_port}" for c in connections)
    interface = ModuleInterface()
    for e in elements:
        definition = CATALOG.get(e.type)
        if definition is None:
            raise ValueError(f"未知元件类型：{e.type}")
        for port in definition["ports"]:
            target = f"{e.id}:{port['id']}"
            if target not in internal:
                alias = f"P{len(interface.exposed_ports) + 1}"
                interface.exposed_ports[alias] = target
                interface.port_labels[alias] = f"{e.name or e.type} · {port['label']}"
        for parameter in definition["parameters"]:
            if parameter.get("runtime"):
                alias = f"param_{len(interface.exposed_parameters) + 1}"
                interface.exposed_parameters[alias] = f"{e.id}.{parameter['key']}"
                interface.parameter_labels[alias] = f"{e.name or e.type} · {parameter['label']}"
    return interface


def validate_interface(elements, connections, interface, complete=False):
    ids = {e.id: e for e in elements}
    ports = {f"{e.id}:{p['id']}": p for e in elements
             for p in CATALOG.get(e.type, {}).get("ports", [])}
    used = set()
    for c in connections:
        ends = (f"{c.source}:{c.source_port}", f"{c.target}:{c.target_port}")
        for end in ends:
            if end not in ports:
                raise ValueError(f"内部连接引用不存在的端口：{end}")
            if end in used:
                raise ValueError(f"内部端口重复连接：{end}")
            used.add(end)
    for mapping in (interface.exposed_ports, interface.exposed_parameters):
        if len(set(mapping.values())) != len(mapping):
            raise ValueError("同一内部端口或参数只能暴露一次")
        for alias in mapping:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", alias):
                raise ValueError(f"接口 ID 仅支持字母、数字、下划线、连字符：{alias}")
    for alias, target in interface.exposed_ports.items():
        if target not in ports or target in used:
            raise ValueError(f"对外端口 {alias} 必须引用未在内部连接的流体端口：{target}")
    for alias, target in interface.exposed_parameters.items():
        eid, key = _address(target, ids, ".")
        if key not in {p["key"] for p in CATALOG[ids[eid].type]["parameters"]}:
            raise ValueError(f"对外参数 {alias} 引用不存在的模型参数：{target}")
    if complete:
        exposed = set(interface.exposed_ports.values())
        for target, port in ports.items():
            if port["required"] and target not in used and target not in exposed:
                raise ValueError(f"必需端口既未内部连接，也未暴露：{target}")
        for e in elements:
            params = get_parameters(e)
            if not CATALOG[e.type].get("control"):
                continue
            target = ids.get(params.get("target_element"))
            if target is None:
                raise ValueError(f"{e.name} 的控制目标必须位于组合内部")
            if not any(p["key"] == params.get("target_parameter") and p.get("runtime")
                       for p in CATALOG[target.type]["parameters"]):
                raise ValueError(f"{e.name} 的目标参数不支持运行时调节")
            if e.type == "pid":
                _, variable = _address(params.get("measurement", ""), ids, ".")
                if variable.rsplit(".", 1)[-1] not in VARIABLES:
                    raise ValueError(f"{e.name} 的测量变量无效")


def group_interface(group):
    return ModuleInterface(**{key: getattr(group, key) for key in ModuleInterface.model_fields})


def validate_groups(project):
    elements = {e.id: e for e in project.elements}
    claimed = set()
    for group in project.groups:
        members = set(group.element_ids)
        if not members or len(members) != len(group.element_ids) or not members <= elements.keys():
            raise ValueError(f"组合 {group.name} 的成员为空、重复或不存在")
        if claimed & members:
            raise ValueError("首版只支持单层组合，一个元件只能属于一个组合")
        claimed.update(members)
        if any(elements[eid].group_id != group.id for eid in members):
            raise ValueError(f"组合 {group.name} 的成员归属不一致")
        if any(elements[eid].page != group.page for eid in members):
            raise ValueError("同一组合的成员必须位于同一项目画布")
        if not set(group.member_keys.values()) <= members or len(set(group.member_keys.values())) != len(group.member_keys):
            raise ValueError("组合的内部稳定 ID 映射无效")
        connections = [c for c in project.connections if c.source in members and c.target in members]
        validate_interface([elements[eid] for eid in group.element_ids], connections, group_interface(group))
        exposed = set(group.exposed_ports.values())
        for c in project.connections:
            if (c.source in members) != (c.target in members):
                address = f"{c.source}:{c.source_port}" if c.source in members else f"{c.target}:{c.target_port}"
                if address not in exposed:
                    raise ValueError(f"组合 {group.name} 的已有外连端口不能移除：{address}")
    group_ids = {g.id for g in project.groups}
    for e in project.elements:
        if e.group_id is not None and (e.group_id not in group_ids or e.id not in claimed):
            raise ValueError(f"元件 {e.name} 引用了不存在的组合")


def normalize_template(template):
    """Validate a portable definition, never accepting executable module code."""
    request = template if isinstance(template, TemplateRequest) else TemplateRequest.model_validate(
        {k: v for k, v in template.items() if k in TemplateRequest.model_fields})
    if request.kind == "equipment":
        e = Element.model_validate({**request.body, "group_id": None})
        get_parameters(e)
        graph = Project(elements=[e])
        body = e.model_dump()
    else:
        raw = deepcopy(request.body)
        if raw.get("groups"):
            raise ValueError("组合模板内部不能再嵌套组合；请先解散内部组合")
        for e in raw.get("elements", []):
            e["group_id"] = None
        graph = Project.model_validate(raw)
        if not graph.elements:
            raise ValueError("组合模板至少需要一个元件")
        for e in graph.elements:
            get_parameters(e)
        body = graph.model_dump()
    interface = request.interface if request.interface is not None else infer_interface(graph.elements, graph.connections)
    validate_interface(graph.elements, graph.connections, interface, complete=True)
    conditions = {k: v.model_dump() for k, v in request.test_conditions.items()}
    if set(conditions) - interface.exposed_ports.keys():
        raise ValueError("测试条件引用了不存在的对外端口")
    for i, alias in enumerate(interface.exposed_ports):
        conditions.setdefault(alias, TestBoundary(pressure_pa=301325 if i % 2 == 0 else 101325).model_dump())
    return {"name": request.name, "kind": request.kind, "body": body,
            "interface": interface.model_dump(), "test_conditions": conditions,
            "revision": request.revision}


def configure_group(project, element_ids, name, interface=None, group_id=None):
    data = project.model_dump()
    selected = set(element_ids)
    members = [e for e in project.elements if e.id in selected]
    if not members or len(members) != len(selected):
        raise ValueError("请选择存在的内部元件")
    if len({e.page for e in members}) != 1:
        raise ValueError("只能封装同一画布的元件")
    previous = next((g for g in project.groups if g.id == group_id), None)
    if group_id and previous is None:
        raise ValueError("组合不存在")
    if previous and set(previous.element_ids) != selected:
        raise ValueError("请在内部画布添加或删除组合成员")
    if any(e.group_id and e.group_id != group_id for e in members):
        raise ValueError("不支持嵌套组合；请先解散已选中的组合")
    links = [c for c in project.connections if c.source in selected and c.target in selected]
    chosen = interface or (group_interface(previous) if previous else infer_interface(members, links))
    validate_interface(members, links, chosen, complete=True)
    # Enforce control closure when publishing a new interface as well.
    raw = previous.model_dump() if previous else {
        "id": new_id(), "collapsed": True, "page": members[0].page,
        "position": {"x": min(e.position.x for e in members), "y": min(e.position.y for e in members)},
        "member_keys": {e.id: e.id for e in members}}
    raw.update(name=name, element_ids=[e.id for e in members], **chosen.model_dump())
    data["groups"] = [g for g in data["groups"] if g["id"] != raw["id"]] + [raw]
    for e in data["elements"]:
        if e["id"] in selected:
            e["group_id"] = raw["id"]
    return Project.model_validate(data), raw["id"]


def extract_group(project, group_id):
    group = next((g for g in project.groups if g.id == group_id), None)
    if group is None:
        raise ValueError("组合不存在")
    members = set(group.element_ids)
    inverse = {eid: key for key, eid in group.member_keys.items()}
    inverse.update({eid: eid for eid in members if eid not in inverse})
    body = project.model_dump()
    body.update(id=new_id(), name=group.name, revision=0, groups=[], scenarios=[])
    body["elements"] = [e for e in body["elements"] if e["id"] in members]
    for e in body["elements"]:
        e["id"] = inverse[e["id"]]
        e["group_id"] = None
        e["position"]["x"] -= group.position.x
        e["position"]["y"] -= group.position.y
        e["page"] = 0
        _remap_control(e["parameters"], inverse)
        for p in CATALOG[e["type"]]["ports"]:
            e["media"].setdefault(p["group"], project.default_medium_id)
    body["connections"] = [c for c in body["connections"] if c["source"] in members and c["target"] in members]
    for c in body["connections"]:
        c["source"], c["target"] = inverse[c["source"]], inverse[c["target"]]
    body["selected_variables"] = [_remap(v, inverse, ".") for v in project.selected_variables
                                  if v.partition(".")[0] in members]
    interface = group_interface(group).model_dump()
    interface["exposed_ports"] = {a: _remap(v, inverse, ":") for a, v in group.exposed_ports.items()}
    interface["exposed_parameters"] = {a: _remap(v, inverse, ".") for a, v in group.exposed_parameters.items()}
    return normalize_template({"name": group.name, "kind": "group", "body": body, "interface": interface})


def _remap_control(parameters, ids):
    target = parameters.get("target_element")
    if target:
        if target not in ids:
            raise ValueError(f"控制目标 {target} 位于组合外部，模板必须完整封装控制引用")
        parameters["target_element"] = ids[target]
    measurement = parameters.get("measurement")
    if measurement:
        parameters["measurement"] = _remap(measurement, ids, ".")


def _merge_media(destination, source):
    mapping = {}
    def signature(m):
        return {k: v for k, v in m.items() if k != "id"}
    for medium in source:
        existing = next((m for m in destination if signature(m) == signature(medium)), None)
        if existing:
            mapping[medium["id"]] = existing["id"]
        else:
            clone = deepcopy(medium)
            if any(m["id"] == clone["id"] for m in destination):
                clone["id"] = "medium_" + new_id()
            mapping[medium["id"]] = clone["id"]
            destination.append(clone)
    return mapping


def _clone_group(data, template, position, page, previous=None):
    definition = normalize_template(template)
    graph = Project.model_validate(definition["body"])
    ids = {e.id: (previous.member_keys.get(e.id) if previous else None) or new_id() for e in graph.elements}
    media = _merge_media(data["media"], [m.model_dump() for m in graph.media])
    group_id = previous.id if previous else new_id()
    elements = []
    for source in graph.elements:
        e = source.model_dump()
        e.update(id=ids[source.id], group_id=group_id, page=page,
                 position={"x": position.x + source.position.x, "y": position.y + source.position.y})
        _remap_control(e["parameters"], ids)
        e["media"] = {p["group"]: media[source.media.get(p["group"], graph.default_medium_id)]
                      for p in CATALOG[e["type"]]["ports"]}
        elements.append(e)
    connections = [{**c.model_dump(), "id": new_id(), "source": ids[c.source], "target": ids[c.target]}
                   for c in graph.connections]
    interface = definition["interface"]
    group = Group(id=group_id, name=previous.name if previous else definition["name"],
                  element_ids=list(ids.values()), member_keys=ids, position=position, page=page,
                  collapsed=previous.collapsed if previous else True,
                  template_id=template.get("id"), template_revision=template.get("revision") or None,
                  exposed_ports={a: _remap(v, ids, ":") for a, v in interface["exposed_ports"].items()},
                  exposed_parameters={a: _remap(v, ids, ".") for a, v in interface["exposed_parameters"].items()},
                  port_labels=interface["port_labels"], parameter_labels=interface["parameter_labels"])
    variables = [_remap(v, ids, ".") for v in graph.selected_variables]
    return elements, connections, group, variables


def insert_template(project, template, position=None, page=0):
    definition = normalize_template(template)
    data = project.model_dump()
    position = position or Position(x=200, y=200)
    if definition["kind"] == "equipment":
        e = deepcopy(definition["body"])
        e.update(id=new_id(), name=definition["name"], position=position.model_dump(), page=page,
                 group_id=None, media={}, template_id=template.get("id"),
                 template_revision=template.get("revision") or None)
        data["elements"].append(e)
        return Project.model_validate(data), None, [e["id"]]
    elements, connections, group, variables = _clone_group(data, template, position, page)
    data["elements"].extend(elements)
    data["connections"].extend(connections)
    data["groups"].append(group.model_dump())
    data["selected_variables"] = list(dict.fromkeys([*data["selected_variables"], *variables]))[:64]
    return Project.model_validate(data), group.id, group.element_ids


def apply_template(project, template, group_id=None, element_id=None):
    """Return an atomic preview; callers explicitly decide whether to install it."""
    definition = normalize_template(template)
    data = project.model_dump()
    changes = {"added": [], "removed": [], "parameters": [], "interfaces": [], "connections": 0}
    if definition["kind"] == "equipment":
        current = next((e for e in data["elements"] if e["id"] == element_id), None)
        if current is None or current["type"] != definition["body"]["type"]:
            raise ValueError("设备型号只能应用到同类型元件")
        before = get_parameters(Element.model_validate(current))
        after = get_parameters(Element.model_validate(definition["body"]))
        changes["parameters"] = [f"{current['name']} · {key}: {before.get(key)} → {value}"
                                 for key, value in after.items() if before.get(key) != value]
        current.update(parameters=after, template_id=template.get("id"),
                       template_revision=template.get("revision") or None)
        candidate = Project.model_validate(data)
        _validate_references(candidate)
        return candidate, changes
    previous = next((g for g in project.groups if g.id == group_id), None)
    if previous is None:
        raise ValueError("请选择要应用版本的组合实例")
    if previous.template_id and template.get("id") != previous.template_id:
        raise ValueError("组合版本必须来自同一型号；其他型号请作为新实例插入")
    old_members = set(previous.element_ids)
    old_elements = {e.id: e for e in project.elements if e.id in old_members}
    elements, connections, group, _ = _clone_group(data, template, previous.position, previous.page, previous)
    new_elements = {e["id"]: e for e in elements}
    for label, before, after, before_labels, after_labels in (
            ("端口", previous.exposed_ports, group.exposed_ports, previous.port_labels, group.port_labels),
            ("参数", previous.exposed_parameters, group.exposed_parameters, previous.parameter_labels, group.parameter_labels)):
        changes["interfaces"].extend(f"{label} {alias}: {before.get(alias, '无')} → {after.get(alias, '无')}"
                                     for alias in sorted(before.keys() | after.keys()) if before.get(alias) != after.get(alias))
        changes["interfaces"].extend(f"{label} {alias} 名称: {before_labels.get(alias, alias)} → {after_labels.get(alias, alias)}"
                                     for alias in sorted(before.keys() & after.keys())
                                     if before_labels.get(alias, alias) != after_labels.get(alias, alias))
    changes["added"] = [e["name"] or e["id"] for e in elements if e["id"] not in old_members]
    changes["removed"] = [e.name or e.id for e in old_elements.values() if e.id not in new_elements]
    for eid, e in new_elements.items():
        if eid in old_elements:
            before = get_parameters(old_elements[eid])
            after = get_parameters(Element.model_validate(e))
            changes["parameters"].extend(f"{e['name']} · {key}: {before.get(key)} → {value}"
                                         for key, value in after.items() if before.get(key) != value)
    endpoint_map = {target: group.exposed_ports[alias] for alias, target in previous.exposed_ports.items()
                    if alias in group.exposed_ports}
    kept = []
    old_internal = {}
    for c in data["connections"]:
        if c["source"] in old_members and c["target"] in old_members:
            old_internal[(c["source"], c["source_port"], c["target"], c["target_port"])] = c["id"]
            continue
        for end in ("source", "target"):
            if c[end] in old_members:
                target = endpoint_map.get(c[end] + ":" + c[end + "_port"])
                if target is None:
                    raise ValueError(f"外部连接 {c['id']} 使用的接口已移除；原实例保持不变")
                c[end], c[end + "_port"] = target.split(":", 1)
        kept.append(c)
    new_internal = set()
    for c in connections:
        key = (c["source"], c["source_port"], c["target"], c["target_port"])
        new_internal.add(key)
        c["id"] = old_internal.get(key, c["id"])
    changes["connections"] = len(set(old_internal) ^ new_internal)
    data["elements"] = [e for e in data["elements"] if e["id"] not in old_members] + elements
    data["connections"] = kept + connections
    data["groups"] = [g for g in data["groups"] if g["id"] != group_id] + [group.model_dump()]
    candidate = Project.model_validate(data)
    _validate_references(candidate)
    return candidate, changes


def _supports_variable(kind, variable):
    if kind == "pid":
        return variable in {"output", "error"}
    if kind == "timer":
        return variable == "output"
    if kind == "junction":
        return variable in {"pressure_pa", "temperature_k"}
    if CATALOG[kind].get("boundary"):
        allowed = {"pressure_pa", "temperature_k", "mass_flow_kg_s", "volume_flow_m3_h", "enthalpy_j_kg", "boundary_heat_w"}
        if kind.startswith("tank_"):
            allowed.update({"mass_kg", "level_m", "stored_energy_j"})
        return variable in allowed
    if kind in {"heat_exchanger", "three_way"}:
        side, separator, variable = variable.partition(".")
        if not separator or side not in {"a", "b"}:
            return False
    allowed = {"mass_flow_kg_s", "volume_flow_m3_h", "inlet_pressure_pa", "outlet_pressure_pa",
               "pressure_drop_pa", "inlet_temperature_k", "temperature_k", "outlet_temperature_k",
               "density_kg_m3", "velocity_m_s", "reynolds", "closed", "heat_w", "power_w", "unmet_heat_w"}
    if kind == "pipe":
        allowed.update({"friction_factor", "stored_energy_j"})
    if kind in {"valve", "three_way"}:
        allowed.add("opening")
    if kind == "pump":
        allowed.update({"speed_ratio", "head_m"})
    return variable in allowed


def _validate_references(project):
    elements = {e.id: e for e in project.elements}
    conflicts = []
    for scenario in project.scenarios:
        for eid, values in scenario.overrides.items():
            if eid not in elements:
                conflicts.append(f"工况 {scenario.name} 引用了被移除的元件 {eid}")
                continue
            try:
                clone = elements[eid].model_copy(deep=True)
                clone.parameters.update(values)
                get_parameters(clone)
            except ModelError as error:
                conflicts.append(f"工况 {scenario.name}：{error}")
    for path in project.selected_variables:
        eid, _, variable = path.partition(".")
        if eid not in elements or not _supports_variable(elements[eid].type, variable):
            conflicts.append(f"记录变量失效：{path}")
    for e in project.elements:
        p = get_parameters(e)
        if CATALOG[e.type].get("control"):
            target = elements.get(p.get("target_element"))
            if target is None or not any(d["key"] == p.get("target_parameter") and d.get("runtime")
                                         for d in CATALOG[target.type]["parameters"]):
                conflicts.append(f"控制器 {e.name} 的目标失效")
            if e.type == "pid":
                eid, _, variable = p.get("measurement", "").partition(".")
                if eid not in elements or not _supports_variable(elements[eid].type, variable):
                    conflicts.append(f"控制器 {e.name} 的测量引用失效")
    if conflicts:
        raise ValueError("；".join(conflicts) + "；请先处理这些引用，原实例保持不变")


def make_bench(template):
    definition = normalize_template(template)
    if definition["kind"] == "group":
        data = deepcopy(definition["body"])
    else:
        e = Element.model_validate({**definition["body"], "media": {}, "group_id": None})
        data = Project(elements=[e]).model_dump()
    data.update(id=new_id(), name="验证 · " + definition["name"], revision=0, groups=[], scenarios=[])
    elements = {e["id"]: e for e in data["elements"]}
    for i, (alias, address) in enumerate(definition["interface"]["exposed_ports"].items()):
        eid, port = address.split(":", 1)
        member = elements[eid]
        port_def = next(p for p in CATALOG[member["type"]]["ports"] if p["id"] == port)
        medium = member["media"].get(port_def["group"], data["default_medium_id"])
        boundary = Element(id="bench_" + new_id(), type="pressure", name="测试边界 · " + alias,
                           parameters={**definition["test_conditions"][alias], "temperature_fixed": True},
                           media={"fluid": medium}, position=Position(x=-240 if i % 2 == 0 else 650, y=i * 140))
        data["elements"].append(boundary.model_dump())
        data["connections"].append({"id": new_id(), "source": boundary.id, "source_port": "p2",
                                     "target": eid, "target_port": port})
    if not data["selected_variables"]:
        data["selected_variables"] = [f"{e['id']}.mass_flow_kg_s" for e in elements.values()
                                      if e["type"] not in {"junction", "pid", "timer", "heat_exchanger", "three_way"}][:6]
    return Project.model_validate(data)
