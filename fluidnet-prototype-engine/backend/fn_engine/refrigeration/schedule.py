"""Schedule events shared by the cold-store and refrigeration-station sessions.

`set_variable` writes a runtime parameter or a PID setpoint/manual output at a simulation time, through
the same atomic `write_variables` path as an outside command (it bumps the parameter revision)."""
from ..compiler import CompilationError, runtime_parameter
from ..models import Diagnostic

EPS = 1e-9


def check_set_variable(project, modules, instances, event):
    """Compile-time check: the key is writable now and not owned by a PID or an enabled control script."""
    parts = event.key.split('.')
    pids = {c.id: c for c in project.controllers}
    owned = {f'{c.instance_id}.param.{c.parameter_id}' for c in project.controllers}
    owned |= {key for script in project.control_scripts if script.enabled for key in script.outputs}
    if event.key in owned:
        raise CompilationError('SCHEDULE_EVENT_CONFLICT', f'事件 {event.id} 要写的 {event.key} 已由 PID 或控制脚本控制',
                               parts[0] if parts[0] in instances else None, 'events')
    if len(parts) == 3 and parts[0] == 'controller' and parts[1] in pids and parts[2] in ('setpoint', 'manual_output'):
        c = pids[parts[1]]
        if parts[2] == 'manual_output' and not c.minimum <= event.value <= c.maximum:
            raise CompilationError('SCHEDULE_EVENT_INVALID', f'事件 {event.id} 的手动输出超出 PID {c.id} 范围', field='events')
        return []
    if len(parts) == 3 and parts[1] == 'param' and parts[0] in instances:
        instance = instances[parts[0]]
        spec = runtime_parameter(instance, modules[instance.module_id], parts[2])
        if spec.value_type != 'number' or spec.minimum is not None and event.value < spec.minimum \
                or spec.maximum is not None and event.value > spec.maximum:
            raise CompilationError('SCHEDULE_EVENT_INVALID', f'事件 {event.id} 的值 {event.value:g} 超出 {event.key} 的范围',
                                   parts[0], 'events')
        return [parts[0]]
    raise CompilationError('SCHEDULE_EVENT_TARGET', f'事件 {event.id} 的 {event.key} 不可写；可写 <设备>.param.<运行参数> 或 '
                           'controller.<PID>.setpoint|manual_output', field='events')


def check_unique(events):
    seen = set()
    for event in events:
        if event.id in seen:
            raise CompilationError('SCHEDULE_EVENT_INVALID', f'日程事件 ID 重复：{event.id}', field='events')
        seen.add(event.id)


def apply_set_variable(session, event):
    session.write_variables({event.key: event.value})
    session.diagnostics.append(Diagnostic(code='SCHEDULE_EVENT', severity='info',
        message=f't={event.time_s:g}s 执行 {event.id}：{event.key} = {event.value:g}'))
