from copy import deepcopy
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.refrigeration.defrost_cooler import transition
from fn_engine.refrigeration.multi_cooler_example import multi_cooler_example
from fn_engine.sessions import create_session
from fn_engine.solver import SolveFailed


def project():
    p=multi_cooler_example()
    for i in p.instances:
        if i.id=='CoolerB':
            i.module_id='defrost_air_cooler'
            i.parameters.update(defrost_duration_s=12.,drip_duration_s=7.,defrost_room_fraction=.6)
    p.modules=[m for key,m in catalog_map().items() if key in {i.module_id for i in p.instances}]
    p.solver.dynamic_step_s=10.
    return p


def test_stage_edges_are_pure_and_requests_do_not_repeat():
    p={'defrost_request':1.,'defrost_duration_s':12.,'drip_duration_s':7.}
    s={'mode':0,'since':0.,'count':0,'requested':False}
    first=transition(s,p,5.); assert s['mode']==0 and first['mode']==1
    assert transition(first,p,17.)['mode']==2
    end=transition(first,p,24.); assert end['mode']==0 and end['count']==1
    assert transition(end,p,30.)['mode']==0
    reset=transition(end,p|{'defrost_request':0.},30.)
    assert transition(reset,p,31.)['mode']==1


def test_defrost_exact_heat_integral_and_other_cooler_keeps_running():
    session=create_session(compile_project(project()),60.,5.)
    try:
        session.initialize(); session.set_parameter('CoolerB','defrost_request',1.)
        frames=[session.advance() for _ in range(5)]
        v=frames[-1].variables
        assert v['CoolerB.state.heater_energy_j']==pytest.approx(1500.*12.)
        assert v['CoolerB.state.defrost_count']==1 and v['CoolerB.state.defrost_mode']==0
        first=frames[0].variables
        assert first['CoolerB.supply_mass_flow_kg_s']==0. and first['CoolerB.fan_power_w']==0.
        assert first['Cooler.supply_mass_flow_kg_s']==pytest.approx(first['Pump.mass_flow_kg_s'])
        assert first['CoolerB.room_cooling_w']==-900. and first['CoolerB.refrigerant_heat_w']==600.
        assert abs(frames[-1].metrics['energy_residual_j'])<.05
        expected=sum(value for key,value in first.items() if '.param.' not in key and key.endswith(('.electric_power_w','.fan_power_w','.heater_power_w')))
        assert frames[0].metrics['electric_power_w']==pytest.approx(expected)
    finally:session.close()


def test_failed_defrost_segment_restores_phase_and_counters(monkeypatch):
    session=create_session(compile_project(project()),30.,5.)
    try:
        session.initialize(); session.set_parameter('CoolerB','defrost_request',1.)
        old=deepcopy(session.defrost_states); energy=dict(session.counters)
        def failed(step):raise RuntimeError('injected physics failure')
        monkeypatch.setattr(session,'_integrate',failed)
        with pytest.raises(SolveFailed): session.advance()
        assert session.time==0. and session.defrost_states==old and session.counters==energy
    finally:session.close()


def test_all_defrost_branches_require_stopped_pump():
    p=project(); next(i for i in p.instances if i.id=='Cooler').parameters['supply_valve_ratio']=0.
    session=create_session(compile_project(p),30.,5.)
    try:
        session.initialize(); session.set_parameter('CoolerB','defrost_request',1.)
        with pytest.raises(SolveFailed) as exc:session.advance()
        assert exc.value.diagnostic.code=='DEFROST_PUMP_NO_OUTLET'
        assert session.time==0.
    finally:session.close()
