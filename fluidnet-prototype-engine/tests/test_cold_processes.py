"""Physical ledger and phase tests for the declared cold-store reference models."""
from copy import deepcopy

import pytest

from fn_engine.catalog import catalog_map
from fn_engine.checkpoints import capture, restore
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.refrigeration.process_examples import process_example
from fn_engine.refrigeration.processes import goods_state, goods_enthalpy, frost_state, door_exchange, FUSION
from fn_engine.refrigeration.cycle import DeviceRangeError
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed


def params(module):
    return {p.id: p.default for p in catalog_map()[module].parameters}


def test_goods_latent_plateau_and_temperature_limits():
    p = params('logistics_cold_room')
    m, latent, freeze = p['goods_mass_kg'], p['goods_latent_heat_j_kg'], p['goods_freezing_temperature_k']
    assert goods_state(p, m * latent / 2.) == (freeze, .5)
    assert goods_state(p, m * latent) == (freeze, 0.)
    assert goods_state(p, 0.) == (freeze, 1.)
    for t in (250., 280.):
        assert goods_state(p, m * goods_enthalpy(p, t))[0] == pytest.approx(t)


def test_frost_melting_uses_latent_energy_and_drain_water():
    p = params('frost_hotgas_cooler')
    assert frost_state(p, 2., FUSION) == (273.15, 1., 1.)
    assert frost_state(p, 2., 2. * FUSION) == (273.15, 0., 2.)
    assert frost_state(p, 2., 2. * FUSION + (p['metal_heat_capacity_j_k'] + 2. * 4180.) * 5.) == (278.15, 0., 2.)


def test_door_closed_and_protection_zero_flux_and_warm_open_heat():
    p = params('logistics_cold_room')
    assert door_exchange(p, 255.15, .001)[0] == 0.
    p['door_opening_ratio'] = 1.
    m, w, q = door_exchange(p, 255.15, .001)
    assert m > 0. and w > .001 and q > 0.
    p['door_protection_efficiency'] = 1.
    assert door_exchange(p, 255.15, .001)[::2] == (0., 0.)


def test_hotgas_requires_complete_flow_path():
    project = process_example(True)
    project.connections = [e for e in project.connections if e.id != 'hot-drain']
    with pytest.raises(CompilationError, match='热气进口'):
        compile_project(project)


def test_process_inventory_energy_and_checkpoint_continuation():
    session = create_session(compile_project(process_example(True, True)), .3, .1)
    resumed = None
    try:
        start = session.initialize()
        frame = session.advance()
        assert frame.variables['Cooler-1.frost_mass_kg'] > start.variables['Cooler-1.frost_mass_kg']
        assert frame.variables['Room-1.state.goods_energy_j'] < start.variables['Room-1.state.goods_energy_j']
        assert abs(frame.variables['Oil.oil_mass_residual_kg']) < 1e-9
        assert abs(frame.metrics['water_mass_residual_kg']) < 1e-9
        assert abs(frame.metrics['energy_residual_j']) < .001
        resumed = restore(capture(session))
        a, b = session.advance(), resumed.advance()
        for k, v in a.variables.items():
            if '.state.' in k and isinstance(v, (int, float)):
                assert b.variables[k] == pytest.approx(v, rel=1e-9, abs=1e-7), k
        assert session.process_modes == resumed.process_modes
        assert 'Cooler-1.state.surface_energy_j' in session.report_keys
    finally:
        session.close()
        if resumed is not None: resumed.close()


def test_hotgas_heat_enters_surface_with_refrigerant_mass_energy_conserved():
    project = process_example(True)
    cooler = next(i for i in project.instances if i.id == 'Cooler-1')
    cooler.parameters.update(defrost_request=1., predrain_duration_s=0., defrost_duration_s=1., electric_defrost_power_w=100.)
    session = create_session(compile_project(project), .1, .1)
    try:
        start = session.initialize()
        frame = session.advance()
        assert frame.variables['Cooler-1.defrost_mode'] == 2
        assert frame.variables['Cooler-1.state.heater_energy_j'] == pytest.approx(10.)
        assert frame.variables['Cooler-1.hot_gas_heat_w'] > 0.
        assert frame.variables['Cooler-1.hot_mass_flow_kg_s'] > 0.
        assert frame.variables['Cooler-1.mass_flow_kg_s'] == 0.
        assert frame.variables['Cooler-1.state.surface_energy_j'] > start.variables['Cooler-1.state.surface_energy_j']
        assert abs(frame.metrics['energy_residual_j']) < .001
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
    finally: session.close()


def test_failure_rolls_back_process_mode_water_oil_and_energy(monkeypatch):
    project = process_example(True, True)
    next(i for i in project.instances if i.id == 'Cooler-1').parameters['defrost_request'] = 1.
    session = create_session(compile_project(project), .1, .1)
    try:
        session.initialize()
        accepted = deepcopy((session.temperatures, session.process_modes, session.counters))
        def reject(*args): raise DeviceRangeError('TEST_FAILURE', 'injected failed trial')
        monkeypatch.setattr(session, '_solve_at', reject)
        with pytest.raises(SolveFailed): session.advance()
        assert session.time == 0.
        assert (session.temperatures, session.process_modes, session.counters) == accepted
    finally: session.close()


def test_hotgas_temperature_termination_is_located_inside_fixed_step():
    project = process_example(True)
    cooler = next(i for i in project.instances if i.id == 'Cooler-1')
    cooler.parameters.update(defrost_request=1., predrain_duration_s=0., initial_frost_mass_kg=0.,
                             initial_surface_temperature_k=278.14, hot_gas_kv_m3_h=.2,
                             natural_ua_ratio=0., drip_duration_s=1.)
    session = create_session(compile_project(project), .1, .1)
    try:
        session.initialize()
        frame = session.advance()
        mode = session.process_modes['Cooler-1']
        assert mode['mode'] == 3
        assert 0. < mode['since'] < .1
        assert frame.variables['Cooler-1.surface_temperature_k'] == pytest.approx(278.15, abs=1e-7)
        assert frame.metrics['internal_steps'] >= 2
        assert abs(frame.metrics['energy_residual_j']) < .001
    finally: session.close()


def test_frozen_report_keeps_process_values_without_executing_models():
    from fn_engine.refrigeration.report import station_csv, station_report
    project = process_example(True, True)
    session = create_session(compile_project(project), .1, .1)
    try:
        row = session.initialize().model_dump(mode='json')
        record = {'id': 'process-report', 'status': 'completed', 'request': {
            'project': project.model_dump(mode='json'), 'duration_s': .1, 'dt_s': .1}}
        assert 'Cooler-1.state.surface_energy_j [J]' in station_csv([row], session.network)
        report = station_report(record, [row], session.network)
        assert '实际固态霜质量' in report and '全油路质量' in report
    finally: session.close()


def test_arbitrary_instance_names_and_two_oil_systems_have_independent_ledgers():
    from fn_engine.models import ModuleInstance, Connection, Endpoint
    project = process_example(True, True)
    project.instances.append(ModuleInstance(id='Oil2', module_id='compressor_oil_system', name='second separator'))
    edge = next(e for e in project.connections if e.source.instance_id == 'Oil')
    target = edge.target.model_copy(deep=True)
    edge.target = Endpoint(instance_id='Oil2', port_id='in0')
    project.connections.append(Connection(id='second-oil-out', source=Endpoint(instance_id='Oil2', port_id='out0'), target=target))
    mapping = {i.id: f'component_{n}' for n, i in enumerate(project.instances)}
    for i in project.instances: i.id = mapping[i.id]
    for edge in project.connections:
        edge.source.instance_id = mapping[edge.source.instance_id]
        edge.target.instance_id = mapping[edge.target.instance_id]
    for circuit in project.circuit_fluids: circuit.anchor.instance_id = mapping[circuit.anchor.instance_id]
    session = create_session(compile_project(project), .1, .1)
    try:
        frame = session.initialize()
        for oil in ('Oil', 'Oil2'):
            assert frame.variables[mapping[oil] + '.oil_total_mass_kg'] == pytest.approx(60.2)
            assert frame.variables[mapping[oil] + '.oil_mass_residual_kg'] == 0.
        result = session._current()
        rates = result['physical_rates']
        assert session.process_engine.space.mass(rates, 'oil') == pytest.approx(0., abs=1e-14)
        assert session.process_engine.space.mass(rates, 'water') == pytest.approx(
            sum(v for k, v in rates.items() if k.endswith('net_water_import_kg')), abs=1e-14)
    finally: session.close()


def test_process_coordinates_participate_in_adaptive_error_acceptance():
    from fn_engine.models import TimeStepOptions
    project = process_example()
    project.solver.time_step = TimeStepOptions(enabled=True, max_internal_step_s=.01, min_internal_step_s=.0001)
    session = create_session(compile_project(project), .01, .01)
    try:
        session.initialize()
        frame = session.advance()
        assert frame.metrics['timestep_adaptive'] == 1
        assert frame.metrics['local_error_norm_max'] <= 1.
        assert frame.metrics['internal_steps'] >= 1
        assert abs(frame.metrics['energy_residual_j']) < .001
        assert abs(frame.metrics['water_mass_residual_kg']) < 1e-9
    finally: session.close()
