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
| `ModuleInstance` | id, module_id, parameters, draft_parameters, banks, model_id, model_version | 已应用参数、草稿、参数库值及型号引用 |
| `Connection` | id, source, target | 两个 Endpoint(instance_id, port_id) 的物理连接 |
| `Scenario` | id, name, overrides | 按实例 ID 提供规范参数覆盖；本次运行使用副本 |
| `Project` | modules, instances, connections, scenarios, selected_variables, solver | 一次可独立计算和复现的项目 |
| `RunRequest` | project, mode, duration_s, dt_s, scenario_id, selected_variables | 创建一次运行；变量选择不影响物理求解 |
| `RunFrame` | status, valid, time_s, variables, diagnostics, metrics | 一个时刻的结果与质量证据 |
| `FluidConfig` | backend, fluid, composition, phase_policy | 物性服务选择和单相约束 |
| `ModulePackageRef` | module_id, version, content_hash | 项目运行锁定的模块版本 |
| `PortState` | pressure, temperature, enthalpy, density, viscosity, flow | Worker 试算和收敛后的端口状态 |
| `NetworkRelation` | relation_id, kind, channel, parameters | 模块向平台注册的设备关系 |
| `EvaluateRequest/Response` | trial_ports, readonly_state / relations, variables | 无副作用的数值试算协议 |
| `CommitStepRequest/Response` | converged_ports, dt / state | 收敛时间步的状态提交协议 |

`source` 支持 runtime/header 文本和 design 文本数组，作为定义资料保存。`state_model`、`thermal_model` 是扩展标识，不代表对应功能已经实现。未知水力模型直接拒绝，水箱状态模型也明确拒绝；当前换热器的热力标识产生未求解警告。

模块包的 `manifest.json` 与源码构成可追踪单元；`content_hash` 不一致时，模块校验和项目编译都会拒绝执行。当前提供的 `modules/programmable_valve` 是首个可执行示例。

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

体积流量是派生量：`Q_m3_h = m_kg_s / rho × 3600`。水力回归兼容值使用约 998.275 kg/m³；配置其他单相流体时由 CoolProp 在参考压力和温度处提供密度与黏度。原型设备变量表压力使用 MPa，适配器明确按 1e6 转换；画布和总览压力按 kPa 显示。不得把表压自动当绝对压力，也不加隐含大气压。

## 变量命名与符号

- `V1.ch0.mass_flow_kg_s`：通路流量，正值表示从 input_port 流向 output_port。
- `V1.mass_flow_kg_s`：单通路设备的便捷别名。换热器无此别名，使用 `HX1.ch0` 和 `HX1.ch1`。
- `V1.in0.pressure_pa`、`V1.out0.pressure_pa`：端口绝对压力。
- `V1.out0.mass_flow_kg_s`：**流入设备为正**，所以正向运行时出口端口值为负。
- `V1.param.opening_ratio`：已应用的规范参数。
- `P1.shaft_power_w`：按压力增益、体积流量和效率估算的轴功率。
- `B1.out0.temperature_k`：压力边界给定温度；其他未求解端口温度为 `null`。

前端为延续原型，按标称端口方向展示流量：出口读数对规范端口流量取反。额外曲线保留原型 sampleKey（如 `V1:out0:FLOW`）和当前显示单位，同时每帧存储原始 `canonical` 字典。未知或未求解量必须显示为空，不能回退到演示值或零。

## 参数与状态

`parameters` 是物理输入；`draft_parameters` 与 `banks` 不自动生效。模块中的参数下限、上限不能覆盖内核注册模型的安全范围。

压力参考按连通子网络检查，关闭阀门会把水力网络分开。如果一侧没有压力参考，编译失败，避免给不可确定的压力赋值。节点允许未连接的可选分支端口，不把它们当作向外界排水。

型号与版本是可追溯元数据；实际计算只读取快照参数。`scenarios` 目前由规范 API 提交，原型工况 UI 的进一步接入尚未完成。
