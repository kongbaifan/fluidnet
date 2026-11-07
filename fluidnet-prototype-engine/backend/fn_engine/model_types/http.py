"""Http contracts; wire fields and validation preserve the legacy model semantics."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .._module_schema_v1 import Identifier, StrictModel
from ..air_models import AirVariableDescriptor, PsychrometricLine
from .base import Diagnostic, FluidConfig, FluidState, ModulePackageRef
from .domain import ControlScript, Project, ProjectDocument
from .module import ModuleDefinition, ModuleMigration, ModuleValidationEvidence, ModuleVersionInfo
from .module_testing import ModuleTestConditions, ModuleTestResponse
from .protocol import ModuleExecutionInfo, ModuleReplaySnapshot
from .run import RunEvent, RunFrame, RunOptions, RunRequest


class ControlPreviewRequest(StrictModel):
    project: Project
    script: ControlScript


class WorkspaceSaveRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    data: dict[str, Any]

    @model_validator(mode='after')
    def check_workspace(self):
        import json
        if self.data.get('schema') != 1:
            raise ValueError('工作区 schema 必须为 1')
        for field in ('projects', 'modules', 'models'):
            items = self.data.get(field)
            if not isinstance(items, list) or (field != 'models' and not items):
                raise ValueError(f'工作区缺少 {field}')
            ids = [item.get('id') for item in items if isinstance(item, dict)]
            if len(ids) != len(items) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                raise ValueError(f'{field} 的 ID 必须是唯一的非空字符串')
        if self.data.get('activeProject') not in {p['id'] for p in self.data['projects']}:
            raise ValueError('活动项目不存在')
        if len(json.dumps(self.data, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 64 * 1024 * 1024:
            raise ValueError('工作区超过 64 MiB，请导出并清理不需要的浏览器历史')
        return self


class ProjectSaveRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    document: ProjectDocument


class ProjectRevisionRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    revision: int = Field(ge=1)


class ProjectDeleteRequest(StrictModel):
    expected_revision: int = Field(ge=0)


class ProjectUpgradeRequest(StrictModel):
    project: Project
    module_id: Identifier
    target_version: int = Field(ge=1)
    migration: ModuleMigration | None = None


class SavedProjectRunRequest(RunOptions):
    """Run a persisted project snapshot; the server supplies its actual revision."""
    revision: int | None = Field(default=None, ge=1)


class ModuleReplayRequest(StrictModel):
    replay: ModuleReplaySnapshot


class ModuleReplayResponse(StrictModel):
    module_id: str
    status: Literal['failed', 'completed']
    matched_failure: bool
    execution: ModuleExecutionInfo
    content_hash: str
    definition_hash: str
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class ModuleFailureResponse(StrictModel):
    run_id: str
    replay: ModuleReplaySnapshot | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class ModuleSaveRequest(StrictModel):
    module: ModuleDefinition
    expected_latest_version: int = Field(ge=0)
    release_notes: str = Field(default="", max_length=2000)
    test: ModuleTestConditions = Field(default_factory=ModuleTestConditions)


class ModuleVersionResponse(ModuleVersionInfo):
    module: ModuleDefinition
    test_conditions: ModuleTestConditions | None = None
    test_result: ModuleTestResponse | None = None


class ModuleVersionsResponse(StrictModel):
    versions: list[ModuleVersionInfo] = Field(default_factory=list)


class RunStatus(StrictModel):
    run_id: str
    status: Literal["queued", "running", "paused", "stopping", "completed", "failed", "cancelled", "interrupted"]
    mode: Literal["steady", "dynamic"]
    progress: float = Field(default=0.0, ge=0, le=1)
    frame: RunFrame | None = None
    total_rows: int = Field(default=0, ge=0)
    command_id: str | None = None
    command_status: Literal['accepted', 'applied', 'rejected'] | None = None
    applied_time_s: float | None = None
    message: str | None = None
    lag_s: float = 0.0


class ErrorDetail(Diagnostic):
    """结构化错误 `detail`：服务端主动抛出的 code/message，可带诊断与定位字段。"""
    code: str
    message: str
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    keys: list[str] = Field(default_factory=list)
    instance_id: str | None = None
    field: str | None = None
    replay: dict[str, Any] | None = Field(default=None, exclude_if=lambda value: value is None)


class ValidationIssue(BaseModel):
    """FastAPI/Pydantic 请求校验失败时 `detail` 列表中的一项（字段随错误类型变化）。"""
    model_config = ConfigDict(extra='allow')

    type: str
    loc: list[str | int] = Field(default_factory=list)
    msg: str
    input: Any = None


class ErrorResponse(StrictModel):
    """HTTP 错误响应包络。

    运行时 FastAPI 统一输出 `{"detail": …}`：`detail` 可能是结构化错误（`ErrorDetail`）、
    纯文本说明，或请求校验问题列表。本模型只用于 OpenAPI 文档化，不改变运行时响应体。
    """
    detail: ErrorDetail | str | list[ValidationIssue]


class CircuitInfo(StrictModel):
    """One fluid circuit of a compiled project: its fluid and the ports it contains."""
    id: int
    fluid: FluidConfig
    source: str  # CircuitFluid.id that set the fluid, or "project"
    ports: list[str] = Field(default_factory=list)


class ValidationResponse(StrictModel):
    valid: bool
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    circuits: list[CircuitInfo] = Field(default_factory=list)


class RunCreateResponse(StrictModel):
    run_id: str
    status: str
    frame: RunFrame | None = None
    total_rows: int = Field(default=0, ge=0)


class RunHistoryResponse(StrictModel):
    rows: list[RunFrame] = Field(default_factory=list)
    # total_rows counts every frame published so far; offsets are absolute frame indices.
    total_rows: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)
    # Oldest frame still held (older frames left the history window); `truncated` when the
    # requested offset was older than that and the rows start at first_offset instead.
    first_offset: int = Field(default=0, ge=0)
    truncated: bool = False


class RunOverviewResponse(StrictModel):
    """Every `stride`-th frame of the whole run (≤ ~2000 rows) plus the latest frame."""
    rows: list[RunFrame] = Field(default_factory=list)
    stride: int = Field(default=1, ge=1)
    total_rows: int = Field(default=0, ge=0)


class RunEventsResponse(StrictModel):
    run_id: str
    events: list[RunEvent] = Field(default_factory=list)


class CatalogResponse(StrictModel):
    modules: list[ModuleDefinition] = Field(default_factory=list)
    prototype_parameter_bindings: dict[str, dict[str, str]] = Field(default_factory=dict)


class ModuleCatalogItem(ModuleDefinition):
    validation_evidence: list[ModuleValidationEvidence] = Field(default_factory=list)
    package: ModulePackageRef | None = None


class ModuleCatalogResponse(StrictModel):
    modules: list[ModuleCatalogItem] = Field(default_factory=list)


class ProjectValidationResponse(ValidationResponse):
    pass


class RunRecordResponse(StrictModel):
    id: str
    status: str
    mode: str
    request: RunRequest
    frame: RunFrame | None = None
    events: list[RunEvent] = Field(default_factory=list)
    total_rows: int = 0
    lag_s: float = 0.0
    persisted_at: str | None = None
    persisted_rows: int = 0
    air_metadata: dict | None = None


class AirVariableCatalogResponse(StrictModel):
    contract_version: Literal[1] = 1
    project_id: str
    run_id: str | None = None
    project_revision: int | None = None
    variables: list[AirVariableDescriptor]
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class AirPropertyResponse(StrictModel):
    contract_version: Literal[1] = 1
    property_backend: Literal['coolprop_ha'] = 'coolprop_ha'
    property_version: str
    state: FluidState
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class AirGridResponse(StrictModel):
    contract_version: Literal[1] = 1
    pressure_pa: float
    temperature_min_k: float
    temperature_max_k: float
    humidity_max_kg_kg: float
    lines: list[PsychrometricLine]
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class AirMigrationRequest(StrictModel):
    project: Project
    upgrade_official_modules: bool = False


class AirMigrationResponse(StrictModel):
    original_project: Project
    project: Project
    changes: list[str]
    valid: bool
    diagnostics: list[Diagnostic]


class RefpropInfo(StrictModel):
    """`GET /health` 上报的 REFPROP 运行时发现结果（不加载 DLL）。"""
    installed: bool
    source: Literal['env', 'bundled', 'system'] | None = None
    path: str | None = None
    version: str | None = None


class HealthCapabilities(StrictModel):
    moist_air_contract_version: Literal[1] | None = None
    wet_cooling_coil: bool = False
    air_humidifier: bool = False
    ahu_components: bool = False
    air_room: bool = False
    cooling_tower_moist: bool = False
    air_variable_catalog: bool = False
    water_coil: bool = False
    water_chiller: bool = False
    air_liquid_coupling: bool = False
    room_temperature_control: bool = False
    air_reports: bool = False
    thermal_coupling: bool = False
    thermal_coupling_liquid_modules: bool = False
    # Two immersed coils bound to one saturated vessel (contract limit is two).
    dual_thermal_coupling: bool = False
    # Built-in ideal electric heater in the single-phase fluid network.
    heater: bool = False
    # Rectangular air ducts (`duct`): hydraulic-diameter friction and optional ambient heat loss.
    air_duct: bool = False
    # Moist-air networks: humidity-ratio transport, wet cooling coil and humidifier.
    moist_air: bool = False
    scenario_batches: bool = False
    # Saturated vessels with up to four stream inlets (`hp_receiver_multi`, `lp_drum_multi`).
    multi_inlet_vessels: bool = False
    cold_room_ideal_source: bool = False
    refrigeration_station: bool = False
    # Case A: storage room + goods, unit cooler, single-stage cycle, schedule events and reports.
    cold_store_cycle: bool = False
    steady_hydraulics: bool
    quasi_steady_series: bool
    thermal: bool
    property_coupling: list[str] = Field(default_factory=list)
    tank_state: bool
    time_integration: str
    coolprop_single_phase: bool
    user_code: bool
    worker_process: bool
    async_runs: bool
    module_versions: bool
    run_control: bool
    live_runs: bool
    pid: bool
    runtime_parameters: bool
    continuous_step: bool
    continuous_runs: bool
    variables_api: bool
    run_stream: bool
    python_controls: bool
    persistent_workspace: bool
    refprop: RefpropInfo


class HealthAuth(StrictModel):
    required: bool


class HealthResponse(StrictModel):
    """`GET /health`：版本、能力标志与全局上限。"""
    status: str
    mode: Literal['studio', 'headless']
    version: str
    solver: str
    supported_domains: list[str] = Field(default_factory=list)
    capabilities: HealthCapabilities
    max_frames: int = Field(ge=0)
    run_retention: int = Field(ge=0)
    history_window_max: int = Field(ge=0)
    overview_points: int = Field(ge=0)
    auth: HealthAuth


class WorkspaceRevision(StrictModel):
    revision: int = Field(ge=0)
    saved_at: str


class WorkspaceResponse(StrictModel):
    """`GET /workspace`：最新（或指定修订）完整工作区；未保存时 revision=0、data=null。"""
    revision: int = Field(ge=0)
    saved_at: str | None = None
    data: dict[str, Any] | None = None
    project_revisions: dict[str, int] = Field(default_factory=dict)


class WorkspaceRevisionsResponse(StrictModel):
    revisions: list[WorkspaceRevision] = Field(default_factory=list)


class WorkspaceStorageResponse(StrictModel):
    database_bytes: int = Field(ge=0)
    reusable_bytes: int = Field(ge=0)
    wal_bytes: int = Field(ge=0)
    free_disk_bytes: int = Field(ge=0)
    runs: int = Field(ge=0)
    frames: int = Field(ge=0)
    revision_retention: int = Field(ge=0)
    run_retention: int = Field(ge=0)
    history_window_max: int = Field(ge=0)
    overview_points: int = Field(ge=0)


class WorkspaceSaveResponse(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    project_revisions: dict[str, int] = Field(default_factory=dict)


class WorkspaceRestoreResponse(StrictModel):
    directory: str
    revision: int = Field(ge=0)
    command: str
    message: str


class ControlPreviewResponse(StrictModel):
    """`POST /controls/preview`：一次 initialize+step 的拟写入值，不产生运行档案。"""
    state: dict[str, Any] = Field(default_factory=dict)
    writes: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    content_hash: str
    time_s: float = 0.0
    applied: bool = False


class ProjectSummary(StrictModel):
    id: str
    name: str
    revision: int = Field(ge=1)
    saved_at: str
    instances: int = Field(ge=0)


class ProjectListResponse(StrictModel):
    projects: list[ProjectSummary] = Field(default_factory=list)


class ProjectRevisionInfo(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    deleted: bool = False


class ProjectRevisionsResponse(StrictModel):
    revisions: list[ProjectRevisionInfo] = Field(default_factory=list)


class ProjectDetailResponse(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    document: ProjectDocument


class ProjectSaveResponse(StrictModel):
    revision: int = Field(ge=1)
    saved_at: str
    workspace_revision: int = Field(ge=1)
    previous_workspace_revision: int = Field(ge=0)


class ProjectRestoreResponse(ProjectSaveResponse):
    document: ProjectDocument


class ProjectDeleteResponse(ProjectSaveResponse):
    pass


class ProjectUpgradeChange(StrictModel):
    field: str
    id: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None


class ProjectUpgradeResponse(StrictModel):
    """`POST /project-upgrades/preview`：版本差异与兼容性结论；兼容时附升级后的项目。"""
    module_id: str
    from_version: int = Field(ge=1)
    to_version: int = Field(ge=1)
    from_hashes: ModulePackageRef
    to_hashes: ModulePackageRef
    source_before: str
    source_after: str
    changes: list[ProjectUpgradeChange] = Field(default_factory=list)
    compatible: bool
    reasons: list[str] = Field(default_factory=list)
    module: ModuleDefinition
    project: Project | None = None
    references: list[str] = Field(default_factory=list)
    migration: ModuleMigration | None = None


class RunSummary(StrictModel):
    id: str
    status: str
    mode: str
    name: str
    time_s: float = 0.0


class RunListResponse(StrictModel):
    runs: list[RunSummary] = Field(default_factory=list)


class RunDeleteResponse(StrictModel):
    deleted: str
