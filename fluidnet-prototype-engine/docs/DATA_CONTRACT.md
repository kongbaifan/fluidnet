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
| `max_step_halvings` (6，0–20) | 含水箱的动态运行中，子步失败后最多减半重试的次数 |
| `hydraulic_method` (`dense`) | `sparse`：按网络拓扑给 `least_squares` 稀疏 Jacobian 结构并用 LSMR，结果与 `dense` 在 1e-6 相对误差内一致；大网络明显更快（见 ALGORITHM） |
| `batch_modules` (true)、`module_parallelism` (1，1–16) | 有 2 个及以上 Python 实例时，实例按轮转分到 `module_parallelism` 个共享 Worker 进程，每次迭代每个 Worker 一次批量 evaluate；实例状态仍各自独立。`batch_modules=false` 恢复每实例一个 Worker |

多工质（v0.4.5）：`Project.circuit_fluids` 是 `CircuitFluid` 列表（`id`、`anchor: Endpoint`、`fluid: FluidConfig`）。回路是经连接、节点/水箱和启用的内部通路连通的端口集合；拓扑决定，不看阀门开关，所以关阀不分隔回路，换热器两侧是两个回路。锚点所在回路用该工质，其余回路用 `Project.fluid`。诊断：`CIRCUIT_ANCHOR_UNKNOWN`（锚点端口不存在）、`FLUID_CONFLICT`（同一回路指定了不同工质；指定相同工质不算冲突）、`MULTIPLE_FLUIDS`（提示，项目确有多种工质）。所有回路工质相同时（如 `Water` 与 `HEOS::Water`）按单工质计算，结果与不设 `circuit_fluids` 逐键一致。`/projects/validate` 的响应新增 `circuits`（`id`、`fluid`、`source`=回路工质 id 或 `project`、`ports`）。原型项目的 `circuitFluids`（`id`、`anchor`、`medium` 或 `fluid`、`fluidReference`）映射到这里。Worker 初始化请求新增 `port_fluids`：跨两个回路的 Python 模块里，`ctx.fluid` 是第一个端口所在回路的工质，`ctx.fluid_at(端口)` 给每个端口自己的工质。

`FluidConfig.fluid` 可写 `REFPROP::` 前缀（v0.4.4，见 ALGORITHM“物性服务”）；`FluidConfig.reference`（`mass` 默认 / `mole`）决定 `A[x]&B[y]` 中比例的含义，FluidState.composition 按同一基准返回组分。原型项目的 `fluid`（非空时替代 `medium`）与 `fluidReference` 映射到这两个字段。`/api/v1/health` 的 `capabilities.refprop.installed` 只检查文件是否存在，不加载 DLL。

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

水箱与时间推进诊断（v0.4）：

| 代码 | 级别 | 含义 |
| --- | --- | --- |
| `STORAGE_CONFLICT` | 错误（编译） | 水箱与压力边界或另一个水箱在同一节点 |
| `PARAMETER_RANGE` | 错误（编译） | 水箱初始液位超过罐高，或温度超出工质范围 |
| `PHASE_UNSUPPORTED` | 错误（编译） | 水箱初始状态不是液相 |
| `TANK_EMPTY`、`TANK_FULL` | 错误（运行） | 液位到达 0 或罐高；history 保留到事件时刻 |
| `STEP_NOT_CONVERGED` | 错误（运行） | 子步减半 `max_step_halvings` 次仍未收敛；history 保留已接受帧 |
| `DYNAMIC_IMPLICIT_EULER` | 提示 | 含水箱的动态运行，一阶隐式 Euler，未做时间误差控制 |
| `STEADY_TANK_AS_RESERVOIR` | 提示 | 稳态把水箱当作液位不变的大容器 |

水箱帧变量为 `<实例>.state.level_m`、`mass_kg`、`volume_m3`、`temperature_k`、`net_inflow_kg_s`（稳态与每个动态帧都有）；含水箱的帧指标另含 `storage_mass_rate_kg_s`，热力层开启时还有 `storage_power_w`。

管道热容（v0.4.1）：内置管道参数 `thermal_cells`（整数 0–50，非整数报 `PARAMETER_INVALID`）、`wall_heat_capacity_j_k`（J/K）。`thermal_cells > 0` 且热力层开启时，帧里另有 `<实例>.state.mean_temperature_k` 与 `<实例>.state.stored_power_w`，并计入 `storage_power_w`；其他情况下不输出（目录中这两个变量是条件变量）。`thermal_cells=0` 的项目结果与 0.4.0 相同，只多出这两个参数的 `<实例>.param.*` 键。

PID 控制器（v0.4.2）：`Project.controllers` 是 `PIDController` 列表，不是画布模块，没有流体端口。

| 字段 | 含义 |
| --- | --- |
| `id` | 控制器 ID，项目内唯一 |
| `measurement` | 反馈变量的完整路径，如 `T1.state.level_m`；必须是该设备模块声明的可采样变量（不能是 `param.*`），否则编译报 `PID_MEASUREMENT_UNKNOWN`；条件变量（如 `thermal_cells=0` 的管道状态）在第 0 帧取不到有限数值时运行失败，`PID_MEASUREMENT_INVALID` |
| `instance_id`、`parameter_id` | 执行参数；必须是 `runtime=true` 的可写数值参数，否则编译报 `PARAMETER_NOT_RUNTIME`；同一参数只能绑定一个控制器 |
| `setpoint`、`kp`、`ki`（1/s）、`kd`（s） | 并联式 PID，u = kp·e + ∫ki·e dt + kd·d(−y)/dt，e = setpoint − y |
| `sample_s` (0.1，0–60] | 采样周期 |
| `minimum`、`maximum` | 输出限幅，必须在目标参数的目录范围内，否则 `PID_TARGET_INVALID` |
| `mode` (`auto`)、`manual_output` | 手动时输出 `manual_output`（缺省保持当前值），切换无扰 |

帧变量 `controller.<id>.measurement`、`setpoint`、`output`、`integral`、`mode`（字符串）。控制器的目标、限幅和反馈变量在编译期检查，`/projects/validate` 与运行报出同一诊断。

运行中被动管段的隔离（v0.4.2）：运行中阀门开度改为 0 后，没有压力参考的子网络如果只含管道、阀门、阻力和换热器，取一个节点保持上一接受步的压力和温度，流量为零，诊断 `ISOLATED_PRESSURE_HELD`（提示）；子网络含泵或 Python 模块（管道、阀门、阻力、换热器以外的支路）时报 `ISOLATED_ACTIVE_NETWORK`。含水箱的子网络由水箱定压，不算隔离。编译期就没有压力参考的子网络仍报 `PRESSURE_REFERENCE_MISSING`。

## 参数与状态

`parameters` 是物理输入；`draft_parameters` 与 `banks` 不自动生效。内置模型的参数上下限不能突破注册约束；Python 模块采用自身 ParameterSpec，返回的 NetworkRelation 另外按关系种类校验物理参数。

压力参考按连通子网络检查，关闭阀门会把水力网络分开。如果一侧没有压力参考，编译失败，避免给不可确定的压力赋值。节点允许未连接的可选分支端口，不把它们当作向外界排水。

型号与版本是可追溯元数据；实际计算只读取快照参数。`scenarios` 目前由规范 API 提交，原型工况 UI 的进一步接入尚未完成；`/projects/validate` 会逐条校验工况覆盖(见 API 文档)，运行与校验共用同一套参数规则；两者报出的工况诊断同源。

## 运行记录与控制

- `RunRequest` v0.4.2 新增 `execution_mode`（`fast`/`realtime`）、`speed_ratio`（0–100]、`start_paused`；v0.4.3 起 `duration_s` 可为 null（后台持续运行，steady 不允许），新增 `history_window`（10–20001，默认 2001）。`RunFrame.sequence` 是绝对帧序号，与 history 的 offset 一致。
- `RunHistoryResponse` v0.4.3 新增 `first_offset`、`truncated`；新增 `RunOverviewResponse`（rows、stride、total_rows）。
- `RunStatus`:run_id、status(queued/running/paused/completed/failed/cancelled/interrupted；`stopping` 未使用)、mode、progress、frame、total_rows、lag_s，命令响应另带 command_id、command_status(accepted/applied/rejected)、applied_time_s、message。`progress` 在 completed 为 1，动态运行按 `frame.time_s / duration_s` 估算。
- `RunCommand`:action(pause/resume/step/stop/set/controller)、可选 command_id(1–96 位字母数字、`_`、`-`)、instance_id、parameter_id、value、controller_id。`RunEvent` 对命令另带 command_id、command_status、message、command 和 parameter_revision。
- `RunFrame` v0.4.2 新增 `sequence`（帧序号）与 `parameter_revision`（该帧计算时运行参数和控制器设定已被修改的次数，0 为未改）。
- `/api/v1/health` 的 `capabilities` 含 `run_control`、`module_versions`、`thermal`、`property_coupling: ["reference","node"]`、`tank_state`、`time_integration: "implicit_euler"`；v0.4.2 起 `live_runs`、`pid`、`runtime_parameters`、`continuous_step` 为 true；v0.4.3 起 `continuous_runs` 为 true，另报 `history_window_max`(20001)、`overview_points`(2000)；`max_frames`(2001，指同步运行)与 `run_retention`(20)不变。
- 取消记录 `frame.status=cancelled`、`valid=false`,`history` 保留取消前已算出的帧;每次运行恰好一条终态事件；已结束的运行再收到命令返回 409 `RUN_ALREADY_FINISHED`。
- 运行中的 `set` 只改本次会话的参数，请求快照（`request.project`）保持提交时的值；修改历史以命令事件为准。

## 状态提交边界

- evaluate 使用已提交 state 的深拷贝；修改嵌套试算值不会进入提交状态。模块内部 self/全局变量仍由作者负责保持试算无副作用。
- 每次运行的 Python 实例在该次运行内复用 Worker（默认 `batch_modules` 时多个实例按分片共用进程，各自的上下文与状态独立），最终 finalize/close。运行中 `set` 修改 Python 参数时，Worker 内该实例的参数同步更新，不重新 initialize。
- t=0 只采样；t>0 的成功步提交一次。含水箱的运行按被接受的子步提交（一帧可有多次，`dt_s` 为子步长），帧上是该帧最后一次提交的变量。非收敛步不提交；编译或求解失败的运行不发布部分历史，只有 `TANK_EMPTY`、`TANK_FULL`、`STEP_NOT_CONVERGED` 例外：history 保留已接受帧。
- RunFrame 追加 `实例.ctx.var字段` 与 `实例.state.字段`，后者只展开标量；完整嵌套状态由 CommitStepResponse 返回。
- 模块不能通过变量输出覆盖求解器的压力或流量。每条启用通路必须恰好返回一个关系。
- 新建运行会重新 initialize；同一后台运行内的 step、set、pause/resume 不会。当前未提供跨 run_id 或跨服务重启的状态恢复。
