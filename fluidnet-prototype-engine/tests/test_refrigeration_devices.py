"""Case-B station devices checked one by one against CoolProp PropsSI, not against the device code."""
import math

from CoolProp.CoolProp import PropsSI
from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map, refrigeration_catalog
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Domain, Endpoint, FluidConfig, ModuleInstance, Project
from fn_engine.properties import property_service
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.devices import DeviceRangeError

NH3 = property_service(FluidConfig(fluid='Ammonia', phase_policy='any'))
CO2 = property_service(FluidConfig(fluid='CarbonDioxide', phase_policy='any'))
CATALOG = {m.id: m for m in refrigeration_catalog()}


def defaults(kind, **overrides):
    return {p.id: p.default for p in CATALOG[kind].parameters} | overrides


def psat(fluid, t):
    return PropsSI('P', 'T', t, 'Q', 0, fluid)


def test_catalog_registers_every_station_device_with_canonical_contracts():
    assert set(CATALOG) == {'hp_receiver', 'lp_drum', 'pumped_drum', 'refrigerant_compressor', 'evaporative_condenser',
                            'expansion_valve', 'cascade_exchanger', 'refrigerant_pump', 'air_cooler', 'refrigerant_header'}
    assert CATALOG.keys() <= catalog_map().keys()
    for definition in CATALOG.values():
        assert definition.category == '制冷站设备' and definition.runtime == 'builtin'
        assert all(p.domain in (Domain.refrigerant, Domain.thermal) for p in definition.ports)
        assert {v.id for v in definition.variables} >= {'param.' + p.id for p in definition.parameters}
    # The coil cools a room through the same thermal port contract the A1 room expects.
    heat = next(p for p in CATALOG['air_cooler'].ports if p.id == 'heat')
    room = catalog_map()['cold_room'].ports[0]
    assert (heat.domain, heat.direction.value, room.direction.value) == (Domain.thermal, 'out', 'in')
    # Only the two NH3/CO2 sides of the cascade exchanger belong to different circuits.
    assert {p.circuit for p in CATALOG['cascade_exchanger'].ports} == {'evaporating', 'condensing'}
    runtime = {k: {p.id for p in d.parameters if p.runtime} for k, d in CATALOG.items()}
    assert runtime['refrigerant_compressor'] == {'running', 'load_ratio'}
    assert runtime['expansion_valve'] == {'opening_ratio'}
    assert runtime['evaporative_condenser'] == {'fan_ratio', 'wet_bulb_temperature_k', 'return_gas_ratio'}
    assert runtime['refrigerant_pump'] == {'running', 'speed_ratio'}
    assert runtime['air_cooler'] == {'running', 'fan_ratio', 'supply_valve_ratio'}
    displacement = next(p for p in CATALOG['refrigerant_compressor'].parameters if p.id == 'displacement_m3_s')
    assert displacement.unit.from_canonical(displacement.default) == pytest.approx(290.)


@pytest.mark.parametrize('kind,service,fluid', [('hp_receiver', NH3, 'Ammonia'), ('lp_drum', NH3, 'Ammonia'),
                                                ('pumped_drum', CO2, 'CarbonDioxide')])
@pytest.mark.parametrize('level', [.06, .4, .62, .94])
def test_vessel_inverts_stored_mass_and_energy_to_saturation_pressure_and_level(kind, service, fluid, level):
    params = defaults(kind, level_ratio=level)
    t = params['temperature_k']
    rho_l, rho_v = PropsSI('D', 'T', t, 'Q', 0, fluid), PropsSI('D', 'T', t, 'Q', 1, fluid)
    u_l, u_v = PropsSI('U', 'T', t, 'Q', 0, fluid), PropsSI('U', 'T', t, 'Q', 1, fluid)
    volume = params['volume_m3']
    mass = volume * (level * rho_l + (1 - level) * rho_v)
    energy = volume * (level * rho_l * u_l + (1 - level) * rho_v * u_v)
    assert devices.vessel_initial(service, params) == pytest.approx((mass, energy), rel=1e-12)
    state = devices.vessel_state(service, params, mass, energy)
    assert state.temperature_k == pytest.approx(t, abs=1e-6)
    assert state.pressure_pa == pytest.approx(psat(fluid, t), rel=1e-6)
    assert state.level_ratio == pytest.approx(level, abs=1e-7)
    assert state.level_m == pytest.approx(level * params['height_m'], abs=1e-6)
    assert state.liquid_mass_kg + state.vapor_mass_kg == pytest.approx(mass, rel=1e-12)
    assert state.liquid_enthalpy_j_kg == pytest.approx(PropsSI('H', 'T', t, 'Q', 0, fluid), rel=1e-6)
    assert state.vapor_enthalpy_j_kg == pytest.approx(PropsSI('H', 'T', t, 'Q', 1, fluid), rel=1e-6)
    variables = state.variables('R1')
    assert variables['R1.state.pressure_pa'] == state.pressure_pa and variables['R1.liquid_enthalpy_j_kg'] == state.liquid_enthalpy_j_kg


def test_drawing_liquid_from_a_receiver_lowers_level_and_flashes_to_lower_pressure():
    params = defaults('hp_receiver')
    mass, energy = devices.vessel_initial(NH3, params)
    before = devices.vessel_state(NH3, params, mass, energy)
    drawn = 50.
    # Open-system balance of a fixed volume: outflow carries h_l = u_l + p·v_l, so the rest flashes and cools.
    after = devices.vessel_state(NH3, params, mass - drawn, energy - drawn * before.liquid_enthalpy_j_kg)
    assert after.level_ratio < before.level_ratio
    assert after.pressure_pa < before.pressure_pa
    assert after.vapor_mass_kg > before.vapor_mass_kg


@pytest.mark.parametrize('mutation', ['subcooled_full', 'superheated', 'empty'])
def test_vessel_reports_states_outside_the_two_phase_model(mutation):
    params = defaults('lp_drum')
    t, volume = params['temperature_k'], params['volume_m3']
    # Compressed liquid filling the whole volume, and a low-density superheated vapor.
    rho, u = {'subcooled_full': (PropsSI('D', 'T', t - 5, 'P', 2e6, 'Ammonia'), PropsSI('U', 'T', t - 5, 'P', 2e6, 'Ammonia')),
              'superheated': (PropsSI('D', 'T', t + 40, 'P', 50000, 'Ammonia'), PropsSI('U', 'T', t + 40, 'P', 50000, 'Ammonia')),
              'empty': (0., 0.)}[mutation]
    mass, energy = volume * rho, volume * rho * u
    with pytest.raises(DeviceRangeError) as error:
        devices.vessel_state(NH3, params, mass, energy)
    assert error.value.code == 'VESSEL_PHASE_RANGE'


def test_vessel_level_band_stops_instead_of_clamping():
    params = defaults('hp_receiver', level_ratio=.97)
    state = devices.vessel_state(NH3, params, *devices.vessel_initial(NH3, params))
    with pytest.raises(DeviceRangeError) as error:
        devices.check_vessel(params, state)
    assert error.value.code == 'VESSEL_LEVEL_RANGE'
    devices.check_vessel(defaults('hp_receiver'), devices.vessel_state(NH3, defaults('hp_receiver'),
                                                                       *devices.vessel_initial(NH3, defaults('hp_receiver'))))


def test_compressor_matches_independent_isentropic_cycle_and_scales_with_load():
    params = defaults('refrigerant_compressor')
    ps, pd = psat('Ammonia', 243.15), psat('Ammonia', 308.15)
    rho, h1, s1 = (PropsSI(k, 'P', ps, 'Q', 1, 'Ammonia') for k in 'DHS')
    h2 = h1 + (PropsSI('H', 'P', pd, 'S', s1, 'Ammonia') - h1) / params['isentropic_efficiency']
    mass = params['displacement_m3_s'] * params['volumetric_efficiency'] * rho
    point = devices.compressor_point(NH3, params, ps, pd)
    assert point['mass_flow_kg_s'] == pytest.approx(mass, rel=1e-9)
    assert point['shaft_power_w'] == pytest.approx(mass * (h2 - h1), rel=1e-6)
    assert point['electric_power_w'] == pytest.approx(mass * (h2 - h1) / params['motor_efficiency'], rel=1e-6)
    assert point['discharge_temperature_k'] == pytest.approx(PropsSI('T', 'P', pd, 'H', h2, 'Ammonia'), rel=1e-6)
    assert point['pressure_ratio'] == pytest.approx(pd / ps) and not point['diagnostics']
    half = devices.compressor_point(NH3, params | {'load_ratio': .5}, ps, pd)
    assert half['mass_flow_kg_s'] == pytest.approx(mass / 2, rel=1e-12)
    assert half['shaft_power_w'] == pytest.approx(point['shaft_power_w'] / 2, rel=1e-9)
    for stopped in (params | {'running': 0.}, params | {'load_ratio': 0.}):
        idle = devices.compressor_point(NH3, stopped, ps, pd)
        assert (idle['mass_flow_kg_s'], idle['electric_power_w'], idle['discharge_temperature_k']) == (0., 0., None)


def test_compressor_flags_envelope_and_refuses_reverse_pressure():
    params = defaults('refrigerant_compressor')
    ps, pd = psat('Ammonia', 233.15), psat('Ammonia', 313.15)
    assert [d.code for d in devices.compressor_point(NH3, params, ps, pd)['diagnostics']] == ['COMPRESSOR_ENVELOPE']
    with pytest.raises(DeviceRangeError) as error:
        devices.compressor_point(NH3, params, pd, ps)
    assert error.value.code == 'COMPRESSOR_PRESSURE_RATIO'
    assert devices.compressor_point(NH3, params | {'running': 0.}, pd, ps)['mass_flow_kg_s'] == 0.


def test_condenser_rejects_ua_times_wet_bulb_difference_and_keeps_the_sign():
    params = defaults('evaporative_condenser')
    p = psat('Ammonia', 308.15)
    full = devices.condenser_duty(NH3, params, p)
    assert full['condensing_temperature_k'] == pytest.approx(308.15, abs=1e-6)
    assert full['heat_rejection_w'] == pytest.approx(params['ua_w_k'] * (308.15 - params['wet_bulb_temperature_k']), rel=1e-6)
    assert full['fan_power_w'] == params['fan_power_w']
    off = devices.condenser_duty(NH3, params | {'fan_ratio': 0.}, p)
    assert off['effective_ua_w_k'] == pytest.approx(params['ua_w_k'] * params['natural_ua_ratio']) and off['fan_power_w'] == 0.
    flooded = devices.condenser_duty(NH3, params | {'return_gas_ratio': 0.}, p)
    assert flooded['effective_ua_w_k'] == pytest.approx(params['ua_w_k'] * params['flooded_ua_ratio'])
    assert off['heat_rejection_w'] < flooded['heat_rejection_w'] < full['heat_rejection_w']
    cold = devices.condenser_duty(NH3, params | {'wet_bulb_temperature_k': 310.15}, p)
    assert cold['heat_rejection_w'] < 0


def test_expansion_valve_uses_the_kv_definition_of_the_water_valve():
    params = defaults('expansion_valve', kv_m3_h=1.2, opening_ratio=.4)
    pin, pout = psat('Ammonia', 308.15), psat('Ammonia', 243.15)
    rho, h = PropsSI('D', 'P', pin, 'Q', 0, 'Ammonia'), PropsSI('H', 'P', pin, 'Q', 0, 'Ammonia')
    flow = devices.valve_flow(NH3, params, pin, pout)
    # Inverse check with the hydraulic valve relation: Δp = 1e5·(ρ/1000)·Q|Q|/Kv² (solver.branch_drop).
    volume = flow['mass_flow_kg_s'] / rho * 3600
    assert 100000 * (rho / 1000) * volume ** 2 / (1.2 * .4) ** 2 == pytest.approx(pin - pout, rel=1e-9)
    assert flow['outlet_quality'] == pytest.approx(PropsSI('Q', 'P', pout, 'H', h, 'Ammonia'), rel=1e-6)
    assert devices.valve_flow(NH3, params, pout, pin)['mass_flow_kg_s'] == 0.
    assert devices.valve_flow(NH3, params | {'opening_ratio': 0.}, pin, pout)['mass_flow_kg_s'] == 0.


def test_cascade_exchanger_balances_latent_heat_on_both_circuits():
    params = defaults('cascade_exchanger')
    pe, pc = psat('Ammonia', 243.15), psat('CarbonDioxide', 247.15)
    duty = devices.cascade_duty(NH3, CO2, params, pe, pc)
    assert duty['heat_w'] == pytest.approx(params['ua_w_k'] * 4., rel=1e-6)
    latent_nh3 = PropsSI('H', 'P', pe, 'Q', 1, 'Ammonia') - PropsSI('H', 'P', pe, 'Q', 0, 'Ammonia')
    latent_co2 = PropsSI('H', 'P', pc, 'Q', 1, 'CarbonDioxide') - PropsSI('H', 'P', pc, 'Q', 0, 'CarbonDioxide')
    assert duty['evaporated_kg_s'] * latent_nh3 == pytest.approx(duty['heat_w'], rel=1e-6)
    assert duty['condensed_kg_s'] * latent_co2 == pytest.approx(duty['heat_w'], rel=1e-6)
    reverse = devices.cascade_duty(NH3, CO2, params, psat('Ammonia', 250.15), pc)
    assert reverse['heat_w'] < 0 and reverse['condensed_kg_s'] < 0


def test_pump_follows_affinity_laws_and_heats_the_liquid():
    params = defaults('refrigerant_pump')
    p = psat('CarbonDioxide', 247.15)
    rho = PropsSI('D', 'P', p, 'Q', 0, 'CarbonDioxide')
    rated = devices.pump_point(CO2, params, p)
    assert rated['electric_power_w'] == pytest.approx(2. * 200000. / rho / params['efficiency_ratio'], rel=1e-6)
    slow = devices.pump_point(CO2, params | {'speed_ratio': .5}, p)
    assert (slow['mass_flow_kg_s'], slow['pressure_rise_pa']) == pytest.approx((1., 50000.))
    assert slow['electric_power_w'] == pytest.approx(rated['electric_power_w'] / 8, rel=1e-9)
    assert slow['heat_to_fluid_w'] == slow['electric_power_w']
    assert devices.pump_point(CO2, params | {'running': 0.}, p)['mass_flow_kg_s'] == 0.


def test_supply_split_follows_valve_openings():
    assert devices.split_supply(2., {'C1': 1., 'C2': .25}) == pytest.approx({'C1': 1.6, 'C2': .4})
    assert devices.split_supply(2., {'C1': 0., 'C2': 0.}) == {'C1': 0., 'C2': 0.}


def test_air_cooler_is_air_side_or_supply_limited_and_keeps_fan_heat_in_the_room():
    params = defaults('air_cooler')
    p = psat('CarbonDioxide', 247.15)
    h_l, h_v = PropsSI('H', 'P', p, 'Q', 0, 'CarbonDioxide'), PropsSI('H', 'P', p, 'Q', 1, 'CarbonDioxide')
    air = devices.air_cooler_point(CO2, params, p, 255.15, 1.)
    assert not air['supply_limited']
    assert air['refrigerant_heat_w'] == pytest.approx(params['ua_w_k'] * 8., rel=1e-6)
    assert air['room_cooling_w'] == pytest.approx(air['refrigerant_heat_w'] - params['fan_power_w'])
    assert air['outlet_enthalpy_j_kg'] == pytest.approx(h_l + air['refrigerant_heat_w'], rel=1e-9)
    assert air['outlet_quality'] == pytest.approx(air['refrigerant_heat_w'] / (h_v - h_l), rel=1e-6)
    starved = devices.air_cooler_point(CO2, params, p, 255.15, .1)
    assert starved['supply_limited']
    assert starved['refrigerant_heat_w'] == pytest.approx(.1 * (h_v - h_l) * params['max_outlet_quality'], rel=1e-6)
    assert starved['outlet_quality'] == pytest.approx(params['max_outlet_quality'], rel=1e-9)
    idle = devices.air_cooler_point(CO2, params | {'running': 0.}, p, 255.15, 1.)
    assert idle['fan_power_w'] == 0.
    assert idle['refrigerant_heat_w'] == pytest.approx(params['ua_w_k'] * params['natural_ua_ratio'] * 8., rel=1e-6)
    cold_room = devices.air_cooler_point(CO2, params, p, 240.15, 1.)
    assert cold_room['refrigerant_heat_w'] == 0. and cold_room['room_cooling_w'] == -params['fan_power_w']
    assert devices.air_cooler_point(CO2, params, p, 255.15, 0.)['outlet_quality'] is None


def station_fragment():
    modules = list(CATALOG.values()) + [catalog_map()['cold_room']]
    return Project(id='station-devices', name='设备片段', modules=modules, instances=[
        ModuleInstance(id='C1', module_id='air_cooler', name='冷风机'),
        ModuleInstance(id='ROOM1', module_id='cold_room', name='库房')],
        connections=[Connection(id='h1', source=Endpoint(instance_id='C1', port_id='heat'),
                                target=Endpoint(instance_id='ROOM1', port_id='heat'))])


def test_station_projects_report_pending_instead_of_falling_into_the_a1_heat_branch():
    with pytest.raises(CompilationError) as error:
        compile_project(station_fragment())
    assert error.value.diagnostic.code == 'REFRIGERATION_STATION_PENDING'


def test_prototype_export_keeps_optional_vessel_ports_and_canonical_parameters():
    receiver = CATALOG['hp_receiver']
    raw = {'format': 'fluidnet-studio-prototype', 'schema': 1, 'activeProject': 'p1',
           'modules': [{'id': 'hp_receiver', 'kind': 'hp_receiver', 'runtime': 'builtin', 'name': receiver.name, 'version': 1,
                        # The browser keeps no `required` flag; the registered port decides.
                        'ports': [{'id': p.id, 'label': p.label, 'direction': p.direction.value, 'domain': p.domain.value}
                                  for p in receiver.ports], 'channels': []}],
           'projects': [{'id': 'p1', 'name': 'p', 'pages': [{'id': 'main', 'nodes': [
               {'id': 'R1', 'moduleId': 'hp_receiver', 'params': {'temperature_k': 30., 'volume_m3': 2.5}}], 'edges': []}]}]}
    project = normalize_prototype_export(raw)
    ports = {p.id: (p.required, p.circuit) for p in project.modules[0].ports}
    assert ports == {'in0': (True, 'refrigerant'), 'in1': (False, 'refrigerant'),
                     'vapor': (False, 'refrigerant'), 'liquid': (True, 'refrigerant')}
    assert project.instances[0].parameters == {'temperature_k': pytest.approx(303.15), 'volume_m3': 2.5}
    assert project.import_diagnostics[-1].code == 'THERMAL_SCOPE'


def test_catalog_endpoint_lists_station_devices():
    modules = {m['id']: m for m in TestClient(create_app()).get('/api/v1/catalog').json()['modules']}
    assert modules['refrigerant_compressor']['ports'][0]['domain'] == 'refrigerant'
    assert math.isclose(modules['hp_receiver']['parameters'][0]['default'], 3.)
