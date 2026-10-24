"""Independent, explicit test cases shared by authoring and release services."""
import hashlib
import json

from .bench import run_module_test
from .models import Diagnostic, ModuleTestRequest, ModuleTestCaseResult, ModuleTestSuiteResponse
from .runtime import module_content_hash, module_definition_hash


def run_module_suite(request):
    cases = []
    for case in request.cases:
        conditions = case.conditions.model_dump(mode='json')
        digest = hashlib.sha256(json.dumps(conditions, sort_keys=True, ensure_ascii=False,
            separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        try:
            result = run_module_test(ModuleTestRequest(module=request.module, **conditions))
            cases.append(ModuleTestCaseResult(id=case.id, passed=all(frame.valid for frame in result.history),
                input_hash=digest, result=result, diagnostics=result.frame.diagnostics))
        except (ValueError, OSError) as error:
            diagnostic = getattr(error, 'diagnostic', None)
            diagnostics = getattr(error, 'diagnostics', None) or ([diagnostic] if diagnostic else
                [Diagnostic(code=getattr(error, 'code', 'MODULE_TEST_FAILED'), message=str(error))])
            cases.append(ModuleTestCaseResult(id=case.id, passed=False, input_hash=digest, diagnostics=diagnostics))
    return ModuleTestSuiteResponse(module_id=request.module.id, content_hash=module_content_hash(request.module),
        definition_hash=module_definition_hash(request.module), passed=all(case.passed for case in cases), cases=cases)
