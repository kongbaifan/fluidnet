import pytest
from CoolProp.CoolProp import PropsSI

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import FluidConfig
from fn_engine.properties import property_service
from fn_engine.refrigeration.performance_compressor import compressor_point, definition, check_operating_point, validate_maps
from fn_engine.refrigeration.performance_example import performance_example
from fn_engine.refrigeration.cycle import DeviceRangeError
from fn_engine.sessions import create_session
from fn_engine.solver import solve_dynamic, SolveFailed


def params():
    return {p.id:p.default for p in definition().parameters}


def test_independent_interpolation_and_thermodynamic_work():
    p = params() | {'isentropic_pressure_curve':[[1.,.8],[9.,.6]], 'volumetric_pressure_curve':[[1.,.9],[9.,.7]],
        'load_factor_curve':[[.2,.8],[1.,1.]], 'speed_factor_curve':[[.2,.8],[1.,1.]], 'load_ratio':.6,'speed_ratio':.6}
    service = property_service(FluidConfig(fluid='R134a',phase_policy='any'))
    ps = PropsSI('P','T',248.15,'Q',1,'R134a'); pd=ps*5
    result = compressor_point(service,p,ps,pd)
    eta_i, eta_v = .7*.9*.9, .8*.9*.9
    density=PropsSI('D','P',ps,'Q',1,'R134a'); h=PropsSI('H','P',ps,'Q',1,'R134a')
    s=PropsSI('S','P',ps,'Q',1,'R134a'); his=PropsSI('H','P',pd,'S',s,'R134a')
    mass=p['displacement_m3_s']*.6*.6*eta_v*density
    assert result['actual_isentropic_efficiency']==pytest.approx(eta_i)
    assert result['mass_flow_kg_s']==pytest.approx(mass)
    assert result['shaft_power_w']==pytest.approx(mass*(his-h)/eta_i,rel=1e-7)
    assert result['electric_power_w']==pytest.approx(result['shaft_power_w']/.92)


@pytest.mark.parametrize('curve', [[], [[1.,.8]], [[2.,.8],[1.,.7]], [[1.,0.],[2.,.8]], [[1.,.8],[2.,float('nan')]]])
def test_invalid_curves_fail_before_network_solve(curve):
    project=performance_example()
    next(i for i in project.instances if i.id=='Compressor').parameters['isentropic_pressure_curve']=curve
    with pytest.raises(CompilationError) as exc: compile_project(project)
    assert exc.value.diagnostic.code=='COMPRESSOR_MAP_INVALID'


def test_probe_continuation_cannot_accept_outside_the_declared_envelope():
    p=params()|{'max_pressure_ratio':3.}
    service=property_service(FluidConfig(fluid='R134a',phase_policy='any'))
    result=compressor_point(service,p,150000.,900000.,check=False)
    with pytest.raises(DeviceRangeError): check_operating_point(p,result)
    for setting in ({'running':0.},{'load_ratio':0.},{'speed_ratio':0.}):
        assert compressor_point(service,p|setting,150000.,900000.)['electric_power_w']==0.
    with pytest.raises(DeviceRangeError) as exc:
        compressor_point(service,params()|{'speed_ratio':.1},150000.,900000.)
    assert exc.value.code=='COMPRESSOR_MAP_RANGE'


def test_network_balance_and_failed_operating_change_preserve_state():
    project=performance_example(); net=compile_project(project)
    frames=solve_dynamic(net,120.,30.)
    assert frames[-1].variables['Room.state.temperature_k']==pytest.approx(255.15,abs=1e-5)
    assert abs(frames[-1].metrics['energy_residual_j'])<.05
    session=create_session(compile_project(project),120.,30.)
    try:
        session.initialize(); session.advance()
        before=(session.time,dict(session.masses),dict(session.energies),dict(session.counters))
        session.set_parameter('Compressor','speed_ratio',.1)
        with pytest.raises(SolveFailed): session.advance()
        assert (session.time,session.masses,session.energies,session.counters)==before
    finally: session.close()
    assert 'speed_ratio' not in {p.id for p in catalog_map()['refrigerant_compressor'].parameters}


def test_repeated_evaluation_is_pure():
    p=params(); service=property_service(FluidConfig(fluid='R134a',phase_policy='any'))
    a=compressor_point(service,p,150000.,900000.)
    assert a==compressor_point(service,p,150000.,900000.)
    validate_maps(p)
