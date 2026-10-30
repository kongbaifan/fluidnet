"""C2：双侧水盘管对独立逆流分段模型、ε–NTU 干工况极限与两本账。"""
import math

import pytest
from CoolProp.CoolProp import HAPropsSI
from scipy.optimize import brentq

from fn_engine.air_devices import evaluate_water_coil
from fn_engine.moist_air import AirPropertyError, MoistAirService, liquid_enthalpy

P = 101325.
PARAMS = {'air_side_ua_w_k': 4000., 'water_side_ua_w_k': 8000.}
CP_W = 4200.


def detailed_counterflow(t_air, w_air, m_da, t_w_in, m_w, ua_a, ua_w, segments=200):
    """逆流分段参考：逐段判断表面干湿，局部焓势（刘易斯数 1），对未知出水温度打靶。

    不使用饱和线线性化或全干/全湿假设；与被测模型只共用 CoolProp 湿空气物性。
    """
    da, dw = ua_a/segments, ua_w/segments

    def march(t_w_out):
        t, w, tw = t_air, w_air, t_w_out
        h = HAPropsSI('H', 'P', P, 'T', t, 'W', w)
        condensate = 0.
        for _ in range(segments):
            cp = HAPropsSI('C', 'P', P, 'T', t, 'W', w)
            dew = HAPropsSI('D', 'P', P, 'T', t, 'W', w) if w > 0 else 0.
            ts = (da*t+dw*tw)/(da+dw)
            if ts >= dew:
                q = da*(t-ts)
                h -= q/m_da
                t = HAPropsSI('T', 'P', P, 'H', h, 'W', w)
                tw -= q/(m_w*CP_W)
                continue
            # 湿段：表面温度满足 (da/cp)·(h − h_s(Ts)) = dw·(Ts − Tw)。
            def balance(surface):
                return da/cp*(h-HAPropsSI('H', 'P', P, 'T', surface, 'R', 1.))-dw*(surface-tw)
            ts = brentq(balance, tw, t, xtol=1e-9)
            ws = HAPropsSI('W', 'P', P, 'T', ts, 'R', 1.)
            q = da/cp*(h-HAPropsSI('H', 'P', P, 'T', ts, 'R', 1.))
            dm = max(da/cp*(w-ws), 0.)
            h -= q/m_da
            w -= dm/m_da
            condensate += dm
            t = HAPropsSI('T', 'P', P, 'H', h, 'W', w)
            tw -= (q-dm*liquid_enthalpy(ts))/(m_w*CP_W)
        return tw, t, w, h, condensate

    t_w_out = brentq(lambda guess: march(guess)[0]-t_w_in, t_w_in+1e-6, t_air-1e-6, xtol=1e-8)
    tw, t, w, h, condensate = march(t_w_out)
    return {'t_out': t, 'w_out': w, 'h_out': h, 'water_heat_w': m_w*CP_W*(t_w_out-t_w_in), 'condensate_kg_s': condensate}


def coil(t_air=300.15, w_air=.0113, m_da=1.6, t_w=280.15, m_w=1., params=PARAMS):
    service = MoistAirService()
    inlet = service.state_ptw(P, t_air, w_air)
    return inlet, evaluate_water_coil(inlet, m_da, t_w, m_w, CP_W, params, P, service)


def test_dry_limit_matches_counterflow_epsilon_ntu():
    inlet, result = coil(t_w=291.15)
    o = result.outputs
    assert not o['wet'] and o['condensate_kg_s'] == 0
    c_air, c_water = 1.6*inlet.specific_heat_j_kg_dry_air_k, 1.*CP_W
    ua = 1/(1/4000.+1/8000.)
    cmin, cmax = min(c_air, c_water), max(c_air, c_water)
    ntu, ratio = ua/cmin, cmin/cmax
    effectiveness = (1-math.exp(-ntu*(1-ratio)))/(1-ratio*math.exp(-ntu*(1-ratio)))
    assert o['water_heat_w'] == pytest.approx(effectiveness*cmin*(300.15-291.15), rel=1e-12)
    assert result.outlet_state.humidity_ratio_kg_kg == pytest.approx(.0113, abs=1e-14)


@pytest.mark.parametrize('t_w,regime', [(280.15, 'partial'), (283.15, 'partial'), (286.15, 'partial'),
                                        (288.15, 'dry'), (291.15, 'dry')])
def test_matches_detailed_counterflow_reference(t_w, regime):
    """进风露点 15.84 °C：7–13 °C 进水为部分湿工况，15 °C 进水虽低于露点但表面全干。

    实测偏差（docs/CHILLER_AIR_LOOP_ACCEPTANCE.md）：热量 ≤ 0.6%、出风温度 ≤ 0.01 K、除湿量 ≤ 4%。"""
    _, result = coil(t_w=t_w)
    reference = detailed_counterflow(300.15, .0113, 1.6, t_w, 1., 4000., 8000.)
    o = result.outputs
    assert (o['wet_fraction'] > 0) == (regime == 'partial')
    assert o['water_heat_w'] == pytest.approx(reference['water_heat_w'], rel=.01)
    assert result.outlet_state.temperature_k == pytest.approx(reference['t_out'], abs=.05)
    dehumidified = .0113-reference['w_out']
    assert .0113-result.outlet_state.humidity_ratio_kg_kg == pytest.approx(dehumidified, rel=.06, abs=2e-6)


@pytest.mark.parametrize('t_w', [279.15, 285.15, 295.15, 320.15])
def test_air_and_water_ledgers_close(t_w):
    inlet, result = coil(t_w=t_w)
    o = result.outputs
    air_loss = 1.6*(inlet.enthalpy_j_kg_dry_air-result.outlet_state.enthalpy_j_kg_dry_air)
    assert air_loss == pytest.approx(o['total_heat_w'], rel=1e-12, abs=1e-9)
    assert o['water_heat_w'] == pytest.approx(air_loss-o['condensate_kg_s']*result.removed_water_enthalpy_j_kg, rel=1e-12, abs=1e-9)
    assert result.heat_to_air_w == pytest.approx(-o['water_heat_w'])
    assert o['condensate_kg_s'] == pytest.approx(1.6*(.0113-result.outlet_state.humidity_ratio_kg_kg), abs=1e-15)
    assert o['condensate_kg_s'] >= 0


def test_hot_water_heats_air_without_condensing():
    _, result = coil(t_w=320.15)
    o = result.outputs
    assert o['water_heat_w'] < 0 and result.outlet_state.temperature_k > 300.15
    assert not o['wet'] and o['condensate_kg_s'] == 0


def test_more_water_or_colder_water_cools_more():
    loads = [coil(m_w=flow)[1].outputs['water_heat_w'] for flow in (.2, .5, 1., 2.)]
    assert loads == sorted(loads)
    loads = [coil(t_w=t)[1].outputs['water_heat_w'] for t in (288.15, 284.15, 280.15)]
    assert loads == sorted(loads)


def test_heat_is_continuous_across_the_dry_wet_boundary():
    """水阀调节会让盘管在干/湿之间来回；热量不能在切换点跳变，否则 PID 会在跳变两侧振荡。"""
    temperatures = [286.15+.05*i for i in range(60)]
    loads = [coil(t_w=value)[1].outputs['water_heat_w'] for value in temperatures]
    steps = [a-b for a, b in zip(loads, loads[1:])]
    assert all(step > 0 for step in steps)
    assert max(steps) < 2*min(steps)
    flows = [.3+.02*i for i in range(40)]
    loads = [coil(t_w=285.15, m_w=value)[1].outputs['water_heat_w'] for value in flows]
    assert all(b > a for a, b in zip(loads, loads[1:]))


def test_idle_and_invalid_states():
    for kwargs in ({'m_w': 0.}, {'m_da': 0.}, {'params': {'air_side_ua_w_k': 0., 'water_side_ua_w_k': 8000.}}):
        inlet, result = coil(**kwargs)
        assert result.outputs['water_heat_w'] == 0 and not result.outputs['active']
        assert result.outlet_state.enthalpy_j_kg_dry_air == pytest.approx(inlet.enthalpy_j_kg_dry_air)
    for kwargs, code in (({'t_w': 272.15}, 'AIR_COIL_FROST_UNSUPPORTED'), ({'m_da': -1.}, 'AIR_REVERSE_FLOW_UNSUPPORTED'),
                         ({'m_w': -1.}, 'AIR_REVERSE_FLOW_UNSUPPORTED')):
        with pytest.raises(AirPropertyError) as error:
            coil(**kwargs)
        assert error.value.code == code
