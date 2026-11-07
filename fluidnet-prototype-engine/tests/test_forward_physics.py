"""Independent geometry/energy checks and real accepted-state networks for S5/S6."""
import math
from copy import deepcopy

import pytest
from scipy.integrate import quad

from fn_engine.compiler import compile_project, CompilationError
from fn_engine.models import Project, ModuleInstance, ModuleTestRequest
from fn_engine.sessions import create_session
from fn_engine.refrigeration.forward_examples import (headed_example,manifold_example,tube_bundle_example,coil_intercooler_example,coupled_buffer_example)
from fn_engine.refrigeration.vessel_geometry import headed_volume,headed_fraction,headed_height_ratio


@pytest.mark.parametrize('fraction',[.01,.1,.25,.5,.9,.99])
def test_headed_volume_independent_vertical_slice_integral(fraction):
    d,l=1.4,3.;r=d/2;h=fraction*d
    volume=quad(lambda y:2*l*math.sqrt(max(0.,r*r-(y-r)**2))+math.pi*max(0.,r*r-(y-r)**2),0,h,epsabs=1e-10)[0]
    assert headed_fraction(fraction,d,l)*headed_volume(d,l)==pytest.approx(volume,rel=1e-9)
    assert headed_height_ratio(volume/headed_volume(d,l),d,l)==pytest.approx(fraction,abs=1e-9)


def test_headed_tap_static_head_changes_real_valve_flow_and_preserves_energy():
    p=headed_example();session=create_session(compile_project(p),.2,.1)
    try:
        f=session.initialize();g=session.advance();v=f.variables
        p0=v['High.state.pressure_pa'];rho=v['High.liquid_density_kg_m3'];h=v['High.state.level_m']-.1
        assert v['High.tap0.pressure_pa']-p0==pytest.approx(rho*9.80665*h,rel=1e-9)
        assert v['High.tap0.submerged']==1 and v['High.tap2.submerged']==0
        assert abs(g.metrics['energy_residual_w'])<.01
        before=deepcopy(session.energies)
        session.network.parameters['High']['tap0_height_ratio']=.95;session._cache=None
        with pytest.raises(Exception,match='需要liquid'):session.advance()
        assert session.energies==before and session.time==.1
    finally:session.close()


@pytest.mark.parametrize('count',[1,6,12])
def test_heat_tree_has_one_room_capacity_and_each_leaf_once(count):
    p=manifold_example(count);network=compile_project(p)
    assert len(network.room_cooler_groups['Room'])==count
    session=create_session(network,.2,.1)
    try:
        f=session.initialize();v=f.variables
        expected=sum(v[f'Cooler{i}.room_cooling_w'] for i in range(count))
        assert v['Room.cooling_power_w']==pytest.approx(expected)
        assert len(session.temperatures)==1
        assert abs(session.advance().metrics['energy_residual_w'])<.01
    finally:session.close()


def test_empty_or_unrooted_heat_manifold_rejected():
    p=manifold_example();p.connections=[c for c in p.connections if c.source.instance_id!='Cooler0' or c.source.port_id!='heat']
    with pytest.raises(CompilationError):compile_project(p)


@pytest.mark.parametrize('factory',[tube_bundle_example,coil_intercooler_example])
def test_finite_tube_heat_changes_stream_h_and_unique_shell_inventory(factory):
    p=factory();session=create_session(compile_project(p),.2,.1)
    iid='Subcooler' if factory==tube_bundle_example else 'Coil'
    shell='Shell' if factory==tube_bundle_example else 'Intermediate'
    try:
        f=session.initialize();v=f.variables;m=v[iid+'.mass_flow_kg_s']
        q=m*(v[iid+'.inlet_enthalpy_j_kg']-v[iid+'.outlet_enthalpy_j_kg'])
        assert q>0 and q==pytest.approx(v[iid+'.shell_heat_w'])
        assert v[iid+'.shell_mass_kg']==v[shell+'.state.mass_kg']
        assert v[iid+'.outlet_temperature_k']>v[shell+'.state.temperature_k']
        old=session.energies[shell];g=session.advance();assert session.energies[shell]!=old
        assert abs(g.metrics['energy_residual_w'])<.02
    finally:session.close()


def test_tube_zero_valve_flow_has_no_phantom_heat():
    p=tube_bundle_example();next(i for i in p.instances if i.id=='Valve').parameters['opening_ratio']=0.
    s=create_session(compile_project(p),.1,.1)
    try:
        v=s.initialize().variables;assert v['Subcooler.shell_heat_w']==0.
    finally:s.close()


def test_coupled_buffer_implicit_h_energy_and_failed_step_rollback():
    p=coupled_buffer_example();s=create_session(compile_project(p),.3,.1)
    try:
        a=s.initialize();old=s.temperatures['Buffer'];b=s.advance();h=s.temperatures['Buffer'];r=s._current();w=r['fluid_result'];j=next(j for j,x in enumerate(s.network.fluid_network.branches) if x.instance_id=='Buffer')
        mass=abs(w.hydraulic.flows[j]);hin=w.thermal.node_states[w.thermal.upstream[j]].enthalpy_j_kg
        assert 100.*(h-old)/.1==pytest.approx(mass*(hin-h),abs=.02)
        assert abs(b.metrics['energy_residual_w'])<.02
        saved=deepcopy((s.masses,s.energies,s.temperatures,s.counters));s.network.parameters['Buffer']['maximum_temperature_k']=280.;s._cache=None
        with pytest.raises(Exception):s.advance()
        assert (s.masses,s.energies,s.temperatures,s.counters)==saved and s.time==.1
        assert a.variables['Buffer.state.temperature_k']==pytest.approx(293.15,abs=1e-6)
    finally:s.close()


def test_legacy_storage_still_rejected_and_explicit_multivessel_relations_work():
    p=coupled_buffer_example();p.coupling_mode='legacy'
    with pytest.raises(CompilationError,match='无储热'):compile_project(p)
    from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
    p=thermal_coupling_example(topology='parallel');p.coupling_mode='storage_v1';p.thermal_couplings[1].refrigerant_vessel_id='HP1'
    s=create_session(compile_project(p),.1,.1)
    try:
        f=s.initialize();assert 'coupling.HX2.heat_w' in f.variables
        assert abs(s.advance().metrics['energy_residual_w'])<.02
    finally:s.close()


def test_closed_refrigeration_groups_duplicate_independent_states_and_roundtrip():
    from fn_engine.composites import module_from_group
    from fn_engine.bench import run_module_test
    p=headed_example();definition=module_from_group(p,[i.id for i in p.instances],'cold_pack','制冷设备组')
    assert 'composite.refrigeration.v1' in definition.sdk.capabilities
    assert not definition.ports
    result=run_module_test(ModuleTestRequest(module=definition,fluid=p.fluid,duration_s=.1,dt_s=.1))
    assert result.frame.valid
    group=Project(id='two-packs',name='two',fluid=p.fluid,modules=[definition],instances=[ModuleInstance(id=k,module_id=definition.id,name=k) for k in ('A','B')],connections=[])
    group=Project.model_validate_json(group.model_dump_json());s=create_session(compile_project(group),.2,.1)
    try:
        a=s.initialize();assert a.variables['A.state.Room.temperature_k']==a.variables['B.state.Room.temperature_k']
        s.set_parameter('A','Room_heat_input_w',7000.)
        b=s.advance();assert b.variables['A.state.Room.temperature_k']!=b.variables['B.state.Room.temperature_k']
        assert abs(b.metrics['energy_residual_w'])<.02
    finally:s.close()


def test_three_couplings_require_explicit_mode_and_two_shell_targets_conserve():
    from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
    from fn_engine.refrigeration.forward_examples import link,finish
    from fn_engine.models import ThermalCoupling,Endpoint
    p=thermal_coupling_example(topology='parallel');p.coupling_mode='storage_v1'
    p.instances.append(ModuleInstance(id='ThirdCoil',name='third',module_id='pipe',parameters={'length_m':1.,'diameter_m':.04}))
    edge=next(c for c in p.connections if c.source.instance_id=='HX_W');target=edge.target;edge.target=Endpoint(instance_id='ThirdCoil',port_id='in0');link(p,('ThirdCoil','out0'),(target.instance_id,target.port_id))
    p.thermal_couplings.append(ThermalCoupling(id='HX3',fluid_instance_id='ThirdCoil',refrigerant_vessel_id='HP1',ua_w_k=50.))
    p=finish(p,'three-coils');s=create_session(compile_project(p),.2,.1)
    try:
        s.initialize();f=s.advance();assert abs(f.metrics['energy_residual_w'])<.02
        assert all(f.variables[f'coupling.HX{i}.energy_residual_w']==0. for i in (1,2,3))
    finally:s.close()
    p.coupling_mode='legacy'
    with pytest.raises(Exception):Project.model_validate_json(p.model_dump_json())


def test_new_storage_time_step_refinement_changes_less_and_frozen_roundtrip():
    from fn_engine.models import Project
    def run(dt):
        p=coupled_buffer_example();p.solver.dynamic_step_s=dt;p=Project.model_validate_json(p.model_dump_json());s=create_session(compile_project(p),1.,dt)
        try:
            s.initialize()
            while not s.done:s.advance()
            return s.temperatures['Buffer']
        finally:s.close()
    a,b,c=run(.5),run(.25),run(.125)
    assert abs(c-b)<abs(b-a)


def test_refrigeration_group_publication_reload_and_legacy_group_refusal(tmp_path):
    from fn_engine.composites import module_from_group
    from fn_engine.packages import ModuleStore
    from fn_engine.models import ModuleSaveRequest,ModuleTestConditions
    p=headed_example();d=module_from_group(p,[i.id for i in p.instances],'closed_cold_pack','Closed cold pack')
    store=ModuleStore(tmp_path/'seeds',tmp_path/'store')
    release=store.save(ModuleSaveRequest(module=d,expected_latest_version=0,test=ModuleTestConditions(fluid=p.fluid,duration_s=.1,dt_s=.1)))
    restored=ModuleStore(tmp_path/'seeds',tmp_path/'store').get('closed_cold_pack',1).module
    assert restored.definition_hash==release.module.definition_hash
    old=restored.model_copy(deep=True);old.sdk.api_version='0.5.0';old.sdk.capabilities=['composite.v1']
    project=Project(id='bad',name='bad',fluid=p.fluid,modules=[old],instances=[ModuleInstance(id='Group',module_id=old.id,name='g')],connections=[])
    with pytest.raises(ValueError,match='流体'):compile_project(project)


@pytest.mark.parametrize('factory,keys',[(tube_bundle_example,['Subcooler.shell_heat_w','Subcooler.shell_internal_energy_j']),
    (headed_example,['High.tap0.pressure_pa','High.tap0.submerged']),
    (manifold_example,['HeatRoot.cooling_power_w','HeatRoot.cooler_count']),
    (coupled_buffer_example,['Buffer.state.enthalpy_j_kg','Buffer.state.stored_energy_j'])])
def test_new_physics_csv_and_html_keep_declared_frozen_results(tmp_path,factory,keys):
    from fastapi.testclient import TestClient
    from fn_engine.api import create_app
    with TestClient(create_app(data_root=tmp_path)) as client:
        project=factory();response=client.post('/api/v1/runs',json={'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':.1,'dt_s':.1})
        assert response.status_code==201,response.text
        run=response.json();assert run['status']=='completed',run
        rid=run['run_id'];csv=client.get(f'/api/v1/runs/{rid}/report.csv');html=client.get(f'/api/v1/runs/{rid}/report.html')
        assert csv.status_code==html.status_code==200
        for key in keys:assert key in csv.text
        assert '扩展设备末帧结果' in html.text


def test_closed_group_equivalent_backend_prefix_does_not_rebind_other_fluid():
    from fn_engine.composites import module_from_group
    p=headed_example();d=module_from_group(p,[i.id for i in p.instances],'fluid_prefix_pack','Pure fluid group')
    q=Project(id='prefix',name='prefix',fluid={'fluid':'HEOS::R134a','phase_policy':'any'},modules=[d],instances=[ModuleInstance(id='Group',module_id=d.id,name='g')],connections=[])
    assert compile_project(q).execution_domain=='refrigeration'
    q.fluid.fluid='Ammonia'
    with pytest.raises(ValueError,match='工质'):compile_project(q)
