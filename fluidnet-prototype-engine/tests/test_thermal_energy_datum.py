"""Energy acceptance uses physical differences, independent of each circuit's enthalpy datum."""
from dataclasses import replace
import sys

import numpy as np
import pytest

from fn_engine import thermal
from fn_engine.compiler import TankState, compile_project
from fn_engine.expansion_example import expansion_example
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.solver import solve_hydraulics, solve_network
from test_multifluid import hx
from test_states import fed_tank
from test_thermal import hx_network, line, project


class OffsetService:
    """Shift h and u together; PT and PH still describe the same physical states."""
    def __init__(self, base, offset):
        self.base, self.offset = base, offset

    def __getattr__(self, name):
        return getattr(self.base, name)

    def shifted(self, state):
        changes = {'enthalpy_j_kg': state.enthalpy_j_kg + self.offset}
        if state.internal_energy_j_kg is not None:
            changes['internal_energy_j_kg'] = state.internal_energy_j_kg + self.offset
        return state.model_copy(update=changes)

    def state_pt(self, pressure, temperature):
        return self.shifted(self.base.state_pt(pressure, temperature))

    def state_ph(self, pressure, enthalpy):
        return self.shifted(self.base.state_ph(pressure, enthalpy - self.offset))


def observed_checks(callback):
    # Observe the actual acceptance scales, without duplicating the solver's formula.
    checks = {}

    def profile(frame, event, result):
        if event == 'return' and frame.f_code is thermal.solve_thermal.__code__ and result is not None:
            checks['global_limit_w'] = thermal.ENERGY_RTOL * frame.f_locals['scale']
            if 'tank_scale' in frame.f_locals:
                checks['tank_limit_w'] = thermal.ENERGY_RTOL * frame.f_locals['tank_scale']
            if 'expansion_scale' in frame.f_locals:
                checks['expansion_limit_w'] = 1e-4 + thermal.ENERGY_RTOL * frame.f_locals['expansion_scale']

    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        result = callback()
    finally:
        sys.setprofile(previous)
    return result, checks


def observed_solve(network, service, hydraulic, storage_step=None):
    return observed_checks(lambda: thermal.solve_thermal(network, service, hydraulic.pressures, hydraulic.flows,
                                                        storage_step=storage_step))


def assert_same_physics_and_limits(reference, shifted):
    result, checks = reference
    other, other_checks = shifted
    assert other_checks == pytest.approx(checks, rel=1e-8, abs=1e-10)
    assert [s.temperature_k for s in other.node_states] == pytest.approx(
        [s.temperature_k for s in result.node_states], abs=1e-6)
    assert other.heat_w == pytest.approx(result.heat_w, abs=1e-6)
    assert other.energy_residual_w == pytest.approx(result.energy_residual_w, abs=1e-6)


def pipe_network(reverse=False, ua=300.):
    return compile_project(line('pipe', {'length_m': 20., 'diameter_m': .04,
        'heat_loss_ua_w_k': ua, 'ambient_temperature_k': 293.15},
        inlet=200000. if reverse else 202000., outlet=202000. if reverse else 200000.,
        t_in=303.15, t_out=303.15))


@pytest.mark.parametrize('offset', [-1e6, 1e6])
@pytest.mark.parametrize('kind', ['forward', 'reverse', 'exchanger'])
def test_global_energy_limit_is_independent_of_enthalpy_datum(kind, offset):
    network = hx_network() if kind == 'exchanger' else pipe_network(kind == 'reverse')
    hydraulic = solve_hydraulics(network)
    base = property_service(network.project.fluid)
    assert_same_physics_and_limits(observed_solve(network, base, hydraulic),
        observed_solve(network, OffsetService(base, offset), hydraulic))


@pytest.mark.parametrize('offsets', [(-1e6, 1e6), (1e6, -1e6)])
def test_exchanger_circuits_can_shift_their_datums_independently(offsets, monkeypatch):
    network = compile_project(hx())
    hydraulic = solve_hydraulics(network)
    base = property_service(FluidConfig())
    reference = observed_solve(network, base, hydraulic)
    original = thermal.service_at

    def service_at(network, node, default=None):
        return OffsetService(original(network, node, default), offsets[network.node_circuit[node]])

    monkeypatch.setattr(thermal, 'service_at', service_at)
    assert_same_physics_and_limits(reference, observed_solve(network, base, hydraulic))


def perturb_node(monkeypatch, node, delta_h):
    original = thermal.spsolve

    def solve(matrix, rhs):
        result = np.atleast_1d(original(matrix, rhs)).copy()
        result[node] += delta_h
        return result

    monkeypatch.setattr(thermal, 'spsolve', solve)


@pytest.mark.parametrize('offset', [0., -1e6, 1e6])
@pytest.mark.parametrize('reverse', [False, True], ids=['forward', 'reverse'])
def test_same_boundary_energy_fault_is_rejected_at_every_datum(offset, reverse, monkeypatch):
    network = pipe_network(reverse, ua=0.)
    hydraulic = solve_hydraulics(network)
    branch = network.branches[0]
    node = branch.start_node if reverse else branch.end_node
    # A 0.5 W wrong sink balance is small enough to pass the old shifted-datum gate.
    perturb_node(monkeypatch, node, .5 / abs(hydraulic.flows[0]))
    service = OffsetService(property_service(network.project.fluid), offset)
    with pytest.raises(thermal.ThermalError) as caught:
        observed_solve(network, service, hydraulic)
    assert caught.value.diagnostic.code == 'THERMAL_ENERGY_IMBALANCE'


@pytest.mark.parametrize('offset', [0., -1e6, 1e6])
def test_adiabatic_roundoff_is_accepted_at_every_datum(offset, monkeypatch):
    network = pipe_network(ua=0.)
    hydraulic = solve_hydraulics(network)
    perturb_node(monkeypatch, network.branches[0].end_node, 1e-9 / abs(hydraulic.flows[0]))
    result, _ = observed_solve(network, OffsetService(property_service(network.project.fluid), offset), hydraulic)
    assert abs(result.energy_residual_w) < 1e-6


def isolated_tank():
    return compile_project(project([('B1', 'source', {'pressure_pa': 200000.}),
        ('V1', 'valve', {'opening_ratio': 0.}), ('TK1', 'tank', {'level_m': 1., 'area_m2': 1.})],
        [('B1:out0', 'V1:in0'), ('V1:out0', 'TK1:in0')]))


@pytest.mark.parametrize('offset', [-1e6, 1e6])
@pytest.mark.parametrize('kind', ['flowing', 'isolated'])
def test_tank_energy_limit_is_independent_of_enthalpy_datum(kind, offset):
    network = compile_project(fed_tank(t_in=333.15, tank_params={
        'heat_input_w': 100., 'heat_loss_ua_w_k': 5., 'ambient_temperature_k': 283.15})) if kind == 'flowing' else isolated_tank()
    hydraulic = solve_hydraulics(network)
    base = property_service(network.project.fluid)
    old = {node: TankState(spec.initial_mass_kg, spec.initial_enthalpy_j_kg) for node, spec in network.storage.items()}
    shifted_old = {node: replace(state, enthalpy_j_kg=state.enthalpy_j_kg+offset) for node, state in old.items()}
    assert_same_physics_and_limits(observed_solve(network, base, hydraulic, (60., old)),
        observed_solve(network, OffsetService(base, offset), hydraulic, (60., shifted_old)))


@pytest.mark.parametrize('offset', [0., -1e6, 1e6])
def test_same_tank_energy_fault_is_rejected_at_every_datum(offset, monkeypatch):
    network = isolated_tank()
    hydraulic = solve_hydraulics(network)
    node, spec = next(iter(network.storage.items()))
    old = {node: TankState(spec.initial_mass_kg, spec.initial_enthalpy_j_kg+offset)}
    perturb_node(monkeypatch, node, .5 * 60. / spec.initial_mass_kg)
    service = OffsetService(property_service(network.project.fluid), offset)
    with pytest.raises(thermal.ThermalError) as caught:
        observed_solve(network, service, hydraulic, (60., old))
    assert caught.value.diagnostic.code == 'THERMAL_ENERGY_IMBALANCE'
    assert caught.value.diagnostic.instance_id == 'TK1'


def expansion_problem(offset, filling):
    project = expansion_example()
    if not filling:
        project.instances[0].parameters['pressure_pa'] = 230000.
    network = compile_project(project)
    service = OffsetService(property_service(network.project.fluid), offset)
    old = {}
    for node, spec in network.storage.items():
        spec.service = service
        spec.initial_enthalpy_j_kg += offset
        old[node] = TankState(spec.initial_mass_kg, spec.initial_enthalpy_j_kg)
    return network, service, old


@pytest.mark.parametrize('offset', [-1e6, 1e6])
@pytest.mark.parametrize('filling', [False, True], ids=['draining', 'filling'])
def test_expansion_liquid_and_gas_energy_solution_survives_a_datum_shift(offset, filling):
    def run(shift):
        network, service, old = expansion_problem(shift, filling)
        return observed_checks(lambda: solve_network(network, service=service, storage_step=(1., old)))

    (reference, checks), (shifted, shifted_checks) = run(0.), run(offset)
    assert 'expansion_limit_w' in checks
    assert shifted_checks == pytest.approx(checks, rel=1e-6, abs=1e-8)
    assert shifted.hydraulic.flows == pytest.approx(reference.hydraulic.flows, abs=1e-8)
    assert [s.temperature_k for s in shifted.thermal.node_states] == pytest.approx(
        [s.temperature_k for s in reference.thermal.node_states], abs=1e-6)
    assert abs(shifted.thermal.energy_residual_w) < 1e-4


@pytest.mark.parametrize('offset', [0., -1e6, 1e6])
@pytest.mark.parametrize('filling', [False, True], ids=['draining', 'filling'])
def test_same_expansion_energy_fault_is_rejected_at_every_datum(offset, filling, monkeypatch):
    network, service, old = expansion_problem(offset, filling)
    spec = next(iter(network.storage.values()))
    original = spec.energy_terms

    def energy_terms(*args):
        diagonal, rhs, stored, work = original(*args)
        # Keep the physical equation unchanged and inject a 1 mW stored-energy defect.
        return diagonal, rhs, stored + .001, work

    monkeypatch.setattr(spec, 'energy_terms', energy_terms)
    with pytest.raises(thermal.ThermalError) as caught:
        solve_network(network, service=service, storage_step=(1., old))
    assert caught.value.diagnostic.code == 'THERMAL_ENERGY_IMBALANCE'
    assert caught.value.diagnostic.instance_id == 'Expansion'
