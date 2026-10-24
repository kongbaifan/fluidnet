"""Host-side callback identity. This records boundaries; it performs no state transaction."""
from uuid import uuid4

from .models import ModuleRequestContext


def new_identity(prefix):
    return f'{prefix}-{uuid4().hex}'


class InvocationState:
    def __init__(self, run_id=None, instance_id=None):
        self.run_id = run_id or new_identity('run')
        self.instance_id = instance_id
        self.step_id: str | None = None
        self.accepted_time_s: float | None = None

    def context(self, *, port_data='trial'):
        return ModuleRequestContext(request_id=new_identity('request'), step_id=self.step_id,
                                    accepted_time_s=self.accepted_time_s, port_data=port_data)


def set_module_step(runners, step_id):
    for runner in runners.values():
        if hasattr(runner, 'execution'):
            runner.execution.step_id = step_id


def begin_module_step(runners):
    step_id = new_identity('step')
    set_module_step(runners, step_id)
    return step_id


def mark_module_accepted(runners, time_s):
    for runner in runners.values():
        if hasattr(runner, 'execution'):
            runner.execution.accepted_time_s = time_s
