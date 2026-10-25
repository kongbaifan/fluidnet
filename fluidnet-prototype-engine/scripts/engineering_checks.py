"""Independent equations, accepted-substep ledgers and A/B result comparisons."""
from __future__ import annotations

from collections import Counter
import math


class Checks:
    def __init__(self):
        self.counts = Counter()
        self.failures = []
        self.maxima = {}

    def require(self, name, passed, **details):
        self.counts[name] += 1
        if not passed and len(self.failures) < 30:
            self.failures.append({'check': name, **details})

    def near(self, name, actual, expected, *, atol, rtol=1e-6, **details):
        error = abs(actual - expected)
        limit = atol + rtol * abs(expected)
        self.maxima[name] = max(self.maxima.get(name, 0.), error)
        self.require(name, math.isfinite(error) and error <= limit,
                     actual=actual, expected=expected, error=error, limit=limit, **details)

    def report(self):
        return {'passed': not self.failures, 'counts': dict(self.counts), 'max_absolute_errors': self.maxima,
                'failures': self.failures}


def comparison_tolerance(key):
    if key.endswith(('commit_count', 'state_revision', 'sequence')):
        return 0., 0.
    if key.endswith('pressure_pa') or key.endswith('pressure_drop_pa'):
        return 1., 1e-6
    if key.endswith('mass_flow_kg_s') or key.endswith('net_inflow_kg_s'):
        return 1e-8, 1e-6
    if key.endswith('temperature_k'):
        return 1e-4, 1e-6
    if key.endswith('_j'):
        return 1e-3, 1e-6
    return 1e-7, 1e-6


def compare_frames(reference, candidate):
    checks = Checks()
    checks.require('frame_count', len(reference) == len(candidate), expected=len(reference), actual=len(candidate))
    for index, (before, after) in enumerate(zip(reference, candidate)):
        for key in ('time_s', 'sequence', 'parameter_revision', 'valid', 'status'):
            checks.require('frame_metadata', before.get(key) == after.get(key), frame=index, key=key,
                           expected=before.get(key), actual=after.get(key))
        left, right = before['variables'], after['variables']
        checks.require('variable_keys', left.keys() == right.keys(), frame=index,
                       missing=sorted(left.keys() - right.keys()), extra=sorted(right.keys() - left.keys()))
        for key in left.keys() & right.keys():
            a, b = left[key], right[key]
            if isinstance(a, (float, int)) and not isinstance(a, bool):
                if not isinstance(b, (float, int)) or isinstance(b, bool):
                    checks.require('variable_type', False, frame=index, key=key)
                    continue
                atol, rtol = comparison_tolerance(key)
                checks.near('variable_values', b, a, atol=atol, rtol=rtol, frame=index, key=key)
            else:
                checks.require('variable_values', a == b, frame=index, key=key, expected=a, actual=b)
    return checks.report()


def effectiveness(ua, first, second, counterflow=True):
    """Independent textbook epsilon-NTU equation; does not call the module SDK."""
    minimum, maximum = min(first, second), max(first, second)
    if minimum <= 0 or maximum <= 0 or ua <= 0:
        return 0.
    ratio, ntu = minimum / maximum, ua / minimum
    if not counterflow:
        return -math.expm1(-ntu * (1 + ratio)) / (1 + ratio)
    if abs(1 - ratio) < 1e-10:
        return ntu / (1 + ntu)
    factor = math.exp(-ntu * (1 - ratio))
    return (1 - factor) / (1 - ratio * factor)


def check_frame(case, network, frame, checks):
    values, metrics = frame.variables, frame.metrics
    domain = getattr(network, 'execution_domain', 'fluid')
    checks.require('valid_frame', frame.valid and not any(d.severity == 'error' for d in frame.diagnostics), time_s=frame.time_s)
    checks.require('finite_variables', all(not isinstance(v, (float, int)) or math.isfinite(v) for v in values.values()),
                   time_s=frame.time_s)
    if domain != 'fluid':
        return
    for key, tolerance in [('pressure_residual_pa', case.project.solver.pressure_tolerance_pa),
                           ('mass_residual_kg_s', case.project.solver.mass_tolerance_kg_s)]:
        value = metrics.get(key)
        checks.require(key, value is not None and math.isfinite(value) and abs(value) <= tolerance,
                       time_s=frame.time_s, actual=value, limit=tolerance)
    balance = [0.] * len(network.node_keys)
    for branch in network.branches:
        flow = values[f'{branch.instance_id}.{branch.channel_id}.mass_flow_kg_s']
        balance[branch.start_node] -= flow
        balance[branch.end_node] += flow
    for node, value in enumerate(balance):
        if node not in network.fixed_pressures and node not in network.storage:
            checks.near('node_mass_balance', value, 0., atol=case.project.solver.mass_tolerance_kg_s,
                        node=node, time_s=frame.time_s)
    if case.project.solver.thermal:
        # An independent, stricter 0.01 W acceptance threshold for these reference cases.
        residual = metrics.get('energy_residual_w')
        checks.require('energy_residual_w', residual is not None and math.isfinite(residual) and abs(residual) <= .01,
                       time_s=frame.time_s, actual=residual, limit=.01)
    if 'pump_branch_mass' in case.checks:
        total = sum(values[f'{i.id}.main.mass_flow_kg_s'] for i in case.project.instances if i.id.startswith('D'))
        checks.near('pump_branch_mass', values['P1.mass_flow_kg_s'], total, atol=1e-8)
    if 'independent_valve_kv' in case.checks:
        for instance in case.project.instances:
            if not instance.id.startswith('D'):
                continue
            prefix, params = instance.id, network.parameters[instance.id]
            delta = values[f'{prefix}.in0.pressure_pa'] - values[f'{prefix}.out0.pressure_pa']
            rho = values[f'{prefix}.density_kg_m3']
            expected = rho / 3600 * params['kv_m3_h'] * params['opening_ratio'] * math.copysign(
                math.sqrt(abs(delta) / (1e5 * rho / 1000)), delta)
            checks.near('independent_valve_kv', values[f'{prefix}.main.mass_flow_kg_s'], expected,
                        atol=1e-8, instance=prefix)
    if 'independent_coil_ntu' in case.checks:
        from fn_engine.compiler import service_at
        for instance in case.project.instances:
            if not instance.id.startswith('D'):
                continue
            prefix, params = instance.id, network.parameters[instance.id]
            q = values[f'{prefix}.main.mass_flow_kg_s']
            port = 'in0' if q >= 0 else 'out0'
            state = service_at(network, network.port_nodes[f'{prefix}:{port}']).state_ph(
                values[f'{prefix}.{port}.pressure_pa'], values[f'{prefix}.{port}.enthalpy_j_kg'])
            water_capacity = abs(q) * state.specific_heat_j_kg_k
            air_capacity = params['air_flow_m3_s'] * params['air_density_kg_m3'] * params['air_cp_j_kg_k']
            expected = effectiveness(params['ua_w_k'], water_capacity, air_capacity) * min(water_capacity, air_capacity) * (
                params['air_inlet_temperature_k'] - state.temperature_k)
            checks.near('independent_coil_ntu', values[f'{prefix}.main.heat_w'], expected,
                        atol=1e-4, instance=prefix, time_s=frame.time_s)
    if 'independent_exchanger_ntu' in case.checks:
        from fn_engine.compiler import service_at
        capacities, temperatures, flows = [], [], []
        for side in ('hot', 'cold'):
            flow = values[f'HX.{side}.mass_flow_kg_s']
            port = f'{side}_in' if flow >= 0 else f'{side}_out'
            state = service_at(network, network.port_nodes[f'HX:{port}']).state_ph(
                values[f'HX.{port}.pressure_pa'], values[f'HX.{port}.enthalpy_j_kg'])
            capacities.append(abs(flow) * state.specific_heat_j_kg_k)
            temperatures.append(state.temperature_k)
            flows.append(flow)
        params = network.parameters['HX']
        expected = effectiveness(params['ua_w_k'], *capacities, counterflow=(flows[0] >= 0) == (flows[1] >= 0)) * min(capacities) * (
            temperatures[0] - temperatures[1])
        checks.near('independent_exchanger_ntu', values['HX.cold.heat_w'], expected, atol=1e-4, time_s=frame.time_s)
        checks.near('exchanger_energy_balance', values['HX.hot.heat_w'] + values['HX.cold.heat_w'], 0., atol=1e-6)
    if 'two_fluids' in case.checks:
        checks.require('two_fluids', network.mixed and len({f.fluid for f in network.circuit_fluids}) == 2)
    if 'pid_response' in case.checks:
        checks.require('pid_output_bounds', 0 <= values['controller.level.output'] <= 1., time_s=frame.time_s)


class AcceptedLedger:
    """Observe committed substeps; output-frame quadrature can miss internal steps."""
    def __init__(self, checks):
        self.checks = checks
        self.steps = 0
        self.records = []

    def observe(self, session, h, old_tanks, old_modules):
        self.steps += 1
        frame = session.last_accepted_frame
        network, result = session.view, session.result
        for node, old_mass in old_tanks.items():
            net = sum(float(q) * ((b.end_node == node) - (b.start_node == node))
                      for b, q in zip(network.branches, result.hydraulic.flows))
            self.checks.near('tank_mass_ledger', session.tanks[node].mass_kg - old_mass, net * h,
                             atol=1e-7, rtol=1e-8, node=node, time_s=session.time)
        for key, previous in old_modules.items():
            state = session.runners[key].state
            if 'throughput_kg' in previous:
                transported = h * sum(abs(float(q)) for b, q in zip(network.branches, result.hydraulic.flows) if b.instance_id == key)
                self.checks.near('module_mass_ledger', state['throughput_kg'] - previous['throughput_kg'], transported,
                                 atol=1e-8, rtol=1e-8, instance=key, time_s=session.time)
            if 'commit_count' in previous:
                self.checks.require('module_commit_count', state['commit_count'] == previous['commit_count'] + 1,
                                    instance=key, time_s=session.time)
            for name, channel in [('thermal_energy_j', 'main'), ('transferred_energy_j', 'cold')]:
                if name in previous:
                    power = frame.variables[f'{key}.{channel}.heat_w']
                    self.checks.near('module_energy_ledger', state[name] - previous[name], power * h,
                                     atol=1e-5, rtol=1e-8, instance=key, time_s=session.time)
        self.records.append({'time_s': session.time, 'dt_s': h})
