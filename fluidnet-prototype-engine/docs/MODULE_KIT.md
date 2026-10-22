# 模块开发套件 v1

> 适用 `fluidnet-prototype-engine` 0.5.0，`schema_version = 1`（`backend/fn_engine/__init__.py:1`）。合同唯一来源是 `backend/fn_engine/models.py` 的 Pydantic v2 模型；本文件是施工手册，冲突时以模型为准。
> 核对基准：`docs/DATA_CONTRACT.md`、`docs/ARCHITECTURE.md`、`modules/programmable_valve/*`、`backend/fn_engine/{runtime,models,packages,compiler,solver,thermal,bench,worker,bridge,module_validation,design}.py`、`tests/test_module_versions.py`、`tests/test_platform_contracts.py`。

## 1. 目的与适用范围

在 `execution_domain='fluid'` 的项目里，用 Python 模块包声明端口、通路、参数、变量与状态，并在独立 Worker 进程里参与稳态/动态求解。模块注册 `NetworkRelation`（`pipe`/`valve`/`pump`/`compressor`/`resistance`），节点方程、压力参考、热力层与温焓输运由平台负责。

- `thermal` / `cold_store` / `refrigeration` 执行域只接受内置设备目录，Python 模块被拒绝（`DATA_CONTRACT.md:179`、`:190`、`:231`）——冷库/制冷站扩展走对应执行域。
- 流体项目里声明非 `fluid` 领域端口 → `DOMAIN_NOT_SOLVABLE`（`compiler.py:365-367`）。
- 需要新 `NetworkRelation.kind`、新 `Domain`、新求解策略 → 内核变更，不是模块包。
- 想用模块去改求解器变量 → `MODULE_OUTPUT_CONFLICT`（`simulation.py:257-259`）。

### 1.1 决策树

```text
1. 内置模型（管道/阀门/泵/边界/Junction/换热器/水箱）能表达？ → 改参数/曲线/型号/场景，不写模块
2. 方程相同、只是取值或曲线不同（Kv、UA、扬程）？          → 内置模型 + LibraryBank/Scenario
3. 需要内置没有的关系式/累计量/跨步状态？                  → 写 Python 模块包（§2–§10）
4. 冷库/冷风机/制冷站/热执行域拓扑？                       → 内置执行域，模块包不支持
5. 新 relation kind / 新端口领域 / 新求解算法？            → 内核变更，不是模块包
```

判据：**公式能化成一个标量参数 + `ctx.net.pipe/valve/pump/compressor` 之一，就用内置模型**；只有需要逐迭代计算或跨时间步记忆时才维护模块包。

## 2. 包结构

```text
modules/<module_id>/                       # 开发/种子目录；种子包只读，API 保存不写这里
├── manifest.json                          # 必需：合同（§3）
├── module.py                              # 必需：运行源码，生命周期四方法
├── design.py                              # 可选：design(ctx)，只影响 definition_hash
└── README.md                              # 可选：人读文档，引擎不读取

<module_storage_root>/module-<id>/v<N>/    # 发布后（ModuleStore.save 写出，packages.py:142-158）
├── manifest.json                          # 模型 dump 生成，含 runtime/content_hash/definition_hash
├── module.py                              # 源码，换行已规范化为 LF
├── design.py                              # 有才写
└── release.json                           # 试算凭据：created_at/release_notes/test_conditions/test_result
```

- 存储根优先级：`module_storage_root` 参数 > 数据目录 `module-packages`（存在时）> `FLUIDNET_MODULE_STORE` > `<repo>/.runtime/module-packages`（`api.py:221-223`）；只扫描含 `manifest.json` 的直接子目录（`packages.py:43-51`），目录名与 `id` 不强绑但请保持一致。
- 编码：UTF-8、**无 BOM**、LF。`load_module_package` 以 `encoding="utf-8"` 读取后直接 `json.loads`，BOM 会导致解析失败（`packages.py:23`）。
- **不要手写 hash**：manifest 写了 `content_hash` 且与 `module.py` 不符，加载即 `ValueError`（`packages.py:26-28`）；`definition_hash` 比对后被覆盖（`packages.py:36-39`）。源目录两者都省略。
- `content_hash = sha256(module.py)`（`runtime.py:138-139`）；`definition_hash` 覆盖整份合同 + 源码，排除 `content_hash`/`definition_hash`/`package_path`（`runtime.py:142-154`），所以移动目录、重排 manifest 不改变契约哈希。内置 ID 不能复用（`packages.py:118-119`）。
- `design.py` 可选，签名 `design(ctx)`：`ctx.parameter(name)` 读库值、`ctx.set(name, value)` 提方案、`ctx.log(msg)`（最多 20 条），输出按参数合同重新校验（`design.py:18-41`、`:77-103`）。

## 3. 合同字段规范

### 3.1 identifier 与命名

- `Identifier = ^[A-Za-z][A-Za-z0-9_-]{0,80}$`（`models.py:9`）：模块/端口/参数/通路 id、`NetworkRelation.relation_id`/`channel`、实例 id 都适用；**id 用英文**，**label 用中文**，`.` 和 `:` 留给变量路径与端口内部键（`DATA_CONTRACT.md:7`）。
- `VariableSpec.id` 是普通 `str`（`models.py:98`），只有 `state.` 前缀表达状态，其余不要用 `.` 造层级；同一份定义内端口/参数/变量/通路 id 不得重复（`models.py:271-283`），通路两端不能是同一端口（`models.py:288-289`）。

### 3.2 ports

| 字段 | 取值 | 规则 |
| --- | --- | --- |
| `id` | Identifier | 帧路径与变量绑定锚点，发布后不可改 |
| `label` | 中文 | 必填 |
| `domain` | `fluid`（模块唯一可用） | 非 fluid → `DOMAIN_NOT_SOLVABLE`（`compiler.py:365-367`） |
| `direction` | `in`/`out`/`bidirectional` | **仅标称**，不限制水力反向流（`DATA_CONTRACT.md:15`） |
| `required` | 默认 `true` | 为真且未连接 → `PORT_UNCONNECTED`（`compiler.py:384-385`） |
| `circuit` | 默认 `fluid` | 多回路工质的所属回路名（`DATA_CONTRACT.md:104`） |

- 启用通路的端口集合必须**恰好等于**声明端口集合，否则 `CHANNEL_COVERAGE`（`compiler.py:434-437`）。`required=false` 只对"未被启用通路引用"的端口有意义：绑在启用通路上却没接，支路另一端没有压力参考，会报 `PRESSURE_REFERENCE_MISSING`（`compiler.py:450-457`）。

### 3.3 channels

| relation | 语义 | Python 模块的落地方式 |
| --- | --- | --- |
| `resistance` | 压差由阻力关系决定 | 返回 `kind` 为 `valve`/`pipe`/`resistance` 的关系 |
| `pump_curve` | 扬程-流量曲线 | 返回 `kind='pump'`，给 `head_curve`/`speed_ratio` |
| `pressure_source` | 定压边界 | 模块不使用（边界是内置设备） |
| `heat_transfer` | 两侧换热通路 | 自己算热流写进 `heat_w`（无内置 ε–NTU 等价） |
| `signal` | 无流动信号通路 | 模块不使用 |

- `relation` 只有这五值（`models.py:92`）。`solver_model` 是自由字符串：**Python 模块跳过 `CHANNEL_MODEL_INVALID`**（`compiler.py:441` 的 `runtime != 'python'` 分支），仍建议取 `valve`/`pipe`/`pump_curve`/`resistance` 并与关系 kind 一致。
- 启用通路集合就是 evaluate 必须返回的关系集合：**恰好一条**（`solver.py:257-260`）；设 `enabled=false` 即移出集合，其端口必须被别的通路覆盖。同一实例的多条通路不能落在同一对节点上，否则 `BRANCH_SHORTED`（`compiler.py:443-445`）。

### 3.4 parameters

| 类型 | default 形状 | 校验（`models.py:57-75`） |
| --- | --- | --- |
| `number` | 有限数值（bool 不算） | 必须落在 `[minimum, maximum]`；可带 `unit` |
| `boolean` | 布尔 | 必须 true/false |
| `text` | 字符串 | — |
| `curve` | `[[x, y], ...]` | 每点两个有限数值；`head_curve` 另需 0→0、x 递增、y 严格递减（`models.py:192-198`） |

- `value_type` 四型见上（`models.py:49`）。非数值参数**不能**声明 `unit`（`models.py:73-74`）；`unit` 只影响显示，模块收到的永远是 canonical（§4）。
- 能进除数/开方/对数的参数**必须写 `minimum`**；`diameter_m` 与 `roughness_m` 同时存在时编译期额外要求 d>0、ε≥0（`compiler.py:175-182`），把 `ZeroDivisionError` 变成可定位诊断。`runtime=false`（默认）运行中不可写，`set`/PID/日程写入报 `PARAMETER_NOT_RUNTIME`（`compiler.py:475`）；PID 目标必须是 `runtime=true` 的可写数值参数（`DATA_CONTRACT.md:157`），`writable=false` 只读。

### 3.5 variables

| `source` | 谁产生 | 帧路径 | 要求 |
| --- | --- | --- | --- |
| `parameter` | 引擎 | `<inst>.param.<id>` | 必须写 `parameter_id` |
| `port` | 引擎 | `<inst>.<port>.<量>` | 必须写 `port_id` |
| `state` | 引擎展开 `ctx.state` | `<inst>.state.<key>` | `id` 必须等于 `state.<key>`，只展开标量 |
| `derived` | 模块 `ctx.var()` | `<inst>.<id>` | evaluate 或 commit_step 必须输出 |
| `system` | 引擎系统量 | 由引擎决定 | 模块不要声明 |

- `parameter_id`/`port_id` 必须引用本模块声明的对象（`models.py:290-294`）。保存前检查所有 `derived`/`state` 变量在试算末帧出现（`D1.<id>`），缺失报 `MODULE_OUTPUT_MISSING`（`packages.py:136-138`）：**变量 id 必须与 `ctx.var` 键、`ctx.state` 键严格同名**。状态只展开标量（`solver.py:267`、`:860-861`），嵌套结构请用派生变量打平。

### 3.6 诊断 code 与 severity

`Diagnostic{code, message, severity, instance_id, field}`，`severity ∈ {info, warning, error}`，默认 `error`（`models.py:628-633`）；入口是 `ctx.diagnostic(code, message, severity="warning")`（`runtime.py:117-118`）。

- **`error` 会中断本次 evaluate/commit 并让运行失败**（`solver.py:263-265`、`:857-858`），只在"结果不可信"时用；`warning` 表示工程包络（超铭牌、参数被截断），结果仍可用；`info` 是一次性提示（模型假设、近似）。
- code 用 `UPPER_SNAKE_CASE`，模块自有码加前缀（如 `MYVALVE_OPENING_CLAMPED`），避开内核码（`NO_FLOW_HEAT`、`PARAMETER_RANGE`、`PHASE_UNSUPPORTED`…）；message 写清实例/通路、数值+单位与建议，不要在每次迭代刷同一 warning（一帧内会累积）。

## 4. 单位规范表

```text
canonical = (display - display_offset) × display_scale        （models.py:39-43）
 display  = canonical / display_scale + display_offset
```

| 量 | canonical | 常见显示 | scale | offset |
| --- | --- | --- | --- | --- |
| 绝对压力 | Pa | kPa / MPa | 1000 / 1e6 | 0 |
| 温度 | K | °C | 1 | −273.15 |
| 开度 / 效率 / 比例 | 1 | % | 0.01 | 0 |
| 管径 / 长度 / 粗糙度 | m | mm | 0.001 | 0 |
| 质量流量 | kg/s | kg/s | 1 | 0 |
| 比焓 | J/kg | kJ/kg | 1000 | 0 |
| 功率 / 热流 / UA | W、W/K | kW、kW/K | 1000 | 0 |
| 动力黏度 | Pa·s | mPa·s | 0.001 | 0 |
| 质量 | kg | kg | 1 | 0 |

- **模块只看到 canonical**：原型显示值在 `bridge.parameter_map` 一次性换算（`bridge.py:54`），编译期不再换算（`compiler.py:132-165`）。模块里**禁止**再乘 1000、再减 273.15。压力一律绝压（不加隐含大气压、不把表压当绝压，`DATA_CONTRACT.md:72`），温差不要声明 offset；换算只支持线性映射，对数/分段量（dB、湿球）用 `curve`/`text`；帧变量一律 canonical，未知量输出 `None`（`DATA_CONTRACT.md:86`）。

## 5. 生命周期与状态语义

| 阶段 | 调用次数 | 允许 | 禁止 |
| --- | --- | --- | --- |
| `initialize(ctx)` | 每次运行一次 | `ctx.state.setdefault` 初值、读参数、缓存静态量 | 算流量、依赖上次运行、发 error 诊断 |
| `evaluate(ctx)` | 每子步多次（数值迭代） | 读参数/试算端口/只读状态、注册关系、`ctx.var` | 写 `ctx.state` 期望生效、改 `self`/全局、IO、`print`、依赖 `ctx.channel` |
| `commit_step(ctx, dt_s)` | 每个**被接受**子步一次 | 用收敛端口/通路更新 `ctx.state`、`ctx.var` | 假定 dt 恒定、发 error 诊断、改求解结果 |
| `finalize(ctx)` | 运行结束一次 | 释放外部资源 | 写状态、抛异常 |

- evaluate 的 `readonly_state`、参数、上下文都是**深拷贝**（`runtime.py:198-199`）：改了不进提交状态；`self`/全局由作者自己保持无副作用。
- evaluate 里 `ctx.port(p).mass_flow_kg_s` 是 `None`（`solver.py:228`），`density_kg_m3`/`viscosity_pa_s` 早期可能为 0；`density_kg_m3=rho or 0.0` 的 0 表示"让求解器用支路物性"（`solver.py:101`）。
- evaluate 里 **`ctx.channel()` 恒为空值** `ChannelState(0,0)`（`runtime.py:111-112`），读流量只能等 commit_step。`dt_s > 0` 是硬约束（`models.py:237`）；t=0 只采样不提交，第一帧没有 commit（`DATA_CONTRACT.md:259`）。
- state 必须是 JSON 字典，`NaN`/`Inf` 被 `allow_inf_nan=False` 拒绝（`models.py:13`）；工程上限 **64 KiB**——控制脚本 `ctx.state` 是硬校验（`control.py:15-16`），模块 state 没有同一条硬校验，但每次 evaluate/commit 都要深拷贝并走 JSON RPC，超限只会表现为超时（默认 10 s，`runtime.py:231`）。状态只在本次运行内有效，跨 run/跨重启不恢复（`DATA_CONTRACT.md:262`），`initialize` 必须能独立构造全部初值。
- **每条启用通路恰好一条关系**（`solver.py:257-260`）：少、多、channel 名拼错都会报错；`relation.channel` 与 `relation_id` 都等于 `ChannelSpec.id`（`runtime.py:61-62`）。
- **零流量不能带热**：热力层对 `|w| ≤ max(1e-12, mass_tolerance_kg_s)` 的通路，`heat_w != 0` 直接报 `NO_FLOW_HEAT`（`thermal.py:165`、`:245-249`），因为 `h_out = h_in + (heat_w + P_shaft)/w`（`ALGORITHM.md:166`）。
- **关阀用 `opening_ratio` 精确 `0`**：求解器把它变成 `flow == 0` 等式约束（`solver.py:292-298`、`:307-310`），热力层同样识别（`thermal.py:171`）。用 `1e-9` 会得到约 `1e18` 量级压降，迭代必然失败。

## 6. 可用 API 速查

`ModuleContext`（`runtime.py:87-118`）：

| 成员 | 签名/返回 | 关键约束 |
| --- | --- | --- |
| `ctx.parameter(name, default=None)` | `dict.get` | 参数表已含全部声明默认值（`compiler.py:154`） |
| `ctx.port(name)` | `PortState`，缺失返回空对象 | evaluate 中流量为 `None` |
| `ctx.channel(name)` | `ChannelState`，缺失返回 0 值 | **仅 commit_step 有真实值** |
| `ctx.var(name, value)` | 写输出变量 | 必须有限；键与 `VariableSpec.id` 同名 |
| `ctx.state` | `dict` | 只有 commit_step 的修改生效 |
| `ctx.fluid` | 物性服务 | 第一个端口所在回路；惰性创建（`runtime.py:42-54`） |
| `ctx.fluid_at(port_id)` | 物性服务 | 跨换热器两侧不同工质（`runtime.py:101-103`） |
| `ctx.diagnostic(code, message, severity="warning")` | 追加诊断 | error 中断运行 |

物性方法 `state_pt(pressure_pa, temperature_k)`、`state_ph(pressure_pa, enthalpy_j_kg)` → `FluidState`（`properties.py:497`、`:504`）；服务按 `(backend, fluid, phase_policy)` 缓存（`properties.py:579-588`）。

### 6.1 `ctx.net` 构建器签名

```python
ctx.net.pipe(*, channel, length_m, diameter_m, roughness_m=0.0,
             density_kg_m3=None, viscosity_pa_s=None, height_m=0.0, heat_w=0.0)
ctx.net.valve(*, channel, kv, opening, density_kg_m3=None, height_m=0.0, heat_w=0.0)
ctx.net.pump(*, channel, head_curve, speed_ratio=1.0, density_kg_m3=None, heat_w=0.0)
ctx.net.compressor(*, channel, forced_mass_flow_kg_s)
```

（`runtime.py:66-84`；`valve` 形参名是 `kv`，落到关系参数 `kv_m3_h`。`heat_w` 以**流体吸热为正**，热力层按 `h_out += heat_w/|m|` 施加，`runtime.py:64-65`。）

### 6.2 `NetworkRelation` kind 与必需参数

| kind | 必需参数 | 额外校验（`models.py:176-198`） |
| --- | --- | --- |
| `pipe` | `length_m`, `diameter_m`, `roughness_m` | `length_m`/`diameter_m` > 0；`roughness_m` ≥ 0 |
| `valve` | `kv_m3_h`, `opening_ratio` | `kv_m3_h` > 0；`opening_ratio ∈ [0,1]` |
| `pump` | `head_curve`, `speed_ratio` | `speed_ratio` > 0；曲线 ≥2 点、首点 x=0、末点 y=0、x 增 y 严格减、全非负 |
| `compressor` | `forced_mass_flow_kg_s` | 有限数值；求解器把它变成强制流量约束（`solver.py:296-298`） |
| `resistance` | `diameter_m`, `loss_coefficient` | d > 0、ζ ≥ 0；方程 `Δp = ζ·m²·sign(m)/(2ρA²)`（`solver.py:113-115`） |

所有参数值必须是有限数值（bool 不算），否则构造时抛 `ValueError`，异常会以运行失败形式出现。

### 6.3 `ctx.net` 没有 `resistance()`

`NetworkBuilder` 只提供 `pipe/valve/pump/compressor`（`runtime.py:57-84`），而 `resistance` 是合法 kind 且求解器已实现方程。两个选项：

1. **折算成 `valve`（推荐）**：`Kv = Q_m3_h / sqrt(Δp_bar / (ρ/1000))`，单一实现路径、已有量纲测试；也可折算成 `pipe`（给长度/内径/粗糙度，由 Colebrook 求解）。
2. **手工追加关系**：`ctx.net.relations.append(NetworkRelation(relation_id="main", kind="resistance", channel="main", parameters={...}))`，需 `from fn_engine.models import NetworkRelation`。风险写进 README：`fn_engine` 不是稳定公共 API，Worker 可导入性依赖 `PYTHONPATH` 注入（`runtime.py:255-264`）；`ctx.net._add` 是私有方法；校验异常会直接打断运行。选这条路就锁版本并在发布说明标注。

## 7. 测试分级

本机若缺 `scipy`/`coolprop`，L3/L4 不可运行；**不要**把全量 pytest 当快速反馈。L1 直接跑命令，L2 代码块存成临时脚本（如 `_l2_check.py`，勿提交）后运行。

### L1 契约（纯 Pydantic）

```powershell
cd F:\beisilu\fluidnet-work\fluidnet-prototype-engine
python -c 'import sys; sys.path.insert(0, "backend"); from fn_engine.packages import load_module_package, package_ref; m = load_module_package("modules/programmable_valve"); print(m.id, m.version, m.entrypoint, m.runtime, len(m.content_hash), len(m.definition_hash), package_ref(m).version)'
```

- 加载不抛异常：manifest+module.py 存在、UTF-8 无 BOM、无多余字段（`extra="forbid"`，`models.py:13`）；`m.runtime == 'python'`（加载时强制注入，`packages.py:33`）；`package_ref(m).version == '1.0.0'`（`packages.py:55`）。
- 两个哈希都是 64 位十六进制；`module_definition_hash` 对 `16` 与 `16.0` 等值（`runtime.py:144-153`；`tests/test_module_versions.py:110-114`）。
- 入口四方法齐全：`WorkerProcess.validate_entrypoint()` 按 `initialize/evaluate/commit_step/finalize` 逐一绑参（`worker.py:42-46`），缺失或写成协程都报错。

### L2 逻辑（`InProcessModuleRunner`，不依赖 scipy/coolprop）

```python
import sys; sys.path.insert(0, 'backend')
from fn_engine.models import ChannelState, CommitStepRequest, EvaluateRequest, FluidConfig, PortState
from fn_engine.packages import load_module_package
from fn_engine.runtime import InProcessModuleRunner
m = load_module_package('modules/programmable_valve')
r = InProcessModuleRunner(m, {p.id: p.default for p in m.parameters}, FluidConfig())
r.initialize()
req = EvaluateRequest(run_id='t', instance_id='D1', iteration_id=1, time_s=0.0,
    trial_ports={'in0': PortState(pressure_pa=250000, temperature_k=293.15, density_kg_m3=998.2),
                 'out0': PortState(pressure_pa=120000, temperature_k=293.15, density_kg_m3=998.2)},
    readonly_state=r.state)
first, second = r.evaluate(req), r.evaluate(req)
assert [x.channel for x in first.relations] == ['main']
assert first.model_dump() == second.model_dump()             # 幂等、无副作用
assert r.state == {'throughput_kg': 0.0, 'commit_count': 0}   # evaluate 未污染已提交状态
r.commit_step(CommitStepRequest(run_id='t', instance_id='D1', time_s=0.1, dt_s=0.1,
    converged_ports=req.trial_ports,
    converged_channels={'main': ChannelState(mass_flow_kg_s=2.5, pressure_drop_pa=130000.0)}))
assert r.state['throughput_kg'] == 0.25                       # abs(2.5) * 0.1
```

- 关系集合等于启用通路集合，`kind`/关键参数在预期范围内；commit 后 state 变化，evaluate 的 `readonly_state` 不被污染（对应 `runtime.py:198`）。
- 负向断言：evaluate 里 `ctx.channel('main').mass_flow_kg_s == 0`（不是真实流量）。
- 全程不触发 CoolProp：给 trial 端口填 `density_kg_m3` 就能让典型模块跳过物性调用。

### L3 网络集成（需要 scipy/coolprop）

```powershell
python -m pytest tests/test_platform_contracts.py -k "python_module_relation or versioned_python_package or dynamic_worker" -q
python -m pytest tests/test_module_versions.py -k "multi_channel or save_restart" -q
```

复用测试里的项目工厂（`tests/test_platform_contracts.py:37-53`）后断言：

```python
from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady, solve_dynamic
net = compile_project(project)                  # 内置 pressure_source + 你的模块
frame = solve_steady(net)
assert frame.valid and frame.variables['V1.main.mass_flow_kg_s'] > 0
assert frame.variables['V1.param.opening_ratio'] == 0.5
assert [f.variables['V1.state.commit_count'] for f in solve_dynamic(net, .25, .1)] == [0, 1, 2, 3]
```

要点：`compile_project` 通过（端口覆盖、压力参考、哈希一致）；稳态 `valid=True`；流量/压降/变量键齐全；动态只对接受子步提交（`tests/test_platform_contracts.py:127-131`）。独立验证台 `POST /api/v1/modules/test` 另有三条接线约束：端口全 `fluid`、每条启用通路占一对独立端口、所有端口都被启用通路绑定（`bench.py:18-34`），否则 422。

### L4 参考算例（解析解/倍思鹿对照）

- 阀门解析解：`Δp = 1e5·(ρ/1000)·Q|Q|/Kv²`，`Kv = kv_m3_h·opening`（`solver.py:104-106`）→ `Q = Kv·sqrt(Δp/(1e5·ρ/1000))`、`m = ρQ/3600`。250 kPa → 120 kPa、Kv=5、ρ=998.2 应得 `m ≈ 50 kg/s`。
- 与倍思鹿/厂商样本对照口径见 `docs/BASELU_COMPARISON.md`；建议容差：流量相对 1e-3、压降相对 1e-6（求解器自身验收 1 Pa / 1e-8 kg/s，`solver.py:362`）。
- 能量：`frame.metrics['energy_residual_w']` 相对全网焓流规模 ≤ 1e-6（`ALGORITHM.md:210`）；带 `heat_w` 的模块必须在这条线上。

## 8. 验收 checklist（发布前逐项打勾）

- [ ] **契约**：manifest 无未知字段；`id`/`label` 分工正确；四类 id 唯一；`entrypoint` 与类名一致。
- [ ] **契约**：端口全 `fluid`；`required` 与接线一致；每端口被启用通路覆盖；关系集合 == 启用通路集合。
- [ ] **单位**：参数/变量全 canonical、无二次换算；压力绝压；温度只用一个 offset；`UnitSpec` 的 scale/offset 与 §4 一致；非数值参数无 `unit`。
- [ ] **诊断**：`error` 只用于"结果不可信"；code 有模块前缀；message 含数值+单位+建议。
- [ ] **边界**：`opening=0` 时 kv/`heat_w` 行为有定义并被 L2 断言覆盖；所有除数量有 `minimum` 或运行时防御。
- [ ] **异常**：参数非法不抛裸异常（无 `ZeroDivisionError`/`KeyError` 冒到运行层）；超界先诊断再取安全值。
- [ ] **数值与守恒**：无 `NaN`/`Inf` 进 `ctx.var` 或 state；除零/开方/对数前判零；动态 `energy_residual_w` 在容差内，累计量等于 `∫|m|dt`。
- [ ] **性能与生命周期**：单次 evaluate 无物性调用时 < 1 ms；稳态迭代数不明显高于内置同构案例；evaluate 幂等、commit 只在接受步、状态只经 commit 生效、`initialize` 自足且 state ≤ 64 KiB。
- [ ] **文档与版本**：README 含物理假设/公式、参数表、单位、诊断码表、已知边界、参考算例；双哈希 64 hex；重排 manifest/移动目录后 `definition_hash` 不变。
- [ ] **兼容与发布**：`expected_latest_version` 与目录一致、旧版本未改写；旧项目快照仍能 `compile_project` + `solve_steady`；不兼容变更已升版；`release.json` 含试算凭据且重启后可重放。

## 9. 版本与发布流程

1. 在 `modules/<id>/` 改源码与合同，先跑 L1/L2。
2. 调 `POST /api/v1/modules/versions`，body `{module, expected_latest_version, release_notes, test}`（`models.py:732-736`）。`expected_latest_version` 必须等于当前最新（首次 0），否则 `ModuleVersionConflict` → HTTP 409（`packages.py:120-121`；`api.py:486-487`）。
3. 保存内部顺序（`packages.py:115-158`）：版本冲突 → 内置 ID 检查 → 版本号 = 最新 + 1 → 清空 `content_hash`/`definition_hash`/`package_path` → `validate_module_definition`（语法 + 入口）→ 换行规范化 → 双哈希 → `run_module_test` 边界试算 → 检查 `derived`/`state` 输出 → 写临时目录 → `os.rename` 原子发布 → 写 `release.json`。
4. 试算失败、输出缺失、语法/入口错误返回 422 且**不落盘**（`tests/test_module_versions.py:166-191`；`api.py:488-490`）；并发保存同一版本一个 201、一个 409，旧版本不被覆盖（`packages.py:153-158`；`tests/test_module_versions.py:206-211`）。
5. 项目绑定：`Project.modules` 存定义快照，`ModuleInstance.package` 存 `ModulePackageRef`（`id` + `N.0.0` + 双哈希）；不一致时模型层报"版本绑定与定义快照不一致"（`models.py:490-499`），源码被篡改则编译期报 `MODULE_HASH_MISMATCH`/`MODULE_DEFINITION_HASH_MISMATCH`（`compiler.py:349-357`）。
6. 旧项目固定旧版本：目录更新不会替换项目实例；跨版本迁移与同项目多版本混用暂不支持（`ARCHITECTURE.md:164-166`）。

**不兼容变更**（必须升版并在 release_notes 标注）：删除/重命名任何 parameter/port/channel/variable id；改端口 `domain`/`direction`/`required`/`circuit`、通路 `input_port`/`output_port`、新增**启用**通路；改 `value_type`、单位 `display_scale`/`display_offset`（原型场景覆盖是显示值，物理含义会变）、`default`；改 `state` 键名（旧项目状态从空开始，累计量断裂）；改关系 `kind`/`solver_model` 的物理语义、`entrypoint`、诊断 code 的对外含义。

**兼容变更**（仍需升版以便追溯）：新增带默认值的参数（编译期补默认，`compiler.py:154`）、新增变量（新帧键）、新增 `enabled=false` 通路、改 `label`/`description`/`README`。

## 10. 模板

### 10.1 `modules/example_valve/manifest.json`

```json
{
  "schema_version": 1, "id": "example_valve", "name": "示例节流阀", "version": 1,
  "category": "自定义模块", "description": "Kv 随开度线性变化，可声明流体吸热；演示合同字段、单位换算、诊断分级与状态累计。",
  "entrypoint": "module:Module", "solver_model": "valve", "source_format": "python-v1",
  "ports": [
    {"id": "in0", "label": "入口", "domain": "fluid", "direction": "in", "required": true, "circuit": "fluid"},
    {"id": "out0", "label": "出口", "domain": "fluid", "direction": "out", "required": true, "circuit": "fluid"}
  ],
  "parameters": [
    {"id": "opening_ratio", "label": "阀门开度", "value_type": "number", "default": 0.8, "minimum": 0.0, "maximum": 1.0,
     "unit": {"quantity": "ratio", "canonical_unit": "1", "display_unit": "%", "display_scale": 0.01}},
    {"id": "kv_m3_h", "label": "额定流量系数 Kv", "value_type": "number", "default": 16.0, "minimum": 0.01},
    {"id": "heat_w", "label": "流体吸热（负为散热）", "value_type": "number", "default": 0.0,
     "unit": {"quantity": "power", "canonical_unit": "W", "display_unit": "kW", "display_scale": 1000}}
  ],
  "variables": [
    {"id": "effective_kv_m3_h", "label": "有效 Kv", "quantity": "flow_coefficient", "source": "derived"},
    {"id": "pressure_drop_pa", "label": "压降", "quantity": "pressure", "source": "derived",
     "unit": {"quantity": "pressure", "canonical_unit": "Pa", "display_unit": "kPa", "display_scale": 1000}},
    {"id": "state.throughput_kg", "label": "累计通过质量", "quantity": "mass", "source": "state", "unit": {"quantity": "mass", "canonical_unit": "kg", "display_unit": "kg"}},
    {"id": "state.closed_time_s", "label": "全关累计时间", "quantity": "time", "source": "state"}
  ],
  "channels": [
    {"id": "main", "name": "主通路", "input_port": "in0", "output_port": "out0", "relation": "resistance", "solver_model": "valve", "enabled": true}
  ],
  "bank_names": ["额定工况", "部分负荷", "调试备份"]
}
```

### 10.2 `modules/example_valve/module.py`

```python
"""示例模块：可编程节流阀。参数已是规范单位（K/Pa/W/m³·h⁻¹/kg·s⁻¹），模块内不再换算；evaluate 无副作用，只有 commit_step 里改 ctx.state 才会保存。"""


class Module:
    def initialize(self, ctx):
        # state 的键必须与 manifest 里 source=state 的变量 id 对齐：state.<key>
        ctx.state.setdefault("throughput_kg", 0.0)
        ctx.state.setdefault("closed_time_s", 0.0)

    def evaluate(self, ctx):
        opening, kv = float(ctx.parameter("opening_ratio")), float(ctx.parameter("kv_m3_h"))
        # 编译期已校验范围；这里再防一次，避免直接调 API 时除零。
        if kv <= 0.0:
            ctx.diagnostic("EXAMPLEVALVE_KV_INVALID", f"kv_m3_h={kv:g} 必须大于 0，本次按 1e-3 计算", "error")
            kv = 1e-3
        if not 0.0 <= opening <= 1.0:
            ctx.diagnostic("EXAMPLEVALVE_OPENING_CLAMPED", f"opening_ratio={opening:g} 超出 [0,1]，已截断", "warning")
            opening = min(max(opening, 0.0), 1.0)

        inlet, outlet = ctx.port("in0"), ctx.port("out0")
        density = inlet.density_kg_m3 or 0.0        # 0 = 未提供，由求解器回退到支路物性
        heat_w = float(ctx.parameter("heat_w"))
        # 关阀必须是精确 0：求解器把 opening_ratio == 0 变成 flow == 0 等式约束。
        if opening == 0.0 and heat_w != 0.0:
            ctx.diagnostic("EXAMPLEVALVE_ZERO_FLOW_HEAT", f"全关时 heat_w={heat_w:g} W 无法施加，已按 0 处理", "warning")
            heat_w = 0.0

        ctx.net.valve(channel="main", kv=kv, opening=opening, density_kg_m3=density, heat_w=heat_w)
        ctx.var("effective_kv_m3_h", kv * opening)
        ctx.var("pressure_drop_pa", (inlet.pressure_pa or 0.0) - (outlet.pressure_pa or 0.0))

    def commit_step(self, ctx, dt_s):
        ctx.state["throughput_kg"] += abs(ctx.channel("main").mass_flow_kg_s) * dt_s
        if ctx.parameter("opening_ratio") == 0.0:
            ctx.state["closed_time_s"] += dt_s

    def finalize(self, ctx):
        pass  # 运行结束即丢弃实例，不写状态
```

发布前把 `example_valve` 换成你的英文 id 并同步目录名；`design.py` 只在需要"由库值反推参数"时添加，写法见 `design.py:43-57`。

## 11. 常见错误清单

| # | 现象 | 根因 | 修法 |
| --- | --- | --- | --- |
| 1 | 运行报"必须为每条启用通路提供且仅提供一条关系" | 少/多返回关系，或 `channel` 拼错 | 按 manifest 的 `enabled` 通路逐个生成；L2 断言集合相等（`solver.py:257-260`） |
| 2 | 加载即 `ValueError: 内容哈希不一致` | manifest 手写 `content_hash`，或源码被改 | 源目录删除 `content_hash`/`definition_hash`（`packages.py:26-28`） |
| 3 | 迭代不收敛、压降爆炸 | 关阀写成 `1e-9` 而非精确 `0` | 用 `opening=0.0`（`solver.py:292`） |
| 4 | evaluate 抛"必须大于零"/"开度必须在 [0,1]" | 参数直接透传给 `NetworkRelation` | 先 clamp/兜底再构造关系（`models.py:186-191`） |
| 5 | `NO_FLOW_HEAT` | 零流量通路仍声明 `heat_w` | 关阀时 `heat_w=0`，或让热流随流量缩放（`thermal.py:245-249`） |
| 6 | commit_step 抛 `KeyError` | 状态键没在 initialize 里 `setdefault` | initialize 里初始化全部键（`modules/programmable_valve/module.py:3-4`） |
| 7 | 流量差 1000 倍、温度差 273 K | 模块内又做了一次单位换算 | 只接受 canonical（`bridge.py:54`） |
| 8 | `MODULE_OUTPUT_MISSING` | `derived`/`state` 变量 id 与 `ctx.var`/`ctx.state` 键不一致 | state 变量 id 必须是 `state.<key>`（`packages.py:136-138`） |
| 9 | "端口方向反了，关阀还有流" | 把 `direction` 当流向开关 | `direction` 只是标称；用 `opening`/`kv` 控流（`DATA_CONTRACT.md:15`） |
| 10 | `PRESSURE_REFERENCE_MISSING` | `required=false` 端口被启用通路引用却没接 | 可选端口不要绑启用通路（`compiler.py:434-457`） |
| 11 | evaluate 里 `ImportError`/`AttributeError` | 依赖 `fn_engine` 内部或 `ctx.net._add` 等私有成员 | 只用 §6 白名单；`resistance` 走 §6.3 受控方案 |
| 12 | 读不到流量 / 状态没保存 | evaluate 里用 `ctx.channel`，或在 evaluate 里改 `ctx.state` | 流量到 commit_step 读，状态只在 commit_step 改（`runtime.py:111-112`、`:198`） |
| 13 | 运行失败且没有部分历史 | 模块抛异常或发 `severity='error'` 诊断 | 分级诊断；异常由 Worker 转成运行失败（`worker.py:83-85`） |
| 14 | 帧里出现 NaN / 校验错误 | `ctx.var` 或 state 传了 NaN | 除法/开方前判零；不确定就输出 `None`（`models.py:13`） |
| 15 | 两个实例数据互相污染 | 用了模块级/全局缓存 | 同 Worker 多实例共享模块对象，缓存必须按实例键（`batch.py:44`） |
| 16 | 运行变慢、偶发超时 | 每次迭代都调 CoolProp 或大循环 | 试算端口已给密度就别再查物性；单次 RPC 默认 10 s（`runtime.py:231`） |
| 17 | `MODULE_OUTPUT_CONFLICT` | commit_step 输出覆盖求解器变量 | 换名，避开 `<inst>.<channel>.*`、`<inst>.mass_flow_kg_s`（`simulation.py:257-259`） |
| 18 | 保存 422 但错误指向 entrypoint | 缺四方法之一，或写成 `async def` | 四个同步方法齐全，签名 `(self, ctx)` / `(self, ctx, dt_s)`（`worker.py:42-46`） |
| 19 | 本地 ruff/mypy 结论与 CI 不一致 | mypy 只查 `backend/fn_engine`；ruff 只开 `E9`/`F`、行宽 120 | 模块目录自行 `ruff check modules/<id>`；删未使用 import（`mypy.ini:15`、`ruff.toml:9-21`） |
| 20 | `evaluate` 里的 print 看不到 | Worker 把 stdout/stderr 重定向到 devnull | 用 `ctx.diagnostic` 表达信息（`worker.py:78`） |
| 21 | 状态在第二次运行里"丢失" | 依赖跨 run 恢复 | 每次运行重新 `initialize`，状态从 0 起（`DATA_CONTRACT.md:262`） |
