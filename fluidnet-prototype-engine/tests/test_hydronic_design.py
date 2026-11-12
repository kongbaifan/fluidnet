"""Design-flow physics, tree paths, catalog bounds and the public adapter boundary."""
from copy import deepcopy
import math
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from fn_engine.adapters import AdapterError, default_registry
from fn_engine.adapters import hydronics
from fn_engine.api import create_app


def inputs():
    return {'temperature_difference_k': 10., 'head_margin_ratio': .1,
        'pipe_sizes': [{'dn': 40, 'inner_diameter_m': .04}],
        'segments': [
            {'id': 'root', 'name': '总管', 'length_m': 10., 'local_loss_coefficient': 0., 'equipment_pressure_drop_pa': 30000.},
            {'id': 'a', 'name': '支路 A', 'parent_id': 'root', 'heat_load_w': 418., 'length_m': 20.,
             'local_loss_coefficient': 0., 'equipment_pressure_drop_pa': 20000., 'valve_pressure_drop_pa': 10000.},
            {'id': 'b', 'name': '支路 B', 'parent_id': 'root', 'heat_load_w': 836., 'length_m': 40.,
             'local_loss_coefficient': 0., 'equipment_pressure_drop_pa': 20000., 'valve_pressure_drop_pa': 10000.}],
        'pumps': [{'id': 'test-p', 'name': '测试泵', 'data_kind': 'example', 'source': '独立手算测试数据',
                   'min_flow_m3_h': .01, 'max_flow_m3_h': 1.,
                   'points': [{'flow_m3_h': 0., 'head_m': 20., 'efficiency': .5}, {'flow_m3_h': 1., 'head_m': 10., 'efficiency': .5}]}],
        'valves': [{'id': f'v-{kv}', 'name': f'测试阀 {kv}', 'data_kind': 'example', 'source': '测试', 'dn': 15, 'kvs_m3_h': kv} for kv in (.2, .4)]}


@pytest.fixture
def registry(monkeypatch):
    water = SimpleNamespace(density_kg_m3=1000., specific_heat_j_kg_k=4180., viscosity_pa_s=.001)
    monkeypatch.setattr(hydronics, 'property_service', lambda _: SimpleNamespace(state_pt=lambda *args: water))
    return default_registry()


def run(registry, data):
    return registry.execute({'adapter_id': 'hydronics.design', 'inputs': data}).outputs


def test_loads_conserve_flow_and_head_is_worst_path_not_sum(registry):
    data = inputs()
    before = deepcopy(data)
    result = run(registry, data)
    root, a, b = result['segments']
    assert result['total_load_w'] == 1254.
    assert result['total_flow_m3_h'] == pytest.approx(.108)
    assert root['flow_m3_h'] == pytest.approx(a['flow_m3_h']+b['flow_m3_h'])
    # All three pipes are laminar: dp=128*mu*L*Q/(pi*D**4).
    root_loss = 128*.001*10*.00003/(math.pi*.04**4)
    a_loss = 128*.001*20*.00001/(math.pi*.04**4)
    b_loss = 128*.001*40*.00002/(math.pi*.04**4)
    assert root['pipe_pressure_drop_pa'] == pytest.approx(root_loss)
    assert result['critical_path'] == ['root', 'b']
    assert result['circuit_pressure_drop_pa'] == pytest.approx(60000+root_loss+b_loss)
    assert result['required_head_m'] == pytest.approx((60000+root_loss+b_loss)*1.1/(1000*9.80665))
    assert a['balancing_pressure_drop_pa'] == pytest.approx(b_loss-a_loss)
    assert b['balancing_pressure_drop_pa'] == 0
    assert data == before


def test_valve_capacity_and_pump_curve_point_are_calculated(registry):
    result = run(registry, inputs())
    a = result['segments'][1]
    valve = a['valve']
    assert valve['required_kv_m3_h'] == pytest.approx(.036/math.sqrt(.1))
    assert valve['selected']['kvs_m3_h'] == .2
    assert valve['full_open_pressure_drop_pa'] == pytest.approx(1e5*(.036/.2)**2)
    pump = result['pump_candidates'][0]
    head = 20-.108*10
    assert pump['available_head_m'] == pytest.approx(head)
    assert pump['input_power_kw'] == pytest.approx(1000*9.80665*.00003*head/.5/1000)
    assert pump['pump']['source'] == '独立手算测试数据'


def test_no_curve_extrapolation_or_undersized_valve_recommendation(registry):
    data = inputs()
    data['pumps'][0]['max_flow_m3_h'] = .05
    data['valves'][0]['kvs_m3_h'] = .001
    data['valves'][1]['kvs_m3_h'] = .002
    result = run(registry, data)
    assert result['pump_candidates'] == []
    assert all(s['valve']['selected'] is None for s in result['segments'][1:])
    assert any('未外推' in message for message in result['warnings'])


def test_pipe_limit_failure_is_explicit_and_suppresses_pump_recommendation(registry):
    data = inputs()
    data['pipe_sizes'] = [{'dn': 1, 'inner_diameter_m': .001}]
    result = run(registry, data)
    assert not result['feasible']
    assert result['segments'][0]['status'] == 'limit_exceeded'
    assert not result['pump_candidates']
    assert result['warnings']


def test_select_smallest_compliant_diameter_and_honor_manual_choice(registry):
    data = inputs()
    data['pipe_sizes'] = [{'dn': 40, 'inner_diameter_m': .04}, {'dn': 20, 'inner_diameter_m': .02}]
    automatic = run(registry, data)
    assert automatic['segments'][0]['dn'] == 20
    data['segments'][0]['fixed_dn'] = 40
    manual = run(registry, data)
    assert manual['segments'][0]['dn'] == 40
    assert manual['required_head_m'] < automatic['required_head_m']


def test_zero_load_has_no_spurious_device_loss_or_selection(registry):
    data = inputs()
    for segment in data['segments']:
        segment['heat_load_w'] = 0.
    result = run(registry, data)
    assert result['required_head_m'] == 0
    assert result['critical_path'] == []
    assert result['pump_candidates'] == []
    assert all(s['pressure_drop_pa'] == 0 and s['valve'] is None for s in result['segments'])


@pytest.mark.parametrize('change', [
    lambda p: p['segments'][0].update(heat_load_w=1.),
    lambda p: p['segments'][0].update(valve_pressure_drop_pa=1.),
    lambda p: p['segments'][1].update(id='root'),
    lambda p: p['segments'][1].update(parent_id='missing'),
    lambda p: (p['segments'][1].update(parent_id='b'), p['segments'][2].update(parent_id='a')),
    lambda p: p['segments'][1].update(parent_id=None),
    lambda p: p['segments'][1].update(fixed_dn=999),
    lambda p: p['segments'][1].update(length_m=True),
    lambda p: p.update(temperature_difference_k=0.),
    lambda p: p.update(temperature_k=float('nan')),
    lambda p: p['pumps'][0]['points'][1].update(flow_m3_h=0.),
    lambda p: p['pumps'][0]['points'][1].update(head_m=25.),
    lambda p: p['pumps'][0].update(max_flow_m3_h=2.),
    lambda p: p['pumps'][0]['points'][0].update(efficiency=0.),
])
def test_invalid_topology_units_and_curves_are_rejected(registry, change):
    data = inputs()
    change(data)
    with pytest.raises(AdapterError) as error:
        run(registry, data)
    assert error.value.detail.code == 'ADAPTER_INPUT_INVALID'


def test_public_http_adapter_uses_real_water_properties():
    with TestClient(create_app()) as client:
        response = client.post('/api/v1/adapters/execute', json={'adapter_id': 'hydronics.design', 'request_id': 'water-1', 'inputs': inputs()})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['request_id'] == 'water-1'
        assert 999 < result['outputs']['density_kg_m3'] < 1001
        assert result['outputs']['critical_path'] == ['root', 'b']


def case_inputs():
    summer = inputs()
    summer['pipe_sizes'] = [{'dn': 80, 'inner_diameter_m': .02}, {'dn': 40, 'inner_diameter_m': .04}, {'dn': 50, 'inner_diameter_m': .05}]
    summer['segments'][1]['heat_load_w'] = 41800.
    summer['segments'][2]['heat_load_w'] = 418.
    winter = deepcopy(summer)
    winter['segments'][1]['heat_load_w'] = 418.
    winter['segments'][2]['heat_load_w'] = 62700.
    return {'cases': [{'id': 'summer', 'name': 'Summer', 'inputs': summer}, {'id': 'winter', 'name': 'Winter', 'inputs': winter}]}


def test_joint_sizes_each_branch_by_actual_bore_and_recomputes_losses(registry):
    data = case_inputs()
    original = deepcopy(data)
    independent = {c['id']: run(registry, c['inputs']) for c in data['cases']}
    output = registry.execute({'adapter_id': 'hydronics.design_cases', 'inputs': data}).outputs
    shared = {s['id']: s for s in output['shared_pipes']}
    assert shared['a']['governing_cases'] == ['summer']
    assert shared['b']['governing_cases'] == ['winter']
    # DN 80 deliberately has the smallest actual bore: numerical DN order must not determine the size.
    assert shared['a']['minimum_dn_by_case']['winter'] == 80
    assert shared['a']['dn'] != 80
    for case in output['cases']:
        native = next(c['inputs'] for c in data['cases'] if c['id'] == case['id'])
        fixed = deepcopy(native)
        for segment in fixed['segments']:
            segment['fixed_dn'] = shared[segment['id']]['dn']
        assert case['design'] == run(registry, fixed)
        assert case['design']['total_flow_m3_h'] == independent[case['id']]['total_flow_m3_h']
        for segment in case['design']['segments']:
            assert segment['dn'] == shared[segment['id']]['dn']
            assert segment['pressure_drop_pa'] == pytest.approx(sum(segment[k] for k in (
                'pipe_pressure_drop_pa', 'local_pressure_drop_pa', 'equipment_pressure_drop_pa', 'valve_pressure_drop_pa')))
    assert data == original


def test_joint_shared_bore_keeps_manual_limit_failure_visible(registry):
    data = case_inputs()
    for case in data['cases']:
        case['inputs']['segments'][1]['fixed_dn'] = 80
    output = registry.execute({'adapter_id': 'hydronics.design_cases', 'inputs': data}).outputs
    assert not output['feasible']
    assert next(s for s in output['shared_pipes'] if s['id'] == 'a')['selection'] == 'fixed'
    assert output['cases'][0]['design']['pump_candidates'] == []


def test_joint_zero_load_case_uses_other_case_pipes_without_extra_losses(registry):
    data = case_inputs()
    for s in data['cases'][1]['inputs']['segments']:
        s['heat_load_w'] = 0.
    output = registry.execute({'adapter_id': 'hydronics.design_cases', 'inputs': data}).outputs
    winter = output['cases'][1]['design']
    assert winter['required_head_m'] == 0 and winter['total_flow_m3_h'] == 0
    assert all(s['pressure_drop_pa'] == 0 for s in winter['segments'])
    assert all('winter' not in s['governing_cases'] for s in output['shared_pipes'])


@pytest.mark.parametrize('change', [
    lambda p: p['cases'][1].update(id='summer'),
    lambda p: p['cases'][1]['inputs']['segments'][1].update(length_m=30.),
    lambda p: p['cases'][1]['inputs']['segments'][1].update(local_loss_coefficient=3.),
    lambda p: p['cases'][1]['inputs']['segments'][1].update(fixed_dn=40),
    lambda p: p['cases'][1]['inputs'].update(roughness_m=.001),
    lambda p: p['cases'][1]['inputs']['pipe_sizes'][0].update(inner_diameter_m=.025),
    lambda p: p.update(cases=p['cases'][:1]),
])
def test_joint_rejects_different_physical_pipes(registry, change):
    data = case_inputs()
    change(data)
    with pytest.raises(AdapterError) as caught:
        registry.execute({'adapter_id': 'hydronics.design_cases', 'inputs': data})
    assert caught.value.detail.code == 'ADAPTER_INPUT_INVALID'
