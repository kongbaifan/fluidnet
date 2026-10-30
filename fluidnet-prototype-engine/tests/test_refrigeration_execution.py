"""Formal refrigeration module execution: conservation, temporal identity and whole-segment acceptance."""
from copy import deepcopy

import pytest

from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.examples import station_case, station_example
from fn_engine.refrigeration.station import StationSession
from fn_engine.solver import SolveFailed
from test_refrigeration_modules import definition, SOURCE


def pair(adaptive=False, source=SOURCE):
    original=station_case()
    original.solver.time_step.enabled=adaptive
    changed=original.model_copy(deep=True)
    module=definition(source);changed.modules.append(module)
    next(i for i in changed.instances if i.id=='EV1').module_id=module.id
    return original,changed


@pytest.mark.parametrize('adaptive',[False,True])
def test_formal_station_matches_builtin_with_controls_and_caches_observations(adaptive):
    original,changed=pair(adaptive)
    sessions=[StationSession(compile_project(p),20.,10.) for p in [original,changed]]
    try:
        for session in sessions:session.initialize()
        for _ in range(2):
            a,b=[session.advance() for session in sessions]
            for name in ['masses','energies','temperatures']:
                assert getattr(sessions[0],name)==pytest.approx(getattr(sessions[1],name),rel=1e-10,abs=1e-8)
            assert a.metrics['energy_residual_j']==pytest.approx(b.metrics['energy_residual_j'],abs=1e-6)
            assert b.variables['EV1.in0.enthalpy_j_kg']==b.variables['EV1.out0.enthalpy_j_kg']
        session=sessions[1];runner=session.runners['EV1'];calls=runner.request_count
        session.snapshot();session.snapshot()
        assert runner.request_count==calls
        assert runner.state['accepted_segments']==2
        assert b.variables['EV1.state.transferred_mass_kg']>0
        assert all(abs(b.metrics[f'mass_residual_kg_circuit{i}'])<1e-8 for i in [0,1])
    finally:
        for session in sessions:session.close()


def test_fixed_failure_halving_uses_true_substep_mass_and_one_module_accept(monkeypatch):
    _,project=pair();session=StationSession(compile_project(project),.1,.1)
    try:
        session.initialize();solve=session._solve;accepted=[];times=[]
        runner=session.runners['EV1'];invoke=runner.evaluate_refrigeration
        def trace(request):
            times.append(request.time_s);return invoke(request)
        monkeypatch.setattr(runner,'evaluate_refrigeration',trace)
        def fail_large(x,h):
            result=solve(x,h)
            if h>.075:raise devices.DeviceRangeError('REFRIGERATION_NOT_CONVERGED','retry')
            accepted.append((h,result[1]['devices']['EV1']['mass_flow_kg_s']))
            return result
        monkeypatch.setattr(session,'_solve',fail_large)
        frame=session.advance()
        assert len(accepted)==2
        assert .05 in times and .1 in times
        assert frame.variables['EV1.state.transferred_mass_kg']==pytest.approx(sum(h*m for h,m in accepted),abs=1e-12)
        assert runner.state['accepted_segments']==1
    finally:session.close()


@pytest.mark.parametrize('adaptive',[False,True])
def test_commit_failure_rolls_back_physics_pid_script_and_mass_ledger(adaptive):
    source=SOURCE.replace("ctx.state['accepted_segments'] = count+1",
        "ctx.state['accepted_segments'] = count+1\n        if ctx.time_s > .15: raise ValueError('commit failed')")
    _,project=pair(adaptive,source)
    for c in project.controllers:c.sample_s=.1
    for c in project.control_scripts:c.sample_s=.1
    session=StationSession(compile_project(project),.2,.1)
    try:
        session.initialize();session.advance();session.set_parameter('ROOM1','heat_input_w',16000.)
        before=deepcopy((session.masses,session.energies,session.counters,session.network.parameters,session.controllers,session.revision))
        script=deepcopy(session.scripts['control'].state)
        with pytest.raises(SolveFailed,match='commit failed'):session.advance()
        assert (session.masses,session.energies,session.counters,session.network.parameters,session.controllers,session.revision)==before
        assert session.scripts['control'].state==script
        assert session.time==.1 and session.frames[-1].time_s==.1
        assert session.runners['EV1'].state['accepted_segments']==1
    finally:session.close()


def test_second_module_failure_does_not_promote_first_candidate():
    module=definition(SOURCE.replace("ctx.state['accepted_segments'] = count+1",
        "ctx.state['accepted_segments'] = count+1\n        if ctx.execution.instance_id == 'EV2': raise ValueError('second module')"))
    p=station_example();p.modules.append(module)
    next(i for i in p.instances if i.id=='EV1').module_id=module.id
    p.instances.extend([ModuleInstance(id='VH',name='Liquid header',module_id='refrigerant_header'),
                        ModuleInstance(id='EV2',name='Second throttle',module_id=module.id,parameters={'opening_ratio':.4})])
    p.connections=[c for c in p.connections if c.id!='v1']
    for identifier,a,ap,b,bp in [('vh0','HP1','liquid','VH','in0'),('vh1','VH','out0','EV1','in0'),
                               ('vh2','VH','out1','EV2','in0'),('vh3','EV2','out0','RH1','in2')]:
        p.connections.append(Connection(id=identifier,source=Endpoint(instance_id=a,port_id=ap),target=Endpoint(instance_id=b,port_id=bp)))
    s=StationSession(compile_project(p),.1,.1)
    try:
        s.initialize();before=deepcopy(s.masses)
        with pytest.raises(SolveFailed,match='second module'):s.advance()
        assert s.masses==before and s.time==0
        assert all(r.state['accepted_segments']==0 and r.state_revision==0 for r in s.runners.values())
    finally:s.close()


def test_post_accept_sync_failure_keeps_new_frame_and_never_repeats_callback(monkeypatch):
    _,p=pair();s=StationSession(compile_project(p),.2,.1)
    try:
        s.initialize();runner=s.runners['EV1'];sync=runner.synchronize_state
        def broken(candidate):
            runner.process.kill();runner.process.wait(timeout=5);return sync(candidate)
        monkeypatch.setattr(runner,'synchronize_state',broken)
        with pytest.raises(SolveFailed) as error:s.advance()
        assert error.value.diagnostic.code=='MODULE_SYNC_FAILED'
        assert s.time==.1 and s.frames[-1].time_s==.1
        assert runner.state['accepted_segments']==1
        assert s.frames[-1].variables['EV1.state.transferred_mass_kg']>0
        with pytest.raises(StopIteration):s.advance()
        assert runner.state['accepted_segments']==1
    finally:s.close()


def test_adaptive_rejection_integrates_only_the_accepted_two_half_steps(monkeypatch):
    from fn_engine.timestep import ErrorEstimate
    _,p=pair(True);s=StationSession(compile_project(p),.1,.1)
    try:
        s.initialize();estimate=s._error_estimate;trials=[];calls=0
        def reject_once(*args):
            nonlocal calls
            calls+=1
            return ErrorEstimate(4.) if calls==1 else estimate(*args)
        monkeypatch.setattr(s,'_error_estimate',reject_once)
        trial=s._trial_doubling
        def record(x,h):
            payload,error=trial(x,h)
            if payload is not None:trials.append(payload['counters'][('EV1','transferred_mass_kg')])
            return payload,error
        monkeypatch.setattr(s,'_trial_doubling',record)
        frame=s.advance()
        assert s.step_stats.rejected==1 and len(trials)>=2
        assert frame.variables['EV1.state.transferred_mass_kg']==pytest.approx(sum(trials),abs=1e-12)
        assert s.runners['EV1'].state['accepted_segments']==1
    finally:s.close()


@pytest.mark.parametrize('adaptive',[False,True])
def test_schedule_and_control_boundaries_preserve_last_accepted_segment_on_later_failure(adaptive):
    from fn_engine.models import ScheduleEvent
    source=SOURCE.replace("ctx.state['accepted_segments'] = count+1",
        "ctx.state['accepted_segments'] = count+1\n        if ctx.time_s > .075: raise ValueError('later segment')")
    _,p=pair(adaptive,source)
    p.controllers=[];p.control_scripts=[]
    p.events=[ScheduleEvent(id='close_valve',type='set_variable',time_s=.05,key='EV1.param.opening_ratio',value=0.)]
    s=StationSession(compile_project(p),.1,.1)
    try:
        s.initialize();opening=s.network.parameters['EV1']['opening_ratio']
        with pytest.raises(SolveFailed,match='later segment') as failure:s.advance()
        assert s.time==.05 and failure.value.frames[-1].time_s==.05
        assert s.event_index==0 and s.events_applied==0
        assert s.network.parameters['EV1']['opening_ratio']==opening
        assert s.runners['EV1'].state['accepted_segments']==1
        assert failure.value.frames[-1].variables['EV1.state.transferred_mass_kg']>0
        assert s.closed
    finally:s.close()


def test_stop_closes_workers_and_prevents_further_evaluation():
    _,p=pair();s=StationSession(compile_project(p),1.,.1)
    s.initialize();s.advance();s.close()
    calls={iid:r.request_count for iid,r in s.runners.items()}
    with pytest.raises(StopIteration):s.advance()
    assert calls=={iid:r.request_count for iid,r in s.runners.items()}
    assert all(r.process is None or r.process.poll() is not None for r in s.runners.values())


@pytest.mark.parametrize('fault',["raise ValueError('failed evaluation')", "ctx.refrigeration.flow(mass_flow_kg_s=float('nan'),effective_kv_m3_h=0.)",
    "__import__('time').sleep(.5)","__import__('os')._exit(7)"])
def test_worker_evaluation_failure_keeps_accepted_physics_and_reclaims_process(fault):
    source=SOURCE.replace('point = ctx.refrigeration.throttle',
        f'if ctx.time_s > .15: {fault}\n        point = ctx.refrigeration.throttle')
    _,p=pair(source=source);s=StationSession(compile_project(p),.2,.1)
    try:
        s.initialize();s.advance();runner=s.runners['EV1'];runner.timeout_s=.1
        before=deepcopy((s.masses,s.energies,s.temperatures,s.counters,runner.state,runner.state_revision))
        with pytest.raises(SolveFailed) as failure:s.advance()
        assert before==(s.masses,s.energies,s.temperatures,s.counters,runner.state,runner.state_revision)
        assert s.time==.1 and failure.value.frames[-1].time_s==.1
        assert failure.value.diagnostic.instance_id=='EV1'
        assert s.closed and (runner.process is None or runner.process.poll() is not None)
    finally:s.close()
