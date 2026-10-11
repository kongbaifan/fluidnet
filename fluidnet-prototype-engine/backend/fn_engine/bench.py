"""Standalone module test using the same compiler, solver and Worker as projects."""
from __future__ import annotations

import math
from copy import deepcopy

from .catalog import catalog_map
from .compiler import compile_project
from .models import (
    CommitStepRequest, Connection, Endpoint, EvaluateRequest, ModuleInstance,
    ModuleTestRequest, ModuleTestResponse, PortState, Project,
)
from .runtime import ChannelResult, RuntimeErrorBase, WorkerProcess, module_content_hash
from .solver import snapshot, solve_hydraulics


def run_module_test(request: ModuleTestRequest) -> ModuleTestResponse:
    module = request.module
    if module.runtime != 'python':
        raise RuntimeErrorBase('模块测试只执行 Python 模块包')
    channels = [c for c in module.channels if c.enabled]
    if len(channels) != 1 or len(module.ports) != 2:
        raise RuntimeErrorBase('当前独立验证台需要一个启用通路和两个流体端口；多通路模块请在项目画布验证')
    channel = channels[0]
    boundary = catalog_map()['source'].model_copy(update={'id':'bench_boundary'})
    project = Project(id='module-test', name=module.name, fluid=request.fluid, modules=[boundary, module],
        instances=[ModuleInstance(id='B1', module_id=boundary.id, name='入口边界',
                                 parameters={'pressure_pa':request.inlet_pressure_pa, 'temperature_k':request.temperature_k}),
                   ModuleInstance(id='D1', module_id=module.id, name=module.name, parameters=request.parameters),
                   ModuleInstance(id='B2', module_id=boundary.id, name='出口边界',
                                 parameters={'pressure_pa':request.outlet_pressure_pa, 'temperature_k':request.temperature_k})],
        connections=[Connection(id='inlet', source=Endpoint(instance_id='B1',port_id='out0'),
                                target=Endpoint(instance_id='D1',port_id=channel.input_port)),
                     Connection(id='outlet', source=Endpoint(instance_id='D1',port_id=channel.output_port),
                                target=Endpoint(instance_id='B2',port_id='out0'))])
    network = compile_project(project)
    runner = WorkerProcess(module, network.parameters['D1'], request.fluid)
    try:
        initial_state = deepcopy(runner.initialize())
        history = []
        for index in range(math.ceil(request.duration_s / request.dt_s) + 1):
            time_s = min(index * request.dt_s, request.duration_s)
            result = solve_hydraulics(network, {'D1':runner}, time_s)
            frame = snapshot(network, result, time_s)
            ports = {port.id:PortState(pressure_pa=float(result.pressures[network.port_nodes[f'D1:{port.id}']]),
                        temperature_k=request.temperature_k, density_kg_m3=result.density, viscosity_pa_s=result.viscosity,
                        mass_flow_kg_s=frame.variables[f'D1.{port.id}.mass_flow_kg_s']) for port in module.ports}
            evaluation = runner.evaluate(EvaluateRequest(run_id='module-test',instance_id='D1',iteration_id=0,
                time_s=time_s,trial_ports=ports,readonly_state=runner.state))
            if index:
                committed = runner.commit_step(CommitStepRequest(run_id='module-test',instance_id='D1',time_s=time_s,
                    dt_s=time_s-history[-1].time_s,converged_ports=ports,
                    converged_channels={channel.id:ChannelResult(mass_flow_kg_s=float(result.flows[0]),
                        pressure_drop_pa=request.inlet_pressure_pa-request.outlet_pressure_pa)}))
                frame.variables.update({f'D1.state.{k}':v for k,v in committed.state.items()
                                        if isinstance(v,(float,int,str,bool)) or v is None})
                if (frame.variables.keys() - result.module_variables.keys()) & {f'D1.{k}' for k in committed.variables}:
                    raise RuntimeErrorBase('commit_step 输出不能覆盖网络求解变量')
                frame.variables.update({f'D1.{k}':v for k,v in committed.variables.items()})
                frame.diagnostics.extend(committed.diagnostics)
            if any(d.severity == 'error' for d in [*frame.diagnostics, *evaluation.diagnostics]):
                raise RuntimeErrorBase('；'.join(d.message for d in [*frame.diagnostics, *evaluation.diagnostics] if d.severity == 'error'))
            history.append(frame)
        return ModuleTestResponse(module_id=module.id,content_hash=module_content_hash(module),state=initial_state,
            evaluation=evaluation,committed=committed,frame=history[-1],history=history)
    finally:
        runner.close()
