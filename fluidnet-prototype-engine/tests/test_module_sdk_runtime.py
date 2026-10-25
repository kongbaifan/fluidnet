"""S0 integration: public interfaces against real host objects and isolated Workers."""
import inspect
import math
from pathlib import Path

import pytest

import fn_sdk
from fn_engine import models, runtime
from fn_engine.bench import run_module_test
from fn_engine.models import EvaluateRequest, FluidConfig, ModuleTestRequest, PortState
from fn_engine.packages import load_module_package
from fn_engine.properties import CoolPropPropertyService

ROOT = Path(__file__).resolve().parents[1]


def typed_valve():
    module = load_module_package(ROOT / 'modules/programmable_valve')
    return module.model_copy(deep=True, update={
        'source': {'runtime': (ROOT / 'examples/module_sdk/valve.py').read_text(encoding='utf-8')},
        'content_hash': None, 'definition_hash': None,
    })


@pytest.mark.parametrize('public,host', [
    (fn_sdk.ModuleContext, runtime.ModuleContext),
    (fn_sdk.NetworkBuilder, runtime.NetworkBuilder),
    (fn_sdk.PropertyService, CoolPropPropertyService),
])
def test_public_method_signatures_match_current_host(public, host):
    for name, method in vars(public).items():
        if name.startswith('_') or not inspect.isfunction(method):
            continue
        expected = inspect.signature(method).parameters
        actual = inspect.signature(getattr(host, name)).parameters
        assert list(actual) == list(expected), name
        for key, parameter in expected.items():
            assert actual[key].kind == parameter.kind, (name, key)
            assert actual[key].default == parameter.default, (name, key)


@pytest.mark.parametrize('public,host', [
    (fn_sdk.PortState, models.PortState),
    (fn_sdk.ChannelResult, models.ChannelState),
    (fn_sdk.FluidState, models.FluidState),
    (fn_sdk.NetworkRelation, models.NetworkRelation),
    (fn_sdk.Diagnostic, models.Diagnostic),
    (fn_sdk.EvaluateResult, models.EvaluateResponse),
    (fn_sdk.CommitResult, models.CommitStepResponse),
    (fn_sdk.ExecutionInfo, models.ModuleExecutionInfo),
])
def test_public_result_fields_exist_in_host_wire_models(public, host):
    fields = {name for name, value in vars(public).items() if isinstance(value, property)}
    assert fields <= host.model_fields.keys()


@pytest.mark.parametrize('flow', [-1.0, 0.0, 1.0])
def test_typed_worker_callbacks_handle_signed_flow_without_eager_properties(flow):
    module = typed_valve()
    worker = runtime.WorkerProcess(module, {'opening_ratio': .8, 'kv_m3_h': 16.}, FluidConfig())
    try:
        worker.initialize()
        before = worker._request({'action': 'startup_report'})
        assert not before['properties_imported']
        evaluation = worker.evaluate(EvaluateRequest(run_id='sdk-test', instance_id='D1', iteration_id=0,
            time_s=0., trial_ports={'in0': PortState(pressure_pa=250000., temperature_k=293.15,
                                                   density_kg_m3=998.2)}))
        assert evaluation.relations[0].kind == 'valve'
        committed = worker.commit_step(models.CommitStepRequest(run_id='sdk-test', instance_id='D1',
            time_s=.5, dt_s=.5, converged_channels={'main': models.ChannelState(mass_flow_kg_s=flow)}))
        assert committed.state['throughput_kg'] == pytest.approx(abs(flow) * .5)
        assert committed.state['commit_count'] == 1
        assert not worker._request({'action': 'startup_report'})['properties_imported']
    finally:
        worker.close()
    assert worker.process is None or worker.process.poll() is not None


def test_typed_example_runs_real_network_and_commits_the_flow_ledger():
    inlet, outlet = 250000., 120000.
    result = run_module_test(ModuleTestRequest(module=typed_valve(), inlet_pressure_pa=inlet,
        outlet_pressure_pa=outlet, duration_s=1.0, dt_s=.5))
    assert all(frame.valid for frame in result.history)
    assert result.committed.state['commit_count'] == 2
    actual = result.frame.variables['D1.main.mass_flow_kg_s']
    rho = result.evaluation.variables['density_kg_m3']
    expected = rho * 16. * .8 / 3600. * math.copysign(math.sqrt(abs(inlet - outlet) / (1e5 * rho / 1000.)), inlet - outlet)
    assert actual == pytest.approx(expected, rel=1e-6, abs=1e-8)
    integrated = sum(abs(frame.variables['D1.main.mass_flow_kg_s']) * (frame.time_s - previous.time_s)
                     for previous, frame in zip(result.history, result.history[1:]))
    assert result.committed.state['throughput_kg'] == pytest.approx(integrated, abs=1e-8)
