"""Real compiler/solver/session checks, including independent balances of all three circuits."""
import csv
from io import StringIO

from fastapi.testclient import TestClient
import pytest

from fn_engine.air_examples import air_example
from fn_engine.air_variables import collect_air_variables, make_air_metadata
from fn_engine.api import create_app
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project, SolverOptions
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady


@pytest.fixture(scope='module')
def complete():
    project = air_example('chiller-air-loop')
    network = compile_project(project)
    return project, network, solve_steady(network)


def test_all_circuits_close_without_a_fictitious_heat_reference(complete):
    _, _, frame = complete
    v = frame.variables
    assert frame.valid and frame.metrics['reference_heat_w'] == 0
    assert v['Chiller.cooling_power_w'] > 10000 and 0 < v['Chiller.load_ratio'] < 1
    assert v['Chiller.out0.temperature_k'] == pytest.approx(280.15, abs=1e-5)
    assert v['Coil.in1.temperature_k'] < v['Coil.out1.temperature_k']
    assert v['Coil.in0.temperature_k'] > v['Coil.out0.temperature_k']
    assert v['Coil.condensate_kg_s'] > 0
    # Closed water loops have zero exchange at the pressure-reference branch.
    assert abs(v['ChilledRef.out0.mass_flow_kg_s']) < 1e-10
    assert abs(v['CoolingRef.out0.mass_flow_kg_s']) < 1e-10
    assert v['Chiller.cooling_power_w'] == pytest.approx(v['Coil.water_heat_w']+v['ChilledPump.shaft_power_w'], abs=.03)
    assert v['Tower.heat_rejected_w'] == pytest.approx(v['Chiller.condenser_heat_w']+v['CoolingPump.shaft_power_w'], abs=.03)
    assert v['Chiller.condenser_heat_w'] == pytest.approx(v['Chiller.cooling_power_w']+v['Chiller.shaft_power_w'], abs=1e-7)
    assert v['Chiller.electric_power_w'] > v['Chiller.shaft_power_w']


def test_independent_air_water_and_energy_books(complete):
    project, _, frame = complete
    v = frame.variables
    water = energy = 0.
    for inst in project.instances:
        if inst.module_id == 'source':
            key = inst.id+'.out0.'
            energy -= v[key+'mass_flow_kg_s']*v[key+'enthalpy_j_kg']
            water -= v.get(key+'water_vapor_mass_flow_kg_s', 0.)
    water += v['Room.moisture_load_kg_s']-v['Coil.condensate_kg_s']
    from fn_engine.moist_air import vapor_enthalpy
    params = next(i.parameters for i in project.instances if i.id == 'Room')
    energy += v['Room.sensible_load_w']+v['Room.moisture_load_kg_s']*vapor_enthalpy(307.15)+v['Room.envelope_heat_w']
    assert params['sensible_load_w'] == v['Room.sensible_load_w']
    energy += v['Fan.heat_w']+v['ChilledPump.shaft_power_w']+v['CoolingPump.shaft_power_w']
    energy += v['Chiller.shaft_power_w']-v['Tower.heat_rejected_w']-v['Coil.condensate_enthalpy_flow_w']
    assert abs(water) < 3e-9
    assert abs(energy) < .04


def test_liquid_ports_never_claim_dry_air_flow_or_humidity(complete):
    project, network, frame = complete
    v = frame.variables
    catalog = {d.key:d for d in collect_air_variables(project)}
    assert len(network.circuit_fluids) == 3
    assert v['Coil.ch0.dry_air_mass_flow_kg_s'] > 0
    assert 'Coil.ch1.dry_air_mass_flow_kg_s' not in v
    assert 'Chiller.in0.humidity_ratio_kg_kg' not in v
    assert 'Chiller.in0.humidity_ratio_kg_kg' not in catalog
    assert catalog['Chiller.in0.mass_flow_kg_s'].mass_basis == 'water'
    assert catalog['Coil.in0.mass_flow_kg_s'].mass_basis == 'mixture'
    assert catalog['Chiller.capacity_limited'].value_type == 'boolean'
    assert catalog['Coil.wet_fraction'].unit.display_unit == '%'
    assert make_air_metadata(project)['continuity_basis'] == 'mixed'
    assert frame.solve_summary['continuity_basis'] == 'mixed'


def water_only_project():
    catalog = catalog_map()
    instances = [ModuleInstance(id='Chiller', module_id='water_chiller', name='水冷机组')]
    connections = []
    for iid, port, pressure, temperature in (('A','in0',201000.,285.15), ('B','out0',200000.,280.15),
                                            ('C','in1',201000.,303.15), ('D','out1',200000.,308.15)):
        instances.append(ModuleInstance(id=iid,module_id='source',name=iid,
            parameters={'pressure_pa':pressure,'temperature_k':temperature}))
        connections.append(Connection(id=iid,source=Endpoint(instance_id=iid,port_id='out0'),
                                      target=Endpoint(instance_id='Chiller',port_id=port)))
    return Project(id='water-chiller-test',name='独立水冷机组',modules=[catalog['source'],catalog['water_chiller']],
        instances=instances,connections=connections,fluid=FluidConfig(fluid='Water',phase_policy='liquid'),
        # The two water circuits share a fluid, but have separate topology.
        solver=SolverOptions(property_coupling='node',max_coupling_iterations=40))


@pytest.mark.parametrize('running', [0., 1.])
def test_water_only_network_and_idle_states(running):
    project = water_only_project()
    project.instances[0].parameters['running'] = running
    frame = solve_steady(compile_project(project))
    v = frame.variables
    if running:
        assert v['Chiller.cooling_power_w'] > 0
        assert v['Chiller.out0.temperature_k'] == pytest.approx(280.15, abs=1e-5)
    else:
        assert v['Chiller.cooling_power_w'] == 0 and v['Chiller.cop'] is None
        assert v['Chiller.out0.enthalpy_j_kg'] == pytest.approx(v['Chiller.in0.enthalpy_j_kg'])


@pytest.mark.parametrize('mutation,code', [
    ('missing-water','WATER_COIL_CIRCUITS'), ('air-condenser','MOIST_AIR_MODEL_UNSUPPORTED'),
    ('thermal-off','AIR_SOLVER_OPTIONS'), ('storage','AIR_STORAGE_UNSUPPORTED'),
    ('no-moisture','MOIST_AIR_REQUIRED'), ('bad-envelope','CHILLER_PARAMETERS'),
])
def test_invalid_circuit_and_solver_configurations_fail_at_compile_time(mutation, code):
    project = air_example('chiller-air-loop')
    if mutation == 'missing-water':
        project.circuit_fluids.pop(0)
    elif mutation == 'air-condenser':
        project.circuit_fluids.pop()
    elif mutation == 'thermal-off':
        project.solver.thermal = False
    elif mutation == 'storage':
        project.modules.append(catalog_map()['pipe'])
        duct = next(i for i in project.instances if i.id == 'FreshDuct')
        duct.module_id, duct.parameters = 'pipe', {'thermal_cells':2,'diameter_m':.4}
    elif mutation == 'no-moisture':
        project.solver.moist_air = False
        project.solver.moist_air_options = None
    else:
        next(i for i in project.instances if i.id == 'Chiller').parameters['min_condensing_temperature_k'] = 340.
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == code


def test_dynamic_cumulative_values_and_runtime_water_setpoint():
    session = SimulationSession(compile_project(air_example('chiller-air-loop')), 4., 2.)
    try:
        initial = session.initialize()
        assert initial.variables['Chiller.state.electric_energy_j'] == 0.
        session.advance()
        first = session.snapshot()
        session.set_parameter('Chiller', 'chilled_water_setpoint_k', 282.15)
        session.advance()
        last = session.snapshot()
        assert last.variables['Chiller.out0.temperature_k'] == pytest.approx(282.15, abs=1e-5)
        for target, rate in (('Chiller.state.electric_energy_j','Chiller.electric_power_w'),
                             ('Chiller.state.cooling_energy_j','Chiller.cooling_power_w'),
                             ('Coil.state.condensate_kg','Coil.condensate_kg_s'),
                             ('Tower.state.makeup_kg','Tower.makeup_kg_s')):
            assert last.variables[target] == pytest.approx(2*(first.variables[rate]+last.variables[rate]), rel=1e-10)
        assert last.variables['Room.state.temperature_k'] < initial.variables['Room.state.temperature_k']
    finally:
        session.close()


def test_api_example_reports_restart_and_snapshot_catalog(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.get('/api/v1/examples/chiller-air-loop')
        assert response.status_code == 200
        project = response.json()
        created = client.post('/api/v1/runs',json={'project':project,'mode':'dynamic','duration_s':2.,'dt_s':2.})
        assert created.status_code == 201, created.text
        assert created.json()['status'] == 'completed', created.text
        rid = created.json()['run_id']
        record = client.get('/api/v1/runs/'+rid).json()
        assert record['air_metadata']['continuity_basis'] == 'mixed'
        html = client.get(f'/api/v1/runs/{rid}/report.html')
        assert '水侧得热' in html.text and '累计耗电量' in html.text
        rows = list(csv.DictReader(StringIO(client.get(f'/api/v1/runs/{rid}/report.csv').content.decode('utf-8-sig'))))
        value = next(row for row in rows if row['变量键']=='Chiller.state.electric_energy_j' and float(row['时间(s)'])==2.)
        assert float(value['规范数值']) == pytest.approx(record['frame']['variables']['Chiller.state.electric_energy_j'],rel=1e-10)
    with TestClient(create_app(data_root=tmp_path)) as client:
        restarted = client.get('/api/v1/runs/'+rid).json()
        assert restarted['air_metadata'] == record['air_metadata']
        assert restarted['frame']['variables']['Chiller.state.electric_energy_j'] == record['frame']['variables']['Chiller.state.electric_energy_j']


def test_published_example_imports_preserve_both_liquid_circuits():
    import json
    from pathlib import Path
    from fn_engine.bridge import normalize_prototype_export
    root = Path(__file__).resolve().parents[1]/'examples'/'air-side'
    canonical = Project.model_validate_json((root/'chiller-air-loop.project.json').read_text(encoding='utf-8'))
    imported = normalize_prototype_export(json.loads((root/'chiller-air-loop.prototype.json').read_text(encoding='utf-8')))
    a, b = compile_project(canonical), compile_project(imported)
    assert a.parameters == b.parameters
    assert a.circuit_fluids == b.circuit_fluids
    assert canonical.connections == imported.connections
    frame = solve_steady(b)
    assert frame.valid and frame.metrics['reference_heat_w'] == 0.
    assert frame.variables['Chiller.out0.temperature_k'] == pytest.approx(280.15,abs=1e-5)


def test_unknown_circuit_anchor_still_produces_failed_run_metadata():
    project = air_example('chiller-air-loop')
    project.circuit_fluids[0].anchor.port_id = 'missing'
    assert make_air_metadata(project) is not None
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == 'CIRCUIT_ANCHOR_UNKNOWN'


def test_single_phase_gas_cannot_be_used_as_chiller_water():
    project = water_only_project()
    project.fluid = FluidConfig(fluid='Nitrogen', phase_policy='single_phase')
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == 'WATER_DEVICE_LIQUID_REQUIRED'


def test_closed_condenser_loop_without_a_heat_sink_is_rejected():
    project = air_example('chiller-air-loop')
    keep = {'Chiller','ChilledPump','CoolingPump','WaterValve','Coil','Tower',
            'ChilledRef','CoolingRef','ChilledJoin','CoolingJoin'}
    project.instances = [i for i in project.instances if i.id in keep]
    project.connections = [c for c in project.connections if c.id.startswith('water')]
    # Replace the air coil by a water heater, and the cooling tower by an insulated water pipe.
    coil = next(i for i in project.instances if i.id == 'Coil')
    coil.module_id, coil.parameters = 'heater', {'heat_input_w':12000.}
    tower = next(i for i in project.instances if i.id == 'Tower')
    tower.module_id, tower.parameters = 'pipe', {'length_m':5.,'diameter_m':.05}
    for c in project.connections:
        for endpoint in (c.source,c.target):
            if endpoint.instance_id == 'Coil':
                endpoint.port_id = endpoint.port_id.replace('1','0')
    project.fluid = FluidConfig(fluid='Water',phase_policy='liquid')
    project.solver.moist_air, project.solver.moist_air_options = False, None
    used = {i.module_id for i in project.instances}
    catalog = catalog_map()
    project.modules = [catalog[k] for k in used]
    network = compile_project(project)
    with pytest.raises(CompilationError) as exc:
        solve_steady(network)
    assert exc.value.diagnostic.code in ('THERMAL_NOT_CONVERGED', 'REFRIGERATION_ENVELOPE',
                                        'CHILLER_CONDENSER_INFEASIBLE', 'PHASE_UNSUPPORTED')
