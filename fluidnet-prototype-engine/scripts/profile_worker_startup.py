"""W0/W1 Worker 启动剖析：import / Worker 初始化 / 首次 evaluate / 首次物性 / 首个成功时间步。

四类 Worker：control（控制脚本）、module（普通 Python 模块）、property（evaluate 内调用物性）、
batch（一次处理多个实例的批量 Worker）。

测量分两层：
1. 进程层：解释器启动、`import fn_engine.worker` 墙钟、`-X importtime` 分解。
2. Worker 层：新进程内首次响应（含 spawn/import/initialize）、首次 evaluate、首次 commit、
   首次物性调用（property 模块）、批量首次调用、首个成功时间步（新进程内 compile→solve）。

用法（仓库根目录）：

    python scripts/profile_worker_startup.py --output artifacts/numerics/<commit>/W0/startup.json

脚本只写 `--output`；测量完成即关闭所有 Worker，不留下子进程。
"""
import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

CONTROL_SCRIPT = '''def initialize(ctx):
    ctx.state.setdefault("samples", 0)


def step(ctx, dt_s):
    ctx.state["samples"] += 1


def finalize(ctx):
    pass
'''

PROPERTY_MODULE = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("calls", 0)

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        state = ctx.fluid.state_pt(inlet.pressure_pa, inlet.temperature_k)
        ctx.net.valve(channel="main", kv=4.0, opening=1.0, density_kg_m3=state.density_kg_m3)
        ctx.var("rho_first", state.density_kg_m3)

    def commit_step(self, ctx, dt_s):
        ctx.state["calls"] += 1
'''


def stats(samples):
    values = [value for value in samples if isinstance(value, (int, float))]
    return {'samples': values,
            'median': statistics.median(values) if values else None,
            'min': min(values) if values else None,
            'max': max(values) if values else None,
            'failures': len(samples) - len(values)}


def time_block(function, repeats):
    samples = []
    for _ in range(repeats):
        try:
            samples.append(function())
        except Exception as error:  # 单个失败不丢整次剖析
            samples.append(f'{type(error).__name__}: {error}'[:500])
    return stats(samples)


def dict_stats(rows):
    """多字段样本（如首个时间步的 compile/solve 分解）按字段汇总中位/最小/最大。

    失败样本以 {'error': ...} 形式保留计数，不参与数值统计。
    """
    passed = [row for row in rows if 'error' not in row]
    report = {'samples': len(rows), 'failures': len(rows) - len(passed)}
    if not passed:
        report['errors'] = [row['error'] for row in rows]
        return report
    for key in passed[0]:
        values = [row[key] for row in passed if isinstance(row.get(key), (int, float))]
        if values:
            report[key] = {'median': statistics.median(values), 'min': min(values), 'max': max(values)}
    return report


def run_process(argv, repeats, cwd=None):
    def once():
        begin = time.perf_counter()
        completed = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, timeout=300)
        elapsed = time.perf_counter() - begin
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr[-500:])
        return elapsed

    return time_block(once, repeats)


def importtime_breakdown(cwd=None):
    completed = subprocess.run([sys.executable, '-X', 'importtime', '-c', 'import fn_engine.worker'],
                               capture_output=True, text=True, cwd=cwd, timeout=300)
    rows = []
    for line in completed.stderr.splitlines():
        if not line.startswith('import time:'):
            continue
        _, _, payload = line.partition('import time:')
        parts = [part.strip() for part in payload.split('|')]
        if len(parts) != 3:
            continue
        try:
            cumulative = int(parts[1])
        except ValueError:
            continue
        if parts[2]:
            rows.append({'package': parts[2], 'cumulative_us': cumulative})
    top = {}
    for row in rows:
        root = row['package'].split('.')[0]
        top[root] = max(top.get(root, 0), row['cumulative_us'])
    ranked = sorted(({'package': key, 'cumulative_us': value} for key, value in top.items()),
                    key=lambda item: item['cumulative_us'], reverse=True)
    return {'total_rows': len(rows), 'top': ranked[:20],
            'fn_engine_us': top.get('fn_engine'), 'coolprop_us': top.get('CoolProp'),
            'pydantic_us': top.get('pydantic'), 'numpy_us': top.get('numpy'), 'scipy_us': top.get('scipy')}


def probe_definition(kind):
    from fn_engine.models import ChannelSpec, ModuleDefinition, PortSpec

    if kind in ('module', 'batch', 'python'):
        from fn_engine.packages import load_module_package
        return load_module_package(ROOT / 'modules' / 'programmable_valve')
    return ModuleDefinition(id='property-probe', name='property-probe', runtime='python',
                            entrypoint='module:Module', solver_model='python_x',
                            source={'runtime': PROPERTY_MODULE},
                            ports=[PortSpec(id='in0', label='in0', direction='in'),
                                   PortSpec(id='out0', label='out0', direction='out')],
                            channels=[ChannelSpec(id='main', name='main', input_port='in0', output_port='out0',
                                                  relation='resistance', solver_model='python_x')])


def trial_port(definition):
    from fn_engine.models import PortState

    inlet = next(port for port in definition.ports if port.direction == 'in')
    # 带上密度/黏度/比热：普通模块 Worker 的 evaluate 不必为缺失物性再查一次 CoolProp，
    # 这样 module/batch 与 property（显式调用 ctx.fluid.state_pt）才是真正可区分的两类。
    return {inlet.id: PortState(pressure_pa=250000., temperature_k=293.15, enthalpy_j_kg=84000.,
                                density_kg_m3=998.2, viscosity_pa_s=.001002, specific_heat_j_kg_k=4184.)}


def probe_parameters(definition):
    return {parameter.id: parameter.default for parameter in definition.parameters}


def worker_phase_samples(kind):
    """单次新 Worker 生命周期内的时间点；返回秒数分解。"""
    from fn_engine.models import CommitStepRequest, ControlScript, EvaluateRequest, FluidConfig, InitializeRequest
    from fn_engine.runtime import WorkerProcess, module_content_hash

    definition = probe_definition(kind)
    fluid = FluidConfig()
    # 参数必须带模块默认值：模块 evaluate 会读 ctx.parameter(...)，缺省会得到非有限值而报错。
    worker = WorkerProcess(definition, probe_parameters(definition), fluid, timeout_s=120)
    phases = {}
    try:
        if kind == 'control':
            script = ControlScript(id='probe', source=CONTROL_SCRIPT, enabled=True)
            begin = time.perf_counter()
            response = worker._request({'action': 'control_initialize', 'definition': script.model_dump(mode='json'),
                                        'values': {}, 'state': {}, 'time_s': 0.})
            phases['first_response_s'] = time.perf_counter() - begin
            begin = time.perf_counter()
            worker._request({'action': 'control_step', 'values': {}, 'state': response.get('state', {}),
                             'time_s': 0., 'dt_s': 1.})
            phases['first_evaluate_s'] = time.perf_counter() - begin
            return phases
        request = InitializeRequest(run_id='probe', instance_id=definition.id,
                                    package={'module_id': definition.id, 'version': f'{definition.version}.0.0',
                                             'content_hash': definition.content_hash or module_content_hash(definition)},
                                    parameters=probe_parameters(definition), fluid=fluid,
                                    port_fluids={}, initial_state={})
        definition_json = definition.model_dump(mode='json')
        begin = time.perf_counter()
        if kind == 'batch':
            item = {'action': 'initialize', 'definition': definition_json,
                    'request': request.model_dump(mode='json')}
            worker._request({'action': 'batch', 'items': {f'k{i}': item for i in range(4)}})
            phases['first_response_s'] = time.perf_counter() - begin
            evaluate = EvaluateRequest(run_id='probe', instance_id=definition.id, iteration_id=0, time_s=0.,
                                       trial_ports=trial_port(definition), readonly_state={})
            item = {'action': 'evaluate', 'request': evaluate.model_dump(mode='json')}
            begin = time.perf_counter()
            worker._request({'action': 'batch', 'items': {f'k{i}': item for i in range(4)}})
            phases['first_evaluate_s'] = time.perf_counter() - begin
            return phases
        worker.initialize()
        phases['first_response_s'] = time.perf_counter() - begin
        evaluate = EvaluateRequest(run_id='probe', instance_id=definition.id, iteration_id=0, time_s=0.,
                                   trial_ports=trial_port(definition), readonly_state={})
        begin = time.perf_counter()
        worker.evaluate(evaluate)
        phases['first_evaluate_s'] = time.perf_counter() - begin
        commit = CommitStepRequest(run_id='probe', instance_id=definition.id, time_s=1., dt_s=1.)
        begin = time.perf_counter()
        worker.commit_step(commit)
        phases['first_commit_s'] = time.perf_counter() - begin
        if kind == 'property':
            phases['first_property_s'] = phases['first_evaluate_s']
        return phases
    finally:
        worker.close(force=True)


def phase_probe(kind, repeats):
    results = []
    for _ in range(repeats):
        try:
            results.append(worker_phase_samples(kind))
        except Exception as error:
            results.append({'error': f'{type(error).__name__}: {error}'[:500]})
    report = {}
    for key in ('first_response_s', 'first_evaluate_s', 'first_commit_s', 'first_property_s'):
        report[key] = stats([row[key] for row in results if key in row])
    # 首个成功步 = 首次响应 + 首次 evaluate（有 commit 时再加 commit），单位秒。
    report['first_success_s'] = stats([
        row['first_response_s'] + row.get('first_evaluate_s', 0.) + row.get('first_commit_s', 0.)
        for row in results if 'first_response_s' in row])
    report['failures'] = sum(1 for row in results if 'error' in row)
    if report['failures']:
        report['errors'] = [row['error'] for row in results if 'error' in row]
    return report


def timestep_sample(kind, cwd=None):
    """新进程内：compile→solve 的 Python 模块网络，统计首个成功时间步墙钟。

    子进程输出写临时文件而不是管道：模块 Worker 是孙进程，管道句柄可能被继承，
    直接子进程退出后父进程仍可能等不到 EOF。
    """
    import tempfile

    begin = time.perf_counter()
    with tempfile.TemporaryDirectory() as folder:
        stdout_path, stderr_path = Path(folder) / 'out.txt', Path(folder) / 'err.txt'
        with open(stdout_path, 'w', encoding='utf-8') as stdout, open(stderr_path, 'w', encoding='utf-8') as stderr:
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--timestep-sample', kind],
                                       stdout=stdout, stderr=stderr, text=True, cwd=cwd, timeout=600)
        wall = time.perf_counter() - begin
        text_out = stdout_path.read_text(encoding='utf-8', errors='replace')
        text_err = stderr_path.read_text(encoding='utf-8', errors='replace')
    if completed.returncode != 0:
        raise RuntimeError(text_err[-800:])
    payload = json.loads(text_out.strip().splitlines()[-1])
    return {'process_wall_s': wall, **payload}


def timestep_network(kind):
    import numerics_cases
    from fn_engine import solver
    from fn_engine.compiler import compile_project

    project = numerics_cases.series_project(30, 0. if kind == 'no-python' else .25)
    project.solver.hydraulic_method = 'sparse'
    begin = time.perf_counter()
    network = compile_project(project)
    compile_s = time.perf_counter() - begin
    begin = time.perf_counter()
    frame = solver.solve_steady(network)
    solve_s = time.perf_counter() - begin
    return {'compile_s': compile_s, 'solve_s': solve_s, 'process_internal_s': compile_s + solve_s,
            'pressure_residual_pa': frame.metrics['pressure_residual_pa'],
            'mass_residual_kg_s': frame.metrics['mass_residual_kg_s']}


def environment():
    load = {'cpu_percent': None, 'python_processes': None, 'memory_percent': None}
    try:
        import psutil
        load['cpu_percent'] = psutil.cpu_percent(interval=.5)
        load['python_processes'] = sum(1 for process in psutil.process_iter(['name'])
                                       if process.info.get('name', '').lower().startswith('python'))
        load['memory_percent'] = psutil.virtual_memory().percent
    except Exception:
        pass
    return {'python': sys.version.split()[0], 'platform': platform.platform(),
            'cpu': platform.processor(), 'native_threads': 1, 'cwd': str(ROOT),
            'git_commit': _git_commit(),
            'load': load}


def _git_commit():
    try:
        completed = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, timeout=10)
        return completed.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/numerics/W0/startup.json')
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--cwd', default=None, help='子进程工作目录（基线快照剖析时用）')
    parser.add_argument('--timestep-sample', choices=('python', 'no-python'))
    args = parser.parse_args(argv)
    if args.timestep_sample:
        print(json.dumps(timestep_network(args.timestep_sample), ensure_ascii=False), flush=True)
        return 0

    cwd = args.cwd or str(ROOT)
    begin = time.perf_counter()
    interpreter = run_process([sys.executable, '-c', 'pass'], args.repeats, cwd)
    imported = run_process([sys.executable, '-c', 'import fn_engine.worker'], args.repeats, cwd)
    report = {'work_package': 'W0', 'format_version': 1,
              'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'environment': environment(), 'repeats': args.repeats, 'cwd': cwd,
              'process': {'interpreter_s': interpreter, 'import_worker_s': imported,
                          'importtime': importtime_breakdown(cwd)},
              'workers': {}, 'timestep': {}}
    report['process']['import_only_s'] = stats([
        max(0.0, imported_value - interpreter['median'])
        for imported_value in imported['samples']])
    for kind in ('control', 'module', 'property', 'batch'):
        report['workers'][kind] = phase_probe(kind, args.repeats)
        print(kind, {key: (round(value['median'], 4) if value['median'] is not None else None)
                     for key, value in report['workers'][kind].items() if isinstance(value, dict)}, flush=True)
    def timestep_rows(kind):
        rows = []
        for _ in range(args.repeats):
            try:
                rows.append(timestep_sample(kind, cwd))
            except Exception as error:
                rows.append({'error': f'{type(error).__name__}: {error}'[:800]})
        return rows

    report['timestep'] = {'no-python': dict_stats(timestep_rows('no-python')),
                          'python-25-percent': dict_stats(timestep_rows('python'))}
    report['elapsed_s'] = time.perf_counter() - begin
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('wrote', path, 'elapsed %.1fs' % report['elapsed_s'], flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
