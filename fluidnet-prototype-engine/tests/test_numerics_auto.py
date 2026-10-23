"""S0/S1：auto 稀疏选择器、显式请求不被覆盖、一次可诊断回退。"""
import pytest

from fn_engine import solver as solver_module
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.solver import (AUTO_DENSE_MAX_SIZE, AUTO_SPARSE_MIN_SIZE, choose_hydraulic_method,
                              solve_hydraulics)


def inst(iid, module_id, **parameters):
    return ModuleInstance(id=iid, module_id=module_id, name=iid, parameters=parameters)


def link(cid, a, b):
    (si, sp), (ti, tp) = a.split(':'), b.split(':')
    return Connection(id=cid, source=Endpoint(instance_id=si, port_id=sp),
                      target=Endpoint(instance_id=ti, port_id=tp))


def chain(n, method='auto'):
    """n 个阀门串联：未知量 = (n - 1) + (n + 1) ≈ 2n，随 n 线性增长。"""
    catalog = catalog_map()
    project = Project(id='chain', name='chain', modules=[catalog['source'], catalog['valve']],
                      instances=[inst('B1', 'source', pressure_pa=400000.), inst('B2', 'source', pressure_pa=100000.)],
                      connections=[])
    previous = 'B1:out0'
    for i in range(n):
        project.instances.append(inst(f'V{i}', 'valve', kv_m3_h=20.))
        project.connections.append(link(f'e{i}', previous, f'V{i}:in0'))
        previous = f'V{i}:out0'
    project.connections.append(link('end', previous, 'B2:out0'))
    project.solver.thermal = False
    project.solver.hydraulic_method = method
    return project


def small_project(method='auto'):
    project = chain(2, method)
    return project


# --- 选择器单元测试（不求解） -------------------------------------------------

def test_selector_respects_explicit_requests():
    assert choose_hydraulic_method('dense', 200, 400).effective == 'dense'
    assert choose_hydraulic_method('dense', 3, 1).effective == 'dense'
    assert choose_hydraulic_method('sparse', 5, 25).effective == 'sparse'


def test_selector_uses_unknowns_and_density_not_instance_count():
    small = choose_hydraulic_method('auto', 10, 40)
    assert (small.requested, small.effective) == ('auto', 'dense')
    assert '未知量 10' in small.reason
    # 规模够大但依赖密集：稀疏分组几乎等于稠密，必须保留稠密。
    dense_pattern = choose_hydraulic_method('auto', 120, 120 * 120)
    assert dense_pattern.effective == 'dense'
    assert '稀疏度' in dense_pattern.reason
    sparse_pattern = choose_hydraulic_method('auto', 120, 800)
    assert sparse_pattern.effective == 'sparse'
    assert '稀疏度' in sparse_pattern.reason


def test_selector_forces_sparse_beyond_dense_memory_limit():
    choice = choose_hydraulic_method('auto', AUTO_DENSE_MAX_SIZE + 1, (AUTO_DENSE_MAX_SIZE + 1) ** 2)
    assert choice.effective == 'sparse'
    assert '内存' in choice.reason


# --- 端到端：auto 与显式方法逐变量一致 --------------------------------------

def test_auto_small_model_is_dense_and_matches_explicit():
    automatic = solve_hydraulics(compile_project(small_project('auto')))
    explicit = solve_hydraulics(compile_project(small_project('dense')))
    assert automatic.requested_method == 'auto'
    assert automatic.effective_method == 'dense'
    assert automatic.method_reason.startswith('auto：未知量')
    assert automatic.matrix_size == explicit.matrix_size
    assert automatic.pressures == pytest.approx(explicit.pressures, rel=0, abs=0)
    assert automatic.flows == pytest.approx(explicit.flows, rel=0, abs=0)


def test_auto_large_model_is_sparse_and_matches_explicit():
    n = 100
    automatic = solve_hydraulics(compile_project(chain(n, 'auto')))
    explicit = solve_hydraulics(compile_project(chain(n, 'sparse')))
    assert automatic.effective_method == 'sparse'
    assert automatic.matrix_size >= AUTO_SPARSE_MIN_SIZE
    assert automatic.matrix_nnz < automatic.matrix_size ** 2
    assert automatic.pressures == pytest.approx(explicit.pressures, rel=1e-9, abs=1e-9)
    assert automatic.flows == pytest.approx(explicit.flows, rel=1e-9, abs=1e-9)


def test_auto_falls_back_to_dense_once(monkeypatch):
    real = solver_module.least_squares
    calls = {'sparse': 0, 'dense': 0}

    def flaky(residual, x0, **options):
        if options.get('tr_solver') == 'lsmr':
            calls['sparse'] += 1
            result = real(residual, x0, **options)
            result.success = False  # 模拟稀疏线性子问题失败
            return result
        calls['dense'] += 1
        return real(residual, x0, **options)

    monkeypatch.setattr(solver_module, 'least_squares', flaky)
    model = chain(100, 'auto')
    model.solver.hydraulic_diagnostics = True
    result = solve_hydraulics(compile_project(model))
    assert calls == {'sparse': 1, 'dense': 1}, '只允许一次回退，不做无限重试'
    assert result.effective_method == 'dense'
    assert '回退 dense' in result.method_reason
    assert result.counters['method_fallback'] == 'dense'
    assert result.counters['solver_attempts'] == 2
    # 回退后仍必须过同一个收敛门。
    assert result.pressure_residual <= model.solver.pressure_tolerance_pa
    assert result.mass_residual <= model.solver.mass_tolerance_kg_s
