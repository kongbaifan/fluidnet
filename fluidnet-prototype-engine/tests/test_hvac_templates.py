"""First-batch HVAC completion: terminal templates, makeup water unit and plant interlock.

All cases run through the real compiler, solver and control Workers; reference values are
computed here from first principles, never read back from the module under test.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.hvac_basic import equipment_definitions
from fn_engine.hvac_examples import HVAC_EXAMPLES, hvac_example
from fn_engine.models import CircuitFluid, Connection, Endpoint, FluidConfig, Project
from fn_engine.packages import load_module_package
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_IDS = ('ahu_standard', 'fahu_standard', 'fcu_terminal')


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path)) as test_client:
        yield test_client


def module(kind):
    return load_module_package(ROOT/'modules'/kind)


def air_network(terminal, air_in_parameters):
    """进风边界 → 末端 → 出风边界，冷冻水为独立开式回路。"""
    catalog = catalog_map()
    terminal_module = module(terminal)
    ports = {port.id for port in terminal_module.ports}
    air_in_port = 'air_in' if 'air_in' in ports else 'return_in'
    air_out_port = 'air_out' if 'air_out' in ports else 'supply_out'
    instances = [
        {'id':'AirIn','module_id':'source','name':'进风','parameters':air_in_parameters},
        {'id':'AirOut','module_id':'source','name':'出风','parameters':{'pressure_pa':101325.}},
        {'id':'WaterIn','module_id':'source','name':'供水','parameters':{'pressure_pa':300000.,'temperature_k':280.15}},
        {'id':'WaterOut','module_id':'source','name':'回水','parameters':{'pressure_pa':240000.,'temperature_k':285.15}},
        {'id':'T','module_id':terminal,'name':'末端'}]
    links = [(('AirIn','out0'),('T',air_in_port)), (('T',air_out_port),('AirOut','out0')),
             (('WaterIn','out0'),('T','water_in')), (('T','water_out'),('WaterOut','out0'))]
    return Project(id='terminal-network', name='末端模板', fluid={'fluid':'Air','phase_policy':'gas'},
        modules=[catalog['source'], terminal_module], instances=instances,
        connections=[Connection(id=f'c{index}', source=Endpoint(instance_id=start[0], port_id=start[1]),
                                target=Endpoint(instance_id=end[0], port_id=end[1]))
                     for index, (start, end) in enumerate(links)],
        circuit_fluids=[CircuitFluid(id='chilled-water', anchor=Endpoint(instance_id='T', port_id='water_in'),
                                     fluid=FluidConfig(fluid='Water', phase_policy='liquid'))],
        solver={'moist_air':True,'moist_air_options':{'contract_version':1},
                'thermal':True,'property_coupling':'node','module_cache':False})


def dynamic_frames(project, duration_s, step_s):
    session = SimulationSession(compile_project(project), duration_s, step_s)
    try:
        session.initialize()
        return [session.advance() for _ in range(int(duration_s/step_s))]
    finally:
        session.close()


def test_terminal_templates_are_published_in_the_module_catalog(client):
    modules = {item['id']: item for item in client.get('/api/v1/modules').json()['modules']}
    for identifier, ports in (('ahu_standard', {'fresh_in','return_in','supply_out','water_in','water_out'}),
                              ('fahu_standard', {'air_in','air_out','water_in','water_out'}),
                              ('fcu_terminal', {'return_in','supply_out','water_in','water_out'}),
                              ('makeup_water_unit', {'makeup_in','supply_out'})):
        item = modules[identifier]
        assert item['category'] == '暖通基础设备'
        assert {port['id'] for port in item['ports']} == ports


def test_templates_compose_public_equipment_and_keep_sources_outside():
    definitions = {module.id: module for module in equipment_definitions()}
    children = {identifier: {child.id: child.module_id for child in definitions[identifier].composite.children}
                for identifier in (*TERMINAL_IDS, 'makeup_water_unit')}
    assert children['ahu_standard'] == {'Mix':'air_mixing_box','Filter':'air_filter','Coil':'water_coil','Fan':'fan'}
    assert children['fahu_standard'] == {'Filter':'air_filter','Coil':'water_coil','Fan':'fan'}
    assert children['fcu_terminal'] == children['fahu_standard']
    assert children['makeup_water_unit'] == {'Strainer':'water_strainer','Check':'hvac_check_valve',
                                             'Balance':'water_balancing_valve'}
    # 组合展开拒绝内置压力源：定压补水边界必须留在组合外部。
    assert not any('source' in values for values in children.values())


@pytest.mark.parametrize('terminal', ['fahu_standard', 'fcu_terminal'])
def test_terminal_template_cools_and_dehumidifies_outdoor_air(terminal):
    frame = solve_steady(compile_project(air_network(
        terminal, {'pressure_pa':101325.,'temperature_k':305.15,'humidity_ratio_kg_kg':.014})))
    values = frame.variables
    assert frame.valid, [diagnostic.message for diagnostic in frame.diagnostics]
    inlet = 'air_in' if terminal == 'fahu_standard' else 'return_in'
    outlet = 'air_out' if terminal == 'fahu_standard' else 'supply_out'
    assert values[f'T.{inlet}.temperature_k'] > 300.
    assert values[f'T.{outlet}.temperature_k'] < values[f'T.{inlet}.temperature_k'] - 5.
    assert values[f'T.{outlet}.humidity_ratio_kg_kg'] < values[f'T.{inlet}.humidity_ratio_kg_kg']
    # 冷冻水吸热升温，热量与质量守恒由全网独立残差校核。
    assert values['T.water_out.temperature_k'] > values['T.water_in.temperature_k'] + .1
    assert abs(frame.metrics['energy_residual_w']) < .05
    assert frame.metrics['mass_residual_kg_s'] < 1e-7


def test_ahu_example_feeds_the_room_with_conditioned_air():
    frame = solve_steady(compile_project(hvac_example('hvac-ahu-terminal')))
    values = frame.variables
    assert frame.valid
    assert values['Room.supply_in.mass_flow_kg_s'] == pytest.approx(-values['Room.return_out.mass_flow_kg_s'], rel=1e-3)
    assert values['Room.supply_in.temperature_k'] < values['Room.state.temperature_k']
    # 测点与独立水侧焓差核算一致：m·Δh 就是盘管制冷量。
    water_mass = values['AHU.water_in.mass_flow_kg_s']
    independent = water_mass*(values['AHU.water_out.enthalpy_j_kg'] - values['AHU.water_in.enthalpy_j_kg'])
    assert values['measurement.coil-cooling-power'] == pytest.approx(independent, rel=1e-6)
    assert values['measurement.coil-cooling-power'] > 1000.
    assert values['measurement.chilled-water-delta-t'] > 1.
    assert values['measurement.supply-air-volume-flow'] > .5
    assert values['measurement.room-temperature'] == pytest.approx(values['Room.state.temperature_k'], rel=1e-9)


@pytest.mark.parametrize('opening', [.02, .1, .6])
def test_makeup_water_matches_the_leak_through_the_real_network(opening):
    project = hvac_example('hvac-closed-loop-makeup')
    next(instance for instance in project.instances if instance.id == 'Leak').parameters['opening_ratio'] = opening
    frame = dynamic_frames(project, 20., 1.)[-1]
    values = frame.variables
    assert frame.valid
    # 闭式回路里补水必须等于泄漏，否则质量不守恒。
    assert values['measurement.makeup-flow'] > 0
    assert values['measurement.makeup-flow'] == pytest.approx(values['measurement.leak-flow'], rel=2e-2)
    assert values['measurement.loop-dp'] > 1000.
    # 补水阀只取全开／最小开度两个位置；回差带内保持上一状态，因此这里只校验控制律输出合法。
    assert values['Makeup.param.Balance_opening_ratio'] in (pytest.approx(.1), pytest.approx(1.))
    assert values['Makeup.state.Check.throughput_kg'] > 0


def test_makeup_unit_keeps_the_pressure_reference_outside_the_composition():
    project = hvac_example('hvac-closed-loop-makeup')
    # 组合里没有压力边界；定压由外部 MakeupSource 提供。
    assert any(instance.id == 'MakeupSource' and instance.module_id == 'source' for instance in project.instances)
    assert any(instance.id == 'Makeup' and instance.module_id == 'makeup_water_unit' for instance in project.instances)
    project.control_scripts = []
    frame = solve_steady(compile_project(project))
    values = frame.variables
    assert frame.valid
    assert values['measurement.makeup-flow'] == pytest.approx(values['measurement.leak-flow'], rel=2e-2)


def test_plant_interlock_starts_pump_one_then_switches_to_the_standby():
    frames = dynamic_frames(hvac_example('hvac-plant-interlock'), 16., 1.)
    for index, frame in enumerate(frames):
        values = frame.variables
        assert frame.valid
        if 2 <= index < 10:
            # 压差确认通过后 1 号泵单独运行，止回阀导通。
            assert values['Pump1.param.running'] == pytest.approx(1.)
            assert values['Pump2.param.running'] == pytest.approx(0.)
            assert abs(values['Pump1.main.mass_flow_kg_s']) > .5
        if index >= 11:
            # 切换顺序：2 号泵投入，1 号泵停止，止回阀截止。
            assert values['Pump1.param.running'] == pytest.approx(0.)
            assert values['Pump2.param.running'] == pytest.approx(1.)
            assert abs(values['Pump2.main.mass_flow_kg_s']) > .5
            assert abs(values['Pump1.main.mass_flow_kg_s']) < 1e-6
    assert frames[-1].variables['script.plant-interlock.state.phase'] == 'running'


def test_plant_interlock_trips_when_the_confirmed_pressure_never_arrives():
    project = hvac_example('hvac-plant-interlock')
    next(instance for instance in project.instances if instance.id == 'Pump1').parameters['head_curve'] = \
        [[0., 2.], [5., 1.], [10., 0.]]
    frames = dynamic_frames(project, 12., 1.)
    last = frames[-1].variables
    assert last['Pump1.param.running'] == pytest.approx(0.)
    assert last['Pump2.param.running'] == pytest.approx(0.)
    assert abs(last['Pump1.main.mass_flow_kg_s']) < 1e-3
    assert last['script.plant-interlock.state.phase'] == 'tripped'


def test_first_batch_examples_are_portable():
    for name in ('hvac-ahu-terminal', 'hvac-closed-loop-makeup', 'hvac-plant-interlock'):
        assert name in HVAC_EXAMPLES
        assert (ROOT/'examples/hvac-basic'/(name + '.project.json')).exists()


def test_control_template_file_is_valid_python_and_keeps_the_sequence():
    source = (ROOT/'examples/control_templates/plant_interlock.py').read_text(encoding='utf-8')
    compile(source, 'plant_interlock.py', 'exec')
    for keyword in ('initialize', 'step', 'finalize', 'tripped', 'switched', 'MIN_DP_PA'):
        assert keyword in source
