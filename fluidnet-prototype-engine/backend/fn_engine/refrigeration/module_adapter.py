"""Typed refrigeration Workers and host-owned flow/state observations."""
from copy import deepcopy

from ..models import CommitStepRequest, Diagnostic, PortState, RefrigerationEvaluateRequest, RefrigerationThrottleInput
from ..module_execution import new_identity, mark_module_accepted
from ..module_transactions import ModuleStepTransaction
from ..runtime import RuntimeErrorBase, WorkerProcess

MASS_COUNTER = 'transferred_mass_kg'


def validate_observations(definition, values):
    from ..refrigeration_roles import RESERVED_FLOW_VARIABLES
    declared = {variable.id for variable in definition.variables if variable.source=='derived'}
    if set(values)-declared or RESERVED_FLOW_VARIABLES & values.keys() or \
            any(key.startswith(('state.','param.','in0.','out0.')) for key in values):
        raise RuntimeErrorBase('制冷设备返回未声明或保留的观察变量',code='MODULE_OUTPUT_INVALID')


def state_variables(definition, state):
    if MASS_COUNTER in state:
        raise RuntimeErrorBase('累计通过质量由平台积分，作者状态不能覆盖它',code='MODULE_STATE_CONFLICT')
    values = {}
    for variable in definition.variables:
        if variable.source!='state' or variable.id==f'state.{MASS_COUNTER}':
            continue
        value = state
        for part in variable.id.removeprefix('state.').split('.'):
            if not isinstance(value,dict) or part not in value:
                break
            value = value[part]
        else:
            if isinstance(value,(dict,list)):
                raise RuntimeErrorBase(f'观察状态 {variable.id} 必须是标量',code='MODULE_OUTPUT_INVALID')
            values[variable.id] = value
    return values


def evaluate_throttle(runner, service, parameters, inlet_pa, outlet_pa, time_s, iteration):
    if runner.parameters!=parameters:
        runner.update_parameters(parameters)
    liquid = service.state_pq(inlet_pa,0.)
    inputs = RefrigerationThrottleInput(inlet_pressure_pa=inlet_pa,outlet_pressure_pa=outlet_pa,
        inlet_temperature_k=liquid.temperature_k,inlet_enthalpy_j_kg=liquid.enthalpy_j_kg,
        inlet_density_kg_m3=liquid.density_kg_m3,opening_ratio=parameters['opening_ratio'],rated_kv_m3_h=parameters['kv_m3_h'])
    response = runner.evaluate_refrigeration(RefrigerationEvaluateRequest(run_id=runner.execution.run_id,
        instance_id=runner.execution.instance_id,iteration_id=iteration,time_s=time_s,throttle=inputs,
        state_revision=runner.state_revision,context=runner.execution.context()))
    validate_observations(runner.definition,response.variables)
    drop = inlet_pa-outlet_pa
    flashed = service.state_ph(outlet_pa,liquid.enthalpy_j_kg) if drop>0 else None
    mass = response.flow.mass_flow_kg_s
    ports = {'in0':PortState(pressure_pa=inlet_pa,temperature_k=liquid.temperature_k,
                 enthalpy_j_kg=liquid.enthalpy_j_kg,density_kg_m3=liquid.density_kg_m3,quality=0.,mass_flow_kg_s=mass),
             'out0':PortState(pressure_pa=outlet_pa,enthalpy_j_kg=liquid.enthalpy_j_kg,
                 temperature_k=flashed.temperature_k if flashed else None,quality=flashed.quality if flashed else None,
                 density_kg_m3=flashed.density_kg_m3 if flashed else None,mass_flow_kg_s=-mass)}
    return {'mass_flow_kg_s':mass,'effective_kv_m3_h':response.flow.effective_kv_m3_h,
            'pressure_drop_pa':drop,'enthalpy_j_kg':liquid.enthalpy_j_kg,'outlet_quality':flashed.quality if flashed else None,
            'module_ports':ports,'module_response':response,'diagnostics':response.diagnostics}


def flow_variables(result):
    values = {key:result[key] for key in ('mass_flow_kg_s','effective_kv_m3_h','pressure_drop_pa','enthalpy_j_kg','outlet_quality')}
    values.update(result['module_response'].variables)
    for port,data in result['module_ports'].items():
        values.update({f'{port}.{key}':value for key,value in data.model_dump().items()
                       if key in {'pressure_pa','temperature_k','enthalpy_j_kg','density_kg_m3','quality','mass_flow_kg_s'}})
    return values


class RefrigerationModules:
    def __init__(self, network):
        self.network = network
        self.iteration = 0
        run_id = new_identity('refrigeration')
        self.runners = {iid:WorkerProcess(definition.model_copy(deep=True),deepcopy(network.parameters[iid]),
            network.vessel_fluids[network.vessel(iid,'in0')],run_id=run_id,instance_id=iid)
            for iid,definition in network.refrigeration_modules.items()}

    def initialize(self):
        for runner in self.runners.values():
            runner.initialize()
            state_variables(runner.definition,runner.state)
        mark_module_accepted(self.runners,0.)

    def evaluate(self, iid, service, parameters, high, low, time_s):
        from .devices import valve_flow
        if iid not in self.runners:
            return valve_flow(service,parameters,high.pressure_pa,low.pressure_pa)
        self.iteration += 1
        try:
            return evaluate_throttle(self.runners[iid],service,parameters,high.pressure_pa,low.pressure_pa,time_s,self.iteration)
        except ValueError as error:
            if isinstance(error,RuntimeErrorBase) and error.diagnostics:
                raise
            raise RuntimeErrorBase(str(error),code=getattr(error,'code','MODULE_REFRIGERATION_FAILED'),
                diagnostics=[Diagnostic(code=getattr(error,'code','MODULE_REFRIGERATION_FAILED'),message=str(error),
                    instance_id=iid,phase='evaluate',time_s=time_s)]) from error

    def prepare(self, step_id, time_s, dt_s, result):
        transaction = ModuleStepTransaction(self.runners,step_id,time_s)
        try:
            for iid,runner in self.runners.items():
                request = CommitStepRequest(run_id=runner.execution.run_id,instance_id=iid,time_s=time_s,dt_s=dt_s,
                    converged_ports=result['devices'][iid]['module_ports'],context=runner.execution.context(port_data='converged'))
                transaction.prepare(iid,request,{})
                state_variables(runner.definition,transaction.candidates[iid].result.state)
                validate_observations(runner.definition,transaction.candidates[iid].result.variables)
            transaction.validate()
            return transaction
        except Exception:
            transaction.discard()
            raise

    def variables(self, result, candidates=None):
        values = {}
        for iid,runner in self.runners.items():
            fields = flow_variables(result['devices'][iid])
            candidate = runner._accepted_candidate if candidates is None else candidates[iid]
            fields.update(state_variables(runner.definition,runner.state if candidates is None else candidate.result.state))
            if candidate is not None:fields.update(candidate.result.variables)
            values.update({f'{iid}.{key}':value for key,value in fields.items()})
        return values
