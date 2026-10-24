"""Module authoring checks. User code is loaded only inside a Worker."""
import ast
from .models import Diagnostic, FluidConfig, ModuleDefinition, ValidationResponse
from .runtime import WorkerProcess, design_source, module_content_hash, module_definition_hash, module_source


def validate_module_definition(module: ModuleDefinition) -> ValidationResponse:
    diagnostics = []
    if module.runtime != "python":
        return ValidationResponse(valid=False, diagnostics=[Diagnostic(code="MODULE_RUNTIME_UNSUPPORTED", message="版本保存只接受 Python 模块")])
    try:
        from .module_contracts import check_module_compatibility
        check_module_compatibility(module)
        source = module_source(module)
        compile(source, "module.py", "exec")
        declared = {channel.id for channel in module.channels}
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            parent = node.func.value
            if isinstance(parent, ast.Attribute) and parent.attr == 'net':
                channel = next((keyword.value for keyword in node.keywords if keyword.arg == 'channel'), None)
                if isinstance(channel, ast.Constant) and isinstance(channel.value, str) and channel.value not in declared:
                    diagnostics.append(Diagnostic(code='MODULE_CHANNEL_UNKNOWN', message=f'源码第 {node.lineno} 行返回未声明通路 {channel.value}',
                        source_file='module.py', source_line=node.lineno, field=f'source.runtime:{node.lineno}'))
        try:
            compile(design_source(module), "design.py", "exec")
        except SyntaxError as error:
            diagnostics.append(Diagnostic(code="DESIGN_SYNTAX_ERROR", message=f"design.py 第 {error.lineno} 行：{error.msg}", field=f"source.design:{error.lineno}"))
        if not module.entrypoint:
            diagnostics.append(Diagnostic(code="MODULE_ENTRYPOINT_MISSING", message="Python 模块必须声明 entrypoint", field="entrypoint"))
        if module.content_hash and module.content_hash != module_content_hash(module):
            diagnostics.append(Diagnostic(code="MODULE_HASH_MISMATCH", message="源码哈希不一致", field="source.runtime"))
        if module.definition_hash and module.definition_hash != module_definition_hash(module):
            diagnostics.append(Diagnostic(code="MODULE_DEFINITION_HASH_MISMATCH", message="契约哈希不一致", field="definition_hash"))
        if not any(item.severity == 'error' for item in diagnostics):
            runner = WorkerProcess(module, {p.id: p.default for p in module.parameters}, FluidConfig())
            try:
                runner.validate_entrypoint()
            finally:
                runner.close()
    except SyntaxError as error:
        diagnostics.append(Diagnostic(code="MODULE_SYNTAX_ERROR", message=f"module.py 第 {error.lineno} 行：{error.msg}",
            field=f"source.runtime:{error.lineno}",source_file='module.py',source_line=error.lineno,module_id=module.id,module_version=module.version,phase='validate'))
    except ValueError as error:
        field = getattr(error, "field", "source.design" if str(error).startswith("design.py") else "entrypoint")
        related=getattr(error,'diagnostics',[])
        diagnostics.extend([item.model_copy(update={'field':field}) if item.field is None else item for item in related] or
            [Diagnostic(code=getattr(error, "code", "MODULE_LOAD_ERROR"), message=str(error), field=field)])
    return ValidationResponse(valid=not diagnostics, diagnostics=diagnostics)
