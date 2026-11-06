"""Allowlisted editable equipment/group reference projects, never an opaque case solver."""
from pathlib import Path
from typing import Literal
from pydantic import Field
from .models import StrictModel, Project
from .catalog import catalog_map
from .packages import load_module_package

ROOT=Path(__file__).resolve().parents[2]
GROUPS={
 'group_pump_branch':('循环泵支路','water','过滤/泵/止回，外部压力边界；无内置启停控制'),
 'group_parallel_pumps':('双支路并联泵组','water','公共吸排口；两个独立泵支路与接受累计'),
 'group_secondary_exchanger':('双侧换热与平衡阀组','water','热侧水、冷侧30%乙二醇；两侧独立边界'),
 'group_filter_fan':('过滤与风机段','air','Air单相或透传湿空气；压差工作点'),
 'group_recovery_section':('过滤与显热回收段','air','两条独立风路；无凝结、结霜'),
 'ahu_standard':('混风空调箱','air','复用现有成套模块；空气/水独立通路'),
 'fahu_standard':('新风机组','air','复用现有成套模块；实际水盘管'),
 'fcu_terminal':('风机盘管末端','air','复用现有成套模块；实际空气/水接口'),
}
DESIGNS={'design_pump':('多点选型泵','water'),'design_fan':('多点选型风机','air'),'design_plate_exchanger':('双侧物性选型板换','water')}
RECIPES={'modular-room':'泵供液库房（可选房间与压缩机数量）','multi-cooler':'同库双冷风机','two-stage':'开式两级闪蒸中冷','dx':'直接膨胀回路'}
class LibraryItem(StrictModel):
    id:str
    name:str
    kind:Literal['group','design','recipe']
    medium:str
    assumptions:str
class LibraryCatalog(StrictModel):
    items:list[LibraryItem]
class LibraryRequest(StrictModel):
    name:str
    prefix:str=Field(default='Own',pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,15}$')
    room_count:int=Field(default=1,ge=1,le=4,strict=True)
    compressor_count:int=Field(default=1,ge=1,le=4,strict=True)

def catalog():
    return LibraryCatalog(items=[*[LibraryItem(id=k,name=v[0],kind='group',medium=v[1],assumptions=v[2]) for k,v in GROUPS.items()],
        *[LibraryItem(id=k,name=v[0],kind='design',medium=v[1],assumptions='通过设备选型计算参数建议；教学曲线，无厂家标定') for k,v in DESIGNS.items()],
        *[LibraryItem(id=k,name=v,kind='recipe',medium='refrigeration',assumptions='可编辑设备recipe；不是普通fluid组合模块') for k,v in RECIPES.items()]])

def group_example(identifier):
    m=load_module_package(ROOT/'modules'/identifier);isair=(GROUPS.get(identifier) or DESIGNS[identifier])[1]=='air'
    source=catalog_map()['source'];nodes=[{'id':'Equipment','module_id':identifier,'name':m.name,'position':{'x':450,'y':250}}];edges=[];fluids=[]
    sideports={p.id:p for p in m.ports}
    for index,(pid,port) in enumerate(sideports.items()):
        water=isair and 'water' in pid or identifier in ('group_secondary_exchanger','design_plate_exchanger')
        hot='hot' in pid;incoming=port.direction=='in' or pid in ('in0','fresh_in','return_in','water_in','hot_in','cold_in','exhaust_in','supply_in')
        p=250000. if water or not isair else 101325.
        if identifier in ('group_pump_branch','group_parallel_pumps','design_pump'):p=250000. if incoming else 260000.
        elif identifier in ('group_filter_fan','design_fan'):p=101325. if incoming else 101375.
        else:p+=1000. if incoming and water else 100. if incoming else 0.
        temp=333.15 if hot else 293.15
        if isair:temp=285.15 if water else 303.15 if 'exhaust' in pid else 293.15
        iid='Boundary'+str(index)
        nodes.append({'id':iid,'module_id':'source','name':port.label+'边界','parameters':{'pressure_pa':p,'temperature_k':temp,'humidity_ratio_kg_kg':.003},'position':{'x':100. if incoming else 800.,'y':100.+index*110.}})
        edges.append({'id':'connection'+str(index),'source':{'instance_id':iid,'port_id':'out0'},'target':{'instance_id':'Equipment','port_id':pid}})
        if incoming and water:fluids.append({'id':'water'+str(index),'anchor':{'instance_id':'Equipment','port_id':pid},'fluid':{'fluid':'INCOMP::MEG[0.3]' if 'cold' in pid else 'Water','phase_policy':'liquid'}})
    return Project(id=identifier,name=m.name,modules=[source,m],instances=nodes,connections=edges,
        fluid={'fluid':'Air' if isair else 'Water','phase_policy':'gas' if isair else 'liquid'},circuit_fluids=fluids,
        solver={'thermal':True,'property_coupling':'node','moist_air':isair,'moist_air_options':{'contract_version':1,'max_iterations':120} if isair else None,'module_mixed_jacobian':False,'max_coupling_iterations':60})

def build(request):
    name=request.name
    if name in GROUPS or name in DESIGNS:p=group_example(name)
    elif name=='modular-room':
        from .refrigeration.modular_examples import modular_room_example
        p=modular_room_example(request.room_count,request.compressor_count)
    elif name=='multi-cooler':
        from .refrigeration.multi_cooler_example import multi_cooler_example
        p=multi_cooler_example()
    elif name=='two-stage':
        from .refrigeration.two_stage_example import modular_two_stage_example
        p=modular_two_stage_example()
    elif name=='dx':
        from .refrigeration.dx_example import dx_example
        p=dx_example()
    else:raise ValueError('未知设备组或选型参考项目')
    if name!='modular-room' and (request.room_count!=1 or request.compressor_count!=1):raise ValueError('只有泵供液库房模板支持数量设置')
    names={i.id:request.prefix+'-'+i.id for i in p.instances}
    for n in p.instances:n.id=names[n.id]
    for c in p.connections:c.source.instance_id=names[c.source.instance_id];c.target.instance_id=names[c.target.instance_id]
    for f in p.circuit_fluids:f.anchor.instance_id=names[f.anchor.instance_id]
    if p.controllers or p.control_scripts or p.scenarios or p.measurements:raise ValueError('模板含未声明的控制或测点引用，拒绝自动重命名')
    p.id=request.prefix+'-'+p.id;p.name=request.prefix+' · '+p.name
    return p
