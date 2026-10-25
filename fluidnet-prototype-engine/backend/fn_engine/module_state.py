"""The managed JSON-state contract shared by parent, module and control Workers."""
import json
import math

MAX_STATE_BYTES = 65536
MAX_STATE_DEPTH = 32
MAX_STATE_ITEMS = 16384
MAX_RESULT_BYTES = 2 * 1024 * 1024


def checked_result(value):
    text=json.dumps(value.model_dump(mode='json'),ensure_ascii=False,allow_nan=False)
    if len(text.encode('utf-8')) > MAX_RESULT_BYTES:
        raise ValueError('模块候选或计算结果超过 2 MiB')
    return value


def checked_state(state):
    if not isinstance(state, dict):
        raise ValueError('ctx.state 必须为字典')
    pending, count = [(state, 0)], 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > MAX_STATE_DEPTH or count > MAX_STATE_ITEMS:
            raise ValueError('ctx.state 超过深度或容器规模限制')
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError('ctx.state 的键必须为字符串')
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
        elif value is None or isinstance(value, (str, bool, int)):
            pass
        elif isinstance(value, float) and math.isfinite(value):
            pass
        else:
            raise ValueError('ctx.state 只接受有限数值和 JSON 数据')
    try:
        text = json.dumps(state, ensure_ascii=False, allow_nan=False)
    except (ValueError, OverflowError) as error:
        raise ValueError('ctx.state 不是有效 JSON') from error
    if len(text.encode('utf-8')) > MAX_STATE_BYTES:
        raise ValueError('ctx.state 超过 64 KiB')
    return json.loads(text)
