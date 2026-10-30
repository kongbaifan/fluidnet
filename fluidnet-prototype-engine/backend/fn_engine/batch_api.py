from contextlib import contextmanager

from fastapi import APIRouter, HTTPException, Query, Response

from .batch_models import (
    BatchCreateRequest, BatchCurveResponse, BatchDeleteResponse, BatchDetailResponse,
    BatchListResponse, BatchPlanRequest, BatchPreviewResponse, BatchSetupResponse,
)
from .batch_store import BatchConflict
from .batches import BatchService
from .compiler import CompilationError
from .errors import protected_error_responses


@contextmanager
def batch_errors():
    try:
        yield
    except KeyError as error:
        raise HTTPException(404, detail={'code': 'BATCH_NOT_FOUND', 'message': '批次、工况或源项目修订不存在'}) from error
    except BatchConflict as error:
        raise HTTPException(409, detail={'code': 'BATCH_CONFLICT', 'message': str(error)}) from error
    except CompilationError as error:
        raise HTTPException(422, detail=error.diagnostic.model_dump(mode='json')) from error
    except ValueError as error:
        raise HTTPException(422, detail={'code': 'BATCH_INVALID', 'message': str(error)}) from error


def batch_router(service: BatchService | None):
    router = APIRouter(prefix='/api/v1', tags=['Scenario batches'])
    failures = protected_error_responses('BATCH_NOT_FOUND', 'BATCH_CONFLICT', 'BATCH_INVALID', 503, 'STORAGE_FAILED')

    def require_service():
        if service is None:
            raise HTTPException(503, detail='批量工况需要持久工作区，请为服务配置 data_root')
        return service

    @router.get('/projects/{project_id}/batch-options', response_model=BatchSetupResponse, responses=failures)
    def options(project_id: str, revision: int | None = Query(None, ge=1)):
        with batch_errors():
            return require_service().setup(project_id, revision)

    @router.post('/projects/{project_id}/batches/preview', response_model=BatchPreviewResponse, responses=failures)
    def preview(project_id: str, request: BatchPlanRequest):
        with batch_errors():
            return require_service().prepare(project_id, request)[1]

    @router.post('/projects/{project_id}/batches', response_model=BatchDetailResponse, status_code=201, responses=failures)
    def create(project_id: str, request: BatchCreateRequest):
        with batch_errors():
            return require_service().create(project_id, request)

    @router.get('/batches', response_model=BatchListResponse, responses=failures)
    def list_batches(project_id: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        with batch_errors():
            return require_service().list(project_id, offset, limit)

    @router.get('/batches/{batch_id}', response_model=BatchDetailResponse, responses=failures)
    def detail(batch_id: str):
        with batch_errors():
            return require_service().detail(batch_id)

    @router.post('/batches/{batch_id}/start', response_model=BatchDetailResponse, responses=failures)
    def start(batch_id: str):
        with batch_errors():
            return require_service().start(batch_id)

    @router.post('/batches/{batch_id}/cancel', response_model=BatchDetailResponse, responses=failures)
    def cancel(batch_id: str):
        with batch_errors():
            return require_service().cancel_remaining(batch_id)

    @router.post('/batches/{batch_id}/delete', response_model=BatchDeleteResponse, responses=failures)
    def delete(batch_id: str):
        with batch_errors():
            return require_service().store.delete(batch_id)

    @router.get('/batches/{batch_id}/items/{item_id}/curve', response_model=BatchCurveResponse, responses=failures)
    def curve(batch_id: str, item_id: str, key: str = Query(..., min_length=1, max_length=512)):
        with batch_errors():
            return require_service().store.curve(batch_id, item_id, key)

    @router.get('/batches/{batch_id}/export', response_class=Response, responses={
        **failures, 200: {'content': {'text/csv': {'schema': {'type': 'string'}}}, 'description': '批次比较表（UTF-8 CSV）'}})
    def export(batch_id: str):
        with batch_errors():
            content = require_service().csv(batch_id)
            return Response(content=content, media_type='text/csv',
                            headers={'Content-Disposition': f'attachment; filename="batch-{batch_id}.csv"'})

    return router
