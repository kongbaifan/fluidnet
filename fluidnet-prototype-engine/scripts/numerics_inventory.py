"""B1 运行清单：导出六类拓扑 × 三档的实际规模计数。

用法（仓库根目录）：

    python scripts/numerics_inventory.py --output artifacts/numerics/<commit>/B1/cases.json

输出可机器读取的 JSON，同时把表格打到 stdout。计数口径来自
``numerics_cases.describe``：水力未知量 = 支路流量 + 未定压节点压力（动态再加水箱净流入）。
"""
import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import numerics_cases


def git_value(args, default='unknown'):
    try:
        return subprocess.run(['git', *args], capture_output=True, text=True, timeout=10).stdout.strip() or default
    except (OSError, subprocess.SubprocessError):
        return default


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='artifacts/numerics/inventory.json')
    parser.add_argument('--families', default=','.join(numerics_cases.FAMILIES))
    parser.add_argument('--tiers', default=','.join(numerics_cases.TIERS))
    args = parser.parse_args(argv)
    families = [name.strip() for name in args.families.split(',') if name.strip()]
    tiers = [name.strip() for name in args.tiers.split(',') if name.strip()]
    begin = time.perf_counter()
    rows = []
    for family in families:
        for tier in tiers:
            counts = numerics_cases.measure_project(numerics_cases.build_project(family, tier))
            rows.append({'family': family, 'tier': tier, **counts})
            print('%-20s %-7s inst=%4d nodes=%4d branches=%4d unknowns=%4d deps=%5d loops=%3d components=%d python=%d' % (
                family, tier, counts['instances'], counts['nodes'], counts['branches'],
                counts['hydraulic_unknowns'], counts['dependency_edges'], counts['independent_loops'],
                counts['graph_components'], counts['python_instances']), flush=True)
    report = {
        'work_package': 'B1',
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'commit': git_value(['rev-parse', 'HEAD']),
        'work_tree_dirty': bool(git_value(['status', '--porcelain'], default='')),
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'native_threads': 1,
        'tier_definitions': {
            'series_instances': numerics_cases.SERIES_INSTANCES,
            'parallel_instances': numerics_cases.PARALLEL_INSTANCES,
            'mesh_grid': numerics_cases.MESH_GRID,
            'component_layout': numerics_cases.COMPONENT_LAYOUT,
            'dual_loop_length': numerics_cases.DUAL_LOOP_LENGTH,
            'python_multiport_count': numerics_cases.PYTHON_MULTIPORT_COUNT,
        },
        'elapsed_s': round(time.perf_counter() - begin, 3),
        'rows': rows,
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('wrote', path, 'rows', len(rows), 'elapsed %.2fs' % report['elapsed_s'], flush=True)


if __name__ == '__main__':
    main()
