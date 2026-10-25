from copy import deepcopy
import math

import pytest

from fn_engine.models import EvaluateRequest, FluidConfig, ModuleDefinition, PortState, ModulePhaseRequest, ChannelState
from fn_engine.module_templates import create_template
from fn_engine.runtime import InProcessModuleRunner,WorkerProcess
from fn_engine.solver import solve_steady
from test_module_execution_network import network_for


def pure_module():
    payload = create_template('resistance', 'pure_probe', 'Pure').model_dump(mode='json')
    payload.update(schema_version=3, pure_evaluate=True, dependency_mode='tracked', hydraulic_dependencies={'main':['in0']})
    return ModuleDefinition.model_validate(payload)


def test_pure_cache_exact_input_state_time_and_parameter_invalidation_is_bounded():
    module = pure_module()
    runner = InProcessModuleRunner(module, {p.id:p.default for p in module.parameters}, FluidConfig(), cache_enabled=True)
    request = EvaluateRequest(run_id='r1', instance_id='D1', iteration_id=0, time_s=0,
        trial_ports={'in0':PortState(density_kg_m3=998.2)})
    first = runner.evaluate(request)
    cached = runner.evaluate(request.model_copy(update={'iteration_id':1}))
    assert not first.cache_hit and cached.cache_hit
    assert first.relations == cached.relations
    for time in range(100):
        assert not runner.evaluate(request.model_copy(update={'time_s':float(time)+.1})).cache_hit
    assert len(runner._evaluate_cache) <= 64
    runner.parameters['loss_coefficient'] = 2.
    assert not runner.evaluate(request).cache_hit
    changed = request.model_copy(update={'readonly_state': {'marker':1}})
    assert not runner.evaluate(changed).cache_hit


def test_out_of_declaration_read_is_rejected_even_when_bypassing_port_method():
    module = pure_module()
    module.source['runtime'] = module.source['runtime'].replace("ctx.port('in0')", "ctx.ports['out0']")
    runner = InProcessModuleRunner(module, {p.id:p.default for p in module.parameters}, FluidConfig())
    with pytest.raises(ValueError, match='越声明端口'):
        runner.evaluate(EvaluateRequest(run_id='r1',instance_id='D1',iteration_id=0,time_s=0,
            trial_ports={'out0':PortState(density_kg_m3=998.2)}))


@pytest.mark.parametrize('sparse', [False, True])
def test_mixed_jacobian_matches_full_finite_difference_physics(sparse):
    module = create_template('managed_state', 'mixed_probe', 'Mixed')
    network = network_for(module, 2, batch=True)
    network.project.solver.hydraulic_method = 'sparse' if sparse else 'dense'
    reference = solve_steady(network)
    candidate = deepcopy(network)
    candidate.project.solver.module_mixed_jacobian = True
    frame = solve_steady(candidate)
    assert frame.valid
    for key, value in reference.variables.items():
        if isinstance(value, (int,float)) and not isinstance(value,bool):
            assert frame.variables[key] == pytest.approx(value, rel=1e-6, abs=1e-8)
    assert frame.solve_summary['jacobian_mode'] == 'mixed'


def test_complete_resistance_derivative_matches_independent_difference():
    module = pure_module()
    module.sdk.api_version = '0.5.0'
    module.sdk.capabilities.append('hydraulic.derivatives.v1')
    module.source['runtime'] += '''
def jacobian(self, ctx):
    import math
    area = math.pi * self_parameter(ctx, 'diameter_m') ** 2 / 4
    rho = ctx.port('in0').density_kg_m3
    slope = self_parameter(ctx, 'loss_coefficient') * abs(ctx.channel('main').mass_flow_kg_s) / (rho * area**2)
    ctx.derivative('main', slope, {})
def self_parameter(ctx, name): return float(ctx.parameter(name))
Module.jacobian = jacobian
'''
    params = {p.id:p.default for p in module.parameters}
    runner = InProcessModuleRunner(module, params, FluidConfig())
    flow, rho = .5, 998.2
    response = runner.phase_call('jacobian', ModulePhaseRequest(run_id='r1',instance_id='D1',time_s=0,
        ports={'in0':PortState(density_kg_m3=rho)},channels={'main':ChannelState(mass_flow_kg_s=flow)}))
    area = math.pi*params['diameter_m']**2/4
    def drop(q): return params['loss_coefficient']*q*abs(q)/(2*rho*area**2)
    difference = (drop(flow+1e-6)-drop(flow-1e-6))/2e-6
    assert response.derivatives['main'].flow_slope_pa_per_kg_s == pytest.approx(difference,rel=1e-8)


def test_compact_worker_request_uses_verified_accepted_state_and_reduces_payload(monkeypatch):
    module=pure_module()
    module.source['runtime']=module.source['runtime'].replace("ctx.state.setdefault('throughput_kg', 0.0)",
        "ctx.state.setdefault('throughput_kg', 0.0)\n        ctx.state['blob']='x'*60000")
    module.source['runtime']=module.source['runtime'].replace("ctx.var('loss_coefficient', coefficient)",
        "ctx.var('loss_coefficient', coefficient)\n        ctx.var('state_size',len(ctx.state['blob']))")
    worker=WorkerProcess(module,{p.id:p.default for p in module.parameters},FluidConfig(),cache_enabled=True)
    try:
        worker.initialize();payloads=[];original=worker._request
        def observed(payload):payloads.append(payload);return original(payload)
        monkeypatch.setattr(worker,'_request',observed)
        request=EvaluateRequest(run_id='r1',instance_id='D1',iteration_id=0,time_s=0,trial_ports={'in0':PortState(density_kg_m3=998.2)})
        response=worker.evaluate(request)
        assert response.variables['state_size']==60000
        assert payloads[0]['request']['readonly_state']=={}
        assert payloads[0]['request']['state_revision']==0
        import json
        assert len(json.dumps(payloads[0]))<2000
    finally:worker.close()
