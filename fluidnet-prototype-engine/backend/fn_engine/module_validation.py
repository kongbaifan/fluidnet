"""Module authoring checks. User code is loaded only inside a Worker."""
from .models import Diagnostic, FluidConfig, ModuleDefinition, ValidationResponse
from .runtime import WorkerProcess, module_content_hash, module_definition_hash, module_source


def validate_module_definition(module: ModuleDefinition) -> ValidationResponse:
    diagnostics = []
    if module.runtime != "python":
        return ValidationResponse(valid=False, diagnostics=[Diagnostic(code="MODULE_RUNTIME_UNSUPPORTED", message="版本保存只接受 Python 模块")])
    try:
        source = module_source(module)
        compile(source, "module.py", "exec")
        if not module.entrypoint:
            diagnostics.append(Diagnostic(code="MODULE_ENTRYPOINT_MISSING", message="Python 模块必须声明 entrypoint", field="entrypoint"))
        if module.content_hash and module.content_hash != module_content_hash(module):
            diagnostics.append(Diagnostic(code="MODULE_HASH_MISMATCH", message="源码哈希不一致", field="source.runtime"))
        if module.definition_hash and module.definition_hash != module_definition_hash(module):
            diagnostics.append(Diagnostic(code="MODULE_DEFINITION_HASH_MISMATCH", message="契约哈希不一致", field="definition_hash"))
        if not diagnostics:
            runner = WorkerProcess(module, {p.id: p.default for p in module.parameters}, FluidConfig())
            try:
                runner.validate_entrypoint()
            finally:
                runner.close()
    except SyntaxError as error:
        diagnostics.append(Diagnostic(code="MODULE_SYNTAX_ERROR", message=f"module.py 第 {error.lineno} 行：{error.msg}", field=f"source.runtime:{error.lineno}"))
    except ValueError as error:
        diagnostics.append(Diagnostic(code=getattr(error, "code", "MODULE_LOAD_ERROR"), message=str(error), field="entrypoint"))
    return ValidationResponse(valid=not diagnostics, diagnostics=diagnostics)
