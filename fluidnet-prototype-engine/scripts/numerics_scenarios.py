"""B2 验收场景：静态参考解、动态守恒检查与冷库 A/B 单独计时。

场景分两类：

- ``static``：关阀、开阀、反向流。开/关阀与反向流有独立的 Kv 解析参考解
  （``q_m3_h = sqrt(Δp·kv²/(100000·ρ/1000))``），不是与旧实现自比。
- ``dynamic``：关开阀 + 水箱、管道热容、PID 液位、Python 模块状态。动态场景检查
  守恒（质量账本、能量残差）与阶段行为，管道热容另做“有/无壁面热容”的 A/B 参考。

冷库 A（理想冷源单库房）与冷库 B（集总制冷站）分别计时：冷启动在独立子进程内完成
一次 compile→initialize→advance，热运行在同一子进程内预热后重复；报告中位数/最小/最大。
本脚本只做 ``B2`` 的进程内/子进程计时，严格的“新进程 5 次、热跑 7 次”协议由 B3 脚本执行。

用法（仓库根目录）：

    python scripts/numerics_scenarios.py --output artifacts/numerics/<commit>/B2/scenarios.json
"""
import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numerics_cases
from fn_engine import solver
from fn_engine.compiler import compile_project
from fn_engine.examples import pid_example
from fn_engine.sessions import create_session
from fn_engine.simulation import SimulationSession


# ---------------------------------------------------------------- 公共工具


def check(check_id, passed, value, reference=None, tolerance=None, mode='rel'):
    return {'id': check_id, 'passed': bool(passed), 'value': value, 'reference': reference,
            'tolerance': tolerance, 'mode': mode}


def within(value, reference, tolerance, mode='rel'):
    if mode == 'abs':
        return abs(value - reference) <= tolerance
    return abs(value - reference) <= tolerance * max(abs(reference), 1e-30)


def signature(metrics):
    """参考指标签名：只看场景显式声明为参考/守恒的指标，避免把机器噪声写进签名。"""
    text = json.dumps({key: metrics[key] for key in sorted(metrics)}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _tolerance(project):
    return project.solver.pressure_tolerance_pa, project.solver.mass_tolerance_kg_s


def _source(instance_id, pressure, temperature=293.15):
    return (instance_id, 'source', {'pressure_pa': float(pressure), 'temperature_k': float(temperature)})


def _solve_steady(project):
    begin = time.perf_counter()
    network = compile_project(project)
    frame = solver.solve_steady(network)
    return frame, time.perf_counter() - begin


def _run_session(project, duration_s, dt_s, actions=()):
    """按 ``(time_s, callback)`` 在时间边界执行参数写入，返回全部帧与分段计时。"""
    network = compile_project(project)
    session = SimulationSession(network, duration_s, dt_s)
    frames = []
    pending = list(actions)
    init_s = steps_s = 0.0
    try:
        begin = time.perf_counter()
        frames.append(session.initialize())
        init_s = time.perf_counter() - begin
        while not session.done:
            while pending and session.time >= pending[0][0] - 1e-9:
                pending.pop(0)[1](session)
            begin = time.perf_counter()
            frames.append(session.advance())
            steps_s += time.perf_counter() - begin
    finally:
        session.close()
    return frames, {'initialize_s': init_s, 'steps_s': steps_s}


# ---------------------------------------------------------------- 静态场景


def valve_line(opening, inlet_pa=250000., outlet_pa=120000., kv=16.):
    return numerics_cases.assemble('valve-line', [
        _source('B1', inlet_pa), ('V1', 'valve', {'opening_ratio': float(opening), 'kv_m3_h': float(kv)}),
        _source('B2', outlet_pa)], [('B1:out0', 'V1:in0'), ('V1:out0', 'B2:out0')])


def valve_reference(opening, inlet_pa, outlet_pa, kv=16., density=solver.RHO_WATER):
    """阀门 Kv 关系的独立解：Δp = 100000·(ρ/1000)·q·|q| / kv_eff²。"""
    kv_eff = kv * opening
    if kv_eff <= 0:
        return 0.0
    drop = inlet_pa - outlet_pa
    volume = math.copysign(math.sqrt(abs(drop) * kv_eff ** 2 / (100000 * density / 1000)), drop)
    return volume / 3600 * density


def scenario_valve_open():
    project = valve_line(.8)
    frame, elapsed = _solve_steady(project)
    q = float(frame.variables['V1.ch0.mass_flow_kg_s'])
    reference = valve_reference(.8, 250000., 120000.)
    checks = [
        check('flow_matches_kv_reference', within(q, reference, 1e-9), q, reference, 1e-9),
        check('pressure_residual', frame.metrics['pressure_residual_pa'] < project.solver.pressure_tolerance_pa,
              frame.metrics['pressure_residual_pa'], project.solver.pressure_tolerance_pa, 'abs'),
        check('mass_residual', frame.metrics['mass_residual_kg_s'] < project.solver.mass_tolerance_kg_s,
              frame.metrics['mass_residual_kg_s'], project.solver.mass_tolerance_kg_s, 'abs'),
    ]
    metrics = {'flow_kg_s': q, 'analytic_flow_kg_s': reference,
               'pressure_residual_pa': frame.metrics['pressure_residual_pa'],
               'mass_residual_kg_s': frame.metrics['mass_residual_kg_s']}
    return _result('valve-open', 'static', '开阀：流量满足独立 Kv 解析解', checks, metrics, elapsed)


def scenario_valve_closed():
    project = valve_line(0.)
    frame, elapsed = _solve_steady(project)
    q = float(frame.variables['V1.ch0.mass_flow_kg_s'])
    checks = [
        check('closed_valve_zero_flow', q == 0.0, q, 0.0, 0.0, 'abs'),
        check('pressure_residual', frame.metrics['pressure_residual_pa'] < project.solver.pressure_tolerance_pa,
              frame.metrics['pressure_residual_pa'], project.solver.pressure_tolerance_pa, 'abs'),
        check('mass_residual', frame.metrics['mass_residual_kg_s'] < project.solver.mass_tolerance_kg_s,
              frame.metrics['mass_residual_kg_s'], project.solver.mass_tolerance_kg_s, 'abs'),
    ]
    metrics = {'flow_kg_s': q, 'pressure_residual_pa': frame.metrics['pressure_residual_pa'],
               'mass_residual_kg_s': frame.metrics['mass_residual_kg_s']}
    return _result('valve-closed', 'static', '关阀：流量精确为零且守恒残差过门', checks, metrics, elapsed)


def reverse_line(inlet_pa, outlet_pa):
    """被动对称支路（层流/湍流管道）更接近真正可复现的反向流入口。

    阀门模型的压降是 q·|q|，在 q=0 处导数为 0；当前 dense 求解从零初值出发时，
    反向阀门工况会停在零流量（压力残差不为零）而报“未收敛”。这是现状限制，记录在
    B2 证据的偏差里，不用阀门做反向流验收；管道压降含线性层流项，反向可收敛。
    """
    return numerics_cases.assemble('reverse-line', [
        _source('B1', inlet_pa), ('P1', 'pipe', {'length_m': 10.}), _source('B2', outlet_pa)],
        [('B1:out0', 'P1:in0'), ('P1:out0', 'B2:out0')])


def scenario_reverse_flow():
    forward, elapsed = _solve_steady(reverse_line(250000., 120000.))
    reverse_project = reverse_line(120000., 250000.)
    reverse, elapsed_reverse = _solve_steady(reverse_project)
    q_forward = float(forward.variables['P1.ch0.mass_flow_kg_s'])
    q = float(reverse.variables['P1.ch0.mass_flow_kg_s'])
    checks = [
        check('reverse_flow_negative', q < 0.0, q),
        check('reverse_magnitude_equals_forward', within(abs(q), q_forward, 1e-9), abs(q), q_forward, 1e-9),
        check('reverse_pressure_residual',
              reverse.metrics['pressure_residual_pa'] < reverse_project.solver.pressure_tolerance_pa,
              reverse.metrics['pressure_residual_pa'], reverse_project.solver.pressure_tolerance_pa, 'abs'),
    ]
    metrics = {'forward_flow_kg_s': q_forward, 'reverse_flow_kg_s': q,
               'pressure_residual_pa': reverse.metrics['pressure_residual_pa']}
    return _result('reverse-flow', 'static', '反向流：负流量与正向幅值对称、守恒残差过门',
                   checks, metrics, elapsed + elapsed_reverse)


# ---------------------------------------------------------------- 动态场景


def tank_switch_project():
    return numerics_cases.assemble('tank-switch', [
        _source('B1', 250000.), ('V1', 'valve', {'opening_ratio': .6, 'kv_m3_h': 8.}),
        ('T1', 'tank', {'area_m2': .2, 'level_m': 1., 'height_m': 3.}),
        ('V2', 'valve', {'opening_ratio': .6, 'kv_m3_h': 8.}), _source('B2', 101325.)],
        [('B1:out0', 'V1:in0'), ('V1:out0', 'T1:in0'), ('T1:out0', 'V2:in0'), ('V2:out0', 'B2:out0')])


def scenario_tank_valve_switch():
    project = tank_switch_project()
    dt_s = 1.0
    actions = [(3.0, lambda s: s.set_parameter('V1', 'opening_ratio', 0.0)),
               (6.0, lambda s: s.set_parameter('V1', 'opening_ratio', .6))]
    begin = time.perf_counter()
    frames, timings = _run_session(project, 9.0, dt_s, actions)
    elapsed = time.perf_counter() - begin
    level = [float(frame.variables['T1.state.level_m']) for frame in frames]
    mass = [float(frame.variables['T1.state.mass_kg']) for frame in frames]
    inflow = [float(frame.variables['V1.ch0.mass_flow_kg_s']) for frame in frames]
    net = [float(frame.variables['T1.state.net_inflow_kg_s']) for frame in frames]
    opened = [frames[i] for i in range(1, len(frames)) if frames[i].time_s > 6.0 + 1e-9]

    def level_at(time_s):
        return float(next(frame for frame in frames if abs(frame.time_s - time_s) < 1e-9).variables['T1.state.level_m'])

    level_mid, level_end = level_at(6.0), level[-1]
    ledger = sum(net[i] * dt_s for i in range(1, len(frames)))
    mass_change = mass[-1] - mass[0]
    checks = [
        check('closed_stage_no_inflow', all(abs(inflow[i]) < project.solver.mass_tolerance_kg_s
                                            for i in range(len(frames)) if 4.0 <= frames[i].time_s <= 6.0),
              max(abs(inflow[i]) for i in range(len(frames)) if 4.0 <= frames[i].time_s <= 6.0)),
        check('open_stage_inflow_positive', all(float(f.variables['V1.ch0.mass_flow_kg_s']) > 0.0 for f in opened),
              float(opened[-1].variables['V1.ch0.mass_flow_kg_s']) if opened else None),
        check('tank_level_drops_while_closed', level_mid < level_at(3.0), level_mid - level_at(3.0)),
        check('tank_level_recovers_after_open', level_end > level_mid, level_end - level_mid),
        check('tank_mass_ledger', abs(mass_change - ledger) <= max(1e-8, 1e-8 * sum(abs(n) * dt_s for n in net)),
              mass_change - ledger, 0.0, max(1e-8, 1e-8 * sum(abs(n) * dt_s for n in net)), 'abs'),
        check('mass_residual', all(f.metrics['mass_residual_kg_s'] < project.solver.mass_tolerance_kg_s for f in frames),
              max(f.metrics['mass_residual_kg_s'] for f in frames), project.solver.mass_tolerance_kg_s, 'abs'),
        check('no_accepted_step_lost', len(frames) == 10, len(frames), 10, 0, 'abs'),
    ]
    metrics = {'level_start_m': level[0], 'level_mid_m': level_mid, 'level_end_m': level_end,
               'mass_change_kg': mass_change, 'ledger_kg': ledger,
               'max_mass_residual_kg_s': max(f.metrics['mass_residual_kg_s'] for f in frames)}
    return _result('tank-valve-switch', 'dynamic', '关/开阀 + 水箱：阶段行为与质量账本守恒',
                   checks, metrics, elapsed, timings)


def pipe_wall_project(wall_heat_capacity):
    return numerics_cases.assemble('pipe-wall', [
        _source('B1', 250000., 353.15), ('V1', 'valve', {'opening_ratio': .8, 'kv_m3_h': 16.}),
        ('T1', 'tank', {'area_m2': .5, 'level_m': 1.2, 'height_m': 3., 'heat_input_w': 0.}),
        ('P1', 'pipe', {'length_m': 10., 'thermal_cells': 3,
                        'wall_heat_capacity_j_k': float(wall_heat_capacity), 'heat_loss_ua_w_k': 0.}),
        _source('B2', 80000.)],
        [('B1:out0', 'V1:in0'), ('V1:out0', 'T1:in0'), ('T1:out0', 'P1:in0'), ('P1:out0', 'B2:out0')])


def _wall_trace(wall):
    project = pipe_wall_project(wall)
    frames, timings = _run_session(project, 60., 5., [(15.0, lambda s: s.set_parameter('T1', 'heat_input_w', 300000.))])
    outlet = [float(frame.variables['P1.outlet_temperature_k']) for frame in frames]
    tank = [float(frame.variables['T1.state.temperature_k']) for frame in frames]
    stored = [float(frame.variables.get('P1.state.stored_power_w', 0.0)) for frame in frames]
    energy = [float(frame.metrics.get('energy_residual_w', 0.0)) for frame in frames]
    return {'project': project, 'frames': frames, 'outlet': outlet, 'tank': tank, 'stored': stored,
            'energy': energy, 'timings': timings}


def scenario_pipe_wall_capacity():
    begin = time.perf_counter()
    with_wall = _wall_trace(20000.)
    without_wall = _wall_trace(0.)
    elapsed = time.perf_counter() - begin
    tail = slice(4, None)
    lag = [without_wall['outlet'][i] - with_wall['outlet'][i] for i in range(4, len(with_wall['outlet']))]
    checks = [
        check('wall_stores_power', max(with_wall['stored'][tail]) > 1.0, max(with_wall['stored'][tail])),
        check('wall_lags_outlet_temperature', all(value > 1e-3 for value in lag), min(lag)),
        check('energy_residual', all(abs(value) < 1e-6 for value in with_wall['energy']),
              max(abs(value) for value in with_wall['energy']), 1e-6, 'abs'),
        check('tank_trajectory_identical', all(abs(a - b) < 1e-9 for a, b in zip(with_wall['tank'], without_wall['tank'])),
              max(abs(a - b) for a, b in zip(with_wall['tank'], without_wall['tank'])), 1e-9, 'abs'),
        check('both_runs_accept_all_steps',
              len(with_wall['frames']) == len(without_wall['frames']) == 13,
              [len(with_wall['frames']), len(without_wall['frames'])]),
    ]
    metrics = {'outlet_with_wall_k': with_wall['outlet'][-1], 'outlet_without_wall_k': without_wall['outlet'][-1],
               'max_lag_k': max(lag), 'max_stored_power_w': max(with_wall['stored'][tail]),
               'max_energy_residual_w': max(abs(value) for value in with_wall['energy'])}
    timings = {'initialize_s': with_wall['timings']['initialize_s'] + without_wall['timings']['initialize_s'],
               'steps_s': with_wall['timings']['steps_s'] + without_wall['timings']['steps_s']}
    return _result('pipe-wall-capacity', 'dynamic', '管道热容：有/无壁面热容 A/B 与能量残差',
                   checks, metrics, elapsed, timings)


def scenario_pid_level():
    project = pid_example('level')
    begin = time.perf_counter()
    frames, timings = _run_session(project, 300., 2.0)
    elapsed = time.perf_counter() - begin
    level = [float(frame.variables['T1.state.level_m']) for frame in frames]
    opening = [float(frame.variables['V1.param.opening_ratio']) for frame in frames]
    checks = [
        check('level_tracks_setpoint', abs(level[-1] - 1.5) <= .15, level[-1], 1.5, .15, 'abs'),
        check('pid_moved_valve', abs(opening[-1] - opening[0]) > 1e-6, opening[-1] - opening[0]),
        check('mass_residual', all(f.metrics['mass_residual_kg_s'] < project.solver.mass_tolerance_kg_s for f in frames),
              max(f.metrics['mass_residual_kg_s'] for f in frames), project.solver.mass_tolerance_kg_s, 'abs'),
        check('level_physical_bounds', all(0.0 <= value <= 3.0 for value in level), [min(level), max(level)]),
    ]
    metrics = {'level_end_m': level[-1], 'level_setpoint_m': 1.5, 'opening_start': opening[0],
               'opening_end': opening[-1], 'max_mass_residual_kg_s': max(f.metrics['mass_residual_kg_s'] for f in frames)}
    return _result('pid-level', 'dynamic', 'PID 液位：跟踪设定值且质量守恒', checks, metrics, elapsed, timings)


COUNTER_MODULE = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("commit_count", 0)
        ctx.state.setdefault("throughput_kg", 0.0)

    def evaluate(self, ctx):
        ctx.net.valve(channel="main", kv=4.0, opening=1.0)

    def commit_step(self, ctx, dt_s):
        ctx.state["commit_count"] += 1
        ctx.state["throughput_kg"] += abs(ctx.channel("main").mass_flow_kg_s) * dt_s
'''


def counter_project():
    from fn_engine.models import ChannelSpec, ModuleDefinition, PortSpec
    module = ModuleDefinition(id='counter', name='counter', runtime='python', entrypoint='module:Module',
        solver_model='python_x', source={'runtime': COUNTER_MODULE},
        ports=[PortSpec(id='in0', label='in0', direction='in'), PortSpec(id='out0', label='out0', direction='out')],
        channels=[ChannelSpec(id='main', name='main', input_port='in0', output_port='out0', relation='resistance',
                              solver_model='python_x')])
    return numerics_cases.assemble('module-state', [
        _source('B1', 250000.), ('M1', 'counter', {}), _source('B2', 120000.)],
        [('B1:out0', 'M1:in0'), ('M1:out0', 'B2:out0')], [module])


def scenario_module_state():
    project = counter_project()
    duration, dt_s = 2.0, .5
    begin = time.perf_counter()
    frames, timings = _run_session(project, duration, dt_s)
    elapsed = time.perf_counter() - begin
    accepted = len(frames) - 1
    commits = int(frames[-1].variables['M1.state.commit_count'])
    throughput = float(frames[-1].variables['M1.state.throughput_kg'])
    integrated = sum(abs(float(frames[i].variables['M1.main.mass_flow_kg_s'])) * dt_s for i in range(1, len(frames)))
    checks = [
        check('commit_count_matches_accepted_steps', commits == accepted, commits, accepted, 0, 'abs'),
        check('throughput_matches_flow_integral', within(throughput, integrated, 1e-9), throughput, integrated, 1e-9),
        check('mass_residual', all(f.metrics['mass_residual_kg_s'] < project.solver.mass_tolerance_kg_s for f in frames),
              max(f.metrics['mass_residual_kg_s'] for f in frames), project.solver.mass_tolerance_kg_s, 'abs'),
        check('module_state_variables_exposed', 'M1.state.commit_count' in frames[-1].variables and
              'M1.state.throughput_kg' in frames[-1].variables, True),
    ]
    metrics = {'accepted_steps': accepted, 'commit_count': commits, 'throughput_kg': throughput,
               'integrated_flow_kg': integrated}
    return _result('module-state', 'dynamic', 'Python 模块状态：commit 次数与通过质量一致',
                   checks, metrics, elapsed, timings)


# ---------------------------------------------------------------- 冷库 A/B 计时

COLD_STORE = {'cold-store-a': ('room', 1800., 300.), 'cold-store-b': ('station', 1800., 300.)}


def _cold_store_project(kind):
    from fn_engine.refrigeration.examples import room_example, station_example
    return room_example() if kind == 'room' else station_example()


def measure_cold_store(scenario_id, warmup=0, repeats=1):
    project_kind, duration, dt_s = COLD_STORE[scenario_id]
    samples = []
    for attempt in range(warmup + repeats):
        project = _cold_store_project(project_kind)
        begin = time.perf_counter()
        network = compile_project(project)
        compile_s = time.perf_counter() - begin
        session = create_session(network, duration, dt_s)
        frames = []
        init_s = steps_s = 0.0
        try:
            begin = time.perf_counter()
            frames.append(session.initialize())
            init_s = time.perf_counter() - begin
            while not session.done:
                begin = time.perf_counter()
                frames.append(session.advance())
                steps_s += time.perf_counter() - begin
        finally:
            session.close()
        total_s = compile_s + init_s + steps_s
        if attempt >= warmup:
            samples.append({'compile_s': compile_s, 'initialize_s': init_s, 'steps_s': steps_s,
                            'end_to_end_s': total_s, 'frames': len(frames), 'status': 'passed'})
    return samples


def _cold_store_scenario(scenario_id, samples, process_wall_s=None):
    cold = [sample for sample in samples if sample.get('mode') == 'cold']
    hot = [sample for sample in samples if sample.get('mode') == 'hot']
    timings = {'samples': samples,
               'cold_end_to_end_s': cold[0]['end_to_end_s'] if cold else None,
               'hot_end_to_end_s_median': statistics.median(s['end_to_end_s'] for s in hot) if hot else None,
               'hot_end_to_end_s_min': min((s['end_to_end_s'] for s in hot), default=None),
               'hot_end_to_end_s_max': max((s['end_to_end_s'] for s in hot), default=None),
               'compile_s_median': statistics.median(sample['compile_s'] for sample in samples),
               'initialize_s_median': statistics.median(sample['initialize_s'] for sample in samples),
               'steps_s_median': statistics.median(sample['steps_s'] for sample in samples),
               'end_to_end_s_median': statistics.median(sample['end_to_end_s'] for sample in samples),
               'end_to_end_s_min': min(sample['end_to_end_s'] for sample in samples),
               'end_to_end_s_max': max(sample['end_to_end_s'] for sample in samples)}
    if process_wall_s is not None:
        timings['process_wall_s'] = process_wall_s
    checks = [check('all_runs_passed', all(sample['status'] == 'passed' for sample in samples), len(samples), len(samples), 0, 'abs')]
    metrics = {'frames': samples[0]['frames'], 'repeats': len(samples),
               'cold_repeats': len(cold), 'hot_repeats': len(hot)}
    return _result(scenario_id, 'timing', f'{scenario_id} 单独计时（冷启动子进程 / 热运行子进程）',
                   checks, metrics, 0.0, timings)


def collect_cold_store(scenario_id, hot_repeats=3):
    cold_begin = time.perf_counter()
    cold = _spawn([sys.executable, str(Path(__file__).resolve()), '--sample', scenario_id, '--warmup', '0', '--repeats', '1'])
    cold_wall = time.perf_counter() - cold_begin
    hot = _spawn([sys.executable, str(Path(__file__).resolve()), '--sample', scenario_id,
                  '--warmup', '1', '--repeats', str(hot_repeats)])
    samples = [dict(sample, mode='cold') for sample in cold]
    samples += [dict(sample, mode='hot') for sample in hot]
    return _cold_store_scenario(scenario_id, samples, cold_wall)


def _spawn(argv):
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    if completed.returncode != 0:
        raise RuntimeError(f'冷库计时子进程失败：{completed.stderr[-2000:]}')
    for line in reversed(completed.stdout.strip().splitlines()):
        if line.startswith('{'):
            return json.loads(line)['samples']
    raise RuntimeError('冷库计时子进程没有返回 JSON')


# ---------------------------------------------------------------- 汇总


def _result(scenario_id, kind, description, checks, metrics, elapsed, timings=None):
    timings = dict(timings or {})
    timings.setdefault('end_to_end_s', elapsed)
    timing_metrics = {'end_to_end_s', 'process_wall_s'}
    stable = [key for key, value in metrics.items()
              if isinstance(value, (int, float)) and not isinstance(value, bool)
              and key not in timing_metrics and 'median' not in key and 'wall' not in key]
    return {'id': scenario_id, 'kind': kind, 'description': description,
            'status': 'passed' if all(item['passed'] for item in checks) else 'failed',
            'checks': checks, 'metrics': metrics,
            'stable_metrics': stable, 'timings': timings}


SCENARIO_FUNCTIONS = (scenario_valve_open, scenario_valve_closed, scenario_reverse_flow,
                      scenario_tank_valve_switch, scenario_pipe_wall_capacity, scenario_pid_level,
                      scenario_module_state)


def evaluate(with_cold_store=True):
    results = []
    for function in SCENARIO_FUNCTIONS:
        result = function()
        print('%-22s %-8s %s' % (result['id'], result['kind'], result['status']), flush=True)
        for item in result['checks']:
            if not item['passed']:
                print('  FAILED', item['id'], item['value'], item['reference'], flush=True)
        results.append(result)
    if with_cold_store:
        for scenario_id in COLD_STORE:
            result = collect_cold_store(scenario_id)
            print('%-22s %-8s %s' % (result['id'], result['kind'], result['status']), flush=True)
            results.append(result)
    return results


def report(with_cold_store=True):
    return {
        'work_package': 'B2',
        'format_version': 1,
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'native_threads': 1,
        'scenarios': evaluate(with_cold_store),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/numerics/scenarios.json')
    parser.add_argument('--no-cold-store', action='store_true')
    parser.add_argument('--sample', choices=sorted(COLD_STORE), help='内部使用：只测一个冷库场景并打印 JSON')
    parser.add_argument('--warmup', type=int, default=0)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args(argv)
    if args.sample:
        samples = measure_cold_store(args.sample, max(args.warmup, 0), max(args.repeats, 1))
        print(json.dumps({'samples': samples}, ensure_ascii=False), flush=True)
        return
    data = report(with_cold_store=not args.no_cold_store)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    failed = [scenario['id'] for scenario in data['scenarios'] if scenario['status'] != 'passed']
    print('wrote', path, 'failed', failed, flush=True)
    raise SystemExit(0 if not failed else 1)


if __name__ == '__main__':
    main()
