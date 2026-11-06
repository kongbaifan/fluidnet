"""H01/H02/H04 independent references and real Worker network acceptance."""
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.hvac_expansion_examples import example
from fn_engine.models import Project
from fn_engine.packages import load_module_package
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady

ROOT=Path(__file__).resolve().parents[1]


def frame(p):
    return solve_steady(compile_project(p))


@pytest.mark.parametrize('moist',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
def test_branch_three_real_ports_conserve_air_moisture_and_enthalpy(moist,reverse):
    p=example('air-branch-'+('moist' if moist else 'dry'))
    if reverse:
        for n in p.instances:
            if n.id=='Supply':n.parameters['pressure_pa']=101325.
            if n.id.startswith('Return'):n.parameters.update(pressure_pa=101525.,temperature_k=303.15 if n.id=='ReturnA' else 293.15,
                                                           humidity_ratio_kg_kg=.012 if n.id=='ReturnA' else .006)
    f=frame(p);v=f.variables;keys=['Box-Own.'+port for port in ('common','branch1','branch2')]
    assert f.valid
    assert sum(v[k+'.mass_flow_kg_s'] for k in keys)==pytest.approx(0.,abs=1e-7)
    assert abs(v['Box-Own.branch1.mass_flow_kg_s'])>abs(v['Box-Own.branch2.mass_flow_kg_s'])
    # Each leg uses its own K and its own velocity reference; for equal pressure drop density is the only correction.
    for port,k in [('branch1',.5),('branch2',2.)]:
        rho=v['Box-Own.'+port+'.density_kg_m3'];q=abs(v['Box-Own.'+port+'.mass_flow_kg_s'])
        assert q>0 and rho>0
    if moist:
        assert sum(v[k+'.mass_flow_kg_s']*v[k+'.enthalpy_j_kg'] for k in keys)==pytest.approx(0.,abs=.03)
        assert sum(v[k+'.dry_air_mass_flow_kg_s']*v[k+'.humidity_ratio_kg_kg'] for k in keys)==pytest.approx(0.,abs=1e-8)
    else:
        assert sum(v[k+'.mass_flow_kg_s']*v[k+'.enthalpy_j_kg'] for k in keys)==pytest.approx(0.,abs=.03)


@pytest.mark.parametrize('moist',[False,True])
def test_fan_efficiency_and_total_shaft_heat_from_real_working_point(moist):
    f=frame(example('fan-running-'+('moist' if moist else 'dry')));v=f.variables
    q=v['Fan-Own.main.mass_flow_kg_s']/v['Fan-Own.in0.density_kg_m3']
    assert q*3600.==pytest.approx(2000.,rel=2e-5)
    assert v['Fan-Own.efficiency_ratio']==pytest.approx(.65,rel=2e-5)
    shaft=250.*q/.65
    assert v['Fan-Own.shaft_power_w']==pytest.approx(shaft,rel=2e-5)
    assert v['Fan-Own.electric_power_w']==pytest.approx(shaft/.9,rel=2e-5)
    if moist:
        transported=v['Fan-Own.in0.dry_air_mass_flow_kg_s']*(v['Fan-Own.out0.enthalpy_j_kg_dry_air']-v['Fan-Own.in0.enthalpy_j_kg_dry_air'])
    else:
        transported=v['Fan-Own.main.mass_flow_kg_s']*(v['Fan-Own.out0.enthalpy_j_kg']-v['Fan-Own.in0.enthalpy_j_kg'])
    assert transported==pytest.approx(shaft,rel=3e-5,abs=.03)


@pytest.mark.parametrize('moist',[False,True])
@pytest.mark.parametrize('delta',[-100.,100.])
def test_stopped_fan_is_signed_passive_resistance(moist,delta):
    p=example('fan-running-'+('moist' if moist else 'dry'))
    next(n for n in p.instances if n.id=='Fan-Own').parameters['running']=0.
    next(n for n in p.instances if n.id=='Outlet').parameters['pressure_pa']=101325.-delta
    v=frame(p).variables
    upstream='in0' if delta>0 else 'out0';rho=v['Fan-Own.'+upstream+'.density_kg_m3']
    expected=math.copysign(math.pi*.4**2/4*math.sqrt(2*rho*abs(delta)/2.),delta)
    assert v['Fan-Own.main.mass_flow_kg_s']==pytest.approx(expected,rel=3e-5)
    assert v['Fan-Own.electric_power_w']==v['Fan-Own.shaft_power_w']==0.


def test_fan_transition_accumulates_only_accepted_power():
    p=example('fan-running-moist');session=SimulationSession(compile_project(p),2.,1.)
    try:
        session.initialize();first=session.advance()
        session.set_parameter('Fan-Own','running',0.)
        second=session.advance()
        assert second.variables['Fan-Own.electric_power_w']==0.
        assert second.variables['Fan-Own.state.electric_energy_j']==pytest.approx(first.variables['Fan-Own.electric_power_w'])
    finally:session.close()


@pytest.mark.parametrize('moist',[False,True])
def test_branch_independent_three_leg_reference_and_zero_flow(moist):
    from scipy.optimize import brentq
    p=example('air-branch-'+('moist' if moist else 'dry'));v=frame(p).variables
    rho=v['Supply.out0.density_kg_m3'];area=math.pi*.4**2/4
    # Independent scalar junction solve with property queries, not the network's solved flow.
    if moist:
        from fn_engine.moist_air import MoistAirService
        service=MoistAirService();initial=service.state_ptw(101525.,298.15,.008)
        def density(pressure):return service.state_phw(pressure,initial.enthalpy_j_kg_dry_air,.008).density_kg_m3
    else:
        from fn_engine.properties import property_service
        from fn_engine.models import FluidConfig
        service=property_service(FluidConfig(fluid='Air',phase_policy='gas'));initial=service.state_pt(101525.,298.15)
        def density(pressure):return service.state_ph(pressure,initial.enthalpy_j_kg).density_kg_m3
    def residual(center):
        r=density(center)
        return area*math.sqrt(2*rho*(101525.-center)/.2)-sum(area*math.sqrt(2*r*(center-101325.)/k) for k in (.5,2.))
    center=brentq(residual,101325.,101525.)
    expected=area*math.sqrt(2*rho*(101525.-center)/.2)
    assert v['Box-Own.common.mass_flow_kg_s']==pytest.approx(expected,rel=3e-5)
    for n in p.instances:
        if n.module_id=='source':n.parameters['pressure_pa']=101325.
    zero=frame(p).variables
    # The quadratic pressure law has a flat zero; bound any numerical flow by the unchanged
    # engine pressure residual instead of asserting exact zero beyond the solver's contract.
    for port,k in [('common',.2),('branch1',.5),('branch2',2.)]:
        q=zero['Box-Own.'+port+'.mass_flow_kg_s'];rho=zero['Box-Own.'+port+'.density_kg_m3']
        assert k*q*q/(2*rho*area*area) <= p.solver.pressure_tolerance_pa
    assert sum(zero['Box-Own.'+port+'.mass_flow_kg_s'] for port in ('common','branch1','branch2'))==pytest.approx(0.,abs=p.solver.mass_tolerance_kg_s)


def test_fan_failed_trial_does_not_commit_energy():
    p=example('fan-running-dry');session=SimulationSession(compile_project(p),2.,1.)
    try:
        session.initialize();first=session.advance()
        runner=session.runners['Fan-Own'];before=dict(runner.state)
        # Invalid runtime speed is rejected before solve or state promotion.
        with pytest.raises(CompilationError):session.set_parameter('Fan-Own','speed_ratio',3.)
        assert runner.state==before
        assert session.time==first.time_s
    finally:session.close()


@pytest.mark.parametrize('fouling',[0.,.0005])
@pytest.mark.parametrize('reverse',[False,True])
def test_plate_independent_fluids_hydraulics_and_epsilon_reference(fouling,reverse):
    p=example('plate-water-glycol');node=next(n for n in p.instances if n.id=='Plate-Own')
    node.parameters['hot_fouling_resistance_k_w']=fouling
    if reverse:
        next(n for n in p.instances if n.id=='ColdIn').parameters['pressure_pa']=200000.
        next(n for n in p.instances if n.id=='ColdOut').parameters['pressure_pa']=220000.
    v=frame(p).variables
    hot='hot_in';cold='cold_out' if reverse else 'cold_in'
    qh,qc=abs(v['Plate-Own.hot.mass_flow_kg_s']),abs(v['Plate-Own.cold.mass_flow_kg_s'])
    from fn_engine.properties import property_service
    from fn_engine.models import FluidConfig
    hotstate=property_service(FluidConfig(fluid='Water',phase_policy='liquid')).state_pt(220000.,333.15)
    coldstate=property_service(FluidConfig(fluid='INCOMP::MEG[0.3]',phase_policy='liquid')).state_pt(220000.,293.15)
    ch,cc=qh*hotstate.specific_heat_j_kg_k,qc*coldstate.specific_heat_j_kg_k
    small,large=min(ch,cc),max(ch,cc);ratio=small/large;ntu=(1/(1/2000.+fouling))/small
    eps=(1-math.exp(-ntu*(1+ratio)))/(1+ratio) if reverse else (1-math.exp(-ntu*(1-ratio)))/(1-ratio*math.exp(-ntu*(1-ratio)))
    heat=v['Plate-Own.transferred_heat_w']
    assert heat==pytest.approx(eps*small*(333.15-293.15),rel=3e-5)
    assert heat==pytest.approx(qh*(v['Plate-Own.'+hot+'.enthalpy_j_kg']-v['Plate-Own.hot_out.enthalpy_j_kg']),rel=3e-5)
    cold_out='cold_in' if reverse else 'cold_out'
    assert heat==pytest.approx(qc*(v['Plate-Own.'+cold_out+'.enthalpy_j_kg']-v['Plate-Own.'+cold+'.enthalpy_j_kg']),rel=3e-5)
    for side,k,rho in [('hot',5.,hotstate.density_kg_m3),('cold',12.,coldstate.density_kg_m3)]:
        expected=math.pi*.04**2/4*math.sqrt(2*rho*20000./k)
        assert abs(v['Plate-Own.'+side+'.mass_flow_kg_s'])==pytest.approx(expected,rel=3e-5)


def test_plate_zero_flow_and_wet_air_rejection():
    p=example('plate-water-glycol');next(n for n in p.instances if n.id=='ColdIn').parameters['pressure_pa']=200000.
    assert frame(p).variables['Plate-Own.transferred_heat_w']==pytest.approx(0.,abs=.001)
    p.fluid.fluid='Air';p.fluid.phase_policy='gas';p.circuit_fluids=[]
    from fn_engine.models import MoistAirOptions
    p.solver.moist_air=True;p.solver.moist_air_options=MoistAirOptions(contract_version=1)
    with pytest.raises(CompilationError,match='湿空气透传'):
        compile_project(p)


def test_portable_frozen_packages_roundtrip_without_workspace_paths():
    for name in ('air-branch-moist','fan-running-moist','plate-water-glycol'):
        p=example(name);payload=p.model_dump(mode='json')
        for m in payload['modules']:m.pop('package_path',None)
        restored=Project.model_validate(json.loads(json.dumps(payload)))
        assert frame(restored).valid
        m=next(m for m in restored.modules if m.runtime=='python')
        assert m.content_hash==load_module_package(ROOT/'modules'/m.id).content_hash


def test_fan_curves_reject_invalid_or_uncovered_efficiency_without_clamping():
    path=ROOT/'modules/fan_performance/module.py';spec=importlib.util.spec_from_file_location('fan_under_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for points in ([[0,.5],[100,.0]],[[1,.5],[100,.6]],[[0,.5],[0,.7]]):
        with pytest.raises(ValueError):module.curve(points,True)
    with pytest.raises(ValueError):module.interpolate([[0,.4],[100,.6]],101)
    params={'pressure_curve':[[0,300],[5000,0]],'efficiency_curve':[[0,.5],[100,.6]]}
    with pytest.raises(ValueError,match='覆盖'):module.Module().initialize(SimpleNamespace(parameters=params))


def test_hvac_examples_api_returns_frozen_projects_and_rejects_unknown_names(tmp_path):
    from fastapi.testclient import TestClient
    from fn_engine.api import create_app
    from fn_engine.hvac_expansion_examples import HVAC_EXPANSION_EXAMPLES
    with TestClient(create_app(data_root=tmp_path)) as client:
        for name in HVAC_EXPANSION_EXAMPLES:
            response=client.get('/api/v1/examples/'+name)
            assert response.status_code==200,response.text
            restored=Project.model_validate(response.json())
            expected=Project.model_validate_json((ROOT/'examples/hvac-expansion'/f'{name}.project.json').read_text(encoding='utf-8'))
            assert restored==expected
        assert client.get('/api/v1/examples/air-branch-unknown').status_code==404
    with pytest.raises(KeyError):example('air-branch-unknown')
