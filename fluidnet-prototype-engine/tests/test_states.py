"""State integration layer, M1: open tanks under implicit Euler (analytic recursions, ledgers, events)."""
import math

import pytest
from fastapi.testclient import TestClient

import fn_engine.solver as solver
from fn_engine.api import create_app
from fn_engine.compiler import GRAVITY, CompilationError, compile_project
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.solver import MU_WATER, RHO_WATER, SolveFailed, pipe_drop, solve_dynamic, solve_steady
from test_run_control import custom_module
from test_thermal import project, prototype

WATER = property_service(FluidConfig())
LAMINAR = {'length_m': 10., 'diameter_m': .01, 'roughness_m': 0.}
AREA = .01


def tank(**params):
    return {'level_m': 1., 'area_m2': AREA, 'height_m': 3., **params}


def fed_tank(p_in=111500., p_out=110500., t_in=293.15, tank_params=None, **solver_options):
    """B1 → L1 (laminar) → TK1 → L2 (laminar) → B2."""
    return project([('B1', 'source', {'pressure_pa': p_in, 'temperature_k': t_in}), ('L1', 'pipe', LAMINAR),
                    ('TK1', 'tank', tank(**(tank_params or {}))), ('L2', 'pipe', LAMINAR),
                    ('B2', 'source', {'pressure_pa': p_out})],
                   [('B1:out0', 'L1:in0'), ('L1:out0', 'TK1:in0'), ('TK1:out0', 'L2:in0'), ('L2:out0', 'B2:out0')],
                   **solver_options)


def resistance():
    """Laminar pipe: Δp = R·q exactly (pure water uses the constant reference properties)."""
    q = 1e-3
    return pipe_drop(LAMINAR, q, RHO_WATER, MU_WATER) / q


def euler_masses(m0, a, b, dt, steps):
    masses = [m0]
    for _ in range(steps):
        masses.append((masses[-1] + dt * a) / (1 + dt * b))
    return masses


def linear_ode(network):
    """dM/dt = a − b·M for fed_tank (p = p_s + g·M/A, q = Δp/R)."""
    spec = next(iter(network.storage.values()))
    r = resistance()
    p_in, p_out = network.parameters['B1']['pressure_pa'], network.parameters['B2']['pressure_pa']
    a = (p_in + p_out - 2 * spec.surface_pressure_pa) / r
    b = 2 * GRAVITY / (spec.area_m2 * r)
    return spec, a, b


def test_initial_state_is_consistent_with_level_and_pressure():
    network = compile_project(fed_tank())
    spec = network.storage[network.port_nodes['TK1:in0']]
    state = WATER.state_pt(spec.initial_pressure_pa, 293.15)
    assert spec.initial_mass_kg == pytest.approx(state.density_kg_m3 * AREA * 1.0, rel=1e-12)
    assert spec.initial_pressure_pa == pytest.approx(101325. + GRAVITY * spec.initial_mass_kg / AREA, rel=1e-15)
    frame = solve_steady(network)
    assert frame.variables['TK1.state.level_m'] == pytest.approx(1.0, rel=1e-12)
    assert frame.variables['TK1.in0.pressure_pa'] == pytest.approx(spec.initial_pressure_pa, rel=1e-12)
    assert frame.variables['TK1.state.net_inflow_kg_s'] == pytest.approx(
        frame.variables['L1.mass_flow_kg_s'] - frame.variables['L2.mass_flow_kg_s'], abs=1e-12)
    assert any(d.code == 'STEADY_TANK_AS_RESERVOIR' for d in frame.diagnostics)


def test_level_follows_the_implicit_euler_recursion_of_the_linear_ode():
    network = compile_project(fed_tank())
    spec, a, b = linear_ode(network)
    frames = solve_dynamic(network, 60., 1.)
    expected = euler_masses(spec.initial_mass_kg, a, b, 1., 60)
    assert len(frames) == 61
    for frame, mass in zip(frames, expected):
        assert frame.variables['TK1.state.mass_kg'] == pytest.approx(mass, abs=1e-6)
    # The run actually moves: the level relaxes towards the equilibrium M* = a/b.
    moved = frames[-1].variables['TK1.state.mass_kg'] - spec.initial_mass_kg
    assert moved == pytest.approx((a / b - spec.initial_mass_kg) * (1 - (1 + b) ** -60), rel=1e-6)
    assert abs(moved) > .05
    assert any(d.code == 'DYNAMIC_IMPLICIT_EULER' for d in frames[-1].diagnostics)
    assert not any(d.code == 'DYNAMIC_QUASI_STEADY' for d in frames[-1].diagnostics)


def test_time_step_halving_halves_the_error_first_order():
    network = compile_project(fed_tank())
    spec, a, b = linear_ode(network)
    exact = a / b + (spec.initial_mass_kg - a / b) * math.exp(-b * 20.)
    errors = [abs(solve_dynamic(network, 20., dt)[-1].variables['TK1.state.mass_kg'] - exact) for dt in (2., 1., .5)]
    assert 1.8 < errors[0] / errors[1] < 2.2 and 1.8 < errors[1] / errors[2] < 2.2


def test_mass_ledger_closes_on_every_step():
    frames = solve_dynamic(compile_project(fed_tank()), 10., .5)
    for before, after in zip(frames, frames[1:]):
        net = after.variables['L1.mass_flow_kg_s'] - after.variables['L2.mass_flow_kg_s']
        assert after.variables['TK1.state.net_inflow_kg_s'] == pytest.approx(net, abs=1e-8)
        delta = after.variables['TK1.state.mass_kg'] - before.variables['TK1.state.mass_kg']
        assert delta == pytest.approx(.5 * after.variables['TK1.state.net_inflow_kg_s'], abs=1e-12)
        assert after.metrics['storage_mass_rate_kg_s'] == after.variables['TK1.state.net_inflow_kg_s']


def test_tank_temperature_mixes_with_the_inflow_by_the_enthalpy_recursion():
    frames = solve_dynamic(compile_project(fed_tank(t_in=333.15)), 30., 1.)
    h_in = WATER.state_pt(111500., 333.15).enthalpy_j_kg  # adiabatic horizontal pipe: isenthalpic
    for before, after in zip(frames, frames[1:]):
        inflow = after.variables['L1.mass_flow_kg_s']
        mass = before.variables['TK1.state.mass_kg']
        h_old = before.variables['TK1.in0.enthalpy_j_kg']
        expected = (mass * h_old + inflow * h_in) / (mass + inflow)
        assert after.variables['TK1.in0.enthalpy_j_kg'] == pytest.approx(expected, rel=1e-9)
        # Outflow leaves at the mixed tank state.
        assert after.variables['L2.inlet_temperature_k'] == pytest.approx(after.variables['TK1.state.temperature_k'], abs=1e-9)
    assert 293.2 < frames[-1].variables['TK1.state.temperature_k'] < 333.15


def test_heater_and_heat_loss_follow_the_energy_balance():
    params = {'level_m': 1., 'area_m2': 1., 'heat_input_w': 10000., 'heat_loss_ua_w_k': 200.,
              'ambient_temperature_k': 283.15}
    p = project([('B1', 'source', {'pressure_pa': 200000.}), ('V1', 'valve', {'opening_ratio': 0.}),
                 ('TK1', 'tank', params)], [('B1:out0', 'V1:in0'), ('V1:out0', 'TK1:in0')])
    frames = solve_dynamic(compile_project(p), 3600., 60.)
    for before, after in zip(frames, frames[1:]):
        mass = after.variables['TK1.state.mass_kg']
        assert mass == before.variables['TK1.state.mass_kg']
        t = after.variables['TK1.state.temperature_k']
        stored = mass * (after.variables['TK1.in0.enthalpy_j_kg'] - before.variables['TK1.in0.enthalpy_j_kg']) / 60.
        assert stored == pytest.approx(10000. - 200. * (t - 283.15), rel=1e-6, abs=1e-3)
        assert after.metrics['storage_power_w'] == pytest.approx(stored, rel=1e-6, abs=1e-3)
    # Constant-cp implicit Euler: T_n = T∞ + (T0 − T∞)·(1 + dt·UA/(M·cp))^−n with T∞ = T_amb + Q/UA.
    mass, cp = frames[0].variables['TK1.state.mass_kg'], WATER.state_pt(110000., 300.).specific_heat_j_kg_k
    expected = 333.15 + (293.15 - 333.15) * (1 + 60. * 200. / (mass * cp)) ** -60
    assert frames[-1].variables['TK1.state.temperature_k'] == pytest.approx(expected, abs=.02)


def test_closed_loop_held_only_by_a_tank_stores_the_pump_work():
    p = project([('TK1', 'tank', {'level_m': 1., 'area_m2': .5}), ('P1', 'pump', {}),
                 ('L1', 'pipe', {'length_m': 20., 'diameter_m': .05, 'roughness_m': 4.5e-5})],
                [('TK1:out0', 'P1:in0'), ('P1:out0', 'L1:in0'), ('L1:out0', 'TK1:in0')])
    network = compile_project(p)
    steady = solve_steady(network)
    assert not any(d.code == 'THERMAL_REFERENCE_FROM_BOUNDARY' for d in steady.diagnostics)
    frames = solve_dynamic(network, 100., 10.)
    for before, after in zip(frames, frames[1:]):
        assert after.variables['TK1.state.mass_kg'] == pytest.approx(before.variables['TK1.state.mass_kg'], abs=1e-6)
        shaft = after.variables['P1.shaft_power_w']
        assert after.metrics['storage_power_w'] == pytest.approx(shaft, rel=1e-6)
    assert frames[-1].variables['TK1.state.temperature_k'] > frames[0].variables['TK1.state.temperature_k']


def drain(height=3.):
    return project([('TK1', 'tank', {'level_m': .2, 'area_m2': .05, 'height_m': height}),
                    ('V1', 'valve', {'opening_ratio': 1., 'kv_m3_h': 1.}), ('B2', 'source', {'pressure_pa': 90000.})],
                   [('TK1:out0', 'V1:in0'), ('V1:out0', 'B2:out0')])


def test_draining_tank_stops_at_the_empty_event_and_keeps_its_history():
    with pytest.raises(SolveFailed) as raised:
        solve_dynamic(compile_project(drain()), 600., 10.)
    error = raised.value
    assert error.diagnostic.code == 'TANK_EMPTY' and error.diagnostic.instance_id == 'TK1'
    frames = error.frames
    last = frames[-1]
    assert last.variables['TK1.state.mass_kg'] == pytest.approx(0., abs=1e-4)
    assert last.time_s % 10. != 0  # the event frame sits between grid frames
    assert [f.time_s for f in frames[:-1]] == pytest.approx([10. * i for i in range(len(frames) - 1)])


def test_filling_tank_stops_at_the_full_event():
    p = project([('B1', 'source', {'pressure_pa': 150000.}), ('V1', 'valve', {'opening_ratio': 1., 'kv_m3_h': 1.}),
                 ('TK1', 'tank', {'level_m': .5, 'area_m2': .05, 'height_m': 1.})],
                [('B1:out0', 'V1:in0'), ('V1:out0', 'TK1:in0')])
    with pytest.raises(SolveFailed) as raised:
        solve_dynamic(compile_project(p), 600., 10.)
    assert raised.value.diagnostic.code == 'TANK_FULL'
    assert raised.value.frames[-1].variables['TK1.state.level_m'] == pytest.approx(1., abs=1e-5)


def test_tank_event_through_the_api_is_failed_with_partial_history():
    with TestClient(create_app()) as client:
        body = {'project': drain().model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 600., 'dt_s': 10.}
        created = client.post('/api/v1/runs', json=body).json()
        assert created['status'] == 'failed'
        assert created['frame']['diagnostics'][0]['code'] == 'TANK_EMPTY'
        rows = client.get(f"/api/v1/runs/{created['run_id']}/history").json()['rows']
        assert len(rows) > 2 and rows[-1]['time_s'] == created['frame']['time_s']
        health = client.get('/api/v1/health').json()['capabilities']
        assert health['tank_state'] is True and health['time_integration'] == 'implicit_euler'


def module_tank():
    module = custom_module()
    return project([('B1', 'source', {'pressure_pa': 111500.}), ('V1', module.id, {'opening_ratio': .5, 'kv_m3_h': 1.}),
                    ('TK1', 'tank', tank()), ('L2', 'pipe', LAMINAR), ('B2', 'source', {'pressure_pa': 110500.})],
                   [('B1:out0', 'V1:in0'), ('V1:out0', 'TK1:in0'), ('TK1:out0', 'L2:in0'), ('L2:out0', 'B2:out0')],
                   extra_modules=[module])


def test_failed_substeps_are_halved_and_change_nothing(monkeypatch):
    real = solver.solve_network
    failed, accepted = [], []
    network = compile_project(module_tank())
    tank_node = network.port_nodes['TK1:in0']
    valve = next(i for i, b in enumerate(network.branches) if b.instance_id == 'V1')

    def flaky(network, runners=None, time_s=0., warm=None, service=None, storage_step=None):
        # Every step longer than 0.3 s fails: 1 s → 0.5 → 0.25 ok, then 0.75 → 0.375 → 0.1875 ok, ...
        if storage_step is not None and storage_step[0] > .3:
            failed.append(storage_step[0])
            raise solver.HydraulicNotConverged('injected')
        result = real(network, runners, time_s, warm, service, storage_step)
        if storage_step is not None:
            accepted.append((storage_step[0], float(result.hydraulic.flows[valve]), result.hydraulic.storage_rates[tank_node]))
        return result

    monkeypatch.setattr(solver, 'solve_network', flaky)
    frames = solve_dynamic(network, 2., 1.)
    assert [f.time_s for f in frames] == [0., 1., 2.]
    assert failed and all(h > .3 for h in failed) and all(h <= .3 for h, _, _ in accepted)
    assert sum(h for h, _, _ in accepted) == pytest.approx(2., abs=1e-12)
    # Failed attempts left no trace: module and tank states add up over the accepted substeps only.
    assert frames[-1].variables['V1.state.commit_count'] == len(accepted)
    assert frames[-1].variables['V1.state.throughput_kg'] == pytest.approx(sum(h * abs(q) for h, q, _ in accepted), rel=1e-12)
    initial = network.storage[tank_node].initial_mass_kg
    assert frames[-1].variables['TK1.state.mass_kg'] == pytest.approx(initial + sum(h * r for h, _, r in accepted), rel=1e-14)


def test_step_that_never_converges_reports_step_not_converged(monkeypatch):
    real = solver.solve_network

    def broken(network, runners=None, time_s=0., warm=None, service=None, storage_step=None):
        if storage_step is not None:
            raise solver.HydraulicNotConverged('injected')
        return real(network, runners, time_s, warm, service, storage_step)

    monkeypatch.setattr(solver, 'solve_network', broken)
    with pytest.raises(SolveFailed) as raised:
        solve_dynamic(compile_project(fed_tank()), 2., 1.)
    assert raised.value.diagnostic.code == 'STEP_NOT_CONVERGED'
    assert [f.time_s for f in raised.value.frames] == [0.]


def test_without_thermal_layer_the_tank_keeps_its_temperature():
    network = compile_project(fed_tank(t_in=333.15, thermal=False))
    spec, a, b = linear_ode(network)
    frames = solve_dynamic(network, 10., 1.)
    assert frames[-1].variables['TK1.state.temperature_k'] == pytest.approx(293.15, abs=1e-9)
    assert frames[-1].variables['TK1.state.mass_kg'] == pytest.approx(euler_masses(spec.initial_mass_kg, a, b, 1., 10)[-1],
                                                                      abs=1e-6)
    assert 'storage_power_w' not in frames[-1].metrics


@pytest.mark.parametrize('case, code', [
    ('source_on_tank', 'STORAGE_CONFLICT'), ('two_tanks', 'STORAGE_CONFLICT'),
    ('over_height', 'PARAMETER_RANGE'), ('vapour', 'PHASE_UNSUPPORTED')])
def test_invalid_tanks_are_compile_errors(case, code):
    if case == 'source_on_tank':
        p = project([('B1', 'source', {'pressure_pa': 2e5}), ('TK1', 'tank', tank())], [('B1:out0', 'TK1:in0')])
    elif case == 'two_tanks':
        p = project([('TK1', 'tank', tank()), ('TK2', 'tank', tank())], [('TK1:out0', 'TK2:in0')])
    elif case == 'over_height':
        p = fed_tank(tank_params={'level_m': 4.})
    else:
        p = fed_tank(tank_params={'temperature_k': 383.15})
    with pytest.raises(CompilationError) as raised:
        compile_project(p)
    assert raised.value.diagnostic.code == code


def test_prototype_tank_control_runs_dynamically():
    network = compile_project(prototype('tank-control'))
    frames = solve_dynamic(network, 20., 1.)
    levels = [f.variables['TK1.state.level_m'] for f in frames]
    assert levels[0] == pytest.approx(2.0, rel=1e-12) and levels[-1] != levels[0]
    assert all(f.metrics['energy_residual_w'] == pytest.approx(0., abs=1e-3) for f in frames)


# --- M2: pipe heat capacity (thermal_cells) --------------------------------------------------------

PIPE = {'length_m': 30., 'diameter_m': .04, 'roughness_m': 4.5e-5}


def cell_line(cells, ua=0., t_in=333.15, ambient=293.15, inlet=250000., outlet=120000., wall=0., **solver_options):
    params = {**PIPE, 'thermal_cells': cells, 'heat_loss_ua_w_k': ua, 'ambient_temperature_k': ambient,
              'wall_heat_capacity_j_k': wall}
    return project([('B1', 'source', {'pressure_pa': inlet, 'temperature_k': t_in}), ('L1', 'pipe', params),
                    ('B2', 'source', {'pressure_pa': outlet, 'temperature_k': t_in})],
                   [('B1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')], **solver_options)


def series_outlet(w, cells, ua, upstream, h_env):
    """N well-mixed cells in series: h_out = h_env + (h_in − h_env)·(w/(w + UA/(N·cp)))^N."""
    ratio = w / (w + ua / (cells * upstream.specific_heat_j_kg_k))
    return h_env + (upstream.enthalpy_j_kg - h_env) * ratio ** cells


def test_steady_cell_profile_follows_the_series_formula_and_tends_to_the_exponential():
    upstream, h_env = WATER.state_pt(250000., 333.15), WATER.state_pt(120000., 293.15).enthalpy_j_kg
    outlets = []
    for cells in (1, 5, 25):
        frame = solve_steady(compile_project(cell_line(cells, ua=2000.)))
        w = abs(frame.variables['L1.mass_flow_kg_s'])
        expected = series_outlet(w, cells, 2000., upstream, h_env)
        assert frame.variables['L1.out0.enthalpy_j_kg'] == pytest.approx(expected, rel=1e-12)
        assert frame.variables['L1.state.stored_power_w'] == 0.
        outlets.append(frame.variables['L1.out0.temperature_k'])
    exact = solve_steady(compile_project(cell_line(0, ua=2000.))).variables['L1.out0.temperature_k']
    # First order in 1/N: five times the cells, a fifth of the gap to the exponential (exact) profile.
    gaps = [abs(t - exact) for t in outlets]
    assert gaps[0] > gaps[1] > gaps[2] and 4.5 < gaps[1] / gaps[2] < 5.5


def test_cells_with_constant_inputs_stay_at_their_steady_profile():
    frames = solve_dynamic(compile_project(cell_line(8, ua=2000., wall=50000.)), 20., 2.)
    assert any(d.code == 'DYNAMIC_IMPLICIT_EULER' for d in frames[0].diagnostics)
    outlet = [f.variables['L1.out0.temperature_k'] for f in frames]
    assert max(outlet) - min(outlet) < 1e-9
    assert all(abs(f.variables['L1.state.stored_power_w']) < 1e-4 for f in frames)


def test_stagnant_pipe_cools_by_the_implicit_cell_recursion():
    params = {**PIPE, 'thermal_cells': 4, 'heat_loss_ua_w_k': 40., 'ambient_temperature_k': 293.15,
              'wall_heat_capacity_j_k': 20000.}
    p = project([('B1', 'source', {'pressure_pa': 200000., 'temperature_k': 353.15}), ('V1', 'valve', {'opening_ratio': 0.}),
                 ('L1', 'pipe', params), ('B2', 'source', {'pressure_pa': 200000., 'temperature_k': 353.15})],
                [('B1:out0', 'V1:in0'), ('V1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])
    frames = solve_dynamic(compile_project(p), 1800., 60.)
    hot, h_env = WATER.state_pt(200000., 353.15), WATER.state_pt(200000., 293.15).enthalpy_j_kg
    volume = math.pi * .04 ** 2 / 4 * 30. / 4
    mass = hot.density_kg_m3 * volume + 20000. / 4 / hot.specific_heat_j_kg_k
    g = 40. / (4 * hot.specific_heat_j_kg_k)
    h = hot.enthalpy_j_kg
    for frame in frames[1:]:
        h_new = (mass / 60. * h + g * h_env) / (mass / 60. + g)
        assert frame.variables['L1.state.stored_power_w'] == pytest.approx(4 * mass * (h_new - h) / 60., rel=1e-9)
        h = h_new
        assert frame.variables['L1.state.mean_temperature_k'] == pytest.approx(
            WATER.state_ph(200000., h).temperature_k, abs=1e-9)
    assert 293.15 < frames[-1].variables['L1.state.mean_temperature_k'] < 353.15 - 5


def heated_tank_line(cells):
    pipe = {**PIPE, 'length_m': 60., 'thermal_cells': cells}
    return project([('B1', 'source', {'pressure_pa': 160000.}), ('V1', 'valve', {'opening_ratio': .3, 'kv_m3_h': 2.}),
                    ('TK1', 'tank', {'level_m': .5, 'area_m2': .2, 'heat_input_w': 200000.}), ('L1', 'pipe', pipe),
                    ('B2', 'source', {'pressure_pa': 101325.})],
                   [('B1:out0', 'V1:in0'), ('V1:out0', 'TK1:in0'), ('TK1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])


def test_pipe_cells_delay_a_rising_inlet_temperature_and_store_its_energy():
    without = solve_dynamic(compile_project(heated_tank_line(0)), 60., 2.)
    # Enthalpy, not temperature: the outlet sits at a lower pressure (isenthalpic, ~1e-6 K colder).
    for frame in without[1:]:
        assert frame.variables['L1.out0.enthalpy_j_kg'] == pytest.approx(frame.variables['TK1.in0.enthalpy_j_kg'], rel=1e-12)
    lags = []
    for frame in solve_dynamic(compile_project(heated_tank_line(10)), 60., 2.)[1:]:
        tank_h, out_h = frame.variables['TK1.in0.enthalpy_j_kg'], frame.variables['L1.out0.enthalpy_j_kg']
        assert out_h < tank_h
        lags.append(frame.variables['TK1.state.temperature_k'] - frame.variables['L1.out0.temperature_k'])
        # Adiabatic cells: the enthalpy the stream loses is exactly what the cells store.
        assert frame.variables['L1.heat_w'] == pytest.approx(-frame.variables['L1.state.stored_power_w'], rel=1e-9, abs=1e-6)
    assert lags[-1] > .05


def test_reversed_flow_runs_through_the_cells_backwards():
    p = cell_line(6, ua=1500., inlet=120000., outlet=250000.)
    frame = solve_steady(compile_project(p))
    assert frame.variables['L1.mass_flow_kg_s'] < 0
    upstream, h_env = WATER.state_pt(250000., 333.15), WATER.state_pt(120000., 293.15).enthalpy_j_kg
    expected = series_outlet(abs(frame.variables['L1.mass_flow_kg_s']), 6, 1500., upstream, h_env)
    assert frame.variables['L1.in0.enthalpy_j_kg'] == pytest.approx(expected, rel=1e-12)
    frames = solve_dynamic(compile_project(p), 6., 2.)
    assert max(abs(f.variables['L1.in0.temperature_k'] - frames[0].variables['L1.in0.temperature_k']) for f in frames) < 1e-9


def test_cells_without_the_thermal_layer_stay_quasi_steady():
    frames = solve_dynamic(compile_project(cell_line(5, thermal=False)), 1., .5)
    assert any(d.code == 'DYNAMIC_QUASI_STEADY' for d in frames[0].diagnostics)
    assert 'L1.state.mean_temperature_k' not in frames[-1].variables


@pytest.mark.parametrize('cells, code', [(2.5, 'PARAMETER_INVALID'), (51, 'PARAMETER_RANGE'), (-1, 'PARAMETER_RANGE')])
def test_invalid_cell_counts_are_compile_errors(cells, code):
    with pytest.raises(CompilationError) as raised:
        compile_project(cell_line(cells))
    assert raised.value.diagnostic.code == code
