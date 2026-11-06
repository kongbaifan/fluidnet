"""P1 open groups keep the complete host physics and immutable child contracts."""
from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.bench import run_module_test
from fn_engine.compiler import compile_project
from fn_engine.composites import module_from_group, OPEN_REFRIGERATION_CAPABILITY
from fn_engine.models import (CircuitFluid, CompositeTestContextRequest, Direction, Domain, Endpoint, ModuleSaveRequest,
    ModuleTestConditions, ModuleTestRequest, Project)
from fn_engine.packages import ModuleStore
from fn_engine.refrigeration.forward_examples import headed_example
from fn_engine.refrigeration.group_examples import GROUPS, open_group_example, grouped_station_example
from fn_engine.refrigeration.group_testing import replace_with_group, test_context as make_context
from fn_engine.sessions import create_session

ROOT = Path(__file__).resolve().parents[1]


def run(project, duration=.2, dt=.1):
    session = create_session(compile_project(project), duration, dt)
    try:
        session.initialize()
        while not session.done:
            session.advance()
        return session.frames
    finally:
        session.close()


@pytest.mark.parametrize('kind', GROUPS)
def test_real_external_connections_match_every_manual_device_value_and_conserve(kind):
    source, module, host = open_group_example(kind)
    assert module.sdk.api_version == '0.10.0'
    assert OPEN_REFRIGERATION_CAPABILITY in module.sdk.capabilities
    assert module.ports and not module.channels
    assert 'fluid' not in {p.domain for p in module.ports}
    selected = set(GROUPS[kind][1])
    network = compile_project(host)
    assert not network.composite_maps['channels']
    assert set(network.vessels) == {'Low', 'High'}
    assert set(network.room_cooler_groups) == {'Room-1', 'Room-2'}
    for expected, actual in zip(run(source), run(Project.model_validate_json(host.model_dump_json())), strict=True):
        assert actual.valid and actual.time_s == expected.time_s
        for key, value in expected.variables.items():
            iid, _, tail = key.partition('.')
            target = ('D1__'+iid if iid in selected else iid)+'.'+tail
            if isinstance(value, (int, float)):
                assert actual.variables[target] == pytest.approx(value, rel=2e-8, abs=2e-6), key
            else:
                assert actual.variables[target] == value, key
        for public, leaf in module.composite.output_aliases.items():
            assert actual.variables['D1.'+public] == pytest.approx(expected.variables[leaf], rel=2e-8, abs=2e-6)
        assert abs(actual.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert abs(actual.metrics['energy_residual_w']) < .02


def test_all_three_groups_build_one_station_with_external_storage():
    host = grouped_station_example()
    frame = run(host)[-1]
    assert frame.valid
    for key in host.selected_variables:
        assert key in frame.variables
    assert len(compile_project(host).vessels) == 2


def test_duplicate_group_instances_keep_parameters_and_cumulative_states_independent():
    _, module, host = open_group_example('liquid-supply')
    def renamed(prefix):
        p = host.model_copy(deep=True)
        for i in p.instances:
            i.id = prefix+i.id
        for c in p.connections:
            c.id = prefix+c.id
            c.source.instance_id = prefix+c.source.instance_id
            c.target.instance_id = prefix+c.target.instance_id
        return p
    project, other = renamed('A'), renamed('B')
    project.instances.extend(other.instances)
    project.connections.extend(other.connections)
    s = create_session(compile_project(project), .2, .1)
    try:
        s.initialize()
        s.set_parameter('AD1', 'Pump_speed_ratio', .05)
        frame = s.advance()
        assert s.network.parameters['AD1__Pump']['speed_ratio'] == .05
        assert s.network.parameters['BD1__Pump']['speed_ratio'] == 1.
        assert frame.variables['AD1.Pump.mass_flow_kg_s'] < frame.variables['BD1.Pump.mass_flow_kg_s']
        assert frame.variables['AD1.state.Pump.electric_energy_j'] < frame.variables['BD1.state.Pump.electric_energy_j']
        assert frame.variables['ARoom-1.state.temperature_k'] > frame.variables['BRoom-1.state.temperature_k']
        for circuit in (0, 1):
            assert abs(frame.metrics[f'mass_residual_kg_circuit{circuit}']) < 1e-8
    finally:
        s.close()


@pytest.mark.parametrize('fault', ['version', 'sdk-version', 'fluid', 'anchor-fluid', 'direction', 'domain', 'required', 'hidden-required', 'old-capability', 'missing-connection', 'unknown-parameter'])
def test_invalid_open_group_contracts_are_rejected_before_running(fault):
    _, _, project = open_group_example('air-coolers')
    module = project.modules[-1]
    if fault == 'version':
        module.composite.children[0].version += 1
    elif fault == 'sdk-version':
        module.sdk.api_version = '0.9.0'
    elif fault == 'fluid':
        project.fluid.fluid = 'Ammonia'
    elif fault == 'anchor-fluid':
        project.circuit_fluids = [CircuitFluid(id='wrong', anchor=Endpoint(instance_id='Low', port_id='liquid'),
            fluid={'fluid':'Ammonia', 'phase_policy':'any'})]
    elif fault == 'direction':
        module.ports[0].direction = Direction.out
    elif fault == 'domain':
        module.ports[0].domain = Domain.fluid
    elif fault == 'required':
        module.ports[0].required = False
    elif fault == 'hidden-required':
        port = module.ports.pop(0)
        del module.composite.external_ports[port.id]
        project.connections = [c for c in project.connections if c.target.port_id != port.id]
    elif fault == 'missing-connection':
        project.connections = [c for c in project.connections if c.target.port_id != 'Cooler-1_in0']
    elif fault == 'unknown-parameter':
        project.instances[-1].parameters['not_a_parameter'] = 1
    else:
        module.sdk.api_version = '0.9.0'
        module.sdk.capabilities = ['composite.v1', 'composite.refrigeration.v1']
    with pytest.raises(ValueError):
        compile_project(project)


def test_factory_rejects_container_partial_group_and_duplicate_selection():
    source, _, _ = open_group_example('compressors')
    with pytest.raises(ValueError, match='容器'):
        module_from_group(source, ['Low'], 'bad_vessel', 'bad')
    with pytest.raises(ValueError, match='重复'):
        module_from_group(source, ['Pump', 'Pump'], 'bad_repeat', 'bad')


def test_host_context_preserves_anchor_and_public_variable_references():
    source, module, _ = open_group_example('air-coolers')
    source.circuit_fluids = [CircuitFluid(id='refrigerant', anchor=Endpoint(instance_id='Cooler-1', port_id='in0'), fluid=source.fluid)]
    source.selected_variables = ['Cooler-1.room_cooling_w', 'Cooler-1.param.fan_ratio']
    context = make_context(CompositeTestContextRequest(project=source, instance_ids=GROUPS['air-coolers'][1], module=module))
    host = context.host_project
    assert host.circuit_fluids[0].anchor == Endpoint(instance_id='D1', port_id='Cooler-1_in0')
    assert host.selected_variables == ['D1.Cooler-1.room_cooling_w', 'D1.param.Cooler-1_fan_ratio']
    assert run_module_test(ModuleTestRequest(module=module, **context.model_dump())).frame.valid


def test_host_bench_rejects_absent_host_and_checks_current_candidate_not_old_definition():
    _, module, host = open_group_example('liquid-supply')
    with pytest.raises(ValueError, match='宿主'):
        run_module_test(ModuleTestRequest(module=module))
    candidate = module.model_copy(deep=True)
    next(p for p in candidate.parameters if p.id == 'Pump_speed_ratio').default = .6
    result = run_module_test(ModuleTestRequest(module=candidate, host_project=host, fluid=host.fluid))
    assert result.frame.variables['D1.param.Pump_speed_ratio'] == .6
    assert result.frame.variables['D1.Pump.mass_flow_kg_s'] == pytest.approx(.24*.6)
    assert next(p for p in host.modules[-1].parameters if p.id == 'Pump_speed_ratio').default == 1.
    candidate.composite.children[0].version += 1
    with pytest.raises(ValueError, match='版本'):
        run_module_test(ModuleTestRequest(module=candidate, host_project=host, fluid=host.fluid))


@pytest.mark.parametrize('kind', GROUPS)
def test_publish_reload_has_real_host_receipt_and_current_version(tmp_path, kind):
    _, module, host = open_group_example(kind)
    conditions = ModuleTestConditions(host_project=host, fluid=host.fluid)
    store = ModuleStore(tmp_path/'seeds', tmp_path/'store')
    release = store.save(ModuleSaveRequest(module=module, expected_latest_version=0, test=conditions))
    restored = ModuleStore(tmp_path/'seeds', tmp_path/'store').get(module.id, 1)
    assert restored.module.definition_hash == release.module.definition_hash
    receipt = json.loads((tmp_path/'store'/f'module-{module.id}'/'v1'/'release.json').read_text(encoding='utf-8'))
    assert receipt['test_conditions']['host_project']['id'] == host.id
    assert receipt['test_result']['frame']['valid']
    assert receipt['validation_evidence'][0]['sdk_version'] == '0.10.0'


def test_failed_actual_host_step_rolls_back_all_physics_and_retains_accepted_public_command():
    source = headed_example()
    next(i for i in source.instances if i.id == 'Compressor').parameters['max_pressure_ratio'] = 1.
    module = module_from_group(source, ['Compressor'], 'open_rollback', 'rollback')
    s = create_session(compile_project(replace_with_group(source, ['Compressor'], module)), .3, .1)
    try:
        first = s.initialize()
        diagnostic = next(d for d in first.diagnostics if d.code == 'COMPRESSOR_ENVELOPE')
        assert diagnostic.instance_id == 'D1' and diagnostic.source_path == 'D1.Compressor'
        s.advance()
        s.set_parameter('D1', 'Compressor_load_ratio', .6)
        before = deepcopy((s.masses, s.energies, s.temperatures, s.counters, s.time, s.revision))
        s.network.parameters['High']['tap0_height_ratio'] = .95
        s._cache = None
        with pytest.raises(Exception, match='需要liquid'):
            s.advance()
        assert (s.masses, s.energies, s.temperatures, s.counters, s.time, s.revision) == before
        assert s.network.parameters['D1__Compressor']['load_ratio'] == .6
        assert s.frames[-1].time_s == .1
    finally:
        s.close()


def test_context_api_and_frozen_portable_examples(tmp_path):
    source, module, host = open_group_example('air-coolers')
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/modules/composites/test-context', json={
            'project':source.model_dump(mode='json'), 'instance_ids':GROUPS['air-coolers'][1], 'module':module.model_dump(mode='json')})
        assert response.status_code == 200, response.text
        conditions = ModuleTestConditions.model_validate(response.json())
        assert conditions.host_project.instances[-1].id == 'D1'
        example = client.get('/api/v1/examples/refrigeration-open-group-station')
        assert example.status_code == 200 and example.json()['id'] == 'open-group-station'
    folder = ROOT/'examples/open-refrigeration-groups'
    assert Project.model_validate_json((folder/'air-coolers.project.json').read_text(encoding='utf-8')) == host
    assert Project.model_validate_json((folder/'grouped-station.project.json').read_text(encoding='utf-8')) == grouped_station_example()


@pytest.mark.parametrize('phase', ['initialize', 'advance'])
def test_child_device_failures_map_to_public_group_without_accepting_state(monkeypatch, phase):
    from fn_engine.refrigeration import devices
    from fn_engine.solver import SolveFailed
    _, _, host = open_group_example('compressors')
    s = create_session(compile_project(host), .2, .1)
    try:
        if phase == 'advance':
            s.initialize()
            s.advance()
        before = deepcopy((s.time, s.masses, s.energies, s.counters))
        def failure(*args):
            raise devices.DeviceRangeError('TEST_COMPRESSOR_FAILURE', 'injected leaf failure')
        monkeypatch.setattr(devices, 'compressor_point', failure)
        s._cache = None
        with pytest.raises(SolveFailed) as error:
            s.initialize() if phase == 'initialize' else s.advance()
        assert error.value.diagnostic.instance_id == 'D1'
        assert error.value.diagnostic.source_path == 'D1.Compressor-1'
        assert (s.time, s.masses, s.energies, s.counters) == before
    finally:
        s.close()
