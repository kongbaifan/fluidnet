"""Independent ventilation, circular/rectangular friction and branching-path checks."""
from copy import deepcopy
import math
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from fn_engine.adapters import AdapterError, default_registry
from fn_engine.adapters import airducts
from fn_engine.api import create_app


def request_data():
    return {'roughness_m': 0., 'pressure_margin_ratio': .1, 'fan_efficiency': .5,
        'duct_sizes': [{'id': 'round', 'name': 'D200', 'shape': 'round', 'diameter_m': .2}],
        'segments': [
            {'id': 'root', 'name': '总管', 'length_m': 10., 'local_loss_coefficient': 2., 'equipment_pressure_drop_pa': 100.},
            {'id': 'a', 'name': '末端 A', 'parent_id': 'root', 'flow_m3_h': 3.6, 'length_m': 20., 'local_loss_coefficient': 0.},
            {'id': 'b', 'name': '末端 B', 'parent_id': 'root', 'flow_m3_h': 7.2, 'length_m': 40., 'local_loss_coefficient': 0.,
             'equipment_pressure_drop_pa': 30.}]}


@pytest.fixture
def registry(monkeypatch):
    state = SimpleNamespace(density_kg_m3=1.2, viscosity_pa_s=1.8e-5)
    monkeypatch.setattr(airducts, 'property_service', lambda _: SimpleNamespace(state_pt=lambda *args: state))
    return default_registry()


def run(registry, data):
    return registry.execute({'adapter_id': 'airflow.duct_design', 'inputs': data}).outputs


def test_fresh_air_takes_max_per_zone_then_sums_without_double_counting():
    zones = [dict(id='a', name='A', area_m2=30., height_m=3., people=4, per_person_m3_h=30., air_changes_h=1.),
             dict(id='b', name='B', area_m2=40., height_m=3., people=2, per_person_m3_h=30., air_changes_h=1.)]
    output = default_registry().execute({'adapter_id': 'ventilation.requirements', 'inputs': {'zones': zones}}).outputs
    assert output['total_flow_m3_h'] == 240  # max(120,90) + max(60,120); not max(180,210), nor 390.
    assert [z['governing'] for z in output['zones']] == ['people', 'air_changes']
    assert output['total_people'] == 6 and output['total_area_m2'] == 70


def test_fresh_air_distinguishes_zero_and_equal_requirements():
    zones = [dict(id='a', name='A', area_m2=20., height_m=3., people=2, per_person_m3_h=30., air_changes_h=1.),
             dict(id='b', name='B', area_m2=20., height_m=3., people=0, per_person_m3_h=30., air_changes_h=0.)]
    registry = default_registry()
    result = registry.execute({'adapter_id': 'ventilation.requirements', 'inputs': {'zones': zones}}).outputs
    assert result['total_flow_m3_h'] == 60
    assert [z['governing'] for z in result['zones']] == ['both', 'none']
    zones[1]['id'] = 'a'
    with pytest.raises(AdapterError) as error:
        registry.execute({'adapter_id': 'ventilation.requirements', 'inputs': {'zones': zones}})
    assert error.value.detail.code == 'ADAPTER_INPUT_INVALID'


def test_tree_conserves_flow_and_uses_worst_path_not_sum(registry):
    data = request_data()
    original = deepcopy(data)
    output = run(registry, data)
    root, a, b = output['segments']
    assert root['flow_m3_h'] == pytest.approx(a['flow_m3_h']+b['flow_m3_h'])
    assert output['total_flow_m3_h'] == pytest.approx(10.8)
    # Laminar circular Darcy loss = 128 mu L Q / (pi D^4).
    expected_root = 128*1.8e-5*10*.003/(math.pi*.2**4)
    expected_b = 128*1.8e-5*40*.002/(math.pi*.2**4)
    dynamic = .5*1.2*(.003/(math.pi*.2**2/4))**2
    expected = 130+expected_root+2*dynamic+expected_b
    assert root['friction_pressure_drop_pa'] == pytest.approx(expected_root)
    assert output['system_pressure_drop_pa'] == pytest.approx(expected)
    assert output['required_fan_total_pressure_pa'] == pytest.approx(expected*1.1)
    assert output['estimated_input_power_kw'] == pytest.approx(.003*expected*1.1/.5/1000)
    assert output['critical_path'] == ['root', 'b']
    assert a['balancing_pressure_drop_pa'] == pytest.approx(b['path_pressure_drop_pa']-a['path_pressure_drop_pa'])
    assert data == original


def test_rectangular_area_and_laminar_shape_factor_are_not_round_equivalent(registry):
    data = request_data()
    data['duct_sizes'] = [{'id': 'rect', 'name': '400x100', 'shape': 'rectangular', 'width_m': .4, 'height_m': .1}]
    data['segments'] = [{'id': 'r', 'name': 'R', 'shape': 'rectangular', 'flow_m3_h': 14.4, 'length_m': 15., 'local_loss_coefficient': 3.}]
    result = run(registry, data)['segments'][0]
    dh, v, alpha = .16, .1, .25
    po = 96*(1-1.3553*alpha+1.9467*alpha**2-1.7012*alpha**3+.9564*alpha**4-.2537*alpha**5)
    assert result['area_m2'] == pytest.approx(.04)
    assert result['velocity_m_s'] == pytest.approx(v)
    assert result['hydraulic_diameter_m'] == pytest.approx(dh)
    assert result['friction_pressure_drop_pa'] == pytest.approx(po*1.8e-5*v/(2*dh**2)*15)
    assert result['local_pressure_drop_pa'] == pytest.approx(3*1.2*v*v/2)


@pytest.mark.parametrize('reynolds', [2300., 3000., 4000., 10000.])
def test_rectangular_transition_and_turbulence_follow_declared_model(registry, reynolds):
    data = request_data()
    a, b, rho, mu = .2, .1, 1.2, 1.8e-5
    dh = 2*a*b/(a+b)
    v = reynolds*mu/(rho*dh)
    data['duct_sizes'] = [{'id': 'r', 'name': '200x100', 'shape': 'rectangular', 'width_m': a, 'height_m': b}]
    data['segments'] = [{'id': 'r', 'name': 'R', 'shape': 'rectangular', 'flow_m3_h': v*a*b*3600}]
    result = run(registry, data)['segments'][0]
    alpha = b/a
    po = 96*(1-1.3553*alpha+1.9467*alpha**2-1.7012*alpha**3+.9564*alpha**4-.2537*alpha**5)
    laminar = po/reynolds*rho*v*v/(2*dh)
    turbulent = (-1.8*math.log10(6.9/reynolds))**-2*rho*v*v/(2*dh)
    blend = min(1, max(0, (reynolds-2300)/1700))
    assert result['specific_drop_pa_m'] == pytest.approx(laminar*(1-blend)+turbulent*blend)


def test_auto_size_uses_area_and_can_reject_unusable_height(registry):
    data = request_data()
    data['duct_sizes'] += [{'id': 'large', 'name': 'D400', 'shape': 'round', 'diameter_m': .4},
                           {'id': 'small', 'name': 'D100', 'shape': 'round', 'diameter_m': .1}]
    data['duct_sizes'].reverse()
    assert run(registry, data)['segments'][0]['size']['id'] == 'small'
    data['segments'][1]['flow_m3_h'] = 1200.
    assert run(registry, data)['segments'][0]['size']['id'] == 'large'
    data['max_height_m'] = .2
    output = run(registry, data)
    assert not output['feasible'] and output['estimated_input_power_kw'] is None
    assert output['segments'][0]['size']['id'] == 'round'


def test_fixed_size_is_never_silently_enlarged(registry):
    data = request_data()
    data['segments'][1].update(flow_m3_h=1500., fixed_size_id='round')
    data['duct_sizes'].append({'id': 'large', 'name': 'D800', 'shape': 'round', 'diameter_m': .8})
    output = run(registry, data)
    assert not output['feasible']
    assert output['segments'][1]['selection'] == 'fixed'
    assert output['segments'][1]['size']['id'] == 'round'


def test_rectangular_fixed_size_is_not_rotated_to_pass_height(registry):
    data = request_data()
    data['max_height_m'] = .2
    data['duct_sizes'] = [{'id': 'tall', 'name': '100x400', 'shape': 'rectangular', 'width_m': .1, 'height_m': .4}]
    data['segments'] = [{'id': 'r', 'name': 'R', 'shape': 'rectangular', 'fixed_size_id': 'tall', 'flow_m3_h': 3.6}]
    output = run(registry, data)
    assert not output['feasible'] and output['segments'][0]['size']['height_m'] == .4


def test_zero_flow_has_no_device_losses_critical_path_or_fan_power(registry):
    data = request_data()
    for s in data['segments']:
        s['flow_m3_h'] = 0.
    result = run(registry, data)
    assert result['total_flow_m3_h'] == result['required_fan_total_pressure_pa'] == result['estimated_input_power_kw'] == 0
    assert result['critical_path'] == []
    assert all(s['pressure_drop_pa'] == 0 and s['status'] == 'no_flow' for s in result['segments'])


def test_high_pressure_does_not_claim_low_pressure_model_is_valid(registry):
    data = request_data()
    data['segments'][0]['equipment_pressure_drop_pa'] = 10000.
    output = run(registry, data)
    assert not output['feasible'] and any('5%' in w for w in output['warnings'])


@pytest.mark.parametrize('mutate', [
    lambda p: p['segments'][0].update(flow_m3_h=1.),
    lambda p: p['segments'][1].update(parent_id='missing'),
    lambda p: p['segments'][1].update(id='root'),
    lambda p: p['segments'][1].update(parent_id=None),
    lambda p: (p['segments'][1].update(parent_id='b'), p['segments'][2].update(parent_id='a')),
    lambda p: p['segments'][1].update(fixed_size_id='missing'),
    lambda p: p['segments'][1].update(shape='rectangular', fixed_size_id='round'),
    lambda p: p['duct_sizes'][0].update(width_m=.2),
    lambda p: p.update(pressure_pa=False),
    lambda p: p.update(fan_efficiency=0.),
    lambda p: p.update(max_height_m=.05),
    lambda p: p['segments'][1].update(flow_m3_h=float('inf')),
])
def test_invalid_geometry_and_values_fail_before_calculation(registry, mutate):
    data = request_data()
    mutate(data)
    with pytest.raises(AdapterError) as error:
        run(registry, data)
    assert error.value.detail.code == 'ADAPTER_INPUT_INVALID'


def test_new_adapters_work_over_http_with_real_air_properties():
    with TestClient(create_app()) as client:
        result = client.post('/api/v1/adapters/execute', json={'adapter_id': 'airflow.duct_design', 'inputs': request_data()})
        assert result.status_code == 200, result.text
        assert 1.19 < result.json()['outputs']['density_kg_m3'] < 1.22
        assert client.get('/api/v1/adapters/ventilation.requirements').status_code == 200
