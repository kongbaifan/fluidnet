"""MOD-B1 module cases; reuse the numerics topology factories, never saved user data."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

from numerics_cases import assemble, dual_loop_project, python_multiport_project, series_project
from fn_engine.packages import load_module_package

CASES = ('single-valve', 'multi-instance', 'fan-coil', 'dual-thermal',
         'python-multiport', 'dynamic-state', 'worker-failure')


def single_module(package, *, failure=False):
    module = load_module_package(ROOT / 'modules' / package)
    if failure:
        # A real child-process exception, not a mocked solver failure.
        source = module.source['runtime'].replace('    def evaluate(self, ctx):',
            '    def evaluate(self, ctx):\n        raise RuntimeError("MOD_B1_INJECTED_FAILURE")')
        module = module.model_copy(deep=True, update={'source': {'runtime': source},
                                                     'content_hash': None, 'definition_hash': None})
    return assemble(f'module-{package}', [
        ('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
        ('D1', module.id, {}),
        ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
        [('B1:out0', 'D1:in0'), ('D1:out0', 'B2:out0')], [module])


def build_case(name, *, batch=True, workers=1):
    if name not in CASES:
        raise ValueError(f'未知模块场景：{name}')
    if workers < 1:
        raise ValueError('workers 必须为正整数')
    if name == 'multi-instance':
        project = series_project(6, 1.0)
    elif name == 'dual-thermal':
        project = dual_loop_project(1)
    elif name == 'python-multiport':
        project = python_multiport_project(1)
    else:
        package = 'fan_coil_unit' if name == 'fan-coil' else 'programmable_valve'
        project = single_module(package, failure=name == 'worker-failure')
    project.solver.hydraulic_method = 'auto'
    project.solver.hydraulic_diagnostics = True
    project.solver.batch_modules = batch
    project.solver.module_parallelism = workers
    return project
