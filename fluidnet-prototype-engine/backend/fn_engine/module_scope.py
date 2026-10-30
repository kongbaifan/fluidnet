"""Configuration restrictions and per-phase operating envelopes in canonical SI units."""
from .models import Diagnostic


def check_scope_configuration(definition, fluid, domain='fluid'):
    scope = definition.applicability
    if scope is None:
        return
    if domain not in scope.execution_domains:
        raise ValueError(f'{definition.id} 不支持执行域 {domain}')
    if scope.fluids and fluid.fluid.casefold() not in {name.casefold() for name in scope.fluids}:
        raise ValueError(f'{definition.id} 不支持工质 {fluid.fluid}')
    if definition.execution_role:
        return  # role-specific saturated/two-phase data is checked by the typed refrigeration protocol
    if fluid.phase_policy in {'liquid','gas'} and fluid.phase_policy not in scope.phases:
        raise ValueError(f'{definition.id} 不支持相态 {fluid.phase_policy}')


def scope_diagnostics(definition, ports, channels, phase, instance_id, time_s):
    scope = definition.applicability
    if scope is None or definition.execution_role:
        return []
    diagnostics = []
    for name, port in ports.items():
        if port.quality is not None and 0 <= port.quality <= 1:
            diagnostics.append(Diagnostic(code='MODULE_PHASE_UNSUPPORTED', message=f'{instance_id}.{name} 两相状态不在模块适用范围',
                instance_id=instance_id, phase=phase, time_s=time_s))
    for limit in scope.limits:
        item = (ports if limit.target == 'port' else channels).get(limit.id)
        value = getattr(item, limit.quantity, None)
        if value is None:
            continue
        outside = limit.minimum is not None and value < limit.minimum or limit.maximum is not None and value > limit.maximum
        if outside:
            trial = phase in {'evaluate','thermal'}
            severity = 'warning' if limit.kind == 'envelope' or trial else 'error'
            diagnostics.append(Diagnostic(code='MODULE_SCOPE_TRIAL_LIMIT' if trial else 'MODULE_SCOPE_LIMIT',
                message=f'{instance_id}.{limit.id} {limit.quantity}={value:g} 超出 {limit.kind} 范围 [{limit.minimum}, {limit.maximum}]',
                severity=severity, instance_id=instance_id, module_id=definition.id, module_version=definition.version,
                phase=phase, time_s=time_s, field=f'applicability.{limit.id}.{limit.quantity}'))
    return diagnostics
