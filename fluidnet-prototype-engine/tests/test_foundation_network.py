"""Graph physics must respond to geometry and retain all reservoir inventory."""
from pathlib import Path
import runpy

import pytest

from fn_engine.checkpoints import capture, restore
from fn_engine.compiler import compile_project
from fn_engine.model_types.domain import Project
from fn_engine.refrigeration.network_examples import network_example
from fn_engine.sessions import create_session


@pytest.mark.parametrize('reverse', [False, True])
def test_refrigerant_check_valve_closes_reverse_flow_and_strainer_adds_resistance(reverse):
    from fn_engine.catalog import catalog_map
    from fn_engine.models import ModuleInstance, Connection, Endpoint, FluidConfig
    catalog = catalog_map()
    project = Project(id='check-filter', name='check-filter', fluid=FluidConfig(fluid='R134a', phase_policy='any'),
        modules=[catalog[k] for k in ('hp_receiver', 'refrigerant_check_valve', 'refrigerant_strainer', 'refrigerant_network_pipe')],
        instances=[ModuleInstance(id='A', module_id='hp_receiver', name='A', parameters={'temperature_k': 260. if reverse else 300.}),
                   ModuleInstance(id='B', module_id='hp_receiver', name='B', parameters={'temperature_k': 300. if reverse else 260.}),
                   ModuleInstance(id='CV', module_id='refrigerant_check_valve', name='CV', parameters={'kv_m3_h': .02}),
                   ModuleInstance(id='Filter', module_id='refrigerant_strainer', name='Filter', parameters={'diameter_m': .01}),
                   ModuleInstance(id='Return', module_id='refrigerant_network_pipe', name='Return', parameters={'diameter_m': .004})],
        connections=[Connection(id=str(i), source=Endpoint(instance_id=a, port_id=b), target=Endpoint(instance_id=c, port_id=d))
            for i, (a, b, c, d) in enumerate([('A', 'liquid', 'CV', 'in0'), ('CV', 'out0', 'Filter', 'in0'), ('Filter', 'out0', 'B', 'in0'),
                                             ('B', 'liquid', 'Return', 'in0'), ('Return', 'out0', 'A', 'in0')])])
    session = create_session(compile_project(project), .01, .01)
    try:
        frame = session.initialize()
        if reverse:
            assert abs(frame.variables['CV.mass_flow_kg_s']) < 1e-12
        else:
            flow = frame.variables['CV.mass_flow_kg_s']
            assert flow > 0.
            assert frame.variables['Filter.pressure_drop_pa'] > 0.
            assert frame.variables['Filter.mass_flow_kg_s'] == pytest.approx(flow, abs=1e-10)
        frame = session.advance()
        assert abs(frame.metrics['energy_residual_j']) < .01
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
    finally: session.close()


def test_public_correlation_and_independent_laminar_limit():
    script = Path(__file__).parents[1] / 'scripts/validate_foundation_reference.py'
    result = runpy.run_path(str(script))['evaluate_reference']()
    assert result['passed'], result


@pytest.mark.parametrize('same_length', [False, True])
def test_geometry_sets_branch_flows_and_curve_pump_workpoint(same_length):
    project = network_example()
    if same_length:
        for i in project.instances:
            if i.id == 'SupplyPipe-2': i.parameters['length_m'] = 3.
            if i.id == 'ReturnPipe-2': i.parameters['length_m'] = 5.
    # IDs carry no physical meaning; persisted custom projects use the same solver.
    ids = {i.id: f'Device{n}' for n, i in enumerate(project.instances)}
    for i in project.instances: i.id = ids[i.id]
    for edge in project.connections:
        edge.source.instance_id = ids[edge.source.instance_id]
        edge.target.instance_id = ids[edge.target.instance_id]
    session = create_session(compile_project(Project.model_validate_json(project.model_dump_json())), .1, .1)
    try:
        frame = session.initialize()
        v = frame.variables
        flow = lambda name: v[f'{ids[name]}.mass_flow_kg_s']
        assert flow('Pump') == pytest.approx(flow('Cooler-1') + flow('Cooler-2'), abs=1e-9)
        if same_length:
            assert flow('Cooler-1') == pytest.approx(flow('Cooler-2'), rel=1e-7)
        else:
            assert flow('Cooler-1') > flow('Cooler-2') > 0.
        rho = v[f'{ids["Low"]}.liquid_density_kg_m3']
        volume_flow = flow('Pump') / rho * 3600.
        points = [(0., 15.), (.3, 12.), (.6, 7.), (.9, 0.)]
        a, b = next((a, b) for a, b in zip(points, points[1:]) if a[0] <= volume_flow <= b[0])
        head = a[1] + (b[1] - a[1]) * (volume_flow - a[0]) / (b[0] - a[0])
        assert v[f'{ids["Pump"]}.pressure_rise_pa'] == pytest.approx(rho * 9.80665 * head, rel=1e-7)
        frame = session.advance()
        assert abs(frame.metrics['energy_residual_j']) < .05
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert frame.metrics['network_pressure_residual_pa'] < project.solver.pressure_tolerance_pa
    finally:
        session.close()


def test_pipe_inventory_is_dynamic_conserved_and_restorable():
    session = create_session(compile_project(network_example(True)), .2, .1)
    resumed = None
    try:
        first = session.initialize()
        frame = session.advance()
        key = 'PipeInventory.state.mass_kg'
        assert abs(frame.variables[key] - first.variables[key]) > 1e-8
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert abs(frame.metrics['energy_residual_j']) < .05
        resumed = restore(capture(session))
        left, right = session.advance(), resumed.advance()
        for name, value in left.variables.items():
            if '.state.' in name and isinstance(value, (int, float)):
                assert right.variables[name] == pytest.approx(value, rel=1e-8, abs=1e-6), name
    finally:
        session.close()
        if resumed is not None: resumed.close()


def test_passive_backflow_draws_actual_reservoir_bulk_enthalpy():
    from fn_engine.catalog import catalog_map
    from fn_engine.models import ModuleInstance, Connection, Endpoint, FluidConfig
    catalog = catalog_map()
    project = Project(id='backflow', name='backflow', fluid=FluidConfig(fluid='R134a', phase_policy='any'),
        modules=[catalog[k] for k in ('hp_receiver', 'refrigerant_network_pipe')],
        instances=[ModuleInstance(id='A', module_id='hp_receiver', name='A', parameters={'temperature_k': 260.}),
                   ModuleInstance(id='B', module_id='hp_receiver', name='B', parameters={'temperature_k': 300.}),
                   ModuleInstance(id='P', module_id='refrigerant_network_pipe', name='P', parameters={'diameter_m': .004}),
                   ModuleInstance(id='Q', module_id='refrigerant_network_pipe', name='Q', parameters={'diameter_m': .004})],
        connections=[Connection(id=str(i), source=Endpoint(instance_id=a, port_id=b), target=Endpoint(instance_id=c, port_id=d))
                     for i, (a, b, c, d) in enumerate([('A','liquid','P','in0'), ('P','out0','B','in0'),
                                                      ('B','liquid','Q','in0'), ('Q','out0','A','in0')])])
    session = create_session(compile_project(project), .01, .01)
    try:
        first = session.initialize()
        vessel = session._current()['vessels']['B']
        bulk_h = (vessel.internal_energy_j + vessel.pressure_pa * session.network.parameters['B']['volume_m3']) / vessel.mass_kg
        assert first.variables['P.mass_flow_kg_s'] < 0.
        assert first.variables['P.inlet_enthalpy_j_kg'] == pytest.approx(bulk_h, abs=1e-6)
        frame = session.advance()
        assert abs(frame.metrics['energy_residual_j']) < .001
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
    finally: session.close()


@pytest.mark.parametrize('kind', ['horizontal_drum', 'headed_receiver'])
def test_graph_reservoir_inlet_enthalpy_uses_geometric_volume(kind):
    from fn_engine.catalog import catalog_map
    from fn_engine.refrigeration.vessel_ports import port_state
    project = network_example()
    catalog = catalog_map()
    reservoir = next(i for i in project.instances if i.id == 'Low')
    reservoir.module_id = kind
    allowed = {p.id for p in catalog[kind].parameters}
    reservoir.parameters = {k: v for k, v in reservoir.parameters.items() if k in allowed}
    project.modules = [catalog[k] for k in {i.module_id for i in project.instances}]
    session = create_session(compile_project(project), .01, .01)
    try:
        frame = session.initialize()
        state = session._current()['vessels']['Low']
        assert state.volume_m3 > 0.
        pressure, enthalpy, _ = port_state(session.network.parameters['Low'], state, 'in0')
        assert enthalpy == pytest.approx((state.internal_energy_j + pressure * state.volume_m3) / state.mass_kg)
        assert frame.variables['Pump.mass_flow_kg_s'] > 0.
        frame = session.advance()
        assert abs(frame.metrics['energy_residual_j']) < .001
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
    finally: session.close()
