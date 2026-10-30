"""Portable coupled example with a public SDK valve and arbitrary instance ID."""
from pathlib import Path

from ..compiler import compile_project
from ..models import Scenario
from ..packages import load_module_package, package_ref
from ..runtime import module_content_hash, module_definition_hash
from .coupling_examples import thermal_coupling_example

ROOT = Path(__file__).resolve().parents[3]
VALVE = 'LiquidValve-Custom'


def coupled_liquid_module_example(coolant='Water', module=None):
    project = thermal_coupling_example(coolant)
    definition = (module or load_module_package(ROOT / 'modules/coupled_liquid_valve')).model_copy(deep=True)
    definition.package_path = None
    definition.content_hash = module_content_hash(definition)
    definition.definition_hash = module_definition_hash(definition)
    valve = next(instance for instance in project.instances if instance.id == 'WV1')
    valve.id, valve.name, valve.module_id = VALVE, '自定义二次液体调节阀', definition.id
    valve.package = package_ref(definition)
    project.modules.append(definition)
    used = {instance.module_id for instance in project.instances}
    project.modules = [item for item in project.modules if item.id in used]
    for edge in project.connections:
        for endpoint in (edge.source, edge.target):
            if endpoint.instance_id == 'WV1':
                endpoint.instance_id = VALVE
    project.id = 'thermal-coupling-author-v1'
    project.name = '作者水阀 · 氨制冷站与二次水网联算'
    project.description = '公共 SDK 单通路阀门进入热耦合水网；可编辑开度特性，固定模块版本，液体侧无独立储量。'
    project.scenarios = [
        Scenario(id='rated', name='线性特性 · 80% 开度'),
        Scenario(id='half-opening', name='线性特性 · 40% 开度', overrides={VALVE: {'opening_ratio': .4}}),
        Scenario(id='quadratic', name='平方特性 · 80% 开度', overrides={VALVE: {'characteristic_exponent': 2.}}),
    ]
    # selected_variables filters published frames, not merely the initial chart.
    # Keep the full frozen result for report/CSV, controls and later observations.
    project.selected_variables = []
    compile_project(project)
    return project
