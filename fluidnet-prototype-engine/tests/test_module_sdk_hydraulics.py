"""S1 pure-SDK checks: independent physics, units, frozen old values and invalid domains."""
import json
import math
from pathlib import Path

import pytest

from fn_sdk import (
    kv_from_loss_coefficient, mass_flow_to_volume_flow_m3_h, pipe_pressure_drop_pa,
    resistance_pressure_drop_pa, valve_pressure_drop_pa, volume_flow_m3_h_to_mass_flow_kg_s,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / 'tests/fixtures/module-system/hydraulics-v1.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('sample', FROZEN)
def test_shared_values_match_pre_extraction_fixture(sample):
    params, q, rho = sample['params'], sample['flow_kg_s'], sample['density_kg_m3']
    if sample['kind'] == 'pipe':
        actual = pipe_pressure_drop_pa(mass_flow_kg_s=q, density_kg_m3=rho,
                                       viscosity_pa_s=sample['viscosity_pa_s'], **params)
    elif sample['kind'] == 'valve':
        actual = valve_pressure_drop_pa(mass_flow_kg_s=q, density_kg_m3=rho,
            kv_m3_h=params['kv_m3_h'], opening_ratio=params['opening_ratio']) + rho * 9.80665 * params['height_m']
    else:
        actual = resistance_pressure_drop_pa(mass_flow_kg_s=q, density_kg_m3=rho, **params)
    assert actual == pytest.approx(sample['pressure_drop_pa'], rel=2e-14, abs=1e-12)


@pytest.mark.parametrize('flow', [-1.2, 0., 1.2])
@pytest.mark.parametrize('density', [1.2, 1000.])
@pytest.mark.parametrize('coefficient', [.05, .9, 8.])
def test_local_loss_and_exact_kv_match_independent_velocity_and_volume_laws(flow, density, coefficient):
    diameter = .05
    velocity = 4.0 * flow / (density * math.pi * diameter ** 2)
    expected = coefficient * .5 * density * velocity * abs(velocity)
    kv = kv_from_loss_coefficient(diameter_m=diameter, loss_coefficient=coefficient)
    from_kv_definition = 1e5 * density / 1000. * (3600. * abs(flow) / density / kv) ** 2
    from_kv_definition = math.copysign(from_kv_definition, flow)
    assert from_kv_definition == pytest.approx(expected, rel=1e-14, abs=1e-12)
    assert resistance_pressure_drop_pa(mass_flow_kg_s=flow, density_kg_m3=density,
        diameter_m=diameter, loss_coefficient=coefficient) == pytest.approx(expected, rel=1e-14, abs=1e-12)
    assert valve_pressure_drop_pa(mass_flow_kg_s=flow, density_kg_m3=density,
        kv_m3_h=kv) == pytest.approx(expected, rel=1e-14, abs=1e-12)


@pytest.mark.parametrize('flow', [-1e-4, -1e-6, 0., 1e-6, 1e-4])
def test_laminar_pipe_matches_independent_poiseuille_volume_formula(flow):
    density, viscosity, length, diameter = 1000., .001, 10., .01
    expected = 128. * viscosity * length * (flow / density) / (math.pi * diameter ** 4)
    actual = pipe_pressure_drop_pa(mass_flow_kg_s=flow, density_kg_m3=density,
        viscosity_pa_s=viscosity, length_m=length, diameter_m=diameter)
    assert actual == pytest.approx(expected, rel=1e-14, abs=1e-14)


@pytest.mark.parametrize('reynolds', [2300., 4000.])
def test_transition_boundaries_are_continuous_and_signed(reynolds):
    q = reynolds * .001 * math.pi * .05 / 4

    def drop(flow):
        return pipe_pressure_drop_pa(mass_flow_kg_s=flow, density_kg_m3=1000.,
            viscosity_pa_s=.001, length_m=10., diameter_m=.05, roughness_m=4.5e-5)

    center = drop(q)
    assert drop(q * (1 - 1e-9)) == pytest.approx(center, rel=1e-7)
    assert drop(q * (1 + 1e-9)) == pytest.approx(center, rel=1e-7)
    assert drop(-q) == pytest.approx(-center, rel=1e-14)


@pytest.mark.parametrize('flow', [-1.2, 0., 1.2])
@pytest.mark.parametrize('density', [1.2, 1000., 1090.])
def test_signed_mass_volume_conversion_roundtrip(flow, density):
    volume = mass_flow_to_volume_flow_m3_h(mass_flow_kg_s=flow, density_kg_m3=density)
    assert volume == pytest.approx(flow * 3600. / density)
    assert volume_flow_m3_h_to_mass_flow_kg_s(volume_flow_m3_h=volume, density_kg_m3=density) == pytest.approx(flow)


VALID_CALLS = [
    (pipe_pressure_drop_pa, dict(mass_flow_kg_s=.5, density_kg_m3=1000., viscosity_pa_s=.001,
                                length_m=10., diameter_m=.05, roughness_m=0.)),
    (resistance_pressure_drop_pa, dict(mass_flow_kg_s=.5, density_kg_m3=1000., diameter_m=.05, loss_coefficient=8.)),
    (valve_pressure_drop_pa, dict(mass_flow_kg_s=.5, density_kg_m3=1000., kv_m3_h=16., opening_ratio=.8)),
    (kv_from_loss_coefficient, dict(diameter_m=.05, loss_coefficient=8.)),
    (mass_flow_to_volume_flow_m3_h, dict(mass_flow_kg_s=.5, density_kg_m3=1000.)),
    (volume_flow_m3_h_to_mass_flow_kg_s, dict(volume_flow_m3_h=3.6, density_kg_m3=1000.)),
]


@pytest.mark.parametrize('function,kwargs', VALID_CALLS)
@pytest.mark.parametrize('invalid', [float('nan'), float('inf'), -float('inf'), True, 'bad', 10 ** 1000])
def test_each_public_input_rejects_nonfinite_nonnumeric_boolean_and_unrepresentable_values(function, kwargs, invalid):
    for field in kwargs:
        with pytest.raises(ValueError, match=field):
            function(**{**kwargs, field: invalid})


@pytest.mark.parametrize('function,kwargs', VALID_CALLS)
def test_positive_domains_reject_zero_or_negative_values(function, kwargs):
    positive = {'density_kg_m3', 'diameter_m', 'viscosity_pa_s', 'length_m', 'kv_m3_h', 'opening_ratio'}
    if function is kv_from_loss_coefficient:
        positive.add('loss_coefficient')
    for field in positive & kwargs.keys():
        for invalid in (0., -1.):
            with pytest.raises(ValueError, match=field):
                function(**{**kwargs, field: invalid})


def test_no_hidden_clipping_of_loss_roughness_or_valve_opening():
    assert resistance_pressure_drop_pa(mass_flow_kg_s=1., density_kg_m3=1000., diameter_m=.05, loss_coefficient=0.) == 0.
    with pytest.raises(ValueError, match='loss_coefficient'):
        resistance_pressure_drop_pa(mass_flow_kg_s=1., density_kg_m3=1000., diameter_m=.05, loss_coefficient=-1.)
    with pytest.raises(ValueError, match='roughness_m'):
        pipe_pressure_drop_pa(mass_flow_kg_s=1., density_kg_m3=1000., viscosity_pa_s=.001,
                              length_m=10., diameter_m=.05, roughness_m=-1.)
    with pytest.raises(ValueError, match='opening_ratio'):
        valve_pressure_drop_pa(mass_flow_kg_s=0., density_kg_m3=1000., kv_m3_h=16., opening_ratio=0.)
    with pytest.raises(ValueError, match='opening_ratio'):
        valve_pressure_drop_pa(mass_flow_kg_s=1., density_kg_m3=1000., kv_m3_h=16., opening_ratio=1.01)


@pytest.mark.parametrize('function,kwargs', [
    (pipe_pressure_drop_pa, dict(mass_flow_kg_s=1., density_kg_m3=1000., viscosity_pa_s=.001,
                                length_m=10., diameter_m=1e308)),
    (resistance_pressure_drop_pa, dict(mass_flow_kg_s=1e308, density_kg_m3=1000., diameter_m=.05, loss_coefficient=8.)),
    (resistance_pressure_drop_pa, dict(mass_flow_kg_s=1e-300, density_kg_m3=1000., diameter_m=.05, loss_coefficient=8.)),
    (valve_pressure_drop_pa, dict(mass_flow_kg_s=1e-300, density_kg_m3=1000., kv_m3_h=16.)),
    (kv_from_loss_coefficient, dict(diameter_m=1e-200, loss_coefficient=8.)),
    (mass_flow_to_volume_flow_m3_h, dict(mass_flow_kg_s=1e308, density_kg_m3=1e-308)),
    (volume_flow_m3_h_to_mass_flow_kg_s, dict(volume_flow_m3_h=1e308, density_kg_m3=1e308)),
])
def test_arithmetic_overflow_and_underflow_are_errors(function, kwargs):
    with pytest.raises(ValueError):
        function(**kwargs)
