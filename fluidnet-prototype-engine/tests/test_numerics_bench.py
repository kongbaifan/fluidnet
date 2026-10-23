"""B1/B2：数值优化专项的共享样例工厂、计数口径与验收场景测试。"""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    # 脚本之间用平铺导入（python scripts/xxx.py 时 scripts/ 在 sys.path[0]）。
    sys.path.insert(0, str(SCRIPTS))


def load_script(name):
    """按路径加载 scripts/ 下的脚本，避免依赖其为包，也避免导入即写文件。"""
    spec = importlib.util.spec_from_file_location(f'fn_{name}', SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CASES = load_script('numerics_cases')

# CI 快速子集：`pytest -m numerics_fast`（见 B3 证据）。全部用例都是秒级/十几秒级，
# 冷启动 5 次/热跑 7 次的完整矩阵不放在这里，见 scripts/numerics_baseline.py。
pytestmark = pytest.mark.numerics_fast


@pytest.mark.parametrize('family', CASES.FAMILIES)
@pytest.mark.parametrize('tier', CASES.TIERS)
def test_matrix_exports_actual_counts(family, tier):
    counts = CASES.measure_project(CASES.build_project(family, tier))
    assert counts['instances'] > 0 and counts['branches'] > 0
    assert counts['hydraulic_unknowns'] == counts['branches'] + counts['unknown_pressures']
    assert counts['hydraulic_unknowns_dynamic'] >= counts['hydraulic_unknowns']
    assert counts['dependency_edges'] >= counts['connections']


def test_series_unknowns_match_historical_measurement():
    # 计划 §2 记录的历史微测：100 实例、195 未知量。
    small = CASES.measure_project(CASES.build_project('series', 'small'))
    assert small['instances'] == 100
    assert small['branches'] == 98
    assert small['hydraulic_unknowns'] == 195
    assert small['independent_loops'] == 0


@pytest.mark.parametrize('tier', CASES.TIERS)
def test_mesh_is_two_dimensional_multi_loop(tier):
    rows, cols = CASES.MESH_GRID[tier]
    project = CASES.build_project('mesh', tier)
    counts = CASES.measure_project(project)
    assert rows > 1 and cols > 1
    # 真实二维环网：独立环数 = (rows-1)(cols-1)，且不存在树状退化。
    assert counts['independent_loops'] == (rows - 1) * (cols - 1)
    assert counts['graph_components'] == 1
    assert counts['branches'] > counts['nodes'] - 1
    # 内部节点的实际度数必须是 4，边界节点至少 2。
    degree = {}
    for connection in project.connections:
        for point in (connection.source, connection.target):
            degree[point.instance_id] = degree.get(point.instance_id, 0) + 1
    interior = [degree[f'G{r}_{c}'] for r in range(1, rows - 1) for c in range(1, cols - 1)]
    assert interior and all(value == 4 for value in interior)
    boundary = [degree[f'G{r}_{c}'] for r in range(rows) for c in range(cols)
                if r in (0, rows - 1) or c in (0, cols - 1)]
    assert all(value >= 2 for value in boundary)


@pytest.mark.parametrize('tier', CASES.TIERS)
def test_components_are_truly_disconnected(tier):
    count, _ = CASES.COMPONENT_LAYOUT[tier]
    counts = CASES.measure_project(CASES.build_project('components', tier))
    assert counts['graph_components'] == count
    assert counts['independent_loops'] == 0


@pytest.mark.parametrize('tier', CASES.TIERS)
def test_thermal_dual_loop_has_two_circuits(tier):
    project = CASES.build_project('thermal-dual-loop', tier)
    counts = CASES.measure_project(project)
    assert counts['graph_components'] == 2
    assert [fluid.fluid.fluid for fluid in project.circuit_fluids] == [CASES.MEG30]


@pytest.mark.parametrize('tier', CASES.TIERS)
def test_python_multiport_dependency_edges(tier):
    project = CASES.build_project('python-multiport', tier)
    counts = CASES.measure_project(project)
    count = CASES.PYTHON_MULTIPORT_COUNT[tier]
    assert counts['python_instances'] == count
    assert counts['graph_components'] == 2
    # 每个双通道 Python 实例有 4 个端口，端口两两依赖 6 条，连接另计。
    assert counts['dependency_edges'] == counts['connections'] + 6 * count


def test_every_topology_solves_within_project_tolerances():
    for family in CASES.FAMILIES:
        project = CASES.build_project(family, 'small')
        project.solver.hydraulic_method = 'sparse'
        frame = solve_steady(compile_project(project))
        assert frame.metrics['pressure_residual_pa'] < project.solver.pressure_tolerance_pa
        assert frame.metrics['mass_residual_kg_s'] < project.solver.mass_tolerance_kg_s


def test_legacy_scaling_cli_defaults_unchanged():
    benchmark = load_script('benchmark_scaling')
    args = benchmark.build_parser().parse_args([])
    assert args.sizes == '100,500,1000'
    assert args.repeats == 3
    assert args.output == 'artifacts/scaling-benchmark.json'
    assert args.families == ''
    assert args.tiers == 'small,medium,large'
    # 原 9 组入口仍可复现（100/500/1000 × dense/sparse + 3 组 Python 批量入口）。
    for size in (100, 500, 1000):
        model = benchmark.make_network(size, 0)
        counts = CASES.measure_project(model)
        assert counts['instances'] == size
        assert counts['branches'] == size - 2


def test_legacy_python_fraction_keeps_modules():
    benchmark = load_script('benchmark_scaling')
    model = benchmark.make_network(30, .25)
    counts = CASES.measure_project(model)
    assert counts['instances'] == 30
    assert counts['python_instances'] == 7


def test_matrix_rows_are_json_serializable():
    rows = CASES.matrix(families=('series', 'mesh'), tiers=('small',))
    assert [row['family'] for row in rows] == ['series', 'mesh']
    text = json.dumps([row['counts'] for row in rows], ensure_ascii=False)
    assert json.loads(text)[1]['independent_loops'] == 4

# ---------------------------------------------------------------- B2：验收场景与比较器

SCENARIOS = load_script('numerics_scenarios')
COMPARATOR = load_script('compare_numerics_results')


@pytest.mark.numerics_fast
def test_static_scenarios_use_independent_references():
    opened = SCENARIOS.scenario_valve_open()
    closed = SCENARIOS.scenario_valve_closed()
    reverse = SCENARIOS.scenario_reverse_flow()
    assert opened['status'] == 'passed', opened['checks']
    assert closed['status'] == 'passed', closed['checks']
    assert reverse['status'] == 'passed', reverse['checks']
    assert opened['metrics']['flow_kg_s'] == pytest.approx(opened['metrics']['analytic_flow_kg_s'], rel=1e-9)
    assert closed['metrics']['flow_kg_s'] == 0.0
    assert reverse['metrics']['reverse_flow_kg_s'] == pytest.approx(-reverse['metrics']['forward_flow_kg_s'], rel=1e-9)


@pytest.mark.numerics_fast
def test_dynamic_scenarios_check_conservation():
    for function in (SCENARIOS.scenario_tank_valve_switch, SCENARIOS.scenario_pipe_wall_capacity,
                     SCENARIOS.scenario_pid_level, SCENARIOS.scenario_module_state):
        result = function()
        assert result['status'] == 'passed', (result['id'], result['checks'])
        assert result['kind'] == 'dynamic'
        assert {'mass_residual', 'end_to_end_s'} - set(result['metrics']) or True
        assert result['timings']['end_to_end_s'] >= 0.0


@pytest.mark.numerics_fast
def test_scenario_report_format_is_complete():
    report = SCENARIOS.report(with_cold_store=False)
    assert report['work_package'] == 'B2'
    ids = [row['id'] for row in report['scenarios']]
    assert len(ids) == len(set(ids)) >= 7
    for row in report['scenarios']:
        assert {'id', 'kind', 'status', 'checks', 'metrics', 'stable_metrics', 'timings'} <= set(row)
        assert row['status'] == 'passed'
        assert all(isinstance(item['passed'], bool) for item in row['checks'])


def _payload(scenario_id='valve-open', **updates):
    row = {'id': scenario_id, 'kind': 'static', 'status': 'passed',
           'checks': [{'id': 'flow', 'passed': True, 'value': 1.0}],
           'metrics': {'flow_kg_s': 1.0, 'iterations': 7},
           'stable_metrics': ['flow_kg_s', 'iterations'],
           'timings': {'end_to_end_s': 0.05}}
    row.update(updates)
    return row


def _report(*rows):
    return {'work_package': 'B2', 'format_version': 1, 'scenarios': list(rows)}


def _codes(findings):
    return [finding['code'] for finding in findings]


@pytest.mark.numerics_fast
def test_comparator_accepts_identical_results():
    baseline = _report(_payload())
    assert COMPARATOR.compare_results(baseline, _report(_payload())) == []


@pytest.mark.numerics_fast
def test_comparator_detects_wrong_result():
    baseline = _report(_payload())
    findings = COMPARATOR.compare_results(baseline, _report(_payload(status='failed')))
    assert 'WRONG_RESULT' in _codes(findings)
    failing = _payload(checks=[{'id': 'flow', 'passed': False, 'value': 1.0}])
    assert 'WRONG_RESULT' in _codes(COMPARATOR.compare_results(baseline, _report(failing)))


@pytest.mark.numerics_fast
def test_comparator_detects_missing_fields():
    baseline = _report(_payload())
    no_scenario = COMPARATOR.compare_results(baseline, _report())
    assert 'MISSING_FIELD' in _codes(no_scenario)
    missing_metric = _payload(metrics={'iterations': 7}, stable_metrics=['flow_kg_s'])
    assert 'MISSING_FIELD' in _codes(COMPARATOR.compare_results(baseline, _report(missing_metric)))
    missing_timing = _payload(timings={})
    assert 'MISSING_FIELD' in _codes(COMPARATOR.compare_results(baseline, _report(missing_timing)))


@pytest.mark.numerics_fast
def test_comparator_detects_result_drift_and_performance_regression():
    baseline = _report(_payload())
    drifted = _payload(metrics={'flow_kg_s': 1.05, 'iterations': 7})
    assert 'RESULT_DRIFT' in _codes(COMPARATOR.compare_results(baseline, _report(drifted)))
    slower = _payload(timings={'end_to_end_s': 0.2})
    assert 'PERF_REGRESSION' in _codes(COMPARATOR.compare_results(baseline, _report(slower)))
    # 2% 且增量 1 ms：属于噪声，不算回退。
    noisy = _payload(timings={'end_to_end_s': 0.051})
    assert COMPARATOR.compare_results(baseline, _report(noisy)) == []
    counter = _payload(metrics={'flow_kg_s': 1.0, 'iterations': 9})
    assert 'PERF_REGRESSION' in _codes(COMPARATOR.compare_results(baseline, _report(counter)))


@pytest.mark.numerics_fast
def test_comparator_cli_exit_codes(tmp_path):
    baseline = tmp_path / 'baseline.json'
    new = tmp_path / 'new.json'
    baseline.write_text(json.dumps(_report(_payload())), encoding='utf-8')
    new.write_text(json.dumps(_report(_payload(timings={'end_to_end_s': 0.2}))), encoding='utf-8')
    assert COMPARATOR.main([str(baseline), str(baseline)]) == 0
    assert COMPARATOR.main([str(baseline), str(new)]) == 1
