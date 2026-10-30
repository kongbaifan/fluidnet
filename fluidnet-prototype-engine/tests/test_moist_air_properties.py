"""A01–A05：独立网格、基准和非法状态；不使用被测函数构造期望。"""
import json

import pytest
from CoolProp.CoolProp import HAPropsSI

from fn_engine.air_models import MoistAirOptions
from fn_engine.models import PortState, UnitSpec
from fn_engine.moist_air import AirPropertyError, MoistAirService


@pytest.mark.parametrize('p,t,rh', [(p,t,r) for p in (60000.,101325.,120000.)
                                  for t in (253.15,293.15,313.15) for r in (0.,.5,1.)])
def test_states_roundtrip_and_mass_basis(p,t,rh):
    service = MoistAirService()
    w = HAPropsSI('W','P',p,'T',t,'R',rh)
    if w > .05:
        with pytest.raises(AirPropertyError, match='含湿量'):
            service.state_ptw(p,t,w)
        return
    state = service.state_ptw(p,t,w)
    assert state.relative_humidity == pytest.approx(rh,abs=1e-6)
    assert service.humidity_from_rh(p,t,rh) == pytest.approx(w,abs=1e-12)
    assert state.enthalpy_j_kg*(1+w) == pytest.approx(HAPropsSI('H','P',p,'T',t,'W',w),abs=1e-8)
    assert state.specific_heat_j_kg_k*(1+w) == pytest.approx(HAPropsSI('C','P',p,'T',t,'W',w))
    assert sum(state.composition.values()) == pytest.approx(1)
    recovered = service.state_phw(p,state.enthalpy_j_kg_dry_air,w)
    assert recovered.temperature_k == pytest.approx(t,abs=1e-5)
    if rh == 0:
        assert state.dew_point_k is None
    json.dumps(state.model_dump(),allow_nan=False)


@pytest.mark.parametrize('p,t,w', [(101325,293.15,-.001),(101325,293.15,.05),
                                  (59999,293.15,.005),(101325,334,.005),(101325,float('nan'),.005)])
def test_invalid_states_fail(p,t,w):
    with pytest.raises(AirPropertyError):
        MoistAirService().state_ptw(p,t,w)


@pytest.mark.parametrize('canonical,display,scale,offset,value', [
    ('K','°C',1,-273.15,300),('1','%',.01,0,.5),('kg/kg_da','g/kg_da',.001,0,.008),
    ('J/kg_da','kJ/kg_da',1000,0,42000),('m3/s','m3/h',1/3600,0,3)])
def test_units_roundtrip(canonical,display,scale,offset,value):
    unit=UnitSpec(quantity='test',canonical_unit=canonical,display_unit=display,
                  display_scale=scale,display_offset=offset)
    assert unit.to_canonical(unit.from_canonical(value)) == pytest.approx(value,rel=1e-12)


def test_cache_is_not_mutated_and_dry_payload_stays_small():
    service=MoistAirService()
    state=service.state_ptw(101325,293.15,.008)
    state.temperature_k=999
    assert service.state_ptw(101325,293.15,.008).temperature_k == 293.15
    assert 'enthalpy_j_kg_dry_air' not in PortState().model_dump()
    assert MoistAirOptions().contract_version == 1
