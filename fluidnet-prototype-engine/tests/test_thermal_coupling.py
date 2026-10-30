"""Cross-domain coil physics and accepted-state integration, checked from public frames."""
import math

from CoolProp.CoolProp import PropsSI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from fn_engine.api import create_app
from fn_engine.compiler import CompilationError, circuit_info, compile_project
from fn_engine.models import Connection, Endpoint, ParameterSpec, PIDController, Project, ScheduleEvent, TimeStepOptions
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
from fn_engine.refrigeration.devices import DeviceRangeError
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed, solve_dynamic, solve_steady


def set_parameters(project, instance_id, **values):
    next(instance for instance in project.instances if instance.id == instance_id).parameters.update(values)
    return project


def initial_frame(project):
    session = create_session(compile_project(project), 1., 1.)
    try:
        return session.initialize()
    finally:
        session.close()


def assert_coil_balance(frame, project):
    """Recompute transferred heat from physical ports and an independent property query."""
    values = frame.variables
    prefix = 'coupling.HX1.'
    flow = values[prefix + 'mass_flow_kg_s']
    inlet, outlet = ('in0', 'out0') if flow >= 0 else ('out0', 'in0')
    inlet_h = values[f'HX_W.{inlet}.enthalpy_j_kg']
    outlet_h = values[f'HX_W.{outlet}.enthalpy_j_kg']
    inlet_t = values[f'HX_W.{inlet}.temperature_k']
    refrigerant_t = values['LP1.state.temperature_k']
    heat = values[prefix + 'heat_w']
    height = next(instance for instance in project.instances if instance.id == 'HX_W').parameters.get('height_m', 0.)
    assert heat == pytest.approx(abs(flow) * (inlet_h - outlet_h) - flow * 9.80665 * height, abs=1e-5)
    assert values['HX_W.heat_w'] == pytest.approx(-heat - flow * 9.80665 * height, abs=1e-7)
    assert values[prefix + 'fluid_heat_w'] + values[prefix + 'refrigerant_heat_w'] == pytest.approx(0., abs=1e-7)
    if abs(flow) > project.solver.mass_tolerance_kg_s:
        coolant = next(c.fluid.fluid for c in project.circuit_fluids if c.id == 'secondary')
        capacity = abs(flow) * PropsSI('C', 'P', values[f'HX_W.{inlet}.pressure_pa'], 'T', inlet_t, coolant)
        effectiveness = -math.expm1(-project.thermal_couplings[0].ua_w_k / capacity)
        assert values[prefix + 'effectiveness'] == pytest.approx(effectiveness, rel=1e-9)
        assert heat == pytest.approx(effectiveness * capacity * (inlet_t - refrigerant_t), abs=1e-4)
    else:
        assert heat == 0.
        assert values[prefix + 'effectiveness'] == 0.
    assert abs(values[prefix + 'equation_residual_w']) < 1e-4
    assert abs(frame.metrics['fluid_energy_residual_w']) < 1e-4
    assert abs(frame.metrics['reference_heat_w']) < 1e-7


def test_compiler_keeps_mass_networks_and_property_services_separate():
    project = thermal_coupling_example()
    network = compile_project(project)
    circuits = circuit_info(network)
    assert network.execution_domain == 'coupled'
    assert [c['id'] for c in circuits] == [0, 1]
    assert [c['fluid'].fluid for c in circuits] == ['Ammonia', 'INCOMP::MEG[0.3]']
    assert set(circuits[0]['ports']).isdisjoint(circuits[1]['ports'])
    assert 'LP1:vapor' in circuits[0]['ports'] and 'HX_W:in0' in circuits[1]['ports']
    assert not network.fluid_network.storage
    assert Project.model_validate(project.model_dump(mode='json')) == project


def test_headless_api_exposes_and_runs_the_coupled_case(tmp_path):
    with TestClient(create_app(module_storage_root=tmp_path / 'modules')) as client:
        health = client.get('/api/v1/health').json()
        assert health['capabilities']['thermal_coupling'] is True
        response = client.get('/api/v1/examples/thermal-coupling')
        assert response.status_code == 200
        project = response.json()
        checked = client.post('/api/v1/projects/validate', json=project)
        assert checked.status_code == 200 and checked.json()['valid']
        response = client.post('/api/v1/runs', json={
            'project': project, 'mode': 'dynamic', 'duration_s': 2., 'dt_s': 1.,
        })
        assert response.status_code == 201
        run = response.json()
        assert run['frame']['valid'] and run['frame']['time_s'] == 2.
        values = client.get(f"/api/v1/runs/{run['run_id']}/variables", params={
            'keys': 'coupling.HX1.heat_w,HX_W.out0.temperature_k,LP1.state.temperature_k',
        })
        assert values.status_code == 200
        assert values.json()['values']['coupling.HX1.heat_w'] > 0.


@pytest.mark.parametrize('coolant', ['Water', 'INCOMP::MEG[0.3]'])
def test_dynamic_conserves_charge_and_independent_energy_ledger(coolant):
    project = thermal_coupling_example(coolant)
    frames = solve_dynamic(compile_project(project), 4., 1.)
    first, last = frames[0].variables, frames[-1].variables
    for frame in frames:
        assert frame.valid
        assert_coil_balance(frame, project)
        assert sum(frame.variables[f'{v}.state.mass_kg'] for v in ('LP1', 'HP1')) == pytest.approx(
            sum(first[f'{v}.state.mass_kg'] for v in ('LP1', 'HP1')), abs=1e-9)
    storage_change = sum(last[f'{v}.state.internal_energy_j'] - first[f'{v}.state.internal_energy_j']
                         for v in ('LP1', 'HP1'))
    boundary = (last['K1.state.electric_energy_j'] * last['K1.param.motor_efficiency']
                - last['EC1.state.heat_rejected_j'] + last['coupling.HX1.state.heat_energy_j'])
    assert storage_change == pytest.approx(boundary, abs=.002)
    # Implicit Euler accumulates the heat from each accepted end-of-step state.
    assert last['coupling.HX1.state.heat_energy_j'] == pytest.approx(
        sum(f.variables['coupling.HX1.heat_w'] for f in frames[1:]), abs=.002)
    assert abs(frames[-1].metrics['energy_residual_j']) < .002
    assert 'WP1.param.head_curve' not in last  # Curves are parameters, not scalar frame variables.


def test_reversing_coil_ports_preserves_heat_and_changes_signed_flow():
    project = thermal_coupling_example()
    forward = initial_frame(project)
    for edge in project.connections:
        for endpoint in (edge.source, edge.target):
            if endpoint.instance_id == 'HX_W':
                endpoint.port_id = {'in0': 'out0', 'out0': 'in0'}[endpoint.port_id]
    reverse = initial_frame(project)
    assert reverse.variables['coupling.HX1.mass_flow_kg_s'] == pytest.approx(
        -forward.variables['coupling.HX1.mass_flow_kg_s'])
    assert reverse.variables['coupling.HX1.heat_w'] == pytest.approx(forward.variables['coupling.HX1.heat_w'])
    assert_coil_balance(reverse, project)


def test_coil_allows_heat_to_flow_from_refrigerant_into_colder_liquid():
    project = set_parameters(thermal_coupling_example(), 'WL1', ambient_temperature_k=273.15)
    frame = initial_frame(project)
    assert frame.variables['coupling.HX1.heat_w'] < 0.
    assert frame.variables['coupling.HX1.fluid_outlet_temperature_k'] > frame.variables['coupling.HX1.fluid_inlet_temperature_k']
    assert_coil_balance(frame, project)


@pytest.mark.parametrize('height', [-.8, .8])
@pytest.mark.parametrize('reverse', [False, True])
def test_coil_separates_gravitational_energy_from_heat(height, reverse):
    project = set_parameters(thermal_coupling_example(), 'HX_W', height_m=height)
    next(module for module in project.modules if module.id == 'pipe').parameters.append(
        ParameterSpec(id='height_m', label='Elevation rise', default=0.))
    # The return section restores elevation, so there is no net gravitational source in the loop.
    set_parameters(project, 'WL1', height_m=-height)
    if reverse:
        for edge in project.connections:
            for endpoint in (edge.source, edge.target):
                if endpoint.instance_id == 'HX_W':
                    endpoint.port_id = {'in0': 'out0', 'out0': 'in0'}[endpoint.port_id]
        set_parameters(project, 'HX_W', height_m=-height)
    assert_coil_balance(initial_frame(project), project)


@pytest.mark.parametrize('isolated_by', ['closed-valve', 'zero-ua'])
def test_no_transfer_without_flow_or_conductance(isolated_by):
    project = thermal_coupling_example()
    if isolated_by == 'closed-valve':
        set_parameters(project, 'WV1', opening_ratio=0.)
    else:
        project.thermal_couplings[0].ua_w_k = 0.
    frame = initial_frame(project)
    assert frame.variables['coupling.HX1.heat_w'] == 0.
    assert_coil_balance(frame, project)


def test_runtime_valve_changes_reach_the_liquid_network_and_can_reopen():
    session = create_session(compile_project(thermal_coupling_example()), 3., 1.)
    try:
        first = session.initialize()
        session.write_variables({'WV1.param.opening_ratio': 0.})
        closed = session.advance()
        assert closed.variables['WV1.param.opening_ratio'] == 0.
        assert closed.variables['coupling.HX1.mass_flow_kg_s'] == pytest.approx(0., abs=1e-10)
        assert closed.variables['coupling.HX1.heat_w'] == 0.
        session.write_variables({'WV1.param.opening_ratio': .8})
        opened = session.advance()
        assert opened.variables['coupling.HX1.mass_flow_kg_s'] == pytest.approx(first.variables['coupling.HX1.mass_flow_kg_s'])
        assert opened.variables['coupling.HX1.heat_w'] > 0.
        assert opened.parameter_revision == 2
    finally:
        session.close()


def test_failed_segment_restores_parameters_state_and_the_current_snapshot(monkeypatch):
    project = thermal_coupling_example()
    project.events = [ScheduleEvent(id='throttle', type='set_variable', time_s=0.,
                                    key='WV1.param.opening_ratio', value=.4)]
    session = create_session(compile_project(project), 2., 1.)
    try:
        initial = session.initialize()
        original_solve = session._solve

        def exhausted_after_evaluation(state, step):
            original_solve(state, step)
            raise DeviceRangeError('REFRIGERATION_NOT_CONVERGED', 'injected solver exhaustion')

        monkeypatch.setattr(session, '_solve', exhausted_after_evaluation)
        with pytest.raises(SolveFailed) as error:
            session.advance()
        assert error.value.diagnostic.code == 'REFRIGERATION_NOT_CONVERGED'
        assert session.time == 0. and session.revision == 0
        assert session.event_index == 0 and session.events_applied == 0
        assert session.counters == {}
        assert session.network.parameters['WV1']['opening_ratio'] == .8
        # The accepted cached fluid solution must not be combined with rejected parameters.
        restored = session.snapshot()
        assert restored.variables == initial.variables
        assert session.network.fluid_network.parameters['WV1']['opening_ratio'] == .8
        assert error.value.frames == [initial]
    finally:
        session.close()


def test_schedule_applies_liquid_parameter_at_exact_boundary():
    project = thermal_coupling_example()
    project.events = [ScheduleEvent(id='close', type='set_variable', time_s=1.5,
                                    key='WV1.param.opening_ratio', value=0.)]
    frames = solve_dynamic(compile_project(project), 3., 1.)
    assert frames[1].variables['coupling.HX1.mass_flow_kg_s'] > 0.
    assert frames[1].metrics['events_applied'] == 0
    assert frames[2].variables['coupling.HX1.mass_flow_kg_s'] == pytest.approx(0., abs=1e-10)
    assert frames[2].metrics['events_applied'] == 1
    assert frames[3].variables['coupling.HX1.state.heat_energy_j'] == frames[2].variables['coupling.HX1.state.heat_energy_j']


def test_manual_controller_can_measure_liquid_temperature_and_actuate_valve():
    project = thermal_coupling_example()
    project.controllers = [PIDController(id='secondary', measurement='HX_W.out0.temperature_k',
                                         instance_id='WV1', parameter_id='opening_ratio', setpoint=285.,
                                         mode='manual', manual_output=.4, sample_s=1.)]
    frame = solve_dynamic(compile_project(project), 1., 1.)[-1]
    assert frame.variables['WV1.param.opening_ratio'] == .4
    assert frame.variables['controller.secondary.output'] == .4
    assert_coil_balance(frame, project)


def test_adaptive_time_steps_preserve_coupled_charge_and_heat_balance():
    project = thermal_coupling_example()
    project.solver.time_step = TimeStepOptions(enabled=True, min_internal_step_s=.01, max_internal_step_s=1.)
    frames = solve_dynamic(compile_project(project), 2., 1.)
    assert frames[-1].metrics['timestep_adaptive'] == 1
    assert abs(frames[-1].metrics['energy_residual_j']) < .002
    for frame in frames:
        assert_coil_balance(frame, project)


def test_steady_design_point_has_zero_inventory_rates_and_keeps_initial_charge():
    project = thermal_coupling_example()
    first = initial_frame(project)
    frame = solve_steady(compile_project(project))
    assert frame.valid
    assert frame.metrics['steady_mass_residual_kg_s'] <= 1e-8
    assert frame.metrics['steady_energy_residual_w'] <= .01
    assert sum(frame.variables[f'{v}.state.mass_kg'] for v in ('LP1', 'HP1')) == pytest.approx(
        sum(first.variables[f'{v}.state.mass_kg'] for v in ('LP1', 'HP1')), rel=1e-8)
    assert abs(frame.metrics['storage_power_w']) <= .02
    assert_coil_balance(frame, project)


def test_steady_rejects_a_non_equilibrium_instead_of_returning_initial_frame():
    project = set_parameters(thermal_coupling_example(), 'EV1', opening_ratio=0.)
    with pytest.raises(CompilationError) as error:
        solve_steady(compile_project(project))
    assert error.value.diagnostic.code == 'COUPLED_STEADY_NOT_CONVERGED'


@pytest.mark.parametrize('change,code', [
    ('thermal-off', 'COUPLED_THERMAL_REQUIRED'),
    ('storage', 'COUPLED_FLUID_STATE_UNSUPPORTED'),
    ('coil-ambient', 'COUPLED_COIL_HEAT_CONFLICT'),
    ('wrong-channel', 'COUPLED_COIL_INVALID'),
    ('wrong-liquid', 'COUPLED_COIL_INVALID'),
    ('wrong-vessel', 'COUPLED_TARGET_INVALID'),
    ('cross-domain-edge', 'COUPLED_CONNECTION_INVALID'),
    ('unsupported-event', 'SCHEDULE_UNSUPPORTED'),
])
def test_unsupported_couplings_are_rejected_before_running(change, code):
    project = thermal_coupling_example()
    coupling = project.thermal_couplings[0]
    if change == 'thermal-off':
        project.solver.thermal = False
    elif change == 'storage':
        set_parameters(project, 'WL1', thermal_cells=2)
    elif change == 'coil-ambient':
        set_parameters(project, 'HX_W', heat_loss_ua_w_k=1.)
    elif change == 'wrong-channel':
        coupling.fluid_channel_id = 'missing'
    elif change == 'wrong-liquid':
        coupling.fluid_instance_id = 'WV1'
    elif change == 'wrong-vessel':
        coupling.refrigerant_vessel_id = 'K1'
    elif change == 'cross-domain-edge':
        project.connections.append(Connection(id='bad', source=Endpoint(instance_id='HX_W', port_id='out0'),
                                               target=Endpoint(instance_id='LP1', port_id='in0')))
    else:
        project.events = [ScheduleEvent(id='ambient', type='ambient_temperature', time_s=1., temperature_k=303.15)]
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == code


def test_steady_rejects_scheduled_writes():
    project = thermal_coupling_example()
    project.events = [ScheduleEvent(id='close', type='set_variable', time_s=1., key='WV1.param.opening_ratio', value=0.)]
    with pytest.raises(CompilationError) as error:
        solve_steady(compile_project(project))
    assert error.value.diagnostic.code == 'COUPLED_STEADY_CONTROL_UNSUPPORTED'


def test_unknown_fluid_anchor_is_rejected_before_partitioning_the_domains():
    project = thermal_coupling_example()
    project.circuit_fluids[1].anchor.instance_id = 'missing'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'CIRCUIT_ANCHOR_UNKNOWN'
    assert error.value.diagnostic.field == 'circuit_fluids'


def test_reserved_instance_prefix_cannot_overwrite_coupling_variables():
    project = thermal_coupling_example()
    next(instance for instance in project.instances if instance.id == 'HX_W').id = 'coupling'
    for edge in project.connections:
        for endpoint in (edge.source, edge.target):
            if endpoint.instance_id == 'HX_W':
                endpoint.instance_id = 'coupling'
    project.thermal_couplings[0].fluid_instance_id = 'coupling'
    project.thermal_couplings[0].id = 'ch0'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'COUPLED_RESERVED_ID'
    assert error.value.diagnostic.instance_id == 'coupling'


@pytest.mark.parametrize('invalid_cells', [None, [], 'invalid'])
def test_malformed_thermal_cells_reports_a_parameter_diagnostic(invalid_cells):
    project = set_parameters(thermal_coupling_example(), 'WL1', thermal_cells=invalid_cells)
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'PARAMETER_INVALID'
    assert error.value.diagnostic.instance_id == 'WL1'
    assert error.value.diagnostic.field == 'thermal_cells'


@pytest.mark.parametrize('change', ['negative-ua', 'missing-instance', 'multiple-coils'])
def test_coupling_contract_rejects_invalid_or_unsupported_links(change):
    data = thermal_coupling_example().model_dump(mode='json')
    if change == 'negative-ua':
        data['thermal_couplings'][0]['ua_w_k'] = -1.
    elif change == 'missing-instance':
        data['thermal_couplings'][0]['fluid_instance_id'] = 'missing'
    else:
        data['thermal_couplings'].append(data['thermal_couplings'][0] | {'id': 'HX2'})
    with pytest.raises(ValidationError):
        Project.model_validate(data)
