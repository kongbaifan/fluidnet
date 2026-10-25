"""Module design functions: library values in, derived parameter values out.

design.py runs only inside fn_engine.worker. The result is a proposal; the caller
decides whether it replaces a library-value set.
"""
from copy import deepcopy
import hashlib
import inspect
import json
import traceback

from .models import Diagnostic, ModuleDesignRequest, ModuleDesignResponse, ModuleInstance, ParameterChange
from .runtime import RuntimeErrorBase, WorkerProcess, _LazyPropertyService, design_source

FILENAME = 'design.py'


class DesignContext:
    def __init__(self, parameters, fluid, declared):
        self._declared = declared
        self.parameters = deepcopy(parameters)
        self.fluid = _LazyPropertyService(fluid)
        self.outputs, self.diagnostics = {}, []

    def parameter(self, name, default=None):
        return self.parameters.get(name, default)

    def set(self, name, value):
        if name not in self._declared:
            raise ValueError(f'未声明的模块参数：{name}')
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(f'{name} 必须是可 JSON 序列化的有限值') from error
        self.outputs[name] = value

    def log(self, message):
        if len(self.diagnostics) >= 20:
            raise ValueError('每次设计计算最多记录 20 条日志')
        self.diagnostics.append(Diagnostic(code='DESIGN_LOG', severity='info', message=str(message)[:1000]).model_dump(mode='json'))


def load_design(source):
    """Compile design.py and return its design(ctx) callable."""
    namespace = {'__name__': 'fluidnet_design'}
    try:
        exec(compile(source, FILENAME, 'exec'), namespace)
    except Exception as error:
        raise ValueError(f'design.py 载入失败：{error}') from error
    callback = namespace.get('design')
    if not callable(callback) or inspect.iscoroutinefunction(callback):
        raise ValueError('design.py 必须实现同步函数 design(ctx)')
    try:
        inspect.signature(callback).bind(None)
    except TypeError as error:
        raise ValueError(f'design.py 的 design 必须只接收 ctx 一个参数：{error}') from error
    return callback


def run_in_worker(definition, parameters, fluid):
    """Worker side of the `design` action."""
    from .models import FluidConfig, ModuleDefinition
    module = ModuleDefinition.model_validate(definition)
    from .module_contracts import check_module_compatibility
    check_module_compatibility(module)
    callback = load_design(design_source(module))
    ctx = DesignContext(parameters, FluidConfig.model_validate(fluid), {p.id for p in module.parameters})
    try:
        callback(ctx)
        result = {'outputs': ctx.outputs, 'diagnostics': ctx.diagnostics}
        json.dumps(result, allow_nan=False)
        return result
    except Exception as error:
        frames = [f for f in traceback.extract_tb(error.__traceback__) if f.filename == FILENAME]
        line = f'第 {frames[-1].lineno} 行：' if frames else ''
        raise ValueError(f'design.py {line}{error}') from error


def run_design(request: ModuleDesignRequest) -> ModuleDesignResponse:
    from .compiler import CompilationError, validated_parameters
    module = request.module
    if module.runtime != 'python':
        raise RuntimeErrorBase('设计函数只在 Python 模块中执行')
    source = design_source(module)
    if not source.strip():
        raise RuntimeErrorBase(f'模块 {module.id} 没有 design.py')
    inputs = validated_parameters(ModuleInstance(id='design', module_id=module.id, name=module.name,
                                                 parameters=request.parameters), module)
    runner = WorkerProcess(module, inputs, request.fluid)
    try:
        response = runner._request({'action': 'design', 'definition': module.model_dump(mode='json'),
                                    'parameters': inputs, 'fluid': request.fluid.model_dump(mode='json')})
    finally:
        runner.close(force=True)
    outputs = response.get('outputs', {})
    try:
        values = validated_parameters(ModuleInstance(id='design', module_id=module.id, name=module.name,
                                                     parameters=inputs | outputs), module)
    except CompilationError as error:
        raise CompilationError('DESIGN_OUTPUT_INVALID', f'design 输出无效：{error}', field=error.diagnostic.field) from error
    changes = [ParameterChange(id=p.id, before=inputs[p.id], after=values[p.id])
               for p in module.parameters if p.id in outputs and values[p.id] != inputs[p.id]]
    return ModuleDesignResponse(module_id=module.id, design_hash=hashlib.sha256(source.encode('utf-8')).hexdigest(),
                                parameters=values, changes=changes,
                                diagnostics=[Diagnostic.model_validate(d) for d in response.get('diagnostics', [])])
