"""Lifecycle source locations, replay inputs and bounded log transport."""
from pathlib import Path

import pytest

from fn_engine.models import EvaluateRequest, FluidConfig
from fn_engine.packages import load_module_package
from fn_engine.runtime import InProcessModuleRunner, WorkerProcess, RuntimeErrorBase
from fn_engine.module_diagnostics import MAX_DIAGNOSTICS

ROOT = Path(__file__).resolve().parents[1]


def failing_definition():
    module = load_module_package(ROOT / 'modules/programmable_valve')
    module.source = {'runtime': '''class Module:
    def initialize(self, ctx): pass
    def evaluate(self, ctx):
        raise ValueError("source location probe")
    def commit_step(self, ctx, dt): pass
    def finalize(self, ctx): pass
'''}
    module.content_hash = module.definition_hash = None
    return module


@pytest.mark.parametrize('runner_type', [InProcessModuleRunner, WorkerProcess])
def test_error_transports_line_instance_time_and_replay(runner_type):
    runner = runner_type(failing_definition(), {}, FluidConfig(), instance_id='valve1')
    try:
        runner.initialize()
        with pytest.raises(RuntimeErrorBase, match='source location probe') as captured:
            runner.evaluate(EvaluateRequest(run_id='run1', instance_id='valve1', iteration_id=0, time_s=.5))
        error = captured.value
        diagnostic = error.diagnostics[0]
        assert diagnostic.source_line == 4
        assert diagnostic.source_file == 'module.py'
        assert diagnostic.instance_id == 'valve1'
        assert diagnostic.phase == 'evaluate' and diagnostic.time_s == .5
        assert error.replay['content_hash']
        assert error.replay['module']['source'] == runner.definition.source
        assert error.replay['state'] == runner.state
    finally:
        if isinstance(runner, WorkerProcess): runner.close()


def test_repeated_and_unique_logs_are_bounded_and_do_not_pollute_rpc():
    module = failing_definition()
    module.source['runtime'] = module.source['runtime'].replace('raise ValueError("source location probe")',
        'for i in range(2000): ctx.log("repeated")\n        for i in range(2000): ctx.log(str(i))')
    worker = WorkerProcess(module, {}, FluidConfig())
    try:
        worker.initialize()
        result = worker.evaluate(EvaluateRequest(run_id='run1', instance_id='D1', iteration_id=0, time_s=.5))
        assert len(result.diagnostics) == MAX_DIAGNOSTICS
        assert result.diagnostics[0].occurrences == 2000
        assert result.diagnostics[-1].code == 'MODULE_LOG_TRUNCATED'
        assert not worker._request({'action': 'startup_report'})['properties_imported']
    finally:
        worker.close()
