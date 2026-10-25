from fn_engine.bench import run_module_test
from fn_engine.models import ModuleTestRequest, ModuleDefinition
from fn_engine.module_templates import TEMPLATES, create_template, template_conditions
from fn_engine.runtime import module_definition_hash

import pytest


@pytest.mark.parametrize('template', TEMPLATES)
def test_each_template_runs_real_network_and_reload_preserves_contract(template):
    module = create_template(template, f'my_{template}', '新设备')
    result = run_module_test(ModuleTestRequest(module=module, **template_conditions(template).model_dump()))
    assert result.frame.valid
    restored = ModuleDefinition.model_validate_json(module.model_dump_json())
    assert module_definition_hash(restored) == module_definition_hash(module)
    if template == 'heat_exchanger':
        hot, cold = result.frame.variables['D1.hot.heat_w'], result.frame.variables['D1.cold.heat_w']
        assert hot < 0 < cold
        assert hot + cold == pytest.approx(0., abs=1e-6)
        assert result.committed.state['transferred_energy_j'] == pytest.approx(.1*cold)
