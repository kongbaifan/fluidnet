"""风侧只读查询与冻结目录；认证沿用主应用 read/control 中间件。"""
from functools import lru_cache

import CoolProp
from fastapi import HTTPException, Query

from .air_models import AirPropertyRequest
from .air_variables import collect_air_variables, is_air_project
from .compiler import CompilationError, compile_project
from .errors import protected_error_responses
from .models import AirGridResponse, AirMigrationRequest, AirMigrationResponse, AirPropertyResponse, AirVariableCatalogResponse, Project
from .moist_air import AirPropertyError, MoistAirService


@lru_cache(maxsize=32)
def psychrometric_grid(pressure,low,high,maximum,version):
    service=MoistAirService()
    lines=[]
    for rh in (i/10 for i in range(1,11)):
        segments=[];segment=[]
        for i in range(161):
            t=low+(high-low)*i/160
            w=service.humidity_from_rh(pressure,t,rh)
            if w <= maximum:
                segment.append({'temperature_k':t,'humidity_ratio_kg_kg':w})
            elif segment:
                segments.append(segment);segment=[]
        if segment:
            segments.append(segment)
        lines.append({'relative_humidity':rh,'segments':segments})
    return {'pressure_pa':pressure,'temperature_min_k':low,'temperature_max_k':high,
            'humidity_max_kg_kg':maximum,'lines':lines}


def register_air_routes(app,get_run):
    errors=protected_error_responses(422,'INTERNAL_ERROR')

    @app.post('/api/v1/air/migrations/preview',response_model=AirMigrationResponse,responses=errors)
    def migration(request:AirMigrationRequest):
        from .migrations import preview_air_migration
        try:
            return preview_air_migration(request.project,request.upgrade_official_modules)
        except ValueError as error:
            raise HTTPException(422,detail={'code':'AIR_MIGRATION_INVALID','message':str(error)}) from error

    @app.post('/api/v1/air/properties',response_model=AirPropertyResponse,responses=errors)
    def properties(request:AirPropertyRequest):
        service=MoistAirService()
        try:
            if request.input_mode=='phw':
                state=service.state_phw(request.pressure_pa,request.enthalpy_j_kg_dry_air,request.humidity_ratio_kg_kg)
            else:
                w=(service.humidity_from_rh(request.pressure_pa,request.temperature_k,request.relative_humidity)
                   if request.input_mode=='ptrh' else request.humidity_ratio_kg_kg)
                state=service.state_ptw(request.pressure_pa,request.temperature_k,w)
        except AirPropertyError as error:
            raise HTTPException(422,detail={'code':error.code,'message':str(error)}) from error
        return AirPropertyResponse(property_version=CoolProp.__version__,state=state)

    @app.get('/api/v1/air/psychrometric-grid',response_model=AirGridResponse,responses=errors)
    def grid(pressure_pa:float=Query(101325,ge=60000,le=120000),
             temperature_min_k:float=Query(273.15,ge=253.15,le=333.15),
             temperature_max_k:float=Query(323.15,ge=253.15,le=333.15),
             humidity_max_kg_kg:float=Query(.03,gt=0,le=.05)):
        if temperature_max_k <= temperature_min_k:
            raise HTTPException(422,detail={'code':'AIR_PROPERTY_RANGE','message':'温度上限必须大于下限'})
        try:
            return psychrometric_grid(pressure_pa,temperature_min_k,temperature_max_k,humidity_max_kg_kg,CoolProp.__version__)
        except AirPropertyError as error:
            raise HTTPException(422,detail={'code':error.code,'message':str(error)}) from error

    @app.post('/api/v1/air/variables/preview',response_model=AirVariableCatalogResponse,responses=errors)
    def preview(project:Project):
        try:
            if not is_air_project(project):
                raise CompilationError('AIR_PROJECT_REQUIRED','请提供湿空气或湿空气冷却塔项目')
            network=compile_project(project)
            return AirVariableCatalogResponse(project_id=project.id,variables=collect_air_variables(project),diagnostics=network.diagnostics)
        except CompilationError as error:
            raise HTTPException(422,detail=error.diagnostic.model_dump()) from error

    @app.get('/api/v1/runs/{run_id}/air-variables',response_model=AirVariableCatalogResponse,
             responses=protected_error_responses(404,409,'STORAGE_FAILED','INTERNAL_ERROR'))
    def run_variables(run_id:str):
        record=get_run(run_id)
        metadata=record.get('air_metadata')
        if not metadata:
            raise HTTPException(409,detail={'code':'AIR_METADATA_UNAVAILABLE','message':'该运行没有风侧合同元数据；历史结果保持原始语义'})
        return {'project_id':record['request']['project']['id'],'run_id':run_id,
                'project_revision':record['request'].get('project_revision'),'variables':metadata['variable_catalog']}
