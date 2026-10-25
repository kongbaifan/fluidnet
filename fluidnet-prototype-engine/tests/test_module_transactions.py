"""Failure injection verifies the whole accepted boundary, including managed controls."""
from copy import deepcopy
from pathlib import Path

import pytest

from fn_engine.models import CommitStepRequest, FluidConfig, ModuleRequestContext, PIDController, ControlScript
from fn_engine.packages import load_module_package
from fn_engine.runtime import InProcessModuleRunner, RuntimeErrorBase
from fn_engine.simulation import SimulationSession
from fn_engine.solver import SolveFailed
from test_module_execution_network import network_for, probe_definition

ROOT = Path(__file__).resolve().parents[1]


def state_module(statement='ctx.state["values"].append(dt)'):
    module = load_module_package(ROOT / 'modules/programmable_valve')
    module.source = {'runtime': f'''class Module:
    def initialize(self, ctx): ctx.state['values'] = []
    def evaluate(self, ctx): pass
    def commit_step(self, ctx, dt):
        {statement}
    def finalize(self, ctx): pass
'''}
    module.content_hash = module.definition_hash = None
    return module


def request(step='step1', time=.5):
    return CommitStepRequest(run_id='run1', instance_id='D1', time_s=time, dt_s=.5,
        context=ModuleRequestContext(request_id='request1', step_id=step))


def test_candidate_nested_state_isolated_retry_idempotent_and_stale_rejected():
    runner = InProcessModuleRunner(state_module(), {}, FluidConfig())
    runner.initialize()
    candidate = runner.prepare_step(request())
    assert runner.state == {'values': []}
    assert candidate.result.state == {'values': [.5]}
    assert runner.prepare_step(request()) == candidate
    runner.synchronize_state(candidate)
    runner.synchronize_state(candidate)
    assert runner.state == {'values': [.5]} and runner.state_revision == 1
    assert runner.prepare_step(request()) == candidate
    next_candidate = runner.prepare_step(request('step2', 1.))
    runner.synchronize_state(next_candidate)
    with pytest.raises(RuntimeErrorBase): runner.synchronize_state(candidate)
    assert runner.state == {'values': [.5, .5]}


@pytest.mark.parametrize('statement', [
    'ctx.state["values"].append(float("nan"))',
    'ctx.state["blob"] = "x" * 65536',
    'ctx.state["bad"] = object()',
    'ctx.state["bad"] = ctx.state',
    'ctx.diagnostic("INVALID", "reject", "error")',
    'ctx.var("bad", float("inf"))',
    'ctx.state["values"].append(dt); raise ValueError("fault")',
])
def test_invalid_candidates_never_mutate_accepted_nested_state(statement):
    runner = InProcessModuleRunner(state_module(statement), {}, FluidConfig())
    runner.initialize()
    with pytest.raises(ValueError): runner.prepare_step(request())
    assert runner.state == {'values': []} and runner.state_revision == 0


@pytest.mark.parametrize('batch,parallelism', [(False, 1), (True, 1), (True, 2)])
def test_second_module_failure_rolls_back_pid_scripts_parameters_and_revision(tmp_path, batch, parallelism):
    module = probe_definition(tmp_path, fail_on='D2')
    for parameter in module.parameters:
        parameter.runtime = True
    network = network_for(module, 2, batch=batch, parallelism=parallelism)
    network.project.controllers = [PIDController(id='pid1', instance_id='D1', parameter_id='opening_ratio',
        measurement='D1.main.mass_flow_kg_s', setpoint=1., kp=.01, minimum=.1, maximum=1., sample_s=.1)]
    network.project.control_scripts = [ControlScript(id='script1', enabled=True, sample_s=.1,
        inputs=['D2.main.mass_flow_kg_s'], outputs=['D2.param.opening_ratio'], source='''
def initialize(ctx): ctx.state['samples'] = 0
def step(ctx, dt):
    ctx.state['samples'] += 1
    ctx.write('D2.param.opening_ratio', .3)
def finalize(ctx): pass
''')]
    session = SimulationSession(network, .5, .5)
    try:
        session.initialize()
        session.set_parameter('D1', 'kv_m3_h', 12.)  # acknowledged boundary command
        before_parameters = deepcopy(network.parameters)
        before_pid = deepcopy(session.controllers['pid1'])
        revision = session.revision
        with pytest.raises(RuntimeErrorBase, match='injected commit failure'): session.advance()
        assert network.parameters == before_parameters
        assert session.revision == revision
        assert session.controllers['pid1'] == before_pid
        script = session.scripts['script1']
        assert script.state == {'samples': 0}
        assert script.samples == 0 and script.next_s == 0 and script.pending is None
        assert all(r.state['commit_count'] == 0 and r.state_revision == 0 for r in session.runners.values())
        assert session.time == 0.
    finally:
        session.close()


@pytest.mark.parametrize('batch', [False, True])
def test_output_conflict_detected_before_any_module_promotes(tmp_path, batch):
    module = probe_definition(tmp_path)
    module.source['runtime'] = module.source['runtime'].replace(
        "ctx.state['commit_count']+=1", "ctx.state['commit_count']+=1\n        ctx.var('main.mass_flow_kg_s', 999.)")
    session = SimulationSession(network_for(module, 2, batch=batch), .5, .5)
    try:
        session.initialize()
        with pytest.raises(ValueError, match='输出不能覆盖'): session.advance()
        assert session.time == 0.
        assert all(r.state_revision == 0 for r in session.runners.values())
    finally:
        session.close()


def test_lost_sync_after_acceptance_keeps_authoritative_states_and_internal_frame(tmp_path, monkeypatch):
    session = SimulationSession(network_for(probe_definition(tmp_path), 2, batch=False), .5, .5)
    try:
        session.initialize()
        def lost(candidate): raise OSError('lost acknowledgement')
        monkeypatch.setattr(session.runners['D2'], 'synchronize_state', lost)
        with pytest.raises(SolveFailed, match='子步已接受') as captured: session.advance()
        assert session.time == .5
        assert all(r.state_revision == 1 and r.state['commit_count'] == 1 for r in session.runners.values())
        assert captured.value.frames[-1].time_s == .5
        assert session.last_accepted_frame.valid
    finally:
        session.close()


@pytest.mark.parametrize('fault', ['timeout', 'exit'])
@pytest.mark.parametrize('batch', [False, True])
def test_real_worker_commit_fault_does_not_promote_other_candidate(tmp_path, fault, batch):
    module = probe_definition(tmp_path)
    statement = "import time; time.sleep(1.)" if fault == 'timeout' else "import os; os._exit(7)"
    module.source['runtime'] = module.source['runtime'].replace("ctx.state['commit_count']+=1",
        f"if ctx.execution.instance_id == 'D2': {statement}\n        ctx.state['commit_count']+=1")
    session = SimulationSession(network_for(module, 2, batch=batch), .5, .5)
    try:
        session.initialize()
        worker = getattr(session.runners['D2'], 'worker', session.runners['D2'])
        worker.timeout_s = .2
        with pytest.raises(RuntimeErrorBase): session.advance()
        assert session.time == 0.
        assert all(r.state_revision == 0 and r.state['commit_count'] == 0 for r in session.runners.values())
        assert worker.process is None
    finally:
        session.close()


def test_old_trial_cannot_accept_after_acknowledged_parameter_change(tmp_path):
    module=probe_definition(tmp_path)
    for parameter in module.parameters:parameter.runtime=True
    session=SimulationSession(network_for(module),.5,.5)
    try:
        session.initialize();trial=session._trial(.5)
        session.set_parameter('D1','kv_m3_h',12.)
        revision=session.revision
        with pytest.raises(ValueError,match='参数修订已变化'):session._accept(.5,*trial)
        assert session.time==0. and session.revision==revision
        assert session.network.parameters['D1']['kv_m3_h']==12.
        assert session.runners['D1'].state['commit_count']==0
    finally:session.close()
