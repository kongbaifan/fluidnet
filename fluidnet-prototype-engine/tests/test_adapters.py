"""Independent arithmetic, unit boundaries and a non-fluid extension prove the generic boundary."""
from copy import deepcopy
import math
import warnings

import pytest
from pydantic import Field

from fn_engine.adapters import AdapterDefinition, AdapterError, AdapterRegistry, UnitRule, default_registry
from fn_engine.adapters.contracts import AdapterModel, AdapterRequest


@pytest.fixture
def registry():
    return default_registry()


def call(registry, adapter, inputs, **extra):
    return registry.execute({'adapter_id': adapter, 'inputs': inputs, **extra})


def test_pipe_units_match_independent_poiseuille(registry):
    # 0.36 kg/h = 0.0001 kg/s, laminar flow; 40 mm internal diameter.
    request = {'adapter_id': 'hydraulics.pipe_pressure_drop', 'request_id': 'business-a-37',
        'inputs': {'mass_flow': .36, 'density': 1., 'viscosity': 1., 'length': 12., 'diameter': 40.},
        'input_units': {'mass_flow': 'kg/h', 'density': 'g/cm3', 'viscosity': 'cP', 'diameter': 'mm'},
        'output_units': {'pressure_drop': 'kPa'}}
    before = deepcopy(request)
    result = registry.execute(request)
    expected_pa = 128*.001*12*(.0001/1000)/(math.pi*.04**4)
    assert result.outputs['pressure_drop'] == pytest.approx(expected_pa/1000, rel=1e-12)
    assert result.output_units == {'pressure_drop': 'kPa'}
    assert result.request_id == 'business-a-37'
    assert request == before


@pytest.mark.parametrize('flow', [-1., 0., 1.])
def test_local_pressure_and_kv_have_same_physical_drop(registry, flow):
    kv = call(registry, 'hydraulics.kv_from_loss_coefficient', {'diameter': .05, 'loss_coefficient': 2.}).outputs['kv']
    local = call(registry, 'hydraulics.local_pressure_drop', {'mass_flow': flow, 'density': 1000., 'diameter': .05, 'loss_coefficient': 2.})
    valve = call(registry, 'hydraulics.valve_pressure_drop', {'mass_flow': flow, 'density': 1000., 'kv': kv, 'opening': 100.},
                 input_units={'opening': '%'})
    velocity = flow/1000/(math.pi*.05**2/4)
    expected = 2*.5*1000*velocity*abs(velocity)
    assert local.outputs['pressure_drop'] == pytest.approx(expected)
    assert valve.outputs['pressure_drop'] == pytest.approx(expected)


def test_volume_flow_conversion_is_separate_from_mass_units(registry):
    mass = call(registry, 'hydraulics.volume_to_mass_flow', {'volume_flow': 60., 'density': 1000.},
                input_units={'volume_flow': 'L/min'}, output_units={'mass_flow': 'kg/h'})
    assert mass.outputs['mass_flow'] == pytest.approx(3600.)
    volume = call(registry, 'hydraulics.mass_to_volume_flow', {'mass_flow': 3600., 'density': 1000.},
                  input_units={'mass_flow': 'kg/h'}, output_units={'volume_flow': 'L/s'})
    assert volume.outputs['volume_flow'] == pytest.approx(1.)


def test_exchanger_equal_capacity_rates(registry):
    result = call(registry, 'thermal.heat_exchanger_effectiveness', {'ua': 2., 'capacity_a': 1., 'capacity_b': 1.},
        input_units={key: 'kW/K' for key in ('ua', 'capacity_a', 'capacity_b')}, output_units={'effectiveness': '%'})
    # Cmin/Cmax=1, epsilon=NTU/(1+NTU)=2/3.
    assert result.outputs['effectiveness'] == pytest.approx(200/3)


@pytest.mark.parametrize('source,value,target,expected', [
    ('degC', 0., 'K', 273.15), ('degF', 32., 'degC', 0.), ('K', 373.15, 'degC', 100.),
])
def test_absolute_temperature_offsets(source, value, target, expected):
    assert UnitRule('temperature', 'K').convert(value, source, target) == pytest.approx(expected)


def test_temperature_differences_have_no_absolute_offset():
    difference = UnitRule('temperature_difference', 'K')
    assert difference.convert(18., 'delta_degF', 'K') == pytest.approx(10.)
    with pytest.raises(ValueError):
        difference.convert(10., 'degC', 'K')


@pytest.mark.parametrize('changes,code', [
    ({'inputs': {'mass_flow': True, 'density': 1000.}}, 'ADAPTER_INPUT_INVALID'),
    ({'inputs': {'mass_flow': '1', 'density': 1000.}}, 'ADAPTER_INPUT_INVALID'),
    ({'inputs': {'mass_flow': math.nan, 'density': 1000.}}, 'ADAPTER_INPUT_INVALID'),
    ({'inputs': {'mass_flow': math.inf, 'density': 1000.}}, 'ADAPTER_INPUT_INVALID'),
    ({'inputs': {'mass_flow': 1., 'density': 0.}}, 'ADAPTER_INPUT_INVALID'),
    ({'inputs': {'mass_flow': 1., 'density': 1000., 'typo': 1.}}, 'ADAPTER_INPUT_INVALID'),
    ({'input_units': {'mass_flow': 'm3/h'}}, 'ADAPTER_UNIT_INVALID'),
    ({'input_units': {'density': 'Pa'}}, 'ADAPTER_UNIT_INVALID'),
    ({'input_units': {'missing': 'm'}}, 'ADAPTER_UNIT_INVALID'),
    ({'output_units': {'volume_flow': 'kg/h'}}, 'ADAPTER_UNIT_INVALID'),
    ({'output_units': {'missing': 'm'}}, 'ADAPTER_UNIT_INVALID'),
    ({'input_units': {'mass_flow': 'kg/h'}, 'inputs': {'mass_flow': True, 'density': 1000.}}, 'ADAPTER_UNIT_INVALID'),
    ({'adapter_id': 'unknown.business'}, 'ADAPTER_NOT_FOUND'),
    ({'version': 99}, 'ADAPTER_NOT_FOUND'),
])
def test_invalid_requests_are_typed_and_correlated(registry, changes, code):
    request = {'adapter_id': 'hydraulics.mass_to_volume_flow', 'request_id': 'job-5',
               'inputs': {'mass_flow': 1., 'density': 1000.}} | changes
    with pytest.raises(AdapterError) as caught:
        registry.execute(request)
    assert caught.value.detail.code == code
    assert caught.value.detail.request_id == 'job-5'


def test_missing_value_cannot_have_units_and_conversion_must_stay_finite(registry):
    for inputs, units in [({'density': 1000.}, {'mass_flow': 'kg/s'}),
                          ({'mass_flow': 1., 'density': 1e308}, {'density': 'g/cm3'})]:
        with pytest.raises(AdapterError, match='单位|数值'):
            call(registry, 'hydraulics.mass_to_volume_flow', inputs, input_units=units)


class ElectricalInput(AdapterModel):
    power: float = Field(ge=0)
    efficiency: float = Field(gt=0, le=1)


class ElectricalOutput(AdapterModel):
    consumed_power: float


def electrical_definition(handler=None, version=1):
    # Third-party business: not coupled to HVAC room or network schemas.
    return AdapterDefinition('electrical.consumption', 'Input power for a requested useful output.',
        ElectricalInput, ElectricalOutput, handler or (lambda p: {'consumed_power': p.power/p.efficiency}),
        version=version, input_units={'power': UnitRule('power', 'W'), 'efficiency': UnitRule('ratio', '1')},
        output_units={'consumed_power': UnitRule('power', 'W')})


def test_custom_business_registration_versions_and_isolation():
    first, second = AdapterRegistry(), AdapterRegistry()
    definition = electrical_definition()
    first.register(definition)
    first.register(electrical_definition(lambda p: {'consumed_power': p.power/p.efficiency+100}, version=2))
    inputs = {'power': 5., 'efficiency': 80.}
    units = {'power': 'kW', 'efficiency': '%'}
    result = call(first, 'electrical.consumption', inputs, input_units=units, output_units={'consumed_power': 'kW'})
    assert result.outputs['consumed_power'] == pytest.approx(6.25)
    assert call(first, 'electrical.consumption', inputs, version=2, input_units=units).outputs['consumed_power'] == pytest.approx(6350.)
    assert not second.catalog().adapters
    with pytest.raises(ValueError, match='already registered'):
        first.register(definition)
    assert [item.version for item in first.catalog().adapters] == [1, 2]
    # Catalog edits cannot mutate a live registration.
    description = first.describe('electrical.consumption')
    description.input_units['power'].accepted_units.append('bad')
    assert 'bad' not in first.describe('electrical.consumption').input_units['power'].accepted_units


def test_validation_precedes_execution_and_result_contract_is_checked():
    called = []
    def handler(p):
        called.append(p)
        return {'consumed_power': float('nan')}
    registry = AdapterRegistry([electrical_definition(handler)])
    with pytest.raises(AdapterError) as caught:
        call(registry, 'electrical.consumption', {'power': 5., 'efficiency': .8}, output_units={'consumed_power': 'Pa'})
    assert caught.value.detail.code == 'ADAPTER_UNIT_INVALID'
    assert not called
    with pytest.raises(AdapterError) as caught:
        call(registry, 'electrical.consumption', {'power': 5., 'efficiency': .8})
    assert caught.value.detail.code == 'ADAPTER_OUTPUT_INVALID'
    assert caught.value.status == 500
    assert len(called) == 1


def test_unexpected_failure_is_not_disguised_as_bad_input():
    def broken(_):
        raise RuntimeError('implementation bug')
    registry = AdapterRegistry([electrical_definition(broken)])
    with pytest.raises(AdapterError) as caught:
        call(registry, 'electrical.consumption', {'power': 5., 'efficiency': .8})
    assert caught.value.status == 500
    assert caught.value.detail.code == 'ADAPTER_INTERNAL_ERROR'


def test_mutated_request_model_is_revalidated(registry):
    request = AdapterRequest(adapter_id='hydraulics.mass_to_volume_flow', inputs={'mass_flow': 1., 'density': 1000.})
    request.version = True
    with pytest.raises(AdapterError):
        registry.execute(request)


@pytest.mark.parametrize('cyclic', [False, True])
def test_mutated_json_is_validated_before_serialization(registry, cyclic):
    request = AdapterRequest(adapter_id='hydraulics.mass_to_volume_flow', request_id='mutated-7')
    request.inputs['mass_flow'] = request.inputs if cyclic else object()
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        with pytest.raises(AdapterError) as caught:
            registry.execute(request)
    assert caught.value.detail.code == 'ADAPTER_INPUT_INVALID'
    assert caught.value.detail.request_id == 'mutated-7'


@pytest.mark.parametrize('body', [None, 'request', [], [('adapter_id', 'hydraulics.mass_to_volume_flow')]])
def test_python_envelope_rejects_non_objects(registry, body):
    with pytest.raises(AdapterError) as caught:
        registry.execute(body)
    assert caught.value.detail.code == 'ADAPTER_INPUT_INVALID'


def test_invalid_correlation_fields_are_not_echoed(registry):
    with pytest.raises(AdapterError) as caught:
        registry.execute({'adapter_id': 'x'*101, 'request_id': 'x'*129, 'version': True})
    assert caught.value.detail.adapter_id is None
    assert caught.value.detail.request_id is None
    assert caught.value.detail.version is None


def test_nested_native_units_are_not_implicitly_converted(registry):
    with pytest.raises(AdapterError) as caught:
        call(registry, 'properties.fluid_state_pt', {'pressure': 200000., 'temperature': 293.15},
             output_units={'state.temperature_k': 'degC'})
    assert caught.value.detail.code == 'ADAPTER_UNIT_INVALID'
    assert caught.value.detail.field == 'output_units.state.temperature_k'


def test_units_must_be_declared_model_fields():
    with pytest.raises(ValueError, match='top-level'):
        AdapterDefinition('custom.invalid', 'Bad unit metadata', ElectricalInput, ElectricalOutput,
            lambda _: {}, input_units={'unknown': UnitRule('power', 'W')})
