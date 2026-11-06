"""Device-level air-condenser physics, limits and public contract; no station fixture required."""
from copy import deepcopy
import math

from CoolProp.CoolProp import PropsSI
import pytest

from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.refrigeration.air_condenser import DEFAULT_PARAMETERS, OUTPUT_KEYS, condenser_duty, definition
from fn_engine.refrigeration.cycle import DeviceRangeError


class FixedSaturation:
    def __init__(self, temperature=313.15):
        self.temperature = temperature

    def saturation_t(self, pressure):
        assert pressure > 0.
        return self.temperature


def point(**changes):
    return condenser_duty(FixedSaturation(), DEFAULT_PARAMETERS | changes, 1e6)


@pytest.mark.parametrize('fluid', ['R134a', 'Ammonia'])
def test_real_fluid_temperature_and_heat_balance_match_differential_air_balance(fluid):
    service = property_service(FluidConfig(fluid=fluid, phase_policy='any'))
    temperature, ambient = 313.15, 298.15
    pressure = PropsSI('P', 'T', temperature, 'Q', 0., fluid)
    params = DEFAULT_PARAMETERS | {'air_inlet_temperature_k': ambient, 'fan_ratio': .7}
    result = condenser_duty(service, params, pressure)
    # Independent integration of dT_air/d(UA)=(T_sat-T_air)/(m_dot*cp), with RK4.
    capacity = 5. * .7 * 1006.
    outlet, increments = ambient, 1000
    step = 4000. / increments
    derivative = lambda t: (temperature - t) / capacity
    for _ in range(increments):
        k1 = derivative(outlet)
        k2 = derivative(outlet + step*k1/2.)
        k3 = derivative(outlet + step*k2/2.)
        k4 = derivative(outlet + step*k3)
        outlet += step*(k1 + 2.*k2 + 2.*k3 + k4)/6.
    assert result['condensing_temperature_k'] == pytest.approx(temperature, abs=1e-7)
    assert result['air_outlet_temperature_k'] == pytest.approx(outlet, abs=1e-7)
    assert result['heat_rejection_w'] == pytest.approx(capacity*(outlet-ambient), rel=1e-8)
    assert ambient < result['air_outlet_temperature_k'] < temperature
    assert 0. < result['heat_rejection_w'] < capacity*(temperature-ambient)
    assert result['heat_rejection_w'] == pytest.approx(result['effective_ua_w_k']*result['approach_k'])


def test_zero_ua_has_no_refrigerant_heat_but_fan_still_consumes_power():
    result = point(ua_w_k=0., fan_ratio=.5)
    assert result['heat_rejection_w'] == 0.
    assert result['air_outlet_temperature_k'] == 303.15
    assert result['effectiveness'] == 0.
    assert result['fan_power_w'] == 125.


def test_air_capacity_limits_infinite_ua_and_tiny_ntu_remains_nonzero():
    saturated = point(ua_w_k=1e12)
    assert saturated['effectiveness'] == 1.
    assert saturated['air_outlet_temperature_k'] == 313.15
    assert saturated['forced_heat_w'] == 5.*1006.*10.
    tiny = point(ua_w_k=1e-12)
    assert tiny['effectiveness'] > 0.
    assert tiny['effective_ua_w_k'] == pytest.approx(1e-12, rel=1e-12, abs=0.)


@pytest.mark.parametrize('fan', [0., 1e-10, .25, .5, 1.])
def test_fan_affinity_and_separate_natural_path_conserve_each_boundary(fan):
    result = point(fan_ratio=fan, natural_ua_w_k=75.)
    assert result['air_mass_flow_kg_s'] == 5.*fan
    assert result['fan_power_w'] == pytest.approx(1000.*fan**3)
    assert result['natural_heat_w'] == 750.
    assert result['heat_rejection_w'] == pytest.approx(result['forced_heat_w']+750.)
    if fan == 0.:
        assert result['air_outlet_temperature_k'] is None
        assert result['forced_heat_w'] == result['effectiveness'] == result['air_capacity_rate_w_k'] == 0.
    else:
        capacity = result['air_capacity_rate_w_k']
        assert capacity*(result['air_outlet_temperature_k']-303.15) == pytest.approx(result['forced_heat_w'], rel=1e-10)
    if fan <= 1e-10:
        assert result['heat_rejection_w'] == pytest.approx(750., abs=1e-5)


def test_stopped_fan_without_natural_path_is_adiabatic():
    result = point(fan_ratio=0.)
    assert result['heat_rejection_w'] == result['fan_power_w'] == result['effective_ua_w_k'] == 0.
    assert result['air_outlet_temperature_k'] is None


def test_equal_temperatures_and_reverse_heat_keep_sign_and_air_energy():
    equal = point(air_inlet_temperature_k=313.15, natural_ua_w_k=75.)
    assert equal['heat_rejection_w'] == 0.
    assert equal['air_outlet_temperature_k'] == 313.15
    assert equal['reverse_heat_flow'] == 0.
    reverse = point(air_inlet_temperature_k=323.15, natural_ua_w_k=75.)
    assert reverse['heat_rejection_w'] < 0.
    assert reverse['natural_heat_w'] == -750.
    assert reverse['reverse_heat_flow'] == 1.
    assert 313.15 < reverse['air_outlet_temperature_k'] < 323.15
    assert reverse['air_capacity_rate_w_k']*(reverse['air_outlet_temperature_k']-323.15) == pytest.approx(reverse['forced_heat_w'])


@pytest.mark.parametrize('key,value', [
    ('ua_w_k', -1.), ('natural_ua_w_k', -1.), ('fan_power_w', -1.),
    ('rated_air_mass_flow_kg_s', 0.), ('air_specific_heat_j_kg_k', 0.),
    ('air_inlet_temperature_k', 0.), ('fan_ratio', -1.), ('fan_ratio', 1.01),
    ('ua_w_k', float('nan')), ('fan_ratio', float('inf')), ('air_specific_heat_j_kg_k', 'bad'),
])
def test_invalid_device_inputs_have_parameter_diagnostics(key, value):
    with pytest.raises(DeviceRangeError) as error:
        point(**{key: value})
    assert error.value.code == 'AIR_CONDENSER_PARAMETER'
    assert error.value.field == key


@pytest.mark.parametrize('pressure', [0., -1., float('nan'), float('inf')])
def test_invalid_pressure_is_rejected_before_property_query(pressure):
    with pytest.raises(DeviceRangeError) as error:
        condenser_duty(FixedSaturation(), DEFAULT_PARAMETERS, pressure)
    assert error.value.code == 'AIR_CONDENSER_PRESSURE'


def test_trial_evaluations_are_pure_and_do_not_accumulate_energy():
    params = deepcopy(DEFAULT_PARAMETERS)
    before = deepcopy(params)
    first = condenser_duty(FixedSaturation(), params, 1e6)
    for _ in range(3):
        assert condenser_duty(FixedSaturation(), params, 1e6) == first
    assert params == before
    assert not any(key.startswith('state.') for key in first)


def test_catalog_factory_matches_defaults_units_and_boundary_contract():
    module = definition()
    assert module.id == module.solver_model == 'air_cooled_condenser'
    assert [(p.id,p.domain.value,p.direction.value) for p in module.ports] == [
        ('in0','refrigerant','in'), ('out0','refrigerant','out')]
    assert not module.channels
    assert {p.id:p.default for p in module.parameters} == DEFAULT_PARAMETERS
    assert {p.id for p in module.parameters if p.runtime} == {'air_inlet_temperature_k','fan_ratio'}
    params = {p.id:p for p in module.parameters}
    assert params['ua_w_k'].unit.from_canonical(4000.) == 4.
    assert params['air_specific_heat_j_kg_k'].unit.from_canonical(1006.) == 1.006
    assert params['air_inlet_temperature_k'].unit.from_canonical(303.15) == pytest.approx(30.)
    assert params['fan_ratio'].unit.from_canonical(.5) == 50.
    output_keys = {v.id for v in module.variables if v.source == 'derived'}
    assert output_keys == set(point())
    assert tuple(point()) == OUTPUT_KEYS
    assert {v.id for v in module.variables if v.source == 'state'} == {'state.heat_rejected_j','state.fan_energy_j'}
    assert all(value is None or math.isfinite(value) for value in point().values())
