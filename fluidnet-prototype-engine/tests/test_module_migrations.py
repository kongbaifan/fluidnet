from copy import deepcopy

import pytest

from fn_engine.models import ModuleMigration, ModuleDefinition, Scenario, ControlScript
from fn_engine.module_templates import create_template
from fn_engine.projects import upgrade_project
from fn_engine.runtime import module_content_hash, module_definition_hash
from test_module_execution_network import network_for


def renamed():
    original = create_template('managed_state', 'migration_probe', 'Migration')
    project = network_for(original, 2).project
    project.scenarios = [Scenario(id='partial',name='Partial',overrides={'D1':{'opening_ratio':.4}})]
    project.selected_variables = ['D1.in0.pressure_pa', 'D2.main.mass_flow_kg_s']
    target = original.model_copy(deep=True)
    target.version = 2
    target.ports[0].id = 'inlet'
    target.channels[0].input_port = 'inlet'
    for parameter in target.parameters:
        if parameter.id == 'opening_ratio': parameter.id = 'opening'
    target.source['runtime'] = target.source['runtime'].replace("'opening_ratio'", "'opening'").replace("'in0'", "'inlet'")
    target.content_hash, target.definition_hash = module_content_hash(target), module_definition_hash(target)
    target = ModuleDefinition.model_validate(target.model_dump())
    return project, target


def test_rename_all_instances_connections_scenario_and_curve_references_without_mutation():
    project,target = renamed()
    before = deepcopy(project.model_dump())
    result = upgrade_project(project,target,ModuleMigration(parameters={'opening_ratio':'opening'},ports={'in0':'inlet'}))
    assert result['compatible'],result['reasons']
    assert project.model_dump() == before
    candidate = result['project']
    assert all('opening' in node['parameters'] for node in candidate['instances'] if node['module_id']==target.id)
    assert candidate['selected_variables'][0] == 'D1.inlet.pressure_pa'
    assert candidate['scenarios'][0]['overrides']['D1']['opening'] == .4
    assert any(edge['target']['port_id']=='inlet' for edge in candidate['connections'])


def test_script_source_old_strings_reported_and_explicit_author_source_can_resolve():
    project,target = renamed()
    project.control_scripts=[ControlScript(id='control', enabled=False, inputs=['D1.in0.pressure_pa'],source='''
def initialize(ctx): pass
def step(ctx,dt): ctx.read('D1.in0.pressure_pa')
def finalize(ctx): pass
''')]
    spec=ModuleMigration(parameters={'opening_ratio':'opening'},ports={'in0':'inlet'})
    before=project.model_dump()
    result=upgrade_project(project,target,spec)
    assert not result['compatible'] and '源码未自动替换' in result['reasons'][0]
    assert project.model_dump()==before
    spec.script_sources={'control':project.control_scripts[0].source.replace('D1.in0.pressure_pa','D1.inlet.pressure_pa')}
    assert upgrade_project(project,target,spec)['compatible']


@pytest.mark.parametrize('changes', [{'parameters':{'opening_ratio':'kv_m3_h'}}, {'ports':{'in0':'missing'}},
    {'variables':{'main.mass_flow_kg_s':'missing'}}, {'unit_conversions':{'opening_ratio':{'from_unit':'1','to_unit':'1','scale':10}}}])
def test_invalid_and_ambiguous_mapping_leaves_original_project_intact(changes):
    project,target = renamed()
    payload={'parameters':{'opening_ratio':'opening'},'ports':{'in0':'inlet'}}
    payload.update(changes)
    before=project.model_dump()
    result=upgrade_project(project,target,ModuleMigration.model_validate(payload))
    assert not result['compatible'] and project.model_dump()==before
