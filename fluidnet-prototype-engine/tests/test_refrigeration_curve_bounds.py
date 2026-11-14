"""Curve-pump volume coordinates retain physical mass balances and consistent derivatives."""
import inspect

import numpy as np

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.refrigeration import devices, network as graph_solver
from fn_engine.refrigeration.examples import station_example
from fn_engine.sessions import create_session


def test_small_graph_jacobian_matches_physical_equations_in_volume_coordinates(monkeypatch):
    host = compile_project(station_example())
    session = create_session(host, 30., 30.)
    try:
        session.initialize()
        service = session.services['LP1']
        vessels = {'LP1': devices.vessel_state(service, host.parameters['LP1'],
                                              session.masses['LP1'], session.energies['LP1'])}
        catalog = catalog_map()
        host.parameters['Pump'] = {p.id: p.default for p in catalog['refrigerant_curve_pump'].parameters}
        host.parameters['Pipe'] = {p.id: p.default for p in catalog['refrigerant_network_pipe'].parameters}
        host.parameters['Pipe'].update(length_m=10., diameter_m=.02)
        component = graph_solver.Component(
            [graph_solver.Edge('Pump', 'Pump', 'refrigerant_curve_pump', 'a', 'b'),
             graph_solver.Edge('Pipe', 'Pipe', 'refrigerant_network_pipe', 'b', 'c')],
            ['a', 'b', 'c'], {'a': ('LP1', 'liquid'), 'c': ('LP1', 'in0')},
            {'a': 'LP1', 'b': 'LP1', 'c': 'LP1'})
        original = np.linalg.solve
        checked = False

        def solve(matrix, rhs):
            nonlocal checked
            caller = inspect.currentframe().f_back
            if caller.f_code is graph_solver._component_point.__code__ and not checked:
                local = caller.f_locals
                vector = local['vector']
                rows = local['rows']
                expected = np.empty_like(matrix)
                for column in range(len(vector)):
                    delta = 1e-6 * max(1., abs(vector[column]))
                    plus, minus = vector.copy(), vector.copy()
                    plus[column] += delta
                    minus[column] -= delta
                    expected[:, column] = (rows(plus)[0] - rows(minus)[0]) / (2*delta)
                error = np.max(np.abs(matrix-expected) / np.maximum(1., np.abs(expected)))
                assert error < 1e-4
                checked = True
            return original(matrix, rhs)

        monkeypatch.setattr(np.linalg, 'solve', solve)
        # Compare derivatives away from the liquid/two-phase saturation boundary.
        warm = {'p': {'b': vessels['LP1'].pressure_pa+50000.},
                'h': {'b': vessels['LP1'].liquid_enthalpy_j_kg},
                'm': {'Pump': .1, 'Pipe': .1}, 'pumps': {'Pump': (1., 1.)}}
        points, cache, pressure_error, mass_error = graph_solver._component_point(
            component, host, service, vessels, {}, {}, warm, {}, None)
        assert checked
        state, rho, _ = graph_solver.mixture(service, points['Pump']['inlet_pressure_pa'],
                                            points['Pump']['inlet_enthalpy_j_kg'])
        volume = points['Pump']['mass_flow_kg_s'] / rho * 3600.
        assert 0. < volume <= host.parameters['Pump']['head_curve'][-1][0]
        assert state.phase in ('liquid', 'twophase', 'supercritical_liquid')
        assert cache['m']['Pump'] == points['Pump']['mass_flow_kg_s']
        assert pressure_error <= host.project.solver.pressure_tolerance_pa
        assert mass_error <= host.project.solver.mass_tolerance_kg_s
    finally:
        session.close()


def test_single_curve_pump_solves_in_declared_volume_coordinates():
    host = compile_project(station_example())
    session = create_session(host, 30., 30.)
    try:
        session.initialize()
        service = session.services['LP1']
        params = dict(host.parameters['LP1'])
        host.parameters['A'] = params
        host.parameters['B'] = {**params, 'temperature_k': params['temperature_k']+1.}
        vessels = {key: devices.vessel_state(service, host.parameters[key],
            *devices.vessel_initial(service, host.parameters[key])) for key in ('A', 'B')}
        host.parameters['Pump'] = {p.id: p.default for p in catalog_map()['refrigerant_curve_pump'].parameters}
        component = graph_solver.Component(
            [graph_solver.Edge('Pump', 'Pump', 'refrigerant_curve_pump', 'a', 'b')],
            ['a', 'b'], {'a': ('A', 'liquid'), 'b': ('B', 'liquid')}, {'a': 'A', 'b': 'B'})
        points, cache, pressure_error, mass_error = graph_solver._component_point(
            component, host, service, vessels, {}, {}, {}, {}, None)
        point = points['Pump']
        _, rho, _ = graph_solver.mixture(service, point['inlet_pressure_pa'], point['inlet_enthalpy_j_kg'])
        volume = point['mass_flow_kg_s']/rho*3600.
        assert 0. < volume <= host.parameters['Pump']['head_curve'][-1][0]
        assert point['outlet_pressure_pa'] > point['inlet_pressure_pa']
        assert cache['m']['Pump'] == point['mass_flow_kg_s']
        assert pressure_error <= host.project.solver.pressure_tolerance_pa
        assert mass_error <= host.project.solver.mass_tolerance_kg_s
    finally:
        session.close()
