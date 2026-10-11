# HTTP API

默认服务：127.0.0.1:8798。`/docs` 为交互文档，`/openapi.json` 为运行时定义，`contracts/openapi.json` 为生成的合同快照。

## 已实现端点

| 方法与路径 | 请求 | 返回 |
| --- | --- | --- |
| GET /api/v1/health | 无 | 版本、能力标志、2001 帧上限、20 次记录保留数 |
| GET /api/v1/catalog | 无 | 模块参数/通路/变量目录、原型参数名映射 |
| GET /api/v1/modules | 无 | 可安装模块包和内置模块清单、版本与内容哈希 |
| POST /api/v1/modules/validate | ModuleDefinition | 契约、Python 语法、Worker 入口与四阶段签名诊断 |
| POST /api/v1/modules/test | ModuleTestRequest | 独立边界求解，返回 evaluation、committed、frame、history |
| POST /api/v1/modules/versions | ModuleSaveRequest | **201** ModuleVersionResponse，校验试算通过后保存新版本 |
| GET /api/v1/modules/{module_id}/versions | 无 | 倒序版本记录，未知模块返回空列表 |
| GET /api/v1/modules/{module_id}/versions/{version} | 整数版本 | 完整模块、引用和试算凭据；未知版本 404 |
| POST /api/v1/prototype/normalize | 原型导出对象 | 规范 Project；显示单位转换；不能归一化时 422 |
| POST /api/v1/projects/validate | Project | valid 和 diagnostics；检查失败时 valid=false |
| POST /api/v1/solve | Project | 同步稳态 RunFrame；计算失败时 422 |
| POST /api/v1/runs | RunRequest | **201**；run_id、status、frame、total_rows |
| GET /api/v1/runs/{run_id} | 无 | 状态、请求快照和最后一帧，不重复携带整段历史 |
| GET /api/v1/runs/{run_id}/history | offset≥0, 1≤limit≤2001 | rows、total_rows、offset |
| GET /api/v1/runs/{run_id}/events | 无 | queued/running/completed/failed 事件 |

`POST /api/v1/runs?background=true` 创建后台运行，返回 HTTP 202 和 `run_id`。默认仍保持兼容的同步模式，返回 HTTP 201。前端稳态使用同步请求，动态与单步使用后台请求并轮询状态。暂停、取消和参数命令仍未开放；前端暂停/停止只控制取回与回放。

## 模块包和 Worker

模块包目录至少包含：

```text
manifest.json
module.py
```

`manifest.json` 由 `ModuleDefinition` 校验；`module.py` 的 SHA-256 保存为 `content_hash`。版本保存要求同步实现 `initialize(ctx)`、`evaluate(ctx)`、`commit_step(ctx, dt_s)`、`finalize(ctx)`，无逻辑的阶段可以使用 `pass`。入口加载和生命周期签名检查均在独立 Worker 中进行。兼容的直接运行接口仍容许省略可选阶段。

## 模块版本写入契约

`ModuleSaveRequest` 包含完整 `module`、`expected_latest_version`、`release_notes` 和可选 `test: ModuleTestConditions`。新 ID 的预期版本为 0，示例模块初始为 1。服务端分配当前版本加一，忽略草稿中的目标版本/哈希/文件路径，不接受覆盖旧版本。内置模型 ID 不可被 Python 模块占用。

`test` 与独立验证台共用参数、工质、边界、时长和步长模型。浏览器保存时使用契约默认参数，以及最近验证台的边界（如选中同一模块），重新执行试算。API 可显式提供测试参数覆盖。试算为每条启用通路各接一组独立压力边界并在一个网络中求解；共用端口、端口未绑定通路或非流体端口返回 422，不会绕过验证写入。

保存依次检查 Pydantic 默认值与引用、Python 语法和入口签名、initialize/evaluate/commit_step/finalize、最终声明输出。成功后将三份文件写入临时目录，原子重命名为版本目录。并发请求使用相同预期版本时只有一个成功；失败请求不留下可发现的半成品版本。

`ModuleVersionResponse` 包含 `module`、`package`（版本、源码哈希、完整定义哈希）、`created_at`、`release_notes`、`tested`、`test_conditions` 和 `test_result`。内置示例没有保存试算凭据，`tested=false`。GET 模块目录只返回每个 ID 的最新版本；历史版本由版本接口读取。

错误：Pydantic 字段错误返回 422/detail 数组；语法、加载、算法或声明输出缺失返回 422/detail `{code: MODULE_SAVE_INVALID, message, diagnostics}`；预期版本过期或同版本并发写入返回 409 `MODULE_VERSION_CONFLICT`；磁盘写入失败返回 500 `MODULE_STORAGE_ERROR`。前端始终保留未成功保存的编辑草稿。

`content_hash` 校验源代码；`definition_hash` 校验整个规范定义（排除两个哈希字段和机器路径，包含版本、参数、端口、输出和代码）。数字整数形式统一，避免浏览器把 `16.0` 序列化成 `16` 导致误报。项目中的 `ModuleInstance.package` 必须与定义快照一致；编译器另行计算哈希，不信任客户端声明。

Worker 消息使用 Pydantic 的 `InitializeRequest`、`EvaluateRequest`、`EvaluateResponse`、`CommitStepRequest` 和 `CommitStepResponse`。`evaluate` 输出 `NetworkRelation`，由网络求解器决定最终压力和流量；模块不能直接返回全网解。

同步请求返回 201 时，计算已经 completed 或 failed；后台请求返回 202 后通过状态接口查询。没有流式推送或命令端点。进程内保留最近 20 次运行，超出或重启后查询返回 404。项目编辑和永久导出目前由前端浏览器管理，不是服务端数据库。

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

## RunRequest

```json
{
  "project": "此处填写完整 Project 对象，不是项目 ID",
  "mode": "dynamic",
  "duration_s": 30,
  "dt_s": 0.1,
  "scenario_id": null,
  "selected_variables": ["P1.mass_flow_kg_s", "V1.mass_flow_kg_s", "V2.mass_flow_kg_s"]
}
```

上例 project 字段是说明占位，实际必须发送对象。mode 可为 steady 或 dynamic。dynamic 当前明确表示准稳态序列。selected_variables 为空数组表示全部；null/省略则使用 project.selected_variables，后者也为空则返回全部。未知变量使本次运行失败，不能静默丢弃。

scenario_id 指向 Project.scenarios。覆盖只修改本次运行的项目副本，参数仍按相同规则校验。未实现随时间变化的参数计划。

## RunFrame

```json
{
  "status": "converged",
  "valid": true,
  "time_s": 0,
  "variables": {
    "V1.mass_flow_kg_s": 3.5826766415095452,
    "V1.out0.temperature_k": null
  },
  "diagnostics": [],
  "metrics": {
    "pressure_residual_pa": 5.82e-11,
    "mass_residual_kg_s": 4.44e-16,
    "iterations": 7,
    "node_count": 5,
    "branch_count": 5
  }
}
```

该示例省略了其他变量和归一化提示。valid 表示当前声明的水力方程已通过验收，不表示热力或状态算法已执行。

Diagnostic 包含 code、message、severity（info/warning/error）、可选 instance_id 与 field。前端可以定位到实例。结构错误采用 PORT_UNCONNECTED、BOUNDARY_CONFLICT、PRESSURE_REFERENCE_MISSING、MODEL_NOT_SUPPORTED 等代码。

POST /runs 对类型正确但编译或求解失败的请求仍创建可查询的记录，status=failed、frame.valid=false、history 为空。schema 不合法、帧数超限等请求在创建前返回 422。POST /solve 则将编译/求解错误直接返回 422/detail Diagnostic。

## 原型归一化

需要 format=`fluidnet-studio-prototype`、modules、projects 和可选 activeProject。只处理活动项目使用的模块；库中未使用的 PID、物性等原型模块不会阻塞水力项目。

支持内置模型及其复制模块（kind 指向已注册模型），以及 runtime=python 的完整清单/前端 manifest 快照，保留实例原有 ID。Python 参数使用清单 ID，显示单位通过 UnitSpec 转换，不能丢弃 entrypoint/source/content_hash。端口/通路 ID 必须与注册模型相容，读取真实端口领域、通路端点和 enabled 状态。编辑为非流体端口或禁用必要通路会在检查/求解时报错。

原型项目的 `moduleSnapshots` 以模块 ID 保存已绑定定义，归一化时优先于全局模块库和编辑草稿。实例 `package` 进入规范合同；已有版本快照不随目录更新。原型格式仍由浏览器导出保存，模块发布不替代项目文件持久化。

归一化只投影计算输入和参数库值，完整原型继续通过原始导出保存。归一化本身不执行 Python/控制脚本；项目求解随后通过 Worker 执行 Python 模块包，不把自定义变量的文本当算法，也不将备用草稿自动生效。

## 独立验证台契约

`ModuleTestRequest` 接收完整 Python `module`、规范单位 `parameters`、入口/出口绝对压力、温度、`duration_s` 和 `dt_s`。测试夹具为每条启用通路各建一组入口/出口压力边界，所有入口共用 `inlet_pressure_pa`、所有出口共用 `outlet_pressure_pa`；多通路模块因此一次求解全部通路。

后端使用相同编译器和求解器建立测试网络。先采样 t=0，不提交状态；随后每个收敛时间步提交一次，最后不足整步时使用实际 dt。`ctx.channel(id)` 因此获得真实质量流量与压降。

响应包含初始 `state`、最终 `evaluation`、最终 `committed`、最后 `frame` 和全部 `history`。变量使用 `D1.*` 路径，状态使用 `D1.state.*`。失败返回 422/detail Diagnostic；没有伪造的收敛残差。

Worker RPC 超时默认 10 秒，超时返回 `MODULE_RUNTIME_TIMEOUT` 并终止进程；源码异常或缺失通路返回 `MODULE_RUNTIME_ERROR`。所有完成/失败路径都回收 Worker。通信显式使用 UTF-8，模块 print 不进入 JSON 通道。

## 后续端点（当前不可调用）

拟增加 `POST /runs/{id}/commands`（pause/resume/step/stop/set）及 `WS /runs/{id}/stream`。异步任务、命令生效时刻、revision 冲突处理和取消语义需要一并实现。现在点击前端暂停/停止仅操作结果回放，不能用这些预留路径调用后端。
