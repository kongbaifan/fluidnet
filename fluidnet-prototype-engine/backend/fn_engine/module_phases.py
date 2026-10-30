"""Current-solution thermal callbacks and observations, isolated from state acceptance."""
import math

from .models import ChannelState, ModulePhaseRequest, PortState
from .runtime import RuntimeErrorBase
from .module_diagnostics import merge_diagnostics

HEAT_ATOL_W = 1e-6
HEAT_RTOL = 1e-6


def has_phase(definition, phase):
    return definition.sdk is not None and f'{phase}.v1' in definition.sdk.capabilities


def heat_hook(network, runners, hydraulic, service, time_s):
    active = {key: runner for key, runner in runners.items()
              if has_phase(network.modules[network.instances[key].module_id], 'thermal')}
    if not active:
        return None
    for branch, relation in hydraulic.relations.items():
        if branch[0] in active and relation.parameters.get('heat_w', 0) != 0:
            raise RuntimeErrorBase('不能同时通过水力关系和热回调供热', code='MODULE_HEAT_DUPLICATED')
    branches = network.branches

    def invoke(states, previous_heat):
        heat, diagnostics = {}, []
        for key, runner in active.items():
            definition = network.modules[network.instances[key].module_id]
            ports = {port.id: PortState(**states[network.port_nodes[f'{key}:{port.id}']].model_dump(
                include=set(PortState.model_fields))) for port in definition.ports}
            channels = {}
            for j, branch in enumerate(branches):
                if branch.instance_id != key:
                    continue
                q = float(hydraulic.flows[j])
                resolved_q = q if abs(q) > network.project.solver.mass_tolerance_kg_s else 0.
                channels[branch.channel_id] = ChannelState(mass_flow_kg_s=resolved_q,
                    pressure_drop_pa=float(hydraulic.pressures[branch.start_node] - hydraulic.pressures[branch.end_node]),
                    heat_w=float(previous_heat[j]))
                up_port, down_port = (branch.input_port, branch.output_port) if q >= 0 else (branch.output_port, branch.input_port)
                up_node, down_node = (branch.start_node, branch.end_node) if q >= 0 else (branch.end_node, branch.start_node)
                if up_node in network.air_nodes:
                    w = states[up_node].humidity_ratio_kg_kg
                    total = resolved_q*(1+w)
                    channels[branch.channel_id] = channels[branch.channel_id].model_copy(update={
                        'mass_flow_kg_s':total,'dry_air_mass_flow_kg_s':resolved_q,
                        'inlet_mass_flow_kg_s':total,'outlet_mass_flow_kg_s':total})
                    ports[up_port] = ports[up_port].model_copy(update={'mass_flow_kg_s':abs(total),
                        'dry_air_mass_flow_kg_s':abs(resolved_q),'water_vapor_mass_flow_kg_s':abs(resolved_q)*w})
                    outlet = service.state_phw(float(hydraulic.pressures[down_node]),
                        states[up_node].enthalpy_j_kg_dry_air+(previous_heat[j]/abs(q) if resolved_q else 0.),w)
                    ports[down_port] = PortState(**outlet.model_dump(include=set(PortState.model_fields)),
                        mass_flow_kg_s=-abs(total),dry_air_mass_flow_kg_s=-abs(resolved_q),water_vapor_mass_flow_kg_s=-abs(resolved_q)*w)
                    continue
                ports[up_port] = ports[up_port].model_copy(update={'mass_flow_kg_s':abs(resolved_q)})
                if abs(q) > network.project.solver.mass_tolerance_kg_s:
                    from .compiler import service_at
                    outlet = service_at(network, down_node, service).state_ph(float(hydraulic.pressures[down_node]),
                        states[up_node].enthalpy_j_kg + previous_heat[j] / abs(q))
                    ports[down_port] = PortState(**outlet.model_dump(include=set(PortState.model_fields)), mass_flow_kg_s=-abs(q))
                else:
                    ports[down_port] = ports[down_port].model_copy(update={'mass_flow_kg_s':0.})
            response = runner.phase_call('thermal', ModulePhaseRequest(run_id=runner.execution.run_id,
                instance_id=key, time_s=time_s, ports=ports, channels=channels, context=runner.execution.context()))
            for channel, power in response.heat_w.items():
                if not math.isfinite(power) or abs(channels[channel].mass_flow_kg_s) <= network.project.solver.mass_tolerance_kg_s and power != 0:
                    raise RuntimeErrorBase(f'{key}.{channel} 非有限热流或零流量供热', code='MODULE_HEAT_INVALID')
                heat[(key, channel)] = power
            if 'thermal.conservative.v1' in definition.sdk.capabilities:
                if abs(sum(response.heat_w.values())) > HEAT_ATOL_W + HEAT_RTOL * max(map(abs, response.heat_w.values()), default=0):
                    raise RuntimeErrorBase(f'{key} 双侧换热不守恒', code='MODULE_HEAT_IMBALANCE')
            diagnostics = merge_diagnostics(diagnostics, response.diagnostics)
        return heat, diagnostics
    return invoke


def observe_modules(network, runners, result, time_s):
    from .module_scope import scope_diagnostics
    from .solver import channel_state
    for key, runner in runners.items():
        definition = network.modules[network.instances[key].module_id]
        channels = {}
        for j, branch in enumerate(network.branches):
            if branch.instance_id == key:
                channels[branch.channel_id] = channel_state(network, result, j)
        ports = {port.id:result.port_states[f'{key}:{port.id}'] for port in definition.ports}
        messages = scope_diagnostics(definition, ports, channels, 'observe', key, time_s)
        if definition.applicability is not None and result.thermal:
            from .thermal import phase_family
            for port in definition.ports:
                family = phase_family(result.thermal.port_states[f'{key}:{port.id}'])
                if family != 'unknown' and family not in definition.applicability.phases:
                    raise RuntimeErrorBase(f'{key}.{port.id} 相态 {family} 超出适用范围', code='MODULE_PHASE_UNSUPPORTED')
        if any(message.severity == 'error' for message in messages):
            raise RuntimeErrorBase('; '.join(message.message for message in messages), diagnostics=messages)
        result.hydraulic.module_diagnostics = merge_diagnostics(result.hydraulic.module_diagnostics, messages)
        if not has_phase(definition, 'observe'):
            continue
        response = runner.phase_call('observe', ModulePhaseRequest(run_id=runner.execution.run_id, instance_id=key,
            time_s=time_s, ports={port.id:result.port_states[f'{key}:{port.id}'] for port in definition.ports},
            channels=channels, context=runner.execution.context(port_data='converged')))
        protected = {'mass_flow_kg_s', 'pressure_drop_pa', 'heat_w', 'inlet_temperature_k', 'outlet_temperature_k'}
        if protected & response.variables.keys() or any(name.startswith(tuple(c.id + '.' for c in definition.channels)) for name in response.variables):
            raise RuntimeErrorBase('观察输出不能覆盖网络变量', code='MODULE_OUTPUT_CONFLICT')
        result.hydraulic.module_variables.update({f'{key}.{name}': value for name, value in response.variables.items()})
        result.hydraulic.module_diagnostics = merge_diagnostics(result.hydraulic.module_diagnostics, response.diagnostics)
