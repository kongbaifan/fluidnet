"""Fixed-composition REFPROP mixtures in the refrigeration station and its two-phase graph network.

The composition is the same everywhere (no fractionation); skipped without a licensed REFPROP."""
import CoolProp.CoolProp as CP
import pytest

from fn_engine import properties
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service, refprop_root
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.dx_example import dx_example
from fn_engine.refrigeration.network import mixture
from fn_engine.refrigeration.network_examples import network_example
from fn_engine.refrigeration.stream_devices import single_phase
from fn_engine.sessions import create_session

pytestmark = pytest.mark.skipif(refprop_root() is None, reason='REFPROP 未安装')
R407C = 'REFPROP::R407C.MIX'


def service(fluid=R407C):
    return property_service(FluidConfig(fluid=fluid, phase_policy='any'))


def test_quality_is_the_vapor_mass_fraction():
    r407c = service()
    state = r407c.state_pq(2e5, .3)
    assert state.quality == .3
    assert r407c.state_ph(2e5, state.enthalpy_j_kg).quality == pytest.approx(.3, abs=1e-5)
    assert r407c.state_du(state.density_kg_m3, state.internal_energy_j_kg).quality == pytest.approx(.3, abs=1e-4)
    # REFPROP 9.1 two-phase flashes of a mixture close to about 1e-5, not to machine precision.
    assert r407c.state_tq(state.temperature_k, .3).pressure_pa == pytest.approx(2e5, rel=1e-5)
    # Independent lever rule on specific volume with the equilibrium phase densities of the same flash.
    with properties._lock(r407c.key):
        flash = properties._abstract_state(r407c.key)
        flash.update(CP.PT_INPUTS, 2e5, state.temperature_k)
        liquid, vapor = (flash.saturated_liquid_keyed_output(CP.iDmass), flash.saturated_vapor_keyed_output(CP.iDmass))
        molar = flash.Q()
    lever = (1. / state.density_kg_m3 - 1. / liquid) / (1. / vapor - 1. / liquid)
    assert lever == pytest.approx(.3, abs=1e-5)
    assert molar > .3 + .01   # the vapor is lighter than the overall mixture, so the molar fraction is larger


def test_vessel_ports_deliver_bubble_liquid_and_dew_vapor():
    r407c = service()
    params = {'volume_m3': .5, 'height_m': 1., 'temperature_k': 248.15, 'level_ratio': .4}
    state = devices.vessel_state(r407c, params, *devices.vessel_initial(r407c, params))
    assert state.level_ratio == pytest.approx(.4, abs=1e-4)
    assert state.temperature_k == pytest.approx(248.15, abs=1e-3)
    bubble, dew = r407c.state_pq(state.pressure_pa, 0.), r407c.state_pq(state.pressure_pa, 1.)
    assert bubble.temperature_k < state.temperature_k < dew.temperature_k
    assert state.liquid_enthalpy_j_kg == bubble.enthalpy_j_kg and state.vapor_enthalpy_j_kg == dew.enthalpy_j_kg
    # The liquid port feeds a pump or a liquid valve: it must be liquid at the vessel pressure.
    assert single_phase(r407c, state.pressure_pa, state.liquid_enthalpy_j_kg)[1] == 'liquid'
    assert single_phase(r407c, state.pressure_pa, state.vapor_enthalpy_j_kg)[1] == 'gas'


def test_glide_lowers_coil_duty_and_condensing_temperature_is_the_mean():
    r407c = service()
    pressure = 2.3e5
    params = {'ua_w_k': 800., 'natural_ua_ratio': .1, 'fan_ratio': 1., 'fan_power_w': 300., 'max_outlet_quality': .8}
    bubble, limit = r407c.state_pq(pressure, 0.), r407c.state_pq(pressure, .8)
    point = devices.air_cooler_point(r407c, params, pressure, 258.15, .05)
    assert not point['supply_limited']
    outlet = r407c.state_ph(pressure, point['outlet_enthalpy_j_kg'])
    assert point['outlet_quality'] == pytest.approx(outlet.quality)
    # Air-side duty against the mean of the refrigerant inlet and (linear-glide) outlet temperature.
    slope = (limit.temperature_k - bubble.temperature_k) / (limit.enthalpy_j_kg - bubble.enthalpy_j_kg)
    leaving = bubble.temperature_k + slope * point['refrigerant_heat_w'] / .05
    assert point['refrigerant_heat_w'] == pytest.approx(800. * (258.15 - .5 * (bubble.temperature_k + leaving)), rel=1e-12)
    assert point['refrigerant_heat_w'] < 800. * (258.15 - bubble.temperature_k)
    starved = devices.air_cooler_point(r407c, params, pressure, 258.15, .005)
    assert starved['supply_limited'] and starved['outlet_quality'] == .8
    assert starved['outlet_enthalpy_j_kg'] == pytest.approx(limit.enthalpy_j_kg)
    condenser = {'ua_w_k': 1000., 'natural_ua_ratio': 0., 'fan_ratio': 1., 'flooded_ua_ratio': 0., 'return_gas_ratio': 1.,
                 'wet_bulb_temperature_k': 298.15, 'fan_power_w': 0.}
    duty = devices.condenser_duty(r407c, condenser, 1.5e6)
    mean = .5 * (r407c.state_pq(1.5e6, 0.).temperature_k + r407c.state_pq(1.5e6, 1.).temperature_k)
    assert duty['condensing_temperature_k'] == pytest.approx(mean)


def test_two_phase_density_is_the_equilibrium_flash_density():
    r407c = service()
    state = r407c.state_pq(2e5, .15)
    _, density, viscosity = mixture(r407c, 2e5, state.enthalpy_j_kg)
    assert density == pytest.approx(state.density_kg_m3, rel=1e-4)
    assert r407c.state_pq(2e5, 1.).viscosity_pa_s < viscosity < r407c.state_pq(2e5, 0.).viscosity_pa_s


def test_mixture_runs_through_the_two_phase_network_and_conserves():
    project = network_example()
    project.fluid.fluid = R407C
    session = create_session(compile_project(project), .1, .1)
    try:
        frame = session.initialize()
        v = frame.variables
        assert v['Pump.mass_flow_kg_s'] == pytest.approx(v['Cooler-1.mass_flow_kg_s'] + v['Cooler-2.mass_flow_kg_s'], abs=1e-9)
        assert v['Cooler-1.mass_flow_kg_s'] > v['Cooler-2.mass_flow_kg_s'] > 0.
        for pipe in ('ReturnPipe-1', 'ReturnPipe-2'):
            assert 0. < v[pipe + '.outlet_quality'] < 1.
            assert v[pipe + '.pressure_drop_pa'] > 0.
        # Wet return: the refrigerant warms along its glide instead of staying at one saturation temperature.
        assert v['Cooler-1.outlet_temperature_k'] > v['Cooler-1.inlet_temperature_k'] + .3
        frame = session.advance()
        assert abs(frame.metrics['energy_residual_j']) < .05
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert frame.metrics['network_pressure_residual_pa'] < project.solver.pressure_tolerance_pa
    finally:
        session.close()


def test_devices_not_checked_for_glide_are_rejected_on_a_mixture_circuit():
    project = dx_example()
    project.fluid.fluid = R407C
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'MIXTURE_DEVICE_UNSUPPORTED'
