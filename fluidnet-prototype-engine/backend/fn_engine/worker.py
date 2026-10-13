from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout, redirect_stderr
import os
import inspect

from .models import CommitStepRequest, EvaluateRequest, InitializeRequest, ModuleDefinition
from .runtime import InProcessModuleRunner, _load_module
from . import properties

# The API process loaded every REFPROP fluid of this project in a probe process before starting us.
properties.PROBE_REFPROP = False


def main():
    runners = {}

    def dispatch(message):
        action=message.get('action')
        key=message.get('instance_id','default')
        runner=runners.get(key)
        if action=='batch':
            return {key:dispatch(item) for key,item in message['items'].items()}
        if action=='validate':
            definition=ModuleDefinition.model_validate(message['definition'])
            target=_load_module(definition)
            for name,count in (('initialize',1),('evaluate',1),('commit_step',2),('finalize',1)):
                callback=getattr(target,name,None)
                if not callable(callback) or inspect.iscoroutinefunction(callback):
                    raise ValueError(f'入口必须实现同步生命周期方法 {name}')
                inspect.signature(callback).bind(*([None]*count))
            return {'ok':True}
        if action=='initialize':
            definition=ModuleDefinition.model_validate(message['definition'])
            request=InitializeRequest.model_validate(message['request'])
            runner=InProcessModuleRunner(definition,request.parameters,request.fluid,request.initial_state)
            runners[key]=runner
            return {'state':runner.initialize()}
        if action=='finalize':
            errors=[]
            for runner in runners.values():
                try: runner.finalize()
                except Exception as error: errors.append(str(error))
            if errors: raise ValueError('; '.join(errors))
            return {'ok':True}
        if runner is None:
            raise ValueError('Worker 尚未初始化')
        if action=='parameters':
            runner.parameters=dict(message['parameters'])
            return {'ok':True}
        if action=='evaluate':
            return runner.evaluate(EvaluateRequest.model_validate(message['request'])).model_dump(mode='json')
        if action=='commit_step':
            return runner.commit_step(CommitStepRequest.model_validate(message['request'])).model_dump(mode='json')
        raise ValueError(f'未知 Worker 操作：{action}')

    for line in sys.stdin:
        try:
            message=json.loads(line)
            with open(os.devnull,'w',encoding='utf-8') as output, redirect_stdout(output), redirect_stderr(output):
                result=dispatch(message)
            sys.stdout.write(json.dumps(result,ensure_ascii=False)+'\n')
            sys.stdout.flush()
            if message.get('action')=='finalize':break
        except Exception as error:
            sys.stdout.write(json.dumps({'error':str(error)},ensure_ascii=False)+'\n')
            sys.stdout.flush()


if __name__ == "__main__":
    main()
