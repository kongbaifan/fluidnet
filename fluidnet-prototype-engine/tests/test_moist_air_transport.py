"""N 类：全网边界独立核算、公共流量、反流和合同拒绝。"""
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import ModuleInstance
from fn_engine.solver import solve_steady
from test_moist_air_phase2 import PA, air_project, boundary, coil_project, humidifier_project, link


@pytest.mark.parametrize('project',[
    coil_project({'coil_surface_temperature_k':285.15,'bypass_factor':.15,'loss_coefficient':5.}),
    humidifier_project({'mode':'isothermal','moisture_addition_kg_kg':.003,'loss_coefficient':5.})])
def test_independent_boundary_water_and_energy(project):
    frame=solve_steady(compile_project(project)); v=frame.variables
    water=energy=0.
    for inst in project.instances:
        if inst.module_id == 'source':
            key=inst.id+'.out0.'
            # 边界端口流入设备为正，因此对网络输入取负号。
            water-=v[key+'water_vapor_mass_flow_kg_s']
            energy-=v[key+'mass_flow_kg_s']*v[key+'enthalpy_j_kg']
    if 'C1.condensate_kg_s' in v:
        water-=v['C1.condensate_kg_s']
        energy+=v['C1.heat_w']-v['C1.condensate_enthalpy_flow_w']
        assert v['C1.inlet_mass_flow_kg_s'] > v['C1.outlet_mass_flow_kg_s']
    else:
        water+=v['H1.moisture_addition_kg_s']; energy+=v['H1.heat_w']
        assert v['H1.inlet_mass_flow_kg_s'] < v['H1.outlet_mass_flow_kg_s']
    assert water == pytest.approx(0,abs=1e-9)
    assert energy == pytest.approx(0,abs=1e-3)
    assert frame.solve_summary['continuity_basis'] == 'dry_air'


def test_reverse_duct_uses_actual_upstream():
    catalog=catalog_map()
    project=air_project([boundary('B1',PA,293.15,.005),boundary('B2',PA+100,303.15,.012),
                         ModuleInstance(id='D',name='反流',module_id='duct')],
                        [link('a',('B1','out0'),('D','in0')),link('b',('D','out0'),('B2','out0'))],
                        [catalog['source'],catalog['duct']])
    v=solve_steady(compile_project(project)).variables
    assert v['D.mass_flow_kg_s'] < 0
    assert v['D.in0.humidity_ratio_kg_kg'] == pytest.approx(.012)
    assert v['B1.out0.humidity_ratio_kg_kg'] == pytest.approx(.012)


def test_legacy_contract_requires_explicit_migration():
    project=coil_project({})
    project.solver.moist_air_options=None
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == 'AIR_CONTRACT_VERSION_REQUIRED'
