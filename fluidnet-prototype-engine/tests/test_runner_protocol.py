"""The same parent transaction works across all three transport shapes."""
import pytest

from fn_engine.batch import Handle
from fn_engine.model_types.base import FluidConfig
from fn_engine.model_types.domain import ModuleInstance
from fn_engine.module_transactions import ModuleStepTransaction
from fn_engine.runtime import InProcessModuleRunner, RuntimeErrorBase, WorkerProcess
from test_module_transactions import request, state_module


@pytest.fixture(params=['inprocess', 'worker', 'batch'])
def transport(request):
    definition = state_module()
    worker = None
    if request.param == 'inprocess':
        runner = InProcessModuleRunner(definition, {}, FluidConfig(), instance_id='D1')
        runner.initialize()
    else:
        worker = WorkerProcess(definition, {}, FluidConfig(), instance_id='D1')
        if request.param == 'worker':
            runner = worker
            runner.initialize()
        else:
            runner = Handle(worker, ModuleInstance(id='D1', name='device', module_id=definition.id),
                            definition, {}, FluidConfig())
    try:
        yield runner, worker
    finally:
        if worker is not None:
            worker.close()
        else:
            runner.finalize()


def test_parent_acceptance_is_transport_free_and_retry_is_idempotent(transport, monkeypatch):
    runner, worker = transport
    trial = ModuleStepTransaction({'D1': runner}, 'step1', .5)
    trial.prepare('D1', request(), None)
    assert runner.state == {'values': []} and runner.state_revision == 0
    trial.discard()
    assert runner.state == {'values': []} and runner.state_revision == 0

    accepted = ModuleStepTransaction({'D1': runner}, 'step1', .5)
    accepted.prepare('D1', request(), None)
    with monkeypatch.context() as guard:
        def forbidden(*args, **kwargs):
            pytest.fail('parent acceptance must not invoke a module or send an RPC')
        guard.setattr(worker or runner, '_request' if worker else '_invoke', forbidden)
        accepted.promote()
    assert accepted.accepted
    assert runner.state == {'values': [.5]} and runner.state_revision == 1
    assert runner.execution.accepted_time_s == .5
    accepted.synchronize()
    assert runner.prepare_step(request()) == accepted.candidates['D1']
    assert runner.state == {'values': [.5]} and runner.state_revision == 1
    accepted.discard()  # An accepted transaction cannot discard committed state.
    second = ModuleStepTransaction({'D1': runner}, 'step2', 1.)
    second.prepare('D1', request('step2', 1.), None)
    second.promote()
    second.synchronize()
    assert runner.state == {'values': [.5, .5]} and runner.state_revision == 2


def test_stale_candidate_is_rejected_before_any_authority_changes(transport):
    runner, _ = transport
    transaction = ModuleStepTransaction({'D1': runner}, 'step1', .5)
    transaction.prepare('D1', request(), None)
    transaction.candidates['D1'] = transaction.candidates['D1'].model_copy(update={'base_revision': 9})
    with pytest.raises(RuntimeErrorBase) as error:
        transaction.promote()
    assert error.value.code == 'MODULE_REVISION_CONFLICT'
    assert not transaction.accepted
    assert runner.state == {'values': []} and runner.state_revision == 0
    assert runner.execution.accepted_time_s is None
    transaction.discard()
