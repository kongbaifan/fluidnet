# P2 模块详细设计：capillary_tube + 控制脚本模板（comparator / fan_coil_thermostat）

> 适用 `fluidnet-prototype-engine` 0.4.10，`schema_version = 1`。合同唯一来源是 `backend/fn_engine/models.py`（Pydantic v2），本文与之冲突时以模型为准。
> 本批是「1 个单相近似模块 + 2 个项目控制脚本模板」：模块落在 `modules/capillary_tube/{manifest.json,module.py,README.md}`，模板落在 `examples/control_templates/{comparator,fan_coil_thermostat}.py`。
> 前置阅读：`docs/MODULE_KIT.md`（下称 KIT）、`docs/MODULES_P0.md`（P0）、`docs/MODULES_P1.md`（P1）、`backend/fn_engine/control.py`。
> 表头约定：`canonical → display（scale / offset）`；参数默认值、上下限、模块内拿到的值**一律 canonical**。
> 实现状态（2026-10-22）：上述三份文件已落地；自动化回归是 `tests/test_bsl_modules_p2.py`（模块）与 `tests/test_control_templates.py`（模板），用例数**以两个测试文件的实际收集结果为准**（§6）。本文只定义行为与接口，`design.py` 本批不需要。

## 接口总览

| 对象 | 形态 | 端口 / 输入 | 通路 / 输出 | 关系 / 执行方式 | 本文用例 |
| --- | --- | --- | --- | --- | --- |
| `capillary_tube` | Python 模块包（v1） | `in0` → `out0`（fluid，required） | `main` | `resistance` / `solver_model="pipe"` | CAP-1..3 |
| `comparator` | 控制脚本模板 | `input.analog` | `output.digital` | 独立 Worker，`state` 存 `output/low/high` | CMP-1..3 |
| `fan_coil_thermostat` | 控制脚本模板 | `input.room_temperature_k` | `output.fan_speed`、`output.valve_opening` | 独立 Worker，`state` 存 `setpoint/band/deadband/stage` | FCT-1..3 |

\* 两个模板里的 `input.*` / `output.*` 是**占位键**：`ControlScript.inputs/outputs` 必须换成真实工程变量路径后才可用（§3.4）。模板不含端口、不注册网络关系、不参与水力与热力方程；它们只写已有设备的运行参数或 PID 字段。

## 1. 目的与范围

本批只做两件事，并刻意不做第三件：

1. **一个单相近似模块** `capillary_tube`（矩阵第 5 行「毛细节流阀」）：把细长管节流建成管网里的一条 `pipe` 阻力支路，输出流通面积、平均流速，累计通过质量。它是**单相液体近似**，不是两相节流模型。
2. **两个项目控制脚本模板**：`comparator`（第 26 行「比较器」，双阈值 + 回差）与 `fan_coil_thermostat`（第 34 行「风机盘管控制」，三速分级 + 比例阀位）。两者是「复制到项目里改路径」的骨架，不是可运行的设备实例。
3. **不做**：不把比较器/温控做成模块包，也不在管网里加「信号端口」。

### 1.1 为什么控制类不做成网络模块

- **端口合同不允许**：编译期对每个端口检查 `port.domain != Domain.fluid`，非流体端口报 `DOMAIN_NOT_SOLVABLE`（`compiler.py:365-367`）。比较器的模拟量、温控器的室温都不是压力/流量，做成实例会立刻违约。
- **求解语义不同**：网络模块的 `evaluate` 在一次牛顿迭代里可能被调很多次，必须无副作用、只注册关系与派生变量（KIT §5）；控制要的是「按采样周期读帧变量 → 改写参数 → 下一子步生效」，且 `ctx.write` 只在 `step` 中允许（`control.py:33-38`）。
- **生命周期与执行位置不同**：控制脚本由 `ControlRunner` 校验三个同步回调的参数个数（`control.py:54-58`），运行期由 `ScriptControl`（继承 `WorkerProcess`）在**独立 Worker 进程**里执行（`control.py:75-77`、`worker.py:24-31`），超时/异常按脚本粒度报错，不污染求解器。
- **执行模式不同**：启用脚本的项目**必须动态运行**，稳态求解直接报 `CONTROL_DYNAMIC_REQUIRED`（`solver.py:771-772`）；网络模块在稳态与动态下都能用。
- **对象层级不同**：脚本是项目级对象 `Project.control_scripts`（最多 16 个，`models.py:463`），默认 `enabled=false`（`models.py:421`），与设备实例、PID 并列而不是嵌在管网里。

因此本批新增的**方程只有一个**（毛细管的 `pipe` 阻力），两个控制模板只写参数：例如 `fan_coil_thermostat` 的 `output.fan_speed` 应指向风机实例的 `speed_ratio`，`output.valve_opening` 指向水阀实例的 `opening_ratio`。

## 2. capillary_tube（毛细管·单相液体近似）

### 2.1 用途与倍思鹿语义

用一段细长圆管表达节流阻力：给定几何与工质物性，由 Darcy–Weisbach + 层流/湍流混合摩擦律求流量—压降关系，并给出流通面积、平均流速与累计通过质量。

倍思鹿 `AlgModule/毛细节流阀` 面向制冷剂节流：入口高压过冷/饱和液，节流后进入两相区，模块内部用物性库反求闪发干度、出口焓熵与两相壅塞流量（矩阵第 5 行，`BSL_MODULE_MAP.md` §4.1 第 2 条）。FluidNet 的管网流动只支持与回路边界一致的单相，两相只能在设备内部查询，所以本模块**只保留同几何的单相阻力语义**：能对齐「给定单相液流量时的压降、流速、通过质量」，不能对齐「出口干度、闪发率、壅塞流量、节流后温度」。每次 `evaluate` 都会发一条 `CAP_TWO_PHASE_UNSUPPORTED(info)` 把这个边界显式说出来（`modules/capillary_tube/module.py:44-51`）。

### 2.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `capillary_tube` / `毛细管` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model="pipe"`） |
| 端口 | `in0`（`in`，fluid，required，`fluid`）、`out0`（`out`，fluid，required，`fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="resistance"`，`solver_model="pipe"`，`enabled=true` |

`relation="resistance"` 是 manifest 的合同字段，运行时真正注册的关系由 `ctx.net.pipe(...)` 生成，`NetworkRelation.kind` 是 `"pipe"`（`runtime.py:61-71`），求解器按 kind 走 `pipe` 分支（Darcy 摩擦 + 标高，`solver.py:107-108`），与本批测试断言的 `relation.kind == "pipe"` 一致。`ctx.net.pipe(...)` 是唯一构造路径，没有手工追加关系。

### 2.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `diameter_m` | number | `0.0015` | `[1e-4, 0.05]` | m → mm（0.001） |
| `length_m` | number | `1.5` | `[0, 100]` | m → m |
| `roughness_m` | number | `1.5e-6` | `[0, 0.001]` | m → mm（0.001） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ → kg/m³ |
| `viscosity_pa_s` | number | `0.001` | `≥ 0` | Pa·s → mPa·s（0.001） |

`diameter_m` 的上限 `0.05 m` 只是「别把毛细管当主管」的工程包络，真正的小口径下限由参数下限 `1e-4 m` 与模块内 clamp 共同兜住。`density_kg_m3` / `viscosity_pa_s` 是**参考物性**：`evaluate` 里若 `in0` 试算端口带了密度/黏度就优先用端口值，否则用参数（`module.py:64-67`）；这条口径与求解器给试算端口填支路物性一致（`solver.py:230-232`），也与关系里 `density_kg_m3`/`viscosity_pa_s` 覆盖支路物性的分支一致（`solver.py:100-102`）。

### 2.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `flow_area_m2` | 流通面积 | derived | m² → m² |
| `mean_velocity_m_s` | 平均流速 | derived | m/s → m/s |
| `state.throughput_kg` | 累计通过质量 | state | kg → kg |

三个 id 与 `ctx.var` / `ctx.state` 键严格同名（`module.py:111-112`、`:116`），`state.throughput_kg` 在 `initialize` 里 `setdefault` 为 `0.0`（`module.py:42`）。平台保留键 `mass_flow_kg_s`、`pressure_drop_pa`、`heat_w` 等**不**声明为派生变量（P0 §4.1）；`heat_w=0` 由关系自带，无需模块输出。

### 2.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("throughput_kg", 0.0)`；取参数后统一 clamp（`module.py:54-73`）：`d=max(diameter_m, 1e-4)`；`L<1e-6` 时先发 `CAP_LENGTH_CLAMPED(warning)` 再取 `L=1e-6`（`pipe` 关系要求 `length_m>0`，`models.py:186-187`）；`ε=max(roughness_m, 0)`；`ρ=max(端口密度 or density_kg_m3, 1e-3)`；`μ_raw=端口黏度 or viscosity_pa_s`，`μ=max(μ_raw, 1e-6)`，`μ_raw≤0` 时发 `CAP_VISCOSITY_FALLBACK(warning)`。
2. **注册关系**：`A=πd²/4`，`ctx.net.pipe(channel="main", length_m=L, diameter_m=d, roughness_m=ε, density_kg_m3=ρ, viscosity_pa_s=μ, heat_w=0.0)`（`module.py:75-86`）。毛细管按绝热处理：`heat_w=0` 既符合物理（无轴功、无外热），也避开零流量带热触发的 `NO_FLOW_HEAT`（`thermal.py:243-249`）。
3. **确定流量**（`module.py:89-108`）：`in0.mass_flow_kg_s` 非空 → 直接取 `|m|`；否则取试算压差 `Δp=p_in−p_out`，端口压力缺失 → `m=0` 并发 `CAP_PRESSURE_UNKNOWN(warning)`；否则在 `m∈[0, 1e4] kg/s` 上二分 80 次反解。反解函数 `_pipe_drop` 与 `solver.pipe_drop` **逐行同律**（`solver.py:68-78`）：层流 `32μLm/(ρAd²)`、Colebrook `f=[−1.8·log10((ε/d/3.7)^1.11+6.9/Re)]⁻²`、`Re≤2300` 取层流、`2300<Re<4000` 用 `(Re−2300)/1700` 线性混合（`module.py:11-36`）。
4. 流速与输出：`v=|m|/(ρ·A)`，`ctx.var("flow_area_m2", A)`、`ctx.var("mean_velocity_m_s", v)`；每次 evaluate 先发 `CAP_TWO_PHASE_UNSUPPORTED(info)`（`module.py:46-51`、`:109-112`）。
5. `commit_step(ctx, dt_s)`：`m=|ctx.channel("main").mass_flow_kg_s|`，`state.throughput_kg += m·dt_s`（`module.py:114-116`）。此时 `ctx.channel` 是收敛通路，流量真实（`solver.py:850-856`）；派生变量不重发，帧里保留最后一次 evaluate 的值。

> **为什么「端口流量优先」在网络里几乎走不到**：求解器给模块的试算端口一律把 `mass_flow_kg_s` 置 `None`（`solver.py:225-232`、`runtime.py:111-112` 同理），所以网络运行时流速总是由收敛压差反解得到；端口优先分支主要服务于独立验证台和 L2 单元测试。**数值自检**（默认几何，水，`ρ=998.2`、`μ=0.001`）：`0.0005 kg/s` → `Re≈424`（层流）、`Δp≈6047 Pa`、`v≈0.2835 m/s`；`0.02 kg/s` → `Re≈1.70e4`、`Δp≈1.832 MPa`、`v≈11.34 m/s`；`0.05 kg/s` → `Re≈4.24e4`、`Δp≈9.736 MPa`、`v≈28.35 m/s`。

### 2.6 诊断码

| code | severity | 触发 | message 要点 / 处理 |
| --- | --- | --- | --- |
| `CAP_TWO_PHASE_UNSUPPORTED` | info | 每次 `evaluate` | 单相液体近似：两相壅塞、闪发、出口干度不在模型内；跨相或湿蒸气工况结果不可信 |
| `CAP_LENGTH_CLAMPED` | warning | `length_m < 1e-6` | 已按 1e-6 m 计算，避免 `pipe.length_m>0` 校验失败（`models.py:186-187`） |
| `CAP_VISCOSITY_FALLBACK` | warning | 有效黏度 `≤ 0` | 已按 1e-6 Pa·s 计算，Re 与压降不可信 |
| `CAP_PRESSURE_UNKNOWN` | warning | 端口流量与压力都缺失 | `mean_velocity_m_s=0`，关系仍按参数注册 |

本模块**不使用 error**：单相近似是合同内的已知边界，几何被截断只是数值保护；这些情况都应继续算完并留下诊断（与 P0/P1 的口径一致）。

### 2.7 测试用例（独立验证台或 L2 `InProcessModuleRunner`）

共用条件：`fluid=Water`、`temperature_k=293.15`、`duration_s=0.5`、`dt_s=0.1`；取**最终帧**；容差：面积/流速相对 1e-6，流量相对 1e-3，压降相对 1e-3。帧键前缀按入口不同：L2 用例是 `M1.`，`POST /api/v1/modules/test` 是 `D1.`。

| # | 输入 | 期望 |
| --- | --- | --- |
| CAP-1 | 默认参数；`in0.mass_flow_kg_s=0.02`、`in0.pressure_pa=300000`、`out0.pressure_pa=250000` | 恰 1 条关系：`kind="pipe"`、`channel="main"`、`heat_w=0.0`；`flow_area_m2≈1.767146e-6`；`mean_velocity_m_s≈11.3381`（端口流量优先，与 50 kPa 压差无关）；诊断含 `CAP_TWO_PHASE_UNSUPPORTED`，**不含** `CAP_PRESSURE_UNKNOWN` |
| CAP-2 | 默认参数；`in0.pressure_pa=200000`、`out0.pressure_pa=200000−6046.98`（对应 0.0005 kg/s 的层流解析解） | `mean_velocity_m_s≈0.283452`（相对 1e-6）；`Re≈424` 属层流；关系仍为 `pipe`；无 `CAP_PRESSURE_UNKNOWN` |
| CAP-3 | 边界与累计：`length_m=0` + `in0.mass_flow_kg_s=0.02`；再单独跑 `viscosity_pa_s=0` 与「端口无压力无流量」两组 | `length_m=0`：关系 `length_m≈1e-6`、诊断含 `CAP_LENGTH_CLAMPED`；`commit_step(dt=2 s, m=0.02)` → `state.throughput_kg≈0.04`；`μ=0`：关系 `viscosity_pa_s≈1e-6`、诊断含 `CAP_VISCOSITY_FALLBACK`；无压力：`mean_velocity_m_s=0`、诊断含 `CAP_PRESSURE_UNKNOWN`、关系仍存在 |

**矩阵第 5 行的验收算例另以 0.05 kg/s 作手算基线**：φ1.5 mm×1.5 m、单相水 20 °C、`m=0.05 kg/s` → `Δp≈9,736,370 Pa`（Colebrook 手算与 `pipe_drop` 同律）、`v≈28.345 m/s`、`Re≈4.24e4`。这个流速已远超液体在毛细管内的常规工况，正是不能拿单相结果代替两相壅塞的原因（§2.8）；自动化用例取 0.02/0.0005 kg/s 两个更接近工程的点。

### 2.8 局限与后续

- **只做单相**：不建模闪发、壅塞、出口干度、沿程蒸发与节流后温度；入口若已是两相或压降后跨相，本模块只保留水力阻力，结果只能当趋势参考，必须以 `CAP_TWO_PHASE_UNSUPPORTED` 与冷库/制冷执行域的内置节流设备为准。
- **绝热**：`heat_w=0`，不计算焦耳—汤姆逊温降、管壁散热与环境换热；出口温度由平台焓方程给出，节流后温度不可信。
- **物性**：单相不可压；`ρ/μ` 取端口试算物性或参数定值，不随温度/压力变化，也不做两相物性查询。反解与注册关系共用同一组 `ρ/μ`，这是水力迭代不漂移的前提。
- **摩擦律是单相充分发展管流**：不含入口效应、层流—湍流转捩滞回、表面张力与亚稳流；`Δp` 近似 ∝ `d⁻⁵`，`±0.05 mm`（约 ±3.3%）的内径偏差会带来 ±15% 量级的压降偏差。
- **几何**：只有直管，不含螺旋/蛇形、进出口局部阻力、管壁厚与结垢；需要局部阻力时串联 `pipe_fitting` 实例。
- **后续（两相专项另立）**：均相/分相两相摩擦压降、壅塞判据（入口过冷度 + 背压）、出口干度与闪发率、与制冷剂物性库的耦合。这需要新增变量（干度、闪发率）与合同字段，属于升版工作，不在本批范围。

## 3. 控制脚本模板通用说明

### 3.1 `ControlScript` 字段

| 字段 | 类型 / 默认 | 说明 |
| --- | --- | --- |
| `id` | `Identifier`，默认 `"control"` | 脚本标识；帧变量前缀 `script.<id>.` |
| `language` / `enabled` | 仅 `"python"` / 默认 `false` | 只有启用的脚本参与校验与执行（`models.py:421`） |
| `source` | 字符串，1–100000 字符 | 脚本原文；模板文件可直接整段粘贴 |
| `sample_s` | `0.001–60`，默认 `0.1` | 采样周期；采样点落在 `k·sample_s` 上 |
| `inputs` / `outputs` | `list[str]`，各 ≤256 | 只读/只写声明；必须与 `ctx.read`/`ctx.write` 的键一致 |
| `timeout_s` | `0.1–30`，默认 `5` | 单次回调的 Worker 超时 |
| `content_hash` | SHA-256 | 服务端按 `source` 生成；携带不一致哈希会被拒（`models.py:429-438`、`API.md:277`） |

每个项目最多 16 个脚本（`models.py:463`）；`inputs`/`outputs` 重复会被模型校验拒绝（`models.py:436-437`）。

### 3.2 生命周期与 `ctx` 语义

| 回调 | 调用时机 | 允许 | 禁止 |
| --- | --- | --- | --- |
| `initialize(ctx)` | 每次运行一次 | `ctx.state.setdefault` 初值、只读当前帧输入 | `ctx.write`（`writable=False`）、依赖全局变量 |
| `step(ctx, dt_s)` | 每个采样点一次 | `ctx.read` 声明输入、`ctx.write` 声明输出、改 `ctx.state`、`ctx.log` | 写未声明键、阻塞 IO、依赖全局变量 |
| `finalize(ctx)` | 运行结束一次 | 释放外部资源 | 写输出、改状态 |

- 三个回调必须是**同步函数**，参数个数分别为 1/2/1，写成协程或签名不符会在加载时报错（`control.py:54-58`）。
- `ctx.read(key)`：只接受已声明输入，键不在 `inputs` 或当前帧没有该变量都抛 `ValueError`（`control.py:26-31`）。
- `ctx.write(key, value)`：**只允许在 `step` 中调用**（`initialize/finalize` 里 `writable=False`，`control.py:33-35`），且只接受已声明输出（`control.py:36-38`）。写入先暂存，采样结束后整批校验并应用（`simulation.py:150-191`），要么全生效要么全不生效。
- `ctx.state`：受管理的 JSON 字典，必须是有限值、`≤64 KiB`（`control.py:11-17`）；只在**被接受的子步**提交（`control.py:107-113`、`simulation.py:244-249`）。全局变量与外部副作用不是事务状态（`DATA_CONTRACT.md:268`）。
- `ctx.time_s` 是当前仿真时刻；`ctx.log(msg)` 每次采样最多 20 条，落成 `CONTROL_LOG(info)` 诊断（`control.py:40-44`）。

### 3.3 采样、重试与失败处理

- 采样网格是 `next_s=(samples+1)·sample_s`（`control.py:104`），推进器会把子步长裁到最近的采样点（`simulation.py:287-288`），所以脚本不会漏采样、也不会在同一时刻重复采样。
- 一次采样先 `prepare` 出「拟写入 + 新状态」，只有在子步被接受后才 `accept` 提交；数值重试复用同一份拟写入，**不重复采样**（`control.py:97-113`）。这保证「累加/翻转」类逻辑不会被 Newton 重试放大。
- 失败面：Worker 超时 → `CONTROL_TIMEOUT`；脚本抛异常 → `CONTROL_SCRIPT_ERROR`，消息带脚本内行号（`control.py:69-72`、`:88-89`）；写入被拒 → `CONTROL_WRITE_REJECTED`（`simulation.py:190-191`）。脚本异常会终止该次运行，但保留已接受的历史帧。
- 首次 `step` 的 `dt_s=0`，之后是实际采样间隔（`control.py:99-100`、`API.md:279`）；模板不应把 `dt_s` 当积分步长使用。

### 3.4 输入输出必须是工程变量路径

- **输入**是帧变量键（`<实例>.<变量>`、`<实例>.state.<键>`、`controller.<id>.*`、`script.<id>.*`）。运行初始化时就检查：声明了但初始帧里不存在 → `CONTROL_INPUT_UNKNOWN`（`simulation.py:72-74`）。输入**不做显示单位换算**，脚本拿到的就是 canonical 值（`DATA_CONTRACT.md:268`）。
- **输出**只允许两类键（`control.py:146-152`）：设备运行参数 `<实例>.param.<参数>`（参数必须 `runtime=true`，由 `validated_parameters` 复核），或 `controller.<id>.setpoint|mode|manual_output`；其它键一律 `CONTROL_OUTPUT_INVALID`。同一目标不能同时被 PID 和脚本、或两个脚本写：编译期报 `CONTROL_TARGET_CONFLICT`（`control.py:143-145`），运行期再报 `PARAMETER_CONTROLLED`（`simulation.py:145-148`）。
- 因此模板里的 `input.analog`、`output.digital`、`input.room_temperature_k`、`output.fan_speed`、`output.valve_opening` 都是**占位符**：部署时必须替换成真实路径，并同步改 `ControlScript.inputs/outputs`，否则初始化即失败。

### 3.5 与 PID 的分工

| 场景 | 用 PID | 用脚本 |
| --- | --- | --- |
| 单测量 → 单参数的连续调节（温度、压差、流量） | ✅ `models.py:390-415`：`kp/ki/kd`、`sample_s`、`minimum/maximum`、手自动无扰 | 不必要 |
| 阈值翻转、回差、分档、顺序/联锁、多输入逻辑 | 不适用 | ✅ 本批两个模板 |
| 同时需要连续回路与分级 | PID 管连续量，脚本管档位/阀门模式，但两者**不能写同一个目标**（`control.py:143-145`） | |

PID 的写入目标是固定的「控制器 → 被控参数」，脚本的写入目标是任意声明的运行参数；两者都走同一个整批校验入口（`simulation.py:150-191`），互斥关系在编译期与运行期各查一次。

### 3.6 部署步骤（两个模板通用）

1. 从 `examples/control_templates/` 复制脚本原文，把文档字符串里列出的占位键替换为**真实工程变量路径**（输入取帧里已有的变量，输出取 `runtime=true` 的参数或 PID 字段）。
2. 新建 `ControlScript`：填 `id`、`source`、`inputs`、`outputs`、`sample_s`、`timeout_s`，`enabled` 先保持 `false`。
3. 调 `POST /controls/preview` 在临时会话里跑 `initialize` + 一次 `step`，核对拟写入值与诊断，不产生运行档案（`API.md:279`）。
4. 启用脚本并把运行模式切到**动态**（稳态会被 `CONTROL_DYNAMIC_REQUIRED` 拒绝），运行后检查 `script.<id>.samples`、`last_time_s`、`content_hash`、`state.*`（`control.py:115-119`）。
5. 改源码会改变 `content_hash`，保存时按新版本重新校验；同一项目脚本数上限 16。

## 4. comparator（比较器模板）

### 4.1 逻辑与回差

`examples/control_templates/comparator.py` 实现「模拟量 → 数字量」的双阈值翻转：

- `value ≥ high` → 输出 `1`；`value ≤ low` → 输出 `0`；
- `low < value < high` → **保持**上一次输出（回差，避免阈值附近抖动）；
- `value is None`（当前帧缺变量）→ 不翻转，只把上一次输出写回。

阈值默认 `low=0.4`、`high=0.6`，写在 `initialize` 的 `setdefault` 里；脚本每步从 `ctx.state` 读取，允许脚本自己在 `step` 里改（例如按工况切换阈值），但平台**没有**外部写脚本 state 的接口——要改阈值请改源码初值后重新启用。

### 4.2 状态与参数

| state 键 | 初值 | 含义 |
| --- | --- | --- |
| `output` | `0` | 上一次输出（0/1），回差的记忆量 |
| `low` | `0.4` | 下阈值：`≤ low` 翻到 0 |
| `high` | `0.6` | 上阈值：`≥ high` 翻到 1 |

三个键都是标量，`state` 总量远小于 64 KiB。`initialize` 只写 state、不写输出（首个 `step` 才产生 `writes`）。

### 4.3 输入输出

输入 `input.analog`（占位）→ 部署时替换为被比较的模拟量变量，如回水温度、压差、功率；输出 `output.digital`（占位）→ 替换为某个 `runtime=true` 的开度/转速参数，或 PID 的 `manual_output`。两个键必须同时出现在 `ControlScript.inputs/outputs` 里，否则 `ctx.read`/`ctx.write` 直接抛错。

### 4.4 部署步骤

1. 选定被比较变量与目标参数，替换两处占位键并同步 `inputs/outputs`。
2. 按工艺改 `low/high` 初值（例如压差报警 0.4/0.6 bar）；两值必须 `low < high`，否则行为退化为单阈值。
3. 用 `POST /controls/preview` 以一个越界值确认翻转与写入路径，再启用 + 动态运行，用 `script.<id>.state.output` 观察回差是否保持。

### 4.5 测试用例（3 个，含期望 writes）

| # | 输入序列 | 期望 writes | 期望 state |
| --- | --- | --- | --- |
| CMP-1 | `initialize`；`analog=0.3` | 首步 `{"output.digital": 0}` | `output=0`；`initialize` 本身 `writes == {}` |
| CMP-2 | 从 `output=0` 起：`0.5` → `0.5` | `0`（中间带保持 0） | `output` 不变 |
| CMP-3 | 从 `output=0` 起：`0.3` → `0.5` → `0.7` → `0.5` → `0.3` | `0` → `0` → `1` → `1` → `0` | 每步 `state.output` 与 writes 一致 |

矩阵第 26 行的验收序列正是 CMP-3（`0.3→0.5→0.7` 的回差翻转）；自动化用例另外覆盖反向下翻（`0.7→0.5→0.3→0.39`）与空值保持。

## 5. fan_coil_thermostat（风机盘管温控模板）

### 5.1 逻辑（三速分级 + 比例阀位）

`examples/control_templates/fan_coil_thermostat.py` 用水温式温控器的常见写法：

- `error = room_temperature_k − setpoint`（默认 `setpoint=300.15 K`，即 27 °C）；
- 档位：`error > band` → 3；`error > 0` → 2；`error > −deadband` → 1；否则 0；
- 阀位：`valve = clamp(error / band, 0, 1)`，与档位解耦，供连续调节；`room is None` 时不改档位、阀位记 0。

默认 `band=1.0 K`、`deadband=0.5 K`。回差体现在停机侧：`0 ≥ error > −deadband` 仍保持 1 档（低风），只有 `error < −deadband` 才降到 0 档；这样设定点附近不会反复启停。

### 5.2 状态与参数

| state 键 | 初值 | 含义 |
| --- | --- | --- |
| `setpoint` | `300.15` | 目标室温（K） |
| `band` | `1.0` | 比例带（K），同时是高挡判定上限；脚本内下限 `1e-6` 防除零 |
| `deadband` | `0.5` | 停机死区（K），脚本内下限 `0` |
| `stage` | `0` | 上一次档位（0/1/2/3），供面板/联锁读取 |

### 5.3 输入输出

输入 `input.room_temperature_k`（占位）→ 房间温度变量（K）；输出 `output.fan_speed`（占位）→ 风机 `speed_ratio` 一类可写参数或三速风机的档位映射参数，`output.valve_opening`（占位）→ 水阀 `opening_ratio`。两个输出都必须在 `outputs` 里声明，且目标参数 `runtime=true`，否则 `CONTROL_OUTPUT_INVALID` 或写入被拒。

### 5.4 部署步骤

1. 替换三处占位键，确认室温变量在初始帧里存在（否则 `CONTROL_INPUT_UNKNOWN`）。
2. 按房间/盘管改 `setpoint/band/deadband`；若风机只有三档且参数是离散档位，需在目标侧再映射一次（本模板只写 0–3 的整数档位）。
3. 预览一次阶跃工况（例如 `room=setpoint+2 K`）确认 3 档、阀位 1，再启用 + 动态运行并观察 `script.<id>.state.stage`。

### 5.5 测试用例（3 个）

| # | 输入 | 期望 writes |
| --- | --- | --- |
| FCT-1 | 室温 `303.15 K`（error=3.0 K > band） | `{"output.fan_speed": 3, "output.valve_opening": 1.0}` |
| FCT-2 | 室温 `300.2 K`（error=0.05 K > 0） | `{"output.fan_speed": 2, "output.valve_opening": 0.05}` |
| FCT-3 | 室温 `299.5 K`（error=−0.65 K < −deadband） | `{"output.fan_speed": 0, "output.valve_opening": 0.0}` |

补充边界（自动化用例覆盖）：`300.65 K` → 2 档 / 0.5；`300.0 K`（error=−0.15）→ 1 档 / 0.0；`300.8 K` → 2 档 / 0.65；`finalize` 不产生 writes、state 不变。矩阵第 34 行的验收写作「303→300.2→299.5」，与 FCT-1..3 同结论（303 K 的 error=2.85 K 同样 > band）。

### 5.6 局限与后续

- 档位是**当前误差的函数**，不是记忆型状态机：没有最短运行/停机时间、没有压缩机防频繁启停、没有多台风机轮换；`state.stage` 只用于观测与联锁。
- 阀位与档位解耦，因此「1 档 + 阀关」是正常输出（设定点附近低风循环）；若工艺要求到点停机，应改判据或加定时器。
- 温度只有一个测点，不含回风/送风加权、房间热惯性、传感器滞后与死区补偿；`deadband` 是人工整定值。
- 后续：多档联锁面板（矩阵里记为缺失能力）应把阈值、档位、阀位做成可视化组态，而不是继续加脚本常量；面板组态不在本批范围。

## 6. 验收与 CI

### 6.1 `tests/test_bsl_modules_p2.py`（模块）

- **契约**：`id/name/version/category`、`runtime="python"`、`entrypoint`、`source_format`、`solver_model="generic"`、双哈希（`content_hash` 等于 `module.py` 的 SHA-256、`definition_hash` 稳定且两者不等）、端口全覆盖且全为 `fluid`、通路 `main` 的 `relation/solver_model`、五个参数默认值、显示单位与 `display_scale`、变量集合。
- **关系与流速**：恰一条 `pipe` 关系，`length/diameter/roughness/heat_w` 与参数一致；`flow_area_m2`、`mean_velocity_m_s` 与 `|m|/(ρA)` 相符；含 `CAP_TWO_PHASE_UNSUPPORTED(info)`，且端口已给流量时不出现 `CAP_PRESSURE_UNKNOWN`。
- **压差反解**：用层流解析解构造 `Δp`，断言反解流速相对 1e-6 命中，关系仍是 `pipe`。
- **长度截断与累计**：`length_m=0` 时关系长度截到 `1e-6`、诊断含 `CAP_LENGTH_CLAMPED`；`commit_step(dt=2 s, m=0.02)` 后 `state.throughput_kg=0.04`。
- **黏度回退与压力缺失**：`viscosity_pa_s=0` 时关系黏度为 `1e-6`、诊断含 `CAP_VISCOSITY_FALLBACK`；端口无流量无压力时 `mean_velocity_m_s=0`、诊断含 `CAP_PRESSURE_UNKNOWN`、关系仍注册。

### 6.2 `tests/test_control_templates.py`（控制模板）

- 按项目实际用法把模板文件原文读成 `ControlScript.source`，用 `ControlRunner` 在进程内跑 `initialize/step/finalize`，不依赖 scipy/CoolProp。
- **比较器**：`initialize` 返回 `state={"output":0,"low":0.4,"high":0.6}` 且无 writes；`0.7→1`、`0.5` 保持 1、`0.3→0`、`0.39` 保持 0；无诊断。
- **温控**：`initialize` 返回 `state={"setpoint":300.15,"band":1.0,"deadband":0.5,"stage":0}`；`303.15 K→3 档/1.0`、`300.65 K→2 档/0.5`、`300.2 K→2 档/0.05`、`300.0 K→1 档/0.0`、`299.5 K→0 档/0.0`、`300.8 K→2 档/0.65`；`finalize` 不写输出、state 不变。

### 6.3 CI

`.github/workflows/bsl-modules.yml` 已包含本批门禁：第 46–48 行用 `ruff check` 覆盖 `modules`、`examples/control_templates`、`tests/test_bsl_modules*.py`、`tests/test_control_templates.py` 与提取脚本；第 49–51 行用 `python -m pytest -q` 只跑四个模块/控制模板测试文件（不跑全量 pytest）；第 53–77 行的 `package` job 把 `modules`、`examples/control_templates`、`MODULES_P0/P1/P2.md`、`BSL_MODULE_MAP.md` 与三个测试文件打成 artifact。该 workflow 依赖 pydantic/pytest/ruff，不需要 scipy 或 CoolProp（第 42–45 行）。注意：workflow 已引用两个 P2 测试文件，若文件缺失，lint 与 pytest 会在收集阶段失败——它们与本批文档同批交付。

## 7. 与 P0/P1 的差异

| 维度 | P0（pipe_fitting / check_valve / fan_coil_unit） | P1（cooling_tower / fan / pump_variable_speed） | P2（本批） |
| --- | --- | --- | --- |
| 交付形态 | 3 个 Python 模块包 | 3 个 Python 模块包 | 1 个模块包 + 2 个控制脚本模板 |
| 网络关系 | `resistance`（`valve`/`valve`/`pipe`） | 新增 `pump_curve`/`pump`；冷却塔仍 `resistance`/`pipe` | 只有 `resistance`/`pipe`（毛细管），控制模板不注册关系 |
| 参数规模 | 4/4/13 | 13/7/7 | 5 |
| 状态变量 | `throughput_kg`、`closed_steps`、`thermal_energy_j` | `thermal_energy_j`、两本轴/电能量账 | 只有 `state.throughput_kg`；控制脚本的 state 由 `ControlScript` 管理 |
| evaluate 流量来源 | FC 用试算压差反解 | 冷却塔反解；fan/泵用设计点 | 端口优先、否则同律反解（网络里实际总走反解） |
| 两相 | 不涉及 | 不涉及（干空气/单相气体） | 显式声明不支持，每帧 `CAP_TWO_PHASE_UNSUPPORTED` |
| 执行位置 | 模块 Worker | 模块 Worker | 模块 Worker + 控制脚本独立 Worker（`control.py:75-77`） |
| 失败面 | 三个模块都不使用 error | 曲线结构性非法可报 error；曲线外/反转由求解器报错 | 模块不用 error；脚本异常 `CONTROL_SCRIPT_ERROR`/`CONTROL_TIMEOUT` |
| 测试形态 | L2 契约 + 逻辑 | 同上 | 模块 L2 + 控制模板用 `ControlRunner` 直接执行 |

补充：P0/P1 的模块都通过「关系 + 派生变量」进入管网；P2 的两个控制模板不进入管网，它们读取帧变量、写参数，再触发下一子步重算。这也是本批唯一需要同时看 `packages.py` 与 `control.py` 的原因。

## 8. 平台依赖点（实现与验收时必须知道）

| # | 事实 | 影响 |
| --- | --- | --- |
| 1 | `solver.pipe_drop` 的层流/Colebrook/过渡混合是内部实现（`solver.py:68-78`） | 毛细管反解必须与它同律；引擎改摩擦律时模块的 `_pipe_drop` 要同步，否则反解流量与注册关系自相矛盾 |
| 2 | 关系里的 `density_kg_m3`/`viscosity_pa_s` 会覆盖支路物性（`solver.py:100-102`） | 模块把同一组 `ρ/μ` 传进关系与反解，保证不会「反解一套、求解另一套」 |
| 3 | evaluate 的试算端口流量恒为 `None`，commit 的 `ctx.channel` 才是真实流量（`solver.py:225-232`、`:850-856`） | 网络里流速永远来自压差反解；`state.throughput_kg` 只能在 commit 累计 |
| 4 | 零流量通路声明非零 `heat_w` 会报 `NO_FLOW_HEAT`（`thermal.py:243-249`） | 毛细管固定 `heat_w=0`，绝热且不触发该错误 |
| 5 | 编译期拒绝非 `fluid` 端口（`compiler.py:365-367`） | 控制不能做成网络模块；只能走 `Project.control_scripts` |
| 6 | 控制脚本在独立 Worker 中执行，超时取 `timeout_s`（`control.py:75-77`、`worker.py:24-31`） | 脚本里的重计算要控制在 `timeout_s` 内，否则 `CONTROL_TIMEOUT` |
| 7 | 采样网格 `(samples+1)·sample_s`，重试不重复采样（`control.py:97-113`） | 脚本的累加/翻转不会被 Newton 重试放大 |
| 8 | 输出只允许 `<实例>.param.*` 或 `controller.<id>.*`（`control.py:146-152`） | 模板里的占位输出必须换成运行参数；指向普通帧变量会被拒 |
| 9 | 启用脚本要求动态运行（`solver.py:771-772`） | 稳态 API 会直接报 `CONTROL_DYNAMIC_REQUIRED` |
| 10 | 首次 `step` 的 `dt_s=0`（`control.py:99-100`） | 模板不能把 `dt_s` 当积分步长 |

## 9. 验收 checklist

- [ ] **接口锁定**：`modules/capillary_tube/manifest.json` 的端口、通路、五个参数（默认/上下限/单位）、三个变量与 §2.2–§2.4 逐字段一致；`relation="resistance"`、`solver_model="pipe"`、`enabled=true`；端口全 `fluid`、被 `main` 覆盖。
- [ ] **合同**：`evaluate` 恰返回一条 `pipe` 关系且 `heat_w=0.0`；`diameter/length>0`（`models.py:186-187`）由参数下限与 clamp 双重保证。
- [ ] **单位**：`diameter_m`/`roughness_m` 显示 mm（0.001）、`viscosity_pa_s` 显示 mPa·s（0.001）、密度与流速不换算；模块内无二次换算。
- [ ] **公式**：`flow_area_m2=πd²/4`、`mean_velocity_m_s=|m|/(ρA)`；层流段与 Colebrook 反解在 CAP-2/CAP-3 与手算一致；0.05 kg/s 的 `Δp≈9.74 MPa` 与 Darcy 手算一致（矩阵第 5 行验收）。
- [ ] **诊断**：每帧有且仅有一次 `CAP_TWO_PHASE_UNSUPPORTED`；`L=0`、`μ=0`、压力缺失分别出 `CAP_LENGTH_CLAMPED`/`CAP_VISCOSITY_FALLBACK`/`CAP_PRESSURE_UNKNOWN`，且都不中断运行。
- [ ] **累计**：`commit_step` 才改 `state.throughput_kg`，数值等于 `∫|m|dt`；`evaluate` 两次调用逐字段相同（幂等、无副作用）。
- [ ] **控制模板**：两个模板的 `initialize/step/finalize` 均为同步、参数个数 1/2/1；`inputs/outputs` 声明与 `ctx.read/write` 键一致；`write` 只出现在 `step`；`state` 全为 JSON 标量且 `<64 KiB`。
- [ ] **比较器**：CMP-3 序列的 writes 与 state 同步；中间带保持上一次输出；`initialize` 不写输出。
- [ ] **温控**：FCT-1..3 的档位/阀位与表格一致；`band≤0`/`deadband<0` 被脚本内 clamp 兜住；`room=None` 时不翻转档位。
- [ ] **占位键**：模板文档字符串里的占位键清单与 `inputs/outputs` 一一对应；`README` 或部署说明明确要求替换（模板不能原样启用）。
- [ ] **CI**：`.github/workflows/bsl-modules.yml` 的 ruff 与 pytest 步骤能收集到 `tests/test_bsl_modules_p2.py`、`tests/test_control_templates.py`；不依赖 scipy/CoolProp。
- [ ] **发布**：模块首次发布 `expected_latest_version=0`、版本 `1.0.0`；保存前试算覆盖全部 derived/state 输出（`MODULE_OUTPUT_MISSING`，`packages.py:136-138`）；模板随 `docs/MODULES_P2.md` 一起进 artifact。
