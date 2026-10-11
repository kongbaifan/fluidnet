"""Standalone module test using the same compiler, solver and Worker as projects."""
from __future__ import annotations

import math
from copy import deepcopy

from .catalog import catalog_map
from .compiler import compile_project
from .models import (
    CommitStepRequest, Connection, Domain, Endpoint, EvaluateRequest, ModuleDefinition,
    ModuleInstance, ModuleTestRequest, ModuleTestResponse, Project,
)
from .properties import property_service
from .runtime import ChannelResult, RuntimeErrorBase, WorkerProcess, module_content_hash
from .solver import snapshot, solve_network


def bench_channels(module: ModuleDefinition) -> list:
    """Enabled channels that the standalone bench can wire to independent boundaries."""
    channels = [c for c in module.channels if c.enabled]
    if not channels:
        raise RuntimeErrorBase('独立验证台需要至少一条启用通路；多通路模块在项目画布验证')
    declared = {port.id for port in module.ports}
    if not declared or not all(port.domain == Domain.fluid for port in module.ports):
        raise RuntimeErrorBase('独立验证台只连接流体端口；其它领域的端口请在项目画布验证')
    wiring = [port for channel in channels for port in (channel.input_port, channel.output_port)]
    missing = sorted(set(wiring) - declared)
    if missing:
        raise RuntimeErrorBase(f'启用通路引用了不存在的端口：{missing}')
    if len(wiring) != len(set(wiring)):
        raise RuntimeErrorBase('独立验证台要求每条启用通路使用独立端口；请检查模块通路设置')
    if set(wiring) != declared:
        raise RuntimeErrorBase(f'独立验证台要求所有端口都绑定到启用通路；未绑定：{sorted(declared - set(wiring))}')
    return channels


def run_module_test(request: ModuleTestRequest) -> ModuleTestResponse:
    module = request.module
    if module.runtime != 'python':
        raise RuntimeErrorBase('模块测试只执行 Python 模块包')
    channels = bench_channels(module)
    boundary = catalog_map()['source'].model_copy(update={'id':'bench_boundary'})
    instances = [ModuleInstance(id='D1', module_id=module.id, name=module.name, parameters=request.parameters)]
    connections = []
    # Every enabled channel gets its own pair of pressure boundaries, so a module with
    # two fluid sides is exercised as one network instead of one channel at a time.
    for index, channel in enumerate(channels, start=1):
        inlet, outlet = f'B{index}', f'S{index}'
        instances.extend([
            ModuleInstance(id=inlet, module_id=boundary.id, name=f'{channel.name} 入口边界',
                           parameters={'pressure_pa':request.inlet_pressure_pa, 'temperature_k':request.temperature_k}),
            ModuleInstance(id=outlet, module_id=boundary.id, name=f'{channel.name} 出口边界',
                           parameters={'pressure_pa':request.outlet_pressure_pa, 'temperature_k':request.temperature_k})])
        connections.extend([
            Connection(id=f'inlet{index}', source=Endpoint(instance_id=inlet,port_id='out0'),
                       target=Endpoint(instance_id='D1',port_id=channel.input_port)),
            Connection(id=f'outlet{index}', source=Endpoint(instance_id='D1',port_id=channel.output_port),
                       target=Endpoint(instance_id=outlet,port_id='out0'))])
    project = Project(id='module-test', name=module.name, fluid=request.fluid, modules=[boundary, module],
        instances=instances, connections=connections)
    network = compile_project(project)
    runner = WorkerProcess(module, network.parameters['D1'], request.fluid)
    try:
        initial_state = deepcopy(runner.initialize())
        service = property_service(request.fluid) if project.solver.thermal else None
        history, previous = [], None
        for index in range(math.ceil(request.duration_s / request.dt_s) + 1):
            time_s = min(index * request.dt_s, request.duration_s)
            network_result = solve_network(network, {'D1':runner}, time_s, warm=previous, service=service)
            previous, result = network_result, network_result.hydraulic
            frame = snapshot(network, network_result, time_s)
            ports = {}
            for port in module.ports:
                flow = frame.variables.get(f'D1.{port.id}.mass_flow_kg_s')
                if flow is None:
                    raise RuntimeErrorBase(f'端口 {port.id} 的流量未在独立网络中解析')
                update = {'mass_flow_kg_s': float(flow)}
                if network_result.thermal is None:
                    update['temperature_k'] = request.temperature_k
                ports[port.id] = network_result.port_states[f'D1:{port.id}'].model_copy(update=update)
            evaluation = runner.evaluate(EvaluateRequest(run_id='module-test',instance_id='D1',iteration_id=0,
                time_s=time_s,trial_ports=ports,readonly_state=runner.state))
            if index:
                committed = runner.commit_step(CommitStepRequest(run_id='module-test',instance_id='D1',time_s=time_s,
                    dt_s=time_s-history[-1].time_s,converged_ports=ports,
                    converged_channels={channel.id:ChannelResult(
                        mass_flow_kg_s=float(frame.variables[f'D1.{channel.id}.mass_flow_kg_s']),
                        pressure_drop_pa=float(frame.variables[f'D1.{channel.id}.pressure_drop_pa'])) for channel in channels}))
                frame.variables.update({f'D1.state.{k}':v for k,v in committed.state.items()
                                        if isinstance(v,(float,int,str,bool)) or v is None})
                if (frame.variables.keys() - result.module_variables.keys()) & {f'D1.{k}' for k in committed.variables}:
                    raise RuntimeErrorBase('commit_step 输出不能覆盖网络求解变量')
                frame.variables.update({f'D1.{k}':v for k,v in committed.variables.items()})
                frame.diagnostics.extend(committed.diagnostics)
            if any(d.severity == 'error' for d in [*frame.diagnostics, *evaluation.diagnostics]):
                raise RuntimeErrorBase('；'.join(d.message for d in [*frame.diagnostics, *evaluation.diagnostics] if d.severity == 'error'))
            history.append(frame)
        runner.finalize()
        return ModuleTestResponse(module_id=module.id,content_hash=module_content_hash(module),state=initial_state,
            evaluation=evaluation,committed=committed,frame=history[-1],history=history)
    finally:
        runner.close()
