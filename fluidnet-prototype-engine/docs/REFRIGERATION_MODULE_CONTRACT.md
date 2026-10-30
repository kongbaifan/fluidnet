# RF-1：制冷作者模块合同、SDK 与 Worker

日期：2026-10-30。状态：**RF-1 已实现并完成定向验证**。承接 [RF-0 设计与实验](REFRIGERATION_EXTENSION_DESIGN.md)，正式建立 schema 4、SDK 0.7.0、角色编译与类型化 Worker 协议。

**后续更新**：RF-2/RF-3 已接通正常运行、制冷验证台与发布，当前使用方式见[运行与作者验证说明](REFRIGERATION_MODULE_EXECUTION.md)。下文保留 RF-1 阶段的接口设计和历史验收边界。

本阶段可校验制冷模块合同和站内拓扑，并在独立 Worker 中执行作者求值及现有状态生命周期。整站动态接受适配属于 RF-2，独立制冷验证台和发布属于 RF-3；这些入口仍明确拒绝，不会用内置阀替代作者代码生成结果。

## 1. 合同与兼容性

新增 [module-v4.schema.json](../contracts/module-v4.schema.json)。旧 schema 1/2/3 解析器及其合同文件保持不变；旧版本不会得到 `execution_role` 等新默认字段，既有导出与定义哈希保持原值。schema 4 的角色和适用范围参与同一套版本及双哈希机制。

首个角色声明：

```json
{
  "schema_version": 4,
  "runtime": "python",
  "source_format": "python-v1",
  "solver_model": "generic",
  "execution_role": "refrigeration.isenthalpic_throttle.v1",
  "sdk": {
    "api_version": "0.7.0",
    "capabilities": [
      "context.execution.v1",
      "refrigeration.throttle.v1",
      "state.transactions.v1"
    ]
  },
  "applicability": {"execution_domains": ["refrigeration"]}
}
```

完整样例见 [清单](../examples/refrigeration_extensions/sdk_throttle.manifest.json)和[作者源码](../examples/refrigeration_extensions/sdk_throttle.py)。它们没有加入正式模块目录，源码只引用公共 `fn_sdk` 与标准库。

| 项目 | 合同要求 |
| --- | --- |
| 端口 | `in0` 为必连制冷剂入口，`out0` 为必连制冷剂出口；均属于 `refrigerant` 回路。上游仍须从饱和容器液相取液 |
| 模型职责 | 无水力通路、独立物理储量、热模型或组合；不能通过设置内置 `solver_model` 冒充角色 |
| `kv_m3_h` | 数值；数量类型 `flow_coefficient`、规范单位 `m³/h`，声明正下限；在运行中固定 |
| `opening_ratio` | 数值；数量类型 `ratio`、规范单位 `1`，范围包含于 0–1，必须可在运行中写入；可用 `%` 显示 |
| 其他参数 | 可声明作者自己的数值、布尔、文本或曲线参数；继续使用已有参数类型、默认值和范围检查 |
| 能力 | 必需上述三项能力；可追加生命周期、JSON 状态、物性及日志基础能力；不允许同时声明流体通路、湿空气、热流、组合或导数能力 |
| 工质 | 初始化采用同一回路 `FluidConfig`，`phase_policy=any`；可用 `applicability.fluids` 限制工质；不能把两端指定为不同工质 |

运行中的参数消息保留未修改的实例值，只允许更改声明为 `runtime && writable` 的参数。额定 Kv 等固定参数的变化需要重新建立运行，不会在局部开度更新时被重置为模块默认值。

## 2. 公共 SDK

`fn_sdk.SDK_API_VERSION` 为 `0.7.0`，仍只导入标准库。新增的公开协议类型为 `RefrigerationContext`、`RefrigerationThrottleInput`、`RefrigerationThrottleFlow`。

在已声明角色的制冷求值中：

```python
point = ctx.refrigeration.throttle
effective = point.rated_kv_m3_h * point.opening_ratio
mass = effective / 3600 * math.sqrt(
    1000 * point.inlet_density_kg_m3
    * max(point.inlet_pressure_pa - point.outlet_pressure_pa, 0) / 100000
)
ctx.refrigeration.flow(mass_flow_kg_s=mass, effective_kv_m3_h=effective)
```

`point` 为只读输入，字段为：

- `inlet_pressure_pa`、`outlet_pressure_pa`：绝压 Pa。
- `inlet_temperature_k`、`inlet_enthalpy_j_kg`、`inlet_density_kg_m3`：上游饱和液体状态，分别为 K、J/kg、kg/m³；比焓允许因参考零点而为负。
- `opening_ratio`、`rated_kv_m3_h`：须与当前实例参数一致，过期开度或 Kv 请求拒绝。

每次求值恰好提交一次流量。数值必须有限，不能用布尔或单位字符串代替数值；有效 Kv 不得超过额定值，流量必须满足单向、零开度关断及有效 Kv 关系。流量经独立响应字段返回，不能再用 `ctx.var('mass_flow_kg_s', ...)` 覆盖平台流股字段。普通派生观察量仍可使用 `ctx.var`。

`ctx.refrigeration` 仅在制冷求值阶段可用；普通流体调用或生命周期其他阶段访问时明确报错。四个同步生命周期方法仍为 `initialize/evaluate/commit_step/finalize`，不改变旧模块签名。状态只通过现有准备/提升/同步机制接受。

## 3. 编译与 Worker

编译器按角色解析作者模块，复用既有取相、压力等级、回路和连接检查，不按自定义模块 ID 分支。编译结果将角色模块保存到 `CompiledStation.refrigeration_modules`，供 RF-2 接入实际执行。模块源码在编译阶段不会执行。

新增消息合同：

- [RefrigerationThrottleInput](../contracts/refrigeration-throttle-input.schema.json)
- [RefrigerationThrottleFlow](../contracts/refrigeration-throttle-flow.schema.json)
- [RefrigerationEvaluateRequest](../contracts/refrigeration-evaluate-request.schema.json)
- [RefrigerationEvaluateResponse](../contracts/refrigeration-evaluate-response.schema.json)

宿主通过 `WorkerProcess.evaluate_refrigeration(request)` 调用 `evaluate_refrigeration` RPC。请求携带运行/实例身份、迭代编号、时间、状态修订、执行上下文和 `throttle` 输入；响应包含 `flow`、普通观察变量和诊断。普通 `evaluate` 与热力/观察/导数阶段不能绕过角色协议。

Worker 初始化在载入用户代码前核对包的模块标识、整数版本所对应的版本串、源码哈希和定义哈希。求值核对身份、状态修订、接受时刻及参数一致性，给作者状态副本。父进程再次按原始输入校验返回流量；Worker 不能通过改写自己的输入绕过物理关系检查。

原有超时、进程退出、受限结果大小、错误源码定位、`prepare_step/synchronize_state/discard_candidate/finalize` 路径继续复用。制冷错误重放额外保留类型化的 `refrigeration` 输入；超时仍终止子进程。

## 4. RF-1 交付时的入口状态（历史）

| 入口 | RF-1 行为 |
| --- | --- |
| `/modules/validate` | 校验 schema 4、能力、源码和同步生命周期；可返回通过 |
| `/projects/validate` | 可校验纯制冷站中的角色模块；附带 `REFRIGERATION_MODULE_EXECUTION_PENDING` 提示 |
| 正常项目运行 / `StationSession` | 在执行前返回上述未接入诊断，不启动作者算法、不返回替代计算值；正式接受适配在 RF-2 |
| 普通流体、湿空气、A 版冷库、热耦合 | 拒绝该角色；普通组合也不能展开非流体端口来绕过限制 |
| `/modules/test` 与版本发布 | 返回 `MODULE_REFRIGERATION_BENCH_UNAVAILABLE`；制冷边界验证台在 RF-3 |
| 独立 Worker 类型化调用 | 已可用，供 SDK 接入与验证；不等同于上述产品入口全部开放 |

纯集总制冷站仍没有独立稳态求解器，继续沿用 RF-0 登记的限制。

## 5. 验证与交接

新增 64 项制冷模块用例，涵盖新旧合同、哈希、OpenAPI 引用、角色/端口/单位、旧 SDK 和能力冲突、实例参数保留、非法运行域、真实 Worker 数值网格、输入冻结、错误输出、版本/身份/修订冲突、状态事务、重放、超时回收、生命周期以及 API 阶段限制。

- 首轮相关后端回归 **277 项通过**，覆盖 SDK、旧合同、Worker 启动、事务、制冷站、热耦合及 RF-0。
- 最后补齐运行参数更新规则后，**136 项收尾检查通过**，覆盖全部新接口用例、湿空气协议、组合、版本、迁移及合同物理检查。两轮数量不相加。
- `browser-module-workflow` 与 `browser-smoke` 通过，页面脚本错误为 0；四类旧模板仍能发布、运行、保存重载并执行作者预期值检查。
- ruff、后端 mypy、公共 SDK 严格类型检查及新作者样例类型检查通过；**90 个生成合同一致**。旧 `module-v1/v2/v3` 合同文件没有变更。

命令、日志与哈希见 [RF-1 验证索引](platform-extension/results/rf1-validation.json)。本轮没有重跑全量后端、完整浏览器链或覆盖率，也没有把 RF-0 的性能数字登记为新协议性能结果。

下一包 **RF-2** 将用此正式协议替换实验运输，将返回流股接入制冷站方程，并完成候选求值、观察、接受事务、自适应及控制事件边界后开放运行；RF-3、RF-4 再完成验证台、发布与项目版本/结果操作。
