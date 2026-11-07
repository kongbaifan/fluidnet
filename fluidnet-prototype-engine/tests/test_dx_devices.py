import pytest
from copy import deepcopy
from CoolProp.CoolProp import PropsSI
from fastapi.testclient import TestClient

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.refrigeration.dx_devices import branch_point,definitions
from fn_engine.refrigeration.modular_examples import modular_room_example
from fn_engine.refrigeration.dx_example import dx_example
from fn_engine.refrigeration.devices import vessel_state,vessel_initial
from fn_engine.refrigeration.cycle import DeviceRangeError
from fn_engine.solver import solve_dynamic,SolveFailed
from fn_engine.sessions import create_session
from fn_engine.api import create_app


def test_dx_evaporator_requires_real_superheat():
    network=compile_project(dx_example());service=property_service(network.project.fluid)
    high=vessel_state(service,network.parameters['High'],*vessel_initial(service,network.parameters['High']))
    result=branch_point(service,high,255.15,network.parameters['Valve'],network.parameters['Cooler'],network.parameters['Compressor'])
    assert result['mass_flow_kg_s']>0. and result['superheat_k']==pytest.approx(3.,abs=1e-5)
    assert result['heat_w']==pytest.approx(5000.,abs=.01)
    ps=result['evaporating_pressure_pa'];hin=result['outlet_enthalpy_j_kg'];pd=high.pressure_pa
    entropy=PropsSI('S','P',ps,'H',hin,'R134a');his=PropsSI('H','P',pd,'S',entropy,'R134a')
    assert result['shaft_power_w']==pytest.approx(result['mass_flow_kg_s']*(his-hin)/network.parameters['Compressor']['isentropic_efficiency'],rel=1e-7)


def test_dx_contract_is_explicitly_separate_from_legacy_path():
    ids={m.id for m in definitions()};assert ids=={'dx_expansion_valve','dx_evaporator','dx_compressor'}
    assert not ids & {m.id for m in catalog_map().values() if m.solver_model in ('refrigerant_compressor','expansion_valve','air_cooler')}


def test_existing_saturated_project_unaffected_by_dx_registration():
    project=modular_room_example(); assert solve_dynamic(compile_project(project),20.,10.)[-1].valid


def test_dx_invalid_stopped_branch_is_clear():
    p={m.id:m for m in definitions()};service=property_service(FluidConfig(fluid='R134a',phase_policy='any'));high=service.state_tq(308.15,0.)
    valve={x.id:x.default for x in p['dx_expansion_valve'].parameters}|{'opening_ratio':.2}
    comp={x.id:x.default for x in p['dx_compressor'].parameters}|{'running':0.}
    with pytest.raises(DeviceRangeError) as exc:branch_point(service,high,278.15,valve,{x.id:x.default for x in p['dx_evaporator'].parameters},comp)
    assert exc.value.code=='DX_OFF_VALVE_OPEN'


def test_dx_network_preserves_mass_and_heat_ledger():
    frames=solve_dynamic(compile_project(dx_example()),30.,10.)
    v=frames[-1].variables
    assert all(f.valid for f in frames)
    assert v['Cooler.superheat_k']==pytest.approx(3.,abs=1e-5)
    assert v['Compressor.inlet_enthalpy_j_kg']==v['Cooler.outlet_enthalpy_j_kg']
    assert v['Cooler.inlet_enthalpy_j_kg']==v['Valve.outlet_enthalpy_j_kg']
    assert v['Room.state.temperature_k']==pytest.approx(255.15,abs=1e-5)
    assert frames[-1].metrics['mass_residual_kg_circuit0']==0.
    assert abs(frames[-1].metrics['energy_residual_j'])<.05


def test_dx_valid_root_near_superheat_boundary_is_not_lost_between_scan_points():
    project=dx_example()
    next(i for i in project.instances if i.id=='Cooler').parameters['minimum_superheat_k']=2.99
    frame=solve_dynamic(compile_project(project),1.,1.)[-1]
    assert frame.valid and frame.variables['Cooler.superheat_k']==pytest.approx(3.,abs=1e-5)


def test_zero_compressor_capacity_requires_closed_dx_valve():
    session=create_session(compile_project(dx_example()),10.,10.)
    try:
        session.initialize();session.set_parameter('Compressor','load_ratio',0.)
        before=deepcopy((session.time,session.masses,session.energies,session.counters))
        with pytest.raises(SolveFailed) as error:session.advance()
        assert error.value.diagnostic.code=='DX_OFF_VALVE_OPEN'
        assert (session.time,session.masses,session.energies,session.counters)==before
    finally:session.close()


def test_dx_valve_feedback_is_real_and_overfeed_failure_does_not_commit():
    session=create_session(compile_project(dx_example()),60.,10.)
    try:
        session.initialize();session.set_parameter('Valve','opening_ratio',.4)
        v=session.advance().variables
        assert v['Cooler.superheat_k']>8.
        old=deepcopy((session.time,session.masses,session.energies,session.temperatures,session.counters))
        session.set_parameter('Valve','opening_ratio',.9)
        with pytest.raises(SolveFailed):session.advance()
        assert (session.time,session.masses,session.energies,session.temperatures,session.counters)==old
    finally:session.close()


def test_dx_closed_valve_and_stopped_compressor_have_zero_cooling():
    session=create_session(compile_project(dx_example()),30.,10.)
    try:
        session.initialize()
        session.write_variables({'Valve.param.opening_ratio':0.,'Compressor.param.running':0.})
        frame=session.advance()
        assert frame.variables['Cooler.heat_w']==0. and frame.variables['Compressor.electric_power_w']==0.
        assert frame.variables['Room.state.temperature_k']>255.15
        assert abs(frame.metrics['energy_residual_j'])<.05
    finally:session.close()


def test_dx_arbitrary_ids_frozen_report_and_restart(tmp_path):
    project=dx_example();mapping={i.id:'User-'+i.id for i in project.instances}
    for i in project.instances:i.id=mapping[i.id]
    for c in project.connections:
        c.source.instance_id=mapping[c.source.instance_id];c.target.instance_id=mapping[c.target.instance_id]
    with TestClient(create_app(data_root=tmp_path)) as client:
        result=client.post('/api/v1/runs',json={'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':10.,'dt_s':10.})
        assert result.status_code==201 and result.json()['status']=='completed',result.text
        rid=result.json()['run_id'];record=client.get('/api/v1/runs/'+rid).json()
        assert 'User-Cooler.superheat_k' in client.get(f'/api/v1/runs/{rid}/report.csv').text
    with TestClient(create_app(data_root=tmp_path)) as client:
        restored=client.get('/api/v1/runs/'+rid).json()
        assert restored['frame']['variables']==record['frame']['variables']
