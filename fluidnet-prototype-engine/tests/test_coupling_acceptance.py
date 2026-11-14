"""The accepted coupled state must satisfy viscosity, flow and final thermal defects."""
from dataclasses import replace
import inspect

import numpy as np
import pytest
from pydantic import ValidationError

from fn_engine import air_transport, solver, thermal
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import FluidConfig, SolverOptions
from fn_engine.properties import property_service
from fn_engine.simulation import SimulationSession
from test_air_room import room_project
from test_moist_air_phase2 import humidifier_project
from test_thermal import line


def coupling_project(domain='liquid', mode='none'):
    if domain == 'air':
        project = humidifier_project({'mode': 'isothermal', 'moisture_addition_kg_kg': 0.})
    else:
        project = line('valve', {}, inlet=202000., outlet=200000., property_coupling='node')
    project.solver.max_coupling_iterations = 4
    project.solver.coupling_acceleration = mode
    return project


@pytest.mark.parametrize('domain,mode', [('liquid', 'none'), ('liquid', 'adaptive'), ('liquid', 'aitken'), ('air', 'none')])
@pytest.mark.parametrize('fault', ['viscosity', 'flow'])
def test_oscillating_coupling_defect_is_not_accepted(domain, mode, fault, monkeypatch):
    network = compile_project(coupling_project(domain, mode))
    calls = 0
    if fault == 'flow':
        original = solver._solve_hydraulics

        def hydraulic(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            return replace(result, flows=result.flows*(1. if calls % 2 else 1.05))

        monkeypatch.setattr(solver, '_solve_hydraulics', hydraulic)
    elif domain == 'liquid':
        original = solver._branch_properties

        def properties(*args):
            nonlocal calls
            rho, mu = original(*args)
            calls += 1
            return rho, mu*(1. if calls % 2 else 1.2)

        monkeypatch.setattr(solver, '_branch_properties', properties)
    else:
        original = air_transport.solve_air_transport

        def transport(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            result.node_states = [s.model_copy(update={'viscosity_pa_s': s.viscosity_pa_s*(1. if calls % 2 else 1.2)})
                                  for s in result.node_states]
            return result

        monkeypatch.setattr(air_transport, 'solve_air_transport', transport)
    with pytest.raises(CompilationError) as caught:
        solver.solve_network(network)
    assert caught.value.diagnostic.code == 'COUPLING_NOT_CONVERGED'
    assert ('黏度' if fault == 'viscosity' else '流量') in str(caught.value)
    assert calls == network.project.solver.max_coupling_iterations


@pytest.mark.parametrize('fluid,mode', [(fluid, mode) for fluid in ['Water', 'INCOMP::MEG[0.3]']
                                     for mode in ['none', 'adaptive', 'aitken']] + [('air', 'none')])
def test_real_coupled_state_reports_all_acceptance_defects(fluid, mode):
    project = coupling_project('air' if fluid == 'air' else 'liquid', mode)
    if fluid != 'air':
        project.fluid = FluidConfig(fluid=fluid)
    network = compile_project(project)
    result = solver.solve_network(network)
    metrics = solver.snapshot(network, result).metrics
    assert metrics['coupling_density_defect'] <= project.solver.coupling_density_rtol
    assert metrics['coupling_viscosity_defect'] <= project.solver.coupling_viscosity_rtol
    assert metrics['coupling_flow_defect'] <= 1.
    assert metrics['coupling_temperature_defect_k'] <= project.solver.thermal_tolerance_k
    assert all(np.isfinite(value) for value in result.coupling_defects.values())
    if fluid == 'air':
        assert metrics['coupling_humidity_defect_kg_kg'] <= project.solver.moist_air_options.humidity_tolerance_kg_kg


@pytest.mark.parametrize('name', ['coupling_viscosity_rtol', 'coupling_flow_rtol'])
@pytest.mark.parametrize('value', [0., -1., float('nan'), float('inf')])
def test_new_coupling_tolerances_require_positive_finite_values(name, value):
    with pytest.raises(ValidationError):
        SolverOptions.model_validate({name: value})


def test_new_tolerances_preserve_default_project_serialization_and_roundtrip_overrides():
    defaults = SolverOptions()
    assert defaults.coupling_viscosity_rtol == defaults.coupling_flow_rtol == 1e-6
    assert 'coupling_viscosity_rtol' not in defaults.model_dump(mode='json')
    assert 'coupling_flow_rtol' not in defaults.model_dump(mode='json')
    configured = SolverOptions(coupling_viscosity_rtol=1e-5, coupling_flow_rtol=1e-4)
    assert SolverOptions.model_validate_json(configured.model_dump_json()) == configured


def test_flow_defect_uses_mass_absolute_tolerance_at_zero_and_detects_direction_changes():
    options = SolverOptions()
    assert solver._coupling_flow_defect(np.array([0.]), np.array([.5e-8]), options) <= 1.
    assert solver._coupling_flow_defect(np.array([0.]), np.array([2e-8]), options) > 1.
    assert solver._coupling_flow_defect(np.array([.1]), np.array([-.1]), options) > 1.


@pytest.mark.parametrize('mode', ['none', 'adaptive', 'aitken'])
@pytest.mark.parametrize('tolerance', [1e-6, 1e-8])
def test_final_thermal_fixed_point_defect_cannot_use_a_looser_gate(mode, tolerance, monkeypatch):
    project = line('pipe', {'heat_loss_ua_w_k': 300., 'ambient_temperature_k': 283.15},
        inlet=202000., outlet=200000., t_in=303.15, thermal_acceleration=mode, thermal_tolerance_k=tolerance)
    network = compile_project(project)
    hydraulic = solver.solve_hydraulics(network)
    original = thermal.spsolve
    injected = False

    def solve(matrix, rhs):
        nonlocal injected
        result = np.atleast_1d(original(matrix, rhs)).copy()
        caller = inspect.currentframe().f_back.f_back
        if caller.f_code is thermal.solve_thermal.__code__ and 'check_states' in caller.f_locals:
            states = caller.f_locals['check_states']
            node = network.branches[0].end_node
            result[node] += 5*tolerance*states[node].specific_heat_j_kg_k
            injected = True
        return result

    monkeypatch.setattr(thermal, 'spsolve', solve)
    with pytest.raises(thermal.ThermalError) as caught:
        thermal.solve_thermal(network, property_service(project.fluid), hydraulic.pressures, hydraulic.flows)
    assert caught.value.diagnostic.code == ('THERMAL_FIXED_POINT_DEFECT' if mode == 'none' else 'THERMAL_ACCELERATION_DEFECT')
    assert injected


@pytest.mark.parametrize('perturbation', [1e-7, 1e-5])
def test_air_device_streams_are_evaluated_at_the_accepted_node_state(monkeypatch, perturbation):
    project = coupling_project('air')
    project.solver.thermal_tolerance_k = 1e-3
    network = compile_project(project)
    hydraulic = solver.solve_hydraulics(network)
    service = air_transport.MoistAirService()
    previous = air_transport._initial(network, service, None)
    inlet_node = network.port_nodes['H1:in0']
    previous[inlet_node] = service.state_ptw(float(hydraulic.pressures[inlet_node]),
        previous[inlet_node].temperature_k+perturbation, previous[inlet_node].humidity_ratio_kg_kg)
    original = air_transport.evaluate_humidifier
    inputs = []

    def evaluate(inlet, *args, **kwargs):
        inputs.append(inlet)
        return original(inlet, *args, **kwargs)

    monkeypatch.setattr(air_transport, 'evaluate_humidifier', evaluate)
    result = air_transport.solve_air_transport(network, hydraulic, previous, service, {}, 0.)
    assert inputs[-1].enthalpy_j_kg_dry_air == pytest.approx(result.node_states[inlet_node].enthalpy_j_kg_dry_air, abs=1e-10)
    assert inputs[-1].temperature_k == pytest.approx(result.node_states[inlet_node].temperature_k, abs=1e-12)
    branch = next(j for j, b in enumerate(network.branches) if b.instance_id == 'H1')
    expected = original(result.node_states[inlet_node], float(hydraulic.flows[branch]),
        network.parameters['H1'], float(hydraulic.pressures[network.port_nodes['H1:out0']]), service)
    assert result.outlet_enthalpies[branch] == pytest.approx(expected.outlet_state.enthalpy_j_kg_dry_air, abs=1e-10)


@pytest.mark.parametrize('capacity', [0., 1e6])
@pytest.mark.parametrize('dt', [1., 30.])
def test_room_inventory_and_device_reports_share_the_final_network_state(capacity, dt):
    project = room_project()
    room = next(i for i in project.instances if i.id == 'Room')
    room.parameters['additional_heat_capacity_j_k'] = capacity
    room.parameters['sensible_load_w'] = 100.
    session = SimulationSession(compile_project(project), dt, dt)
    try:
        session.initialize()
        _, result, _, _, _ = session._trial(dt)
        thermal_result = result.thermal
        assert thermal_result.air_metrics['air_energy_defect'] <= 1.
        assert thermal_result.air_metrics['air_moisture_defect'] <= 1.
        for node, accepted_room in thermal_result.air_room_results.items():
            state = thermal_result.node_states[node]
            assert accepted_room.state == state
            assert accepted_room.outputs['state.temperature_k'] == state.temperature_k
            assert accepted_room.outputs['state.humidity_ratio_kg_kg'] == state.humidity_ratio_kg_kg
    finally:
        session.close()
