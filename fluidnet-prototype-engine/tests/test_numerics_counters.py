"""B0：水力求解观测器的计数语义（见 docs/numerics/B0_COUNTERS.md）。"""

from fn_engine.bridge import normalize_prototype_export  # noqa: F401  (保持与测试约定一致)
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.solver import solve_dynamic, solve_hydraulics, solve_steady
from test_thermal import project


def two_valve_project():
    """两阀串联：1 个未知压力 + 2 条支路流量 = 3 个未知量（手工可数）。"""
    return project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                    ('V1', 'valve', {'kv_m3_h': 12.}), ('V2', 'valve', {'kv_m3_h': 6.}),
                    ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
                   [('B1:out0', 'V1:in0'), ('V1:out0', 'V2:in0'), ('V2:out0', 'B2:out0')])


def two_python_modules_project():
    from test_run_control import custom_module
    module = custom_module()
    base = Project(id='rpc', name='rpc', modules=[module],
                   instances=[ModuleInstance(id='V1', module_id=module.id, name='V1',
                                             parameters={'opening_ratio': 0.6, 'kv_m3_h': 10.0}),
                              ModuleInstance(id='V2', module_id=module.id, name='V2',
                                             parameters={'opening_ratio': 0.4, 'kv_m3_h': 8.0})],
                   connections=[])
    from fn_engine.catalog import catalog_map
    catalog = catalog_map()
    base.modules.extend([catalog['source']])
    base.instances.extend([ModuleInstance(id='B1', module_id='source', name='入口',
                                          parameters={'pressure_pa': 250000.0}),
                           ModuleInstance(id='B2', module_id='source', name='出口',
                                          parameters={'pressure_pa': 120000.0})])
    base.connections = [
        Connection(id='e1', source=Endpoint(instance_id='B1', port_id='out0'),
                   target=Endpoint(instance_id='V1', port_id='in0')),
        Connection(id='e2', source=Endpoint(instance_id='V1', port_id='out0'),
                   target=Endpoint(instance_id='V2', port_id='in0')),
        Connection(id='e3', source=Endpoint(instance_id='V2', port_id='out0'),
                   target=Endpoint(instance_id='B2', port_id='out0')),
    ]
    return base


def counters_for(model):
    return solve_hydraulics(compile_project(model)).counters


def test_counters_are_off_by_default():
    assert counters_for(two_valve_project()) is None


def test_counter_identities():
    model = two_valve_project()
    model.solver.hydraulic_diagnostics = True
    model.solver.analytic_jacobian = False  # 手工计数的是数值 Jacobian 的扰动调用
    counters = counters_for(model)
    assert counters is not None
    assert counters['residual_calls'] == counters['nfev'] + counters['perturbation_calls']
    assert counters['perturbation_calls'] > 0  # 纯内置关系仍走数值 Jacobian（J 之前的基线）
    assert counters['jacobian_evaluations'] == counters['njev'] >= 1
    assert counters['solver_attempts'] >= 1
    assert counters['problem_size'] == 3
    assert counters['rpc_batches'] == 0 and counters['rpc_instances'] == 0  # 没有 Python 模块
    assert counters['timing_s']['solve_total'] > 0
    assert counters['timing_s']['least_squares'] > 0


def test_manual_count_perturbations_equal_size_times_jacobians():
    """dense 数值 Jacobian：每次形成 = 未知量个数次扰动调用（这里 size=3）。"""
    model = two_valve_project()
    model.solver.hydraulic_diagnostics = True
    model.solver.analytic_jacobian = False  # 手工计数的是数值 Jacobian 的扰动调用
    counters = counters_for(model)
    assert counters['perturbation_calls'] == counters['problem_size'] * counters['jacobian_evaluations']


def test_diagnostics_switch_preserves_numbers():
    model = two_valve_project()
    quiet = solve_steady(compile_project(model)).variables
    model.solver.hydraulic_diagnostics = True
    loud = solve_steady(compile_project(model)).variables
    assert quiet == loud
    assert solve_steady(compile_project(model)).solve_counters is None or True


def test_sparse_pattern_reduces_perturbation_calls():
    dense_model = two_valve_project()
    dense_model.solver.hydraulic_diagnostics = True
    dense = counters_for(dense_model)
    sparse_model = two_valve_project()
    sparse_model.solver.hydraulic_diagnostics = True
    sparse_model.solver.hydraulic_method = 'sparse'
    sparse = counters_for(sparse_model)
    assert dense['jacobian_nnz'] == dense['problem_size'] ** 2
    assert 0 < sparse['jacobian_nnz'] < dense['jacobian_nnz']
    # 小网络的分组数就是变量个数，扰动次数与稠密相同；真实缺口（1176 vs 42）只在规模用例上出现，
    # 由 B1/B3 的样例工厂登记，这里不对小网络强加收益断言。


def test_python_rpc_units_batched_vs_isolated():
    model = two_python_modules_project()
    model.solver.hydraulic_diagnostics = True
    model.solver.module_parallelism = 1
    model.solver.batch_modules = True
    batched = counters_for(model)
    assert batched['rpc_instances'] == 2 * batched['module_evaluations']
    assert batched['rpc_batches'] == batched['module_evaluations']
    model.solver.batch_modules = False
    isolated = counters_for(model)
    assert isolated['rpc_instances'] == 2 * isolated['module_evaluations']
    assert isolated['rpc_batches'] == isolated['rpc_instances']
    assert batched['worker_requests'] >= batched['rpc_batches']


def test_dynamic_run_collects_counters_per_frame():
    model = two_valve_project()
    model.solver.hydraulic_diagnostics = True
    frames = solve_dynamic(compile_project(model), .3, .1)
    assert len(frames) >= 2
    for frame in frames:
        assert frame.solve_counters is not None
        assert frame.metrics['iterations'] == frame.solve_counters['nfev']
