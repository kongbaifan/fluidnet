"""RF-0 uses real Worker processes; only explicit fault-injection tests replace a transport call."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import math
import sys

import pytest

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.examples import station_case, station_example
from fn_engine.refrigeration.station import StationSession, evaluate
from fn_engine.runtime import RuntimeErrorBase
from fn_engine.solver import SolveFailed, solve_steady

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from rf0_probe import ProbeSession, compile_probe, throttle_module  # noqa: E402


def probe(source=None, duration=.2, dt=.1, project=None):
    return ProbeSession(compile_probe(project or station_example(),{'EV1':throttle_module(source)}),duration,dt)


@pytest.fixture(scope='module')
def grid_session():
    session = probe()
    try:
        session.initialize()
        yield session
    finally:
        session.close()


@pytest.mark.parametrize('opening',[0.,.5,1.])
@pytest.mark.parametrize('high,low',[(900000.,300000.),(1200000.,400000.),(2000000.,500000.),(900000.,900000.),(900000.,1200000.)])
def test_independent_kv_grid_and_host_owned_isenthalpic_ports(grid_session,opening,high,low):
    session=grid_session
    params={**session.network.parameters['EV1'],'opening_ratio':opening}
    service=session.services['HP1']
    result=session._valve('EV1',service,params,SimpleNamespace(pressure_pa=high),SimpleNamespace(pressure_pa=low))
    liquid=service.state_pq(high,0.)
    expected=params['kv_m3_h']*opening*math.sqrt(1000*liquid.density_kg_m3*max(high-low,0)/100000)/3600
    assert result['mass_flow_kg_s']==pytest.approx(expected,rel=1e-12,abs=1e-14)
    assert result['enthalpy_j_kg']==liquid.enthalpy_j_kg
    ports=session.last_ports['EV1']
    assert ports['in0'].enthalpy_j_kg==ports['out0'].enthalpy_j_kg
    assert ports['in0'].mass_flow_kg_s+ports['out0'].mass_flow_kg_s==0.
    assert session.runners['EV1'].state['accepted_segments']==0


def test_same_candidate_pressure_enthalpy_and_station_ledgers():
    session=probe()
    try:
        session.initialize()
        energies={**session.energies,'HP1':session.energies['HP1']*1.00001}
        result=session._evaluate(session.masses,energies,session.temperatures)
        reference=evaluate(session.network,session.services,session.masses,energies,session.temperatures)
        for field in ('dm','du','dt'):
            assert result[field]==pytest.approx(reference[field],rel=1e-12,abs=1e-10)
        assert result['boundary_w']==reference['boundary_w']
        request=session.last_requests['EV1']
        assert request.trial_ports['in0'].pressure_pa==result['vessels']['HP1'].pressure_pa
        assert request.context.accepted_time_s==0.
        assert request.readonly_state=={}  # Worker supplies the authoritative accepted state copy.
        assert session.runners['EV1'].state['accepted_segments']==0
    finally:
        session.close()


def test_dynamic_matches_builtin_and_duplicate_messages_never_accept_twice():
    session=probe()
    baseline=StationSession(compile_project(station_example()),.2,.1)
    try:
        session.initialize();baseline.initialize()
        session.advance();reference=baseline.advance()
        assert session.masses==pytest.approx(baseline.masses,rel=1e-12)
        assert session.energies==pytest.approx(baseline.energies,rel=1e-12)
        assert session.temperatures==pytest.approx(baseline.temperatures,rel=1e-12)
        assert session.frames[-1].metrics['energy_residual_j']==pytest.approx(reference.metrics['energy_residual_j'],abs=1e-8)
        runner=session.runners['EV1'];state=deepcopy(runner.state)
        assert state=={'accepted_segments':1,'last_accepted_time_s':.1}
        assert runner.prepare_step(session.last_commit_requests['EV1'])==session.last_transaction.candidates['EV1']
        session.last_transaction.synchronize()
        assert runner.state==state and runner.state_revision==1
        with pytest.raises(RuntimeErrorBase): session.last_transaction.promote()
        calls=runner.request_count
        session.snapshot();session.snapshot()
        assert runner.request_count==calls  # observations do not execute author code again
        session.advance();baseline.advance()
        assert session.masses==pytest.approx(baseline.masses,rel=1e-12)
        assert runner.state['accepted_segments']==2
        for key in range(len(session.circuit_mass)):
            assert abs(session.frames[-1].metrics[f'mass_residual_kg_circuit{key}'])<1e-9
    finally:
        session.close();baseline.close()


def test_rejected_numerical_trial_halves_without_duplicate_state_or_mass(monkeypatch):
    session=probe(duration=.1)
    try:
        session.initialize()
        original=session._solve
        successful=[]
        def fail_large(x,h):
            result=original(x,h)
            if h>.075:
                raise devices.DeviceRangeError('REFRIGERATION_NOT_CONVERGED','injected trial rejection')
            successful.append((h,result[1]['devices']['EV1']['mass_flow_kg_s']))
            return result
        monkeypatch.setattr(session,'_solve',fail_large)
        frame=session.advance()
        assert len(successful)==2
        assert frame.variables['EV1.state.transferred_mass_kg']==pytest.approx(sum(h*m for h,m in successful),abs=1e-12)
        assert session.runners['EV1'].state['accepted_segments']==1
        assert session.last_requests['EV1'].time_s==.1
        assert session.evaluations>session.runners['EV1'].state['accepted_segments']
    finally:
        session.close()


@pytest.mark.parametrize('bad',['-1.0','float("nan")','float("inf")','True','"1 kg/s"','1e20','mass/2'])
def test_invalid_author_outputs_rejected_without_advancing_state(bad):
    source=throttle_module().source['runtime'].replace("ctx.var('mass_flow_kg_s', mass)",f"ctx.var('mass_flow_kg_s', {bad} if ctx.time_s > 0 else mass)")
    session=probe(source)
    try:
        session.initialize();state=deepcopy(session.masses)
        with pytest.raises(SolveFailed): session.advance()
        assert session.masses==state and session.time==0.
        assert session.runners['EV1'].state['accepted_segments']==0
        assert session.closed
    finally:
        session.close()


def test_commit_exception_preserves_last_accepted_physics_control_and_parameters():
    original=throttle_module().source['runtime']
    source=original.replace("ctx.state['accepted_segments'] = count + 1",
        "ctx.state['accepted_segments'] = count + 1\n        if ctx.time_s > .15: raise ValueError('commit fault')")
    assert source!=original
    project=station_case()
    for controller in project.controllers:controller.sample_s=.1
    for script in project.control_scripts:script.sample_s=.1
    session=probe(source,project=project)
    try:
        session.initialize();session.advance()
        session.set_parameter('ROOM1','heat_input_w',16000.)  # acknowledged command stays in transaction base
        before=deepcopy((session.masses,session.energies,session.counters,session.network.parameters,session.revision))
        controllers=deepcopy(session.controllers)
        scripts={iid:deepcopy((s.state,s.samples,s.next_s,s.pending)) for iid,s in session.scripts.items()}
        with pytest.raises(SolveFailed,match='commit fault'): session.advance()
        assert (session.masses,session.energies,session.counters,session.network.parameters,session.revision)==before
        assert session.controllers==controllers
        assert {iid:(s.state,s.samples,s.next_s,s.pending) for iid,s in session.scripts.items()}==scripts
        assert session.time==.1 and session.frames[-1].time_s==.1
        assert session.runners['EV1'].state['accepted_segments']==1
    finally:
        session.close()


def test_evaluate_mutation_cannot_advance_author_state():
    source=throttle_module().source['runtime'].replace("opening = number(ctx.parameter('opening_ratio'))",
        "ctx.state['accepted_segments'] += 1000\n        opening = number(ctx.parameter('opening_ratio'))")
    session=probe(source)
    try:
        session.initialize()
        assert session.runners['EV1'].state['accepted_segments']==0
        session.advance()
        assert session.runners['EV1'].state['accepted_segments']==1
    finally:
        session.close()


def test_adaptive_and_other_device_roles_remain_outside_probe():
    project=station_example();project.solver.time_step.enabled=True
    with pytest.raises(ValueError,match='自适应'): compile_probe(project,{'EV1':throttle_module()})
    with pytest.raises(ValueError,match='只替换'): compile_probe(station_example(),{'K1':throttle_module()})


@pytest.mark.parametrize('fault',['port','unit','hash'])
def test_probe_rejects_incompatible_contracts(fault):
    from fn_engine.models import Domain, UnitSpec
    module=throttle_module()
    if fault=='port':module.ports[0].domain=Domain.fluid
    elif fault=='unit':module.parameters[0].unit=UnitSpec(quantity='pressure',canonical_unit='Pa',display_unit='Pa')
    else:module.content_hash='0'*64
    with pytest.raises(ValueError):compile_probe(station_example(),{'EV1':module})


def test_timeout_terminates_worker_and_retains_accepted_state():
    source=throttle_module().source['runtime'].replace('import math','import math\nimport time').replace(
        "inlet, outlet = ctx.port('in0'), ctx.port('out0')",
        "if ctx.time_s > 0: time.sleep(1)\n        inlet, outlet = ctx.port('in0'), ctx.port('out0')")
    session=probe(source)
    try:
        session.initialize();runner=session.runners['EV1'];process=runner.process;runner.timeout_s=.05
        with pytest.raises(SolveFailed): session.advance()
        assert process.poll() is not None
        assert session.time==0. and runner.state['accepted_segments']==0
    finally:
        session.close()


def test_sync_failure_is_after_acceptance_and_keeps_new_frame(monkeypatch):
    session=probe()
    try:
        session.initialize();runner=session.runners['EV1'];original=runner.synchronize_state
        def kill_on_sync(candidate):
            runner.process.kill();runner.process.wait(timeout=5)
            return original(candidate)
        monkeypatch.setattr(runner,'synchronize_state',kill_on_sync)
        with pytest.raises(SolveFailed) as failure: session.advance()
        assert failure.value.diagnostic.code=='MODULE_SYNC_FAILED'
        assert session.time==.1 and runner.state['accepted_segments']==1
        assert session.frames[-1].time_s==.1
        assert session.frames[-1].variables['EV1.state.accepted_segments']==1
    finally:
        session.close()


def test_experiment_does_not_open_public_compiler_or_claim_a_steady_solver():
    network=compile_probe(station_example(),{'EV1':throttle_module()})
    with pytest.raises(CompilationError) as error: compile_project(network.project)
    assert error.value.diagnostic.code=='REFRIGERATION_MODEL_UNSUPPORTED'
    with pytest.raises(CompilationError) as error: solve_steady(compile_project(station_example()))
    assert error.value.diagnostic.code=='REFRIGERATION_DYNAMIC_REQUIRED'
