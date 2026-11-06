"""Public device-map example: derive a balanced initial point without case-ID logic."""
from ..catalog import catalog_map
from ..properties import property_service
from .modular_examples import modular_room_example
from .performance_compressor import compressor_point
from . import devices


def performance_example():
    project = modular_room_example()
    catalog = catalog_map()
    nodes = {i.id:i for i in project.instances}
    service = property_service(project.fluid)
    low = service.state_tq(nodes['Low'].parameters['temperature_k'],1.)
    high = service.state_tq(nodes['High'].parameters['temperature_k'],0.)
    old_parameters = {p.id:p.default for p in catalog['refrigerant_compressor'].parameters} | nodes['Compressor'].parameters
    old = devices.compressor_point(service, old_parameters, low.pressure_pa, high.pressure_pa)
    node = nodes['Compressor']
    node.module_id, node.name = 'performance_compressor', '性能曲线压缩机'
    params = {p.id:p.default for p in catalog[node.module_id].parameters}
    point = compressor_point(service, params, low.pressure_pa, high.pressure_pa)
    displacement = params['displacement_m3_s']*old['mass_flow_kg_s']/point['mass_flow_kg_s']
    node.parameters = {'displacement_m3_s':float(format(displacement,'.10g')), 'load_ratio':.75, 'speed_ratio':1.}
    point = compressor_point(service, params | node.parameters, low.pressure_pa, high.pressure_pa)
    cooling = old['mass_flow_kg_s']*(low.enthalpy_j_kg-high.enthalpy_j_kg)
    nodes['Condenser'].parameters['ua_w_k'] = float(format((cooling+point['shaft_power_w'])/15.,'.10g'))
    project.modules = [m for key,m in catalog.items() if key in {i.module_id for i in project.instances}]
    project.id, project.name = 'modular-performance-compressor', '设备性能 · 曲线压缩机单库'
    project.description = '教学性能曲线，非厂家数据；饱和吸气，工况域外明确拒绝；初态按5kW库负荷平衡，无控制脚本。'
    return project
