"""Independent, explicit test cases shared by authoring and release services."""
import hashlib
import json
import math
from fractions import Fraction

from .bench import run_module_test
from .models import (
    Diagnostic, ModuleTestAssertion, ModuleTestAssertionResult, ModuleTestRequest,
    ModuleTestCaseResult, ModuleTestSuiteRequest, ModuleTestSuiteResponse, RunFrame,
)
from .runtime import module_content_hash, module_definition_hash


def check_assertion(assertion: ModuleTestAssertion, frame: RunFrame) -> ModuleTestAssertionResult:
    fields = assertion.model_dump()
    if assertion.key not in frame.variables:
        return ModuleTestAssertionResult(**fields, passed=False, status='missing', message='最终帧中不存在该变量')
    actual = frame.variables[assertion.key]
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        return ModuleTestAssertionResult(**fields, actual=actual, passed=False, status='non_numeric',
            message='最终帧变量必须是数值，不能是布尔值、字符串或空值')
    if isinstance(actual, float) and not math.isfinite(actual):
        return ModuleTestAssertionResult(**fields, passed=False, status='non_finite', message='最终帧变量不是有限浮点数')
    # Compare the exact values of the supplied finite numbers: converting an integer
    # to float can erase a unit above 2**53; float differences/products can overflow.
    expected = Fraction(assertion.expected)
    error = abs(Fraction(actual) - expected)
    allowed = max(Fraction(assertion.absolute_tolerance), Fraction(assertion.relative_tolerance) * abs(expected))
    passed = error <= allowed
    errors: list[float | None] = []
    for value in (error, allowed):
        try:
            errors.append(float(value))
        except OverflowError:
            errors.append(None)
    message = '最终帧数值满足容差' if passed else '最终帧数值超出容差'
    if None in errors:
        message += '；超出浮点表示范围的误差或容差返回 null，判定保留有效比较结果'
    return ModuleTestAssertionResult(**fields, actual=actual,
        absolute_error=errors[0], allowed_error=errors[1],
        passed=passed, status='passed' if passed else 'outside_tolerance', message=message)


def run_module_suite(request: ModuleTestSuiteRequest) -> ModuleTestSuiteResponse:
    cases = []
    for case in request.cases:
        conditions = case.conditions.model_dump(mode='json')
        # Preserve hashes for existing suites; asserted cases bind their author-supplied
        # expectations as well as their simulation inputs to the evidence digest.
        inputs = {'conditions': conditions, 'assertions': [item.model_dump(mode='json') for item in case.assertions]} if case.assertions else conditions
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False,
            separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        try:
            result = run_module_test(ModuleTestRequest(module=request.module, **conditions))
            assertions = [check_assertion(item, result.frame) for item in case.assertions]
            passed = result.frame.valid and all(frame.valid for frame in result.history) and all(item.passed for item in assertions)
            cases.append(ModuleTestCaseResult(id=case.id, passed=passed,
                input_hash=digest, result=result, diagnostics=result.frame.diagnostics, assertions=assertions))
        except (ValueError, OSError) as error:
            diagnostic = getattr(error, 'diagnostic', None)
            diagnostics = getattr(error, 'diagnostics', None) or ([diagnostic] if diagnostic else
                [Diagnostic(code=getattr(error, 'code', 'MODULE_TEST_FAILED'), message=str(error))])
            assertions = [ModuleTestAssertionResult(**item.model_dump(), passed=False, status='not_evaluated',
                message='测试运行失败，未执行数值断言') for item in case.assertions]
            cases.append(ModuleTestCaseResult(id=case.id, passed=False, input_hash=digest, diagnostics=diagnostics,
                assertions=assertions))
    return ModuleTestSuiteResponse(module_id=request.module.id, content_hash=module_content_hash(request.module),
        definition_hash=module_definition_hash(request.module), passed=all(case.passed for case in cases), cases=cases)
