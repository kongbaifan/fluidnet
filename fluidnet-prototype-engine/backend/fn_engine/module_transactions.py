"""Whole-step candidate collection with parent-owned state and revision authority."""
from copy import deepcopy
import json

from .models import CommitStepRequest,Diagnostic
from .module_execution import mark_module_accepted
from .runtime import RuntimeErrorBase
from .runtime import module_content_hash,module_definition_hash
from .module_state import checked_state,checked_result


class ModuleStepTransaction:
    def __init__(self, runners, step_id, time_s):
        self.runners, self.step_id, self.time_s = runners, step_id, time_s
        self.candidates = {}
        self.accepted = False

    def prepare(self, instance_id, request: CommitStepRequest, channels):
        runner = self.runners[instance_id]
        candidate = runner.prepare_step(request, channels=channels)
        self.candidates[instance_id] = candidate
        return candidate.result

    def validate(self):
        if set(self.candidates) != set(self.runners):
            raise RuntimeErrorBase('模块候选集合不完整', code='MODULE_CANDIDATE_INCOMPLETE')
        for key, candidate in self.candidates.items():
            runner = self.runners[key]
            definition=getattr(runner,'definition',None) or runner.worker._definitions[key]
            if (candidate.base_revision != runner.state_revision or candidate.step_id != self.step_id or candidate.time_s != self.time_s
                    or candidate.content_hash != module_content_hash(definition) or candidate.definition_hash != module_definition_hash(definition)):
                raise RuntimeErrorBase('模块候选状态已过期', code='MODULE_REVISION_CONFLICT')
            checked_state(candidate.result.state)
            checked_result(candidate)
            json.dumps(candidate.model_dump(mode='json'),allow_nan=False)

    def promote(self):
        self.validate()
        # No RPC or user code occurs inside the parent acceptance point.
        for key, candidate in self.candidates.items():
            runner = self.runners[key]
            runner.state = deepcopy(candidate.result.state)
            runner.state_revision += 1
            runner._accepted_candidate = candidate
            if hasattr(runner,'_last_committed_time_s'):
                runner._last_committed_time_s = self.time_s
                runner._accepted_digest = runner._pending_digest
                runner._pending_candidate = None
        self.accepted = True
        mark_module_accepted(self.runners, self.time_s)

    def synchronize(self):
        errors,diagnostics = [],[]
        for key, runner in self.runners.items():
            try:
                runner.synchronize_state(self.candidates[key])
            except Exception as error:
                errors.append(f'{key}: {error}')
                diagnostics.extend(getattr(error,'diagnostics',[]) or [Diagnostic(code='MODULE_SYNC_FAILED',
                    message=str(error),instance_id=key,phase='synchronize',time_s=self.time_s)])
        if errors:
            message='子步已接受，Worker 状态同步失败：'+'; '.join(errors)
            main=diagnostics[0].model_copy(update={'code':'MODULE_SYNC_FAILED','message':message,'phase':'synchronize','time_s':self.time_s})
            failure = RuntimeErrorBase(message,code='MODULE_SYNC_FAILED',diagnostics=[main,*diagnostics])
            failure.accepted = True
            raise failure

    def discard(self):
        if self.accepted:
            return
        for key in self.candidates:
            try:
                self.runners[key].discard_candidate()
            except Exception:
                # Parent remains authoritative; an unavailable Worker is closed.
                worker = getattr(self.runners[key], 'worker', self.runners[key])
                if hasattr(worker, 'close'):
                    worker.close(force=True)
