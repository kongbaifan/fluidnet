"""S3 real network scopes, retries, per-shard identity and accepted-time provenance."""
import json
import math

import pytest

from fn_engine.bench import run_module_test
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance, ModuleTestRequest, Project
from fn_engine.runtime import RuntimeErrorBase
from fn_engine.simulation import SimulationSession
from fn_engine.solver import RHO_WATER
from test_module_execution import ROOT, probe_definition


def network_for(module, count=1, *, batch=True, parallelism=1, node=False):
    instances = [ModuleInstance(id='B1',module_id='source',name='入口',parameters={'pressure_pa':250000.})]
    instances += [ModuleInstance(id=f'D{index}',module_id=module.id,name=f'Device {index}') for index in range(1,count+1)]
    instances += [ModuleInstance(id='B2',module_id='source',name='出口',parameters={'pressure_pa':120000.})]
    edges = [('B1','out0','D1','in0')]
    edges += [(f'D{index}','out0',f'D{index+1}','in0') for index in range(1,count)]
    edges += [(f'D{count}','out0','B2','out0')]
    project = Project(id='execution-network', name='Execution network',modules=[catalog_map()['source'],module],
        instances=instances,connections=[Connection(id=f'e{index}',source=Endpoint(instance_id=a,port_id=ap),
            target=Endpoint(instance_id=b,port_id=bp)) for index,(a,ap,b,bp) in enumerate(edges)])
    project.solver.batch_modules = batch
    project.solver.module_parallelism = parallelism
    project.solver.thermal = node
    project.solver.property_coupling = 'node' if node else 'reference'
    return compile_project(project)


def records(path, instance='D1'):
    return [json.loads(line) for line in (path/f'{instance}.jsonl').read_text(encoding='utf-8').splitlines()]


@pytest.mark.parametrize('batch,count,parallelism,node', [
    (False,1,1,False), (False,2,1,False), (True,2,1,False), (True,2,2,False), (True,2,2,True),
])
def test_session_scopes_are_shared_across_residuals_instances_and_coupling_passes(tmp_path,batch,count,parallelism,node):
    session = SimulationSession(network_for(probe_definition(tmp_path),count,batch=batch,
        parallelism=parallelism,node=node),duration_s=1.,dt_s=.5)
    try:
        session.initialize()
        session.advance()
        session.advance()
        assert session.time == 1.
    finally:
        session.close()
    all_records = []
    time_steps = {}
    for index in range(1,count+1):
        instance = f'D{index}'
        rows = records(tmp_path,instance)
        all_records.extend(rows)
        assert all(row['instance_id']==instance for row in rows)
        assert rows[0]['phase']=='initialize' and rows[0]['step_id'] is None
        assert rows[-1]['phase']=='finalize' and rows[-1]['time_s']==1.
        assert rows[-1]['accepted_time_s']==1.
        for row in rows:
            if row['phase'] not in {'evaluate','commit_step'}:
                continue
            time_steps.setdefault(row['time_s'],set()).add(row['step_id'])
            if row['phase']=='evaluate':
                assert row['port_data']=='trial' and row['channel_data']=='unavailable'
                assert row['iteration_id'] is not None and row['state_data']=='input_copy'
            else:
                assert row['port_data']==row['channel_data']=='converged'
                assert row['state_data']=='candidate' and row['iteration_id'] is None
            expected = None if row['time_s']==0. else row['time_s']-.5
            assert row['accepted_time_s']==expected
        assert [row['time_s'] for row in rows if row['phase']=='commit_step']==[.5,1.]
    assert len({row['run_id'] for row in all_records})==1
    assert len({row['request_id'] for row in all_records})==len(all_records)
    assert set(time_steps)=={0.,.5,1.}
    assert all(len(ids)==1 and None not in ids for ids in time_steps.values())
    assert len(set.union(*time_steps.values()))==3


def test_discarded_same_time_trial_gets_new_identity_and_commit_uses_selected_result(tmp_path):
    session = SimulationSession(network_for(probe_definition(tmp_path)),duration_s=1.,dt_s=.5)
    try:
        session.initialize()
        first = session._trial(.5)
        second = session._trial(.5)
        assert first[1].module_step_id != second[1].module_step_id
        assert session.time==0. and session.runners['D1'].state['commit_count']==0
        session._accept(.5,*first)
        assert session.time==.5
    finally:
        session.close()
    rows = records(tmp_path)
    trials = [row for row in rows if row['phase']=='evaluate' and row['time_s']==.5]
    assert {row['step_id'] for row in trials}=={first[1].module_step_id,second[1].module_step_id}
    assert all(row['accepted_time_s']==0. for row in trials)
    commit = next(row for row in rows if row['phase']=='commit_step')
    assert commit['step_id']==first[1].module_step_id
    assert commit['accepted_time_s']==0.
    assert rows[-1]['accepted_time_s']==.5


@pytest.mark.parametrize('batch', [False,True])
def test_failed_later_module_preserves_all_module_states_and_owner_watermark(tmp_path,batch):
    session = SimulationSession(network_for(probe_definition(tmp_path,fail_on='D2'),2,batch=batch),duration_s=1.,dt_s=.5)
    try:
        session.initialize()
        trial = session._trial(.5)
        with pytest.raises(RuntimeErrorBase,match='injected commit failure'):
            session._accept(.5,*trial)
        assert session.time==0.
        assert all(runner.execution.accepted_time_s==0. for runner in session.runners.values())
        assert session.runners['D1'].state['commit_count']==0
        assert session.runners['D2'].state['commit_count']==0
    finally:
        session.close()
    final1, final2 = records(tmp_path,'D1')[-1], records(tmp_path,'D2')[-1]
    assert final1['time_s']==final2['time_s']==0.
    assert final1['accepted_time_s']==final2['accepted_time_s']==0.
    assert final1['state_data']==final2['state_data']=='module_committed'


def test_bench_postsolve_evaluation_is_labelled_converged_and_final_acceptance_is_visible(tmp_path):
    result = run_module_test(ModuleTestRequest(module=probe_definition(tmp_path),duration_s=1.,dt_s=.5))
    assert result.committed.state['commit_count']==2
    rows = records(tmp_path)
    final_evaluations = [row for row in rows if row['phase']=='evaluate' and row['port_data']=='converged']
    assert [row['time_s'] for row in final_evaluations]==[0.,.5,1.]
    assert all(row['channel_data']=='unavailable' for row in final_evaluations)
    assert rows[-1]['phase']=='finalize' and rows[-1]['accepted_time_s']==1.


def test_typed_time_dependent_equation_uses_current_time_and_commits_only_twice():
    module = probe_definition()
    module.source = {'runtime':(ROOT/'examples/module_sdk/timed_valve.py').read_text(encoding='utf-8')}
    result = run_module_test(ModuleTestRequest(module=module,duration_s=1.,dt_s=.5))
    assert result.committed.state['commit_count']==2
    assert result.evaluation.variables['evaluation_time_s']==1.
    for frame in result.history:
        kv = 10*(1+.1*math.sin(frame.time_s))
        expected = RHO_WATER*kv*.8/3600*math.sqrt(130000/(1e5*RHO_WATER/1000))
        assert frame.variables['D1.main.mass_flow_kg_s']==pytest.approx(expected,rel=1e-6)
