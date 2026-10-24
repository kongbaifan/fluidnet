"""Published SDK seeds, independent flow/ledger checks and immutable reload."""
import math
from pathlib import Path

import pytest

from fn_engine.bench import run_module_test
from fn_engine.models import ModuleDefinition, ModuleSaveRequest, ModuleTestRequest
from fn_engine.packages import ModuleStore, load_module_package
from fn_engine.runtime import module_content_hash, module_definition_hash

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('directory', ['programmable_valve_sdk', 'sdk_resistance'])
def test_sdk_seed_real_network_flow_ledger_and_export(directory):
    module = load_module_package(ROOT / 'modules' / directory)
    result = run_module_test(ModuleTestRequest(module=module, duration_s=.2, dt_s=.1))
    flow = result.frame.variables['D1.main.mass_flow_kg_s']
    rho = result.evaluation.variables['density_kg_m3']
    params = {p.id: p.default for p in module.parameters}
    if directory == 'programmable_valve_sdk':
        expected = rho * params['kv_m3_h'] * params['opening_ratio'] / 3600 * math.sqrt(130000 / (1e5 * rho / 1000))
    else:
        area = math.pi * params['diameter_m'] ** 2 / 4
        expected = area * math.sqrt(2 * rho * 130000 / params['loss_coefficient'])
    assert flow == pytest.approx(expected, rel=1e-6, abs=1e-8)
    assert result.committed.state['throughput_kg'] == pytest.approx(abs(flow) * .2)
    restored = ModuleDefinition.model_validate_json(module.model_dump_json())
    assert module_content_hash(restored) == module.content_hash
    assert module_definition_hash(restored) == module.definition_hash


def test_sdk_package_can_save_and_reload_new_release(tmp_path):
    module = load_module_package(ROOT / 'modules/sdk_resistance')
    store = ModuleStore(ROOT / 'modules', tmp_path)
    release = store.save(ModuleSaveRequest(module=module, expected_latest_version=1))
    assert release.module.version == 2
    restored = ModuleStore(ROOT / 'modules', tmp_path).get(module.id, 2)
    assert restored.module.source == release.module.source
    assert restored.package == release.package
    assert store.get(module.id, 1).module.definition_hash == module.definition_hash


@pytest.mark.parametrize('directory',['programmable_valve_sdk','sdk_resistance'])
@pytest.mark.parametrize('pressure',[120000.,250000.])
def test_new_passive_examples_support_reverse_and_zero_fixed_boundary_starts(directory,pressure):
    module=load_module_package(ROOT/'modules'/directory)
    result=run_module_test(ModuleTestRequest(module=module,inlet_pressure_pa=pressure,outlet_pressure_pa=250000.))
    flow=result.frame.variables['D1.main.mass_flow_kg_s']
    assert flow<0 if pressure<250000 else abs(flow)<=1e-8
