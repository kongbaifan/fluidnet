"""B2 结果比较器：识别错误结果、缺字段与人为性能回退。

用法（仓库根目录）：

    python scripts/compare_numerics_results.py <基线.json> <新结果.json>
    python scripts/compare_numerics_results.py <基线.json> <新结果.json> --max-regression 0.10 --json-out report.json

退出码：0 = 无发现；1 = 存在错误/缺字段/回退。比较口径与计划 §3.2 一致：
- 先过正确性门（状态、检查项、参考指标漂移），再比性能；
- 性能回退门默认“中位数回退 ≤10% 且绝对增量 >5 ms”才算回退，避免单次机器噪声；
- 计数类指标（迭代、Worker 启动、物性调用等）增加超过 10% 也记为回退。
"""
import argparse
import json
import sys
from pathlib import Path

REQUIRED_SCENARIO_KEYS = ('id', 'kind', 'status', 'checks', 'metrics', 'timings')
REQUIRED_CHECK_KEYS = ('id', 'passed', 'value')
RESULT_CODES = ('WRONG_RESULT', 'MISSING_FIELD', 'PERF_REGRESSION', 'RESULT_DRIFT')
# 计数类指标：只禁止“变大”（变多是更多真实工作，不是优化）。
COUNTER_HINTS = ('iterations', 'count', 'starts', 'calls', 'evaluations', 'rpc', 'nnz', 'size')


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _close(new, baseline, rtol, atol):
    return abs(new - baseline) <= max(atol, rtol * abs(baseline))


def _timing_value(timings, key):
    value = timings.get(key)
    return value if _is_number(value) else None


def compare_results(baseline, new, max_regression=0.10, timing_floor_s=0.005, drift_rtol=1e-6,
                    drift_atol=1e-9):
    """返回发现列表；空列表表示通过。不修改输入。"""
    findings = []

    def add(code, scenario, detail):
        assert code in RESULT_CODES
        findings.append({'code': code, 'scenario': scenario, 'detail': detail})

    base_rows = baseline.get('scenarios') if isinstance(baseline, dict) else None
    new_rows = new.get('scenarios') if isinstance(new, dict) else None
    if not isinstance(base_rows, list) or not isinstance(new_rows, list):
        add('MISSING_FIELD', None, '结果文件缺少顶层 scenarios 列表')
        return findings
    base_map = {row.get('id'): row for row in base_rows if isinstance(row, dict)}
    new_map = {row.get('id'): row for row in new_rows if isinstance(row, dict)}

    for scenario_id in base_map:
        if scenario_id not in new_map:
            add('MISSING_FIELD', scenario_id, '新结果缺少该场景')
    for scenario_id in new_map:
        if scenario_id not in base_map:
            add('MISSING_FIELD', scenario_id, '新结果出现基线没有的场景，比较器拒绝静默接受')

    for scenario_id, base in base_map.items():
        current = new_map.get(scenario_id)
        if current is None:
            continue
        missing = [key for key in REQUIRED_SCENARIO_KEYS if key not in current]
        if missing:
            add('MISSING_FIELD', scenario_id, f'场景字段缺失：{missing}')
            continue
        if not isinstance(current['checks'], list):
            add('MISSING_FIELD', scenario_id, 'checks 不是列表')
            continue
        if current['status'] != 'passed':
            add('WRONG_RESULT', scenario_id, f'场景状态为 {current["status"]}')
        base_checks = {item.get('id'): item for item in base.get('checks', []) if isinstance(item, dict)}
        new_checks = {item.get('id'): item for item in current['checks'] if isinstance(item, dict)}
        for check_id, base_check in base_checks.items():
            current_check = new_checks.get(check_id)
            if current_check is None:
                add('MISSING_FIELD', scenario_id, f'检查项缺失：{check_id}')
                continue
            for key in REQUIRED_CHECK_KEYS:
                if key not in current_check:
                    add('MISSING_FIELD', scenario_id, f'检查项 {check_id} 缺少字段 {key}')
            if not current_check.get('passed'):
                add('WRONG_RESULT', scenario_id, f'检查项未通过：{check_id}')
        # 结果漂移：只比较基线声明的稳定指标（默认全部数值指标，排除计时类）。
        stable = base.get('stable_metrics')
        if stable is None:
            stable = [key for key, value in base.get('metrics', {}).items()
                      if _is_number(value) and not key.endswith('_s') and not key.endswith('_s_median')]
        base_metrics, new_metrics = base.get('metrics', {}), current.get('metrics', {})
        for key in stable:
            if key not in new_metrics:
                add('MISSING_FIELD', scenario_id, f'稳定指标缺失：{key}')
                continue
            if not _is_number(base_metrics.get(key)) or not _is_number(new_metrics[key]):
                continue
            if not _close(new_metrics[key], base_metrics[key], drift_rtol, drift_atol):
                add('RESULT_DRIFT', scenario_id,
                    f'{key} 由 {base_metrics[key]:.12g} 变为 {new_metrics[key]:.12g}')
        # 性能回退：计时中位数 + 计数类指标只允许下降或持平。
        base_timings, new_timings = base.get('timings', {}), current.get('timings', {})
        for key, base_value in base_timings.items():
            if key == 'samples' or not _is_number(base_value):
                continue
            if key not in new_timings or not _is_number(new_timings[key]):
                add('MISSING_FIELD', scenario_id, f'计时字段缺失：{key}')
                continue
            new_value = new_timings[key]
            if new_value > base_value * (1 + max_regression) and new_value - base_value > timing_floor_s:
                add('PERF_REGRESSION', scenario_id,
                    f'{key} 由 {base_value:.4f}s 升至 {new_value:.4f}s（>{(1 + max_regression) * 100 - 100:.0f}%）')
        for key in COUNTER_HINTS:
            base_value = base_metrics.get(key)
            new_value = new_metrics.get(key)
            if _is_number(base_value) and _is_number(new_value) and base_value > 0:
                if new_value > base_value * (1 + max_regression):
                    add('PERF_REGRESSION', scenario_id,
                        f'计数 {key} 由 {base_value:g} 增至 {new_value:g}')
    return findings


def summarize(findings):
    counts = {code: 0 for code in RESULT_CODES}
    for finding in findings:
        counts[finding['code']] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('baseline')
    parser.add_argument('new')
    parser.add_argument('--max-regression', type=float, default=0.10)
    parser.add_argument('--timing-floor-s', type=float, default=0.005)
    parser.add_argument('--drift-rtol', type=float, default=1e-6)
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)
    baseline = json.loads(Path(args.baseline).read_text(encoding='utf-8'))
    new = json.loads(Path(args.new).read_text(encoding='utf-8'))
    findings = compare_results(baseline, new, args.max_regression, args.timing_floor_s, args.drift_rtol)
    counts = summarize(findings)
    for finding in findings:
        print(f'[{finding["code"]}] {finding["scenario"]}: {finding["detail"]}')
    print(json.dumps({'ok': not findings, 'counts': counts, 'findings': len(findings)}, ensure_ascii=False))
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'counts': counts, 'findings': findings}, indent=2, ensure_ascii=False),
                        encoding='utf-8')
    return 0 if not findings else 1


if __name__ == '__main__':
    sys.exit(main())
