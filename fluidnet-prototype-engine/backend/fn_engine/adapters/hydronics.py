"""Closed-loop radial water sizing, independent of building/business object models.

Every segment describes the combined supply/return length and loss coefficient.
Flows are prescribed by terminal heat duties; this is a design calculation, not
an unbalanced network operating-point simulation. Catalog curves are never extrapolated.
"""
from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import Field, model_validator

from fn_sdk import pipe_pressure_drop_pa, resistance_pressure_drop_pa
from ..model_types.base import FluidConfig
from ..properties import property_service
from .contracts import AdapterModel
from .registry import AdapterDefinition

G = 9.80665


class PipeSize(AdapterModel):
    dn: int = Field(gt=0, le=2000)
    inner_diameter_m: float = Field(gt=0, le=2)


class DesignSegment(AdapterModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None
    heat_load_w: float = Field(default=0, ge=0, le=1e9)
    length_m: float = Field(default=20, ge=0, le=10000)
    local_loss_coefficient: float = Field(default=3, ge=0, le=1000)
    equipment_pressure_drop_pa: float = Field(default=0, ge=0, le=1e7)
    valve_pressure_drop_pa: float = Field(default=0, ge=0, le=1e6)
    fixed_dn: int | None = Field(default=None, gt=0)


class CurvePoint(AdapterModel):
    flow_m3_h: float = Field(ge=0, le=1e6)
    head_m: float = Field(ge=0, le=1e4)
    efficiency: float = Field(gt=0, le=1, description='Overall wire-to-water efficiency.')


class CatalogItem(AdapterModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    data_kind: Literal['example', 'manufacturer']
    source: str = Field(min_length=1, max_length=1000)


class PumpSpec(CatalogItem):
    points: list[CurvePoint] = Field(min_length=2, max_length=100)
    min_flow_m3_h: float = Field(ge=0)
    max_flow_m3_h: float = Field(gt=0)

    @model_validator(mode='after')
    def curve_valid(self) -> Self:
        if not self.points[0].flow_m3_h <= self.min_flow_m3_h < self.max_flow_m3_h <= self.points[-1].flow_m3_h:
            raise ValueError('泵推荐流量范围必须位于曲线范围内')
        for a, b in zip(self.points, self.points[1:]):
            if b.flow_m3_h <= a.flow_m3_h or b.head_m > a.head_m:
                raise ValueError('泵曲线要求流量严格递增，扬程不递增')
        return self


class ValveSpec(CatalogItem):
    dn: int = Field(gt=0, le=2000)
    kvs_m3_h: float = Field(gt=0, le=1e6)


class HydronicDesignInput(AdapterModel):
    temperature_k: float = Field(default=282.65, ge=274.15, le=363.15)
    temperature_difference_k: float = Field(default=5, gt=0, le=50)
    roughness_m: float = Field(default=.000045, ge=0, le=.005)
    max_velocity_m_s: float = Field(default=1.5, gt=0, le=5)
    max_specific_drop_pa_m: float = Field(default=200, gt=0, le=2000)
    head_margin_ratio: float = Field(default=.1, ge=0, le=.5)
    segments: list[DesignSegment] = Field(min_length=1, max_length=1200)
    pipe_sizes: list[PipeSize] = Field(min_length=1, max_length=100)
    pumps: list[PumpSpec] = Field(default_factory=list, max_length=200)
    valves: list[ValveSpec] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def validate_tree(self) -> Self:
        ids = {s.id for s in self.segments}
        if len(ids) != len(self.segments):
            raise ValueError('管段编号不能重复')
        roots = [s for s in self.segments if s.parent_id is None]
        if len(roots) != 1:
            raise ValueError('管路必须有且只有一条总管')
        children: dict[str, list[str]] = {s.id: [] for s in self.segments}
        for segment in self.segments:
            if segment.parent_id is not None:
                if segment.parent_id not in ids or segment.parent_id == segment.id:
                    raise ValueError('管段上级不存在或引用自身')
                children[segment.parent_id].append(segment.id)
        visited, pending = set(), [roots[0].id]
        while pending:
            node = pending.pop()
            if node in visited:
                raise ValueError('管路存在循环')
            visited.add(node)
            pending.extend(children[node])
        if visited != ids:
            raise ValueError('管路存在循环或未连接到总管')
        for segment in self.segments:
            if children[segment.id] and (segment.heat_load_w or segment.valve_pressure_drop_pa):
                raise ValueError('负荷和末端控制阀压降仅在末端管段填写')
        for entries in (self.pumps, self.valves):
            if len({item.id for item in entries}) != len(entries):
                raise ValueError('设备目录编号不能重复')
        if len({size.dn for size in self.pipe_sizes}) != len(self.pipe_sizes):
            raise ValueError('管径目录 DN 不能重复')
        sizes = {size.dn for size in self.pipe_sizes}
        if any(s.fixed_dn is not None and s.fixed_dn not in sizes for s in self.segments):
            raise ValueError('指定管径不在管径目录中')
        return self


class ValveSelection(AdapterModel):
    required_kv_m3_h: float
    selected: ValveSpec | None
    full_open_pressure_drop_pa: float | None


class SegmentResult(AdapterModel):
    id: str
    name: str
    parent_id: str | None
    heat_load_w: float
    flow_m3_h: float
    mass_flow_kg_s: float
    dn: int
    inner_diameter_m: float
    velocity_m_s: float
    specific_drop_pa_m: float
    pipe_pressure_drop_pa: float
    local_pressure_drop_pa: float
    equipment_pressure_drop_pa: float
    valve_pressure_drop_pa: float
    pressure_drop_pa: float
    path_pressure_drop_pa: float = 0
    balancing_pressure_drop_pa: float = 0
    status: Literal['ok', 'limit_exceeded', 'no_load']
    valve: ValveSelection | None


class PumpSelection(AdapterModel):
    pump: PumpSpec
    available_head_m: float
    excess_head_m: float
    efficiency: float
    input_power_kw: float


class HydronicDesignOutput(AdapterModel):
    feasible: bool
    total_load_w: float
    total_flow_m3_h: float
    density_kg_m3: float
    specific_heat_j_kg_k: float
    viscosity_pa_s: float
    circuit_pressure_drop_pa: float
    required_head_m: float
    critical_path: list[str]
    segments: list[SegmentResult]
    pump_candidates: list[PumpSelection]
    warnings: list[str]


def _interpolate(pump: PumpSpec, flow: float) -> tuple[float, float] | None:
    if not pump.min_flow_m3_h <= flow <= pump.max_flow_m3_h:
        return None
    for a, b in zip(pump.points, pump.points[1:]):
        if a.flow_m3_h <= flow <= b.flow_m3_h:
            t = (flow-a.flow_m3_h)/(b.flow_m3_h-a.flow_m3_h)
            return a.head_m+t*(b.head_m-a.head_m), a.efficiency+t*(b.efficiency-a.efficiency)
    return None


def design(p: HydronicDesignInput) -> HydronicDesignOutput:
    state = property_service(FluidConfig(fluid='Water', phase_policy='liquid')).state_pt(200000., p.temperature_k)
    rho, cp, mu = state.density_kg_m3, state.specific_heat_j_kg_k, state.viscosity_pa_s
    if cp is None or mu is None or cp <= 0 or mu <= 0:
        raise ValueError('当前水温没有可用的单相物性')
    nodes = {s.id: s for s in p.segments}
    children: dict[str, list[str]] = {key: [] for key in nodes}
    root = next(s.id for s in p.segments if s.parent_id is None)
    for segment in p.segments:
        if segment.parent_id is not None:
            children[segment.parent_id].append(segment.id)
    order, pending = [], [root]
    while pending:
        node = pending.pop()
        order.append(node)
        pending.extend(reversed(children[node]))
    loads: dict[str, float] = {}
    for key in reversed(order):
        loads[key] = sum(loads[c] for c in children[key]) if children[key] else nodes[key].heat_load_w
    sizes = sorted(p.pipe_sizes, key=lambda size: size.inner_diameter_m)
    results: dict[str, SegmentResult] = {}
    warnings: list[str] = []
    for key in order:
        segment = nodes[key]
        mass = loads[key]/(cp*p.temperature_difference_k)
        volume = mass/rho
        allowed = [s for s in sizes if s.dn == segment.fixed_dn] if segment.fixed_dn is not None else sizes
        for size in allowed:
            velocity = volume/(math.pi*size.inner_diameter_m**2/4)
            friction = pipe_pressure_drop_pa(mass_flow_kg_s=mass, density_kg_m3=rho, viscosity_pa_s=mu,
                length_m=1., diameter_m=size.inner_diameter_m, roughness_m=p.roughness_m)
            if velocity <= p.max_velocity_m_s and friction <= p.max_specific_drop_pa_m:
                break
        status: Literal['ok', 'limit_exceeded', 'no_load'] = 'ok'
        if not mass:
            status = 'no_load'
        elif velocity > p.max_velocity_m_s or friction > p.max_specific_drop_pa_m:
            status = 'limit_exceeded'
            warnings.append(f'{segment.name}：DN{size.dn} 超出流速或比摩阻限制，请调整管径目录或指定管径。')
        pipe_dp = friction*segment.length_m
        local_dp = resistance_pressure_drop_pa(mass_flow_kg_s=mass, density_kg_m3=rho,
            diameter_m=size.inner_diameter_m, loss_coefficient=segment.local_loss_coefficient)
        equipment_dp = segment.equipment_pressure_drop_pa if mass else 0.
        valve_dp = segment.valve_pressure_drop_pa if mass else 0.
        valve = None
        if valve_dp:
            required_kv = volume*3600*math.sqrt((rho/1000)/(valve_dp/1e5))
            candidates = sorted((v for v in p.valves if required_kv <= v.kvs_m3_h <= required_kv*2), key=lambda v: v.kvs_m3_h)
            selected = candidates[0] if candidates else None
            valve = ValveSelection(required_kv_m3_h=required_kv, selected=selected,
                full_open_pressure_drop_pa=1e5*(rho/1000)*(volume*3600/selected.kvs_m3_h)**2 if selected else None)
            if selected is None:
                warnings.append(f'{segment.name}：阀门目录没有 Kvs 在所需 Kv 的 1～2 倍内的型号。')
        result = SegmentResult(id=key, name=segment.name, parent_id=segment.parent_id, heat_load_w=loads[key],
            flow_m3_h=volume*3600, mass_flow_kg_s=mass, dn=size.dn, inner_diameter_m=size.inner_diameter_m,
            velocity_m_s=velocity, specific_drop_pa_m=friction, pipe_pressure_drop_pa=pipe_dp,
            local_pressure_drop_pa=local_dp, equipment_pressure_drop_pa=equipment_dp, valve_pressure_drop_pa=valve_dp,
            pressure_drop_pa=pipe_dp+local_dp+equipment_dp+valve_dp, status=status, valve=valve)
        result.path_pressure_drop_pa = result.pressure_drop_pa + (results[segment.parent_id].path_pressure_drop_pa if segment.parent_id else 0.)
        results[key] = result
    active = [s for s in results.values() if not children[s.id] and s.flow_m3_h > 0]
    worst = max(active, key=lambda s: s.path_pressure_drop_pa) if active else None
    circuit_dp = worst.path_pressure_drop_pa if worst else 0.
    for terminal in active:
        terminal.balancing_pressure_drop_pa = circuit_dp-terminal.path_pressure_drop_pa
    critical: list[str] = []
    cursor = worst.id if worst else None
    while cursor is not None:
        critical.append(cursor)
        cursor = nodes[cursor].parent_id
    critical.reverse()
    head = circuit_dp*(1+p.head_margin_ratio)/(rho*G)
    total_flow = results[root].flow_m3_h
    feasible = all(s.status != 'limit_exceeded' for s in results.values())
    pumps = []
    if total_flow and feasible:
        for pump in p.pumps:
            point = _interpolate(pump, total_flow)
            if point and point[0] >= head:
                available, efficiency = point
                pumps.append(PumpSelection(pump=pump, available_head_m=available, excess_head_m=available-head,
                    efficiency=efficiency, input_power_kw=rho*G*(total_flow/3600)*available/efficiency/1000))
        pumps.sort(key=lambda candidate: (candidate.excess_head_m, candidate.input_power_kw, candidate.pump.id))
        if not pumps:
            warnings.append('泵目录中没有同时满足设计流量范围与扬程的型号；未外推曲线。')
    if not total_flow:
        warnings.append('当前工况没有水侧负荷，无需选择循环泵。')
    return HydronicDesignOutput(feasible=feasible, total_load_w=loads[root], total_flow_m3_h=total_flow,
        density_kg_m3=rho, specific_heat_j_kg_k=cp, viscosity_pa_s=mu, circuit_pressure_drop_pa=circuit_dp,
        required_head_m=head, critical_path=critical, segments=list(results.values()), pump_candidates=pumps[:10], warnings=warnings)


def definition() -> AdapterDefinition:
    return AdapterDefinition('hydronics.design', '闭式树形水系统设计：负荷转水量、管径与环路阻力、泵阀目录校核；嵌套字段使用明示 SI 单位。',
        HydronicDesignInput, HydronicDesignOutput, design)
