"""Bounded diagnostics and replay metadata, independent of the numerical stack."""
import traceback

from .models import Diagnostic

MAX_DIAGNOSTICS = 128
MAX_MESSAGE_CHARS = 2000


def exception_diagnostic(error, definition, execution=None):
    line = getattr(error, 'lineno', None)
    filename = getattr(error, 'filename', None)
    for frame in traceback.extract_tb(error.__traceback__):
        if frame.filename == f'<{definition.id}>' or frame.filename.endswith('/module.py'):
            line, filename = frame.lineno, 'module.py'
    return Diagnostic(code=getattr(error, 'code', 'MODULE_RUNTIME_ERROR'), message=str(error)[:MAX_MESSAGE_CHARS],
        module_id=definition.id, module_version=definition.version,
        instance_id=execution.instance_id if execution else None,
        phase=execution.phase if execution else 'load', time_s=execution.time_s if execution else None,
        source_file='module.py' if filename == f'<{definition.id}>' else filename, source_line=line,
        field=f'source.runtime:{line}' if line else None)


def merge_diagnostics(existing, incoming):
    """Merge repeated messages; overflow is explicit and errors are never dropped."""
    result = list(existing)
    for diagnostic in incoming:
        key = (diagnostic.code, diagnostic.message, diagnostic.severity, diagnostic.instance_id,
               diagnostic.module_id, diagnostic.phase, diagnostic.field, diagnostic.channel_id)
        found = next((i for i, item in enumerate(result) if
            (item.code, item.message, item.severity, item.instance_id, item.module_id,
             item.phase, item.field, item.channel_id) == key), None)
        if found is not None:
            previous = result[found]
            result[found] = previous.model_copy(update={
                'occurrences': previous.occurrences + diagnostic.occurrences,
                'first_time_s': previous.first_time_s if previous.first_time_s is not None else previous.time_s,
                'last_time_s': diagnostic.time_s})
        elif len(result) < MAX_DIAGNOSTICS:
            result.append(diagnostic)
        elif diagnostic.severity == 'error':
            # Terminate rather than discarding a correctness failure behind log noise.
            raise ValueError(f'模块诊断超过 {MAX_DIAGNOSTICS} 条：{diagnostic.message}')
        else:
            marker = next((item for item in result if item.code == 'MODULE_LOG_TRUNCATED'), None)
            if marker is None:
                result[-1] = Diagnostic(code='MODULE_LOG_TRUNCATED', severity='warning',
                    message=f'模块日志超过 {MAX_DIAGNOSTICS} 条，后续非错误日志省略', occurrences=1)
            else:
                index=result.index(marker)
                result[index]=marker.model_copy(update={'occurrences':marker.occurrences+1})
    return result
