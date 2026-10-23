"""L0：热力层与 node 外循环的耗时占比 / 迭代分布 / 温度与密度轨迹。

选取大温差、多工质、强换热慢例（Water + MEG30 双回路、强 UA 换热器、node 物性耦合、
带管道热容的动态工况），回答“热力/外循环是否是主要端到端耗时”。

测量分层（重叠计时不相加）：compile、hydraulic、thermal、coupling 外循环（含 hydraulic+thermal
重复）、serialize、其他；同时统计 thermal_iterations / coupling_iterations 分布、物性调用次数、
温度跨度和密度范围。

用法（仓库根目录）：

    python scripts/profile_thermal.py --output artifacts/numerics/<commit>/L0/thermal.json
"""
import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numerics_cases
from fn_engine import properties, solver
from fn_engine.compiler import compile_project
from fn_engine.models import CircuitFluid, Connection, Endpoint, FluidConfig, ModuleInstance, Project

MEG30 = numerics_cases.MEG30
PROPERTY_METHODS = ('state_pt', 'state_ph', 'state_ps', 'state_pq', 'state_tq', 'state_du',
                    'saturation_t', 'saturation_p', 'limits')


def instance(instance_id, module_id, parameters=None):
    return ModuleInstance(id=instance_id, module_id=module_id, name=instance_id, parameters=parameters or {})


def link(cid, source, target):
    def point(text):
        instance_id, port_id = text.split(':')
        return Endpoint(instance_id=instance_id, port_id=port_id)

    return Connection(id=cid, source=point(source), target=point(target))


def assemble(name, nodes, edges, circuit_fluids=()):
    catalog = numerics_cases.catalog_map()
    kinds = sorted({kind for _, kind, _ in nodes})
    return Project(id=name, name=name, modules=[catalog[kind] for kind in kinds],
                   instances=[instance(i, kind, params) for i, kind, params in nodes],
                   connections=[link(f'e{n}', a, b) for n, (a, b) in enumerate(edges)],
                   circuit_fluids=list(circuit_fluids))


def strong_exchanger(coupling='node', ua=20000., pipes=6):
    """强换热双回路：大 UA + 长管段 + node 物性耦合，尽量压出 thermal/外循环迭代。"""
    nodes = [('BH', 'source', {'pressure_pa': 400000., 'temperature_k': 373.15}),
             ('BC', 'source', {'pressure_pa': 400000., 'temperature_k': 263.15}),
             ('HX', 'exchanger', {'ua_w_k': ua, 'loss_coefficient': 2.0}),
             ('SH', 'source', {'pressure_pa': 300000., 'temperature_k': 343.15}),
             ('SC', 'source', {'pressure_pa': 300000., 'temperature_k': 293.15})]
    edges = [('BH:out0', 'HP0:in0')]
    for i in range(pipes):
        nodes.append((f'HP{i}', 'pipe', {'length_m': 20., 'heat_loss_ua_w_k': 0.}))
        edges.append((f'HP{i}:out0', f'HP{i + 1}:in0' if i + 1 < pipes else 'HX:in0'))
    edges.append(('HX:out0', 'SH:out0'))
    edges.append(('BC:out0', 'CP0:in0'))
    for i in range(pipes):
        nodes.append((f'CP{i}', 'pipe', {'length_m': 20., 'heat_loss_ua_w_k': 0.}))
        edges.append((f'CP{i}:out0', f'CP{i + 1}:in0' if i + 1 < pipes else 'HX:in1'))
    edges.append(('HX:out1', 'SC:out0'))
    project = assemble('strong-exchanger', nodes, edges,
                       [CircuitFluid(id='brine', anchor=Endpoint(instance_id='BC', port_id='out0'),
                                     fluid=FluidConfig(fluid=MEG30))])
    project.solver.property_coupling = coupling
    project.solver.hydraulic_method = 'sparse'
    return project


def thermal_heavy(pipes=20, cells=4):
    """热力重例：多段带热容/散热管段，热力层要做 cell 链与壁面松弛。"""
    nodes = [('BH', 'source', {'pressure_pa': 400000., 'temperature_k': 353.15})]
    edges = [('BH:out0', 'P0:in0')]
    for i in range(pipes):
        nodes.append((f'P{i}', 'pipe', {'length_m': 5., 'thermal_cells': cells,
                                        'wall_heat_capacity_j_k': 8000., 'heat_loss_ua_w_k': 600.,
                                        'ambient_temperature_k': 293.15}))
        edges.append((f'P{i}:out0', f'P{i + 1}:in0' if i + 1 < pipes else 'B2:out0'))
    nodes.append(('B2', 'source', {'pressure_pa': 200000., 'temperature_k': 293.15}))
    project = assemble('thermal-heavy', nodes, edges)
    project.solver.hydraulic_method = 'sparse'
    return project


CASES = {
    'dual-loop-medium': lambda: numerics_cases.build_project('thermal-dual-loop', 'medium'),
    'dual-loop-large': lambda: numerics_cases.build_project('thermal-dual-loop', 'large'),
    'strong-hx-node-coupling': lambda: strong_exchanger('node', 20000., 6),
    'strong-hx-reference': lambda: strong_exchanger('reference', 20000., 6),
    'thermal-heavy-cells': lambda: thermal_heavy(),
}


def temperature_density_trajectory(frame):
    temperatures = [(key, value) for key, value in frame.variables.items()
                    if key.endswith('.temperature_k') and isinstance(value, (int, float))]
    densities = [(key, value) for key, value in frame.variables.items()
                 if key.endswith('.density_kg_m3') and isinstance(value, (int, float))]
    temps = [value for _, value in temperatures]
    rhos = [value for _, value in densities]
    return {
        'temperature_min_k': min(temps) if temps else None,
        'temperature_max_k': max(temps) if temps else None,
        'temperature_span_k': (max(temps) - min(temps)) if temps else None,
        'density_min_kg_m3': min(rhos) if rhos else None,
        'density_max_kg_m3': max(rhos) if rhos else None,
        'density_span_kg_m3': (max(rhos) - min(rhos)) if rhos else None,
        'sample_temperatures': dict(sorted(temperatures, key=lambda item: item[0])[:12]),
    }


def instrument():
    """替换 solver/properties 的可观测入口，返回计时器与计数器和 restore 函数。"""
    state = {'hydraulic_s': 0., 'thermal_s': 0., 'property_calls': {name: 0 for name in PROPERTY_METHODS}}
    originals = {'solve_thermal': solver.solve_thermal, 'solve_hydraulics': solver._solve_hydraulics}

    def timed(name):
        def wrapper(*args, **kwargs):
            begin = time.perf_counter()
            try:
                return originals[name](*args, **kwargs)
            finally:
                state['hydraulic_s' if name == 'solve_hydraulics' else 'thermal_s'] += time.perf_counter() - begin
        return wrapper

    solver.solve_thermal = timed('solve_thermal')
    solver._solve_hydraulics = timed('solve_hydraulics')
    property_originals = {name: getattr(properties.CoolPropPropertyService, name) for name in PROPERTY_METHODS}
    for name in PROPERTY_METHODS:
        def wrapper(self, *args, _name=name, _original=property_originals[name], **kwargs):
            state['property_calls'][_name] += 1
            return _original(self, *args, **kwargs)
        setattr(properties.CoolPropPropertyService, name, wrapper)

    def restore():
        solver.solve_thermal = originals['solve_thermal']
        solver._solve_hydraulics = originals['solve_hydraulics']
        for name, original in property_originals.items():
            setattr(properties.CoolPropPropertyService, name, original)
    return state, restore


def measure_steady(case_id, builder, repeats):
    project = builder()
    begin = time.perf_counter()
    network = compile_project(project)
    compile_s = time.perf_counter() - begin
    rows, iterations, frame = [], [], None
    for _ in range(repeats):
        state, restore = instrument()
        begin = time.perf_counter()
        try:
            frame = solver.solve_steady(network)
        finally:
            restore()
        total_s = time.perf_counter() - begin
        rows.append({'total_s': total_s, 'hydraulic_s': state['hydraulic_s'], 'thermal_s': state['thermal_s'],
                     'property_calls': sum(state['property_calls'].values()),
                     'iterations_hydraulic': frame.metrics.get('iterations'),
                     'iterations_thermal': frame.metrics.get('thermal_iterations'),
                     'coupling_iterations': frame.metrics.get('coupling_iterations')})
        iterations.append((frame.metrics.get('thermal_iterations'), frame.metrics.get('coupling_iterations')))
    return {'id': case_id, 'kind': 'steady', 'compile_s': compile_s, 'repeats': rows,
            'trajectory': temperature_density_trajectory(frame) if frame is not None else {},
            'residuals': {key: frame.metrics.get(key) for key in
                          ('pressure_residual_pa', 'mass_residual_kg_s', 'energy_residual_w', 'reference_heat_w')}
            if frame is not None else {},
            'iteration_pairs': iterations}


def measure_dynamic(case_id, project, duration_s, dt_s):
    begin = time.perf_counter()
    network = compile_project(project)
    compile_s = time.perf_counter() - begin
    state, restore = instrument()
    begin = time.perf_counter()
    try:
        frames = solver.solve_dynamic(network, duration_s, dt_s)
    finally:
        restore()
    total_s = time.perf_counter() - begin
    thermal_rates = [frame.metrics.get('thermal_iterations') for frame in frames[1:]]
    coupling = [frame.metrics.get('coupling_iterations') for frame in frames[1:]]
    return {'id': case_id, 'kind': 'dynamic', 'compile_s': compile_s, 'total_s': total_s,
            'hydraulic_s': state['hydraulic_s'], 'thermal_s': state['thermal_s'],
            'frames': len(frames), 'property_calls': sum(state['property_calls'].values()),
            'thermal_iterations': {'median': statistics.median(thermal_rates) if thermal_rates else None,
                                   'max': max(thermal_rates) if thermal_rates else None,
                                   'values': thermal_rates},
            'coupling_iterations': {'median': statistics.median(coupling) if coupling else None,
                                    'max': max(coupling) if coupling else None},
            'trajectory': temperature_density_trajectory(frames[-1]),
            'residuals': {key: frames[-1].metrics.get(key) for key in
                          ('pressure_residual_pa', 'mass_residual_kg_s', 'energy_residual_w')}}


def summarize(case):
    if case['kind'] == 'steady':
        totals = [row['total_s'] for row in case['repeats']]
        hydraulic = [row['hydraulic_s'] for row in case['repeats']]
        thermal = [row['thermal_s'] for row in case['repeats']]
        total = statistics.median(totals)
        return {'end_to_end_s_median': total, 'hydraulic_s_median': statistics.median(hydraulic),
                'thermal_s_median': statistics.median(thermal),
                'thermal_share': (statistics.median(thermal) / total) if total else None,
                'hydraulic_share': (statistics.median(hydraulic) / total) if total else None}
    total = case['total_s']
    return {'end_to_end_s': total, 'hydraulic_s': case['hydraulic_s'], 'thermal_s': case['thermal_s'],
            'thermal_share': (case['thermal_s'] / total) if total else None,
            'hydraulic_share': (case['hydraulic_s'] / total) if total else None}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/numerics/L0/thermal.json')
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args(argv)
    begin = time.perf_counter()
    cases = []
    for case_id, builder in CASES.items():
        case = measure_steady(case_id, builder, args.repeats)
        case['summary'] = summarize(case)
        cases.append(case)
        print(case_id, json.dumps(case['summary'], ensure_ascii=False),
              'iterations', case['iteration_pairs'], flush=True)
    dynamic_cases = (
        ('dual-loop-medium-dynamic', numerics_cases.build_project('thermal-dual-loop', 'medium')),
        ('thermal-heavy-dynamic', thermal_heavy()),
    )
    for case_id, dynamic_project in dynamic_cases:
        dynamic_case = measure_dynamic(case_id, dynamic_project, 30., 5.)
        dynamic_case['summary'] = summarize(dynamic_case)
        cases.append(dynamic_case)
        print(dynamic_case['id'], json.dumps(dynamic_case['summary'], ensure_ascii=False), flush=True)
    report = {'work_package': 'L0', 'format_version': 1,
              'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'python': sys.version.split()[0], 'platform': platform.platform(), 'native_threads': 1,
              'elapsed_s': time.perf_counter() - begin, 'cases': cases}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('wrote', path, 'elapsed %.1fs' % report['elapsed_s'], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
