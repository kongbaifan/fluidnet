"""Implicit coupling of a lumped refrigerant station and an algebraic liquid network.

The coil stores no mass or heat. Its current liquid-side enthalpy loss enters the
saturated vessel in the same nonlinear state evaluation, with the opposite sign.
"""
from dataclasses import dataclass, field
import math

import numpy as np
from scipy.optimize import least_squares

from ..compiler import CompilationError, circuit_info, compile_project, validate_controllers, validated_parameters
from ..control import validate_scripts
from ..models import Diagnostic, Domain
from ..properties import PropertyError
from ..solver import solve_network, snapshot as fluid_snapshot
from ..thermal import GRAVITY, phase_family
from . import devices
from .schedule import check_set_variable, check_unique
from .station import CompiledStation, StationSession, compile_station, station_circuits


@dataclass
class CompiledCoupled(CompiledStation):
    fluid_network: object = None
    couplings: list = field(default_factory=list)
    coil_indices: dict = field(default_factory=dict)
    execution_domain: str = 'coupled'


def compile_coupled_project(project):
    definitions = {module.id:module for module in project.modules}
    for instance in project.instances:
        if definitions[instance.module_id].execution_role:
            raise CompilationError('MODULE_EXECUTION_DOMAIN_UNSUPPORTED',
                '热耦合项目尚不支持制冷作者模块',instance.id,'execution_role')
    if not project.solver.thermal:
        raise CompilationError('COUPLED_THERMAL_REQUIRED', '热耦合需要启用热力计算')
    links = project.thermal_couplings
    # Recheck at compilation as Python callers can mutate a validated Project.
    # Never allow a duplicate to overwrite the per-channel or per-ID heat map.
    if len(links) > 2:
        raise CompilationError('COUPLED_LIMIT', '当前最多支持两条热耦合关系', field='thermal_couplings')
    if len({link.id for link in links}) != len(links):
        raise CompilationError('COUPLED_ID_DUPLICATE', '热耦合关系 ID 必须唯一', field='thermal_couplings')
    if len({(link.fluid_instance_id, link.fluid_channel_id) for link in links}) != len(links):
        raise CompilationError('COUPLED_CHANNEL_DUPLICATE', '同一液体通路只能绑定一条热耦合关系', field='thermal_couplings')
    if len({link.refrigerant_vessel_id for link in links}) > 1:
        raise CompilationError('COUPLED_VESSEL_SCOPE', '当前双盘管须关联同一个饱和制冷剂容器', field='thermal_couplings')
    modules = {module.id: module for module in project.modules}
    liquid_ids, station_ids = set(), set()
    for instance in project.instances:
        if instance.id == 'coupling':
            raise CompilationError('COUPLED_RESERVED_ID', '热耦合项目的设备 ID 不能为保留变量前缀 coupling', instance.id)
        definition = modules[instance.module_id]
        domains = {port.domain for port in definition.ports}
        if domains and domains <= {Domain.fluid}:
            liquid_ids.add(instance.id)
            parameters = validated_parameters(instance, definition)
            if definition.runtime != 'builtin' or definition.state_model or parameters.get('thermal_cells', 0) != 0:
                raise CompilationError('COUPLED_FLUID_STATE_UNSUPPORTED',
                    '当前联算的单相侧只支持无储热内置网络；不含水箱、管壁/流体储热及 Python 设备模块', instance.id)
        elif domains and domains <= {Domain.refrigerant, Domain.thermal}:
            station_ids.add(instance.id)
        else:
            raise CompilationError('COUPLED_MODULE_DOMAIN', '耦合两侧设备须分别属于单相流体网络或集总制冷站', instance.id)
    if not liquid_ids or not station_ids:
        raise CompilationError('COUPLED_DOMAIN_MISSING', '热耦合必须同时包含单相流体网络和制冷站')
    for entry in project.circuit_fluids:
        if entry.anchor.instance_id not in liquid_ids | station_ids:
            raise CompilationError('CIRCUIT_ANCHOR_UNKNOWN', f'回路工质 {entry.id} 的锚点设备不存在',
                                   field='circuit_fluids')
    for edge in project.connections:
        if (edge.source.instance_id in liquid_ids) != (edge.target.instance_id in liquid_ids):
            raise CompilationError('COUPLED_CONNECTION_INVALID', '不同物理域通过 thermal_couplings 交换热量，不能直接连接流体端口',
                                   edge.source.instance_id)

    def subset(ids):
        used = {instance.module_id for instance in project.instances if instance.id in ids}
        return project.model_copy(deep=True, update={
            'instances': [instance.model_copy(deep=True) for instance in project.instances if instance.id in ids],
            'modules': [module.model_copy(deep=True) for module in project.modules if module.id in used],
            'connections': [edge.model_copy(deep=True) for edge in project.connections if edge.source.instance_id in ids],
            'circuit_fluids': [entry.model_copy(deep=True) for entry in project.circuit_fluids if entry.anchor.instance_id in ids],
            'thermal_couplings': [], 'controllers': [], 'control_scripts': [], 'events': [], 'scenarios': [],
        })

    liquid = compile_project(subset(liquid_ids))
    if liquid.storage or liquid.trapped:
        raise CompilationError('COUPLED_FLUID_STATE_UNSUPPORTED', '当前联算的单相侧不包含储量状态')
    # The inner algebraic solution participates in finite-difference derivatives of
    # the station state. Resolve its temperature accurately enough for those probes.
    liquid.project.solver.thermal_tolerance_k = min(liquid.project.solver.thermal_tolerance_k, 1e-8)
    station = compile_station(subset(station_ids))
    coil_indices = {}
    for coupling in project.thermal_couplings:
        if coupling.fluid_instance_id not in liquid_ids:
            raise CompilationError('COUPLED_TARGET_INVALID',
                f'热耦合 {coupling.id} 的液体侧设备 {coupling.fluid_instance_id} 必须属于单相流体网络',
                coupling.fluid_instance_id, 'fluid_instance_id')
        if station.kinds.get(coupling.refrigerant_vessel_id) != 'saturated_vessel':
            raise CompilationError('COUPLED_TARGET_INVALID',
                f'热耦合 {coupling.id} 的制冷剂侧设备 {coupling.refrigerant_vessel_id} 必须是饱和容器',
                coupling.refrigerant_vessel_id, 'refrigerant_vessel_id')
        indices = [i for i, branch in enumerate(liquid.branches)
                   if (branch.instance_id, branch.channel_id) == (coupling.fluid_instance_id, coupling.fluid_channel_id)]
        definition = liquid.modules[liquid.instances[coupling.fluid_instance_id].module_id]
        parameters = liquid.parameters[coupling.fluid_instance_id]
        if definition.solver_model != 'pipe' or len(definition.channels) != 1:
            raise CompilationError('COUPLED_COIL_INVALID',
                f'热耦合 {coupling.id} 的液体侧设备 {coupling.fluid_instance_id} 须为只有一条通路的内置圆管',
                coupling.fluid_instance_id, 'fluid_instance_id')
        if len(indices) != 1:
            raise CompilationError('COUPLED_COIL_INVALID',
                f'热耦合 {coupling.id} 的 {coupling.fluid_instance_id}.{coupling.fluid_channel_id} 须为内置圆管的唯一通路',
                coupling.fluid_instance_id, 'fluid_channel_id')
        if parameters.get('heat_loss_ua_w_k', 0) != 0 or parameters.get('thermal_cells', 0) != 0:
            raise CompilationError('COUPLED_COIL_HEAT_CONFLICT', '盘管原有环境散热 UA 和热容分段数须为零，换热由耦合合同定义',
                                   coupling.fluid_instance_id)
        coil_indices[coupling.id] = indices[0]
    values = vars(station).copy()
    values.update(project=project.model_copy(deep=True), modules=modules,
                  instances={instance.id: instance for instance in project.instances},
                  parameters=station.parameters | liquid.parameters, branches=liquid.branches,
                  execution_domain='coupled', fluid_network=liquid,
                  couplings=list(project.thermal_couplings), coil_indices=coil_indices,
                  events=sorted(project.events, key=lambda event: event.time_s))
    network = CompiledCoupled(**values)
    validate_controllers(project, network.modules, network.instances)
    validate_scripts(project, network.modules, network.instances)
    check_unique(project.events)
    for event in project.events:
        if event.type != 'set_variable':
            raise CompilationError('SCHEDULE_UNSUPPORTED', '当前联算日程只支持 set_variable', field='events')
        check_set_variable(project, network.modules, network.instances, event)
    network.diagnostics += liquid.diagnostics
    return network


def coupled_circuits(network):
    result = station_circuits(network)
    offset = len(result)
    return result + [item | {'id': item['id'] + offset} for item in circuit_info(network.fluid_network)]


class CoupledStationSession(StationSession):
    _segment_fields: tuple[str, ...] = StationSession._segment_fields + ('_fluid_warm',)

    def _init_state(self):
        super()._init_state()
        self._fluid_warm = None

    def _evaluate(self, masses, energies, temperatures):
        result = super()._evaluate(masses, energies, temperatures)
        liquid = self.network.fluid_network
        liquid.parameters = {iid: self.network.parameters[iid] for iid in liquid.instances}
        liquid.saturated_coils = {
            (link.fluid_instance_id, link.fluid_channel_id):
                (link.ua_w_k, result['vessels'][link.refrigerant_vessel_id].temperature_k)
            for link in self.network.couplings}
        try:
            water = solve_network(liquid, runners={}, time_s=self.time, warm=self._fluid_warm)
        except (CompilationError, ValueError) as error:
            raise devices.DeviceRangeError('COUPLED_FLUID_FAILED', f'单相侧试算失败：{error}') from error
        if water.thermal is None or any(phase_family(state) != 'liquid' for state in water.thermal.node_states):
            raise devices.DeviceRangeError('COUPLED_LIQUID_REQUIRED', '当前浸没盘管联算仅支持液态水或液态单相载冷剂')
        self._fluid_warm = water
        result['fluid_result'] = water
        result['couplings'] = {}
        for link in self.network.couplings:
            index = self.network.coil_indices[link.id]
            thermal = water.thermal
            flow = float(water.hydraulic.flows[index])
            up = thermal.node_states[thermal.upstream[index]]
            outlet = thermal.outlet_states[index]
            refrigerant_t = result['vessels'][link.refrigerant_vessel_id].temperature_k
            capacity = abs(flow) * up.specific_heat_j_kg_k
            flowing = abs(flow) > max(liquid.project.solver.mass_tolerance_kg_s, 1e-12)
            effectiveness = -math.expm1(-link.ua_w_k / capacity) if flowing else 0.
            # Branch enthalpy also includes elevation work. Only heat crosses
            # the coil wall; reversing the flow reverses this potential term.
            height = liquid.parameters[link.fluid_instance_id].get('height_m', 0.)
            heat = -float(thermal.heat_w[index]) - GRAVITY * height * flow
            predicted = effectiveness * capacity * (up.temperature_k - refrigerant_t) if flowing else 0.
            values = {'heat_w': heat, 'fluid_heat_w': -heat, 'refrigerant_heat_w': heat,
                      'energy_residual_w': 0., 'mass_flow_kg_s': flow, 'effectiveness': effectiveness,
                      'refrigerant_temperature_k': refrigerant_t,
                      'fluid_inlet_temperature_k': up.temperature_k, 'fluid_outlet_temperature_k': outlet.temperature_k,
                      'inlet_temperature_k': up.temperature_k, 'outlet_temperature_k': outlet.temperature_k,
                      'equation_residual_w': heat - predicted}
            result['couplings'][link.id] = values
            result['du'][link.refrigerant_vessel_id] += heat
            # No state resides in the liquid loop; its net external heat enters the
            # refrigerant inventory through this same, accepted algebraic solution.
            result['boundary_w'] += heat
        return result

    def _powers(self, result):
        powers = super()._powers(result)
        for identifier, coupling in result['couplings'].items():
            powers[(f'coupling.{identifier}', 'transfer_energy_j')] = coupling['heat_w']
        return powers

    def snapshot(self):
        frame = super().snapshot()
        result = self._current()
        liquid = self.network.fluid_network
        # A rejected controlled segment restores the station's parameters and
        # cached accepted solution. Keep the nested network's parameter exports
        # on that same accepted revision even when _current reuses the cache.
        liquid.parameters = {iid: self.network.parameters[iid] for iid in liquid.instances}
        water = fluid_snapshot(liquid, result['fluid_result'], self.time)
        frame.variables.update(water.variables)
        for identifier, values in result['couplings'].items():
            frame.variables.update({f'coupling.{identifier}.{key}': value for key, value in values.items()})
            energy = self.counters.get((f'coupling.{identifier}', 'transfer_energy_j'), 0.)
            frame.variables[f'coupling.{identifier}.state.heat_energy_j'] = energy
        frame.metrics.update({key: water.metrics[key] for key in ('pressure_residual_pa', 'mass_residual_kg_s')})
        frame.metrics.update(fluid_energy_residual_w=water.metrics['energy_residual_w'],
                             reference_heat_w=water.metrics['reference_heat_w'], coupling_energy_residual_w=0.)
        totals = {
            'coupling_heat_w': sum(values['heat_w'] for values in result['couplings'].values()),
            'coupling_heat_energy_j': sum(self.counters.get((f'coupling.{identifier}', 'transfer_energy_j'), 0.)
                                          for identifier in result['couplings']),
        }
        frame.metrics.update(totals)
        frame.variables.update({f'metrics.{key}': value for key, value in totals.items()})
        frame.diagnostics.extend(water.diagnostics)
        frame.diagnostics.append(Diagnostic(code='COUPLED_SCOPE', severity='info',
            message='浸没盘管：制冷剂容器状态与无储热单相液体网络联合求解；水侧仅内置设备，盘管无持液/管壁储热'))
        return frame


def _saturation_interval(service, initial):
    limits = service.limits()
    def valid(temperature):
        try:
            service.state_tq(temperature, 0.)
            service.state_tq(temperature, 1.)
            return True
        except PropertyError:
            return False
    endpoints = []
    for candidate in (max(float(limits['t_min_k']) + 1e-4, initial - 150.),
                      min(float(limits['t_max_k']) - 1e-4, initial + 200.)):
        if valid(candidate):
            endpoints.append(candidate)
            continue
        good, bad = initial, candidate
        for _ in range(36):
            middle = .5 * (good + bad)
            if valid(middle):
                good = middle
            else:
                bad = middle
        endpoints.append(good + (.01 if good < initial else -.01))
    return tuple(endpoints)


def solve_coupled_steady(network):
    """A true equilibrium: all inventory rates vanish and every circuit keeps its initial mass."""
    if network.project.events or any(script.enabled for script in network.project.control_scripts) or network.project.controllers:
        raise CompilationError('COUPLED_STEADY_CONTROL_UNSUPPORTED', '联算稳态平衡不执行控制器、脚本或日程，请停用后求解或改用动态运行')
    if any(kind == 'cold_room' for kind in network.kinds.values()):
        raise CompilationError('COUPLED_STEADY_ROOM_UNSUPPORTED', '首版联算稳态限无库房储热的制冷站与无储热液体回路')
    session = CoupledStationSession(network, 1., 1.)
    try:
        vessels = network.vessels
        y0, lower, upper = [], [], []
        for vessel in vessels:
            parameters = network.parameters[vessel]
            lo, hi = _saturation_interval(session.services[vessel], parameters['temperature_k'])
            y0 += [parameters['temperature_k'], parameters['level_ratio']]
            lower += [lo, max(parameters['min_level_ratio'], 1e-6)]
            upper += [hi, min(parameters['max_level_ratio'], 1 - 1e-6)]
        last_vessel = {c: next(v for v in reversed(vessels) if network.circuit_of[v] == c)
                       for c in range(len(network.circuit_fluids))}

        def state(values):
            masses, energies = {}, {}
            for i, vessel in enumerate(vessels):
                parameters = network.parameters[vessel] | {'temperature_k': float(values[2*i]), 'level_ratio': float(values[2*i+1])}
                masses[vessel], energies[vessel] = devices.vessel_initial(session.services[vessel], parameters)
            return masses, energies

        def residual(values):
            try:
                masses, energies = state(values)
                result = session._evaluate(masses, energies, {})
                rows = []
                for vessel in vessels:
                    circuit = network.circuit_of[vessel]
                    mass = ((sum(masses[v] for v in vessels if network.circuit_of[v] == circuit) - session.circuit_mass[circuit])
                            / max(session.circuit_mass[circuit], 1.)) if vessel == last_vessel[circuit] else result['dm'][vessel] / .1
                    rows += [mass, result['du'][vessel] / 10000.]
                return np.asarray(rows)
            except (devices.DeviceRangeError, CompilationError, PropertyError, ValueError):
                # Invalid trial states are never accepted as a physical solution;
                # the final result below is recomputed and checked without a penalty.
                return np.full(len(y0), 1e6) + (np.asarray(values) - y0) / np.tile([100., 1.], len(vessels))

        solved = least_squares(residual, y0, bounds=(lower, upper), x_scale=np.tile([100., 1.], len(vessels)),
                               ftol=1e-12, xtol=1e-12, gtol=1e-12, max_nfev=200, diff_step=1e-5)
        session.masses, session.energies = state(solved.x)
        session._cache = None
        result = session._current()
        mass_rate = max(map(abs, result['dm'].values()), default=0.)
        energy_rate = max(map(abs, result['du'].values()), default=0.)
        inventory_error = max((abs(sum(session.masses[v] for v in vessels if network.circuit_of[v] == c) - total)
                               / max(total, 1.) for c, total in enumerate(session.circuit_mass)), default=0.)
        if not solved.success or mass_rate > 1e-8 or energy_rate > .01 or inventory_error > 1e-8:
            raise CompilationError('COUPLED_STEADY_NOT_CONVERGED',
                f'联算稳态平衡未通过：质量变化率 {mass_rate:g} kg/s，能量变化率 {energy_rate:g} W，'
                f'回路总质量相对偏差 {inventory_error:g}')
        session._check_vessels(result)
        frame = session.snapshot()
        frame.metrics.update(steady_mass_residual_kg_s=mass_rate, steady_energy_residual_w=energy_rate,
                             steady_inventory_relative_error=inventory_error, steady_iterations=int(solved.nfev))
        frame.diagnostics.append(Diagnostic(code='COUPLED_STEADY_EQUILIBRIUM', severity='info',
            message='保持每个制冷剂回路初始总质量，联立求解容器质量/能量变化率为零的平衡状态'))
        return frame
    finally:
        session.close()
