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


def test_zero_flow_heater_is_rejected_without_fake_flow():
    c=catalog_map()
    project=air_project([boundary('A'),boundary('Z'),ModuleInstance(id='H',module_id='heater',name='零流加热',
                        parameters={'diameter_m':.4,'loss_coefficient':2.,'heat_input_w':100.})],
        [link('a',('A','out0'),('H','in0')),link('z',('H','out0'),('Z','out0'))],[c['source'],c['heater']])
    with pytest.raises(CompilationError) as exc:
        solve_steady(compile_project(project))
    assert exc.value.diagnostic.code=='ZERO_FLOW_HEAT_INPUT'


@pytest.mark.parametrize('speed',[.8,1.2])
def test_new_fan_curve_uses_actual_volume_and_density(speed):
    import numpy as np
    from fn_engine.air_examples import air_example
    project=air_example('ahu-wet')
    next(i for i in project.instances if i.id=='Fan').parameters['speed_ratio']=speed
    values=solve_steady(compile_project(project)).variables
    volume=values['Fan.volume_flow_m3_h']
    rise=np.interp(volume/speed,[0,2000,4000,5000],[300,250,120,0])*speed**2
    assert values['Fan.pressure_rise_pa']==pytest.approx(rise,rel=2e-6)
    assert volume/3600==pytest.approx(values['Fan.mass_flow_kg_s']/values['Fan.in0.density_kg_m3'],rel=1e-8)


def test_circulating_air_without_actual_boundary_supply_has_no_humidity_reference():
    from pathlib import Path
    from fn_engine.packages import load_module_package
    c=catalog_map();fan=load_module_package(Path(__file__).resolve().parents[1]/'modules/fan')
    project=air_project([boundary('A'),ModuleInstance(id='J',module_id='junction',name='参考节点'),
        ModuleInstance(id='F',module_id='fan',name='循环风机'),ModuleInstance(id='D',module_id='duct',name='回风管')],
        [link('a',('A','out0'),('J','in0')),link('b',('J','out0'),('F','in0')),
         link('c',('F','out0'),('D','in0')),link('d',('D','out0'),('J','out1'))],
        [c['source'],c['junction'],c['duct'],fan])
    with pytest.raises(CompilationError) as exc:
        solve_steady(compile_project(project))
    assert exc.value.diagnostic.code=='MOISTURE_REFERENCE_MISSING'
