"""Versioned, JSON-only accepted-session checkpoints; no executable deserializer."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import fields, is_dataclass
from enum import Enum
from functools import lru_cache
from hashlib import sha256
from importlib import import_module
from importlib.metadata import version
import json
import math
from pathlib import Path
import sys

import numpy as np
from pydantic import BaseModel

from .compiler import CompilationError, compile_project
from .model_types.domain import Project
from .model_types.run import RunFrame
from .module_state import checked_state

FORMAT_VERSION = 1
MAX_BYTES = 32 * 1024 * 1024
_MODULES = frozenset({
    'fn_engine.compiler', 'fn_engine.solver', 'fn_engine.thermal', 'fn_engine.trapped',
    'fn_engine.timestep', 'fn_engine.controllers', 'fn_engine.air_transport',
    'fn_engine.air_models', 'fn_engine.air_room', 'fn_engine.air_liquid',
    'fn_engine.buffer_tank', 'fn_engine.expansion_tank', 'fn_engine.tower_pool',
    'fn_engine.coupled_tower_pool', 'fn_engine.water_chiller', 'fn_engine.air_water_chiller',
    'fn_engine.air_source_heat_pump', 'fn_engine.refrigeration.devices',
    'fn_engine.refrigeration.cycle', 'fn_engine.refrigeration.cold_store',
    'fn_engine.refrigeration.coupling', 'fn_engine.model_types.base',
    'fn_engine.model_types.domain', 'fn_engine.model_types.protocol',
    'fn_engine.model_types.run', 'fn_engine.refrigeration_models',
    'fn_engine.refrigeration_physics',
    'fn_engine._module_schema_v1', 'fn_engine.module_execution',
})
# These objects contain live resources or derived numerical workspaces, not accepted physical state.
_VOLATILE = frozenset({
    'network', 'service', 'services', 'runners', 'scripts', 'controllers',
    'closed', '_control_base', 'module_adapter', '_module_transaction',
    'march', 'frames', 'view', 'process_engine',
})


def _class(module, name):
    if module not in _MODULES or '.' in name or name.startswith('_'):
        raise ValueError('Checkpoint contains an unsupported data class')
    cls = getattr(import_module(module), name, None)
    if not isinstance(cls, type) or not (is_dataclass(cls) or issubclass(cls, (BaseModel, Enum))):
        raise ValueError('Checkpoint class must be a registered data model')
    return cls


def _encode(value, depth=0, allow_limit=False):
    if depth > 64:
        raise ValueError('Checkpoint nesting exceeds 64')
    encode = lambda child: _encode(child, depth + 1)
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, Enum):
        return {'kind': 'enum', 'module': type(value).__module__, 'name': type(value).__name__, 'value': value.value}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            if allow_limit and value == math.inf:
                return {'kind': 'unbounded_limit'}
            raise ValueError('Checkpoint values must be finite')
        return value
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in 'biuf' or not np.isfinite(value).all():
            raise ValueError('Checkpoint arrays must contain finite numbers')
        return {'kind': 'array', 'dtype': str(value.dtype), 'value': value.tolist()}
    if isinstance(value, dict):
        return {'kind': 'mapping', 'value': [[encode(k), encode(v)] for k, v in value.items()]}
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return {'kind': type(value).__name__, 'value': [encode(v) for v in value]}
    cls = type(value)
    _class(cls.__module__, cls.__name__)
    if isinstance(value, BaseModel):
        return {'kind': 'model', 'module': cls.__module__, 'name': cls.__name__,
                'value': value.model_dump(mode='json')}
    if is_dataclass(value):
        return {'kind': 'data', 'module': cls.__module__, 'name': cls.__name__,
                'value': {f.name: _encode(getattr(value, f.name), depth + 1,
                    cls.__module__ == 'fn_engine.timestep' and cls.__name__ in ('StepStatistics', 'TimeStepConfig'))
                    for f in fields(value)}}
    raise ValueError(f'Unsupported checkpoint field: {cls.__name__}')


def _decode(value, depth=0):
    if depth > 64:
        raise ValueError('Checkpoint nesting exceeds 64')
    if not isinstance(value, dict):
        if value is None or isinstance(value, (str, bool, int)) or isinstance(value, float) and math.isfinite(value):
            return value
        raise ValueError('Invalid checkpoint scalar')
    decode = lambda child: _decode(child, depth + 1)
    kind, data = value.get('kind'), value.get('value')
    if kind == 'unbounded_limit':
        return math.inf
    if kind == 'mapping':
        return {decode(k): decode(v) for k, v in data}
    if kind in ('list', 'tuple', 'set', 'frozenset', 'deque'):
        factory = {'list': list, 'tuple': tuple, 'set': set, 'frozenset': frozenset, 'deque': deque}[kind]
        return factory(decode(v) for v in data)
    if kind == 'array':
        dtype = np.dtype(value['dtype'])
        if dtype.kind not in 'biuf':
            raise ValueError('Invalid checkpoint array type')
        array = np.array(data, dtype=dtype)
        if not np.isfinite(array).all():
            raise ValueError('Invalid checkpoint array values')
        return array
    if kind in ('model', 'data', 'enum'):
        cls = _class(value['module'], value['name'])
        if kind == 'model':
            return cls.model_validate(data)
        if kind == 'enum':
            return cls(data)
        return cls(**{k: decode(v) for k, v in data.items()})
    raise ValueError('Invalid checkpoint data tag')


def _bytes(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(data) > MAX_BYTES:
        raise ValueError('Session checkpoint exceeds 32 MiB')
    return data


@lru_cache(maxsize=1)
def kernel_fingerprint():
    """A resumed calculation must use the same numerical implementation."""
    root = Path(__file__).parent
    # Air-side physics, author contracts and SDK behavior also affect continuation.
    # Hash all engine/SDK sources so a newly changed domain cannot resume an old
    # numerical state merely because its implementation was outside a short list.
    files = sorted(root.rglob('*.py')) + sorted((root.parent / 'fn_sdk').rglob('*.py'))
    digest = sha256()
    digest.update(sys.version.encode())
    for dependency in ('numpy', 'scipy', 'CoolProp', 'pydantic'):
        digest.update((dependency + '=' + version(dependency)).encode())
    for path in files:
        digest.update(path.relative_to(root.parent).as_posix().encode())
        digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
    return digest.hexdigest()


def capture(session):
    if session.closed or not session.frames:
        raise CompilationError('CHECKPOINT_BOUNDARY_REQUIRED', '只能保存仍开放的已接受发布帧')
    if getattr(session, '_module_transaction', None) is not None:
        raise CompilationError('CHECKPOINT_BOUNDARY_REQUIRED', '模块接受事务尚未结束')
    try:
        host = {key: _encode(value) for key, value in vars(session).items() if key not in _VOLATILE}
        controllers = {key: _encode(pid) for key, pid in session.controllers.items()}
        modules = {key: {'state': checked_state(runner.state), 'revision': runner.state_revision}
                   for key, runner in session.runners.items()}
        scripts = {}
        for key, script in session.scripts.items():
            if script.pending is not None:
                raise ValueError('Control proposal has not been accepted')
            scripts[key] = {name: _encode(getattr(script, name))
                            for name in ('state', 'last_s', 'next_s', 'samples', 'last_values', 'pending')}
        packet = {'format': FORMAT_VERSION, 'kernel': kernel_fingerprint(),
                  'domain': getattr(session.network, 'execution_domain', 'fluid'),
                  'session': type(session).__name__, 'project': session.network.project.model_dump(mode='json'),
                  'parameters': deepcopy(session.network.parameters), 'host': host,
                  'controllers': controllers, 'modules': modules, 'scripts': scripts,
                  'next_step_s': session.march._next_h if getattr(session, 'march', None) is not None else None,
                  'frame': session.frames[-1].model_dump(mode='json')}
        packet['frame']['parameter_revision'] = session.revision
        packet['sha256'] = sha256(_bytes(packet)).hexdigest()
        return packet
    except (ValueError, TypeError, AttributeError) as error:
        raise CompilationError('CHECKPOINT_STATE_UNSUPPORTED', f'会话快照不可保存：{error}') from error


def validate(packet):
    packet = deepcopy(packet)
    checksum = packet.pop('sha256', None)
    if packet.get('format') != FORMAT_VERSION or sha256(_bytes(packet)).hexdigest() != checksum:
        raise CompilationError('CHECKPOINT_INVALID', '会话快照版本或完整性校验失败')
    if packet.get('kernel') != kernel_fingerprint():
        raise CompilationError('CHECKPOINT_KERNEL_MISMATCH', '数值实现已变化，请使用原版本续算或新建运行')
    packet['sha256'] = checksum
    return packet


def accepted_project(packet):
    """Editable copy of the accepted parameters and controller settings, without runtime resources."""
    packet = validate(packet)
    project = deepcopy(packet['project'])
    for instance in project['instances']:
        instance['parameters'] = deepcopy(packet['parameters'][instance['id']])
        instance['draft_parameters'] = deepcopy(instance['parameters'])
    controllers = {key: _decode(value).config.model_dump(mode='json')
                   for key, value in packet['controllers'].items()}
    project['controllers'] = [controllers.get(item['id'], item) for item in project.get('controllers', [])]
    return Project.model_validate(project)


def restore(packet, *, duration_s=None, keep=8):
    """Create fresh resources, restore only accepted parent/managed state, and continue the original clock."""
    from .sessions import create_session
    packet = validate(packet)
    project = Project.model_validate(packet['project'])
    host = {key: _decode(value) for key, value in packet['host'].items()}
    if _VOLATILE & host.keys() or host['time'] < 0:
        raise CompilationError('CHECKPOINT_INVALID', '会话快照含非法资源字段或时刻')
    duration = host['duration'] if duration_s is None else duration_s
    if duration is not None and duration <= host['time']:
        raise CompilationError('CHECKPOINT_DURATION', '续算终止时刻必须晚于快照时刻')
    session = create_session(compile_project(project), duration, host['dt'], keep=keep)
    try:
        if type(session).__name__ != packet['session']:
            raise CompilationError('CHECKPOINT_DOMAIN_MISMATCH', '快照执行域与项目不一致')
        session.initialize()
        if set(packet['modules']) != set(session.runners) or set(packet['scripts']) != set(session.scripts):
            raise CompilationError('CHECKPOINT_MODULE_MISMATCH', '快照模块或控制脚本不一致')
        candidates = packet['parameters']
        for key, parameters in candidates.items():
            if key not in session.network.parameters:
                raise CompilationError('CHECKPOINT_INVALID', '快照含未知设备参数')
            session.validate_parameter_values(key, parameters)
        session._commit_parameter_candidates(candidates, {})
        for key, values in packet['modules'].items():
            session.runners[key].restore_checkpoint(values['state'], values['revision'], host['time'])
        for key, values in packet['scripts'].items():
            script = session.scripts[key]
            for name, value in values.items():
                setattr(script, name, _decode(value))
            script.state = checked_state(script.state)
        session.controllers = {key: _decode(value) for key, value in packet['controllers'].items()}
        for key, value in host.items():
            setattr(session, key, value)
        session.duration = duration
        session.closed = False
        session._control_base = None
        if getattr(session, 'march', None) is not None:
            session.march._next_h = packet['next_step_s']
            session.march.stats = session.step_stats
        session.frames.clear()
        session.frames.append(RunFrame.model_validate(packet['frame']))
        return session
    except BaseException:
        session.close()
        raise
