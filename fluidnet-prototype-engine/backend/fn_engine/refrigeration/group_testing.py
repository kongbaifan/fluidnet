"""Real host-network validation for open refrigeration equipment groups."""
from copy import deepcopy

from ..models import Endpoint, ModuleInstance, ModuleTestConditions, ModuleTestResponse, EvaluateResponse, CommitStepResponse, Position
from ..composites import OPEN_REFRIGERATION_CAPABILITY
from ..runtime import module_content_hash


def replace_with_group(project, selected_ids, module, instance_id='D1'):
    """Create an editable host copy; preserve actual external connections and explicit references."""
    if not module.composite or not module.sdk or OPEN_REFRIGERATION_CAPABILITY not in module.sdk.capabilities:
        raise ValueError('宿主测试上下文仅用于开放端口制冷组')
    selected=set(selected_ids)
    if selected!={child.id for child in module.composite.children}:
        raise ValueError('宿主选组与组合子实例不一致')
    if not selected<={i.id for i in project.instances}:
        raise ValueError('宿主缺少原选组设备')
    if any(i.id==instance_id for i in project.instances if i.id not in selected):
        raise ValueError('宿主测试实例ID冲突')
    if any(i.module_id==module.id for i in project.instances if i.id not in selected):
        raise ValueError('宿主已包含相同模块ID，请选择独立验证宿主')
    if project.control_scripts or project.events or any(s.events for s in project.scenarios):
        raise ValueError('宿主含脚本或日程，不能自动改写；请先在专用验证项目中移除并显式配置')
    result=project.model_copy(deep=True)
    originals=[i for i in result.instances if i.id in selected]
    page=originals[0].page_id
    on_page=[i for i in originals if i.page_id==page]
    center=Position(x=sum(i.position.x for i in on_page)/len(on_page),y=sum(i.position.y for i in on_page)/len(on_page))
    external={(e.instance_id,e.port_id):name for name,e in module.composite.external_ports.items()}
    parameters={(e.instance_id,e.parameter_id):name for name,items in module.composite.parameter_maps.items() for e in items}
    variables={ref:instance_id+'.'+name for name,ref in module.composite.output_aliases.items()}
    def endpoint(e):
        if e.instance_id not in selected:return e
        if (e.instance_id,e.port_id) not in external:raise ValueError('外部引用的组端口没有公开')
        return Endpoint(instance_id=instance_id,port_id=external[(e.instance_id,e.port_id)])
    def reference(key):
        if key in variables:return variables[key]
        iid,_,tail=key.partition('.')
        if iid not in selected:return key
        if tail.startswith('param.') and (iid,tail[6:]) in parameters:return instance_id+'.param.'+parameters[(iid,tail[6:])]
        port,_,field=tail.partition('.')
        if (iid,port) in external:return instance_id+'.'+external[(iid,port)]+'.'+field
        raise ValueError('宿主引用了未公开的组内变量：'+key)
    result.instances=[i for i in result.instances if i.id not in selected]
    result.instances.append(ModuleInstance(id=instance_id,module_id=module.id,name=module.name,page_id=page,position=center))
    result.modules=[m for m in result.modules if m.id!=module.id]+[module.model_copy(deep=True)]
    connections=[]
    for c in result.connections:
        if c.source.instance_id in selected and c.target.instance_id in selected:continue
        c.source=endpoint(c.source);c.target=endpoint(c.target);connections.append(c)
    result.connections=connections
    for anchor in result.circuit_fluids:anchor.anchor=endpoint(anchor.anchor)
    for pid in result.controllers:
        if pid.instance_id in selected:
            key=(pid.instance_id,pid.parameter_id)
            if key not in parameters:raise ValueError('宿主控制器执行参数未公开')
            pid.instance_id=instance_id;pid.parameter_id=parameters[key]
        pid.measurement=reference(pid.measurement)
    for measure in result.measurements:measure.sources=[reference(key) for key in measure.sources]
    result.selected_variables=[reference(key) for key in result.selected_variables]
    for scenario in result.scenarios:
        remapped={}
        for iid,patch in scenario.overrides.items():
            for key,value in patch.items():
                if iid in selected:
                    if (iid,key) not in parameters:raise ValueError('宿主工况覆盖了未公开参数')
                    remapped.setdefault(instance_id,{})[parameters[(iid,key)]]=value
                else:remapped.setdefault(iid,{})[key]=value
        scenario.overrides=remapped
    return result


def test_context(request):
    project=replace_with_group(request.project,request.instance_ids,request.module)
    from ..compiler import compile_project
    compile_project(project)
    return ModuleTestConditions(host_project=project,host_instance_id='D1',fluid=project.fluid,
                                duration_s=.1,dt_s=.1)


def run_host_test(request):
    from ..compiler import compile_project
    from ..sessions import create_session
    module=request.module
    if request.host_project is None:raise ValueError('开放制冷组需要完整冻结宿主测试项目；不能使用普通压力边界')
    project=request.host_project.model_copy(deep=True)
    target=next((i for i in project.instances if i.id==request.host_instance_id),None)
    if target is None or target.module_id!=module.id:raise ValueError('宿主测试目标与候选模块不一致')
    if target.id!='D1' and any(i.id=='D1' for i in project.instances):raise ValueError('宿主D1标识保留给待测组输出，请重命名外部D1设备')
    if sum(i.module_id==module.id for i in project.instances)!=1:raise ValueError('独立宿主测试必须只有一个待发布组实例')
    if project.control_scripts or project.events or project.controllers:raise ValueError('发布宿主测试不得带活动控制或日程；请用固定边界专用验证项目')
    if request.channel_boundaries or request.moist_air or request.property_coupling!='reference':raise ValueError('宿主制冷测试不接受普通水力/湿空气边界覆盖')
    # Never validate a stale published definition that happens to have the candidate's ID.
    project.modules=[m for m in project.modules if m.id!=module.id]+[module.model_copy(deep=True)]
    target.parameters=deepcopy(request.parameters);target.package=None
    project.id='open-group-test';project.name=module.name+' · 宿主验证'
    network=compile_project(project)
    if network.execution_domain!='refrigeration':raise ValueError('开放制冷组仅在纯制冷宿主项目测试')
    session=create_session(network,request.duration_s,request.dt_s)
    try:
        first=session.initialize()
        while not session.done:session.advance()
        history=[];prefix=request.host_instance_id+'.'
        for source in session.frames:
            frame=source.model_copy(deep=True)
            if request.host_instance_id!='D1':
                frame.variables.update({'D1.'+key[len(prefix):]:v for key,v in frame.variables.items() if key.startswith(prefix)})
            history.append(frame)
        public={k[3:]:v for k,v in history[-1].variables.items() if k.startswith('D1.')}
        initial={k[len(prefix):]:v for k,v in first.variables.items() if k.startswith(prefix+'state.')}
        final_state={k:v for k,v in public.items() if k.startswith('state.')}
        return ModuleTestResponse(module_id=module.id,content_hash=module_content_hash(module),state=initial,execution_domain='refrigeration',
            evaluation=EvaluateResponse(variables=public,diagnostics=history[-1].diagnostics),
            committed=CommitStepResponse(state=final_state,variables=public),frame=history[-1],history=history)
    finally:session.close()
