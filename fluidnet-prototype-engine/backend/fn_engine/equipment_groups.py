"""Frozen reusable water/air equipment groups; sources and pressure boundaries remain external."""
from .catalog import catalog_map
from .hvac_basic import compose, pump_module, check_module, filter_module, valve_module, junction_module
from .hvac_expansion import fan_performance, plate_exchanger, air_recovery_sensible

def node(i,m,**parameters):return {'id':i,'name':i,'module_id':m.id,'parameters':parameters}
def link(a,b):
    ai,ap=a.split(':');bi,bp=b.split(':')
    return {'id':ai+'_'+ap+'_'+bi+'_'+bp,'source':{'instance_id':ai,'port_id':ap},'target':{'instance_id':bi,'port_id':bp}}

def pump_branch():
    pump,check,strainer=pump_module(),check_module(),filter_module()
    return compose('group_pump_branch','循环泵支路（过滤/水泵/止回）',[pump,check,strainer],
        [node('Strainer',strainer),node('Pump',pump),node('Check',check)],
        [link('Strainer:out0','Pump:in0'),link('Pump:out0','Check:in0')],
        {'Strainer_in0':('in0','吸入口'),'Check_out0':('out0','排出口')})

def parallel_pumps():
    branch=pump_branch();j=junction_module(3)
    return compose('group_parallel_pumps','双支路并联泵组',[branch,j],
        [node('Split',j),node('Join',j),node('A',branch),node('B',branch)],
        [link('Split:p1','A:in0'),link('Split:p2','B:in0'),link('A:out0','Join:p1'),link('B:out0','Join:p2')],
        {'Split_p0':('in0','公共吸入口'),'Join_p0':('out0','公共排出口')})

def secondary_exchanger():
    plate,valve=plate_exchanger(),valve_module()
    return compose('group_secondary_exchanger','双侧换热与平衡阀组',[plate,valve],
        [node('Exchanger',plate),node('HotValve',valve),node('ColdValve',valve)],
        [link('HotValve:out0','Exchanger:hot_in'),link('ColdValve:out0','Exchanger:cold_in')],
        {'HotValve_in0':('hot_in','热侧入口'),'Exchanger_hot_out':('hot_out','热侧出口'),
         'ColdValve_in0':('cold_in','冷侧入口'),'Exchanger_cold_out':('cold_out','冷侧出口')})

def filter_fan():
    filtr=catalog_map()['air_filter'];fan=fan_performance()
    return compose('group_filter_fan','过滤与性能风机段',[filtr,fan],
        [node('Filter',filtr),node('Fan',fan)],[link('Filter:out0','Fan:in0')],
        {'Filter_in0':('in0','进风'),'Fan_out0':('out0','送风')})

def recovery_section():
    recovery=air_recovery_sensible();filtr=catalog_map()['air_filter']
    return compose('group_recovery_section','双风道过滤与显热回收段',[recovery,filtr],
        [node('Recovery',recovery),node('ExhaustFilter',filtr),node('SupplyFilter',filtr)],
        [link('ExhaustFilter:out0','Recovery:exhaust_in'),link('SupplyFilter:out0','Recovery:supply_in')],
        {'ExhaustFilter_in0':('exhaust_in','排风入口'),'Recovery_exhaust_out':('exhaust_out','排风出口'),
         'SupplyFilter_in0':('supply_in','新风入口'),'Recovery_supply_out':('supply_out','新风出口')})

def definitions():return [pump_branch(),parallel_pumps(),secondary_exchanger(),filter_fan(),recovery_section()]
