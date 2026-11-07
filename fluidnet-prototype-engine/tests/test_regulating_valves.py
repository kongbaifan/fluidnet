import math

import pytest

from fn_engine.bench import run_module_test
from fn_engine.compiler import compile_project
from fn_engine.models import ModuleTestRequest
from fn_engine.regulating_valves import example, valve_definition
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady


@pytest.mark.parametrize('drop',[-50000.,0.,10000.,20000.,50000.,150000.])
@pytest.mark.parametrize('opening',[0.,.4,1.])
def test_picv_has_finite_authority_and_a_pressure_independent_range(drop,opening):
    p=example()
    p.instances[1].parameters['opening_ratio']=opening
    p.instances[2].parameters['pressure_pa']=250000.-drop
    v=solve_steady(compile_project(p)).variables
    expected=0. if drop<=0 else 5.*opening*min(1.,math.sqrt(drop/20000.))
    assert v['Regulator.actual_volume_flow_m3_h']==pytest.approx(expected,abs=1e-6)
    assert v['Regulator.regulating']==int(opening>0 and drop>=20000.)
    assert v['Regulator.main.mass_flow_kg_s']*drop>=-1e-8


@pytest.mark.parametrize('drop',[-10000.,0.,20000.,35000.,50000.,100000.])
def test_bypass_threshold_proportional_band_and_full_open_resistance(drop):
    p=example('differential_bypass_valve')
    p.instances[2].parameters['pressure_pa']=250000.-drop
    v=solve_steady(compile_project(p)).variables
    opening=min(1.,max(0.,(drop-20000.)/30000.))
    rho=v['Regulator.in0.density_kg_m3']
    expected=16*opening*math.sqrt(max(0.,drop)/1e5/(rho/1000.))
    assert v['Regulator.effective_opening']==pytest.approx(opening)
    assert v['Regulator.actual_volume_flow_m3_h']==pytest.approx(expected,abs=1e-6)


def test_runtime_setting_and_failed_range_do_not_advance_counters():
    p=example();p.instances[0].parameters['pressure_pa']=600000.
    p.instances[2].parameters['pressure_pa']=550000.
    session=SimulationSession(compile_project(p),2.,.1)
    try:
        session.initialize();first=session.advance()
        session.set_parameter('Regulator','opening_ratio',.5)
        second=session.advance()
        assert second.variables['Regulator.actual_volume_flow_m3_h']==pytest.approx(2.5,rel=1e-6)
        accepted=session.last_accepted_frame
        session.set_parameter('Return','pressure_pa',200000.)
        with pytest.raises(Exception):session.advance()
        assert session.time==.2 and session.last_accepted_frame==accepted
        expected=.1*(first.variables['Regulator.main.mass_flow_kg_s']+second.variables['Regulator.main.mass_flow_kg_s'])
        assert accepted.variables['Regulator.state.throughput_kg']==pytest.approx(expected)
    finally:session.close()


@pytest.mark.parametrize('picv',[False,True])
def test_author_validation_uses_actual_worker_and_declared_outputs(picv):
    result=run_module_test(ModuleTestRequest(module=valve_definition(picv),inlet_pressure_pa=250000.,outlet_pressure_pa=200000.))
    assert result.frame.valid and result.frame.variables['D1.actual_volume_flow_m3_h']>0
