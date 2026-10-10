from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from .compiler import CompiledBranch, CompiledNetwork
from .models import Diagnostic, RunFrame

RHO_WATER = 998.2
MU_WATER = 1.002e-3
GRAVITY = 9.80665
PRESSURE_SCALE = 100000.0


@dataclass
class HydraulicResult:
    pressures: np.ndarray
    flows: np.ndarray
    iterations: int
    pressure_residual: float
    mass_residual: float


def pipe_drop(params, flow):
    length, diameter, roughness = params['length_m'], params['diameter_m'], params['roughness_m']
    area = math.pi * diameter ** 2 / 4
    reynolds = abs(flow) * diameter / (MU_WATER * area)
    laminar = 32 * MU_WATER * length * flow / (RHO_WATER * area * diameter ** 2)
    if reynolds <= 2300:
        return laminar
    friction = (-1.8 * math.log10((roughness / diameter / 3.7) ** 1.11 + 6.9 / reynolds)) ** -2
    turbulent = friction * length / diameter * flow * abs(flow) / (2 * RHO_WATER * area ** 2)
    blend = min(1., (reynolds - 2300) / 1700)
    return laminar * (1 - blend) + turbulent * blend


def pump_head(curve, flow_m3_h, speed):
    x = flow_m3_h / speed
    # Linear extrapolation is used only to locate the root. Out-of-curve results are rejected below.
    points = curve
    if x < points[0][0]:
        a, b = points[:2]
    elif x > points[-1][0]:
        a, b = points[-2:]
    else:
        return float(np.interp(x, [p[0] for p in points], [p[1] for p in points])) * speed ** 2
    return (a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])) * speed ** 2


def branch_drop(network: CompiledNetwork, branch: CompiledBranch, flow_kg_s: float) -> float:
    params, model = network.parameters[branch.instance_id], branch.solver_model
    volume = flow_kg_s / RHO_WATER * 3600
    if model == 'valve':
        kv = params['kv_m3_h'] * params['opening_ratio']
        return 100000 * (RHO_WATER / 1000) * volume * abs(volume) / kv ** 2
    if model == 'pipe':
        return pipe_drop(params, flow_kg_s)
    if model == 'pump_curve':
        if params['speed_ratio'] <= 0:
            raise ValueError(f'{branch.instance_id} 停泵阻力模型尚未定义，转速必须大于零')
        return -RHO_WATER * GRAVITY * pump_head(params['head_curve'], volume, params['speed_ratio'])
    if model == 'resistance':
        area = math.pi * params['diameter_m'] ** 2 / 4
        return params['loss_coefficient'] * flow_kg_s * abs(flow_kg_s) / (2 * RHO_WATER * area ** 2)
    raise ValueError(f'未注册的支路模型：{model}')


def solve_hydraulics(network: CompiledNetwork) -> HydraulicResult:
    n_nodes, fixed = len(network.node_keys), network.fixed_pressures
    unknown = [n for n in range(n_nodes) if n not in fixed]
    options = network.project.solver

    def unpack(vector):
        pressures = np.zeros(n_nodes)
        for node, value in fixed.items():
            pressures[node] = value
        pressures[unknown] = vector[:len(unknown)] * PRESSURE_SCALE
        return pressures, vector[len(unknown):]

    def physical_residual(vector):
        pressures, flows = unpack(vector)
        drops, balance, closed = [], np.zeros(n_nodes), []
        for branch, flow in zip(network.branches, flows):
            if branch.closed:
                drops.append(0.)
                closed.append(float(flow))
            else:
                drops.append(pressures[branch.start_node] - pressures[branch.end_node] - branch_drop(network, branch, float(flow)))
            balance[branch.start_node] -= flow
            balance[branch.end_node] += flow
        return np.asarray(drops), balance[unknown], closed

    def residual(vector):
        drops, balance, _ = physical_residual(vector)
        _, flows = unpack(vector)
        scaled = drops / PRESSURE_SCALE
        for idx, branch in enumerate(network.branches):
            if branch.closed:
                scaled[idx] = flows[idx]
        return np.concatenate((scaled, balance))

    initial = np.concatenate((np.full(len(unknown), np.mean(list(fixed.values())) / PRESSURE_SCALE), np.full(len(network.branches), .1)))
    result = least_squares(residual, initial, max_nfev=options.max_iterations, xtol=1e-12, ftol=1e-12, gtol=1e-12, x_scale='jac')
    pressures, flows = unpack(result.x)
    drops, balance, closed = physical_residual(result.x)
    pressure_error = float(np.max(np.abs(drops), initial=0))
    mass_error = max(float(np.max(np.abs(balance), initial=0)), max(map(abs, closed), default=0.))
    if not result.success or pressure_error > options.pressure_tolerance_pa or mass_error > options.mass_tolerance_kg_s:
        raise ValueError(f'水力求解未收敛：压力残差 {pressure_error:.6g} Pa，质量残差 {mass_error:.6g} kg/s；{result.message}')
    if np.any(pressures <= 0) or not np.all(np.isfinite(result.x)):
        raise ValueError('求解产生非正绝对压力或非有限结果')
    for branch, flow in zip(network.branches, flows):
        if branch.solver_model == 'pump_curve':
            params = network.parameters[branch.instance_id]
            q = flow / RHO_WATER * 3600
            if q < -1e-8 or q > params['head_curve'][-1][0] * params['speed_ratio'] + 1e-8:
                raise ValueError(f'{branch.instance_id} 工作点 {q:.6g} m³/h 超出泵曲线范围；反向流和曲线外工况尚未支持')
    return HydraulicResult(pressures, flows, int(result.nfev), pressure_error, mass_error)


def snapshot(network, result, time_s=0., warning=None):
    variables, port_flows = {}, {}
    diagnostics = list(network.diagnostics) + ([warning] if warning else [])
    for branch, flow in zip(network.branches, result.flows):
        q = float(flow)
        prefix = f'{branch.instance_id}.{branch.channel_id}'
        values = {'mass_flow_kg_s': q, 'volume_flow_m3_h': q / RHO_WATER * 3600,
                  'inlet_pressure_pa': float(result.pressures[branch.start_node]),
                  'outlet_pressure_pa': float(result.pressures[branch.end_node]),
                  'pressure_drop_pa': float(result.pressures[branch.start_node] - result.pressures[branch.end_node])}
        variables.update({f'{prefix}.{k}': v for k, v in values.items()})
        if sum(b.instance_id == branch.instance_id for b in network.branches) == 1:
            variables.update({f'{branch.instance_id}.{k}': v for k, v in values.items()})
        for port, value in ((branch.input_port, q), (branch.output_port, -q)):
            key = f'{branch.instance_id}:{port}'
            port_flows[key] = port_flows.get(key, 0.) + value
        if branch.solver_model == 'pump_curve':
            variables[f'{branch.instance_id}.shaft_power_w'] = -values['pressure_drop_pa'] * q / RHO_WATER / network.parameters[branch.instance_id]['efficiency_ratio']
    # Boundary and junction port flow follows its directly connected equipment port.
    pairs = [(f'{c.source.instance_id}:{c.source.port_id}', f'{c.target.instance_id}:{c.target.port_id}') for c in network.project.connections]
    pending = list(pairs)
    while pending:
        progress = False
        for a, b in pending[:]:
            if a in port_flows or b in port_flows:
                if a not in port_flows:
                    port_flows[a] = -port_flows[b]
                if b not in port_flows:
                    port_flows[b] = -port_flows[a]
                pending.remove((a,b))
                progress = True
        for inst in network.instances.values():
            if network.modules[inst.module_id].solver_model != 'junction':
                continue
            keys = [f'{inst.id}:{p.id}' for p in network.modules[inst.module_id].ports]
            connected = {key for pair in pairs for key in pair}
            for key in keys:
                if key not in connected:
                    port_flows[key] = 0.
            missing = [key for key in keys if key not in port_flows]
            if len(missing) == 1:
                port_flows[missing[0]] = -sum(port_flows.get(key, 0.) for key in keys)
                progress = True
        if not progress:
            break
    for key, node in network.port_nodes.items():
        inst_id, port_id = key.split(':', 1)
        prefix = f'{inst_id}.{port_id}'
        variables[f'{prefix}.pressure_pa'] = float(result.pressures[node])
        variables[f'{prefix}.mass_flow_kg_s'] = port_flows.get(key)
        variables[f'{prefix}.temperature_k'] = network.parameters[inst_id].get('temperature_k')
    for inst, params in network.parameters.items():
        variables.update({f'{inst}.param.{k}': v for k,v in params.items() if isinstance(v, (float,int))})
    return RunFrame(status='converged', valid=True, time_s=time_s, variables=variables, diagnostics=diagnostics,
                    metrics={'pressure_residual_pa': result.pressure_residual, 'mass_residual_kg_s': result.mass_residual,
                             'iterations': result.iterations, 'node_count': len(network.node_keys), 'branch_count': len(network.branches)})


def solve_steady(network):
    return snapshot(network, solve_hydraulics(network))


def solve_dynamic(network, duration_s, dt_s):
    if not math.isfinite(duration_s) or not math.isfinite(dt_s) or dt_s <= 0 or duration_s <= 0:
        raise ValueError('运行时长和步长必须是有限正数')
    if duration_s > 2000 * dt_s:
        raise ValueError('单次准稳态运行最多 2001 帧')
    count = math.ceil(duration_s / dt_s)
    warning = Diagnostic(code='DYNAMIC_QUASI_STEADY', message='准稳态时间序列：固定参数下复用同一稳态解；未计算容积、热惯性或控制器状态', severity='warning')
    result = solve_hydraulics(network)
    return [snapshot(network, result, min(i * dt_s, duration_s), warning) for i in range(count + 1)]
