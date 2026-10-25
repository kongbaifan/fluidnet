"""RPC avoidance, invalidation and sparse mixed-network derivatives."""
from copy import deepcopy
from pathlib import Path
import sys

import numpy as np
import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import ChannelState, CommitStepRequest, EvaluateRequest, FluidConfig, PortState
from fn_engine.runtime import RuntimeErrorBase, WorkerProcess
from fn_engine.solver import _close_runners, _python_runners, solve_dynamic, solve_network
from test_module_execution_network import network_for
from test_module_performance import pure_module

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from numerics_cases import python_multiport_project, series_project


def cache_probe():
    module = pure_module()
    module.source['runtime'] = '''class Module:
    def initialize(self, ctx): ctx.state['total'] = 0.
    def evaluate(self, ctx):
        ctx.net.resistance(channel='main', diameter_m=ctx.parameter('diameter_m'),
            loss_coefficient=ctx.parameter('loss_coefficient'), density_kg_m3=ctx.port('in0').density_kg_m3)
        ctx.var('total', ctx.state['total'])
        ctx.var('time', ctx.time_s)
    def commit_step(self, ctx, dt_s):
        ctx.state['total'] += abs(ctx.channel('main').mass_flow_kg_s) * dt_s
    def finalize(self, ctx): pass
'''
    return module


def request_for(instance='D1', time_s=0., density=998.2):
    return EvaluateRequest(run_id='cache-test', instance_id=instance, iteration_id=0, time_s=time_s,
        trial_ports={'in0': PortState(pressure_pa=250000., density_kg_m3=density),
                     'out0': PortState(pressure_pa=120000.)})


def test_parent_cache_requires_worker_ack_and_invalidates_on_inputs_and_commit():
    module = cache_probe()
    params = {p.id: p.default for p in module.parameters}
    worker = WorkerProcess(module, params, FluidConfig(), instance_id='D1', cache_enabled=True)
    try:
        worker.initialize()
        request = request_for()
        before = worker.request_count
        assert not worker.evaluate(request).cache_hit
        assert worker.evaluate(request).cache_hit
        assert worker.request_count == before + 2  # Second response grants Worker consent.
        third = worker.evaluate(request.model_copy(update={'iteration_id': 17}))
        assert worker.request_count == before + 2
        third.variables['total'] = 999
        third.relations[0].parameters['loss_coefficient'] = 999
        unchanged = worker.evaluate(request)
        assert unchanged.variables['total'] == 0.
        assert unchanged.relations[0].parameters['loss_coefficient'] == params['loss_coefficient']

        changed = worker.evaluate(request_for(time_s=.5, density=1100.))
        assert not changed.cache_hit
        assert changed.variables['time'] == .5
        assert changed.relations[0].parameters['density_kg_m3'] == 1100.
        worker.update_parameters({**params, 'loss_coefficient': 3.})
        assert worker.evaluate(request).relations[0].parameters['loss_coefficient'] == 3.

        worker.evaluate(request)
        count = worker.request_count
        worker.evaluate(request)
        assert worker.request_count == count
        candidate = worker.prepare_step(CommitStepRequest(run_id='cache-test', instance_id='D1', time_s=1., dt_s=1.,
            converged_channels={'main': ChannelState(mass_flow_kg_s=2.)}))
        worker.discard_candidate()
        assert worker.evaluate(request).variables['total'] == 0.
        assert worker.request_count == count + 2  # Discard does not change accepted state.
        worker.commit_step(CommitStepRequest(run_id='cache-test', instance_id='D1', time_s=1., dt_s=1.,
            converged_channels={'main': ChannelState(mass_flow_kg_s=2.)}))
        accepted = worker.evaluate(request)
        assert worker.state_revision == candidate.base_revision + 1
        assert not accepted.cache_hit and accepted.variables['total'] == 2.
        worker.evaluate(request)
        worker.evaluate(request)
        worker.close(force=True)
        with pytest.raises(RuntimeErrorBase, match='已关闭') as failed:
            worker.evaluate(request)
        assert failed.value.diagnostics[0].instance_id == 'D1'
        assert failed.value.diagnostics[0].phase == 'evaluate'
    finally:
        worker.close()


@pytest.mark.parametrize('batch', [False, True])
def test_execution_identity_is_never_hidden_by_parent_cache(batch):
    module = cache_probe()
    module.source['runtime'] = module.source['runtime'].replace("ctx.var('time', ctx.time_s)",
        "ctx.var('time', ctx.time_s)\n        ctx.var('iteration', ctx.execution.iteration_id)")
    network = network_for(module, 2 if batch else 1, batch=batch)
    network.project.solver.module_cache = True
    runners = _python_runners(network)
    try:
        for iteration in range(4):
            requests = {key: request_for(key).model_copy(update={'iteration_id': iteration}) for key in runners}
            responses = runners.evaluate(requests) if batch else {key: runner.evaluate(requests[key]) for key, runner in runners.items()}
            assert all(r.variables['iteration'] == iteration and not r.cache_hit for r in responses.values())
        if batch:
            assert runners.parent_cache_hits == 0
        else:
            assert runners['D1'].parent_cache_hits == 0
    finally:
        _close_runners(runners)


@pytest.mark.parametrize('batch', [False, True])
@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_ports_cannot_alias_a_cached_null_input(batch, invalid):
    network = network_for(cache_probe(), 2 if batch else 1, batch=batch)
    network.project.solver.module_cache = True
    runners = _python_runners(network)

    def evaluate(requests):
        return runners.evaluate(requests) if batch else {key: runner.evaluate(requests[key]) for key, runner in runners.items()}

    try:
        requests = {key: request_for(key, density=None) for key in runners}
        evaluate(requests)
        evaluate(requests)
        evaluate(requests)
        before = runners.request_count if batch else runners['D1'].request_count
        # Internal trial construction uses model_copy(update=...), which does not
        # run Pydantic validators; the Worker normally revalidates the wire data.
        broken = request_for('D1', density=None)
        broken.trial_ports['in0'] = broken.trial_ports['in0'].model_copy(update={'density_kg_m3': invalid})
        with pytest.raises(RuntimeErrorBase):
            evaluate({**requests, 'D1': broken})
        after = runners.request_count if batch else runners['D1'].request_count
        assert after > before  # Delegate invalid input to the original Worker validation path.
        assert evaluate(requests)['D1'].relations[0].parameters['density_kg_m3'] == 0.
    finally:
        _close_runners(runners)


def test_batched_parent_hits_skip_empty_shards_and_keep_instance_caches_isolated():
    network = network_for(cache_probe(), 4, parallelism=2)
    network.project.solver.module_cache = True
    runners = _python_runners(network)
    try:
        requests = {key: request_for(key) for key in runners}
        runners.evaluate(requests)
        runners.evaluate(requests)
        before = runners.request_count
        runners.evaluate(requests)
        assert runners.request_count == before and runners.parent_cache_hits == 4
        changed = dict(requests, D1=request_for('D1', time_s=1.))
        responses = runners.evaluate(changed)
        assert runners.request_count == before + 1
        assert responses['D1'].variables['time'] == 1.
        assert responses['D2'].variables['time'] == 0.
        runners['D1'].update_parameters({**network.parameters['D1'], 'loss_coefficient': 5.})
        before = runners.request_count
        responses = runners.evaluate(requests)
        assert runners.request_count == before + 1
        assert responses['D1'].relations[0].parameters['loss_coefficient'] == 5.
        assert responses['D3'].relations[0].parameters['loss_coefficient'] != 5.
        runners.workers[0].close(force=True)
        with pytest.raises(RuntimeErrorBase, match='已关闭') as failed:
            runners.evaluate(requests)
        assert failed.value.diagnostics[0].instance_id == 'D1'
        assert failed.value.diagnostics[0].phase == 'evaluate'
    finally:
        _close_runners(runners)


def test_solve_counters_count_actual_shard_requests_and_exclude_parent_hits():
    network = network_for(pure_module(), 4, parallelism=2)
    network.project.solver.hydraulic_method = 'sparse'
    network.project.solver.hydraulic_diagnostics = True
    network.project.solver.module_cache = True
    runners = _python_runners(network)
    try:
        warm = solve_network(network, runners)
        before = runners.request_count
        warm = solve_network(network, runners, warm=warm)
        assert warm.hydraulic.counters['rpc_batches'] == runners.request_count - before
        before = runners.request_count
        warm = solve_network(network, runners, warm=warm)
        assert warm.hydraulic.counters['rpc_batches'] == runners.request_count - before == 0
        assert warm.hydraulic.counters['rpc_instances'] == 0
        assert warm.hydraulic.counters['parent_cache_hits'] > 0
    finally:
        _close_runners(runners)


@pytest.mark.parametrize('size', [8, 40])
def test_mixed_jacobian_perturbations_do_not_grow_with_series_network_size(size):
    project = series_project(size + 2, python_fraction=.5)
    project.solver.thermal = False
    project.solver.hydraulic_method = 'sparse'
    project.solver.hydraulic_diagnostics = True
    network = compile_project(project)
    runners = _python_runners(network)
    try:
        reference = solve_network(network, runners)
        network.project.solver.module_mixed_jacobian = True
        warm = solve_network(network, runners, warm=reference)
        np.testing.assert_allclose(warm.hydraulic.flows, reference.hydraulic.flows, rtol=1e-6, atol=1e-8)
        assert warm.hydraulic.counters['problem_size'] == size * 2 - 1
        assert warm.hydraulic.counters['perturbation_calls'] <= 5
        assert warm.hydraulic.pressure_residual <= project.solver.pressure_tolerance_pa
        assert warm.hydraulic.mass_residual <= project.solver.mass_tolerance_kg_s
    finally:
        _close_runners(runners)


@pytest.mark.parametrize('method', ['dense', 'sparse'])
def test_grouped_mixed_jacobian_keeps_cross_channel_pressure_dependencies(method):
    project = python_multiport_project(4)
    module = next(m for m in project.modules if m.runtime == 'python')
    module.source['runtime'] = module.source['runtime'].replace('kv=ctx.parameter("kv_m3_h")',
        'kv=ctx.parameter("kv_m3_h") * ctx.port("in1" if channel == "a" else "in0").pressure_pa / 200000.')
    project.solver.thermal = False
    project.solver.hydraulic_method = method
    expected = solve_network(compile_project(project))
    project.solver.module_mixed_jacobian = True
    actual = solve_network(compile_project(project))
    np.testing.assert_allclose(actual.hydraulic.flows, expected.hydraulic.flows, rtol=1e-6, atol=1e-8)
    np.testing.assert_allclose(actual.hydraulic.pressures, expected.hydraulic.pressures, rtol=1e-6, atol=1e-3)


def test_sparse_mixed_jacobian_does_not_materialize_full_dense_matrix(monkeypatch):
    from scipy.sparse import csr_matrix

    project = series_project(18, python_fraction=.5)
    project.solver.thermal = False
    project.solver.hydraulic_method = 'sparse'
    project.solver.module_mixed_jacobian = True
    original = csr_matrix.toarray

    def guarded(matrix, *args, **kwargs):
        assert min(matrix.shape) <= 1, 'Sparse solve allocated a full dense matrix'
        return original(matrix, *args, **kwargs)

    monkeypatch.setattr(csr_matrix, 'toarray', guarded)
    result = solve_network(compile_project(deepcopy(project)))
    assert result.hydraulic.pressure_residual <= project.solver.pressure_tolerance_pa


@pytest.mark.parametrize('batch', [False, True])
def test_cached_dynamic_time_dependent_relations_and_accepted_mass_match_reference(batch):
    module = pure_module()
    module.source['runtime'] = module.source['runtime'].replace('loss_coefficient=coefficient,',
        'loss_coefficient=coefficient * (1. + ctx.time_s),')
    network = network_for(module, 2, batch=batch, node=True)
    network.project.solver.hydraulic_method = 'sparse'
    reference = solve_dynamic(network, .3, .1)
    optimized = deepcopy(network)
    optimized.project.solver.module_cache = True
    optimized.project.solver.module_mixed_jacobian = True
    actual = solve_dynamic(optimized, .3, .1)
    assert len(actual) == len(reference)
    assert actual[-1].variables['D1.mass_flow_kg_s'] < actual[0].variables['D1.mass_flow_kg_s']
    assert actual[-1].variables['D1.state.throughput_kg'] > 0
    for frame, expected in zip(actual, reference, strict=True):
        for key, value in expected.variables.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                assert frame.variables[key] == pytest.approx(value, rel=1e-6, abs=1e-7), key


@pytest.mark.parametrize('factor', [1., 2.])
def test_declared_derivative_keeps_sparse_validation_and_falls_back_when_wrong(monkeypatch, factor):
    from scipy.sparse import csr_matrix

    module = pure_module()
    module.sdk.capabilities.append('hydraulic.derivatives.v1')
    module.source['runtime'] += f'''
def jacobian(self, ctx):
    import math
    area = math.pi * ctx.parameter('diameter_m') ** 2 / 4
    slope = 2 * ctx.parameter('loss_coefficient') * abs(ctx.channel('main').mass_flow_kg_s)
    slope /= 2 * ctx.port('in0').density_kg_m3 * area**2
    ctx.derivative('main', slope * {factor!r}, {{}})
Module.jacobian = jacobian
'''
    network = network_for(module, 3)
    network.project.solver.hydraulic_method = 'sparse'
    expected = solve_network(network)
    network.project.solver.module_mixed_jacobian = True
    original = csr_matrix.toarray

    def guarded(matrix, *args, **kwargs):
        assert min(matrix.shape) <= 1
        return original(matrix, *args, **kwargs)

    monkeypatch.setattr(csr_matrix, 'toarray', guarded)
    result = solve_network(network)
    np.testing.assert_allclose(result.hydraulic.flows, expected.hydraulic.flows, rtol=1e-6, atol=1e-8)
    fallback = any(d.code == 'MODULE_DERIVATIVE_FALLBACK' for d in result.hydraulic.module_diagnostics)
    assert fallback == (factor != 1.)
