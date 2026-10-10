# HTTP API

默认服务：127.0.0.1:8798。`/docs` 为交互文档，`/openapi.json` 为运行时定义，`contracts/openapi.json` 为生成的合同快照。

## 已实现端点

| 方法与路径 | 请求 | 返回 |
| --- | --- | --- |
| GET /api/v1/health | 无 | 版本、能力标志、2001 帧上限、20 次记录保留数 |
| GET /api/v1/catalog | 无 | 模块参数/通路/变量目录、原型参数名映射 |
| GET /api/v1/modules | 无 | 可安装模块包和内置模块清单、版本与内容哈希 |
| POST /api/v1/modules/validate | ModuleDefinition | 模块清单、入口和源码哈希诊断 |
| POST /api/v1/modules/test | ModuleTestRequest | 在独立 Worker 中执行一次 initialize/evaluate/commit_step |
| POST /api/v1/prototype/normalize | 原型导出对象 | 规范 Project；显示单位转换；不能归一化时 422 |
| POST /api/v1/projects/validate | Project | valid 和 diagnostics；检查失败时 valid=false |
| POST /api/v1/solve | Project | 同步稳态 RunFrame；计算失败时 422 |
| POST /api/v1/runs | RunRequest | **201**；run_id、status、frame、total_rows |
| GET /api/v1/runs/{run_id} | 无 | 状态、请求快照和最后一帧，不重复携带整段历史 |
| GET /api/v1/runs/{run_id}/history | offset≥0, 1≤limit≤2001 | rows、total_rows、offset |
| GET /api/v1/runs/{run_id}/events | 无 | queued/running/completed/failed 事件 |

`POST /api/v1/runs?background=true` 创建后台运行，返回 HTTP 202 和 `run_id`。默认仍保持兼容的同步模式：稳态和现有前端动态回放请求直接在请求期间完成并返回 HTTP 201。后台模式当前用于验证运行编排和查询协议，暂停、取消和参数命令仍未开放。

## 模块包和 Worker

模块包目录至少包含：

```text
manifest.json
module.py
```

`manifest.json` 由 `ModuleDefinition` 校验；`module.py` 的 SHA-256 保存为 `content_hash`。Python 模块入口必须实现 `initialize/evaluate/commit_step/finalize` 生命周期中的 `evaluate`，其他阶段可以为空实现。

Worker 消息使用 Pydantic 的 `InitializeRequest`、`EvaluateRequest`、`EvaluateResponse`、`CommitStepRequest` 和 `CommitStepResponse`。`evaluate` 输出 `NetworkRelation`，由网络求解器决定最终压力和流量；模块不能直接返回全网解。

运行接口现在是同步计算。返回 201 时，计算已经 completed 或 failed；没有后台排队、流式推送或命令端点。进程内保留最近 20 次运行，超出或重启后查询返回 404。项目编辑和永久导出目前由前端浏览器管理，不是服务端数据库。

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
    "V1.mass_flow_kg_s": 3.582426729656114,
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

支持内置模型及其复制模块（kind 指向已注册模型），保留实例原有 ID。端口/通路 ID 必须与注册模型相容，读取真实端口领域、通路端点和 enabled 状态。编辑为非流体端口或禁用必要通路会在检查/求解时报错。

归一化只投影计算输入和参数库值，完整原型继续通过原始导出保存。它不会执行 Python/控制脚本，不把自定义变量的文本当算法，也不将备用草稿自动生效。

## 后续端点（当前不可调用）

拟增加 `POST /runs/{id}/commands`（pause/resume/step/stop/set）及 `WS /runs/{id}/stream`。异步任务、命令生效时刻、revision 冲突处理和取消语义需要一并实现。现在点击前端暂停/停止仅操作结果回放，不能用这些预留路径调用后端。
