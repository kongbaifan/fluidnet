"""集中注册 HTTP 错误码与 OpenAPI 错误响应声明。

运行时响应体保持不变：错误仍是 FastAPI 的 `{"detail": …}` 包络——结构化
`{"code","message",…}`、纯文本说明，或请求校验问题列表。本模块只把错误码/状态码
映射为 HTTP 状态与描述，并生成路由的 `responses=` 文档；不参与运行时序列化，
也不改变任何状态码或响应字段。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ErrorResponse


@dataclass(frozen=True)
class ErrorCode:
    """服务端主动产生的错误码：HTTP 状态与 OpenAPI 描述。"""
    status: int
    description: str


# 静态错误码：api.py 与异常处理器直接写进响应体 detail.code 的值。
ERROR_CODES: dict[str, ErrorCode] = {
    'AUTH_REQUIRED': ErrorCode(401, '缺少或无效的访问令牌'),
    'AUTH_SCOPE': ErrorCode(403, '令牌权限不足以执行该请求方法'),
    'RUN_NOT_FOUND': ErrorCode(404, '运行记录不存在或已过期'),
    'PROJECT_CONFLICT': ErrorCode(409, '项目或工作区修订冲突'),
    'WORKSPACE_CONFLICT': ErrorCode(409, '工作区修订冲突'),
    'MODULE_VERSION_CONFLICT': ErrorCode(409, '模块版本冲突'),
    'RUN_ALREADY_FINISHED': ErrorCode(409, '运行已结束，命令被拒绝'),
    'COMMAND_ID_CONFLICT': ErrorCode(409, '命令 ID 已用于不同内容'),
    'NO_FRAME': ErrorCode(409, '运行还没有可读的帧'),
    'MODULE_SAVE_INVALID': ErrorCode(422, '模块版本校验或试算未通过'),
    'MODULE_WORKER_IO_ERROR': ErrorCode(422, '模块 Worker 子进程 I/O 故障'),
    'RUN_LIMIT': ErrorCode(422, '后台运行数量达到上限'),
    'RUN_TOO_LONG': ErrorCode(422, '同步运行帧数超过上限'),
    'VARIABLE_UNKNOWN': ErrorCode(422, '请求的帧变量不存在'),
    'MODULE_STORAGE_ERROR': ErrorCode(500, '模块版本写入失败'),
    'INTERNAL_ERROR': ErrorCode(500, '服务内部错误（已记录日志）'),
    'STORAGE_FAILED': ErrorCode(507, '工作区存储故障（磁盘空间或目录权限）'),
}

# 诊断码：由编译/求解/物性层产生，作为 detail.code 透传，状态由各路由决定（多为 422）。
# 编译器的完整诊断码集合是开放的，这里只登记 api.py 自己会拼出的静态值。
DIAGNOSTIC_CODES: dict[str, int] = {
    'SCENARIO_NOT_FOUND': 422,
    'SCENARIO_INSTANCE_MISSING': 422,
    'TREND_VARIABLE_UNKNOWN': 422,
    'SOLVER_ERROR': 422,
}

# 没有 detail.code、只有纯文本 detail 的错误按状态登记（用于 OpenAPI 描述）。
STATUS_ERRORS: dict[int, str] = {
    404: '资源不存在（运行记录、项目修订、模块版本、示例或工作区修订）',
    409: '资源状态冲突（活动运行、修订号或命令状态）',
    413: '请求体超过大小上限',
    422: '请求体或计算结果校验失败',
    500: '服务内部错误',
    503: '持久存储未启用',
    507: '工作区存储故障',
}


def error_responses(*entries: str | int) -> dict[int | str, dict[str, Any]]:
    """把错误码和/或状态码展开成 FastAPI `responses=` 声明（只影响 OpenAPI 文档）。

    参数可混用错误码字符串与状态码整数；同一状态下的多个错误码合并为一条描述。
    未登记的错误码/状态码会立即报错，保证注册表与路由声明一致。
    """
    grouped: dict[int, list[str]] = {}
    for entry in entries:
        if isinstance(entry, str):
            try:
                spec = ERROR_CODES[entry]
            except KeyError:
                raise KeyError(f'未注册的错误码：{entry}（请先在 errors.ERROR_CODES 登记）') from None
            status, description = spec.status, f'{entry}：{spec.description}'
        elif isinstance(entry, int):
            try:
                description = STATUS_ERRORS[entry]
            except KeyError:
                raise KeyError(f'未注册的错误状态：{entry}（请先在 errors.STATUS_ERRORS 登记）') from None
            status = entry
        else:
            raise TypeError(f'错误声明必须是错误码字符串或状态码整数：{entry!r}')
        grouped.setdefault(status, []).append(description)
    return {status: {'model': ErrorResponse, 'description': '；'.join(descriptions)}
            for status, descriptions in sorted(grouped.items())}


def protected_error_responses(*entries: str | int) -> dict[int | str, dict[str, Any]]:
    """受令牌保护路由的错误响应：固定包含 401 AUTH_REQUIRED 与 403 AUTH_SCOPE。"""
    return error_responses('AUTH_REQUIRED', 'AUTH_SCOPE', *entries)
