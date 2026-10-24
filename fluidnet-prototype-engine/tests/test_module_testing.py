from pathlib import Path

from fn_engine.models import ModuleTestSuiteRequest
from fn_engine.module_testing import run_module_suite
from fn_engine.packages import load_module_package

ROOT = Path(__file__).resolve().parents[1]


def test_suite_does_not_hide_failure_or_skip_following_case():
    module = load_module_package(ROOT / 'modules/programmable_valve_sdk')
    suite = ModuleTestSuiteRequest(module=module, cases=[
        {'id': 'forward'}, {'id': 'invalid', 'conditions': {'parameters': {'kv_m3_h': -1}}},
        {'id': 'partial', 'conditions': {'parameters': {'opening_ratio': .4}}},
    ])
    result = run_module_suite(suite)
    assert [case.passed for case in result.cases] == [True, False, True]
    assert not result.passed and result.cases[1].diagnostics
    assert len({case.input_hash for case in result.cases}) == 3
    assert all(case.level == 'L3' for case in result.cases)
    assert result.cases[2].result.frame.variables['D1.main.mass_flow_kg_s'] < result.cases[0].result.frame.variables['D1.main.mass_flow_kg_s']
