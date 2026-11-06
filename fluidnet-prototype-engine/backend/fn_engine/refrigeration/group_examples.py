"""Three open equipment groups with explicit, reproducible external host connections."""
from ..composites import module_from_group
from .group_testing import replace_with_group
from .modular_examples import modular_room_example


GROUPS = {
    'compressors': ('压缩机组', ['Compressor-1', 'Compressor-2', 'Suction', 'Discharge']),
    'liquid-supply': ('泵与节流供液组', ['Pump', 'Supply', 'Valve']),
    'air-coolers': ('冷风机组', ['Cooler-1', 'Cooler-2', 'Return']),
}


def open_group_example(kind):
    if kind not in GROUPS:
        raise ValueError('开放制冷组示例不存在：'+str(kind))
    name, selected = GROUPS[kind]
    source = modular_room_example(2, 2)
    module = module_from_group(source, selected, 'open_'+kind.replace('-', '_'), name)
    host = replace_with_group(source, selected, module)
    host.id, host.name = 'open-'+kind, name+' · 真实宿主'
    return source, module, host


def grouped_station_example():
    """A complete station assembled from all three groups and external vessels/rooms."""
    source = modular_room_example(2, 2)
    for kind, (name, selected) in GROUPS.items():
        module = module_from_group(source, selected, 'open_'+kind.replace('-', '_'), name)
        source = replace_with_group(source, selected, module, 'Group'+kind.replace('-', ''))
    source.id, source.name = 'open-group-station', '三个设备组搭建制冷站'
    source.selected_variables = ['Groupcompressors.Compressor-1.mass_flow_kg_s',
        'Groupliquidsupply.Pump.mass_flow_kg_s', 'Groupaircoolers.Cooler-1.room_cooling_w',
        'Room-1.state.temperature_k', 'Room-2.state.temperature_k']
    return source
