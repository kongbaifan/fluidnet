"""Two real liquid circuits/branches exchange heat with one refrigerant inventory."""
from copy import deepcopy
import math

from CoolProp.CoolProp import PropsSI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from fn_engine.api import create_app
from fn_engine.compiler import CompilationError, circuit_info, compile_project
from fn_engine.models import Project, ScheduleEvent, TimeStepOptions
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
from fn_engine.refrigeration.devices import DeviceRangeError
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed, solve_dynamic, solve_steady
from test_continuous import wait
from test_thermal_coupling_bridge import prototype_case


def check_balance(frame, project):
    values = frame.variables
    fluids = {c.id: c.fluid.fluid for c in project.circuit_fluids}
    for link in project.thermal_couplings:
        prefix = f'coupling.{link.id}.'
        flow = values[prefix + 'mass_flow_kg_s']
        inlet, outlet = ('in0', 'out0') if flow >= 0 else ('out0', 'in0')
        pipe = link.fluid_instance_id
        heat = values[prefix + 'heat_w']
        assert heat == pytest.approx(abs(flow) * (values[f'{pipe}.{inlet}.enthalpy_j_kg']
                                                 - values[f'{pipe}.{outlet}.enthalpy_j_kg']), abs=1e-5)
        assert values[prefix + 'fluid_heat_w'] + values[prefix + 'refrigerant_heat_w'] == pytest.approx(0., abs=1e-8)
        if abs(flow) > project.solver.mass_tolerance_kg_s:
            fluid = fluids.get('secondary2', fluids['secondary']) if pipe == 'HX_W2' else fluids['secondary']
            temperature = values[f'{pipe}.{inlet}.temperature_k']
            capacity = abs(flow) * PropsSI('C', 'P', values[f'{pipe}.{inlet}.pressure_pa'], 'T', temperature, fluid)
            effectiveness = -math.expm1(-link.ua_w_k / capacity)
            assert heat == pytest.approx(effectiveness * capacity * (temperature - values['LP1.state.temperature_k']), abs=1e-4)
        else:
            assert heat == 0.
        assert abs(values[prefix + 'equation_residual_w']) < 1e-4
    total_heat = sum(values[f'coupling.{link.id}.heat_w'] for link in project.thermal_couplings)
    total_energy = sum(values[f'coupling.{link.id}.state.heat_energy_j'] for link in project.thermal_couplings)
    assert frame.metrics['coupling_heat_w'] == pytest.approx(total_heat, abs=1e-8)
    assert frame.metrics['coupling_heat_energy_j'] == pytest.approx(total_energy, abs=1e-8)
    assert values['metrics.coupling_heat_w'] == frame.metrics['coupling_heat_w']
    assert values['metrics.coupling_heat_energy_j'] == frame.metrics['coupling_heat_energy_j']
    assert abs(frame.metrics['fluid_energy_residual_w']) < 1e-4
    assert abs(frame.metrics['reference_heat_w']) < 1e-6


@pytest.mark.parametrize('topology', ['parallel', 'independent'])
def test_dual_design_point_has_real_equilibrium_and_correct_circuits(topology):
    project = thermal_coupling_example(topology=topology)
    network = compile_project(project)
    circuits = circuit_info(network)
    expected = ['Ammonia', 'INCOMP::MEG[0.3]'] if topology == 'parallel' else ['Ammonia', 'Water', 'INCOMP::MEG[0.3]']
    assert [c['fluid'].fluid for c in circuits] == expected
    for a, circuit in enumerate(circuits):
        assert all(set(circuit['ports']).isdisjoint(other['ports']) for other in circuits[a + 1:])
    frame = solve_steady(network)
    check_balance(frame, project)
    assert frame.metrics['steady_mass_residual_kg_s'] < 1e-8
    assert frame.metrics['steady_energy_residual_w'] < .01
    assert frame.metrics['steady_inventory_relative_error'] < 1e-8
    q1, q2 = (frame.variables[f'coupling.HX{i}.mass_flow_kg_s'] for i in (1, 2))
    assert q1 > 0. and q2 > 0.
    if topology == 'parallel':
        assert frame.variables['WP1.mass_flow_kg_s'] == pytest.approx(q1 + q2, abs=1e-8)
    else:
        assert frame.variables['WP1.mass_flow_kg_s'] == pytest.approx(q1, abs=1e-8)
        assert frame.variables['WP2.mass_flow_kg_s'] == pytest.approx(q2, abs=1e-8)
        assert frame.variables['HX_W2.in0.density_kg_m3'] > frame.variables['HX_W.in0.density_kg_m3']


@pytest.mark.parametrize('topology', ['parallel', 'independent'])
@pytest.mark.parametrize('adaptive', [False, True])
def test_two_coils_preserve_refrigerant_mass_and_independent_energy_ledger(topology, adaptive):
    project = thermal_coupling_example(topology=topology)
    next(n for n in project.instances if n.id == 'WL2').parameters['ambient_temperature_k'] = 313.15
    if adaptive:
        project.solver.time_step = TimeStepOptions(enabled=True, min_internal_step_s=.01, max_internal_step_s=1.)
    frames = solve_dynamic(compile_project(project), 3., 1.)
    first, last = frames[0].variables, frames[-1].variables
    initial_mass = sum(first[f'{v}.state.mass_kg'] for v in ('LP1', 'HP1'))
    for frame in frames:
        check_balance(frame, project)
        assert sum(frame.variables[f'{v}.state.mass_kg'] for v in ('LP1', 'HP1')) == pytest.approx(initial_mass, abs=1e-9)
    stored = sum(last[f'{v}.state.internal_energy_j'] - first[f'{v}.state.internal_energy_j'] for v in ('LP1', 'HP1'))
    boundary = (last['K1.state.electric_energy_j'] * last['K1.param.motor_efficiency']
                - last['EC1.state.heat_rejected_j']
                + sum(last[f'coupling.HX{i}.state.heat_energy_j'] for i in (1, 2)))
    assert stored == pytest.approx(boundary, abs=.002)
    assert abs(frames[-1].metrics['energy_residual_j']) < .002
    if not adaptive:
        for i in (1, 2):
            assert last[f'coupling.HX{i}.state.heat_energy_j'] == pytest.approx(
                sum(frame.variables[f'coupling.HX{i}.heat_w'] for frame in frames[1:]), abs=.002)


@pytest.mark.parametrize('topology', ['parallel', 'independent'])
def test_closing_one_branch_does_not_erase_the_other_coil(topology):
    project = thermal_coupling_example(topology=topology)
    session = create_session(compile_project(project), 2., 1.)
    try:
        session.initialize()
        session.write_variables({'WV2.param.opening_ratio': 0.})
        closed = session.advance()
        check_balance(closed, project)
        assert closed.variables['coupling.HX2.heat_w'] == 0.
        assert closed.variables['coupling.HX2.state.heat_energy_j'] == 0.
        assert closed.variables['coupling.HX1.heat_w'] > 0.
        session.write_variables({'WV2.param.opening_ratio': .7})
        reopened = session.advance()
        check_balance(reopened, project)
        assert reopened.variables['coupling.HX2.heat_w'] > 0.
        assert reopened.variables['coupling.HX2.state.heat_energy_j'] > 0.
    finally:
        session.close()


@pytest.mark.parametrize('reverse_temperature', [False, True])
def test_second_coil_supports_signed_flow_and_signed_heat(reverse_temperature):
    project = thermal_coupling_example(topology='independent')
    if reverse_temperature:
        next(n for n in project.instances if n.id == 'WL2').parameters['ambient_temperature_k'] = 273.15
    for edge in project.connections:
        for endpoint in (edge.source, edge.target):
            if endpoint.instance_id == 'HX_W2':
                endpoint.port_id = {'in0': 'out0', 'out0': 'in0'}[endpoint.port_id]
    session = create_session(compile_project(project), 1., 1.)
    try:
        frame = session.initialize()
        check_balance(frame, project)
        assert frame.variables['coupling.HX2.mass_flow_kg_s'] < 0.
        assert (frame.variables['coupling.HX2.heat_w'] < 0.) == reverse_temperature
        assert frame.variables['coupling.HX1.heat_w'] > 0.
    finally:
        session.close()


def test_rejected_step_cannot_publish_or_accumulate_either_coil(monkeypatch):
    project = thermal_coupling_example(topology='parallel')
    project.events = [ScheduleEvent(id='close2', type='set_variable', time_s=0., key='WV2.param.opening_ratio', value=0.)]
    session = create_session(compile_project(project), 2., 1.)
    try:
        initial = session.initialize()
        original_solve = session._solve
        def fail_after_solve(state, step):
            original_solve(state, step)
            raise DeviceRangeError('REFRIGERATION_NOT_CONVERGED', 'injected rejection')
        monkeypatch.setattr(session, '_solve', fail_after_solve)
        with pytest.raises(SolveFailed):
            session.advance()
        assert session.snapshot().variables == initial.variables
        assert session.counters == {}
        assert session.time == 0. and session.revision == 0
        assert session.events_applied == 0
        monkeypatch.setattr(session, '_solve', original_solve)
        accepted = session.advance()
        check_balance(accepted, project)
        assert accepted.variables['coupling.HX2.state.heat_energy_j'] == 0.
        assert accepted.variables['coupling.HX1.state.heat_energy_j'] == pytest.approx(accepted.variables['coupling.HX1.heat_w'], abs=.002)
    finally:
        session.close()


@pytest.mark.parametrize('bad,code', [('id', 'COUPLED_ID_DUPLICATE'), ('channel', 'COUPLED_CHANNEL_DUPLICATE'),
                                    ('third', 'COUPLED_LIMIT'), ('vessel', 'COUPLED_VESSEL_SCOPE')])
def test_ambiguous_or_unsupported_bindings_are_rejected_before_solving(bad, code):
    project = thermal_coupling_example(topology='parallel')
    if bad == 'id':
        project.thermal_couplings[1].id = project.thermal_couplings[0].id
    elif bad == 'channel':
        project.thermal_couplings[1].fluid_instance_id = project.thermal_couplings[0].fluid_instance_id
    elif bad == 'third':
        project.thermal_couplings.append(project.thermal_couplings[0].model_copy(update={'id': 'HX3', 'fluid_instance_id': 'WL1'}))
    else:
        project.thermal_couplings[1].refrigerant_vessel_id = 'HP1'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == code
    if bad != 'vessel':
        with pytest.raises(ValidationError):
            Project.model_validate(project.model_dump())


@pytest.mark.parametrize('topology', ['parallel', 'independent'])
def test_example_api_and_saved_project_round_trip_keep_both_circuits(tmp_path, topology):
    root = tmp_path / 'data'
    with TestClient(create_app(data_root=root, module_storage_root=tmp_path / 'modules')) as client:
        example = client.get('/api/v1/examples/thermal-coupling', params={'topology': topology})
        assert example.status_code == 200, example.text
        model, payload = prototype_case(Project.model_validate(example.json()))
        payload.update(models=[], charts={'extra': []})
        assert client.post('/api/v1/workspace', json={'data': payload, 'expected_revision': 0}).status_code == 200
        canonical = client.post('/api/v1/prototype/normalize', json=payload)
        assert canonical.status_code == 200
        assert canonical.json()['thermal_couplings'] == example.json()['thermal_couplings']
        assert canonical.json()['circuit_fluids'] == example.json()['circuit_fluids']
        direct = client.post('/api/v1/runs', json={'project': canonical.json(), 'mode': 'dynamic', 'duration_s': 2., 'dt_s': 1.})
        assert direct.status_code == 201, direct.text
        expected = deepcopy(direct.json()['frame']['variables'])
    with TestClient(create_app(data_root=root, module_storage_root=tmp_path / 'modules')) as client:
        saved = client.get('/api/v1/projects/' + model.id).json()['document']['project']
        assert len(saved['thermalCouplings']) == 2
        created = client.post(f'/api/v1/projects/{model.id}/runs', json={'mode': 'dynamic', 'duration_s': 2., 'dt_s': 1.})
        assert created.status_code == 202, created.text
        result = wait(client, created.json()['run_id'], lambda row: row['status'] in {'completed', 'failed'})
        assert result['status'] == 'completed'
        assert result['frame']['variables'] == expected
        assert client.get('/api/v1/examples/thermal-coupling?topology=unsupported').status_code == 422
