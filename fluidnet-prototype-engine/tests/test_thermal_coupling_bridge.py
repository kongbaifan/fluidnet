from copy import deepcopy

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from fn_engine.api import create_app
from fn_engine.bridge import PARAMETER_BINDINGS, normalize_prototype_export
from fn_engine.compiler import CompilationError, compile_project, validate_project_details
from fn_engine.models import FluidConfig, Project
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
from fn_engine.solver import solve_steady
from test_continuous import wait


def prototype_case(model=None):
    model = model or thermal_coupling_example()
    definitions = {m.id: m for m in model.modules}

    def parameters(module_id, values):
        names = {value: key for key, value in PARAMETER_BINDINGS[module_id].items()}
        specs = {p.id: p for p in definitions[module_id].parameters}
        return {names[key]: value / specs[key].unit.display_scale + specs[key].unit.display_offset
                if specs[key].unit else value for key, value in values.items()}

    instances = {n.id: n for n in model.instances}
    raw = {'id': model.id, 'name': model.name, 'fluid': model.fluid.fluid,
           'fluidConfig': model.fluid.model_dump(), 'solverOptions': model.solver.model_dump(),
           'thermalCouplings': [c.model_dump() for c in model.thermal_couplings],
           'circuitFluids': [{'id': c.id, 'anchor': c.anchor.model_dump(), 'fluidConfig': c.fluid.model_dump()}
                             for c in model.circuit_fluids],
           'pages': [{'id': 'main', 'nodes': [
               {'id': n.id, 'moduleId': n.module_id, 'params': parameters(n.module_id, n.parameters)}
               for n in model.instances], 'edges': [[c.id, c.source.instance_id, c.source.port_id,
                    c.target.instance_id, c.target.port_id] for c in model.connections]}],
           'scenarios': [{'id': s.id, 'name': s.name, 'overrides': {
               iid: parameters(instances[iid].module_id, values) for iid, values in s.overrides.items()}}
               for s in model.scenarios]}
    return model, {'format': 'fluidnet-studio-prototype', 'schema': 1, 'activeProject': model.id,
                   'projects': [raw], 'modules': [{'id': m.id, 'kind': m.id} for m in model.modules]}


def test_coupled_case_retains_physical_configuration_through_prototype():
    model, payload = prototype_case()
    actual = normalize_prototype_export(payload)
    assert actual.thermal_couplings == model.thermal_couplings
    assert actual.fluid == model.fluid
    assert actual.circuit_fluids == model.circuit_fluids
    assert actual.solver == model.solver
    for old, new in zip(model.instances, actual.instances, strict=True):
        assert old.parameters == new.parameters
    assert actual.scenarios == model.scenarios


def test_visible_solver_controls_override_only_their_fields():
    model, payload = prototype_case()
    raw = payload['projects'][0]
    raw['solverOptions']['max_thermal_iterations'] = 93
    raw['solverOptions']['property_coupling'] = 'node'
    raw['solver'] = {'maxIter': 60, 'pressureAtol': .5, 'hydraulicMethod': 'dense'}
    actual = normalize_prototype_export(payload)
    assert actual.solver.max_iterations == 60
    assert actual.solver.pressure_tolerance_pa == .5
    assert actual.solver.hydraulic_method == 'dense'
    assert actual.solver.dynamic_step_s == model.solver.dynamic_step_s
    assert actual.solver.max_thermal_iterations == 93
    assert actual.solver.property_coupling == 'node'


def test_imported_fluid_composition_and_phase_policy_survive_visible_selectors():
    _, payload = prototype_case()
    raw = payload['projects'][0]
    config = FluidConfig(fluid='R32&R125', composition={'R32': .5, 'R125': .5},
                         reference='mole', phase_policy='liquid').model_dump()
    raw['fluidConfig'] = deepcopy(config)
    raw['fluid'] = config['fluid']
    raw['fluidReference'] = 'mass'
    raw['circuitFluids'][1]['fluidConfig'] = deepcopy(config)
    actual = normalize_prototype_export(payload)
    assert actual.fluid == FluidConfig.model_validate(config | {'reference': 'mass'})
    assert actual.circuit_fluids[1].fluid == FluidConfig.model_validate(config)


def custom_named_case():
    model = thermal_coupling_example()
    rename = {instance.id: 'Plant_' + instance.id for instance in model.instances}
    for instance in model.instances:
        instance.id = rename[instance.id]
    for edge in model.connections:
        edge.source.instance_id = rename[edge.source.instance_id]
        edge.target.instance_id = rename[edge.target.instance_id]
    for circuit in model.circuit_fluids:
        circuit.anchor.instance_id = rename[circuit.anchor.instance_id]
    for scenario in model.scenarios:
        scenario.overrides = {rename[key]: value for key, value in scenario.overrides.items()}
    link = model.thermal_couplings[0]
    link.id = 'Coil_Custom-2'
    link.fluid_instance_id = rename[link.fluid_instance_id]
    link.refrigerant_vessel_id = rename[link.refrigerant_vessel_id]
    return prototype_case(Project.model_validate(model.model_dump()))


def test_custom_identifiers_survive_conversion_and_keep_the_same_physics():
    original = solve_steady(compile_project(thermal_coupling_example()))
    model, payload = custom_named_case()
    actual = normalize_prototype_export(payload)
    assert actual.thermal_couplings == model.thermal_couplings
    assert actual.circuit_fluids == model.circuit_fluids
    assert actual.scenarios == model.scenarios
    assert [node.id for node in actual.instances] == [node.id for node in model.instances]
    frame = solve_steady(compile_project(actual))
    for key in ('heat_w', 'mass_flow_kg_s', 'fluid_inlet_temperature_k', 'fluid_outlet_temperature_k'):
        assert frame.variables['coupling.Coil_Custom-2.' + key] == pytest.approx(
            original.variables['coupling.HX1.' + key], rel=1e-9, abs=1e-6)
    assert not any(key.startswith(('coupling.HX1.', 'HX_W.', 'LP1.')) for key in frame.variables)


def test_missing_relation_is_a_run_diagnostic_and_does_not_reject_drafts():
    _, payload = custom_named_case()
    payload['projects'][0]['thermalCouplings'] = []
    draft = normalize_prototype_export(payload)
    assert Project.model_validate_json(draft.model_dump_json()) == draft
    diagnostics, circuits = validate_project_details(draft)
    assert circuits == []
    assert [item.code for item in diagnostics] == ['COUPLED_RELATION_MISSING']
    assert diagnostics[0].field == 'thermal_couplings'
    assert '尚未建立热耦合' in diagnostics[0].message
    with pytest.raises(CompilationError, match='尚未建立热耦合'):
        compile_project(draft)


def test_draft_and_custom_relation_survive_save_restart_and_saved_run(tmp_path):
    model, payload = custom_named_case()
    link = deepcopy(payload['projects'][0]['thermalCouplings'])
    payload['projects'][0]['thermalCouplings'] = []
    payload.update(models=[], charts={'extra': []})
    with TestClient(create_app(data_root=tmp_path / 'data', module_storage_root=tmp_path / 'modules')) as client:
        saved = client.post('/api/v1/workspace', json={'data': payload, 'expected_revision': 0})
        assert saved.status_code == 200, saved.text
        normalized = client.post('/api/v1/prototype/normalize', json=payload)
        assert normalized.status_code == 200, normalized.text
        checked = client.post('/api/v1/projects/validate', json=normalized.json())
        assert checked.status_code == 200 and not checked.json()['valid']
        assert checked.json()['diagnostics'][0]['code'] == 'COUPLED_RELATION_MISSING'
        refused = client.post('/api/v1/solve', json=normalized.json())
        assert refused.status_code == 422
        assert refused.json()['detail']['code'] == 'COUPLED_RELATION_MISSING'

    with TestClient(create_app(data_root=tmp_path / 'data', module_storage_root=tmp_path / 'modules')) as client:
        stored = client.get('/api/v1/projects/' + model.id).json()
        document = stored['document']
        assert document['project']['thermalCouplings'] == []
        document['project']['thermalCouplings'] = link
        saved = client.post('/api/v1/projects/' + model.id, json={
            'document': document, 'expected_revision': stored['revision']})
        assert saved.status_code == 200, saved.text
        submitted = client.post(f'/api/v1/projects/{model.id}/runs', json={'mode': 'steady'})
        assert submitted.status_code == 202, submitted.text
        record = wait(client, submitted.json()['run_id'], lambda item: item['status'] in {'completed', 'failed'})
        assert record['status'] == 'completed', record.get('frame')
        assert record['request']['project']['thermal_couplings'] == link
        assert record['request']['project']['circuit_fluids'] == [c.model_dump(mode='json') for c in model.circuit_fluids]
        assert record['request']['project']['solver'] == model.solver.model_dump(mode='json')
        assert record['frame']['variables']['coupling.Coil_Custom-2.heat_w'] > 0.


@pytest.mark.parametrize('field,value,code,instance_id', [
    ('fluid_instance_id', 'Plant_LP1', 'COUPLED_TARGET_INVALID', 'Plant_LP1'),
    ('fluid_instance_id', 'Plant_WV1', 'COUPLED_COIL_INVALID', 'Plant_WV1'),
    ('refrigerant_vessel_id', 'Plant_K1', 'COUPLED_TARGET_INVALID', 'Plant_K1'),
    ('fluid_channel_id', 'missing', 'COUPLED_COIL_INVALID', 'Plant_HX_W'),
])
def test_invalid_custom_targets_identify_the_relationship_and_field(field, value, code, instance_id):
    _, payload = custom_named_case()
    payload['projects'][0]['thermalCouplings'][0][field] = value
    project = normalize_prototype_export(payload)
    diagnostics, _ = validate_project_details(project)
    assert diagnostics[0].code == code
    assert diagnostics[0].instance_id == instance_id
    assert diagnostics[0].field == field
    assert 'Coil_Custom-2' in diagnostics[0].message


@pytest.mark.parametrize('value', [-1., float('nan'), float('inf'), float('-inf')])
def test_invalid_coupling_ua_is_rejected_during_normalization(value):
    _, payload = custom_named_case()
    payload['projects'][0]['thermalCouplings'][0]['ua_w_k'] = value
    with pytest.raises(ValidationError) as error:
        normalize_prototype_export(payload)
    assert error.value.errors()[0]['loc'] == ('thermal_couplings', 0, 'ua_w_k')


def test_unknown_custom_target_is_rejected_during_normalization():
    _, payload = custom_named_case()
    payload['projects'][0]['thermalCouplings'][0]['fluid_instance_id'] = 'Deleted_Coil'
    with pytest.raises(ValidationError, match='热耦合引用了不存在的设备'):
        normalize_prototype_export(payload)
