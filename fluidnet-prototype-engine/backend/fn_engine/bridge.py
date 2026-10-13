from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .catalog import catalog_map
from .models import (ChannelSpec, Connection, Diagnostic, Endpoint, FluidConfig, LibraryBank, ModuleInstance, PortSpec,
                     Position, Project, SolverOptions)

# Prototype project `medium` -> CoolProp fluid string for the single project fluid. Range checks
# (temperature/pressure per fluid) are done by the engine; one fluid per project until phase B.
PROTOTYPE_MEDIA = {
    'water': 'Water',
    'air': 'Air',
    'ammonia': 'Ammonia',
    'co2': 'CarbonDioxide',
    'r134a': 'R134a',
    'meg30': 'INCOMP::MEG[0.3]',
}

# Prototype parameter names -> canonical contract names. Conversion comes from UnitSpec.
PARAMETER_BINDINGS = {
    'source': {'pressure':'pressure_pa', 'temperature':'temperature_k'},
    'pump': {'speed':'speed_ratio', 'efficiency':'efficiency_ratio', 'head_curve':'head_curve'},
    'valve': {'opening':'opening_ratio', 'kv':'kv_m3_h'},
    'pipe': {'length':'length_m', 'diameter':'diameter_m', 'roughness':'roughness_m',
             'heatLoss':'heat_loss_ua_w_k', 'ambient':'ambient_temperature_k',
             'cells':'thermal_cells', 'wallHeat':'wall_heat_capacity_j_k'},
    'junction': {'elevation':'elevation_m'},
    'exchanger': {'ua':'ua_w_k', 'loss':'loss_coefficient', 'diameter':'diameter_m'},
    'tank': {'level':'level_m', 'area':'area_m2', 'height':'height_m', 'surface':'surface_pressure_pa',
             'temperature':'temperature_k', 'heater':'heat_input_w', 'heatLoss':'heat_loss_ua_w_k',
             'ambient':'ambient_temperature_k'},
}


def parameter_map(kind, params, definition):
    # Python module packages own their canonical contract IDs. Built-in
    # prototype modules still use the legacy UI names and bindings below.
    names = {key: key for key in params} if definition.runtime == 'python' else PARAMETER_BINDINGS[kind]
    unknown = params.keys() - names.keys()
    if unknown:
        raise ValueError(f'{kind} 不支持参数 {sorted(unknown)}')
    specs = {p.id:p for p in definition.parameters}
    for key, value in params.items():
        if names[key] not in specs:
            raise ValueError(f'{kind} 未声明参数 {names[key]}')
        if specs[names[key]].value_type == 'number' and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError(f'{kind}.{key} 必须是有限数值')
    return {names[key]: specs[names[key]].unit.to_canonical(value) if specs[names[key]].unit else deepcopy(value)
            for key,value in params.items()}


def normalize_prototype_export(data: dict[str, Any]) -> Project:
    if data.get('format') != 'fluidnet-studio-prototype':
        raise ValueError('需要包含项目的 fluidnet-studio-prototype 导出文件')
    projects = data.get('projects', [])
    if not projects:
        raise ValueError('原型导出文件没有项目')
    active_id = data.get('activeProject') or projects[0].get('id')
    raw = next((p for p in projects if p.get('id') == active_id), None)
    if raw is None:
        raise ValueError('activeProject 引用了不存在的项目')
    medium = raw.get('medium', 'water')
    # An explicit fluid string (e.g. REFPROP::R407C.MIX) overrides the preset medium.
    fluid_text = str(raw.get('fluid') or '').strip()
    if not fluid_text and medium not in PROTOTYPE_MEDIA:
        raise ValueError(f'不支持的介质 {medium}；可选：{"、".join(PROTOTYPE_MEDIA)}')
    reference = raw.get('fluidReference', 'mass')
    if reference not in ('mass', 'mole'):
        raise ValueError('fluidReference 只能是 mass 或 mole')
    catalog = catalog_map()
    raw_modules = data.get('modules', [])
    if len({m['id'] for m in raw_modules}) != len(raw_modules):
        raise ValueError('模块 ID 重复')
    originals = {m['id']:m for m in raw_modules}
    # Project-owned immutable snapshots take precedence over library drafts/latest releases.
    originals.update(raw.get('moduleSnapshots', {}))
    used_ids = list(dict.fromkeys(n['moduleId'] for pg in raw.get('pages', []) for n in pg.get('nodes', [])))
    definitions, kinds = {}, {}
    for module_id in used_ids:
        original = originals.get(module_id)
        if original is None:
            raise ValueError(f'缺少模块定义：{module_id}')
        kind = original.get('kind', module_id)
        runtime = original.get('runtime', 'builtin')
        if runtime == 'python':
            # The manifest is the source of truth for a versioned package. It
            # is still constrained by the registered hydraulic solver model,
            # but its ports, parameters, channels and source remain intact.
            from .models import ModuleDefinition
            allowed = set(ModuleDefinition.model_fields)
            manifest = deepcopy(original.get('manifest', original))
            if original.get('manifest') and not original.get('frozen'):
                manifest.update(id=module_id, name=original['name'], version=original['version'], source={'runtime':original['source']['runtime']})
                manifest['content_hash'] = original.get('contentHash') if manifest['source'] == original['manifest']['source'] else None
                manifest['ports'] = [{**next((p for p in manifest['ports'] if p['id'] == item['id']), {}),
                                      **{k:item[k] for k in ('id','label','direction','domain')}} for item in original['ports']]
                manifest['channels'] = [{**next((c for c in manifest['channels'] if c['id']==item['id']), {}),
                    'id':item['id'],'name':item['name'],'input_port':item['input'],'output_port':item['output'],
                    'relation':item['kind'],'enabled':item['enabled']} for item in original['channels']]
            definition = ModuleDefinition.model_validate({key: value for key, value in manifest.items() if key in allowed})
            definition.id = module_id
        else:
            if kind not in catalog:
                raise ValueError(f'项目使用的模块 {module_id} ({kind}) 尚未注册求解算法')
            definition = catalog[kind].model_copy(deep=True)
            definition.id, definition.name = module_id, original.get('name', definition.name)
            definition.version = original.get('version', 1)
            definition.source = original.get('source', {})
            definition.bank_names = original.get('bankNames', definition.bank_names)
            if 'ports' in original:
                definition.ports = [PortSpec(id=p['id'], label=p.get('label',p['id']), direction=p['direction'], domain=p['domain'], required=kind not in {'junction','tank'}) for p in original['ports']]
            if 'channels' in original:
                if kind in {'source','junction','tank'} and original['channels']:
                    raise ValueError(f'{module_id} 当前模型不允许额外通路')
                model = 'resistance' if kind == 'exchanger' else definition.solver_model
                definition.channels = [ChannelSpec(id=c['id'], name=c.get('name',c['id']), input_port=c['input'], output_port=c['output'],
                    relation='pump_curve' if model == 'pump_curve' else c.get('kind','resistance'), solver_model=model, enabled=c.get('enabled',True)) for c in original['channels']]
            # Port/variable IDs must remain compatible with the registered model in this version.
            if {p.id for p in definition.ports} != {p.id for p in catalog[kind].ports}:
                raise ValueError(f'{module_id} 的端口 ID 已改变；需要注册对应的声明式模型')
            if {c.id for c in definition.channels} != {c.id for c in catalog[kind].channels}:
                raise ValueError(f'{module_id} 的通路 ID 已改变；需要注册对应的声明式模型')
        definitions[module_id] = type(definition).model_validate(definition.model_dump())
        kinds[module_id] = kind
    instances, connections, diagnostics = [], [], []
    for pg in raw.get('pages', []):
        for node in pg.get('nodes', []):
            module_id = node['moduleId']
            definition, kind = definitions[module_id], kinds[module_id]
            variable_state = node.get('variableState', {})
            banks = []
            for idx, bank in enumerate(variable_state.get('banks', [])):
                params = {k.removeprefix('param:'):v for k,v in bank.items() if k.startswith('param:')}
                names = variable_state.get('bankNames', definition.bank_names)
                banks.append(LibraryBank(name=names[idx] if idx < len(names) else f'库值 {idx+1}', values=parameter_map(kind,params,definition)))
            instances.append(ModuleInstance(id=node['id'], module_id=module_id, name=node.get('name',node['id']), page_id=pg.get('id','main'),
                position=Position(x=node.get('x',0),y=node.get('y',0)), rotation=node.get('rotation',0),
                parameters=parameter_map(kind,node.get('params',{}),definition),
                draft_parameters=parameter_map(kind,node.get('draft',node.get('params',{})),definition), banks=banks,
                model_id=node.get('modelId'), model_version=node.get('modelVersion'),
                package=node.get('package')))
        for edge in pg.get('edges', []):
            if not isinstance(edge,list) or len(edge) != 5:
                raise ValueError(f'原型连接格式无效：{edge}')
            connections.append(Connection(id=edge[0],source=Endpoint(instance_id=edge[1],port_id=edge[2]),target=Endpoint(instance_id=edge[3],port_id=edge[4])))
    solver = raw.get('solver', {})
    diagnostics.append(Diagnostic(code='HYDRAULIC_SCOPE', severity='info', message='按已应用参数计算液态水水力与端口焓、温度；水箱与分段管道在动态计算中按隐式 Euler 积分液位、水温和管内温度；Python 模块包在独立 Worker 中执行；PID 控制器参与动态计算，控制脚本尚未参与求解'))
    return Project(id=raw['id'], name=raw.get('name','原型项目'), description=raw.get('description',''),
        fluid=FluidConfig(fluid=fluid_text or PROTOTYPE_MEDIA[medium], reference=reference),
        modules=list(definitions.values()),instances=instances,connections=connections,import_diagnostics=diagnostics,
        controllers=raw.get('controllers', []),
        solver=SolverOptions(pressure_tolerance_pa=solver.get('pressureAtol',1.),mass_tolerance_kg_s=solver.get('massAtol',1e-8),
                             max_iterations=solver.get('maxIter',80),dynamic_step_s=solver.get('dt',.1)))
