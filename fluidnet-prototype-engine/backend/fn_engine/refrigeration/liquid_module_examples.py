"""Portable coupled example with a public SDK valve and arbitrary instance ID."""
from pathlib import Path

from ..compiler import compile_project
from ..models import Scenario
from ..packages import load_module_package, package_ref
from ..runtime import module_content_hash, module_definition_hash
from .coupling_examples import thermal_coupling_example

ROOT = Path(__file__).resolve().parents[3]
VALVE = 'LiquidValve-Custom'
LAYOUT = {'LP1': (140, 95), 'K1': (340, 50), 'EC1': (560, 50), 'HP1': (760, 130),
          'EV1': (440, 175), 'WB1': (120, 310), 'WN1': (245, 310), 'WP1': (380, 285),
          'WL1': (550, 285), VALVE: (740, 350), 'HX_W': (470, 410)}


def coupled_liquid_module_example(coolant='Water', module=None):
    project = thermal_coupling_example(coolant)
    # This portable reference is a reproducible authoring input, not a binary
    # dump of the sizing solver's last bits. Publish derived device sizes at
    # ten significant digits, well within the model's existing tolerances.
    # Only new example construction uses this precision; saved user projects
    # and simulation results retain their original values.
    sized = {'K1': 'displacement_m3_s', 'EC1': 'ua_w_k', 'EV1': 'kv_m3_h'}
    for instance in project.instances:
        parameter = sized.get(instance.id)
        if parameter:
            instance.parameters[parameter] = float(format(instance.parameters[parameter], '.10g'))
    definition = (module or load_module_package(ROOT / 'modules/coupled_liquid_valve')).model_copy(deep=True)
    definition.package_path = None
    definition.content_hash = module_content_hash(definition)
    definition.definition_hash = module_definition_hash(definition)
    valve = next(instance for instance in project.instances if instance.id == 'WV1')
    valve.id, valve.name, valve.module_id = VALVE, '自定义二次液体调节阀', definition.id
    valve.package = package_ref(definition)
    for instance in project.instances:
        instance.position.x, instance.position.y = LAYOUT[instance.id]
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
