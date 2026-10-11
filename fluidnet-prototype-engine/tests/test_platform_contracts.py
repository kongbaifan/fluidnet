import time
import os
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import (
    Connection,
    Endpoint,
    FluidConfig,
    ModuleDefinition,
    ModuleInstance,
    Project,
    PortSpec,
    ChannelSpec,
    ParameterSpec,
)
from fn_engine.packages import load_module_package
from fn_engine.properties import property_service
from fn_engine.solver import solve_steady, solve_dynamic
from fn_engine.runtime import WorkerProcess, RuntimeErrorBase, ModuleRuntimeTimeout
from fn_engine.models import EvaluateRequest, CommitStepRequest, ChannelState
from fn_engine.bridge import normalize_prototype_export


ROOT = Path(__file__).parents[1]


def custom_module():
    return load_module_package(ROOT / "modules" / "programmable_valve")


def custom_project():
    catalog = catalog_map()
    module = custom_module()
    return Project(
        id="custom-valve-project",
        name="可编程阀门验收",
        modules=[catalog["source"], module],
        instances=[
            ModuleInstance(id="B1", module_id="source", name="入口", parameters={"pressure_pa": 250000.0}),
            ModuleInstance(id="V1", module_id=module.id, name="可编程阀", parameters={"opening_ratio": 0.5, "kv_m3_h": 10.0}),
            ModuleInstance(id="B2", module_id="source", name="出口", parameters={"pressure_pa": 120000.0}),
        ],
        connections=[
            Connection(id="e1", source=Endpoint(instance_id="B1", port_id="out0"), target=Endpoint(instance_id="V1", port_id="in0")),
            Connection(id="e2", source=Endpoint(instance_id="V1", port_id="out0"), target=Endpoint(instance_id="B2", port_id="out0")),
        ],
    )


def test_coolprop_service_supports_single_phase_water_and_air():
    water = property_service(FluidConfig(fluid="Water", phase_policy="liquid")).state_pt(250000, 293.15)
    air = property_service(FluidConfig(fluid="Air", phase_policy="gas")).state_pt(250000, 293.15)
    assert water.density_kg_m3 > 900
    assert water.viscosity_pa_s > 0
    assert air.density_kg_m3 > 1
    assert "gas" in air.phase


def test_versioned_python_package_runs_in_worker_and_commits_once():
    module = custom_module()
    client = TestClient(create_app())
    response = client.post("/api/v1/modules/test", json={
        "module": module.model_dump(mode="json"),
        "parameters": {"opening_ratio": 0.5, "kv_m3_h": 10.0},
    })
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content_hash"] == module.content_hash
    assert body["evaluation"]["relations"][0]["kind"] == "valve"
    assert body["committed"]["state"]["commit_count"] == 1


def test_module_catalog_discovers_versioned_package():
    response = TestClient(create_app()).get("/api/v1/modules")
    assert response.status_code == 200
    item = next(module for module in response.json()["modules"] if module["id"] == "programmable_valve")
    assert item["runtime"] == "python"
    assert len(item["package"]["content_hash"]) == 64


def test_python_module_relation_is_used_by_network_solver():
    frame = solve_steady(compile_project(custom_project()))
    assert frame.valid
    assert frame.variables["V1.mass_flow_kg_s"] > 0
    assert frame.variables["V1.param.opening_ratio"] == pytest.approx(0.5)


def test_module_default_is_not_overwritten_by_registered_builtin():
    module = custom_module().model_copy(update={
        "definition_hash": None,
        "parameters": [ParameterSpec(id="opening_ratio", label="开度", default=0.25, minimum=0, maximum=1),
                        ParameterSpec(id="kv_m3_h", label="Kv", default=20.0, minimum=.001)]
    })
    project = custom_project()
    project.modules[-1] = module
    project.instances[1].parameters = {}
    compiled = compile_project(project)
    assert compiled.parameters["V1"]["opening_ratio"] == pytest.approx(0.25)
    assert compiled.parameters["V1"]["kv_m3_h"] == pytest.approx(20.0)


def test_dynamic_background_run_is_queryable():
    client = TestClient(create_app())
    response = client.post("/api/v1/runs?background=true", json={
        "project": custom_project().model_dump(mode="json"),
        "mode": "dynamic",
        "duration_s": 0.2,
        "dt_s": 0.1,
    })
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(250):
        status = client.get(f"/api/v1/runs/{run_id}").json()
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(0.02)
    assert status["status"] == "completed", status
    assert client.get(f"/api/v1/runs/{run_id}/events").json()["events"]


def test_dynamic_worker_commits_only_accepted_steps_and_partial_dt():
    frames = solve_dynamic(compile_project(custom_project()), .25, .1)
    assert [f.variables['V1.state.commit_count'] for f in frames] == [0, 1, 2, 3]
    q = frames[-1].variables['V1.mass_flow_kg_s']
    assert frames[-1].variables['V1.state.throughput_kg'] == pytest.approx(abs(q) * .25)


def test_worker_is_separate_process_and_cleans_up_after_failure(monkeypatch):
    import fn_engine.solver as solver
    processes = []
    original_initialize = WorkerProcess.initialize
    def track(runner):
        result = original_initialize(runner)
        processes.append(runner.process)
        return result
    monkeypatch.setattr(WorkerProcess, 'initialize', track)
    project = custom_project()
    module = project.modules[-1]
    module.content_hash = None
    module.definition_hash = None
    module.source['runtime'] = module.source['runtime'].replace('        inlet = ctx.port("in0")',
        '        import os\n        ctx.var("pid", os.getpid())\n        print("中文单位 kg/m³")\n        inlet = ctx.port("in0")')
    frame = solve_steady(compile_project(project))
    assert frame.variables['V1.pid'] != os.getpid()
    assert processes[-1].poll() is not None
    module.source['runtime'] = module.source['runtime'].replace('        inlet = ctx.port("in0")', '        raise ValueError("测试模块失败")')
    with pytest.raises(RuntimeErrorBase, match='测试模块失败'):
        solver.solve_steady(compile_project(project))
    assert processes[-1].poll() is not None


def test_worker_evaluate_cannot_commit_nested_state_and_timeout_terminates():
    module = custom_module()
    module.content_hash = None
    module.definition_hash = None
    module.source['runtime'] = '''class Module:
    def initialize(self, ctx):
        ctx.state['nested'] = {'count': 0}
    def evaluate(self, ctx):
        ctx.state['nested']['count'] += 1
        ctx.var('trial', ctx.state['nested']['count'])
    def commit_step(self, ctx, dt_s):
        ctx.state['nested']['count'] += 1
'''
    runner = WorkerProcess(module, {}, FluidConfig())
    try:
        runner.initialize()
        request = EvaluateRequest(run_id='test',instance_id='D1',iteration_id=0,time_s=0)
        assert runner.evaluate(request).variables['trial'] == 1
        assert runner.evaluate(request).variables['trial'] == 1
        assert runner.state['nested']['count'] == 0
        committed = runner.commit_step(CommitStepRequest(run_id='test',instance_id='D1',time_s=.1,dt_s=.1))
        assert committed.state['nested']['count'] == 1
    finally:
        runner.close()
    module.source['runtime'] = 'import time\nclass Module:\n    def evaluate(self, ctx):\n        time.sleep(60)\n'
    runner = WorkerProcess(module, {}, FluidConfig())
    runner.initialize()
    process = runner.process
    runner.timeout_s = .1
    with pytest.raises(ModuleRuntimeTimeout):
        runner.evaluate(request)
    assert process.poll() is not None
    assert runner.process is None


def test_module_bench_solves_flow_before_committing_and_rejects_bad_parameters():
    client = TestClient(create_app())
    payload = {'module':custom_module().model_dump(mode='json'), 'duration_s':.25,'dt_s':.1}
    response = client.post('/api/v1/modules/test',json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body['history']) == 4
    assert body['committed']['state']['commit_count'] == 3
    assert body['committed']['state']['throughput_kg'] == pytest.approx(body['frame']['variables']['D1.mass_flow_kg_s'] * .25)
    assert body['state']['commit_count'] == 0
    response = client.post('/api/v1/modules/test',json={**payload,'parameters':{'opening_ratio':2}})
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'PARAMETER_RANGE'


def test_prototype_normalizes_versioned_package_without_builtin_bindings():
    module = custom_module().model_dump(mode='json')
    prototype = {'format':'fluidnet-studio-prototype','activeProject':'test','modules':[{'id':'source','kind':'source'},module],
        'projects':[{'id':'test','name':'包验收','pages':[{'id':'main','nodes':[
            {'id':'B1','moduleId':'source','params':{'pressure':250}},
            {'id':'V1','moduleId':module['id'],'params':{'opening_ratio':.5,'kv_m3_h':10}},
            {'id':'B2','moduleId':'source','params':{'pressure':120}}],
            'edges':[['e1','B1','out0','V1','in0'],['e2','V1','out0','B2','out0']]}]}]}
    project = normalize_prototype_export(prototype)
    assert project.modules[-1].runtime == 'python'
    assert project.modules[-1].content_hash == module['content_hash']
    assert solve_steady(compile_project(project)).valid


@pytest.mark.parametrize('source,expected',[
    ('ctx.net.compressor(channel="main", forced_mass_flow_kg_s=0.7)',.7),
    ('ctx.net.valve(channel="main", kv=10, opening=0)',0),
])
def test_python_module_can_use_generic_model_and_sdk_flow_constraints(source,expected):
    project = custom_project()
    module = project.modules[-1]
    module.solver_model = 'generic'
    module.content_hash = None
    module.definition_hash = None
    module.parameters = []
    module.channels[0].solver_model = 'generic'
    module.source['runtime'] = 'class Module:\n    def evaluate(self, ctx):\n        '+source+'\n'
    project.instances[1].parameters = {}
    frame = solve_steady(compile_project(project))
    assert frame.variables['V1.mass_flow_kg_s'] == pytest.approx(expected,abs=1e-9)


def test_missing_python_relation_is_a_runtime_error():
    project=custom_project()
    project.modules[-1].content_hash=None
    project.modules[-1].definition_hash=None
    project.modules[-1].source['runtime']='class Module:\n    def evaluate(self, ctx):\n        pass\n'
    result=TestClient(create_app()).post('/api/v1/runs',json={'project':project.model_dump(mode='json')}).json()
    assert result['status']=='failed'
    assert result['frame']['diagnostics'][0]['code']=='MODULE_RUNTIME_ERROR'
