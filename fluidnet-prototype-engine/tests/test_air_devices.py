"""C/H：CoolProp 独立物性和设备能量/水分极限，不从实现生成 expected。"""
import pytest
from CoolProp.CoolProp import HAPropsSI

from fn_engine.air_devices import evaluate_cooling_coil, evaluate_humidifier
from fn_engine.moist_air import AirPropertyError, MoistAirService


def inlet(t=303.15,w=.015):
    return MoistAirService().state_ptw(101325,t,w)


@pytest.mark.parametrize('w',[.004,.015])
@pytest.mark.parametrize('bf',[0.,.15,1.])
def test_coil_dry_wet_and_bypass(w,bf):
    source=inlet(w=w)
    result=evaluate_cooling_coil(source,1.3,{'coil_surface_temperature_k':285.15,'bypass_factor':bf})
    out=result.outlet_state
    ws=HAPropsSI('W','P',101325,'T',285.15,'R',1.)
    expected_w=w if w <= ws else bf*w+(1-bf)*ws
    assert out.humidity_ratio_kg_kg == pytest.approx(expected_w,abs=1e-11)
    assert result.water_removed_kg_s == pytest.approx(1.3*(w-expected_w),abs=1e-11)
    assert (1.3*source.enthalpy_j_kg_dry_air+result.heat_to_air_w
            -result.water_removed_kg_s*4180*12-1.3*out.enthalpy_j_kg_dry_air) == pytest.approx(0,abs=1e-6)
    if bf == 1:
        assert result.outputs['shr'] is None


@pytest.mark.parametrize('mode',['adiabatic','isothermal'])
def test_humidifier_saturation_limit(mode):
    source=inlet(293.15,.008)
    parameters={'mode':mode,'moisture_addition_kg_kg':.04,'saturation_action':'limit'}
    result=evaluate_humidifier(source,2.,parameters)
    assert result.outputs['limited']
    assert result.outlet_state.relative_humidity == pytest.approx(1.,abs=1e-7)
    assert result.water_added_kg_s == pytest.approx(2*(result.outlet_state.humidity_ratio_kg_kg-.008))
    assert result.heat_to_air_w == pytest.approx(2*(result.outlet_state.enthalpy_j_kg_dry_air-source.enthalpy_j_kg_dry_air),abs=1e-6)
    with pytest.raises(AirPropertyError,match='饱和'):
        evaluate_humidifier(source,2.,{**parameters,'saturation_action':'error'})


def test_zero_flow_no_cooling_and_rejected_reverse():
    params={'coil_surface_temperature_k':303.15,'bypass_factor':.15}
    assert not evaluate_cooling_coil(inlet(),1.,params).outputs['active']
    assert evaluate_cooling_coil(inlet(),0.,params).water_removed_kg_s == 0
    with pytest.raises(AirPropertyError,match='反向'):
        evaluate_cooling_coil(inlet(),-1.,params)
    with pytest.raises(AirPropertyError,match='结霜'):
        evaluate_cooling_coil(inlet(),1.,{**params,'coil_surface_temperature_k':270.})
