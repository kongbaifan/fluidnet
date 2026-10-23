"""W1/W2：Worker 冷启动诊断与生命周期专项测试。

覆盖：启动报告（--startup-report 与 startup_report 动作）、惰性物性导入、设计函数、
批量/独立 Worker、超时、异常、关闭与进程残留；同时锁定旧错误消息与控制预览行为。
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil
import pytest

from fn_engine.models import (
    ChannelSpec, ControlScript, EvaluateRequest, FluidConfig, ModuleDefinition, ParameterSpec, PortSpec, PortState,
)
from fn_engine.packages import load_module_package
from fn_engine.runtime import ModuleRuntimeTimeout, RuntimeErrorBase, WorkerProcess, module_content_hash

ROOT = Path(__file__).resolve().parents[1]
WORKER = 'fn_engine.worker'


def backend_env():
    env = os.environ.copy()
    extra = str(ROOT / 'backend')
    env['PYTHONPATH'] = extra + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def valve_module():
    return load_module_package(ROOT / 'modules' / 'programmable_valve')


def valve_parameters(module):
    return {parameter.id: parameter.default for parameter in module.parameters}


PORTS = [PortSpec(id='in0', label='in0', direction='in'), PortSpec(id='out0', label='out0', direction='out')]


def custom_module(source, module_id='probe', parameters=()):
    return ModuleDefinition(
        id=module_id, name=module_id, runtime='python', entrypoint='module:Module', solver_model='python_x',
        source={'runtime': source}, ports=PORTS, parameters=list(parameters),
        channels=[ChannelSpec(id='main', name='main', input_port='in0', output_port='out0',
                              relation='resistance', solver_model='python_x')])


def define(source, module_id='probe'):
    return custom_module(source, module_id, [ParameterSpec(id='kv_m3_h', label='kv', default=16.0)])


VALVE_SOURCE = '''class Module:
    def evaluate(self, ctx):
        ctx.net.valve(channel="main", kv=16.0, opening=0.8)
'''

SLOW_SOURCE = '''class Module:
    def evaluate(self, ctx):
        import time
        time.sleep(0.6)
        ctx.net.valve(channel="main", kv=16.0, opening=0.8)
'''

FAIL_SOURCE = '''class Module:
    def evaluate(self, ctx):
        raise TypeError("boom")
'''

DESIGN_SOURCE = {
    'runtime': VALVE_SOURCE,
    'design': 'def design(ctx):\n    ctx.set("kv_m3_h", 20.0)\n    ctx.log("design-ran")\n',
}


# ---------------------------------------------------------------- 进程残留


def child_pids():
    try:
        return {child.pid for child in psutil.Process().children(recursive=True)}
    except psutil.Error:
        return set()


def wait_for_no_children(timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not child_pids():
            return True
        time.sleep(0.02)
    return not child_pids()


@pytest.fixture(autouse=True)
def no_leftover_workers():
    before = child_pids()
    yield
    wait_for_no_children()
    assert child_pids() <= before, f'测试后仍有 Worker 子进程：{child_pids() - before}'


# ---------------------------------------------------------------- 启动报告与惰性导入


@pytest.mark.numerics_fast
def test_startup_report_action_reports_import_budget():
    completed = subprocess.run(
        [sys.executable, '-m', WORKER, '--startup-report'],
        input='{"action": "startup_report"}\n{"action": "finalize"}\n',
        capture_output=True, text=True, timeout=120, cwd=str(ROOT), env=backend_env())
    assert completed.returncode == 0, completed.stderr[-2000:]
    lines = [line for line in completed.stdout.splitlines() if line.startswith('{')]
    reports = [json.loads(line) for line in lines]
    report = next(item for item in reports if 'module_import_s' in item)
    assert report['module_import_s'] >= 0.0
    assert report['properties_imported'] is False
    assert report['first_request_uptime_s'] is not None
    assert any(line.startswith('FN_STARTUP ') for line in completed.stderr.splitlines())


@pytest.mark.numerics_fast
def test_control_worker_does_not_import_properties():
    script = ControlScript(id='control', enabled=True, source='def initialize(ctx):\n    ctx.state["n"] = 0\n'
                          'def step(ctx, dt_s):\n    ctx.state["n"] += 1\n'
                          'def finalize(ctx):\n    pass\n')
    worker = WorkerProcess(ModuleDefinition(id=script.id, name=script.id), {}, FluidConfig())
    try:
        response = worker._request({'action': 'control_initialize', 'definition': script.model_dump(mode='json'),
                                    'values': {}})
        assert response['state'] == {'n': 0}
        report = worker._request({'action': 'startup_report'})
        assert report['properties_imported'] is False
        assert report['probe_refprop'] is None
        step = worker._request({'action': 'control_step', 'values': {}, 'state': {'n': 0}, 'time_s': 0., 'dt_s': .1})
        assert step['state'] == {'n': 1}
    finally:
        worker.close()
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_module_worker_keeps_probe_skip_and_imports_properties_on_demand():
    module = valve_module()
    worker = WorkerProcess(module, valve_parameters(module), FluidConfig())
    try:
        worker.initialize()
        report = worker._request({'action': 'startup_report'})
        # 惰性导入：initialize 不访问 ctx.fluid 时不应导入 CoolProp。
        assert report['properties_imported'] is False
        # programmable_valve 在试算端口缺密度时会查一次物性，把导入推迟到这一刻。
        request = EvaluateRequest(run_id='worker', instance_id=module.id, iteration_id=0, time_s=0.,
                                  trial_ports={'in0': PortState(pressure_pa=250000., temperature_k=293.15)},
                                  readonly_state={})
        worker.evaluate(request)
        report = worker._request({'action': 'startup_report'})
        assert report['properties_imported'] is True
        # v0.5.0 语义保留：Worker 进程跳过 REFPROP 预探测。
        assert report['probe_refprop'] is False
    finally:
        worker.close()
    assert wait_for_no_children()


# ---------------------------------------------------------------- 生命周期


def evaluate_request(instance_id='probe'):
    return EvaluateRequest(run_id='worker', instance_id=instance_id, iteration_id=0, time_s=0., trial_ports={},
                           readonly_state={}).model_dump(mode='json')


def initialize_message(module, instance_id='probe'):
    return {'action': 'initialize', 'definition': module.model_dump(mode='json'),
            'request': {'run_id': 'worker', 'instance_id': instance_id,
                        'package': {'module_id': module.id, 'version': f'{module.version}.0.0',
                                    'content_hash': module_content_hash(module)},
                        'parameters': {}, 'fluid': FluidConfig().model_dump(mode='json'), 'initial_state': {}}}


@pytest.mark.numerics_fast
def test_batch_worker_keeps_items_independent():
    module = custom_module(VALVE_SOURCE, module_id='batch-probe')
    worker = WorkerProcess(module, {}, FluidConfig())
    try:
        batch = {'action': 'batch',
                 'items': {f'k{i}': initialize_message(module, instance_id=f'inst{i}') for i in range(3)}}
        response = worker._request(batch)
        assert set(response) == {'k0', 'k1', 'k2'}
        assert all(value.get('state') == {} for value in response.values())
        evaluate = {'action': 'batch',
                    'items': {f'k{i}': {'action': 'evaluate', 'request': evaluate_request(f'inst{i}')}
                              for i in range(3)}}
        result = worker._request(evaluate)
        assert set(result) == {'k0', 'k1', 'k2'}
        assert all('relations' in value for value in result.values())
    finally:
        worker.close(force=True)
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_worker_reuses_process_across_requests():
    module = custom_module(VALVE_SOURCE, module_id='reuse-probe')
    worker = WorkerProcess(module, {}, FluidConfig())
    try:
        worker.initialize()
        first = worker.process.pid
        worker.evaluate(EvaluateRequest(run_id='worker', instance_id='probe', iteration_id=1, time_s=.1,
                                        trial_ports={}, readonly_state={}))
        assert worker.process.pid == first
        assert worker.request_count >= 2
    finally:
        worker.close()
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_design_function_runs_in_dedicated_lifecycle():
    module = define(VALVE_SOURCE)
    module.source = DESIGN_SOURCE
    worker = WorkerProcess(module, {}, FluidConfig())
    try:
        response = worker._request({'action': 'design', 'definition': module.model_dump(mode='json'),
                                    'parameters': {'kv_m3_h': 16.0},
                                    'fluid': FluidConfig().model_dump(mode='json')})
        assert response['outputs'] == {'kv_m3_h': 20.0}
        assert response['diagnostics'][0]['code'] == 'DESIGN_LOG'
    finally:
        worker.close()
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_worker_timeout_terminates_process_without_residue():
    module = custom_module(SLOW_SOURCE, module_id='slow-probe')
    worker = WorkerProcess(module, {}, FluidConfig(), timeout_s=30)
    try:
        worker.initialize()
        # 初始化本身要 import Worker，不能用 0.15 s 的短超时；只对慢 evaluate 用短超时。
        worker.timeout_s = .15
        with pytest.raises(ModuleRuntimeTimeout):
            worker.evaluate(EvaluateRequest(run_id='worker', instance_id='probe', iteration_id=0, time_s=0.,
                                            trial_ports={}, readonly_state={}))
        assert worker.process is None
    finally:
        worker.close(force=True)
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_worker_exception_keeps_old_code_and_worker_usable():
    module = custom_module(FAIL_SOURCE, module_id='fail-probe')
    worker = WorkerProcess(module, {}, FluidConfig())
    try:
        worker.initialize()
        with pytest.raises(RuntimeErrorBase) as error:
            worker.evaluate(EvaluateRequest(run_id='worker', instance_id='probe', iteration_id=0, time_s=0.,
                                            trial_ports={}, readonly_state={}))
        assert error.value.code == 'MODULE_RUNTIME_ERROR'
        assert 'boom' in str(error.value)
    finally:
        worker.close()
    # 未 initialize 的独立 Worker：evaluate 仍返回旧错误消息，并且进程在 finally 里被关闭。
    uninitialized = WorkerProcess(module, {}, FluidConfig())
    try:
        with pytest.raises(RuntimeErrorBase, match='Worker 尚未初始化'):
            uninitialized._request({'action': 'evaluate', 'request': evaluate_request()})
    finally:
        uninitialized.close(force=True)
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_close_is_idempotent_and_unknown_action_message_unchanged():
    module = valve_module()
    worker = WorkerProcess(module, valve_parameters(module), FluidConfig())
    worker.initialize()
    with pytest.raises(RuntimeErrorBase, match='未知 Worker 操作'):
        worker._request({'action': 'nope'})
    worker.close()
    worker.close(force=True)
    assert worker.process is None
    assert wait_for_no_children()


@pytest.mark.numerics_fast
def test_control_preview_response_unchanged(tmp_path):
    from fastapi.testclient import TestClient

    from fn_engine.api import create_app
    from test_controls_storage import controlled

    project = controlled()
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/controls/preview',
                               json={'project': project.model_dump(mode='json'),
                                     'script': project.control_scripts[0].model_dump(mode='json')})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['writes'] == {'V1.param.opening_ratio': .5}
        assert body['state'] == {'count': 1}
        assert body['applied'] is False
        assert len(body['content_hash']) == 64
