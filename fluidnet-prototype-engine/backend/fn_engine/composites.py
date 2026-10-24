"""Bounded deterministic composition of ordinary fluid devices, without extra equations."""
from copy import deepcopy
import hashlib

from .models import ModuleDefinition, ModuleInstance, Endpoint, Connection
from .runtime import module_content_hash, module_definition_hash

MAX_DEPTH = 8
MAX_INSTANCES = 1000
PORT_FIELDS = ['pressure_pa','temperature_k','enthalpy_j_kg','mass_flow_kg_s','density_kg_m3','viscosity_pa_s','quality']


def _namespace(root, path):
    full = '__'.join([root,*path])
    return full if len(full) <= 80 else root[:30]+'__'+hashlib.sha256(full.encode()).hexdigest()[:24]


def expand_composites(project):
    definitions = {module.id:module for module in project.modules}
    if not any(definitions[instance.module_id].composite is not None for instance in project.instances):
        return project, {}
    leaves, connections, aliases, computed, parameters, sources, channel_maps = [], [], {}, {}, {}, {}, {}
    used_ids = {instance.id for instance in project.instances if definitions[instance.module_id].composite is None}
    root_endpoints = {}

    def register(module):
        previous = definitions.get(module.id)
        if previous is not None and (previous.version, module_definition_hash(previous)) != (module.version, module_definition_hash(module)):
            raise ValueError(f'组合依赖版本冲突：{module.id}，不同版本不能同时进入项目')
        definitions[module.id] = module

    def expand(instance, root, path, stack):
        definition = definitions[instance.module_id]
        marker = (definition.id, definition.version)
        if marker in stack or len(stack) >= MAX_DEPTH:
            raise ValueError('组合存在循环依赖或超过 8 层深度')
        name = _namespace(root,path) if path else instance.id
        if definition.composite is None:
            if name in used_ids and path:
                raise ValueError(f'组合展开 ID 冲突：{name}')
            used_ids.add(name)
            if len(leaves) >= MAX_INSTANCES:
                raise ValueError('组合展开超过 1000 个实例')
            if any(port.domain != 'fluid' for port in definition.ports):
                raise ValueError('组合仅支持普通流体执行域')
            leaf = instance.model_copy(deep=True, update={'id':name})
            leaves.append(leaf)
            if path:
                sources[name] = {'owner':root,'path':'.'.join([root,*path])}
            port_map = {port.id:Endpoint(instance_id=name,port_id=port.id) for port in definition.ports}
            parameter_map = {parameter.id:[(name,parameter.id)] for parameter in definition.parameters}
            variable_map = {variable.id:f'{name}.{variable.id}' for variable in definition.variables}
            variable_map.update({f'{port.id}.{field}':f'{name}.{port.id}.{field}' for port in definition.ports for field in PORT_FIELDS})
            variable_map.update({f'{channel.id}.{field}':f'{name}.{channel.id}.{field}' for channel in definition.channels
                                for field in ['mass_flow_kg_s','pressure_drop_pa','heat_w','inlet_temperature_k','outlet_temperature_k']})
            variable_map.update({f'param.{p.id}':f'{name}.param.{p.id}' for p in definition.parameters})
            return port_map,parameter_map,variable_map
        if not definition.sdk or 'composite.v1' not in definition.sdk.capabilities:
            raise ValueError('组合模块必须声明 composite.v1')
        spec = definition.composite
        first_leaf = len(leaves)
        if len({child.id for child in spec.children}) != len(spec.children):
            raise ValueError('组合子实例 ID 重复')
        for payload in spec.modules:
            register(ModuleDefinition.model_validate(payload))
        children = {child.id:child for child in spec.children}
        if set(spec.external_ports) != {port.id for port in definition.ports}:
            raise ValueError('组合外端口映射不完整')
        mapped_ports = [(endpoint.instance_id, endpoint.port_id) for endpoint in spec.external_ports.values()]
        if len(mapped_ports) != len(set(mapped_ports)):
            raise ValueError('组合外端口必须一对一映射')
        child_parameters = {child.id:deepcopy(child.parameters) for child in spec.children}
        defaults = {parameter.id:deepcopy(parameter.default) for parameter in definition.parameters}
        defaults.update(instance.parameters)
        targets = set()
        for public, destinations in spec.parameter_maps.items():
            if public not in defaults or len(destinations) != 1:
                raise ValueError('首版组合参数采用一对一映射，公共参数必须已声明')
            for destination in destinations:
                pair = (destination.instance_id,destination.parameter_id)
                if pair in targets or destination.instance_id not in children:
                    raise ValueError('组合参数目标冲突或子实例不存在')
                targets.add(pair)
                child_parameters[destination.instance_id][destination.parameter_id] = deepcopy(defaults[public])
        results = {}
        for child_id in sorted(children):
            child = children[child_id]
            module = definitions.get(child.module_id)
            if module is None:
                raise ValueError(f'缺少组合子版本 {child.module_id} v{child.version}')
            if (module.version,module_definition_hash(module)) != (child.version,child.definition_hash):
                raise ValueError(f'组合子版本或契约哈希不一致：{child.module_id}')
            if module.runtime == 'python' and module_content_hash(module) != child.content_hash:
                raise ValueError(f'组合子源码哈希不一致：{child.module_id}')
            declared = {parameter.id:parameter for parameter in module.parameters}
            if set(child_parameters[child_id]) - declared.keys():
                raise ValueError(f'组合子参数引用不存在：{child_id}')
            for public, destinations in spec.parameter_maps.items():
                public_spec = next(parameter for parameter in definition.parameters if parameter.id == public)
                for destination in destinations:
                    if destination.instance_id != child_id:
                        continue
                    target_spec = declared[destination.parameter_id]
                    a, b = public_spec.unit, target_spec.unit
                    if public_spec.value_type != target_spec.value_type or (a.canonical_unit if a else None) != (b.canonical_unit if b else None):
                        raise ValueError('组合参数类型或规范单位不匹配')
            nested = ModuleInstance(id=child_id,module_id=module.id,name=child_id,parameters=child_parameters[child_id])
            results[child_id] = expand(nested,root,path+[child_id],stack+[marker])
        def endpoint(reference):
            if reference.instance_id not in results or reference.port_id not in results[reference.instance_id][0]:
                raise ValueError('组合端口引用不存在')
            return results[reference.instance_id][0][reference.port_id].model_copy(deep=True)
        for edge in spec.connections:
            connections.append(Connection(id=_namespace(root,path+[edge.id]),source=endpoint(edge.source),target=endpoint(edge.target)))
        port_map = {public:endpoint(reference) for public,reference in spec.external_ports.items()}
        for public, destinations in spec.parameter_maps.items():
            destination = destinations[0]
            parameters[f'{name}.param.{public}'] = results[destination.instance_id][1][destination.parameter_id]
        parameter_map = {public:parameters[f'{name}.param.{public}'] for public in spec.parameter_maps}
        variable_map = {}
        if set(spec.output_aliases) != {variable.id for variable in definition.variables if variable.source in {'state','derived'}}:
            raise ValueError('组合输出别名必须覆盖全部声明的状态和派生输出')
        for public, reference in spec.output_aliases.items():
            child_id, _, suffix = reference.partition('.')
            if child_id not in results or suffix not in results[child_id][2]:
                raise ValueError(f'组合输出引用不存在：{reference}')
            variable_map[public] = results[child_id][2][suffix]
        for public,reference in port_map.items():
            for field in PORT_FIELDS:
                variable_map[f'{public}.{field}'] = f'{reference.instance_id}.{reference.port_id}.{field}'
        for public,destinations in parameter_map.items():
            variable_map['param.'+public] = destinations[0][0]+'.param.'+destinations[0][1]
        for public,reference in variable_map.items():
            aliases[f'{name}.{public}'] = reference
        for channel in definition.channels:
            start, end = port_map[channel.input_port], port_map[channel.output_port]
            channel_maps[f'{name}.{channel.id}'] = {'start':start.model_dump(),'end':end.model_dump(),
                'instances':[leaf.id for leaf in leaves[first_leaf:]]}
            aliases[f'{name}.{channel.id}.mass_flow_kg_s'] = f'{start.instance_id}.{start.port_id}.mass_flow_kg_s'
            computed[f'{name}.{channel.id}.pressure_drop_pa'] = ('difference',[
                f'{start.instance_id}.{start.port_id}.pressure_pa', f'{end.instance_id}.{end.port_id}.pressure_pa'])
            if len(definition.channels) == 1:
                aliases[f'{name}.mass_flow_kg_s'] = f'{name}.{channel.id}.mass_flow_kg_s'
                aliases[f'{name}.pressure_drop_pa'] = f'{name}.{channel.id}.pressure_drop_pa'
        return port_map,parameter_map,variable_map

    for instance in project.instances:
        port_map,_,_ = expand(instance,instance.id,[],[])
        for port,reference in port_map.items():
            root_endpoints[(instance.id,port)] = reference
    for edge in project.connections:
        connections.append(edge.model_copy(deep=True,update={
            'source':root_endpoints[(edge.source.instance_id,edge.source.port_id)],
            'target':root_endpoints[(edge.target.instance_id,edge.target.port_id)]}))
    candidate = project.model_copy(deep=True,update={'instances':leaves,'connections':connections,
        'modules':sorted(definitions.values(),key=lambda module:module.id)})
    for circuit in candidate.circuit_fluids:
        circuit.anchor = root_endpoints[(circuit.anchor.instance_id,circuit.anchor.port_id)].model_copy(deep=True)
    for controller in candidate.controllers:
        target = parameters.get(f'{controller.instance_id}.param.{controller.parameter_id}')
        if target:
            controller.instance_id,controller.parameter_id = target[0]
        controller.measurement = aliases.get(controller.measurement,controller.measurement)
    for scenario in candidate.scenarios:
        mapped = {}
        for instance,values in scenario.overrides.items():
            for parameter,value in values.items():
                destinations = parameters.get(f'{instance}.param.{parameter}',[(instance,parameter)])
                for target,identifier in destinations:
                    if identifier in mapped.setdefault(target,{}):
                        raise ValueError('组合工况参数写入冲突')
                    mapped[target][identifier] = value
        scenario.overrides = mapped
    if len({edge.id for edge in connections}) != len(connections):
        raise ValueError('组合展开连接 ID 冲突')
    mapping = {'variables':aliases,'computed':computed,'parameters':parameters,'sources':sources,'channels':channel_maps}
    candidate._composite_maps = mapping
    return candidate,mapping


def map_frame(network,frame):
    mapping = getattr(network,'composite_maps',{})
    values = frame.variables
    for _ in range(MAX_DEPTH+1):
        for public,reference in mapping.get('variables',{}).items():
            if reference in values:
                values[public] = values[reference]
        for public,(kind,references) in mapping.get('computed',{}).items():
            if all(reference in values for reference in references):
                values[public] = values[references[0]]-values[references[1]] if kind == 'difference' else sum(values[key] for key in references)
    for public,channel in mapping.get('channels',{}).items():
        start,end = channel['start'],channel['end']
        node = network.port_nodes[start['instance_id']+':'+start['port_id']]
        circuit = network.node_circuit[node]
        terms=[f'{branch.instance_id}.{branch.channel_id}.heat_w' for branch in network.branches
            if branch.instance_id in channel['instances'] and network.node_circuit[branch.start_node]==circuit]
        if terms and all(term in values for term in terms):
            values[public+'.heat_w'] = sum(values[term] for term in terms)
        flow = values.get(public+'.mass_flow_kg_s',0)
        upstream,downstream = (start,end) if flow >= 0 else (end,start)
        for label,endpoint in [('inlet_temperature_k',upstream),('outlet_temperature_k',downstream)]:
            key=endpoint['instance_id']+'.'+endpoint['port_id']+'.temperature_k'
            if key in values:
                values[public+'.'+label]=values[key]
    frame.diagnostics = map_diagnostics(mapping,frame.diagnostics)
    return frame


def map_diagnostics(mapping,diagnostics):
    result=[]
    for diagnostic in diagnostics:
        source=mapping.get('sources',{}).get(diagnostic.instance_id)
        result.append(diagnostic.model_copy(update={'instance_id':source['owner'],'source_path':source['path']}) if source else diagnostic)
    return result


def module_from_group(project, instance_ids, identifier, name):
    selected = {instance.id:instance for instance in project.instances if instance.id in instance_ids}
    if not selected or len(selected) != len(set(instance_ids)):
        raise ValueError('设备组包含不存在或重复的实例')
    definitions = {module.id:module for module in project.modules}
    if any(definitions[instance.module_id].solver_model == 'pressure_source' for instance in selected.values()):
        raise ValueError('压力边界应保留在组合外部')
    children, embedded, edges, external, parameters, parameter_maps, outputs, variables = [], {}, [], {}, [], {}, {}, []
    occupied = set()
    for edge in project.connections:
        if edge.source.instance_id in selected and edge.target.instance_id in selected:
            payload=edge.model_dump(mode='json')
            payload['id']=f'link{len(edges)}'
            edges.append(payload)
            occupied.update([(edge.source.instance_id,edge.source.port_id),(edge.target.instance_id,edge.target.port_id)])
    parents = {}
    def find(value):
        parents.setdefault(value,value)
        if parents[value] != value:
            parents[value] = find(parents[value])
        return parents[value]
    def union(a,b):
        parents[find(a)] = find(b)
    for edge in edges:
        union((edge['source']['instance_id'],edge['source']['port_id']), (edge['target']['instance_id'],edge['target']['port_id']))
    ports=[]
    for key, instance in sorted(selected.items()):
        definition = definitions[instance.module_id]
        if any(port.domain != 'fluid' for port in definition.ports):
            raise ValueError('组合只支持普通流体设备')
        child = definition.model_copy(deep=True)
        child.definition_hash = module_definition_hash(child)
        if child.runtime == 'python':
            child.content_hash = module_content_hash(child)
        embedded[child.id] = child.model_dump(mode='json',exclude={'package_path'})
        children.append({'id':key,'module_id':child.id,'version':child.version,'definition_hash':child.definition_hash,
            'content_hash':child.content_hash,'parameters':deepcopy(instance.parameters)})
        for channel in child.channels:
            if channel.enabled:
                union((key,channel.input_port),(key,channel.output_port))
        for port in child.ports:
            if (key,port.id) not in occupied:
                public = f'{key}_{port.id}'
                external[public] = {'instance_id':key,'port_id':port.id}
                ports.append({**port.model_dump(mode='json'),'id':public,'label':key+' · '+port.label})
        for spec in child.parameters:
            if spec.runtime and spec.writable:
                public = f'{key}_{spec.id}'
                parameters.append({**spec.model_dump(mode='json'),'id':public,'label':key+' · '+spec.label,
                    'default':deepcopy(instance.parameters.get(spec.id,spec.default))})
                parameter_maps[public]=[{'instance_id':key,'parameter_id':spec.id}]
        for variable in child.variables:
            if variable.source not in {'state','derived'}:
                continue
            public = 'state.'+key+'.'+variable.id[6:] if variable.source == 'state' else key+'.'+variable.id
            outputs[public] = key+'.'+variable.id
            variables.append({**variable.model_dump(mode='json'),'id':public,'label':key+' · '+variable.label})
    groups={}
    for port in ports:
        ref=external[port['id']]
        group=find((ref['instance_id'],ref['port_id']))
        groups.setdefault(group,[]).append(port)
    channels=[]
    for index,group in enumerate(sorted(groups,key=str)):
        entries=groups[group]
        for port in entries:
            port['circuit']=f'fluid{index}'
        if len(entries)==2:
            entries.sort(key=lambda port:(port['direction']!='in',port['id']))
            channels.append({'id':'main' if len(groups)==1 else f'side{index}', 'name':f'通路 {index+1}',
                'input_port':entries[0]['id'],'output_port':entries[1]['id'],'relation':'resistance','solver_model':'generic'})
    payload={'schema_version':3,'id':identifier,'name':name,'runtime':'python','entrypoint':'module:Module',
        'ports':ports,'parameters':parameters,'variables':variables,'channels':channels,
        'sdk':{'api_version':'0.5.0','capabilities':['composite.v1']},
        'source':{'runtime':'class Module:\n    def initialize(self,ctx): pass\n    def evaluate(self,ctx): pass\n    def commit_step(self,ctx,dt): pass\n    def finalize(self,ctx): pass\n'},
        'composite':{'children':children,'modules':list(embedded.values()),'connections':edges,
                     'external_ports':external,'parameter_maps':parameter_maps,'output_aliases':outputs},
        'applicability':{'assumptions':['组合展开复用子模块精确版本；外端口和公开参数一对一映射。']}}
    return ModuleDefinition.model_validate(payload)
