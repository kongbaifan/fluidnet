# 模块合同 schema 与 SDK 协商

S2 增加模块合同 schema 2。工程版本、模块整数版本、合同 schema、SDK API 版本和状态合同版本各自独立；当前工程为 0.5.0，S3 后公共 Python SDK 为 0.3.0。旧合同不自动迁移。

## 1. 声明方式

新 Python 模块在原合同上明确增加：

```json
{
  "schema_version": 2,
  "runtime": "python",
  "sdk": {
    "api_version": "0.2.0",
    "capabilities": ["hydraulics.v1", "net.resistance", "state.json.v1"],
    "state_contract_version": 1
  }
}
```

以上是合同片段，完整模块仍需原有 ID、名称、端口、参数、通路、源码等。正式作者示例版本按 S4 发布；固定测试样例不是已发布模块。

| 字段 | 解释 / 校验 |
| --- | --- |
| `schema_version` | 省略继续按 1 解释。2 仅用于 Python 模块，必须明确 `runtime="python"` 及非空 `sdk` 对象；未知 schema 拒绝解析 |
| `sdk.api_version` | 必填，精确的三段版本字符串，不接受区间、预发布或带前导零的版本；运行时按支持列表检查 |
| `sdk.capabilities` | 所需能力，省略为 `[]`；小写点分名称，拒绝重复；按名称排序后保存和计算哈希 |
| `sdk.state_contract_version` | 省略为整数 1；必须为正整数，不接受布尔或浮点数；运行时检查支持列表 |

schema 1 拒绝任何显式 `sdk` 字段，包括 `null`；模型内部的兼容占位值不会写入 JSON、项目快照或包 manifest。SDK 声明不会被静默补到旧合同中。

## 2. 当前支持表

| API 版本 | 支持的能力名称 |
| --- | --- |
| `0.1.0` | `lifecycle.v1`、`state.json.v1`、`properties.v1`、`net.pipe`、`net.valve`、`net.pump`、`net.compressor` |
| `0.2.0` | 上述全部，加 `net.resistance`、`hydraulics.v1` |
| `0.3.0` | 0.2.0 全部，加 `context.execution.v1`（[时间、阶段与身份](EXECUTION_CONTEXT.md)） |

`lifecycle.v1` 是已有四个同步回调，`properties.v1` 是惰性物性服务接口；可查询属性不等于网络支持任意相态。`hydraulics.v1` 是 S1 的六个公共标量工具。状态合同仅支持 1：沿用已有 `ctx.state` 和 `commit_step`；不宣称已实现事务回滚、状态限值或跨重启续算。

版本按显式支持列表协商，不自动推断语义版本兼容范围。例如 `0.2.1`、`0.4.0` 或 `1.0.0` 即使格式有效，也会在执行前拒绝。能力按所声明 API 版本的表检查：声明 0.1.0 再要求 `net.resistance` 会被拒绝；0.1/0.2 不能声明 `context.execution.v1`。能力列表是模块的兼容要求，不是权限控制，也不检测或限制任意 Python 副作用。

## 3. 冻结解析与哈希

- `_module_schema_v1.py` 保存原有模块及其端口、单位、参数、通路和变量模型的字段、默认值与校验；`models.py` 继续导出历史类型名称。
- `_module_schema_v2.py` 基于冻结 v1 字段增加 SDK 声明；`module_contracts.py` 按 schema 选择解析器。后续字段或默认语义变更要新增 schema，不能修改已交付的冻结类。
- `ModuleDefinition` 保持现有调用入口，按 schema 先冻结解析。保存包和执行前再次按对应 schema 校验，防止程序内未校验的属性修改跳过合同约束。定义哈希按冻结字段投影序列化，允许升级预览先为编辑中的草稿计算哈希，再报告端口/通路引用不兼容；哈希不代替合同合法性校验。
- `content_hash` 仍只计算 `module_source()` 的 UTF-8 运行源码；源码列表按换行连接。SDK 声明改变不影响源码哈希。
- `definition_hash` 使用对应冻结模型的完整 JSON 默认解释，排除 `content_hash`、`definition_hash`、`package_path`，递归把整数值浮点数规范为整数，再按原有排序键、紧凑分隔符、UTF-8 和 `allow_nan=False` 的规则计算 SHA-256。schema 2 的 SDK 声明参与定义哈希；catalog 的展示字段不属于模块合同。

schema 1 的十个历史种子包、三个旧项目、原 JSON Schema 作为固定样例继续校验；schema 2 新增两个完整定义及固定规范化 JSON/双哈希。测试不得运行时生成预期哈希。固定文件位于 `tests/fixtures/module-system/`；历史样例不能被重算覆盖。

生成合同包含 `module-v1.schema.json`、`module-v2.schema.json` 和现有 `module.schema.json` 的入口；项目、API 请求/响应与 OpenAPI 同步引用新入口。项目 schema 仍为 1，可包含不同 schema 的模块快照。

## 4. 拒绝时机与诊断

编译项目、作者验证、Worker 启动及 `_load_module()` 均检查兼容性；批量执行在创建第一个 Worker 前检查全部实例，子进程也对每份传入定义重新检查。设计回调同样在执行源码前检查。保存流程沿用作者验证，拒绝时不写入新版本。

| 拒绝原因 | 诊断代码 / 字段 |
| --- | --- |
| SDK 版本未支持 | `MODULE_SDK_UNSUPPORTED` / `sdk.api_version` |
| 能力未支持 | `MODULE_CAPABILITY_UNSUPPORTED` / `sdk.capabilities` |
| 状态合同未支持 | `MODULE_STATE_CONTRACT_UNSUPPORTED` / `sdk.state_contract_version` |

格式有效但不受支持的声明可以加载和导出，以保留原始合同；执行入口会拒绝。未知 schema 或非法字段在严格解析阶段拒绝。作者验证和项目编译提供上述代码和字段；试算/设计 API 沿用既有诊断包装。既有 Worker 错误传输仍为原字符串协议，原始 RPC 的结构化错误扩展留到 D0/T2。

S2 的本地验证、适用范围及未运行项目见 [实施证据](results/S2.md)。
