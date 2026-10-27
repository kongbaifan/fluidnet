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
| `SavedProjectRunRequest` | revision?, mode, duration_s, dt_s, scenario_id, selected_variables, history, trend_variables | 按路径项目 ID 启动已保存文档，服务端归一化并固定实际修订；运行选项与 `RunRequest` 共用 `RunOptions` |
| `ThermalCoupling` | id, fluid_instance_id, fluid_channel_id, refrigerant_vessel_id, ua_w_k | `Project.thermal_couplings` 内的浸没盘管合同，首版最多一条，UA ≥ 0；两侧压力/质量网络分离，只交换热量，详见 [热耦合说明](THERMAL_COUPLING.md) |
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

`source` 支持 runtime/header 文本和 design 文本。Python 模块的 `source.design` 必须是单个 `design.py` 文本，可经 `POST /modules/design` 执行；内置模型原型中的三份 design 文本数组只作定义资料保存，不执行。`state_model`、`thermal_model` 是扩展标识，不代表对应功能已经实现。内置未知水力模型和水箱状态模型明确拒绝；Python 模块可声明 generic，必须在 evaluate 为每条启用通路返回有效 SDK 关系。内置换热器的 `epsilon_ntu` 已由热力层计算；只有 `thermal=False` 时才产生 `THERMAL_NOT_SOLVED` 警告。

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

多工质（v0.4.5）：`Project.circuit_fluids` 是 `CircuitFluid` 列表（`id`、`anchor: Endpoint`、`fluid: FluidConfig`）。回路是经连接、节点/水箱和启用的内部通路连通的端口集合；拓扑决定，不看阀门开关，所以关阀不分隔回路，换热器两侧是两个回路。锚点所在回路用该工质，其余回路用 `Project.fluid`。诊断：`CIRCUIT_ANCHOR_UNKNOWN`（锚点端口不存在）、`FLUID_CONFLICT`（同一回路指定了不同工质；指定相同工质不算冲突）、`MULTIPLE_FLUIDS`（提示，有回路工质不同于项目工质或彼此不同）。所有回路工质都与 `Project.fluid` 相同时（如 `Water` 与 `HEOS::Water`）按单工质计算，结果与不设 `circuit_fluids` 逐键一致。`/projects/validate` 的响应新增 `circuits`（`id`、`fluid`、`source`=回路工质 id 或 `project`、`ports`）。原型项目的 `circuitFluids`（`id`、`anchor`、`medium` 或 `fluid`、`fluidReference`）映射到这里。Worker 初始化请求新增 `port_fluids`：跨两个回路的 Python 模块里，`ctx.fluid` 是第一个端口所在回路的工质，`ctx.fluid_at(端口)` 给每个端口自己的工质。

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

## 冷库 A1 热执行域（2026-10-20）

冷库案例引入与流体网络并列的**热执行域（`execution_domain='thermal'`）**：项目里被使用的模块只要含 `domain=thermal` 端口，`compile_project` 就走热编译分支，不建立压力节点、不求解质量流量；其余项目仍走既有水力/热力层路径，行为不变。

A1 只有两台内置设备：

| 设备 | 参数（规范单位） | 状态与派生变量 |
| --- | --- | --- |
| `cold_room` 库房热节点 | `temperature_k` 初始库温（K）、`heat_capacity_j_k` 等效热容（J/K）、`ambient_temperature_k` 室外温度、`ground_temperature_k` 地面温度、`wall_ua_w_k` / `roof_ua_w_k` / `floor_ua_w_k` 围护 UA（W/K）、`heat_input_w` 附加热负荷（W，runtime） | `state.temperature_k`、`envelope_heat_w`、`stored_energy_j`（相对 273.15 K）、`state.external_energy_j`、`cooling_power_w` |
| `ideal_cold_source` 理想恒容量冷源 | `cooling_power_w` 额定冷却功率（W，runtime）、`capacity_ratio` 容量比例（0–1，runtime） | `cooling_power_w`（实际输出）、`state.cooling_energy_j` |

- 端口：两台设备各有一个 `domain=thermal` 的 `heat` 端口（库房 `in`、冷源 `out`，`required=true`、`circuit='thermal'`）。热连接必须一对一、方向相反；未连接端口报 `THERMAL_CONNECTION_MISSING`，重复/反向/自连报 `THERMAL_CONNECTION_INVALID`。
- 模型合同：热设备的 `solver_model`、`state_model`、端口和参数声明由内置 `thermal_catalog()` 固定；项目只能改参数默认值，改动类型、单位、runtime/writable 或上下限报 `THERMAL_PARAMETER_CONTRACT`。混入流体设备、Python 运行模块或改动端口定义分别报 `THERMAL_MODEL_UNSUPPORTED` / `THERMAL_PORT_INVALID` / `THERMAL_TOPOLOGY_UNSUPPORTED`。项目若配置 `circuit_fluids` 也报 `THERMAL_TOPOLOGY_UNSUPPORTED`。
- 求解开关：热项目必须 `SolverOptions.thermal=true`，否则报 `THERMAL_REQUIRED`；带 PID 或 Python 控制脚本的项目只能动态运行（`CONTROL_DYNAMIC_REQUIRED`），稳态只返回一个热平衡帧，无 UA 参考时报 `THERMAL_STEADY_UNDEFINED`。
- 帧变量：两台设备的 `param.*` 与上表状态/派生变量进入同一 RunFrame，另有 PID/脚本变量；指标含 `energy_residual_j`、`energy_residual_w`、`storage_power_w`。每帧带提示 `COLD_ROOM_IDEAL_SOURCE`，说明尚未计算货物热状态、制冷循环、电功率或 COP。
- 单位：原型设备面板按显示单位编辑（温度 °C、功率 kW、等效热容 kJ/K），归一化按 `UnitSpec` 换算为 K/W/J；帧变量保留规范单位。热项目的 `dynamic_step_s` 归一化后不超过 10 s，导入诊断用 `THERMAL_SCOPE`。
- 会话与接口：`sessions.create_session` 按 `execution_domain` 选择 `ThermalSession` 或 `SimulationSession`；同步运行、后台运行、控制预览、变量写入、命令、历史、归档、备份和重启读取对两种执行域使用同一响应模型。
- 能力上报：`GET /api/v1/health` 的 `supported_domains` 增加 `thermal`，`capabilities.cold_room_ideal_source=true`；`GET /api/v1/examples/cold-storage` 返回 A1 种子项目（2 h、30 s 发布、10 s 内部步长）。
- 诊断码：`THERMAL_CONNECTION_MISSING`、`THERMAL_CONNECTION_INVALID`、`THERMAL_PORT_INVALID`、`THERMAL_MODEL_UNSUPPORTED`、`THERMAL_PARAMETER_CONTRACT`、`THERMAL_TOPOLOGY_UNSUPPORTED`、`THERMAL_REQUIRED`、`THERMAL_STEADY_UNDEFINED`、`THERMAL_STEP_INVALID`、`THERMAL_STATE_RANGE`（运行错误）、`COLD_ROOM_IDEAL_SOURCE`（提示）。
- 已知边界：A1 只支持单库房 + 理想冷源的一对一热拓扑，不混合流体与热端口，不含货物热节点、冷风机、制冷循环、融霜和电量；这些在 A2–A4 按案例计划扩展。

## 冷库 A 单库房案例（2026-10-21）

执行域 `execution_domain='cold_store'`：项目里使用了下表任一设备时，`compile_project` 走 `refrigeration/cold_store.py`，只允许这三类设备组成的“机组 → 冷风机 → 库房”链（可多条）。混入流体设备、A1 理想冷源、制冷站设备或 Python 模块报 `COLD_STORE_MODEL_UNSUPPORTED`。方程见 [ALGORITHM](ALGORITHM.md#冷库-a-单库房与单级循环2026-10-21执行域-cold_store)。

| 设备 | 端口（thermal） | runtime 参数 | 主要输出 |
| --- | --- | --- | --- |
| `storage_room` 冻结物库房 | `heat` 入 | `setpoint_temperature_k`、`hysteresis_k`、`alarm_temperature_k`、`ambient_temperature_k`、`ground_temperature_k`、`lighting_on`、`heat_input_w` | `state.temperature_k`、`state.goods_temperature_k`、`state.goods_mass_kg`、各项热流（`envelope/door/lighting/goods/fan/defrost_heat_w`、`cooling_power_w`、`net_heat_w`）、`stored_energy_j`、累计 `state.external/goods/cooling/lighting_energy_j`、超温 `state.time_above_alarm_s`、`state.degree_hours_above_alarm`、保温期 `state.service_*`、`state.pulldown_time_s`、`state.max/min_service_temperature_k` |
| `unit_cooler` 冷风机 | `supply` 入、`heat` 出 | `fan_continuous` | `state.mode`（0 制冷 / 1 融霜加热 / 2 滴水）、`state.fan_running`、`refrigerant_heat_w`、`fan_power_w`、`heater_power_w`、`state.defrost_count`、`state.defrost_pending`、累计 `state.fan/heater_energy_j` |
| `condensing_unit` 单级制冷机组 | `cold` 出 | `run_request`、`capacity_ratio`、`variable_capacity`、`ambient_temperature_k` | `state.running`、`actual_capacity_ratio`、`state.starts`、`state.run_time_s`、`state.state_elapsed_s`、`state.switch_blocked`、蒸发/冷凝温度与压力、吸排气温度、压比、质量流量、制冷量、轴功率、电功率、冷凝排热、冷凝风机功率、`cop`、`system_cop`、`state1…4.{pressure_pa,temperature_k,enthalpy_j_kg,entropy_j_kg_k,quality}`、`displacement_m3_s`、`condenser_ua_w_k`、累计 `state.electric/condenser_fan/cooling_energy_j`、`state.condenser_heat_j` |

- 机组停机时温度、压力、状态点与 COP 为 `null`，功率与流量为 0。启停与布尔类请求用 0/1 数值参数（≥ 0.5 为真）。
- 制冷剂取 `Project.fluid`；配置 `circuit_fluids` 报 `COLD_STORE_TOPOLOGY`。额定点不能饱和（如水）报 `CYCLE_DESIGN_INVALID`。
- 负荷日程：`Project.events: list[ScheduleEvent]`（≤ 500），字段 `id`、`type`、`time_s`、可选 `instance_id`，按类型必填且只能填：`door_heat`（`duration_s`、`heat_w`，区间 `[t, t+duration)`）、`goods_addition`（`mass_kg`、`temperature_k`）、`ambient_temperature`（`temperature_k`，写所有库房与机组的室外温度）、`electric_defrost`（无数值，按冷风机参数）。`Scenario.events` 为 `null` 时沿用项目日程，为列表（含空列表）时替换。原型导出的 `projects[].events` 与 `scenarios[].events` 使用规范单位。
- 日程校验：ID 重复或入库货温超出冻结模型 `SCHEDULE_EVENT_INVALID`；目标不存在、类型不符或多台候选未指定 `SCHEDULE_EVENT_TARGET`；室外温度目标已被 PID/脚本控制 `SCHEDULE_EVENT_CONFLICT`；非冷库项目带日程 `SCHEDULE_UNSUPPORTED`。工况日程在 `/projects/validate` 中按合并后的参数校验。运行时超出时长的事件给 `SCHEDULE_EVENT_AFTER_RUN`，每次执行给 `SCHEDULE_EVENT`，重叠融霜请求给 `DEFROST_REQUEST_IGNORED`。
- 运行诊断：`REFRIGERATION_ENVELOPE`（带 `field`）、`GOODS_TEMPERATURE_RANGE`、`THERMAL_STATE_RANGE`、`COLD_STORE_NOT_CONVERGED`、`CYCLE_*` 物性/相态码；警告 `CYCLE_SUPERHEAT_APPROACH`、`COLD_ROOM_CAPACITY_SHORTFALL`；提示 `COLD_STORE_MODEL`。稳态请求 `COLD_STORE_DYNAMIC_REQUIRED`。
- 帧指标：`energy_residual_j/_w`、`storage_power_w`、`electric_power_w`、`lighting_power_w`、`coupling_residual_w`、`events_applied`。
- 趋势历史：冷库会话的标准曲线变量（`refrigeration/report.py::series_keys`）在所有趋势帧上保留，报告与 CSV 不依赖前端传入的 `trend_variables`。
- 接口：`GET /api/v1/examples/cold-storage-room`（案例种子项目，含 8 个工况）；`POST /api/v1/cold-store/workpoint`（`UnitWorkpointRequest` → `UnitWorkpointResponse`，与运行同一循环函数，越界作为警告返回）；`GET /api/v1/runs/{id}/report.html`、`/report.csv`、`GET /api/v1/runs/compare/report.html?a=&b=`（结束后可用；非冷库运行 `REPORT_UNSUPPORTED`；历史窗口不含全部帧时曲线改用抽稀概览并在报告中注明）。health `capabilities.cold_store_cycle=true`。
- 已知边界：单级准稳态循环；不计制冷剂管路压降与存量动态、冻结潜热、湿度与结霜、融霜完成程度；参数为工程示范假设。
- `set_variable` 事件（2026-10-21，冷库与制冷站共用）：`key` 为 `<设备>.param.<运行参数>` 或 `controller.<PID>.setpoint|manual_output`，`value` 为数值；按与外部命令相同的整批写入执行（增加 `parameter_revision`）。编译时检查：目标不可写 `SCHEDULE_EVENT_TARGET` / `PARAMETER_NOT_RUNTIME`，越界 `SCHEDULE_EVENT_INVALID`，已被 PID 或启用脚本控制 `SCHEDULE_EVENT_CONFLICT`。制冷站项目只接受 `set_variable`，其他类型 `SCHEDULE_UNSUPPORTED`。

## 冷库 B 制冷站设备（2026-10-20，设备层）

`Domain` 增加 `refrigerant`（集总制冷站物流，不是管网压力节点）。`builtin_catalog()` 增加 10 台内置设备，分类“制冷站设备”，由 `refrigeration_catalog()` 固定，方程见 [ALGORITHM](ALGORITHM.md#冷库-b-集总制冷站设备2026-10-20设备层)。

| 设备 | 端口 | runtime 参数 | 主要输出 |
| --- | --- | --- | --- |
| `hp_receiver` 高压贮液器 / `lp_drum` 低压循环桶 / `pumped_drum` 泵供液储液器（同一 `saturated_vessel` 模型，默认值不同） | `in0`、`in1`（入）、`vapor`、`liquid`（出）；必连端口按角色不同，其余可选 | — | `state.pressure_pa/temperature_k/mass_kg/internal_energy_j/liquid_mass_kg/vapor_mass_kg/quality/level_ratio/level_m`、`liquid_enthalpy_j_kg`、`vapor_enthalpy_j_kg`、`net_inflow_kg_s` |
| `refrigerant_compressor` 压缩机 | `suction` 入、`discharge` 出 | `running`、`load_ratio` | `mass_flow_kg_s`、`shaft_power_w`、`electric_power_w`、`discharge_temperature_k`、`pressure_ratio` |
| `evaporative_condenser` 蒸发式冷凝器 | `in0`、`out0` | `fan_ratio`、`wet_bulb_temperature_k`、`return_gas_ratio` | `heat_rejection_w`、`effective_ua_w_k`、`condensing_temperature_k`、`fan_power_w` |
| `expansion_valve` 电磁节流阀 | `in0`、`out0` | `opening_ratio` | `mass_flow_kg_s`、`pressure_drop_pa`、`outlet_quality` |
| `cascade_exchanger` 复叠换热器 | `evap_in/evap_out`（回路 `evaporating`）、`cond_in/cond_out`（回路 `condensing`） | — | `heat_w`、`approach_k`、`evaporated_kg_s`、`condensed_kg_s` |
| `refrigerant_pump` 制冷剂液泵 | `in0`、`out0` | `running`、`speed_ratio`（0–1.2） | `mass_flow_kg_s`、`pressure_rise_pa`、`electric_power_w` |
| `air_cooler` 冷风机 | `in0`、`out0`（refrigerant）、`heat`（thermal 出，接 `cold_room.heat`） | `running`、`fan_ratio`、`supply_valve_ratio` | `refrigerant_heat_w`、`room_cooling_w`、`fan_power_w`、`supply_mass_flow_kg_s`、`outlet_quality`、`evaporating_temperature_k` |
| `refrigerant_header` 制冷剂集管 | `in0–in3`、`out0–out3`，均可选 | — | — |

- 启停类执行器用 0/1 数值参数（≥ 0.5 为运行），不扩展布尔类型；每台设备的 `param.*` 变量与其他内置设备一致。
- 单位：排量规范单位 m³/s（显示 m³/h），压力 Pa（容器显示 MPa），UA W/K（显示 kW/K），温度 K（显示 °C）。
- 原型归一化：这些设备在原型里直接使用规范参数 ID；端口未写 `required`/`circuit` 时按注册定义取值（此前非节点设备一律视为必连）。
- 累计量：压缩机与液泵 `state.electric_energy_j`，冷凝器 `state.heat_rejected_j`、`state.fan_energy_j`，冷风机 `state.cooling_energy_j`（库房净冷量）、`state.fan_energy_j`；库房沿用 `state.external_energy_j`。容器另有 `liquid_density_kg_m3`、`vapor_density_kg_m3`。
- 执行域：含 `refrigerant` 端口的项目 `execution_domain='refrigeration'`，由 `StationSession` 运行；拓扑规则与时间推进见 [ALGORITHM](ALGORITHM.md#制冷站系统层refrigerationstationpy执行域-refrigeration)。回路工质用 `circuit_fluids` 指定，锚点为任一已连接的制冷剂端口；`/projects/validate` 的 `circuits` 按制冷剂回路列出端口。
- 帧指标：`energy_residual_j`、`energy_residual_w`、`storage_power_w`、`electric_power_w`、`mass_residual_kg_circuit<i>`；每帧带提示 `REFRIGERATION_STATION`。
- 能力上报：`supported_domains` 增加 `refrigerant`，`capabilities.refrigeration_station=true`。
- 诊断码（编译）：`REFRIGERATION_MODEL_UNSUPPORTED`、`REFRIGERATION_PORT_INVALID`、`REFRIGERATION_PARAMETER_CONTRACT`、`REFRIGERATION_CONNECTION_INVALID`、`REFRIGERATION_CONNECTION_MISSING`、`REFRIGERATION_VESSEL_SHORT`、`REFRIGERATION_PORT_ROLE`、`REFRIGERATION_LEVEL_VESSELS`、`REFRIGERATION_LEVEL_NO_VESSEL`、`REFRIGERATION_BRIDGE_SAME_LEVEL`、`REFRIGERATION_CASCADE_CIRCUIT`、`REFRIGERATION_COIL_SUPPLY`、`VESSEL_INITIAL_STATE`、`REFRIGERATION_DYNAMIC_REQUIRED`（稳态请求）；（运行）`VESSEL_LEVEL_RANGE`、`VESSEL_PHASE_RANGE`、`COMPRESSOR_PRESSURE_RATIO`、`REFRIGERATION_NOT_CONVERGED` 及物性错误码；`COMPRESSOR_ENVELOPE`（警告）。
- 分层控制案例（2026-10-21）：`GET /api/v1/examples/cold-storage-nh3co2` 返回 `station_case()`（5 个 PID、上层脚本、B-S01～B-S04 四个工况）；帧变量 `script.control.state.{running,satisfaction,starts,stops,fan_changes,reason,infeasible}`；帧指标增加 `events_applied`。`/runs/{id}/report.html`、`/report.csv` 支持制冷站运行（标准曲线变量在所有趋势帧保留）；对照报告仍只支持冷库 A。
- 已知边界：不计管路压降、换热器持液与过冷/过热、油冷却；不含双级、乙二醇与融霜回路。

## 参数与状态

`parameters` 是物理输入；`draft_parameters` 与 `banks` 不自动生效。内置模型的参数上下限不能突破注册约束；Python 模块采用自身 ParameterSpec，返回的 NetworkRelation 另外按关系种类校验物理参数。

压力参考按连通子网络检查，关闭阀门会把水力网络分开。如果一侧没有压力参考，编译失败，避免给不可确定的压力赋值。节点允许未连接的可选分支端口，不把它们当作向外界排水。

型号与版本是可追溯元数据；实际计算只读取快照参数。原型工况 UI 已接通新建、复制、编辑、选择与保存；原型 `scenarios[].overrides` 使用显示单位，归一化时转换成规范参数，`activeScenarioId` 形成运行请求的 `scenario_id`。`/projects/validate` 会逐条校验工况覆盖(见 API 文档)，运行与校验共用同一套参数规则；两者报出的工况诊断同源。

## 运行记录与控制

- v0.4.6：`RunCommand.action` 新增 `write`，配 `values`（帧变量键 → 值，最多 256 个）；新增 `VariableWrite`（values、command_id、wait_s 0–10）与 `VariableValues`（run_id、status、time_s、sequence、parameter_revision、values）；新诊断 `VARIABLE_NOT_WRITABLE`、`VARIABLE_WRITE_EMPTY`、`VARIABLE_UNKNOWN`、`NO_FRAME`、`AUTH_REQUIRED`、`AUTH_SCOPE`。`PARAMETER_CONTROLLED` 改为：被 PID 绑定的参数在手动模式下也不能直接写（`set` 的行为不变，仍只在自动模式下拒绝）。
- `RunRequest` v0.4.2 新增 `execution_mode`（`fast`/`realtime`）、`speed_ratio`（0–100]、`start_paused`；v0.4.3 起 `duration_s` 可为 null（后台持续运行，steady 不允许），新增 `history_window`（10–20001，默认 2001）。`RunFrame.sequence` 是绝对帧序号，与 history 的 offset 一致。
- `RunHistoryResponse` v0.4.3 新增 `first_offset`、`truncated`；新增 `RunOverviewResponse`（rows、stride、total_rows）。
- `RunStatus`:run_id、status(queued/running/paused/completed/failed/cancelled/interrupted；`stopping` 未使用)、mode、progress、frame、total_rows、lag_s，命令响应另带 command_id、command_status(accepted/applied/rejected)、applied_time_s、message。`progress` 在 completed 为 1，动态运行按 `frame.time_s / duration_s` 估算。
- `RunCommand`:action(pause/resume/step/stop/set/controller)、可选 command_id(1–96 位字母数字、`_`、`-`)、instance_id、parameter_id、value、controller_id。`RunEvent` 对命令另带 command_id、command_status、message、command 和 parameter_revision。
- `RunFrame` v0.4.2 新增 `sequence`（帧序号）与 `parameter_revision`（该帧计算时运行参数和控制器设定已被修改的次数，0 为未改）。
- `/api/v1/health` 的 `capabilities` 含 `run_control`、`module_versions`、`thermal`、`property_coupling: ["reference","node"]`、`tank_state`、`time_integration: "implicit_euler"`；v0.4.2 起 `live_runs`、`pid`、`runtime_parameters`、`continuous_step` 为 true；v0.4.3 起 `continuous_runs` 为 true，另报 `history_window_max`(20001)、`overview_points`(2000)；`max_frames`(2001，指同步运行)与 `run_retention`(20)不变。冷库 A1（2026-10-20）起顶层 `supported_domains` 为 `["fluid","thermal"]`，`capabilities.cold_room_ideal_source` 为 true。
- 取消记录 `frame.status=cancelled`、`valid=false`,`history` 保留取消前已算出的帧;每次运行恰好一条终态事件；已结束的运行再收到命令返回 409 `RUN_ALREADY_FINISHED`。
- 运行中的 `set` 只改本次会话的参数，请求快照（`request.project`）保持提交时的值；修改历史以命令事件为准。

## 状态提交边界

- evaluate 使用已提交 state 的深拷贝；修改嵌套试算值不会进入提交状态。模块内部 self/全局变量仍由作者负责保持试算无副作用。
- 每次运行的 Python 实例在该次运行内复用 Worker（默认 `batch_modules` 时多个实例按分片共用进程，各自的上下文与状态独立），最终 finalize/close。运行中 `set` 修改 Python 参数时，Worker 内该实例的参数同步更新，不重新 initialize。
- t=0 只采样；t>0 的成功步提交一次。含水箱的运行按被接受的子步提交（一帧可有多次，`dt_s` 为子步长），帧上是该帧最后一次提交的变量。非收敛步不提交；编译或求解失败的运行不发布部分历史，只有 `TANK_EMPTY`、`TANK_FULL`、`STEP_NOT_CONVERGED` 例外：history 保留已接受帧。
- RunFrame 追加 `实例.ctx.var字段` 与 `实例.state.字段`，后者只展开标量；完整嵌套状态由 CommitStepResponse 返回。
- 模块不能通过变量输出覆盖求解器的压力或流量。每条启用通路必须恰好返回一个关系。
- 新建运行会重新 initialize；同一后台运行内的 step、set、pause/resume 不会。当前未提供跨 run_id 或跨服务重启的状态恢复。

## Python 控制与工作区归档补充

`Project.control_scripts` 保存 Python 脚本快照（id、language、source、content_hash、enabled、sample_s、inputs、outputs、timeout_s），与设备模块和 PID 分开；原型字段为 control/controlLanguage/controlEnabled/controlInputs/controlOutputs/controlConfig，适配器形成 controlScripts 后归一化。旧版文本标为 legacy 且禁用。

控制输出使用运行变量的规范键：设备 `<id>.param.<parameter>` 或 `controller.<id>.setpoint|mode|manual_output`。输入必须存在于初始接受帧且已声明；不做显示单位换算。首次 step 的 dt_s=0，其后按仿真时间；采样输出对下一子步生效，接受后提交 ctx.state，数值重试不重复采样。脚本状态与计数由 `script.<id>.*` 帧变量暴露，运行快照固定源码哈希。受管理 state 是最多 64 KiB 的有限 JSON 字典；全局 Python 变量和外部副作用不属于事务状态。

工作区以完整 schema=1 原型文档存储，独立于规范 Project；保存修订号覆盖全部项目、模块草稿、型号、关联快照等。SQLite 事务成功才确认 revision/saved_at，最近 5 个修订可读。RunRecordResponse 的 persisted_at/persisted_rows 标明最后确认的归档边界；重启保留项目与历史，并将未结束运行标为 interrupted，不恢复内存会话继续推进。窗口、全程抽稀与终态保留数见 API 文档。

数据库版本 2 增加独立项目历史，每个项目保留最近 5 个修订；版本 1 自动从最新工作区建立项目初始修订。单项目交换格式为 `fluidnet-project`、schema=1，包含原型 project、modules、models 和 charts。项目保存按该项目的 expected_revision 检测冲突，并与完整工作区修订在同一事务中提交。工作区响应新增 `project_revisions`；运行请求新增可选 `project_revision`，用于标记当时已保存的项目修订。
