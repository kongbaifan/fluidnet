# 数据合同与定义

## 版本与来源

`schema_version = 1`。Pydantic v2 模型是唯一合同来源；运行 `python scripts/generate_contracts.py` 同步 JSON Schema、OpenAPI 与参考文件。额外字段默认拒绝，数值参数在编译时进行有限性和模型范围校验。项目和 Worker 边界使用 Pydantic，求解器内部不把每次迭代包装成 JSON 对象。

模块、实例、端口、参数、通路的 ID 使用字母开头、字母/数字/下划线/短横线组合，最长 81 个字符。`.` 和 `:` 留给变量路径及端口内部键。

## 对象

| 对象 | 核心字段 | 含义 |
| --- | --- | --- |
| `ModuleDefinition` | id, version, ports, parameters, variables, channels, solver_model | 一个可复用设备类型的计算定义 |
| `PortSpec` | id, domain, direction, required, circuit | 连接位置；in/out 是标称方向，不限制水力反向流 |
| `ChannelSpec` | id, input_port, output_port, relation, solver_model, enabled | 设备内部的一条物理关系；换热器有两条独立通路 |
| `ParameterSpec` | id, default, unit, minimum, maximum, runtime, writable | 规范值默认参数；runtime 是后续命令能力声明 |
| `VariableSpec` | id, quantity, unit, source, port_id, parameter_id | 相对于实例的稳定变量路径及来源 |
| `ModuleInstance` | id, module_id, parameters, draft_parameters, banks, model_id, model_version, package | 参数与型号引用；package 锁定 Python 模块定义 |
| `Connection` | id, source, target | 两个 Endpoint(instance_id, port_id) 的物理连接 |
| `Scenario` | id, name, overrides | 按实例 ID 提供规范参数覆盖；本次运行使用副本 |
| `Project` | modules, instances, connections, scenarios, selected_variables, solver | 一次可独立计算和复现的项目 |
| `RunRequest` | project, mode, duration_s, dt_s, scenario_id, selected_variables, history, trend_variables | 创建一次运行；变量选择与历史瘦身（`history='trend'`）不影响物理求解 |
| `RunCommand` | action, instance_id, parameter_id, value | 后台运行控制请求;仅 pause/resume/stop 生效 |
| `RunFrame` | status, valid, time_s, variables, diagnostics, metrics, full | 一个时刻的结果与质量证据；`full=false` 表示瘦身历史中只含曲线变量的帧 |
| `FluidConfig` | backend, fluid, composition, phase_policy | 物性服务选择和单相约束；`fluid` 可带后端前缀与质量分数，如 `INCOMP::MEG[0.3]` |
| `ModulePackageRef` | module_id, version, content_hash, definition_hash | 模块 ID、N.0.0 版本、源码与规范定义哈希 |
| `ModuleSaveRequest` | module, expected_latest_version, release_notes, test | 带版本冲突检查的模块保存请求 |
| `ModuleVersionResponse` | module, package, created_at, release_notes, tested, test_conditions, test_result | 不可变版本及试算凭据 |
| `PortState` | pressure, temperature, enthalpy, density, viscosity, specific_heat, flow, quality | Worker 试算和收敛后的端口状态，全部可空 |
| `FluidState` | pressure, temperature, enthalpy, density, viscosity?, specific_heat?, conductivity?, entropy?, internal_energy?, cv?, speed_of_sound?, phase, quality? | 物性服务返回值；两相区内黏度、比热、导热、cv、声速为空；INCOMP 无声速 |
| `SolverOptions` | 容差、迭代上限、动态步长、热力层与耦合选项 | 见下文「求解选项与热力诊断」 |
| `ChannelState` | mass_flow_kg_s, pressure_drop_pa | 收敛通路结果，供 commit_step 累计状态 |
| `NetworkRelation` | relation_id, kind, channel, parameters | 模块向平台注册的设备关系 |
| `EvaluateRequest/Response` | trial_ports, readonly_state / relations, variables | 无副作用的数值试算协议 |
| `CommitStepRequest/Response` | converged_ports, converged_channels, dt_s / state | 收敛时间步的状态提交协议 |

`source` 支持 runtime/header 文本和 design 文本数组，作为定义资料保存。`state_model`、`thermal_model` 是扩展标识，不代表对应功能已经实现。内置未知水力模型和水箱状态模型明确拒绝；Python 模块可声明 generic，必须在 evaluate 为每条启用通路返回有效 SDK 关系。内置换热器的 `epsilon_ntu` 已由热力层计算；只有 `thermal=False` 时才产生 `THERMAL_NOT_SOLVED` 警告。

`NetworkRelation.parameters` 可带 `heat_w`（W，流体吸热为正，有限数），由 `ctx.net.pipe/valve/pump(..., heat_w=...)` 提交，热力层按 `h_out += heat_w / |m|` 处理。`pump`、`compressor` 关系的水力功率 `Δp·|m|/ρ` 另作为轴功计入流体焓升；关系不带效率，泵损失需由模块用 `heat_w` 声明。

模块包的 `manifest.json` 与源码构成可追踪单元；`content_hash` 不一致时，模块校验和项目编译都会拒绝执行。当前提供的 `modules/programmable_valve` 是首个可执行示例。

已保存版本另外携带 `definition_hash`，覆盖源码、版本和契约字段，排除机器路径与哈希字段本身。ParameterSpec.default 中的 `16` 与 `16.0` 按等值处理；哈希不是数字签名。未绑定的草稿可清空两个哈希用于独立测试，项目快照必须保留保存时的值。实例若携带 `package`，其 ID、版本及双哈希必须与 `Project.modules` 中对应定义一致。

参数默认值在 Pydantic 层检查类型、有限性、上下限及范围顺序；非数值参数不能声明数值单位换算。变量的 `parameter_id` 和 `port_id` 必须引用本模块声明。版本保存还要求试算结果包含所有声明的 derived/state 输出。

只要参数集合同时含 `diameter_m` 与 `roughness_m`，编译即检查前者严格大于零、后者不小于零(非有限数值或布尔值也拒绝)，违反时抛 `PARAMETER_RANGE`；相对粗糙度上限仍是 `ROUGHNESS_RANGE`。自定义 Python 模块若未声明参数下限，可能传入零或负的内径，这条检查把它转成可定位的诊断而不是 `ZeroDivisionError`。

`ParameterSpec.value_type` 决定实例参数的形状：`number` 为有限数值并可用 `unit` 做显示换算，`boolean`/`text` 为布尔或字符串，`curve` 为 `[x, y]` 有限数值点对数组。四种类型都可以在设备面板逐实例编辑，草稿经“预览并应用”写入 `ModuleInstance.parameters`；`parameter_map` 只对数值参数做单位换算，其余类型按原值传递。

## 单位

`UnitSpec` 使用以下统一公式：

```text
canonical = (display - display_offset) × display_scale
 display  = canonical / display_scale + display_offset
```

| 量 | 规范单位 | 显示单位 | scale | offset |
| --- | --- | --- | --- | --- |
| 绝对压力 | Pa | kPa | 1000 | 0 |
| 温度 | K | °C | 1 | -273.15 |
| 开度、效率 | 1 | % | 0.01 | 0 |
| 内径、粗糙度 | m | mm | 0.001 | 0 |
| 质量流量 | kg/s | kg/s | 1 | 0 |
| 比焓 | J/kg | kJ/kg | 1000 | 0 |
| 动力黏度 | Pa·s | mPa·s | 0.001 | 0 |
| 定压比热 | J/(kg·K) | kJ/(kg·K) | 1000 | 0 |
| 传热/散热能力 | W/K | W/K | 1 | 0 |

体积流量是派生量：`Q_m3_h = m_kg_s / rho × 3600`，`rho` 为该支路水力所用密度。`reference` 模式的水力回归兼容值使用约 998.275 kg/m³；配置其他单相流体时由 CoolProp 在参考压力和温度处提供密度与黏度；`node` 模式使用支路两端节点的平均物性。原型设备变量表压力使用 MPa，适配器明确按 1e6 转换；画布和总览压力按 kPa 显示。不得把表压自动当绝对压力，也不加隐含大气压。

## 变量命名与符号

- `V1.ch0.mass_flow_kg_s`：通路流量，正值表示从 input_port 流向 output_port。
- `V1.mass_flow_kg_s`：单通路设备的便捷别名。换热器无此别名，使用 `HX1.ch0` 和 `HX1.ch1`。
- `V1.in0.pressure_pa`、`V1.out0.pressure_pa`：端口绝对压力。
- `V1.out0.mass_flow_kg_s`：**流入设备为正**，所以正向运行时出口端口值为负。
- `V1.param.opening_ratio`：已应用的规范参数。
- `P1.shaft_power_w`：按压力增益、体积流量和效率估算的轴功率；热力层把它全部计入流体焓升。
- `V1.out0.{temperature_k, enthalpy_j_kg, density_kg_m3, viscosity_pa_s, specific_heat_j_kg_k, quality}`：端口热力状态。出口端口为该支路出口流（混合前），入口和节点端口为节点混合状态，向网络补给的压力边界端口为边界给定状态，吸收流量的压力边界端口为到达的流体状态（设定值见 `B2.param.temperature_k`）。`quality` 单相时为空。
- `V1.ch0.{inlet_temperature_k, outlet_temperature_k, heat_w}`：通路上风侧温度、出口流温度、流体焓流增量 `w·(h_out − h_in)`（含换热、轴功和位能）；单通路设备另有无前缀别名（如 `V1.heat_w`）。
- `thermal=False` 时上述热力变量不出现在帧中（目录仍声明，`solver.THERMAL_ONLY_SUFFIXES` 列出这些后缀），端口温度只在压力边界保留给定值，帧的键集合与 0.2 相同。

前端为延续原型，按标称端口方向展示流量：出口读数对规范端口流量取反。额外曲线保留原型 sampleKey（如 `V1:out0:FLOW`）和当前显示单位，同时每帧存储原始 `canonical` 字典。未知或未求解量必须显示为空，不能回退到演示值或零。

## 求解选项与热力诊断

`SolverOptions` 字段（括号内为默认值）：

| 字段 | 含义 |
| --- | --- |
| `pressure_tolerance_pa` (1.0)、`mass_tolerance_kg_s` (1e-8)、`max_iterations` (80) | 水力验收与迭代上限；`mass_tolerance_kg_s` 同时决定热力层的零流量阈值 |
| `dynamic_step_s` (0.1) | 原型动态步长 |
| `thermal` (true) | 开启热力代数层 |
| `property_coupling` (`reference`) | `reference`：水力用参考常数物性，单向；`node`：节点平均物性回到水力，外迭代 |
| `thermal_tolerance_k` (1e-6)、`max_thermal_iterations` (50) | 热力迭代收敛判据与上限 |
| `max_coupling_iterations` (20)、`coupling_density_rtol` (1e-6) | `node` 模式外迭代上限与密度判据 |

`FluidConfig.phase_policy` 可取 `single_phase`（默认）、`liquid`、`gas`、`any`；`any` 供模块代码查询两相状态，网络流动仍由热力层按边界相态检查。

内置管道新增参数 `heat_loss_ua_w_k`（W/K，默认 0，即绝热）和 `ambient_temperature_k`（默认 293.15 K）。v0.3.1 起压力边界 `temperature_k` 与管道 `ambient_temperature_k` 不再写死 274.15–363.15 K，目录只要求不小于 1 K，编译期按项目工质的 `limits()` 检查（见 ALGORITHM“物性服务”）；换热器 `ua_w_k` 已参与计算。

热力诊断：

| 代码 | 级别 | 含义 |
| --- | --- | --- |
| `BOUNDARY_TEMPERATURE_CONFLICT` | 错误（编译） | 同一节点的压力边界温度不同 |
| `NO_FLOW_HEAT` | 错误 | Python 通路零流量却声明 `heat_w` |
| `FLUID_UNKNOWN` | 错误 | 编译期项目工质名称无法识别（`field='fluid'`） |
| `PARAMETER_RANGE` | 错误 | 边界/环境温度、边界压力超出工质 `limits()`；INCOMP 质量分数超出关联式范围 |
| `PHASE_UNSUPPORTED` | 错误 | （编译期，`thermal=True`）水边界不是液相 |
| `REFERENCE_DENSITY_DEVIATION` | 警告 | `reference` 模式下节点密度偏离参考密度超过 2% |
| `TREND_VARIABLE_UNKNOWN` | 错误 | `history='trend'` 时 `trend_variables` 含不存在的变量键 |
| `PHASE_UNSUPPORTED` | 错误 | 节点或出口流进入两相，或进入与边界不同的单相 |
| `THERMAL_REFERENCE_MISSING` | 错误 | 闭合回路没有补给也没有可用温度参考，或焓方程奇异 |
| `THERMAL_NOT_CONVERGED`、`THERMAL_NOT_FINITE` | 错误 | 热力迭代不收敛或解非有限 |
| `THERMAL_ENERGY_IMBALANCE` | 错误 | 能量残差超过相对 1e-6 |
| `COUPLING_NOT_CONVERGED` | 错误 | `node` 模式外迭代不收敛 |
| `THERMAL_REFERENCE_FROM_BOUNDARY` | 警告 | 闭合回路温度参考取自边界，等效热量见 `reference_heat_w` |
| `THERMAL_STAGNANT_NODE` | 提示 | 无流动节点保持边界或初始温度 |
| `THERMAL_EXCHANGER_NO_FLOW` | 提示 | 换热器至少一侧无流量，本次不换热 |
| `THERMAL_NOT_SOLVED` | 警告 | `thermal=False` 时带热力标识的设备未计算换热 |

运行帧指标在热力层开启时另含 `thermal_iterations`、`coupling_iterations`、`energy_residual_w`、`reference_heat_w`。

## 参数与状态

`parameters` 是物理输入；`draft_parameters` 与 `banks` 不自动生效。内置模型的参数上下限不能突破注册约束；Python 模块采用自身 ParameterSpec，返回的 NetworkRelation 另外按关系种类校验物理参数。

压力参考按连通子网络检查，关闭阀门会把水力网络分开。如果一侧没有压力参考，编译失败，避免给不可确定的压力赋值。节点允许未连接的可选分支端口，不把它们当作向外界排水。

型号与版本是可追溯元数据；实际计算只读取快照参数。`scenarios` 目前由规范 API 提交，原型工况 UI 的进一步接入尚未完成；`/projects/validate` 会逐条校验工况覆盖(见 API 文档)，运行与校验共用同一套参数规则；两者报出的工况诊断同源。

## 运行记录与控制

- `RunStatus`:run_id、status(queued/running/completed/failed/cancelled)、mode、progress、frame、total_rows。`progress` 在 completed 为 1;动态运行仅在有 frame 时按 `frame.time_s / duration_s` 估算(运行中 frame 为 null,故仍为 0;取消记录带 frame,可为非零);其余为 0。
- `RunCommand`:action(pause/resume/step/stop/set)、可选 instance_id、parameter_id、value,仍按严格模型校验。只有 pause/resume/stop 被实现;step/set 返回 422 `RUN_COMMAND_UNSUPPORTED`。
- `/api/v1/health` 的 `capabilities` 含 `run_control: true`、`module_versions: true`、`thermal: true` 与 `property_coupling: ["reference","node"]`;`tank_state` 仍为 false;`max_frames`(2001)与 `run_retention`(20)保持不变。
- 取消记录 `frame.status=cancelled`、`valid=false`,`history` 保留取消前已算出的帧;run_id 与请求快照照常保留。stop 会立即写一条 cancelled 事件使轮询立刻结束,求解线程收尾时只在事件尾部不是终态时才追加,因此每次运行恰好一条终态事件;已结束的运行再收到 stop 会被终态检查拒绝(409 RUN_ALREADY_FINISHED)，与首次 stop 并发的第二次也不会追加事件。

## 状态提交边界

- evaluate 使用已提交 state 的深拷贝；修改嵌套试算值不会进入提交状态。模块内部 self/全局变量仍由作者负责保持试算无副作用。
- 每次运行、每个 Python 实例拥有一个 Worker，跨该次动态运行的全部时间步复用，最终 finalize/close。
- t=0 只采样；t>0 的成功步提交一次。非收敛步不提交；失败运行不发布部分有效历史。
- RunFrame 追加 `实例.ctx.var字段` 与 `实例.state.字段`，后者只展开标量；完整嵌套状态由 CommitStepResponse 返回。
- 模块不能通过变量输出覆盖求解器的压力或流量。每条启用通路必须恰好返回一个关系。
- 新建运行会重新 initialize；当前未提供跨 run_id 的状态恢复，服务端 `step`/`set` 也未实现(运行控制只有 pause/resume/stop，见 API 文档)。
