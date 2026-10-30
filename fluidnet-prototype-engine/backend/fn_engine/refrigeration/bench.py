"""Independent saturated-liquid supply and pressure receiver for author throttles."""
from copy import deepcopy
import math

from ..models import (CommitStepRequest, CommitStepResponse, Diagnostic, EvaluateResponse,
                     ModuleTestConditions, ModuleTestResponse, RunFrame)
from ..module_execution import begin_module_step, mark_module_accepted
from ..module_transactions import ModuleStepTransaction
from ..properties import property_service
from ..runtime import RuntimeErrorBase, WorkerProcess, module_content_hash
from .module_adapter import evaluate_throttle, flow_variables, state_variables, validate_observations


def effective_test_conditions(module, conditions):
    if not module.execution_role:
        return conditions
    fields = conditions.model_dump(mode='json',exclude_unset=True,exclude={'module'})
    defaults = {'fluid':{'fluid':module.applicability.fluids[0] if module.applicability.fluids else 'Ammonia','phase_policy':'any'},
                'inlet_pressure_pa':1350000.,'outlet_pressure_pa':110000.}
    return ModuleTestConditions.model_validate({**defaults,**fields})


def run_refrigeration_test(request):
    module=request.module
    conditions=effective_test_conditions(module,request)
    if conditions.moist_air or conditions.channel_boundaries or conditions.property_coupling!='reference':
        raise RuntimeErrorBase('制冷独立验证不使用湿空气、流体通路边界或单相节点物性迭代',code='REFRIGERATION_BENCH_OPTIONS')
    runner=WorkerProcess(module,conditions.parameters,conditions.fluid,instance_id='D1')
    service=property_service(conditions.fluid)
    history=[];mass=0.;transaction=None
    try:
        initial=deepcopy(runner.initialize());mark_module_accepted({'D1':runner},0.)
        committed=CommitStepResponse(state=initial)
        for index in range(math.ceil(conditions.duration_s/conditions.dt_s)+1):
            time_s=min(index*conditions.dt_s,conditions.duration_s)
            if history and time_s<=history[-1].time_s:
                continue
            step_id=begin_module_step({'D1':runner})
            result=evaluate_throttle(runner,service,runner.parameters,conditions.inlet_pressure_pa,
                conditions.outlet_pressure_pa,time_s,index)
            state=runner.state
            if index:
                dt=time_s-history[-1].time_s
                transaction=ModuleStepTransaction({'D1':runner},step_id,time_s)
                committed=transaction.prepare('D1',CommitStepRequest(run_id=runner.execution.run_id,instance_id='D1',
                    time_s=time_s,dt_s=dt,converged_ports=result['module_ports'],context=runner.execution.context(port_data='converged')),None)
                state=committed.state
                validate_observations(module,committed.variables)
                mass+=dt*result['mass_flow_kg_s']
            values=flow_variables(result)
            values.update(state_variables(module,state))
            values.update(committed.variables)
            values.update({f'param.{key}':value for key,value in runner.parameters.items()})
            values['state.transferred_mass_kg']=mass
            diagnostics=[*result['diagnostics'],Diagnostic(code='REFRIGERATION_BENCH_BOUNDARIES',severity='info',
                message='入口为给定压力的饱和液体，温度由压力确定；出口为给定压力的同焓流股。此验证台不积分容器存量。')]
            frame=RunFrame(status='converged',valid=True,time_s=time_s,
                variables={f'D1.{key}':value for key,value in values.items()},diagnostics=diagnostics,
                metrics={'mass_residual_kg_s':0.,'energy_residual_w':0.},sequence=index)
            RunFrame.model_validate_json(frame.model_dump_json())
            if index:
                transaction.promote()
            history.append(frame)
            if index:
                transaction.synchronize()
        runner.finalize()
        return ModuleTestResponse(module_id=module.id,content_hash=module_content_hash(module),state=initial,
            evaluation=EvaluateResponse(variables=flow_variables(result),diagnostics=result['diagnostics']),
            refrigeration_evaluation=result['module_response'],execution_domain='refrigeration',
            committed=committed,frame=history[-1],history=history)
    except Exception:
        if transaction is not None:transaction.discard()
        raise
    finally:runner.close()
