"""Single-project exchange documents and conservative module-version upgrades."""
from copy import deepcopy

from .compiler import compile_project, validate_scenarios
from .models import ModuleDefinition, Project
from .packages import package_ref


def project_document(workspace, project_id):
    project = deepcopy(next(p for p in workspace['projects'] if p['id'] == project_id))
    used = {n['moduleId'] for pg in project.get('pages', []) for n in pg.get('nodes', [])}
    modules = {m['id']: m for m in workspace['modules']}
    modules.update(project.get('moduleSnapshots', {}))
    snapshots = {mid: deepcopy(modules[mid]) for mid in used if mid in modules}
    project.setdefault('moduleSnapshots', {}).update(snapshots)
    return {'format': 'fluidnet-project', 'schema': 1, 'project': project,
            'modules': list(snapshots.values()),
            'models': [deepcopy(m) for m in workspace['models'] if m.get('moduleId') in used],
            'charts': [deepcopy(c) for c in workspace.get('charts', {}).get('extra', []) if isinstance(c, dict) and c.get('projectId') == project_id]}


def merge_project(workspace, document):
    data = deepcopy(workspace)
    project = deepcopy(document['project'])
    project['moduleSnapshots'] = {m['id']: deepcopy(m) for m in document['modules']} | project.get('moduleSnapshots', {})
    previous = next((i for i, p in enumerate(data['projects']) if p['id'] == project['id']), None)
    if previous is None:
        data['projects'].append(project)
    else:
        data['projects'][previous] = project
    # Other projects keep their libraries. Project-owned snapshots resolve ID conflicts.
    for field in ('modules', 'models'):
        existing = {m['id'] for m in data[field]}
        data[field].extend(deepcopy(m) for m in document[field] if m['id'] not in existing)
    if 'charts' in data:
        data['charts']['extra'] = [c for c in data['charts'].get('extra', []) if not isinstance(c, dict) or c.get('projectId') != project['id']] + deepcopy(document['charts'])
    return data


def upgrade_project(project: Project, target: ModuleDefinition):
    old = next((m for m in project.modules if m.id == target.id), None)
    if old is None or old.runtime != 'python':
        raise ValueError('项目未绑定该 Python 模块')
    if target.version == old.version:
        raise ValueError('项目已经绑定该版本')
    changes, reasons = [], []
    fields = {'parameters': ('value_type', 'unit'), 'ports': ('domain', 'direction', 'circuit'),
              'channels': ('input_port', 'output_port', 'relation', 'solver_model', 'enabled'),
              'variables': ('quantity', 'unit', 'source', 'parameter_id', 'port_id')}
    for field, incompatible in fields.items():
        before = {v.id: v.model_dump(mode='json') for v in getattr(old, field)}
        after = {v.id: v.model_dump(mode='json') for v in getattr(target, field)}
        for key in sorted(before.keys() | after.keys()):
            a, b = before.get(key), after.get(key)
            if a == b:
                continue
            changes.append({'field': field, 'id': key, 'before': a, 'after': b})
            if a and (not b or any(a[k] != b[k] for k in incompatible)):
                reasons.append(f'{field}.{key} 被删除或类型、单位、引用发生不兼容变化')
    result = {'module_id': old.id, 'from_version': old.version, 'to_version': target.version,
              'from_hashes': package_ref(old).model_dump(mode='json'),
              'to_hashes': package_ref(target).model_dump(mode='json'),
              'source_before': old.source.get('runtime', ''), 'source_after': target.source.get('runtime', ''),
              'changes': changes, 'compatible': not reasons, 'reasons': reasons, 'module': target.model_dump(mode='json')}
    if reasons:
        return result
    candidate = project.model_copy(deep=True)
    candidate.modules = [target.model_copy(deep=True) if m.id == target.id else m for m in candidate.modules]
    defaults = {p.id: deepcopy(p.default) for p in target.parameters}
    for node in candidate.instances:
        if node.module_id != target.id:
            continue
        node.parameters = defaults | node.parameters
        node.draft_parameters = defaults | node.draft_parameters
        for bank in node.banks:
            bank.values = defaults | bank.values
        node.package = package_ref(target)
    try:
        candidate = Project.model_validate(candidate.model_dump())
        network = compile_project(candidate)
        errors = [d for d in network.diagnostics + validate_scenarios(candidate, network.modules) if d.severity == 'error']
        if errors:
            raise ValueError('；'.join(d.message for d in errors))
    except ValueError as error:
        result.update(compatible=False, reasons=[str(error)])
    if result['compatible']:
        result['project'] = candidate.model_dump(mode='json')
    return result
