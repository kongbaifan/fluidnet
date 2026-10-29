"""R 类：独立散湿/一阶解析解、网络动态和拒绝子步事务。"""
import pytest

from fn_engine.air_room import build_spec, evaluate_room
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import ModuleInstance
from fn_engine.moist_air import AirPropertyError, MoistAirService
from fn_engine.simulation import SimulationSession
from test_moist_air_phase2 import PA, air_project, boundary, link


def room_parameters(**updates):
    return {p.id:p.default for p in catalog_map()['air_room'].parameters} | {
        'envelope_ua_w_k':0.,'sensible_load_w':0.,'additional_heat_capacity_j_k':0.} | updates


def room_project():
    c=catalog_map()
    return air_project([boundary('B1',PA+100,293.15,.006),boundary('B2',PA,293.15,.006),
        ModuleInstance(id='D1',module_id='duct',name='送风'),ModuleInstance(id='D2',module_id='duct',name='回风'),
        ModuleInstance(id='Room',module_id='air_room',name='房间')],
        [link('a',('B1','out0'),('D1','in0')),link('b',('D1','out0'),('Room','supply_in')),
         link('c',('Room','return_out'),('D2','in0')),link('d',('D2','out0'),('B2','out0'))],
        [c['source'],c['duct'],c['air_room']])


def test_closed_room_constant_moisture_is_exact():
    params=room_parameters(moisture_load_kg_s=1e-5)
    spec=build_spec('R',params); old=spec.initial_state; service=MoistAirService()
    for _ in range(10):
        old=evaluate_room(spec,params,PA,0,0,0,old,1.,service).state
    assert spec.dry_air_mass_kg*(old.humidity_ratio_kg_kg-spec.initial_state.humidity_ratio_kg_kg) == pytest.approx(1e-4,abs=1e-10)
    with pytest.raises(AirPropertyError) as exc:
        evaluate_room(spec,params,PA,0,0,0,None,None,service)
    assert exc.value.code == 'AIR_ROOM_NO_STEADY_STATE'


def test_zero_ventilation_room_in_real_network_accumulates_moisture():
    project=room_project()
    next(i for i in project.instances if i.id=='B1').parameters['pressure_pa']=PA
    session=SimulationSession(compile_project(project),2.,1.)
    try:
        initial=session.initialize()
        session.advance();final=session.advance()
        assert final.variables['D1.dry_air_mass_flow_kg_s']==pytest.approx(0,abs=1e-12)
        assert final.variables['Room.state.water_vapor_mass_kg']-initial.variables['Room.state.water_vapor_mass_kg']==pytest.approx(.0002,abs=1e-9)
        assert abs(final.metrics['moisture_residual_kg_s'])<1e-9
    finally:
        session.close()


def test_ventilated_room_matches_backward_euler_moisture():
    params=room_parameters();spec=build_spec('R',params);service=MoistAirService()
    supply=service.state_ptw(PA,293.15,.006)
    dt=10.;m=1.2
    result=evaluate_room(spec,params,PA,m,m*supply.enthalpy_j_kg_dry_air,m*.006,None,dt,service)
    expected=(spec.dry_air_mass_kg*.010/dt+m*.006+params['moisture_load_kg_s'])/(spec.dry_air_mass_kg/dt+m)
    assert result.state.humidity_ratio_kg_kg == pytest.approx(expected,abs=1e-12)
    assert result.moisture_storage_kg_s == pytest.approx(m*(.006-expected)+params['moisture_load_kg_s'],abs=1e-10)


def test_rejected_substep_does_not_double_room_or_device_ledgers(monkeypatch):
    def run(dt,reject):
        session=SimulationSession(compile_project(room_project()),2.,dt)
        try:
            session.initialize()
            if reject:
                original=session._trial;failed=False
                def trial(h):
                    nonlocal failed
                    result=original(h)
                    if not failed:
                        failed=True
                        raise CompilationError('THERMAL_NOT_CONVERGED','强制拒绝候选')
                    return result
                monkeypatch.setattr(session,'_trial',trial)
            while not session.done: session.advance()
            return session.snapshot()
        finally:
            session.close()
    baseline=run(1.,False);retried=run(2.,True)
    for key in ('Room.state.humidity_ratio_kg_kg','Room.state.temperature_k','Room.state.moisture_added_kg','Room.state.load_energy_j'):
        assert retried.variables[key] == pytest.approx(baseline.variables[key],rel=1e-9,abs=1e-9)
    assert retried.variables['Room.state.moisture_added_kg'] == pytest.approx(.0002)


def test_runtime_boundary_batch_is_atomic():
    session=SimulationSession(compile_project(room_project()),2.,1.)
    try:
        session.initialize()
        with pytest.raises(CompilationError):
            session.write_variables({'B1.param.temperature_k':273.15})
        assert session.network.parameters['B1']['temperature_k']==293.15
        session.write_variables({'B1.param.temperature_k':283.15,'B1.param.humidity_ratio_kg_kg':.003})
        frame=session.advance()
        assert frame.variables['B1.out0.temperature_k']==pytest.approx(283.15)
    finally:
        session.close()


def test_halving_room_step_converges_to_independent_exponential():
    import math
    params=room_parameters();spec=build_spec('R',params);service=MoistAirService()
    supply=service.state_ptw(PA,293.15,.006);flow=1.2;duration=400.
    equilibrium=.006+params['moisture_load_kg_s']/flow
    exact=equilibrium+(.010-equilibrium)*math.exp(-flow*duration/spec.dry_air_mass_kg)
    errors=[]
    for dt in (40.,20.,10.):
        old=spec.initial_state
        for _ in range(int(duration/dt)):
            old=evaluate_room(spec,params,PA,flow,flow*supply.enthalpy_j_kg_dry_air,flow*.006,old,dt,service).state
        errors.append(abs(old.humidity_ratio_kg_kg-exact))
    assert 1.7<errors[0]/errors[1]<2.3
    assert 1.7<errors[1]/errors[2]<2.3


def test_failed_later_step_keeps_accepted_history(monkeypatch):
    from fn_engine.solver import SolveFailed,solve_dynamic
    original=SimulationSession._trial
    def fail_later(self,h):
        if self.time>=1.:
            raise CompilationError('AIR_ROOM_STATE_INFEASIBLE','模拟不可行热湿状态')
        return original(self,h)
    monkeypatch.setattr(SimulationSession,'_trial',fail_later)
    with pytest.raises(SolveFailed) as exc:
        solve_dynamic(compile_project(room_project()),2.,1.)
    assert [frame.time_s for frame in exc.value.frames]==[0.,1.]
    assert exc.value.frames[-1].variables['Room.state.moisture_added_kg']==pytest.approx(.0001)
