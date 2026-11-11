"""Prescribed-flow, low-pressure air duct sizing on one supply or exhaust tree.

Lengths are one-way. All entered losses use total pressure, including terminals.
Rectangular turbulent friction uses hydraulic diameter; laminar friction uses the
rectangular Poiseuille polynomial, blended to the SDK Haaland model at Re=4000.
"""
import math
from typing import Literal, Self

from pydantic import Field, model_validator

from fn_sdk import pipe_pressure_drop_pa
from ..model_types.base import FluidConfig
from ..properties import property_service
from .contracts import AdapterModel
from .registry import AdapterDefinition


class DuctSize(AdapterModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    shape: Literal['round', 'rectangular']
    diameter_m: float | None = Field(default=None, ge=.05, le=4)
    width_m: float | None = Field(default=None, ge=.05, le=4)
    height_m: float | None = Field(default=None, ge=.05, le=4)

    @model_validator(mode='after')
    def shape_dimensions(self) -> Self:
        if self.shape == 'round':
            if self.diameter_m is None or self.width_m is not None or self.height_m is not None:
                raise ValueError('圆形风管只填写实际内径')
        elif self.width_m is None or self.height_m is None or self.diameter_m is not None:
            raise ValueError('矩形风管只填写实际内宽和内高')
        return self

    def geometry(self) -> tuple[float, float, float, float]:
        if self.diameter_m is not None:
            d = self.diameter_m
            return math.pi*d*d/4, d, d, 1.
        assert self.width_m is not None and self.height_m is not None
        a, b = self.width_m, self.height_m
        return a*b, 2*a*b/(a+b), b, max(a, b)/min(a, b)


class DuctSegment(AdapterModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    parent_id: str | None = None
    flow_m3_h: float = Field(default=0, ge=0, le=1e7, description='Only terminals prescribe actual-condition volume flow.')
    shape: Literal['round', 'rectangular'] = 'round'
    length_m: float = Field(default=10, ge=0, le=10000)
    local_loss_coefficient: float = Field(default=2, ge=0, le=1000)
    equipment_pressure_drop_pa: float = Field(default=0, ge=0, le=100000,
        description='Total-pressure loss at design flow; include filters, coils and terminal/outlet losses.')
    fixed_size_id: str | None = None


def _tree(segments: list[DuctSegment]) -> tuple[dict[str, list[str]], list[str]]:
    nodes = {s.id: s for s in segments}
    if len(nodes) != len(segments):
        raise ValueError('风管编号不能重复')
    roots = [s.id for s in segments if s.parent_id is None]
    if len(roots) != 1:
        raise ValueError('风管应有且只有一个总管根节点')
    children: dict[str, list[str]] = {key: [] for key in nodes}
    for s in segments:
        if s.parent_id is not None:
            if s.parent_id not in nodes or s.parent_id == s.id:
                raise ValueError('风管上级不存在或引用自身')
            children[s.parent_id].append(s.id)
    visited: set[str] = set()
    order, pending = [], [roots[0]]
    while pending:
        key = pending.pop()
        if key in visited:
            raise ValueError('风管树存在循环')
        visited.add(key)
        order.append(key)
        pending.extend(reversed(children[key]))
    if len(visited) != len(nodes):
        raise ValueError('风管存在未连接到总管的节点或循环')
    if any(s.flow_m3_h and children[s.id] for s in segments):
        raise ValueError('仅末端可填写风量；内部管段汇总下游风量')
    return children, order


class DuctDesignInput(AdapterModel):
    temperature_k: float = Field(default=293.15, ge=253.15, le=333.15)
    pressure_pa: float = Field(default=101325, ge=60000, le=120000)
    roughness_m: float = Field(default=.00015, ge=0, le=.005)
    max_velocity_m_s: float = Field(default=5, ge=.1, le=20)
    max_specific_drop_pa_m: float = Field(default=1, ge=.01, le=20)
    max_aspect_ratio: float = Field(default=4, ge=1, le=4)
    max_height_m: float | None = Field(default=None, ge=.05, le=4)
    pressure_margin_ratio: float = Field(default=.1, ge=0, le=.5)
    fan_efficiency: float = Field(default=.6, ge=.05, le=1, description='Overall wire-to-air efficiency, for power estimate only.')
    segments: list[DuctSegment] = Field(min_length=1, max_length=1200)
    duct_sizes: list[DuctSize] = Field(min_length=1, max_length=200)

    @model_validator(mode='after')
    def valid_design(self) -> Self:
        _tree(self.segments)
        sizes = {s.id: s for s in self.duct_sizes}
        if len(sizes) != len(self.duct_sizes):
            raise ValueError('风管规格编号不能重复')
        for segment in self.segments:
            if segment.fixed_size_id is not None:
                size = sizes.get(segment.fixed_size_id)
                if size is None or size.shape != segment.shape:
                    raise ValueError(f'{segment.name}：指定规格不存在或与风管形状不同')
            elif not any(s.shape == segment.shape and self.fits_geometry(s) for s in self.duct_sizes):
                raise ValueError(f'{segment.name}：目录没有符合形状、限高和宽高比的规格')
        return self

    def fits_geometry(self, size: DuctSize) -> bool:
        _, _, height, ratio = size.geometry()
        return ratio <= self.max_aspect_ratio and (self.max_height_m is None or height <= self.max_height_m)


class DuctSegmentResult(AdapterModel):
    id: str
    name: str
    parent_id: str | None
    flow_m3_h: float
    size: DuctSize
    selection: Literal['automatic', 'fixed']
    area_m2: float
    hydraulic_diameter_m: float
    velocity_m_s: float
    reynolds: float
    specific_drop_pa_m: float
    friction_pressure_drop_pa: float
    local_pressure_drop_pa: float
    equipment_pressure_drop_pa: float
    pressure_drop_pa: float
    path_pressure_drop_pa: float
    balancing_pressure_drop_pa: float = 0
    status: Literal['ok', 'limit_exceeded', 'no_flow']


class DuctDesignOutput(AdapterModel):
    feasible: bool
    total_flow_m3_h: float
    density_kg_m3: float
    viscosity_pa_s: float
    system_pressure_drop_pa: float
    required_fan_total_pressure_pa: float
    estimated_input_power_kw: float | None
    critical_path: list[str]
    segments: list[DuctSegmentResult]
    warnings: list[str]


def _flow_terms(size: DuctSize, flow: float, rho: float, mu: float, roughness: float) -> tuple[float, float, float]:
    area, diameter, _, aspect = size.geometry()
    velocity = flow/3600/area
    reynolds = rho*velocity*diameter/mu
    # The SDK round-pipe calculation receives the mass flow giving the SAME velocity at Dh.
    equivalent_mass = rho*velocity*math.pi*diameter**2/4
    friction = pipe_pressure_drop_pa(mass_flow_kg_s=equivalent_mass, density_kg_m3=rho,
        viscosity_pa_s=mu, length_m=1., diameter_m=diameter, roughness_m=roughness)
    if size.shape == 'rectangular' and 0 < reynolds < 4000:
        alpha = 1/aspect
        poiseuille = 96*(1-1.3553*alpha+1.9467*alpha**2-1.7012*alpha**3+.9564*alpha**4-.2537*alpha**5)
        laminar_weight = 1-min(1., max(0., (reynolds-2300)/1700))
        friction += laminar_weight*(poiseuille-64)*mu*velocity/(2*diameter**2)
    return velocity, reynolds, friction


def design(p: DuctDesignInput) -> DuctDesignOutput:
    state = property_service(FluidConfig(fluid='Air', phase_policy='gas')).state_pt(p.pressure_pa, p.temperature_k)
    rho, mu = state.density_kg_m3, state.viscosity_pa_s
    if mu is None or mu <= 0 or rho <= 0:
        raise ValueError('当前工况没有可用的空气物性')
    nodes = {s.id: s for s in p.segments}
    children, order = _tree(p.segments)
    flows: dict[str, float] = {}
    for key in reversed(order):
        flows[key] = sum(flows[c] for c in children[key]) if children[key] else nodes[key].flow_m3_h
    sizes = sorted(p.duct_sizes, key=lambda s: (s.geometry()[0], s.geometry()[3], s.id))
    results: dict[str, DuctSegmentResult] = {}
    warnings = []
    for key in order:
        segment, flow = nodes[key], flows[key]
        allowed = ([s for s in sizes if s.id == segment.fixed_size_id] if segment.fixed_size_id is not None
                   else [s for s in sizes if s.shape == segment.shape and p.fits_geometry(s)])
        size = allowed[-1]
        for size in allowed:
            velocity, reynolds, friction = _flow_terms(size, flow, rho, mu, p.roughness_m)
            if velocity <= p.max_velocity_m_s and friction <= p.max_specific_drop_pa_m:
                break
        fits = p.fits_geometry(size) and velocity <= p.max_velocity_m_s and friction <= p.max_specific_drop_pa_m
        status: Literal['ok', 'limit_exceeded', 'no_flow'] = ('ok' if flow else 'no_flow') if fits else 'limit_exceeded'
        if not fits:
            warnings.append(f'{segment.name}：{size.name} 超出流速、比摩阻或安装尺寸限制，请调整规格。')
        friction_dp = friction*segment.length_m
        local_dp = segment.local_loss_coefficient*rho*velocity**2/2
        equipment_dp = segment.equipment_pressure_drop_pa if flow else 0.
        drop = friction_dp+local_dp+equipment_dp
        results[key] = DuctSegmentResult(id=key, name=segment.name, parent_id=segment.parent_id,
            flow_m3_h=flow, size=size, selection='fixed' if segment.fixed_size_id is not None else 'automatic',
            area_m2=size.geometry()[0], hydraulic_diameter_m=size.geometry()[1], velocity_m_s=velocity,
            reynolds=reynolds, specific_drop_pa_m=friction, friction_pressure_drop_pa=friction_dp,
            local_pressure_drop_pa=local_dp, equipment_pressure_drop_pa=equipment_dp, pressure_drop_pa=drop,
            path_pressure_drop_pa=drop+(results[segment.parent_id].path_pressure_drop_pa if segment.parent_id is not None else 0.),
            status=status)
    active = [s for s in results.values() if not children[s.id] and s.flow_m3_h > 0]
    worst = max(active, key=lambda s: s.path_pressure_drop_pa) if active else None
    system_dp = worst.path_pressure_drop_pa if worst else 0.
    critical: list[str] = []
    cursor = worst.id if worst else None
    while cursor is not None:
        critical.append(cursor)
        cursor = nodes[cursor].parent_id
    critical.reverse()
    for terminal in active:
        terminal.balancing_pressure_drop_pa = system_dp-terminal.path_pressure_drop_pa
    fan_dp = system_dp*(1+p.pressure_margin_ratio)
    feasible = all(s.status != 'limit_exceeded' for s in results.values())
    if fan_dp > .05*p.pressure_pa:
        feasible = False
        warnings.append('所需压升超过绝对压力的 5%，超出本低压定密度模型范围。')
    total = flows[order[0]]
    if not total:
        warnings.append('当前没有新风需求，风量、阻力和功率均为零。')
    return DuctDesignOutput(feasible=feasible, total_flow_m3_h=total, density_kg_m3=rho, viscosity_pa_s=mu,
        system_pressure_drop_pa=system_dp, required_fan_total_pressure_pa=fan_dp,
        estimated_input_power_kw=total/3600*fan_dp/p.fan_efficiency/1000 if feasible else None,
        critical_path=critical, segments=list(results.values()), warnings=warnings)


def definition() -> AdapterDefinition:
    return AdapterDefinition('airflow.duct_design',
        '单路送风或排风树的低压设计：圆形/矩形选径、总压损失、最不利路径与风机全压及功率估算；非实际流量分配求解。',
        DuctDesignInput, DuctDesignOutput, design)
