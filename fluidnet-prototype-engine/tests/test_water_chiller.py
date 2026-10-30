"""C4：水冷冷水机组对三方程联立解、能量守恒、满载上漂与停机/越界。"""
import math

import numpy as np
import pytest
from scipy.optimize import least_squares

from fn_engine.air_catalog import water_chiller
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.refrigeration.cycle import DeviceRangeError, cycle_rates, rated_displacement
from fn_engine.water_chiller import evaluate_chiller, refrigerant_service

PARAMS = {p.id: p.default for p in water_chiller().parameters}
WATER = property_service(FluidConfig(fluid='Water', phase_policy='liquid'))


def run(t_in=285.15, m_e=1., t_c=303.15, m_c=1.6, check=True, **updates):
    e, c = WATER.state_pt(250000., t_in), WATER.state_pt(250000., t_c)
    return e, c, evaluate_chiller(e, m_e, c, m_c, PARAMS | updates, WATER, 240000., check=check)


def independent(e, m_e, c, m_c, setpoint_k, limited):
    """直接联立：蒸发器、冷凝器 ε–NTU 与循环，按是否满载选未知量。"""
    service = refrigerant_service(PARAMS)
    displacement = rated_displacement(service, PARAMS)
    ce, cc = m_e*e.specific_heat_j_kg_k, m_c*c.specific_heat_j_kg_k
    ge, gc = ce*-math.expm1(-PARAMS['evaporator_ua_w_k']/ce), cc*-math.expm1(-PARAMS['condenser_ua_w_k']/cc)
    target = m_e*(e.enthalpy_j_kg-WATER.state_pt(240000., setpoint_k).enthalpy_j_kg)

    def residual(x):
        te, tc, load = x[0], x[1], 1. if limited else x[2]
        rates = cycle_rates(service, PARAMS, displacement, te, tc, 1.)
        rows = [(ge*(e.temperature_k-te)-load*rates['cooling_w'])/1000, (gc*(tc-c.temperature_k)-load*rates['rejection_w'])/1000]
        return rows if limited else rows+[(load*rates['cooling_w']-target)/1000]
    start = [e.temperature_k-4, c.temperature_k+6] + ([] if limited else [.5])
    solution = least_squares(residual, start, xtol=1e-14, ftol=1e-14, gtol=1e-14).x
    return solution[0], solution[1], 1. if limited else solution[2]


@pytest.mark.parametrize('t_in,m_e,t_c,limited', [(285.15, 1., 303.15, False), (285.15, 1.5, 303.15, False),
                                                   (281.15, 1., 303.15, False), (288.15, 2., 303.15, True)])
def test_operating_point_matches_direct_solve(t_in, m_e, t_c, limited):
    e, c, result = run(t_in, m_e, t_c)
    o = result['outputs']
    assert o['capacity_limited'] is limited
    te, tc, load = independent(e, m_e, c, 1.6, PARAMS['chilled_water_setpoint_k'], limited)
    assert o['evaporating_temperature_k'] == pytest.approx(te, abs=1e-6)
    assert o['condensing_temperature_k'] == pytest.approx(tc, abs=1e-6)
    assert o['load_ratio'] == pytest.approx(load, rel=1e-8)
    leaving = WATER.state_ph(240000., result['evaporator_outlet_h']).temperature_k
    if limited:
        assert leaving > PARAMS['chilled_water_setpoint_k']+.5
    else:
        assert leaving == pytest.approx(PARAMS['chilled_water_setpoint_k'], abs=1e-9)


@pytest.mark.parametrize('t_in,m_e', [(285.15, 1.), (288.15, 2.)])
def test_energy_closes_on_both_water_sides(t_in, m_e):
    e, c, result = run(t_in, m_e)
    o = result['outputs']
    assert o['condenser_heat_w'] == pytest.approx(o['cooling_power_w']+o['shaft_power_w'], rel=1e-12)
    assert m_e*(e.enthalpy_j_kg-result['evaporator_outlet_h']) == pytest.approx(o['cooling_power_w'], rel=1e-12)
    assert 1.6*(result['condenser_outlet_h']-c.enthalpy_j_kg) == pytest.approx(o['condenser_heat_w'], rel=1e-12)
    assert o['electric_power_w'] == pytest.approx(o['shaft_power_w']/PARAMS['motor_efficiency'])
    assert abs(o['evaporator_equation_residual_w']) < 1e-6 and abs(o['condenser_equation_residual_w']) < 1e-6


def test_warmer_condenser_water_lowers_cop_at_same_duty():
    cops = [run(t_c=value)[2]['outputs'] for value in (298.15, 303.15, 308.15)]
    assert [o['cooling_power_w'] for o in cops] == pytest.approx([cops[0]['cooling_power_w']]*3, rel=1e-9)
    assert cops[0]['cop'] > cops[1]['cop'] > cops[2]['cop']


def test_idle_states_pass_water_through():
    for kwargs in ({'t_in': 279.15}, {'m_e': 0.}, {'running': 0.}):
        e, c, result = run(**kwargs)
        assert not result['active'] and result['outputs']['cooling_power_w'] == 0
        assert result['evaporator_outlet_h'] == e.enthalpy_j_kg and result['condenser_outlet_h'] == c.enthalpy_j_kg
    assert np.isclose(run(m_c=0., t_in=279.15)[2]['outputs']['load_ratio'], 0.)


def test_rejects_missing_condenser_flow_and_envelope():
    with pytest.raises(DeviceRangeError) as error:
        run(m_c=0.)
    assert error.value.code == 'CHILLER_CONDENSER_NO_FLOW'
    with pytest.raises(DeviceRangeError) as error:
        run(max_condensing_temperature_k=305.15)
    assert error.value.code == 'REFRIGERATION_ENVELOPE'
    assert run(max_condensing_temperature_k=305.15, check=False)[2]['active']
