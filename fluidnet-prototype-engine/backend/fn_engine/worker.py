from __future__ import annotations

import json
import sys

from .models import CommitStepRequest, EvaluateRequest, FluidConfig, InitializeRequest, ModuleDefinition
from .runtime import InProcessModuleRunner


def main():
    runner = None
    for line in sys.stdin:
        try:
            message = json.loads(line)
            action = message.get("action")
            if action == "initialize":
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
        except Exception as exc:
            sys.stdout.write(json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
