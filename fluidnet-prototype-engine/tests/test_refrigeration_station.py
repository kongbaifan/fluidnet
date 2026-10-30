"""Case-B station: topology rules, conservation and actuator directions, checked from frame data."""
from CoolProp.CoolProp import PropsSI
from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, circuit_info, compile_project
from fn_engine.models import CircuitFluid, Connection, Endpoint, FluidConfig, ModuleInstance, PIDController
from fn_engine.refrigeration.examples import station_example
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed, solve_dynamic, solve_steady
from test_continuous import wait


def run(project, duration=600., dt=600.):
    return solve_dynamic(compile_project(project), duration, dt)


def with_params(**changes):
    project = station_example()
    for instance in project.instances:
        instance.parameters.update(changes.get(instance.id, {}))
    return project


def link(id, a, b):
    return Connection(id=id, source=Endpoint(instance_id=a[0], port_id=a[1]), target=Endpoint(instance_id=b[0], port_id=b[1]))


def test_example_compiles_into_three_pressure_levels_and_two_circuits():
    network = compile_project(station_example())
    assert network.execution_domain == 'refrigeration'
    assert (network.vessel('K1', 'suction'), network.vessel('K1', 'discharge')) == ('LP1', 'HP1')
    assert (network.vessel('EV1', 'in0'), network.vessel('EV1', 'out0')) == ('HP1', 'LP1')
    assert (network.vessel('HX1', 'evap_in'), network.vessel('HX1', 'cond_out')) == ('LP1', 'CD1')
    assert network.vessel('EC1', 'out0') == 'HP1' and network.vessel('AC2', 'out0') == 'CD1'
    assert network.supply == {'AC1': ['PU1'], 'AC2': ['PU1']}
    assert network.room_coolers == {'ROOM1': 'AC1', 'ROOM2': 'AC2'}
    circuits = circuit_info(network)
    assert [c['fluid'].fluid for c in circuits] == ['Ammonia', 'CarbonDioxide']
    assert 'K3:suction' in circuits[0]['ports'] and 'AC1:in0' in circuits[1]['ports']
    # Unused optional header ports are not part of any level.
    assert ('SH1', 'in1') not in network.levels


def mutate(project, drop=(), add=(), instances=(), remove=()):
    project.connections = [c for c in project.connections if c.id not in drop] + list(add)
    project.instances = [i for i in project.instances if i.id not in remove] + list(instances)
    used = {i.module_id for i in project.instances}
    project.modules = [m for m in catalog_map().values() if m.id in used]
    return project


def optional_co2_vapor(project):
    for module in project.modules:
        if module.id == 'pumped_drum':
            module.ports = [p.model_copy(update={'required': False}) if p.id == 'vapor' else p for p in module.ports]
    return project


TOPOLOGY_ERRORS = {
    'REFRIGERATION_CONNECTION_MISSING': lambda p: mutate(p, drop={'c1'}),
    'REFRIGERATION_CONNECTION_INVALID': lambda p: mutate(p, drop={'d4'}, add=[link('bad', ('K4', 'discharge'), ('HP1', 'vapor'))]),
    'REFRIGERATION_PORT_ROLE': lambda p: mutate(p, drop={'s0', 'x1'}, add=[link('s0', ('LP1', 'liquid'), ('SH1', 'in0')),
                                                                         link('x1', ('LP1', 'vapor'), ('HX1', 'evap_in'))]),
    'REFRIGERATION_VESSEL_SHORT': lambda p: mutate(p, add=[link('short', ('HP1', 'vapor'), ('SH1', 'in1'))]),
    'REFRIGERATION_LEVEL_VESSELS': lambda p: mutate(p, instances=[ModuleInstance(id='EC2', module_id='evaporative_condenser', name='x')],
        add=[link('e1', ('HP1', 'vapor'), ('EC2', 'in0')), link('e2', ('EC2', 'out0'), ('LP1', 'in1'))]),
    'REFRIGERATION_LEVEL_NO_VESSEL': lambda p: mutate(p, drop={'d4'}, instances=[ModuleInstance(id='XH', module_id='refrigerant_header', name='x')],
        add=[link('d4', ('K4', 'discharge'), ('XH', 'in0'))]),
    'REFRIGERATION_BRIDGE_SAME_LEVEL': lambda p: mutate(p, drop={'s4', 'd4', 'v2'}, remove={'K4'},
        add=[link('v2', ('EV1', 'out0'), ('DH1', 'in3'))]),
    'REFRIGERATION_CASCADE_CIRCUIT': lambda p: optional_co2_vapor(mutate(p, drop={'x3', 'x4'},
        add=[link('x3', ('HP1', 'vapor'), ('HX1', 'cond_in')), link('x4', ('HX1', 'cond_out'), ('HP1', 'in1'))])),
    'REFRIGERATION_COIL_SUPPLY': lambda p: mutate(p, drop={'p1', 'p2'}, remove={'PU1'}, add=[link('p1', ('CD1', 'liquid'), ('FH1', 'in0'))]),
    # A liquid pipe now belongs to the coupled execution domain and requires an
    # explicit relation. An ideal cold source still is not a station device.
    'COUPLED_RELATION_MISSING': lambda p: mutate(p, instances=[ModuleInstance(id='PIPE', module_id='pipe', name='x')]),
    'REFRIGERATION_MODEL_UNSUPPORTED': lambda p: mutate(p, instances=[ModuleInstance(id='SOURCE', module_id='ideal_cold_source', name='x')]),
}


def edit_module(module_id, **update):
    def apply(project):
        project.modules = [m.model_copy(update=update) if m.id == module_id else m for m in project.modules]
        return project
    return apply


TOPOLOGY_ERRORS |= {
    'REFRIGERATION_PORT_INVALID': lambda p: edit_module('refrigerant_compressor', ports=[
        port.model_copy(update={'circuit': 'other'}) for port in catalog_map()['refrigerant_compressor'].ports])(p),
    'REFRIGERATION_PARAMETER_CONTRACT': lambda p: edit_module('expansion_valve', parameters=[
        spec.model_copy(update={'maximum': 2.}) if spec.id == 'opening_ratio' else spec
        for spec in catalog_map()['expansion_valve'].parameters])(p),
}


@pytest.mark.parametrize('code', TOPOLOGY_ERRORS)
def test_topology_rules_reject_unsupported_stations(code):
    with pytest.raises(CompilationError) as error:
        compile_project(TOPOLOGY_ERRORS[code](station_example()))
    assert error.value.diagnostic.code == code


def test_fluid_and_initial_state_rules():
    project = station_example()
    project.circuit_fluids.append(CircuitFluid(id='w', anchor=Endpoint(instance_id='HP1', port_id='in0'), fluid=FluidConfig(fluid='Water')))
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'FLUID_CONFLICT'
    # No silent fallback: without circuit fluids the project fluid (water) cannot exist at −30 °C.
    project = station_example()
    project.circuit_fluids = []
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert (error.value.diagnostic.code, error.value.diagnostic.instance_id) == ('VESSEL_INITIAL_STATE', 'LP1')
    with pytest.raises(CompilationError) as error:
        compile_project(with_params(CD1={'temperature_k': 310.15}))  # above the CO₂ critical point
    assert (error.value.diagnostic.code, error.value.diagnostic.instance_id) == ('VESSEL_INITIAL_STATE', 'CD1')
    with pytest.raises(CompilationError) as error:
        solve_steady(compile_project(station_example()))
    assert error.value.diagnostic.code == 'REFRIGERATION_DYNAMIC_REQUIRED'


def test_frame_wiring_matches_independent_device_relations():
    """Each device reads the vessel it is connected to: recomputed from frame pressures with PropsSI."""
    v = run(station_example(), 300., 300.)[-1].variables
    p_lp, p_hp, p_co2 = v['LP1.state.pressure_pa'], v['HP1.state.pressure_pa'], v['CD1.state.pressure_pa']
    assert v['LP1.state.temperature_k'] == pytest.approx(PropsSI('T', 'P', p_lp, 'Q', 0, 'Ammonia'), abs=1e-6)
    assert v['CD1.state.temperature_k'] == pytest.approx(PropsSI('T', 'P', p_co2, 'Q', 0, 'CarbonDioxide'), abs=1e-6)
    compressors = [f'K{i}' for i in range(1, 5)]
    rho = PropsSI('D', 'P', p_lp, 'Q', 1, 'Ammonia')
    assert v['K1.mass_flow_kg_s'] == pytest.approx(v['K1.param.displacement_m3_s'] * .8 * .8 * rho, rel=1e-8)
    assert v['K4.mass_flow_kg_s'] == 0. and v['K4.discharge_temperature_k'] is None
    assert v['K1.pressure_ratio'] == pytest.approx(p_hp / p_lp, rel=1e-12)
    assert v['LP1.net_inflow_kg_s'] == pytest.approx(v['EV1.mass_flow_kg_s'] - sum(v[f'{k}.mass_flow_kg_s'] for k in compressors), abs=1e-12)
    assert v['HP1.net_inflow_kg_s'] == pytest.approx(-v['LP1.net_inflow_kg_s'], abs=1e-12)
    assert v['CD1.net_inflow_kg_s'] == 0.
    t_lp, t_co2 = PropsSI('T', 'P', p_lp, 'Q', 0, 'Ammonia'), PropsSI('T', 'P', p_co2, 'Q', 0, 'CarbonDioxide')
    assert v['HX1.heat_w'] == pytest.approx(v['HX1.param.ua_w_k'] * (t_co2 - t_lp), rel=1e-6)
    assert v['EC1.condensing_temperature_k'] == pytest.approx(PropsSI('T', 'P', p_hp, 'Q', 0, 'Ammonia'), abs=1e-6)
    assert v['AC1.supply_mass_flow_kg_s'] == pytest.approx(v['PU1.mass_flow_kg_s'] / 2)
    for i in (1, 2):
        assert v[f'AC{i}.refrigerant_heat_w'] == pytest.approx(
            v[f'AC{i}.param.ua_w_k'] * (v[f'ROOM{i}.state.temperature_k'] - t_co2), rel=1e-6)
        assert v[f'ROOM{i}.cooling_power_w'] == pytest.approx(v[f'AC{i}.refrigerant_heat_w'] - v[f'AC{i}.fan_power_w'])


def stored(v, project):
    rooms = [i.id for i in project.instances if i.module_id == 'cold_room']
    return (sum(v[f'{x}.state.internal_energy_j'] for x in ('LP1', 'HP1', 'CD1'))
            + sum(v[f'{r}.param.heat_capacity_j_k'] * v[f'{r}.state.temperature_k'] for r in rooms))


def boundary(v):
    """Energy crossing the station boundary from the cumulative counters (shaft = motor efficiency × electric)."""
    return (sum(v[f'K{i}.param.motor_efficiency'] * v[f'K{i}.state.electric_energy_j'] for i in range(1, 5))
            + v['PU1.state.electric_energy_j'] - v['EC1.state.heat_rejected_j']
            + sum(v[f'AC{i}.state.fan_energy_j'] + v[f'ROOM{i}.state.external_energy_j'] for i in (1, 2)))


def test_two_hour_run_conserves_both_charges_and_closes_the_energy_ledger():
    project = station_example()
    frames = run(project, 7200., 600.)
    first, last = frames[0].variables, frames[-1].variables
    throughput = last['EC1.state.heat_rejected_j'] + sum(last[f'ROOM{i}.state.external_energy_j'] for i in (1, 2))
    imbalance = stored(last, project) - stored(first, project) - (boundary(last) - boundary(first))
    assert abs(imbalance) < 1e-8 * throughput
    assert abs(frames[-1].metrics['energy_residual_j']) < 1e-8 * throughput
    nh3 = lambda v: v['LP1.state.mass_kg'] + v['HP1.state.mass_kg']
    assert nh3(last) == pytest.approx(nh3(first), rel=1e-12)
    assert last['CD1.state.mass_kg'] == pytest.approx(first['CD1.state.mass_kg'], rel=1e-12)
    assert abs(frames[-1].metrics['mass_residual_kg_circuit0']) < 1e-9
    assert all(f.valid and any(d.code == 'REFRIGERATION_STATION' for d in f.diagnostics) for f in frames)
    # Electric power is the sum over consumers (compressors, condenser fans, pump, coil fans).
    consumers = sum(last[f'K{i}.electric_power_w'] for i in range(1, 5)) + last['EC1.fan_power_w'] + \
        last['PU1.electric_power_w'] + last['AC1.fan_power_w'] + last['AC2.fan_power_w']
    assert frames[-1].metrics['electric_power_w'] == pytest.approx(consumers)


def test_implicit_euler_error_halves_with_the_internal_step():
    finals = []
    for step in (20., 10., 5.):
        project = station_example()
        project.solver.dynamic_step_s = step
        v = run(project, 1800., 1800.)[-1].variables
        finals.append((v['ROOM1.state.temperature_k'], v['LP1.state.pressure_pa'], v['HP1.state.level_ratio']))
    for key in range(3):
        ratio = (finals[0][key] - finals[1][key]) / (finals[1][key] - finals[2][key])
        assert 1.7 < ratio < 2.3


@pytest.mark.parametrize('changes,check', [
    ({f'K{i}': {'load_ratio': 1.} for i in (1, 2, 3)}, lambda a, b: b['LP1.state.pressure_pa'] < a['LP1.state.pressure_pa']),
    ({'EV1': {'opening_ratio': .6}}, lambda a, b: b['HP1.state.level_ratio'] < a['HP1.state.level_ratio']
     and b['LP1.state.level_ratio'] > a['LP1.state.level_ratio']),
    ({'EC1': {'fan_ratio': .5}}, lambda a, b: b['HP1.state.pressure_pa'] > a['HP1.state.pressure_pa']),
    ({'EC1': {'return_gas_ratio': 0.}}, lambda a, b: b['HP1.state.pressure_pa'] > a['HP1.state.pressure_pa']),
    ({'EC1': {'wet_bulb_temperature_k': 303.15}}, lambda a, b: b['HP1.state.pressure_pa'] > a['HP1.state.pressure_pa']),
    ({'PU1': {'speed_ratio': .3}}, lambda a, b: b['ROOM1.state.temperature_k'] > a['ROOM1.state.temperature_k']),
    # Shared cold source: less load from room 1 lets the CO₂ loop run colder, so room 2 cools further.
    ({'AC1': {'fan_ratio': .5}}, lambda a, b: b['ROOM1.state.temperature_k'] > a['ROOM1.state.temperature_k']
     and b['CD1.state.temperature_k'] < a['CD1.state.temperature_k']
     and b['ROOM2.state.temperature_k'] < a['ROOM2.state.temperature_k']),
    ({'AC2': {'supply_valve_ratio': .1}, 'PU1': {'speed_ratio': .4}},
     lambda a, b: b['AC2.supply_mass_flow_kg_s'] < b['AC1.supply_mass_flow_kg_s']),
    ({'ROOM1': {'heat_input_w': 60000.}}, lambda a, b: b['AC1.refrigerant_heat_w'] > a['AC1.refrigerant_heat_w']),
], ids=['load-lowers-suction', 'valve-moves-charge', 'fans-off-raise-head', 'return-gas-closed-floods',
        'wet-bulb-raises-head', 'pump-starves-coils', 'coil-fan-shared-source', 'supply-valve-split', 'room-load-draws-heat'])
def test_actuators_move_the_station_in_the_physical_direction(changes, check):
    base = run(station_example())[-1].variables
    assert check(base, run(with_params(**changes))[-1].variables)


def test_runtime_writes_apply_next_step_and_non_runtime_writes_are_rejected():
    session = create_session(compile_project(station_example()), 120., 60.)
    try:
        first = session.initialize()
        session.write_variables({'K4.param.running': 1., 'K4.param.load_ratio': .5})
        assert session.revision == 1
        frame = session.advance()
        assert frame.variables['K4.mass_flow_kg_s'] > 0 and frame.parameter_revision == 1
        assert first.variables['K4.mass_flow_kg_s'] == 0.
        with pytest.raises(CompilationError) as error:
            session.write_variables({'HP1.param.volume_m3': 2.})
        assert error.value.diagnostic.code == 'PARAMETER_NOT_RUNTIME'
    finally:
        session.close()


def test_level_band_stops_the_run_and_keeps_accepted_frames():
    project = with_params(HP1={'min_level_ratio': .6}, EV1={'kv_m3_h': 3., 'opening_ratio': 1.})
    with pytest.raises(SolveFailed) as error:
        run(project, 600., 10.)
    assert (error.value.diagnostic.code, error.value.diagnostic.instance_id) == ('VESSEL_LEVEL_RANGE', 'HP1')
    assert error.value.frames and all(f.variables['HP1.state.level_ratio'] >= .6 for f in error.value.frames)


def test_every_declared_variable_is_published():
    project = station_example()
    frame = run(project, 60., 60.)[-1]
    modules = {m.id: m for m in project.modules}
    missing = [f'{i.id}.{v.id}' for i in project.instances for v in modules[i.module_id].variables
               if f'{i.id}.{v.id}' not in frame.variables]
    assert not missing


def test_pid_on_compressor_load_runs_inside_the_station():
    project = station_example()
    project.controllers = [PIDController(id='suction', measurement='LP1.state.pressure_pa', instance_id='K1',
                                         parameter_id='load_ratio', setpoint=125000., kp=-2e-4, ki=-2e-6, sample_s=10.,
                                         minimum=0., maximum=1.)]
    frames = run(project, 600., 300.)
    assert frames[-1].variables['K1.param.load_ratio'] != .8
    assert frames[-1].variables['controller.suction.setpoint'] == 125000.


def prototype_export(project):
    definitions = {m.id: m for m in project.modules}
    nodes = []
    for instance in project.instances:
        values = {p.id: p.unit.from_canonical(instance.parameters.get(p.id, p.default)) for p in definitions[instance.module_id].parameters}
        nodes.append({'id': instance.id, 'moduleId': instance.module_id, 'params': values})
    return {'format': 'fluidnet-studio-prototype', 'schema': 1, 'activeProject': project.id,
            'modules': [{'id': m.id, 'kind': m.id, 'runtime': 'builtin', 'name': m.name, 'version': 1,
                         'ports': [{'id': p.id, 'label': p.label, 'direction': p.direction.value, 'domain': p.domain.value}
                                   for p in m.ports], 'channels': []} for m in project.modules],
            'projects': [{'id': project.id, 'name': project.name, 'solver': {'dt': 30},
                          'circuitFluids': [{'id': c.id, 'anchor': c.anchor.model_dump(), 'fluid': c.fluid.fluid}
                                            for c in project.circuit_fluids],
                          'pages': [{'id': 'main', 'nodes': nodes, 'edges': [[c.id, c.source.instance_id, c.source.port_id,
                                    c.target.instance_id, c.target.port_id] for c in project.connections]}]}]}


def test_prototype_export_of_the_station_compiles_to_the_same_run():
    expected = run(station_example(), 60., 60.)[-1].variables
    actual = run(normalize_prototype_export(prototype_export(station_example())), 60., 60.)[-1].variables
    for key in ('LP1.state.pressure_pa', 'HP1.state.level_ratio', 'ROOM1.state.temperature_k', 'HX1.heat_w'):
        assert actual[key] == pytest.approx(expected[key], rel=1e-9)


def test_api_background_run_takes_commands_and_validation_reports_circuits(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        health = client.get('/api/v1/health').json()
        assert 'refrigerant' in health['supported_domains'] and health['capabilities']['refrigeration_station']
        project = station_example().model_dump(mode='json')
        validation = client.post('/api/v1/projects/validate', json=project).json()
        assert [c['fluid']['fluid'] for c in validation['circuits']] == ['Ammonia', 'CarbonDioxide']
        steady = client.post('/api/v1/runs', json={'project': project, 'mode': 'steady'}).json()
        assert steady['frame']['diagnostics'][0]['code'] == 'REFRIGERATION_DYNAMIC_REQUIRED'
        run_id = client.post('/api/v1/runs?background=true', json={'project': project, 'mode': 'dynamic',
                             'duration_s': 120., 'dt_s': 60., 'start_paused': True}).json()['run_id']
        wait(client, run_id, lambda r: r['status'] == 'paused')
        base = '/api/v1/runs/' + run_id
        client.post(base + '/command', json={'action': 'set', 'instance_id': 'K4', 'parameter_id': 'running',
                                           'value': 1.}).raise_for_status()
        client.post(base + '/command', json={'action': 'resume'}).raise_for_status()
        record = wait(client, run_id, lambda r: r['status'] == 'completed')
        assert record['frame']['variables']['K4.mass_flow_kg_s'] > 0
