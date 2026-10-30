# HTTP API

默认服务：127.0.0.1:8798。`/docs` 为交互文档，`/openapi.json` 为运行时定义，`contracts/openapi.json` 为生成的合同快照。

## 已实现端点

| 方法与路径 | 请求 | 返回模型与内容 | 错误响应（`detail.code`） |
| --- | --- | --- | --- |
| GET /api/v1/health | 无 | `HealthResponse`：版本（0.5.0）、`mode`（`studio` 或 `headless`）、`supported_domains`（`fluid`、`thermal`、`refrigerant`）、能力标志（含 `thermal`、`property_coupling`、`tank_state`、`live_runs`、`pid`、`runtime_parameters`、`continuous_step`、`continuous_runs`、`variables_api`、`run_stream`、`python_controls`、`persistent_workspace`、`cold_room_ideal_source`，以及 `refprop: {installed,source,path,version}`）、`auth.required`、同步运行 2001 帧上限、`history_window_max`、`overview_points`、20 次记录保留数 | 500 `INTERNAL_ERROR`（health 不受令牌限制） |
| GET /api/v1/examples/{name} | `level`、`temperature`、`cold-storage`、`cold-storage-room`、`cold-storage-nh3co2` 或 `thermal-coupling` | `Project`：内置 PID、冷库或制冷站与二次液体回路示例；热耦合范围见 [说明](THERMAL_COUPLING.md) | 404（未知示例）；401/403 |
| GET /api/v1/workspace | 可选 revision | `WorkspaceResponse`：完整原型工作区、revision、saved_at、project_revisions；未保存时 data=null | 404（修订不存在）、503（持久存储未启用）、507 `STORAGE_FAILED`；401/403 |
| POST /api/v1/workspace | data、expected_revision | `WorkspaceSaveResponse`：已落盘修订、时间与项目修订映射 | 409 `WORKSPACE_CONFLICT`、503、507 `STORAGE_FAILED`；401/403 |
| GET /api/v1/workspace/revisions | 无 | `WorkspaceRevisionsResponse`：最近 5 个修订元数据 | 503、507；401/403 |
| GET /api/v1/workspace/storage | 无 | `WorkspaceStorageResponse`：数据库、可复用页、WAL、剩余磁盘字节数，运行/帧数量和保留上限 | 503、507；401/403 |
| POST /api/v1/workspace/backup | 无 | `application/zip` 二进制（无 JSON response_model；OpenAPI 显式声明 binary schema）：SQLite 一致快照、模块包与 SHA-256 清单 | 503、507；401/403 |
| POST /api/v1/workspace/restore | ZIP 原始字节，最多 256 MiB | `WorkspaceRestoreResponse`：新目录、revision、启动 command 和 message | 413（上传超限）、422（非法备份）、503、507；401/403 |
| POST /api/v1/controls/preview | project、script | `ControlPreviewResponse`：state、writes、diagnostics、content_hash、time_s、applied=false | 422（脚本/项目校验失败）；401/403 |
| POST /api/v1/runs/{run_id}/delete | 空对象 | `RunDeleteResponse`：`deleted` 为被删除的运行 ID | 404、409（活动运行未停止）、507；401/403 |
| GET /api/v1/catalog | 无 | `CatalogResponse`：模块参数/通路/变量目录、原型参数名映射 | 401/403 |
| GET /api/v1/modules | 无 | `ModuleCatalogResponse`：可安装模块包和内置模块清单、版本与内容哈希 | 500 `MODULE_STORAGE_ERROR`；401/403 |
| POST /api/v1/modules/validate | ModuleDefinition | `ValidationResponse`：契约、Python 语法、Worker 入口与四阶段签名诊断 | 422（请求体校验）；401/403 |
| POST /api/v1/modules/test | ModuleTestRequest | `ModuleTestResponse`：独立边界求解，返回 evaluation、committed、frame、history | 422（含 `MODULE_WORKER_IO_ERROR`）；401/403 |
| POST /api/v1/modules/design | ModuleDesignRequest | `ModuleDesignResponse`：独立 Worker 执行 design.py；返回 design_hash、parameters、changes、diagnostics | 422（非法输出，含 `MODULE_WORKER_IO_ERROR`）；401/403 |
| POST /api/v1/modules/versions | ModuleSaveRequest | **201** `ModuleVersionResponse`：校验试算通过后保存新版本 | 409 `MODULE_VERSION_CONFLICT`、422 `MODULE_SAVE_INVALID`、500 `MODULE_STORAGE_ERROR`；401/403 |
| GET /api/v1/modules/{module_id}/versions | 无 | `ModuleVersionsResponse`：倒序版本记录，未知模块返回空列表 | 500 `MODULE_STORAGE_ERROR`；401/403 |
| GET /api/v1/modules/{module_id}/versions/{version} | 整数版本 | `ModuleVersionResponse`：完整模块、引用和试算凭据 | 404（未知版本）、500；401/403 |
| POST /api/v1/prototype/normalize | 原型导出对象 | `Project`：规范 Project；显示单位转换 | 422（不能归一化）；401/403 |
| POST /api/v1/projects/validate | Project | `ValidationResponse`：valid、diagnostics 和 circuits（各回路的工质、来源、端口）；检查失败时 valid=false、circuits 为空 | 422（请求体校验）；401/403 |
| POST /api/v1/solve | Project | `RunFrame`：同步稳态 RunFrame | 422（计算失败或 `MODULE_WORKER_IO_ERROR`）、500 `INTERNAL_ERROR`；401/403 |
| POST /api/v1/runs | RunRequest | **201** `RunCreateResponse`（run_id、status、frame、total_rows）。`?background=true` 改返回 **202** `RunStatus`（queued、frame 为 null，frame 由状态接口补） | 422 `RUN_LIMIT`/`RUN_TOO_LONG`、500；401/403 |
| POST /api/v1/projects/{project_id}/runs | SavedProjectRunRequest：可选 revision、scenario_id 和运行选项 | **202** `RunStatus`：服务端固定已保存项目快照并创建后台运行，返回 run_id、queued | 404（项目或修订不存在）、422（文档/选项错误或 `RUN_LIMIT`）、503（持久存储未启用）、507 `STORAGE_FAILED`、500；401/403 |
| GET /api/v1/runs/{run_id} | 无 | `RunRecordResponse`：状态、请求快照、最后一帧与事件，不重复携带整段历史（历史由 /history 提供） | 404（记录不存在或已被保留上限淘汰，detail 为固定字符串）、507；401/403 |
| GET /api/v1/runs/{run_id}/history | offset≥0, 1≤limit≤2001（绝对帧序号） | `RunHistoryResponse`：rows、total_rows（已发布帧数）、offset（实际起点）、first_offset（窗口内最早帧）、truncated（请求的 offset 已移出窗口） | 404、507；401/403 |
| GET /api/v1/runs/{run_id}/overview | 无 | `RunOverviewResponse`：全程抽稀 rows（每 stride 帧一行加最新帧，只含曲线变量和状态，无诊断）、stride、total_rows | 404、507；401/403 |
| GET /api/v1/runs | 无 | `RunListResponse`：运行列表（活动运行与已归档运行：id、status、mode、项目名、当前 time_s） | 507；401/403 |
| GET /api/v1/runs/{run_id}/events | 无 | `RunEventsResponse`：状态事件与命令事件（accepted/applied/rejected），每次运行恰好一条终态事件；后台运行只保留最近 1000 条事件，已处理的命令回执也只保留最近 1000 个（更早的 `command_id` 重发会当作新命令） | 404、507；401/403 |
| POST /api/v1/runs/{run_id}/command | RunCommand | `RunStatus` 加命令回执；见「运行生命周期与控制」 | 404、409 `RUN_ALREADY_FINISHED`/`COMMAND_ID_CONFLICT`、422（命令校验）；401/403 |
| GET /api/v1/runs/{run_id}/variables | `keys`（逗号分隔的帧变量键，省略为全部） | `VariableValues`：status、time_s、sequence、parameter_revision、values | 404、409 `NO_FRAME`（还没有帧）、422 `VARIABLE_UNKNOWN`（附 keys）、507；401/403 |
| POST /api/v1/runs/{run_id}/variables | VariableWrite | `RunStatus` 加命令回执；见「变量接口」 | 404、409（运行已结束或命令冲突）、422；401/403 |
| WS /api/v1/runs/{run_id}/stream | `keys`、`interval_ms`（10–5000，默认 50） | WebSocket 推送（非 OpenAPI response）：`{"type":"frame",…}`，结束时 `{"type":"end","status":…}`；见「变量接口」 | WS 关闭码 4401（令牌无效）、4404（运行不存在）、4422（未知变量） |

`POST /api/v1/runs?background=true` 创建后台运行，返回 HTTP 202 和 `run_id`；已有 20 个非终态运行时返回 422 `RUN_LIMIT`。默认仍保持兼容的同步模式，返回 HTTP 201。前端稳态使用同步请求；动态项目在 health 报告 `live_runs` 时使用后台会话（运行、单步、暂停、改参数都对同一个 run_id 发命令）。同步运行不能中途控制。

`GET /api/v1/health` 的 `capabilities` 中，`dual_thermal_coupling`、`heater`、`multi_inlet_vessels`、`air_duct`、`moist_air` 分别表示双盘管（两条耦合绑定同一饱和容器）、内置电加热器、多支路饱和容器（`hp_receiver_multi` / `lp_drum_multi`）、内置矩形风管与湿空气输运（含湿量 + 湿工况表冷器/加湿器）。`capabilities.refprop` 为 `{"installed": bool, "source": "env" | "bundled" | "system" | null, "path": str | null, "version": str | null}`，向后兼容原来的 `installed` 布尔。`source` 表示 REFPROP 目录的发现方式：`env` 为环境变量 `FLUIDNET_REFPROP_PATH`，`bundled` 为捆绑候选（项目根、仓库根、当前工作目录或 `sys.executable` 所在目录下的 `vendor/refprop9.1`、`refprop9.1`、`refprop`、`NISTRefprop9.1`），`system` 为 Windows 默认安装目录 `C:\Program Files (x86)\REFPROP`；`path` 为实际生效目录，未检测到时两者为 `null`。`version` 优先取该目录 `refprop-manifest.json` 的 `version`，清单缺失或损坏时为 `null`，不影响 `installed`。详见 [内置 REFPROP 9.1](REFPROP_BUNDLE.md)。

## 批量工况与独立结果存档（2026-10-28）

`capabilities.scenario_batches` 表示批量工况能力；仅在启用持久工作区时为 true。批次创建时固定项目、模块和控制脚本输入，各项独立顺序运行。完整路径、请求示例与单位约定见[批量工况说明](SCENARIO_BATCHES.md)。

入口为 `GET /api/v1/projects/{project_id}/batch-options`、`POST /api/v1/projects/{project_id}/batches/preview` 和 `POST /api/v1/projects/{project_id}/batches`；创建返回 201 和 `BatchDetailResponse`，状态为 ready。之后通过 `POST /api/v1/batches/{batch_id}/start` 启动或继续未完成项。

`GET /api/v1/batches` 列表、`GET /api/v1/batches/{batch_id}` 详情、`POST …/cancel`、`POST …/delete`、`GET …/items/{item_id}/curve?key=…` 与 `GET …/export` 分别提供历史、控制、独立曲线和 CSV。JSON 响应均有严格模型；CSV 使用 `text/csv` 成功响应 schema。错误包括 404 `BATCH_NOT_FOUND`、409 `BATCH_CONFLICT`、422 `BATCH_INVALID`、503（未启用存储）及 507 `STORAGE_FAILED`。

参数扫描的 `values`／`range` 使用参数的**显示单位**；结果 `values` 和曲线点仍使用**规范单位**，由随批次固定的 `UnitSpec` 换算。每批最多 20 个工况、16 个观察变量，每条曲线最多 2000 个抽样点，首版一个活动批次。

## 错误响应与错误码（v0.4.10 起）

所有 HTTP 错误仍保持 FastAPI 的 `{"detail": …}` 包络，运行时响应体与状态码语义未变；OpenAPI 只是把错误路径文档化（`contracts/openapi.json` 中每个错误状态都引用 `ErrorResponse`）：

- 结构化错误：`{"detail": {"code": "...", "message": "...", "diagnostics": [...], "keys": [...], "instance_id": ..., "field": ...}}`，用于服务端主动抛出的业务错误；
- 纯文本错误：`{"detail": "..."}`，用于 404 资源不存在、409 活动运行、413 上传超限、422 文本校验、503 持久存储未启用等；
- 请求校验错误：`{"detail": [{"type", "loc", "msg", "input"}, …]}`（FastAPI/Pydantic 默认格式）。

`backend/fn_engine/errors.py` 是错误码的唯一注册表：`ERROR_CODES`（静态 `detail.code`）、`DIAGNOSTIC_CODES`（编译/求解/物性诊断码透传）、`STATUS_ERRORS`（无 code 的纯文本错误按状态登记）。路由通过 `error_responses()` / `protected_error_responses()` 生成 OpenAPI `responses`；除 `GET /api/v1/health` 外，所有 `/api/` 路由都声明 401 `AUTH_REQUIRED` 与 403 `AUTH_SCOPE`。

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| `AUTH_REQUIRED` | 401 | 缺少或无效的访问令牌（响应带 `WWW-Authenticate: Bearer`） |
| `AUTH_SCOPE` | 403 | 令牌权限不足以执行该请求方法（只读令牌发 POST） |
| `RUN_NOT_FOUND` | 404 | 运行记录不存在或已过期（WebSocket 关闭码 4404） |
| `PROJECT_CONFLICT` | 409 | 项目或工作区修订冲突（`WorkspaceConflict` 异常处理器） |
| `WORKSPACE_CONFLICT` | 409 | 工作区 `expected_revision` 陈旧 |
| `MODULE_VERSION_CONFLICT` | 409 | 模块版本写入冲突 |
| `RUN_ALREADY_FINISHED` | 409 | 运行已结束，命令被拒绝 |
| `COMMAND_ID_CONFLICT` | 409 | 命令 ID 已用于不同内容 |
| `NO_FRAME` | 409 | 运行还没有可读的帧 |
| `MODULE_SAVE_INVALID` | 422 | 模块版本校验或试算未通过（附 `diagnostics`） |
| `MODULE_WORKER_IO_ERROR` | 422 | 模块 Worker 子进程 I/O 故障 |
| `RUN_LIMIT` | 422 | 后台运行数量达到上限（20 个非终态运行） |
| `RUN_TOO_LONG` | 422 | 同步运行帧数超过 2001 上限 |
| `VARIABLE_UNKNOWN` | 422 | 请求的帧变量不存在（附 `keys`） |
| `MODULE_STORAGE_ERROR` | 500 | 模块版本写入失败（目录权限/磁盘空间） |
| `INTERNAL_ERROR` | 500 | 服务内部错误（原始信息保留，traceback 记入日志） |
| `STORAGE_FAILED` | 507 | 工作区存储故障（磁盘空间或目录权限，`StorageError` 处理器） |

编译/求解/物性层的诊断码（如 `SCENARIO_NOT_FOUND`、`SCENARIO_INSTANCE_MISSING`、`TREND_VARIABLE_UNKNOWN`、`SOLVER_ERROR` 以及编译器的完整诊断集）通过 `detail.code` 透传，HTTP 状态由所在路由决定（多为 422，运行命令冲突为 409）。

## 模块包和 Worker

模块包目录至少包含：

```text
manifest.json
module.py
```

`manifest.json` 由 `ModuleDefinition` 校验；`module.py` 的 SHA-256 保存为 `content_hash`。版本保存要求同步实现 `initialize(ctx)`、`evaluate(ctx)`、`commit_step(ctx, dt_s)`、`finalize(ctx)`，无逻辑的阶段可以使用 `pass`。入口加载和生命周期签名检查均在独立 Worker 中进行。兼容的直接运行接口仍容许省略可选阶段。

### 设计函数 design.py

可选的 `design.py`（定义中的 `source.design`，单个文本）实现 `design(ctx)`，由一组库值计算派生参数，不参与运行求解。`ctx.parameter(id)` 读取规范单位的参数值，`ctx.set(id, value)` 写出已声明参数，`ctx.fluid` 为当前工质物性服务，`ctx.log(text)` 最多 20 条。版本保存时校验语法与签名，`design.py` 随版本写入目录，由 `definition_hash` 覆盖；`content_hash` 仍只对应 `module.py`。

`POST /api/v1/modules/design` 接收 `ModuleDesignRequest {module, parameters, fluid}`，在独立 Worker 中执行一次，返回 `ModuleDesignResponse {module_id, design_hash, parameters, changes, diagnostics}`。输入和输出都按参数契约校验类型与范围；越限返回 422 `DESIGN_OUTPUT_INVALID`，未声明参数、非有限值、异常（含 design.py 行号）也返回 422。服务端不保存结果；浏览器在「变量值」页展示差异，确认后才写入所选库值。内置模型没有可执行的设计函数。

## 模块版本写入契约

`ModuleSaveRequest` 包含完整 `module`、`expected_latest_version`、`release_notes` 和可选 `test: ModuleTestConditions`。新 ID 的预期版本为 0，示例模块初始为 1。服务端分配当前版本加一，忽略草稿中的目标版本/哈希/文件路径，不接受覆盖旧版本。内置模型 ID 不可被 Python 模块占用。

`test` 与独立验证台共用参数、工质、边界、时长和步长模型。浏览器保存时使用契约默认参数，以及最近验证台的边界（如选中同一模块），重新执行试算。API 可显式提供测试参数覆盖。试算为每条启用通路各接一组独立压力边界并在一个网络中求解；共用端口、端口未绑定通路或非流体端口返回 422，不会绕过验证写入。

保存依次检查 Pydantic 默认值与引用、Python 语法和入口签名、initialize/evaluate/commit_step/finalize、最终声明输出。成功后将三份文件写入临时目录，原子重命名为版本目录。并发请求使用相同预期版本时只有一个成功；失败请求不留下可发现的半成品版本。

`ModuleVersionResponse` 包含 `module`、`package`（版本、源码哈希、完整定义哈希）、`created_at`、`release_notes`、`tested`、`test_conditions` 和 `test_result`。内置示例没有保存试算凭据，`tested=false`。GET 模块目录只返回每个 ID 的最新版本；历史版本由版本接口读取。

错误：Pydantic 字段错误返回 422/detail 数组；语法、加载、算法或声明输出缺失返回 422/detail `{code: MODULE_SAVE_INVALID, message, diagnostics}`；预期版本过期或同版本并发写入返回 409 `MODULE_VERSION_CONFLICT`；磁盘写入失败返回 500 `MODULE_STORAGE_ERROR`。前端始终保留未成功保存的编辑草稿。

`content_hash` 校验源代码；`definition_hash` 校验整个规范定义（排除两个哈希字段和机器路径，包含版本、参数、端口、输出和代码）。数字整数形式统一，避免浏览器把 `16.0` 序列化成 `16` 导致误报。项目中的 `ModuleInstance.package` 必须与定义快照一致；编译器另行计算哈希，不信任客户端声明。

Worker 消息使用 Pydantic 的 `InitializeRequest`、`EvaluateRequest`、`EvaluateResponse`、`CommitStepRequest` 和 `CommitStepResponse`。`evaluate` 输出 `NetworkRelation`，由网络求解器决定最终压力和流量；模块不能直接返回全网解。

同步请求返回 201 时，计算已经 completed 或 failed；后台请求返回 202 后通过状态接口查询，控制通过 `POST /runs/{run_id}/command`，变量推送使用 `WS /runs/{id}/stream`。保留最近 20 次已结束运行（活动运行不淘汰）；启用持久工作区时，项目与已落盘历史在重启后仍可读取，淘汰的运行返回 404。原型草稿由浏览器保留，点击保存后进入服务端 SQLite 工作区。

## 直接运行参考项目

服务启动后：

```powershell
$project = Get-Content -Raw -Encoding utf8 contracts\reference-project.json | ConvertFrom-Json
$request = @{ project = $project; mode = 'steady' } | ConvertTo-Json -Depth 100
$result = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8798/api/v1/runs' -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($request))
$result.frame.variables
Invoke-RestMethod ('http://127.0.0.1:8798/api/v1/runs/' + $result.run_id + '/history')
```

`contracts/reference-project.json` 是完整模块、实例与连接集合，不是空占位。`reference-result.json` 为同一算例的预期输出。

## 冷库案例 A1（2026-10-20）

`GET /api/v1/examples/cold-storage` 返回可直接运行的冷库 A1 示例 `Project`（`id=cold-room-ideal-v1`）：两台设备 `ROOM1`（`cold_room` 库房热节点）与 `COLD1`（`ideal_cold_source` 理想恒容量冷源）、一条热连接、一个库温 PID，默认动态运行 2 h / 30 s 发布 / 10 s 内部步长。前端项目页的「−18°C 冷库案例」按钮调用同一接口生成可保存副本。

- 热项目只含 `domain=thermal` 端口，运行方式与流体项目相同：`POST /api/v1/runs`（动态可走 `?background=true`）、命令、历史、归档、流式推送均沿用本文合同；`circuit_info` 为空，不返回水力回路。
- 帧变量为两台设备的 `param.*`、`ROOM1.state.temperature_k`、`ROOM1.envelope_heat_w`、`ROOM1.stored_energy_j`、`ROOM1.state.external_energy_j`、`ROOM1.cooling_power_w`、`COLD1.cooling_power_w`、`COLD1.state.cooling_energy_j`，另有 PID 变量；帧诊断含 `COLD_ROOM_IDEAL_SOURCE` 提示。
- 设备、参数、单位换算、诊断码与已知边界见 [数据合同「冷库 A1 热执行域」](DATA_CONTRACT.md#冷库-a1-热执行域2026-10-20)；数值方法与能量校核见 [算法文档](ALGORITHM.md#冷库-a1-热执行域2026-10-20)。

## RunRequest

```json
{
  "project": "此处填写完整 Project 对象，不是项目 ID",
  "mode": "dynamic",
  "duration_s": 30,
  "dt_s": 0.1,
  "scenario_id": null,
  "selected_variables": ["P1.mass_flow_kg_s", "V1.mass_flow_kg_s", "V2.mass_flow_kg_s"],
  "history": "full",
  "trend_variables": [],
  "execution_mode": "fast",
  "speed_ratio": 1.0,
  "start_paused": false
}
```

持续运行（v0.4.3）：`duration_s` 可为 `null`，只允许后台动态运行，一直推进到 `stop`。同步 `POST /runs` 一次返回全部帧，仍限 2001 帧且必须有时长，否则 422 `RUN_TOO_LONG`；更长的有限运行也走后台。后台运行只在内存保留最近 `history_window`（默认 2001，10–20001）帧，另存一条全程抽稀曲线：每 `stride` 帧一行，超过 2000 行时 `stride` 翻倍并丢掉不对齐的行。`history='trend'` 的关键帧间隔按 `min(总帧数, history_window) / 50` 计算，持续运行按窗口计算。

`execution_mode`、`speed_ratio`（0–100]、`start_paused` 只对后台动态运行有意义：`fast` 连续计算，`realtime` 按 `dt_s / speed_ratio` 墙钟间隔推进一帧；`start_paused=true` 时算完 t=0 后停在 paused，等待 step 或 resume。

上例 project 字段是说明占位，实际必须发送对象。mode 可为 steady 或 dynamic。dynamic 对没有状态设备的项目是准稳态序列，对含水箱的项目是隐式 Euler 时间推进（见 ALGORITHM）。selected_variables 为空数组表示全部；null/省略则使用 project.selected_variables，后者也为空则返回全部。未知变量使本次运行失败，不能静默丢弃。

### 历史瘦身（v0.3.1）

`history` 可取 `full`（默认，每帧保留全部变量）或 `trend`，只对 dynamic 生效（steady 只有一帧，忽略）。`trend` 时：

- 关键帧：首帧、末帧和每隔 K 帧（K = ceil(帧数/50)，最多约 51 帧）保留全部变量，`full=true`。
- 其余帧只保留 `trend_variables`（规范变量键，最多 256 个）和所有 `<实例>.state.*` 模块状态，`full=false`；`metrics` 每帧都保留；与上一关键帧相同的诊断从这些帧中省略，帧特有的诊断保留。
- 先按 selected_variables 过滤，再做瘦身。`trend_variables` 中任何一个键不在首帧或末帧中，运行失败，诊断码 `TREND_VARIABLE_UNKNOWN`（与未知 selected_variables 同一失败路径）。
- 取消的运行保留的部分帧同样瘦身；末帧始终完整。

实测 water-net 2001 帧：`full` 约 22.7 MB，`trend`（5 条曲线）约 1.74 MB（减少约 92%），关键帧 50 帧；曲线值与 `full` 逐帧完全相同。前端应只发送当前项目中存在的变量键，并在非关键帧沿用最近一个关键帧的设备读数。

兼容性：0.3.1 起每个 RunFrame 都带 `full` 字段（默认 `true`）。按 0.3.0 的 `run-frame.schema.json`（`additionalProperties: false`）严格校验响应的客户端需要更新 schema；只读取已有字段的客户端不受影响。

scenario_id 指向 Project.scenarios。覆盖只修改本次运行的项目副本，参数仍按相同规则校验。未实现随时间变化的参数计划。

`/projects/validate` 现在也校验每个工况的覆盖：引用不存在的实例返回 `SCENARIO_INSTANCE_MISSING`；覆盖未知参数或把数值写到越界、非有限值返回 `UNKNOWN_PARAMETER`、`PARAMETER_RANGE`、`PARAMETER_INVALID`(诊断消息带 `工况 <id>:` 前缀)。因此此前被判为 valid 的项目现在可能 valid=false。

## RunFrame

```json
{
  "status": "converged",
  "valid": true,
  "time_s": 0,
  "variables": {
    "V1.mass_flow_kg_s": 3.5826766415095452,
    "V1.out0.temperature_k": 293.18118038705103,
    "V1.out0.enthalpy_j_kg": 84218.99861178166,
    "P1.shaft_power_w": 733.8810612788247,
    "P1.heat_w": 733.8810612788526
  },
  "diagnostics": [],
  "metrics": {
    "pressure_residual_pa": 1.02e-10,
    "mass_residual_kg_s": 4.44e-16,
    "iterations": 7,
    "node_count": 5,
    "branch_count": 5,
    "thermal_iterations": 1,
    "coupling_iterations": 1,
    "energy_residual_w": 3.36e-10,
    "reference_heat_w": 0.0
  }
}
```

该示例取自 `contracts/reference-result.json`，省略了其他变量和归一化提示。valid 表示当前声明的水力方程和热力层（`thermal=True` 时）已通过验收；含水箱的动态帧还表示水箱储能方程已通过验收。`SolverOptions.thermal=False` 时热力变量为 null，指标中没有热力项。

### 时间误差控制设置与指标（A0–A4）

`Project.solver.time_step` 保存时间误差控制设置（`TimeStepOptions`）：`enabled`（默认 false）、`mass_atol_kg`、`energy_atol_j`、`temperature_atol_k`、`rtol`、`min_internal_step_s`、`max_internal_step_s`（null 表示沿用 `dynamic_step_s`）、`safety`、`growth_factor`、`shrink_factor`。项目保存/恢复、工况复制和运行请求都携带这些字段；缺字段按旧固定步长行为解释。首轮只在理想热模型（`thermal`）与冷库 B（`refrigeration`）生效，其他执行域开启时编译/建会话报 `TIMESTEP_DOMAIN_UNSUPPORTED`。

这两个执行域的 `RunFrame.metrics` 另有稳定键：`timestep_adaptive`（1/0）、`internal_step_s`、`internal_steps`、`internal_rejections`、`solver_retries`、`boundary_truncations`、`local_error_norm_max`、`internal_steps_total`、`internal_rejections_total`、`accepted_step_min_s`、`accepted_step_max_s`。其中 `local_error_norm_max` 是 step-doubling 的 **局部** 时间离散误差范数最大值，不是全程误差，也不是模型准确度保证；冷库报告按“局部时间离散误差范数最大值”展示并附此说明。最小步长仍不满足误差时运行以 `TIME_STEP_MIN_EXCEEDED` 失败、边界截断的细小步仍不满足时以 `TIME_STEP_BOUNDARY_EXCEEDED` 失败，两种记录都保留失败前已接受的 history。

Diagnostic 包含 code、message、severity（info/warning/error）、可选 instance_id 与 field。前端可以定位到实例。结构错误采用 PORT_UNCONNECTED、BOUNDARY_CONFLICT、BOUNDARY_TEMPERATURE_CONFLICT、PRESSURE_REFERENCE_MISSING、MODEL_NOT_SUPPORTED 等代码;参数与工况错误采用 PARAMETER_RANGE(含 `diameter_m` 不大于零、`roughness_m` 为负)、ROUGHNESS_RANGE、UNKNOWN_PARAMETER、PARAMETER_INVALID、CURVE_INVALID、SCENARIO_INSTANCE_MISSING 等代码;热力错误采用 PHASE_UNSUPPORTED、NO_FLOW_HEAT、THERMAL_REFERENCE_MISSING、THERMAL_NOT_CONVERGED、COUPLING_NOT_CONVERGED 等代码(完整列表见数据合同文档)。

POST /runs 对类型正确但编译或求解失败的请求仍创建可查询的记录，status=failed、frame.valid=false、history 为空。例外：动态运行在水箱事件（`TANK_EMPTY`、`TANK_FULL`）或 `STEP_NOT_CONVERGED` 处停止时，history 保留已接受的帧，`frame.time_s` 为最后一帧时刻，`frame.diagnostics` 给出停止原因。schema 不合法、帧数超限等请求在创建前返回 422。POST /solve 则将编译/求解错误直接返回 422/detail Diagnostic。被取消的后台运行同样保留记录:status=cancelled,frame.status=cancelled、valid=false,history 保留取消前已算出的帧。


## 运行生命周期与控制

`RunStatus.status`：queued、running、paused、completed、failed、cancelled、interrupted（`stopping` 保留在枚举中，当前不会出现）。

- 同步 `POST /runs` 在响应返回前已结束，status 只会是 completed 或 failed。
- 后台运行先写 queued；算完 t=0 后转 running（`start_paused` 时为 paused）；推进到 duration 转 completed；编译或求解失败写 failed，frame.valid=false，失败前已发布的帧保留在 history。
- cancelled 只能通过 `stop` 到达；服务关闭时未结束的运行记为 interrupted。
- 运行中 `GET /runs/{id}` 的 frame 是最新发布帧；`lag_s` 是实时运行落后墙钟的秒数（快速运行为 0）。

`POST /api/v1/runs/{run_id}/command` 请求体为 `RunCommand`：`action`，可选 `command_id`、`instance_id`、`parameter_id`、`value`、`controller_id`。响应是当前 `RunStatus` 加回执字段 `command_id`、`command_status`（首次为 `accepted`）、`applied_time_s`、`message`。命令在下一帧开始前执行，结果写入事件：`command_status` 变为 `applied`（带生效时刻）或 `rejected`（带原因）。客户端应轮询 `/events` 确认，而不是假设已生效。

| action | 行为 |
| --- | --- |
| pause | 当前帧算完后停在 paused，不占计算线程，不过期。 |
| resume | 回到 running；实时运行从当前墙钟重新计时。 |
| step | 只能在 paused 时执行：推进一帧后回到 paused。会话不重新 initialize，Python 状态连续。 |
| set | 改 `instance_id.parameter_id` 为 `value`（规范单位）。参数必须声明 `runtime=true`（内置：阀门开度、泵转速比、水箱加热功率），按目录范围校验；被自动模式 PID 绑定的参数拒绝。从下一子步生效，请求快照里的项目不变。 |
| controller | 改 PID `controller_id` 的 `parameter_id`（只允许 `setpoint`、`mode`、`manual_output`），立即在下一子步采样。 |
| stop | 当前帧算完后结束为 cancelled，history 保留已算帧，Worker 回收。 |

错误：未知 run_id 404；已结束（含同步运行）409 `RUN_ALREADY_FINISHED`；同一 `command_id` 内容不同 409 `COMMAND_ID_CONFLICT`，内容相同返回原回执。运行时才能判断的错误（非 paused 时 step、参数不可写或越界、参数被 PID 控制、控制器不存在）不返回 HTTP 错误，而是该命令事件为 rejected。

前端把后台 `run_id` 记在 `owner.run.runId`，用增量 `history?offset=` 轮询新帧；命令带随机 `command_id` 并等待 applied/rejected 事件（最长约 10 秒），超时提示“命令已接收，尚未确认生效”，不自动重发。

## 原型归一化

需要 format=`fluidnet-studio-prototype`、modules、projects 和可选 activeProject。只处理活动项目使用的模块；库中未使用的 PID、物性等原型模块不会阻塞水力项目。

支持内置模型及其复制模块（kind 指向已注册模型），以及 runtime=python 的完整清单/前端 manifest 快照，保留实例原有 ID。Python 参数使用清单 ID，显示单位通过 UnitSpec 转换，不能丢弃 entrypoint/source/content_hash。端口/通路 ID 必须与注册模型相容，读取真实端口领域、通路端点和 enabled 状态。编辑为非流体端口或禁用必要通路会在检查/求解时报错。

原型项目的 `moduleSnapshots` 以模块 ID 保存已绑定定义，归一化时优先于全局模块库和编辑草稿。实例 `package` 进入规范合同；已有版本快照不随目录更新。原型格式仍由浏览器导出保存，模块发布不替代项目文件持久化。

归一化只投影计算输入和参数库值，完整原型继续通过原始导出保存。归一化本身不执行 Python/控制脚本；项目求解随后通过 Worker 执行 Python 模块包，不把自定义变量的文本当算法，也不将备用草稿自动生效。

## 独立验证台契约

`ModuleTestRequest` 接收完整 Python `module`、规范单位 `parameters`、入口/出口绝对压力、温度、`duration_s` 和 `dt_s`。测试夹具为每条启用通路各建一组入口/出口压力边界；未覆盖的通路使用通用压力和温度，`channel_boundaries` 可独立指定各通路的压力、温度与工质。存在某通路覆盖时，该通路使用 `ChannelTestBoundary` 的显式值或默认值。多通路模块在同一个网络中求解。

后端使用相同编译器和求解器建立测试网络。先采样 t=0，不提交状态；随后每个收敛时间步提交一次，最后不足整步时使用实际 dt。`ctx.channel(id)` 因此获得真实质量流量与压降。

响应包含初始 `state`、最终 `evaluation`、最终 `committed`、最后 `frame` 和全部 `history`。变量使用 `D1.*` 路径，状态使用 `D1.state.*`。失败返回 422/detail Diagnostic；没有伪造的收敛残差。

Worker RPC 超时默认 10 秒，超时返回 `MODULE_RUNTIME_TIMEOUT` 并终止进程；源码异常或缺失通路返回 `MODULE_RUNTIME_ERROR`。所有完成/失败路径都回收 Worker。通信显式使用 UTF-8，模块 print 不进入 JSON 通道。

`POST /api/v1/modules/test-suite` 接收 `module` 和 1–64 项 `cases`。每项包含唯一 `id`、`conditions` 和可选 `assertions`，例如：

```json
{
  "id": "forward",
  "conditions": {"inlet_pressure_pa": 250000, "outlet_pressure_pa": 120000},
  "assertions": [
    {"key": "D1.in0.pressure_pa", "expected": 250000, "absolute_tolerance": 0.01, "relative_tolerance": 0}
  ]
}
```

断言使用最终帧和规范单位，要求 `abs(actual-expected) <= max(absolute_tolerance, relative_tolerance*abs(expected))`。预期值必须是有限数值，容差必须有限且非负，同一工况不可重复声明变量键。每项最多 256 条断言。响应回显预期值与容差，并包含 `actual`、`absolute_error`、`allowed_error`、`passed`、`status`、`message`；变量缺失、非数值和求解失败均明确报告。数值误差超过浮点表示范围时返回 `null` 并给出说明，比较本身保留精确判定。

全部结果帧有效且全部断言通过才判工况通过，所有工况通过才判组合通过。任一工况失败仍执行后续工况；未设置断言时兼容旧行为及输入哈希，有断言时 `input_hash` 同时绑定边界、参数和断言。请求字段不合法返回 422；非有限 JSON 输入的错误详情以可序列化文本表示，不会转成服务器 500。

## 变量接口（v0.4.6）

面向三维界面、数字孪生、网关等外部程序，按帧变量键读写一个正在运行的后台会话，键名与 RunFrame.variables 相同。

- 读：`GET /runs/{id}/variables?keys=T1.state.level_m,V1.mass_flow_kg_s` 只返回最新发布帧的这些值，不复制整条记录。运行指定了 `selected_variables` 时只能读这些变量。同步运行也可读（读其最终帧）。
- 写：`POST /runs/{id}/variables`，请求体 `{"values": {"V1.param.opening_ratio": 0.6, "controller.level.setpoint": 1.2}, "command_id": "可选", "wait_s": 2}`。
  - 可写的键：`<设备>.param.<运行参数>`（`runtime=true` 的参数，同 `set`），`controller.<id>.setpoint|mode|manual_output`。
  - 所有值在同一个帧边界一起生效，`parameter_revision` 只加 1；任何一项不合法（不可写、越界、被 PID 绑定、键格式不对）整批拒绝，什么都不改。
  - 被 PID 绑定的参数一律拒绝直接写入，手动模式也一样（手动时 PID 每个子步写 manual_output，外部写入会被覆盖）；请改控制器字段。
  - `wait_s` > 0 时等到命令 applied 或 rejected 再返回（最多 10 秒），否则立即返回 `accepted` 回执，与 `/command` 相同；暂停的会话也会处理写入。底层是新的 RunCommand `action="write"`、`values`。
- 推送：`WS /runs/{id}/stream?keys=…` 在每个新发布的帧推送一条 `{"type":"frame","status","time_s","sequence","parameter_revision","values"}`。客户端慢时跳过中间帧而不排队，`sequence` 体现跳过的帧；运行结束发 `{"type":"end","status":…}` 并关闭。未知运行关闭码 4404，未知变量 4422，令牌无效 4401。只有后台运行可以订阅。

## 无界面服务与已保存项目运行

`python -m fn_engine serve --headless --data-dir .runtime/workspace` 启动无界面服务，`health.mode` 为 `headless`，前端 `/`、`/studio.js` 返回 404；REST、WebSocket、`/docs`、`/openapi.json`、令牌、跨域和工作区行为保持一致。普通 `serve` 的模式为 `studio`；`--headless` 与 `--open` 互斥。嵌入调用 `create_app(data_root=...)` 不传前端目录时也是无界面模式。

第三方可先用 `GET /api/v1/projects` 查询已保存项目，再调用 `POST /api/v1/projects/{project_id}/runs`。示例请求：

```json
{
  "revision": 2,
  "scenario_id": "throttle",
  "mode": "dynamic",
  "duration_s": null,
  "dt_s": 0.1,
  "start_paused": true,
  "execution_mode": "realtime"
}
```

`revision` 省略或为 null 时读取提交瞬间的最新保存修订；`scenario_id` 可省略。其余字段与 `RunRequest` 共用 `RunOptions`，默认 `mode=steady`，需要连续运行时显式传 `mode=dynamic,duration_s=null`。请求始终走后台运行，成功受理为 HTTP 202；随后通过现有 `/runs/{id}`、`/command`、`/variables` 和 `/stream` 接口查询和控制。

服务端读取单项目文档并完成显示单位归一化，固定该修订的模块和控制脚本快照，使用已应用参数。编辑器的 `draft` 值不进入计算。运行记录中的 `request.project_revision` 来自实际读取的修订，客户端不能传入 `project` 或 `project_revision` 替换它；并发保存不会改变已捕获的运行快照。编译或求解失败（包括未知工况）沿用后台任务语义：请求可受理为 202，随后记录变为 `failed`，原因见 `frame.diagnostics`。

该 POST 在认证启用时需要 control 令牌；只读令牌返回 403。未启用工作区返回 503，项目或修订缺失返回 404，无法归一化的保存文档返回 422 且不创建运行。停止并正常关闭服务后，重启可查询该运行的归档和项目修订；原仿真跨重启续算仍未实现。

可直接运行的 [Python 和 JavaScript 客户端](../examples/external_clients/README.md) 包含令牌设置、按修订启动、订阅变量、写变量、暂停/继续和停止流程。变量仍使用完整规范键，值为规范单位。

## 访问控制（v0.4.6）

服务以 `--auth required`，或 `--auth auto` 监听本机以外地址启动时，除 `GET /api/v1/health` 外所有 `/api/` 请求都要 `Authorization: Bearer <令牌>`：没有或无效返回 401 `AUTH_REQUIRED`，只读令牌发 POST 返回 403 `AUTH_SCOPE`。只读令牌可调用 GET 接口和订阅推送；控制令牌还可以调用全部 POST（校验、求解、运行、命令、写变量、模块保存）。WebSocket 可在请求头带令牌，或用子协议 `fluidnet.bearer.<令牌>`（服务端回应同一子协议）。静态前端页面、`/docs` 和 `/openapi.json` 不受令牌限制，它们不含运行数据。`/api/v1/health` 返回 `auth.required`，供前端决定是否要求输入令牌。跨域来源由 `--cors-origin` 显式列出，默认不允许跨域。

## 尚未实现

串口桥接与外部变量别名映射（「对接」页的串口、变量绑定仍是演示）；HTTPS（请用反向代理）；原仿真跨重启续算；窗口外完整逐帧归档；声明式参数计划（现有变量接口支持整批写入，Python 控制脚本可按采样时间写入）。

## Python 控制与持久工作区

`Project.control_scripts` 为 `ControlScript[]`，原型归一化从 `controlScripts` 读取。脚本包含 id、language=`python`、source、enabled（默认 false）、sample_s（0.001–60，默认 0.1）、inputs/outputs（各最多 256）、timeout_s（0.1–30，默认 5）和源码 SHA-256 `content_hash`。哈希由服务端生成；携带不匹配哈希会返回 422。最多 16 个脚本，只有启用的脚本参与校验/执行。启用脚本要求动态运行，稳态返回 `CONTROL_DYNAMIC_REQUIRED`。

浏览器工作区使用 `controlPrograms` 保留各脚本编辑信息，选择项为 `selectedControlId`；原有 `control*` 字段保留所选脚本的编辑投影。运行和归一化导出全部 Python 脚本到 `controlScripts`，旧语言文本及禁用的空源码草稿只随工作区保存。首次打开旧单脚本或已有多脚本项目会迁入列表；模块升级按 ID 更新运行合同，保留未参与运行投影的草稿。切换所选脚本不改变计算输入，修改源码后清除旧哈希并由后端重新计算。

`POST /controls/preview` 将目标脚本放入独立临时会话，在 t=0 完成 initialize 和一次 step，校验并返回拟写入值；不修改原型项目，不产生运行档案。生命周期均为同步 Python 函数，`step(ctx,dt_s)` 第一次 dt_s=0，之后为实际仿真采样间隔。ctx.time_s、ctx.read、ctx.write、ctx.state、ctx.log 可用；state 必须为有限值 JSON 字典且不超过 64 KiB。读写只能使用声明键，写入先整批校验，再交给运行参数/PID 接口；PID 目标和不同脚本的直接写目标不能重叠。运行帧增加 `script.<id>.samples/last_time_s/content_hash/state.<标量键>`。

`serve` 启用本地持久化（`--data-dir` / `FLUIDNET_DATA_DIR`），`create_app` 嵌入调用则通过 `data_root` 显式启用。health.capabilities 中 `python_controls` 为 true，`persistent_workspace` 表示本实例是否启用存储。未启用时 workspace 接口返回 503。保存的 data 是 schema=1 的完整原型工作区，含 projects/modules/models 和 activeProject，最大 64 MiB；不等同于规范计算 Project。expected_revision=0 表示首次保存；修订冲突不会覆盖现有数据。

归档 RunRecordResponse 增加 `persisted_at`（最近成功落盘时间）与 `persisted_rows`（累计落盘帧数）。每帧元数据、窗口行与必要的 overview 在一个 SQLite 事务中写入；最后 20 次终态运行保留在磁盘。`history_window` 默认 2001、最大 20001；更早逐帧历史被淘汰，全程保留抽稀曲线。history=full 仅控制窗口帧内容，不保证无限保留全帧。重启恢复将未结束运行变为 interrupted，并拒绝尚无生效确认的命令。已结束档案可读变量/历史/overview，不能 resume。

完整备份使用 SQLite online backup API，并在复制模块包时持有模块发布锁。恢复在临时目录内校验清单、文件大小与哈希、数据库完整性/版本/引用/修订号及模块双哈希，全部通过后发布为独立目录；不会覆盖现有目录。备份格式 v1、当前数据库版本 3，恢复接受版本 1、2、3；旧版本首次打开时迁移到版本 3，保留项目／运行并建立批次表。最多 10000 个 ZIP 条目、2 GiB 解压体积。未启用持久化时返回 503；认证规则与其他接口一致，两个 POST 需要 control 权限。CLI 与目录优先级见 [备份说明](WORKSPACE_BACKUP.md)。

## 单项目修订与模块升级

以下路径均以 `/api/v1` 为前缀。单项目存储接口需要先保存初始工作区。

| 接口 | 请求 | 返回模型与结果 | 错误响应（`detail.code`） |
| --- | --- | --- | --- |
| GET /projects | 无 | `ProjectListResponse`：已保存项目的 ID、名称、修订、保存时间和实例数 | 503、507；401/403 |
| GET /projects/{project_id}?revision=N | 可选 revision | `ProjectDetailResponse`：当前或指定项目修订，返回 revision、saved_at 和 document | 404（不存在或已删除）、503、507；401/403 |
| GET /projects/{project_id}/revisions | 无 | `ProjectRevisionsResponse`：最近 5 个项目修订，含 deleted 标记 | 503、507；401/403 |
| POST /projects/{project_id} | ProjectSaveRequest：expected_revision 和 document | `ProjectSaveResponse`：项目 revision、saved_at、workspace_revision 和 previous_workspace_revision | 409 `PROJECT_CONFLICT`/`WORKSPACE_CONFLICT`、422、503、507；401/403 |
| POST /projects/{project_id}/restore | ProjectRevisionRequest：expected_revision 和目标 revision | `ProjectRestoreResponse`：恢复生成新修订，并返回恢复的 document | 404（修订不存在）、409 `PROJECT_CONFLICT`、503、507；401/403 |
| POST /projects/{project_id}/delete | ProjectDeleteRequest：expected_revision | `ProjectDeleteResponse`：保留其他项目和运行档案；删除最后一个项目返回 422 | 409 `PROJECT_CONFLICT`/`WORKSPACE_CONFLICT`、422、503、507；401/403 |
| POST /project-upgrades/preview | ProjectUpgradeRequest：规范 project、module_id、target_version | `ProjectUpgradeResponse`：前后双哈希、源码、定义差异、兼容性及原因，兼容时另含升级后的 project | 404（模块版本不存在）、409（项目有活动运行）、422、500；401/403 |

`document` 是格式为 `fluidnet-project`、schema=1 的单项目交换文档，含原型 project、固定模块快照 modules、关联 models 和 charts。路径中的 `project_id` 必须与文档一致。expected_revision 使用各项目独立修订号，冲突返回 409 `PROJECT_CONFLICT`，成功保存会在同一事务中更新项目历史和完整工作区。项目保存、恢复、删除和模块升级预览在项目有活动运行时返回 409。

升级预览不写入项目。前端应用时先保存原修订，再保存升级文档；已归档运行继续使用原快照。`RunRequest.project_revision` 为可选正整数元数据，前端仅在当前模型与已保存状态一致时填写。原型工况 overrides 经归一化转换为规范参数和单位，所选工况通过 `scenario_id` 提交。

## 风侧合同 1

客户端检查 `health.capabilities.moist_air_contract_version == 1`。细分能力为 `wet_cooling_coil`、`air_humidifier`、`ahu_components`、`air_room`、`cooling_tower_moist`、`air_variable_catalog`、`air_reports`；真实水盘管、水冷冷水机组与风水联算分别由 `water_coil`、`water_chiller`、`air_liquid_coupling` 标记。这些能力不替代模块自己的 SDK 协商。

| 方法与路径（/api/v1） | 用途 |
| --- | --- |
| POST `/air/properties` | `input_mode=ptw/ptrh/phw`，查询完整湿空气状态与实际物性版本 |
| GET `/air/psychrometric-grid` | 压力、温度范围与含湿量上限下的 10 条 RH 背景线，每条最多 161 点 |
| POST `/air/variables/preview` | 完整 Project → 中文变量目录、单位、质量基准、可写性；不启动 Worker |
| GET `/runs/{run_id}/air-variables` | 创建运行时冻结的变量目录 |
| POST `/air/migrations/preview` | `{project, upgrade_official_modules}` → 原项目、候选项目、变化和诊断；不写工作区 |

新增查询 POST 仍要求 control 权限，GET/WS 使用 read 权限。物性/项目语义错误为 422；旧运行无风侧元数据时目录返回 409 `AIR_METADATA_UNAVAILABLE`。旧湿空气项目需先迁移，不能静默改变既有焓/质量语义。

`RunRecordResponse.air_metadata` 保存合同/引擎/物性版本、项目摘要、冻结目录与模型假设。旧档案该字段为 null。既有 `report.csv`/`report.html` 路径按该元数据生成风侧报告，不重新编译或求解项目。

`chiller-air-loop` 通过 `circuit_fluids` 指定独立冷冻水与冷却水回路，默认 Air/gas。混合项目的元数据 `continuity_basis`/`enthalpy_basis` 为 `mixed`：空气按干空气输运，液体按各自工质质量与比焓输运；变量目录只为空气端口声明含湿量和干空气流量。累计量与报告沿用原接受帧机制，详见[风水联算](CHILLER_AIR_LOOP.md)。

```json
{"input_mode":"ptrh","pressure_pa":101325,"temperature_k":299.15,"relative_humidity":0.5}
```

完整对象见 `contracts/air-*.schema.json`、`contracts/moist-air-options.schema.json` 及 OpenAPI。示例可通过 `/examples/{name}` 获取，见[示例目录](../examples/air-side/README.md)。操作与质量基准见[风侧使用说明](AIR_SIDE_USER_GUIDE.md)。
