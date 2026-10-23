"""B3 固定环境完整基线：冷启动 5 次、热跑 7 次，登记配置/重复/失败/哈希。

用法（仓库根目录）：

    python scripts/numerics_baseline.py --output artifacts/numerics/<commit>/B3/baseline.json
    python scripts/numerics_baseline.py --list                      # 只列出用例清单
    python scripts/numerics_baseline.py --only series,python-batch  # 复测子集

协议（计划 §3.2）：
- 冷启动 = 独立子进程内完成 import→compile→solve，记录子进程整体墙钟；共 5 次。
- 热运行 = 同一子进程内先预热 1 次，再重复 7 次。
- 报告中位数/最小/最大值/失败数，不报 P95（样本太少）。
- 记录提交、依赖版本、硬件、原生线程数、物性后端、进程/Worker 数。

脚本只写 ``--output`` 指定路径（通常为 gitignore 的 artifacts/），不改用户工作区。
"""
import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

COLD_REPEATS = 5
HOT_REPEATS = 7
HOT_WARMUP = 1

# 用例清单：kind=topology 用 numerics_cases 工厂；kind=legacy 用原 benchmark_scaling 入口。
CASES = [
    {'id': 'topology/series/small', 'kind': 'topology', 'family': 'series', 'tier': 'small'},
    {'id': 'topology/series/medium', 'kind': 'topology', 'family': 'series', 'tier': 'medium'},
    {'id': 'topology/series/large', 'kind': 'topology', 'family': 'series', 'tier': 'large'},
    {'id': 'topology/parallel/small', 'kind': 'topology', 'family': 'parallel', 'tier': 'small'},
    {'id': 'topology/parallel/medium', 'kind': 'topology', 'family': 'parallel', 'tier': 'medium'},
    {'id': 'topology/mesh/small', 'kind': 'topology', 'family': 'mesh', 'tier': 'small'},
    {'id': 'topology/mesh/medium', 'kind': 'topology', 'family': 'mesh', 'tier': 'medium'},
    {'id': 'topology/components/small', 'kind': 'topology', 'family': 'components', 'tier': 'small'},
    {'id': 'topology/components/medium', 'kind': 'topology', 'family': 'components', 'tier': 'medium'},
    {'id': 'topology/thermal-dual-loop/small', 'kind': 'topology', 'family': 'thermal-dual-loop', 'tier': 'small'},
    {'id': 'topology/thermal-dual-loop/medium', 'kind': 'topology', 'family': 'thermal-dual-loop', 'tier': 'medium'},
    {'id': 'topology/python-multiport/small', 'kind': 'topology', 'family': 'python-multiport', 'tier': 'small'},
    # python-multiport/medium 有 16 个 Python 实例；v0.5.0 每个实例顺序启动 Worker，单次运行约 8 s，
    # 冷 5 次 + 热 7 次的完整协议会单独耗掉数分钟且只反映 Worker 启动（W0/W1 主题），故不放进
    # B3 计时矩阵；其节点/支路/依赖计数见 B1，Worker 启动分解见 W0/W1。
    {'id': 'legacy/series-100-dense', 'kind': 'legacy', 'size': 100, 'python_fraction': 0., 'method': 'dense'},
    # dense 500/1000 的逐变量数值 Jacobian 成本很高（共享开发机上单次 30 s / 2 min 量级），
    # 完整 5+7 协议会独占机器十几分钟；这两组只做“非协议单次记录”并在条目里标注 repeats 覆盖。
    {'id': 'legacy/series-500-dense', 'kind': 'legacy', 'size': 500, 'python_fraction': 0., 'method': 'dense',
     'repeats': {'cold': 1, 'hot': 1}},
    # series-1000-dense 在 v0.5.0 的逐变量数值 Jacobian 下单次运行 >11 分钟（共享机实测），
    # 不进基线矩阵；dense 在 500 实例的实测已在上一行，规模外推留给 S/J 证据，不伪造协议数字。
    {'id': 'legacy/series-100-sparse', 'kind': 'legacy', 'size': 100, 'python_fraction': 0., 'method': 'sparse'},
    {'id': 'legacy/series-500-sparse', 'kind': 'legacy', 'size': 500, 'python_fraction': 0., 'method': 'sparse'},
    {'id': 'legacy/series-1000-sparse', 'kind': 'legacy', 'size': 1000, 'python_fraction': 0., 'method': 'sparse'},
    {'id': 'legacy/python-batch-25-b1w1', 'kind': 'legacy', 'size': 30, 'python_fraction': .25, 'batch': True, 'workers': 1},
    {'id': 'legacy/python-batch-100-b1w1', 'kind': 'legacy', 'size': 30, 'python_fraction': 1., 'batch': True, 'workers': 1},
    {'id': 'legacy/python-batch-100-b1w2', 'kind': 'legacy', 'size': 30, 'python_fraction': 1., 'batch': True, 'workers': 2},
]


# ---------------------------------------------------------------- 单次测量


def build_case(case):
    from benchmark_scaling import make_network
    from numerics_cases import build_project

    if case['kind'] == 'topology':
        project = build_project(case['family'], case['tier'])
    else:
        project = make_network(case['size'], case.get('python_fraction', 0.))
    project.solver.hydraulic_method = case.get('method', 'sparse')
    project.solver.batch_modules = case.get('batch', True)
    project.solver.module_parallelism = case.get('workers', 1)
    return project


def measure_once(case):
    from benchmark_scaling import measure

    project = build_case(case)
    begin = time.perf_counter()
    result = measure(project)
    result['measure_wall_s'] = time.perf_counter() - begin
    return result


def case_config(case):
    """用例配置快照：项目构造参数 + 实例数 + 算法开关（不重复编译，节省基线时间）。"""
    project = build_case(case)
    return {'instances': len(project.instances),
            'hydraulic_method': project.solver.hydraulic_method,
            'batch_modules': project.solver.batch_modules,
            'module_parallelism': project.solver.module_parallelism}


def run_samples(case, warmup, repeats):
    samples = []
    for _ in range(warmup):
        try:
            measure_once(case)
        except Exception as error:  # 预热失败也继续测，失败样本单独登记
            samples.append({'status': 'failed', 'error': f'{type(error).__name__}: {error}'[:2000]})
    for _ in range(repeats):
        try:
            samples.append(dict(measure_once(case), status='passed'))
        except Exception as error:
            samples.append({'status': 'failed', 'error': f'{type(error).__name__}: {error}'[:2000]})
    return samples


# ---------------------------------------------------------------- 配置登记


def sha256_file(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def dependency_versions():
    versions = {}
    for name in ('numpy', 'scipy', 'pydantic', 'fastapi', 'uvicorn', 'psutil'):
        try:
            versions[name] = __import__(name).__version__
        except Exception:
            versions[name] = None
    try:
        import CoolProp
        versions['CoolProp'] = CoolProp.__version__
    except Exception:
        versions['CoolProp'] = None
    return versions


def property_backend():
    info = {'library': 'CoolProp', 'coolprop_version': dependency_versions().get('CoolProp'),
            'refprop_available': None, 'refprop_env': os.environ.get('FLUIDNET_REFPROP_PATH')}
    try:
        from fn_engine.properties import REFPROP_DEFAULT, REFPROP_LIBRARY
        info['refprop_default_path'] = str(REFPROP_DEFAULT)
        info['refprop_library'] = REFPROP_LIBRARY
        info['refprop_available'] = REFPROP_DEFAULT.exists()
    except Exception as error:
        info['probe_error'] = f'{type(error).__name__}: {error}'
    return info


def git_value(args, default='unknown'):
    try:
        result = subprocess.run(['git', *args], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or default
    except (OSError, subprocess.SubprocessError):
        return default


def solver_defaults():
    """求解器默认开关快照：改造后 A/B 需要能读出 analytic_jacobian / auto 等方法状态。"""
    try:
        from fn_engine.models import SolverOptions
        fields = SolverOptions.model_fields
        return {name: (field.get_default(call_default_factory=True) if field.is_required() is False else None)
                for name, field in fields.items()
                if any(word in name for word in ('method', 'jacobian', 'compression', 'blocks', 'iterat', 'coupl'))}
    except Exception as error:
        return {'error': f'{type(error).__name__}: {error}'[:200]}


def current_load():
    """共享机器上的负载快照：并行工作流会抬高绝对墙钟，报告中必须能看出这一点。"""
    info = {'cpu_percent': None, 'python_processes': None, 'memory_percent': None}
    try:
        import psutil
        info['cpu_percent'] = psutil.cpu_percent(interval=0.5)
        info['python_processes'] = sum(1 for process in psutil.process_iter(['name'])
                                       if process.info.get('name', '').lower().startswith('python'))
        info['memory_percent'] = psutil.virtual_memory().percent
    except Exception:
        pass
    return info


def environment_info():
    import fn_engine
    engine = Path(fn_engine.__file__).resolve().parents[1]
    files = {name: sha256_file(engine / 'fn_engine' / name)
             for name in ('solver.py', 'worker.py', 'runtime.py', 'control.py', 'thermal.py', 'models.py',
                          'bench.py', 'properties.py')}
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:
        ram_gb = None
    return {'python': sys.version.split()[0],
            'python_executable': sys.executable,
            'platform': platform.platform(),
            'processor': platform.processor(),
            'cpu_count_logical': os.cpu_count(),
            'ram_total_gb': ram_gb,
            'native_threads': 1,
            'engine_path': str(engine),
            'git_commit': git_value(['rev-parse', 'HEAD']),
            'work_tree_dirty': bool(git_value(['status', '--porcelain'], default='')),
            'file_sha256': files,
            'dependencies': dependency_versions(),
            'property_backend': property_backend(),
            'solver_defaults': solver_defaults(),
            'cpu_load': current_load(),
            'env_threads': {name: os.environ.get(name) for name in
                            ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}}


# ---------------------------------------------------------------- 汇总


def stats(samples):
    passed = [sample for sample in samples if sample.get('status') == 'passed']
    failed = [sample for sample in samples if sample.get('status') != 'passed']
    summary = {'samples': len(samples), 'failures': len(failed)}
    if failed:
        summary['failed_errors'] = [sample.get('error') for sample in failed]
    if not passed:
        return summary
    keys = [key for key, value in passed[0].items() if isinstance(value, (int, float)) and not isinstance(value, bool)]
    for key in keys:
        values = [sample[key] for sample in passed]
        summary[key] = {'median': statistics.median(values), 'min': min(values), 'max': max(values)}
    return summary


def _kill_tree(process):
    """超时时连子进程一起清理：Worker 会继承父进程句柄，只杀直接子进程会留下孤儿。"""
    try:
        import psutil
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.Error:
                pass
    except Exception:
        pass
    try:
        process.kill()
    except OSError:
        pass


def spawn(argv, timeout_s=1800):
    """用临时文件接收子进程输出。

    不能用 ``capture_output=True``：Python 模块 Worker 会继承子进程 stdout 管道句柄，
    即使直接子进程退出，管道也可能被孙进程保持打开，导致父进程读到 EOF 前一直挂起。
    """
    import tempfile

    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as folder:
        stdout_path, stderr_path = Path(folder) / 'stdout.txt', Path(folder) / 'stderr.txt'
        with open(stdout_path, 'w', encoding='utf-8') as stdout, open(stderr_path, 'w', encoding='utf-8') as stderr:
            process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, text=True)
            try:
                process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                _kill_tree(process)
                process.wait(timeout=30)
                raise RuntimeError(f'子进程超时 {timeout_s}s：{argv[-3:]}')
        wall = time.perf_counter() - started
        text_out = stdout_path.read_text(encoding='utf-8', errors='replace')
        text_err = stderr_path.read_text(encoding='utf-8', errors='replace')
    if process.returncode != 0:
        raise RuntimeError(f'子进程失败：{text_err[-2000:]}')
    for line in reversed(text_out.strip().splitlines()):
        if line.startswith('{') and '"samples"' in line:
            return json.loads(line)['samples'], wall
    raise RuntimeError(f'子进程没有返回样本 JSON：{text_out[-1000:]}')


def measure_case(case, cold_repeats, hot_repeats):
    script = str(Path(__file__).resolve())
    cold_repeats = case.get('repeats', {}).get('cold', cold_repeats)
    hot_repeats = case.get('repeats', {}).get('hot', hot_repeats)
    cold_samples, cold_wall = [], 0.0
    for _ in range(cold_repeats):
        samples, wall = spawn([sys.executable, script, '--run-case', case['id'], '--mode', 'cold',
                               '--warmup', '0', '--repeats', '1'])
        cold_samples.extend(samples)
        cold_wall += wall
    hot_samples, hot_wall = spawn([sys.executable, script, '--run-case', case['id'], '--mode', 'hot',
                                   '--warmup', str(HOT_WARMUP), '--repeats', str(hot_repeats)])
    cold = stats(cold_samples)
    cold['process_wall_s'] = {'median': cold_wall / max(cold_repeats, 1)}
    hot = stats(hot_samples)
    hot['process_wall_s'] = {'median': hot_wall}
    return {'cold': cold, 'hot': hot}


def find_case(case_id):
    for case in CASES:
        if case['id'] == case_id:
            return case
    raise KeyError(f'未知用例：{case_id}')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/numerics/B3/baseline.json')
    parser.add_argument('--cold-repeats', type=int, default=COLD_REPEATS)
    parser.add_argument('--hot-repeats', type=int, default=HOT_REPEATS)
    parser.add_argument('--only', default='', help='逗号分隔的子串过滤，匹配用例 id')
    parser.add_argument('--exclude', default='')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--run-case', dest='run_case')
    parser.add_argument('--mode', choices=('cold', 'hot'), default='cold')
    parser.add_argument('--warmup', type=int, default=0)
    parser.add_argument('--repeats', type=int, default=1)
    args = parser.parse_args(argv)

    if args.list:
        for case in CASES:
            print(case['id'])
        return 0
    if args.run_case:
        case = find_case(args.run_case)
        samples = run_samples(case, args.warmup, args.repeats)
        print(json.dumps({'samples': samples}, ensure_ascii=False), flush=True)
        return 0

    include = [name.strip() for name in args.only.split(',') if name.strip()]
    exclude = [name.strip() for name in args.exclude.split(',') if name.strip()]
    selected = [case for case in CASES
                if (not include or any(name in case['id'] for name in include))
                and not any(name in case['id'] for name in exclude)]
    if not selected:
        raise SystemExit('没有匹配的用例')

    report = {'work_package': 'B3', 'format_version': 1,
              'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
              'protocol': {'cold_repeats': args.cold_repeats, 'hot_repeats': args.hot_repeats,
                           'hot_warmup': HOT_WARMUP, 'report': 'median/min/max/failures; no P95'},
              'environment': environment_info(), 'cases': []}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    for case in selected:
        begin = time.perf_counter()
        try:
            result = measure_case(case, args.cold_repeats, args.hot_repeats)
            status = 'passed' if result['cold']['failures'] == 0 and result['hot']['failures'] == 0 else 'failed'
        except Exception as error:
            result = {'error': f'{type(error).__name__}: {error}'[:2000], 'cold': {}, 'hot': {}}
            status = 'failed'
        entry = {'id': case['id'], 'kind': case['kind'], 'status': status,
                 'case': {key: value for key, value in case.items() if key != 'id'},
                 'repeats': case.get('repeats', {'cold': args.cold_repeats, 'hot': args.hot_repeats}),
                 'elapsed_s': time.perf_counter() - begin, **result}
        try:
            entry['config'] = case_config(case)
        except Exception as error:
            entry['config'] = {'error': f'{type(error).__name__}: {error}'[:500]}
        report['cases'].append(entry)
        print(f"{entry['id']:<38s} {status:6s} "
              f"cold_med={entry.get('cold', {}).get('measure_wall_s', {}).get('median')} "
              f"hot_med={entry.get('hot', {}).get('measure_wall_s', {}).get('median')}", flush=True)
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    payload = json.dumps(report, indent=2, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    report['raw_result_sha256'] = digest
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    failed = [case['id'] for case in report['cases'] if case['status'] != 'passed']
    print('wrote', path, 'cases', len(report['cases']), 'failed', failed, 'sha256', digest[:16], flush=True)
    return 0 if not failed else 1


if __name__ == '__main__':
    raise SystemExit(main())
