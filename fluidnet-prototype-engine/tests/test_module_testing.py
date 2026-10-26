import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fn_engine.models import ModuleTestAssertion, ModuleTestCase, ModuleTestResponse, ModuleTestSuiteRequest, RunFrame
from fn_engine.module_testing import check_assertion, run_module_suite
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
    assert all(case.assertions == [] for case in result.cases)
    old_input = json.dumps(suite.cases[0].conditions.model_dump(mode='json'), sort_keys=True,
        ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    assert result.cases[0].input_hash == hashlib.sha256(old_input).hexdigest()


def test_final_state_expectations_fail_independently_and_bind_the_evidence_hash():
    module = load_module_package(ROOT / 'modules/programmable_valve_sdk')
    conditions = {'duration_s': .2, 'dt_s': .1}
    cases = [
        {'id': 'accepted_steps', 'conditions': conditions,
         'assertions': [{'key': 'D1.state.commit_count', 'expected': 2}]},
        {'id': 'wrong_expectation', 'conditions': conditions,
         'assertions': [{'key': 'D1.state.commit_count', 'expected': 0}, {'key': 'D1.opening_ratio', 'expected': .8}]},
        {'id': 'invalid_input', 'conditions': {'parameters': {'kv_m3_h': -1}},
         'assertions': [{'key': 'D1.state.commit_count', 'expected': 1}]},
        {'id': 'still_runs', 'conditions': {'parameters': {'opening_ratio': .4}},
         'assertions': [{'key': 'D1.opening_ratio', 'expected': .4}]},
    ]
    result = run_module_suite(ModuleTestSuiteRequest(module=module, cases=cases))
    assert [case.passed for case in result.cases] == [True, False, False, True]
    assert not result.passed
    assert result.cases[0].result.history[0].variables['D1.state.commit_count'] == 0
    assert result.cases[0].assertions[0].actual == 2
    failed = result.cases[1].assertions[0]
    assert (failed.status, failed.absolute_error, failed.allowed_error) == ('outside_tolerance', 2, 0)
    assert result.cases[1].assertions[1].passed
    assert result.cases[2].assertions[0].status == 'not_evaluated'
    assert result.cases[2].assertions[0].actual is None
    assert result.cases[0].input_hash != result.cases[1].input_hash


@pytest.mark.parametrize('actual,expected,absolute,relative,passed', [
    (10.125, 10, .125, 0, True),
    (10.25, 10, .125, 0, False),
    (10.5, 10, 0, .05, True),
    (11.1, 10, 0, .1, False),  # Relative tolerance is based on the expectation.
    (-10.5, -10, 0, .05, True),
    (.125, 0, .125, 1, True),
    (.125, 0, 0, 1, False),
    (11.5, 10, 1, .1, False),  # Absolute and relative tolerances are not added.
    (0, 0, 0, 0, True),
])
def test_expected_value_tolerance_boundaries(actual, expected, absolute, relative, passed):
    assertion = ModuleTestAssertion(key='D1.value', expected=expected,
        absolute_tolerance=absolute, relative_tolerance=relative)
    frame = RunFrame(status='converged', valid=True, time_s=1, variables={'D1.value': actual})
    result = check_assertion(assertion, frame)
    assert result.passed is passed
    assert result.actual == actual
    assert result.status == ('passed' if passed else 'outside_tolerance')


@pytest.mark.parametrize('variables,status', [
    ({}, 'missing'),
    ({'D1.value': True}, 'non_numeric'),
    ({'D1.value': False}, 'non_numeric'),
    ({'D1.value': '1'}, 'non_numeric'),
    ({'D1.value': None}, 'non_numeric'),
    ({'D1.value': float('nan')}, 'non_finite'),
    ({'D1.value': float('inf')}, 'non_finite'),
    ({'D1.value': -float('inf')}, 'non_finite'),
])
def test_missing_and_invalid_actual_values_are_explicit_json_safe_failures(variables, status):
    # Bypass frame validation to exercise the defensive assertion boundary as well.
    frame = RunFrame.model_construct(status='converged', valid=True, time_s=1, variables=variables)
    result = check_assertion(ModuleTestAssertion(key='D1.value', expected=1), frame)
    assert not result.passed and result.status == status
    assert result.absolute_error is None and result.allowed_error is None
    if status == 'non_finite':
        assert result.actual is None
    json.dumps(result.model_dump(mode='json'), allow_nan=False)


@pytest.mark.parametrize('expected,relative,passed', [(1e308, 1.9, False), (1e308, 2., True), (-1e308, 1e308, True)])
def test_finite_values_with_overflowing_errors_do_not_pass_by_infinity_comparison(expected, relative, passed):
    frame = RunFrame(status='converged', valid=True, time_s=1, variables={'D1.value': -1e308})
    result = check_assertion(ModuleTestAssertion(key='D1.value', expected=expected, relative_tolerance=relative), frame)
    assert result.passed is passed
    assert result.allowed_error is None
    assert result.absolute_error == (0 if expected < 0 else None)
    assert result.actual == -1e308
    json.dumps(result.model_dump(mode='json'), allow_nan=False)


def test_integer_actual_value_is_not_rounded_before_exact_comparison():
    actual = 2**53 + 1
    frame = RunFrame(status='converged', valid=True, time_s=1, variables={'D1.count': actual})
    result = check_assertion(ModuleTestAssertion(key='D1.count', expected=2**53), frame)
    assert not result.passed
    assert result.actual == actual and result.absolute_error == 1
    assert result.allowed_error == 0


@pytest.mark.parametrize('field', ['expected', 'absolute_tolerance', 'relative_tolerance'])
@pytest.mark.parametrize('value', [True, False, '1', float('nan'), float('inf'), -float('inf')])
def test_assertions_reject_non_finite_or_coerced_numbers(field, value):
    with pytest.raises(ValidationError):
        ModuleTestAssertion.model_validate({'key': 'D1.value', 'expected': 1, field: value})


@pytest.mark.parametrize('field', ['absolute_tolerance', 'relative_tolerance'])
def test_assertions_reject_negative_tolerances(field):
    with pytest.raises(ValidationError):
        ModuleTestAssertion.model_validate({'key': 'D1.value', 'expected': -1, field: -1e-12})


@pytest.mark.parametrize('key', ['', ' ', 'D1.value ', 'D1. value'])
def test_assertions_reject_empty_or_whitespace_keys(key):
    with pytest.raises(ValidationError):
        ModuleTestAssertion(key=key, expected=1)


def test_case_rejects_ambiguous_duplicate_assertions():
    with pytest.raises(ValidationError, match='测试断言变量键重复'):
        ModuleTestCase(id='duplicate', assertions=[{'key': 'D1.value', 'expected': 1}, {'key': 'D1.value', 'expected': 2}])


@pytest.mark.parametrize('invalid_frame', ['earlier', 'final'])
def test_passing_assertions_do_not_hide_invalid_simulation_frames(monkeypatch, invalid_frame):
    module = load_module_package(ROOT / 'modules/programmable_valve_sdk')
    first = RunFrame(status='converged', valid=invalid_frame != 'earlier', time_s=0, variables={'D1.value': 1})
    final = RunFrame(status='converged', valid=invalid_frame != 'final', time_s=1, variables={'D1.value': 1})
    response = ModuleTestResponse(module_id=module.id, content_hash='test', evaluation={}, committed={},
        frame=final, history=[first, final])
    monkeypatch.setattr('fn_engine.module_testing.run_module_test', lambda request: response)
    suite = ModuleTestSuiteRequest(module=module, cases=[{'id': 'invalid', 'assertions': [{'key': 'D1.value', 'expected': 1}]}])
    result = run_module_suite(suite)
    assert result.cases[0].assertions[0].passed
    assert not result.cases[0].passed and not result.passed
