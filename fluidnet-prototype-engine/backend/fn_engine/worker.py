from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout, redirect_stderr
import os
import inspect

from .models import CommitStepRequest, EvaluateRequest, InitializeRequest, ModuleDefinition
from .runtime import InProcessModuleRunner, _load_module


def main():
    runner = None
    for line in sys.stdin:
        try:
            message = json.loads(line)
            action = message.get("action")
            # User print calls must never corrupt the JSON RPC stream.
            with open(os.devnull, "w", encoding="utf-8") as output, redirect_stdout(output), redirect_stderr(output):
                if action == "validate":
                    definition = ModuleDefinition.model_validate(message["definition"])
                    target = _load_module(definition)
                    for name, count in (("initialize", 1), ("evaluate", 1), ("commit_step", 2), ("finalize", 1)):
                        callback = getattr(target, name, None)
                        if not callable(callback) or inspect.iscoroutinefunction(callback):
                            raise ValueError(f"入口必须实现同步生命周期方法 {name}")
                        inspect.signature(callback).bind(*([None] * count))
                    result = {"ok": True}
                elif action == "initialize":
                    definition = ModuleDefinition.model_validate(message["definition"])
                    request = InitializeRequest.model_validate(message["request"])
                    runner = InProcessModuleRunner(definition, request.parameters, request.fluid, request.initial_state)
                    result = {"state": runner.initialize()}
                elif action == "evaluate":
                    if runner is None:
                        raise ValueError("Worker 尚未初始化")
                    result = runner.evaluate(EvaluateRequest.model_validate(message["request"])).model_dump(mode="json")
                elif action == "commit_step":
                    if runner is None:
                        raise ValueError("Worker 尚未初始化")
                    result = runner.commit_step(CommitStepRequest.model_validate(message["request"])).model_dump(mode="json")
                elif action == "finalize":
                    if runner is not None:
                        runner.finalize()
                    result = {"ok": True}
                else:
                    raise ValueError(f"未知 Worker 操作：{action}")
            sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
            sys.stdout.flush()
            if action == "finalize":
                break
        except Exception as exc:
            sys.stdout.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
