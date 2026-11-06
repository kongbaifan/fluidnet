"""An independently sized DX branch; no low-pressure storage vessel or fictitious saturation suction."""
import math
from ..catalog import catalog_map
from ..models import Connection,Endpoint
from ..properties import property_service
from .modular_examples import modular_room_example
from .cycle import compress


def dx_example():
    project=modular_room_example();catalog=catalog_map();service=property_service(project.fluid)
    high=service.state_tq(308.15,0.);vapor=service.state_tq(248.15,1.)
    suction=service.state_pt(vapor.pressure_pa,251.15)
    mass=5000./(suction.enthalpy_j_kg-high.enthalpy_j_kg)
    displacement=mass/(.75*.8*suction.density_kg_m3)
    kv=mass*3600./(.5*math.sqrt(1000.*high.density_kg_m3*(high.pressure_pa-vapor.pressure_pa)/1e5))
    ua=mass*(vapor.enthalpy_j_kg-high.enthalpy_j_kg)/7.-math.log1p(-3./7.)*mass*vapor.specific_heat_j_kg_k
    _,h2=compress(service,suction,high.pressure_pa,.72);shaft=mass*(h2-suction.enthalpy_j_kg)
    project.instances=[i for i in project.instances if i.id not in ('Low','Pump')]
    nodes={i.id:i for i in project.instances}
    nodes['Compressor'].module_id='dx_compressor';nodes['Compressor'].parameters={'displacement_m3_s':displacement,'load_ratio':.75}
    nodes['Valve'].module_id='dx_expansion_valve';nodes['Valve'].parameters={'kv_m3_h':kv,'opening_ratio':.5}
    nodes['Cooler'].module_id='dx_evaporator';nodes['Cooler'].name='真实过热DX蒸发器';nodes['Cooler'].parameters={'ua_w_k':ua,'minimum_superheat_k':.5,'minimum_evaporating_temperature_k':233.15}
    nodes['Condenser'].parameters['ua_w_k']=(5000.+shaft)/15.
    pairs=[(('High','liquid'),('Valve','in0')),(('Valve','out0'),('Cooler','in0')),(('Cooler','out0'),('Compressor','in0')),
           (('Compressor','out0'),('Condenser','in0')),(('Condenser','out0'),('High','in0')),(('Cooler','heat'),('Room','heat'))]
    project.connections=[Connection(id=f'dx-{i}',source=Endpoint(instance_id=a[0],port_id=a[1]),target=Endpoint(instance_id=b[0],port_id=b[1])) for i,(a,b) in enumerate(pairs)]
    project.modules=[m for key,m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.id,project.name='modular-dx-superheat','DX三模块 · 实际出口过热'
    project.description='阀、两区DX蒸发器和真实吸气压缩机联立蒸发压力；冷媒低压支路准稳态无储量，高压容器/库房动态。设计过热3K、库负荷5kW；无厂家标定。'
    return project
