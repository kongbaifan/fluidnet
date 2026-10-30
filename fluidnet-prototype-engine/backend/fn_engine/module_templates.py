"""Runnable authoring templates with canonical units and explicit reference boundaries."""
from copy import deepcopy
from pathlib import Path

from .models import ModuleDefinition, ModuleTestConditions
from .packages import load_module_package

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = {
    'resistance': {'name': '两端口局部阻力', 'description': 'K 阻力关系及通过质量累计。'},
    'pump': {'name': '泵／风机', 'description': '流量扬程曲线和可调转速；边界为入口低压、出口高压。'},
    'heat_exchanger': {'name': '双侧换热', 'description': '两侧独立工质的单相显热 ε–NTU 模型。'},
    'managed_state': {'name': '受管理状态', 'description': '显式离散累计量；只在接受子步累计，不作为隐式热容。'},
    'refrigeration_throttle': {'name':'制冷等焓节流阀','description':'饱和液体等焓节流；线性或等百分比开度特性，可用于集总制冷站。'},
}


def template_conditions(template):
    if template=='refrigeration_throttle':
        return ModuleTestConditions(fluid={'fluid':'Ammonia','phase_policy':'any'},inlet_pressure_pa=1350000.,outlet_pressure_pa=110000.)
    if template == 'pump':
        return ModuleTestConditions(inlet_pressure_pa=120000., outlet_pressure_pa=250000.)
    if template == 'heat_exchanger':
        return ModuleTestConditions(channel_boundaries={
            'hot': {'inlet_temperature_k': 320., 'outlet_temperature_k': 320.},
            'cold': {'inlet_temperature_k': 290., 'outlet_temperature_k': 290.}})
    return ModuleTestConditions()


def create_template(template, identifier, name, category='自定义模块'):
    if template not in TEMPLATES:
        raise ValueError('未知模块模板')
    if template=='refrigeration_throttle':
        base=load_module_package(ROOT/'modules/isenthalpic_throttle')
        return ModuleDefinition.model_validate({**base.model_dump(mode='json'),'id':identifier,'name':name,'category':category,
            'version':1,'package_path':None,'content_hash':None,'definition_hash':None})
    base = load_module_package(ROOT / 'modules' / ('sdk_resistance' if template == 'resistance' else 'programmable_valve_sdk'))
    payload = base.model_dump(mode='json')
    payload.update(schema_version=3,id=identifier, name=name, category=category, version=1, content_hash=None, definition_hash=None,
        package_path=None, sdk={'api_version':'0.5.0', 'capabilities':['state.transactions.v1']})
    if template == 'resistance':
        payload['sdk']['capabilities'].append('net.resistance')
        payload['sdk']['capabilities'].append('hydraulic.signed_start.v1')
    elif template == 'managed_state':
        payload['sdk']['capabilities'].append('net.valve')
        payload['sdk']['capabilities'].append('hydraulic.signed_start.v1')
    elif template == 'pump':
        payload['parameters'] = [
            {'id':'head_curve', 'label':'体积流量 m³/h—扬程 m', 'value_type':'curve', 'default':[[0,25],[30,15],[60,0]]},
            {'id':'speed_ratio', 'label':'转速比例', 'default':1., 'minimum':.1, 'maximum':2., 'runtime':True}]
        payload['variables'] = [{'id':'speed', 'label':'有效转速比例', 'quantity':'ratio', 'source':'derived'}]
        payload['channels'][0]['solver_model'] = 'pump_curve'
        payload['solver_model'] = 'generic'
        payload['sdk']['capabilities'].append('net.pump')
        payload['source'] = {'runtime': '''class Module:
    def initialize(self,ctx): pass
    def evaluate(self,ctx):
        ctx.net.pump(channel='main',head_curve=ctx.parameter('head_curve'),speed_ratio=ctx.parameter('speed_ratio'),density_kg_m3=ctx.port('in0').density_kg_m3)
        ctx.var('speed',ctx.parameter('speed_ratio'))
    def commit_step(self,ctx,dt): pass
    def finalize(self,ctx): pass
'''}
    else:
        payload['ports'] = [{'id':f'{side}_{direction}', 'label':f'{side} {direction}', 'direction':'in' if direction == 'in' else 'out',
            'circuit':side} for side in ['hot','cold'] for direction in ['in','out']]
        payload['channels'] = [{'id':side, 'name':side, 'input_port':f'{side}_in', 'output_port':f'{side}_out',
            'solver_model':'generic', 'relation':'resistance'} for side in ['hot','cold']]
        payload['parameters'] = [
            {'id':'diameter_m','label':'通路直径','default':.03,'minimum':.0001,
                'unit':{'quantity':'length','canonical_unit':'m','display_unit':'mm','display_scale':.001}},
            {'id':'loss_coefficient','label':'局部阻力系数','default':10.,'minimum':.001},
            {'id':'ua_w_k','label':'UA','default':100.,'minimum':0.,'runtime':True,
                'unit':{'quantity':'conductance','canonical_unit':'W/K','display_unit':'W/K'}}]
        payload['variables'] = [
            {'id':'transferred_heat_w','label':'冷侧获得热流','quantity':'power','source':'derived'},
            {'id':'state.transferred_energy_j','label':'累计冷侧热量','quantity':'energy','source':'state'}]
        payload['solver_model'] = 'generic'
        payload['sdk']['capabilities'] += ['net.resistance', 'thermal.v1', 'observe.v1', 'thermal.conservative.v1']
        payload['source'] = {'runtime':(ROOT / 'examples/module_templates/dual_heat_exchanger.py').read_text(encoding='utf-8')}
    payload['description'] = TEMPLATES[template]['description']
    return ModuleDefinition.model_validate(deepcopy(payload))
