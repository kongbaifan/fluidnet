"""HTTP transport for the same in-process registry, under the host's existing auth policy."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..errors import protected_error_responses
from .contracts import (
    AdapterCatalog, AdapterDescription, AdapterError, AdapterErrorResponse, AdapterFailure,
    AdapterId, AdapterRequest, AdapterResult, correlate_failure,
)
from .registry import AdapterRegistry


def validation_response(error: RequestValidationError) -> JSONResponse:
    first = error.errors()[0]
    detail = AdapterFailure(code='ADAPTER_INPUT_INVALID', message=first['msg'],
                            field='.'.join(str(part) for part in first['loc']))
    correlate_failure(detail, error.body)
    return JSONResponse(status_code=422, content={'detail': detail.model_dump(mode='json')})


def adapter_router(registry: AdapterRegistry) -> APIRouter:
    router = APIRouter(prefix='/api/v1/adapters', tags=['Calculation adapters'])
    failures = protected_error_responses('ADAPTER_NOT_FOUND', 'ADAPTER_INPUT_INVALID', 'ADAPTER_UNIT_INVALID',
        'ADAPTER_CALCULATION_FAILED', 'ADAPTER_INTERNAL_ERROR', 'ADAPTER_OUTPUT_INVALID')
    for status in (404, 422, 500):
        failures[status]['model'] = AdapterErrorResponse

    @router.get('', response_model=AdapterCatalog, responses=protected_error_responses('INTERNAL_ERROR'))
    def catalog():
        return registry.catalog()

    @router.post('/execute', response_model=AdapterResult, responses=failures)
    def execute(request: AdapterRequest):
        try:
            return registry.execute(request)
        except AdapterError as error:
            raise HTTPException(error.status, detail=error.detail.model_dump(mode='json')) from error

    @router.get('/{adapter_id}', response_model=AdapterDescription, responses=failures)
    def describe(adapter_id: AdapterId, version: int = Query(1, ge=1)):
        try:
            return registry.describe(adapter_id, version)
        except AdapterError as error:
            error.detail.adapter_id, error.detail.version = adapter_id, version
            raise HTTPException(error.status, detail=error.detail.model_dump(mode='json')) from error

    return router
