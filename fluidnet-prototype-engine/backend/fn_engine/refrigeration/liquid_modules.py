"""Hydraulic-only Python devices inside the coupled algebraic liquid network.

The station owns acceptance. Nested Newton/step-doubling solves see the same
accepted module state; commit_step runs once at the complete segment boundary.
"""
from copy import deepcopy

from ..compiler import CompilationError, instance_fluids
from ..model_types.base import Diagnostic
from ..module_execution import mark_module_accepted, new_identity
from ..runtime import RuntimeErrorBase, WorkerProcess
from ..solver import _close_runners, _commit_modules
from .devices import valve_flow


def check_output_variables(definition, variables):
    declared = {variable.id for variable in definition.variables if variable.source == 'derived'}
    protected = {'mass_flow_kg_s', 'volume_flow_m3_h', 'pressure_drop_pa', 'inlet_pressure_pa',
                 'outlet_pressure_pa', 'inlet_temperature_k', 'outlet_temperature_k', 'heat_w', 'shaft_power_w'}
    prefixes = ('state.', 'param.', *(port.id + '.' for port in definition.ports),
                *(channel.id + '.' for channel in definition.channels))
    if set(variables) - declared or protected & variables.keys() or any(key.startswith(prefixes) for key in variables):
        raise RuntimeErrorBase('作者回调不能返回未声明的观察变量或覆盖平台通路、端口、参数与状态字段',
                               code='MODULE_OUTPUT_INVALID')


def check_liquid_module(definition, instance_id):
    required = {'state.transactions.v1'}
    allowed = {'lifecycle.v1', 'state.json.v1', 'properties.v1', 'context.execution.v1',
               'context.log.v1', 'state.transactions.v1', 'hydraulics.v1', 'observe.v1',
               'hydraulic.signed_start.v1', 'hydraulic.derivatives.v1', 'evaluate.pure.v1',
               'net.valve', 'net.resistance'}
    capabilities = set(definition.sdk.capabilities) if definition.sdk else set()
    channels = definition.channels
    if (definition.schema_version not in {2, 3} or required - capabilities or capabilities - allowed
            or not capabilities & {'net.valve', 'net.resistance'}
            or len(definition.ports) != 2 or len(channels) != 1
            or channels[0].relation != 'resistance' or not channels[0].enabled
            or channels[0].solver_model not in {'valve', 'generic', 'resistance'}
            or definition.state_model or definition.thermal_model):
        raise CompilationError('COUPLED_LIQUID_MODULE_UNSUPPORTED',
            '热耦合液体侧 Python 首批仅支持声明 state.transactions.v1 的无储量、单通路阀门/局部阻力；'
            '不支持主动供热、泵、跨侧换热或独立物理储量', instance_id, 'sdk.capabilities')


class LiquidWorker(WorkerProcess):
    """Recheck actual returned relations, including undeclared SDK calls."""

    def evaluate(self, request):
        response = super().evaluate(request)
        check_output_variables(self.definition, response.variables)
        for relation in response.relations:
            allowed = ({'kv_m3_h', 'opening_ratio', 'density_kg_m3', 'height_m', 'heat_w'} if relation.kind == 'valve'
                       else {'diameter_m', 'loss_coefficient', 'density_kg_m3', 'heat_w'})
            if (relation.kind not in {'valve', 'resistance'}
                    or set(relation.parameters) - allowed or relation.parameters.get('heat_w', 0) != 0):
                message = '热耦合液体侧作者设备只能返回无附加热流的阀门或局部阻力关系'
                diagnostic = Diagnostic(code='COUPLED_LIQUID_RELATION_UNSUPPORTED', message=message,
                    instance_id=self.execution.instance_id, channel_id=relation.channel,
                    phase='evaluate', time_s=request.time_s)
                raise RuntimeErrorBase(message, code=diagnostic.code, diagnostics=[diagnostic])
        return response

    def phase_call(self, phase, request):
        response = super().phase_call(phase, request)
        if phase == 'observe':
            check_output_variables(self.definition, response.variables)
        return response


class CoupledLiquidModules:
    def __init__(self, network):
        self.network = network.fluid_network
        self.runners = {}
        self._initialized = False
        run_id = new_identity('coupled-liquid')
        for iid, instance in self.network.instances.items():
            definition = self.network.modules[instance.module_id]
            if definition.runtime != 'python':
                continue
            fluid, ports = instance_fluids(self.network, iid)
            self.runners[iid] = LiquidWorker(definition, deepcopy(network.parameters[iid]), fluid,
                port_fluids=ports, run_id=run_id, instance_id=iid,
                cache_enabled=self.network.project.solver.module_cache)

    def initialize(self):
        if self._initialized:
            return
        try:
            for runner in self.runners.values():
                runner.initialize()
            mark_module_accepted(self.runners, 0.)
            self._initialized = True
        except BaseException:
            _close_runners(self.runners)
            raise

    def evaluate(self, iid, service, parameters, high, low, time_s):
        # StationSession routes its built-in refrigerant valves through this hook.
        # These remain built-in; only the separate liquid solver uses our Workers.
        return valve_flow(service, parameters, high.pressure_pa, low.pressure_pa)

    def prepare(self, step_id, time_s, dt_s, result):
        water = result['fluid_result']
        # Each nested solve has a trial ID; preparation belongs to the enclosing
        # station segment, never the last finite-difference trial.
        water.module_step_id = step_id
        _, diagnostics, transaction = _commit_modules(self.network, self.runners, water, time_s, dt_s)
        try:
            self.variables(result, transaction.candidates)
        except Exception:
            transaction.discard()
            raise
        water.hydraulic.module_diagnostics.extend(diagnostics)
        return transaction

    def variables(self, result, candidates=None):
        values = {}
        for iid, runner in self.runners.items():
            candidate = runner._accepted_candidate if candidates is None else candidates[iid]
            state = runner.state if candidates is None else candidate.result.state
            if 'transferred_mass_kg' in state:
                raise RuntimeErrorBase('transferred_mass_kg 由平台按实际接受子步积分，作者状态不能覆盖',
                                       code='MODULE_STATE_CONFLICT')
            if candidate is not None:
                check_output_variables(runner.definition, candidate.result.variables)
                values.update({f'{iid}.{key}': value for key, value in candidate.result.variables.items()})
            values.update({f'{iid}.state.{key}': value for key, value in state.items()
                           if isinstance(value, (float, int, str, bool)) or value is None})
        return values
