import math
import threading

import pytest
from CoolProp.CoolProp import PropsSI

from fn_engine.models import FluidConfig
from fn_engine.properties import PropertyError, property_service


def water(policy='single_phase'):
    return property_service(FluidConfig(fluid='Water', phase_policy=policy))


def two_phase_enthalpy(pressure=300000., quality=.5):
    return PropsSI('Hmass', 'P', pressure, 'Q', quality, 'Water')


def test_liquid_pt_ph_roundtrip():
    service = water('liquid')
    forward = service.state_pt(300000, 293.15)
    assert forward.phase == 'liquid'
    assert forward.enthalpy_j_kg == pytest.approx(PropsSI('Hmass', 'P', 300000, 'T', 293.15, 'Water'), rel=1e-12)
    assert forward.density_kg_m3 == pytest.approx(998.298, rel=1e-5)
    assert forward.viscosity_pa_s > 0 and forward.specific_heat_j_kg_k > 4000 and forward.thermal_conductivity_w_m_k > 0
    back = service.state_ph(300000, forward.enthalpy_j_kg)
    assert back.temperature_k == pytest.approx(293.15, abs=1e-9)
    assert back.density_kg_m3 == pytest.approx(forward.density_kg_m3, rel=1e-12)
    assert back.viscosity_pa_s == pytest.approx(forward.viscosity_pa_s, rel=1e-12)


def test_single_phase_quality_is_none():
    assert water().state_pt(300000, 293.15).quality is None
    assert water().state_ph(300000, 84194.25).quality is None


def test_two_phase_ph_returns_quality_without_transport_properties():
    state = water('any').state_ph(300000, two_phase_enthalpy())
    assert state.phase == 'twophase'
    assert state.quality == pytest.approx(.5, abs=1e-9)
    assert state.temperature_k == pytest.approx(PropsSI('T', 'P', 300000, 'Q', 0, 'Water'), rel=1e-9)
    assert state.viscosity_pa_s is None
    assert state.thermal_conductivity_w_m_k is None
    assert state.density_kg_m3 > 0


@pytest.mark.parametrize('policy', ['liquid', 'gas', 'single_phase'])
def test_two_phase_rejected_unless_policy_is_any(policy):
    with pytest.raises(PropertyError) as error:
        water(policy).state_ph(300000, two_phase_enthalpy())
    assert error.value.code == 'PHASE_UNSUPPORTED'


def test_phase_policy_rejects_wrong_single_phase():
    with pytest.raises(PropertyError) as error:
        water('liquid').state_pt(250000, 500)
    assert error.value.code == 'PHASE_UNSUPPORTED'
    with pytest.raises(PropertyError) as error:
        water('gas').state_pt(250000, 293.15)
    assert error.value.code == 'PHASE_UNSUPPORTED'
    assert 'gas' in water('any').state_pt(250000, 500).phase


def test_air_gas_state():
    state = property_service(FluidConfig(fluid='Air', phase_policy='gas')).state_pt(200000, 293.15)
    assert 'gas' in state.phase
    # Air at 2 bar / 20 °C is close to ideal: rho = p / (R T), R = 287.05 J/(kg K).
    assert state.density_kg_m3 == pytest.approx(200000 / (287.05 * 293.15), rel=2e-3)
    assert state.viscosity_pa_s == pytest.approx(1.8e-5, rel=.05)


@pytest.mark.parametrize('args', [(math.nan, 293.15), (300000, math.inf), (0, 293.15), (-1, 293.15), (300000, 0), (300000, -5)])
def test_invalid_pt_inputs_raise_property_range(args):
    with pytest.raises(PropertyError) as error:
        water().state_pt(*args)
    assert error.value.code == 'PROPERTY_RANGE'


@pytest.mark.parametrize('args', [(math.nan, 84000.), (300000, math.nan), (0, 84000.), (-1, 84000.)])
def test_invalid_ph_inputs_raise_property_range(args):
    with pytest.raises(PropertyError) as error:
        water().state_ph(*args)
    assert error.value.code == 'PROPERTY_RANGE'


def test_unsupported_configurations_keep_their_codes():
    with pytest.raises(PropertyError) as error:
        property_service(FluidConfig(fluid='Water', composition={'Water': 1.0}))
    assert error.value.code == 'COMPOSITION_UNSUPPORTED'
    with pytest.raises(PropertyError) as error:
        property_service(FluidConfig.model_construct(backend='refprop', fluid='Water', composition={}, phase_policy='single_phase'))
    assert error.value.code == 'PROPERTY_BACKEND_UNSUPPORTED'
    with pytest.raises(PropertyError) as error:
        property_service(FluidConfig(fluid='NotAFluid')).state_pt(300000, 293.15)
    assert error.value.code == 'PROPERTY_FAILURE'
    assert water().backend == 'coolprop'


def test_service_is_shared_and_results_are_isolated():
    assert water('liquid') is water('liquid')
    assert water('liquid') is not water('gas')
    first = water().state_pt(300000, 293.15)
    first.composition['Water'] = 0.0
    first.density_kg_m3 = -1.0
    second = water().state_pt(300000, 293.15)
    assert second.composition == {'Water': 1.0}
    assert second.density_kg_m3 > 900


def test_concurrent_queries_match_single_thread():
    service = water('liquid')
    # Distinct, never-cached inputs per thread so the flash cache cannot hide a shared
    # AbstractState; the reference comes straight from PropsSI, not from the service.
    inputs = {name: [(200000 + 37 * i + offset, 280 + (i % 60) + offset * 1e-3) for i in range(400)]
              for name, offset in (('a', 1), ('b', 2))}
    expected = {name: [tuple(PropsSI(key, 'P', p, 'T', t, 'Water') for key in ('Hmass', 'Dmass', 'VISCOSITY')) for p, t in xs]
                for name, xs in inputs.items()}
    results, errors = {}, []
    start = threading.Barrier(2)

    def worker(name):
        try:
            start.wait()
            results[name] = [(s.enthalpy_j_kg, s.density_kg_m3, s.viscosity_pa_s)
                             for s in (service.state_pt(*x) for x in inputs[name])]
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(name,)) for name in inputs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    for name in inputs:
        assert len(results[name]) == len(expected[name])
        for got, want in zip(results[name], expected[name]):
            assert got == pytest.approx(want, rel=1e-10)
