# Python 模块公共 SDK：S0–S3 接口

当前 `fn_sdk.SDK_API_VERSION = '0.3.0'`；S0 的 0.1.0 类型接口、S1 的 resistance 与水力工具保留。S2 接入 schema 2 的版本协商，S3 增加时间、阶段与执行身份。SDK 版本与软件版本 0.5.0、模块整数版本及合同 schema 分开管理；四个 Python 回调签名保持。

## 1. 导入与安装

```python
from fn_sdk import ModuleContext

def evaluate(ctx: ModuleContext) -> None:
    density = ctx.port('in0').density_kg_m3
    ctx.net.valve(channel='main', kv=16.0, opening=0.8, density_kg_m3=density)
```

SDK 位于 `backend/fn_sdk/`，和当前工程一起安装，包含 PEP 561 的 `py.typed`。工程的原有安装方式继续适用；源码检查可设置 `PYTHONPATH=backend`。整个工程 wheel 的依赖仍包含引擎依赖，不将它描述为独立的轻依赖发行包。

`fn_sdk` 本身只导入标准库，不导入 `fn_engine`、Pydantic、NumPy、SciPy、CoolProp，不启动 Worker，也不查询物性。公开类都是 `typing.Protocol` 类型接口，实际对象由宿主在回调时提供；不直接实例化它们，也不用它们做 `isinstance` 检查。公共水力函数可直接调用；回调结果验证和序列化继续由宿主负责。

完整带类型示例见 [valve.py](../../examples/module_sdk/valve.py)。它只引用公共 SDK 和标准库，使用现有可编程阀合同做隔离测试，没有覆盖或发布种子模块版本。

局部阻力示例见 [resistance.py](../../examples/module_sdk/resistance.py)，测试合同由 `tests/test_module_resistance.py::resistance_module()` 构造：`in0/out0` 两端口、`main` 通路、`diameter_m/loss_coefficient/heat_w` 参数，输出 K、密度和状态账本。它也是未发布的作者示例，正式模块版本发布留到 S4。

S3 的 [timed_valve.py](../../examples/module_sdk/timed_valve.py) 演示用当前时间构造纯关系，并只在提交累计次数；声明方式、阶段可用量与身份语义见[执行上下文](EXECUTION_CONTEXT.md)。

## 2. 模块生命周期与上下文

`DeviceModule` 描述四个同步方法，均返回 `None`：

```python
def initialize(self, ctx: ModuleContext) -> None: ...
def evaluate(self, ctx: ModuleContext) -> None: ...
def commit_step(self, ctx: ModuleContext, dt_s: float) -> None: ...
def finalize(self, ctx: ModuleContext) -> None: ...
```

| 公共接口 | 类型 / 语义 |
| --- | --- |
| `ctx.time_s` / `ctx.phase` | 只读仿真时间 / `CallbackPhase`；直接手工构造时为 None / manual |
| `ctx.execution` | 只读 `ExecutionInfo`；会话/实例/请求/子步 ID、迭代、dt、数据来源与接受时间；详见[阶段合同](EXECUTION_CONTEXT.md) |
| `ctx.parameter(name, default=None)` | 返回 `JSONValue`；作者按合同检查具体类型，不把布尔值当数值 |
| `ctx.parameters` | `Mapping[str, JSONValue]`；已应用的计算参数 |
| `ctx.port(name)` / `ctx.ports` | `PortState` / 只读映射；可能缺少物理量，检查 `None` |
| `ctx.channel(name)` / `ctx.channels` | `ChannelResult` / 只读映射；提交阶段的实际收敛通路结果 |
| `ctx.state` | `MutableMapping[str, JSONValue]`；初始化和提交阶段管理的状态 |
| `ctx.net` | 宿主提供的 `NetworkBuilder`，注册通路关系 |
| `ctx.fluid` / `ctx.fluid_at(port_id)` | 默认回路 / 指定端口所在回路的惰性 `PropertyService` |
| `ctx.var(name, value)` | 发布 `ScalarValue` 输出，返回 `None`；名称应与合同一致 |
| `ctx.diagnostic(code, message, severity='warning')` | 发布 `info` / `warning` / `error` 诊断，返回 `None` |

`ScalarValue` 为数值、字符串、布尔或 `None`；`JSONValue` 再允许递归的列表和字符串键字典。类型声明不保证浮点数有限或物理工况合法；示例明确检查有限数值，状态限值及统一有限值门禁按 T0/T1 实现。

输入映射及结果属性在 SDK 类型层面只读，内部的列表/字典也应作为只读输入使用。S0 没有增加深度冻结或新的运行期拦截。evaluate 会重复执行，不得用它推进累计量；状态统一接受语义仍待 MOD-T，SDK 类型本身不提供事务或任意 Python 副作用恢复。

当前 v1 缺少端口名时返回空端口状态，缺少通路名时返回零值对象；这不代表该名称合法或该阶段已有实际解。作者应使用合同声明的名称，不依赖缺失名称的回退行为。水力 evaluate 中的流量可以为 `None`；S3 的来源标记明确区分 unavailable/trial/converged。H 组的热力/观察回调、D1 的日志仍待后续实现。

## 3. 关系构建器

所有参数均为关键字参数；每次 evaluate 对每条启用通路恰好注册一条关系，宿主负责覆盖/重复检查。方法返回 `None`，已注册关系可通过只读的 `net.relations` 序列读取。

| 方法 | 必填参数 | 可选参数及默认值 |
| --- | --- | --- |
| `pipe` | `channel`, `length_m`, `diameter_m` | `roughness_m=0.0`, `density_kg_m3=None`, `viscosity_pa_s=None`, `height_m=0.0`, `heat_w=0.0` |
| `valve` | `channel`, `kv`, `opening` | `density_kg_m3=None`, `height_m=0.0`, `heat_w=0.0` |
| `pump` | `channel`, `head_curve` | `speed_ratio=1.0`, `density_kg_m3=None`, `heat_w=0.0` |
| `compressor` | `channel`, `forced_mass_flow_kg_s` | 无 |
| `resistance` | `channel`, `diameter_m`, `loss_coefficient` | `density_kg_m3=None`, `heat_w=0.0` |

长度/扬程为 m，绝对压力为 Pa，温度为 K，质量流量为 kg/s，黏度为 Pa·s；Kv 为 m³/h，开度及转速比为无量纲。`head_curve` 使用 `list[list[float]]` 的 `[m³/h, m]` 点对。`heat_w` 单位为 W，正值向该通路流体加热，负值移热；轴功仍按原热力路径单独处理。

密度/黏度 `None` 沿用宿主参考物性行为，不在 SDK 导入时查询物性。新 `resistance()` 使用现有关系合同，不增加 schema 字段。K 允许为零，不设隐藏下限；密度省略时编码为宿主原有的参考物性标记 0。构建器复用现有有限值和关系参数校验，不截断负值或非有限值。

resistance 只有局部损失，不接受 `height_m`，不补入原模型没有的高差压降；它也不是“关闭通路”约束。高度、水力线性项或隐式状态模型不能借这个 K 关系自动获得。

## 4. 返回类型与物性

- `PortState`：绝压、温度、比焓、密度、黏度、比热、流量、干度可为 `None`，另有组分映射。端口质量流量正号表示流入设备。
- `ChannelResult`：`mass_flow_kg_s` 沿声明的输入端口到输出端口为正；`pressure_drop_pa = p_input - p_output`，不随实际流向改写定义。
- `FluidState`：物性服务返回的压力、温度、比焓、密度、相态与组分，另有可缺失的输运/量热属性、熵、内能、声速及干度。
- `NetworkRelation`：关系 ID、类型、通路名和只读参数映射。`Diagnostic`：错误码、消息、级别及可选实例/字段定位。
- `EvaluateResult`：宿主 evaluate 结果形状，包含关系、输出与诊断；不是模块 evaluate 方法的返回值。
- `CommitResult`：宿主提交结果形状，包含状态、输出与诊断；不代表该子步已获得全步接受。

`PropertyService` 提供 `state_pt/ph/ps/pq/tq/du`、`saturation_t/p`、`limits()`、`humid_air()`。压力为绝压 Pa、温度为 K、焓/内能为 J/kg、熵为 J/(kg·K)、密度为 kg/m³；湿空气相对湿度为 0–1。只在调用时访问实际物性服务，查询可因相态、输入或后端能力抛出 `ValueError`。允许查询某相态不等于网络支持该相态；流动仍遵循项目支持范围。

## 5. 共享水力工具

可从 `fn_sdk` 或 `fn_sdk.hydraulics` 导入。所有参数均为关键字参数，全部密度由调用者提供；函数不查询物性、不反解流量、不推进状态。返回压降沿声明的 input→output 为正，不含高差、轴功或热量。

| 函数 | 输入 / 默认值 | 返回 |
| --- | --- | --- |
| `pipe_pressure_drop_pa` | `mass_flow_kg_s`, `density_kg_m3`, `viscosity_pa_s`, `length_m`, `diameter_m`, `roughness_m=0.0` | 管道摩擦压降 Pa |
| `resistance_pressure_drop_pa` | `mass_flow_kg_s`, `density_kg_m3`, `diameter_m`, `loss_coefficient` | 局部损失压降 Pa |
| `valve_pressure_drop_pa` | `mass_flow_kg_s`, `density_kg_m3`, `kv_m3_h`, `opening_ratio=1.0` | 开阀压降 Pa |
| `kv_from_loss_coefficient` | `diameter_m`, `loss_coefficient` | 等效 Kv，m³/h |
| `mass_flow_to_volume_flow_m3_h` | `mass_flow_kg_s`, `density_kg_m3` | 带符号 m³/h |
| `volume_flow_m3_h_to_mass_flow_kg_s` | `volume_flow_m3_h`, `density_kg_m3` | 带符号 kg/s |

面积 `A=πD²/4`。局部阻力使用 `Δp=K*m*|m|/(2*ρ*A²)`，Kv 定义使用 `Δp=100000*(ρ/1000)*Q*|Q|/Kv²`（Q 为 m³/h）；因此等效转换为 `Kv=3600*sqrt(200)*A/sqrt(K)`。旧 pipe_fitting v1 包中的近似常数 50912 和 K 下限保持原样；新公共工具按上述 Kv 定义换算，不用旧包近似值替换引擎公式。

管道沿用原 Poiseuille/Haaland 公式：Re≤2300 为层流，2300<Re<4000 线性混合层流/湍流压降，Re≥4000 为湍流。过渡点只保证值连续，不宣称全局可微。引擎旧入口及导数基础项与公共工具共用标量核心，原参考常数和运算顺序保留；已有种子模块源码不重写。

公共函数拒绝布尔、非数值、NaN/Inf 和无效范围。密度、黏度、直径、管长、Kv 必须大于零，粗糙度与 K 非负；质量/体积流量可正、负或零。`valve_pressure_drop_pa` 要求 0<opening≤1：关阀是零流量约束，不能在这个压降函数里把其任意压差算成零。K=0 可计算零局部压降，但没有有限等效 Kv，转换函数会拒绝。

在无法得到有限结果、运算溢出，或应为非零的结果下溢成零时抛出 `ValueError`。零输入不跳过其余参数校验。可信的引擎残差路径复用内部数学核心，保持原校验/失败行为，不在每次残差调用重复执行公共函数的防御校验。这些工具仍是现有单相近似，不增加两相、可压缩管流或设备适用包络。

## 6. 公共与内部边界

| 范围 | 使用方式 |
| --- | --- |
| 公共 | `fn_sdk.__all__`、`fn_sdk.hydraulics.__all__` 列出的类型、函数、别名和 SDK 版本；本页明确的属性与方法 |
| SDK 内部 | `_protocols.py`、`_hydraulic_core.py`；引擎在同一工程内复用核心，作者不依赖该内部路径 |
| 引擎内部 | `fn_engine.runtime` 的上下文构造、Worker、runner、私有方法，求解器对象和 Pydantic wire 模型 |
| 后续接口 | 状态事务、热回调、日志；按各工作包新增并验证 |

旧模块已有的源码、import 和快照不被改写。新作者代码应只从 `fn_sdk` 导入类型；宿主提供对象，无需构造引擎内部上下文。

## 7. 验证入口

```powershell
python -m mypy --config-file mypy-sdk.ini
python -m pytest -q tests/test_module_sdk.py tests/test_module_sdk_hydraulics.py tests/test_module_sdk_runtime.py tests/test_module_resistance.py tests/test_module_sdk_contracts.py tests/test_module_contracts_runtime.py
```

独立 `module-sdk` CI job 使用轻依赖运行 SDK lint、严格类型检查及公共数学函数测试/独立覆盖率；后端 job 在全量环境执行实际宿主签名、Worker、网络和旧公式回放。SDK 覆盖率不代表全部物理工况或协议分支覆盖率。旧压差驱动反向冷启动/等压工况限制见 [S0 执行证据](results/S0.md)，S1 的范围和实测结果见 [S1 执行证据](results/S1.md)。

`bsl-modules` 轻依赖门禁还覆盖 schema 冻结、哈希和 SDK 声明校验；实际保存/Worker/设计接入见 [S2 执行证据](results/S2.md)。
