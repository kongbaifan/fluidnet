# P0 模块详细设计：pipe_fitting / check_valve / fan_coil_unit

> 适用 `fluidnet-prototype-engine` 0.5.0，`schema_version = 1`。合同唯一来源是 `backend/fn_engine/models.py`（Pydantic v2），本文冲突时以模型为准。
> 本文只定义三个 Python 模块包的**行为与接口**；实现落在 `modules/<id>/{manifest.json,module.py,README.md}`，`design.py` 本批不需要。
> 前置阅读：`docs/DATA_CONTRACT.md`、`docs/MODULE_KIT.md`（下称 KIT）、`modules/programmable_valve/*`。
> 表头约定：`canonical → display（scale / offset）`；参数默认值、上下限、模块内拿到的值**一律 canonical**。
> 实现状态（2026-10-22）：三个包已在 `modules/{pipe_fitting,check_valve,fan_coil_unit}/` 落地；`tests/test_bsl_modules.py` 7 项通过；fan_coil_unit 按本文要求用试算压差反解水侧流量，模块换热量对外键为 `heat_flow_w`（平台别名 `heat_w` 仍由求解器生成）。

## 接口总览

| 模块 | 端口（均 fluid，required） | 通路 | relation / solver_model | 参数个数 | 派生变量 | 状态变量 | 用例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `pipe_fitting` | `in0` → `out0` | `main` | `resistance` / `valve` | 4 | `loss_coefficient`、`velocity_m_s` | `state.throughput_kg` | 4 |
| `check_valve` | `in0` → `out0` | `main` | `resistance` / `valve` | 4 | `opening_ratio`、`direction` | `state.closed_steps`、`state.throughput_kg` | 4 |
| `fan_coil_unit` | `in0` → `out0` | `main` | `resistance` / `pipe` | 13 | `heat_flow_w`（平台另有别名 `heat_w`）、`air_outlet_temperature_k`、`effectiveness` | `state.thermal_energy_j` | 4 |

\* 平台会为单通路实例生成 `<I>.heat_w`（来自已注册关系的 `heat_w`），模块**不得**用 `ctx.var("heat_w", ...)` 输出同名键；本实现另用 `heat_flow_w` 暴露水侧换热量，见 §3.4。三个包合计 12 个设计用例（PF-1..4 / CV-1..4 / FC-1..4），自动化回归在 `tests/test_bsl_modules.py`（7 项，本批已通过）。

## 0. 三个模块共同的前提

- evaluate 里 `ctx.channel()` 恒为空值、`ctx.port(p).mass_flow_kg_s` 恒为 `None`；真实流量只能在 `commit_step` 读（`runtime.py:111-112`、`solver.py:225-232`）。
- evaluate 收到深拷贝，改 `ctx.state` 不生效；只有 `commit_step` 里的修改会提交（`runtime.py:198-199`、`:206-211`）。
- 每条启用通路必须**恰好**返回一条关系，`channel` 与 `ChannelSpec.id` 同名（`solver.py:257-260`）。
- 关断必须用 `opening_ratio` 精确 `0.0`；求解器把该支路换成 `flow==0` 等式约束，写 `1e-9` 会得到约 1e18 Pa 的压降（`solver.py:292-298`、`:307-310`）。
- 零流量通路不得带非零 `heat_w`，否则 `NO_FLOW_HEAT`（`thermal.py:243-249`）。
- 单通路模块的 `<I>.mass_flow_kg_s`、`pressure_drop_pa`、`inlet_temperature_k`、`outlet_temperature_k`、`heat_w` 由平台快照生成；模块若用 `ctx.var` 输出同名键会被 "模块输出不能覆盖网络求解变量" 拒绝（`solver.py:693-712`，`simulation.py:257-259`）。**fan_coil_unit 的 `heat_w` 正属于此类，见 §3.4。**
- Python 模块通路若在运行中把子网隔成无压力参考，水力求解直接报 "模块通路关系产生了缺少压力参考的子网络"（`solver.py:370-385`）；`ISOLATED_PRESSURE_HELD` 只对被动内置管段生效（`simulation.py:220-227`）。

---

## 1. pipe_fitting（管件局部阻力）

### 1.1 用途与倍思鹿语义

把弯头、异径管、三通、进出口的**局部阻力系数 K** 折算成一条阻力通路：`Δp = K·ρ·v²/2`。倍思鹿对应 `AlgModule/弯管`、`异径管`、`管道通用`：模块读入流量/密度/DN，调用 `PIPECV_ELBOW` / `PIPECV_RDC` / `PIPECV` 由物性算出 `RLS`（阻力）与 `CV`（流通能力），再用 `Netlink_Pipe(0, RLS, CV, DENSITY, DHIGH)` 注册。本设计不复刻其关联式，只保留工程 K 表口径：同一 K 在不同 DN 下折算成不同的 Kv，由求解器统一按阀门平方律算压降。

### 1.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `pipe_fitting` / `管件局部阻力` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model=valve`） |
| 端口 | `in0`（`in`，fluid，required，circuit `fluid`）、`out0`（`out`，fluid，required，circuit `fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="resistance"`，`solver_model="valve"`，`enabled=true` |

端口/通路覆盖必须通过 `CHANNEL_COVERAGE`（`compiler.py:434-437`）；Python 模块跳过 `CHANNEL_MODEL_INVALID`，但 `solver_model` 建议与实际关系 kind 一致，便于阅读与未来收紧（`compiler.py:439-442`）。

### 1.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `fitting_type` | text | `"elbow_90"` | 见 K 表（含 `custom`） | 无单位（text 不能声明 unit） |
| `loss_coefficient` | number | `0.9` | `[0, 100]` | 1 → 1（scale 1, offset 0） |
| `diameter_m` | number | `0.05` | `≥ 1e-4` | m → mm（scale 0.001） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ → kg/m³ |

内置 K 表（`fitting_type → K`）：`elbow_90=0.9`、`elbow_45=0.4`、`reducer=0.5`、`tee_through=0.2`、`tee_branch=1.0`、`entrance=0.5`、`exit=1.0`、`custom=loss_coefficient`。有效 K 下限 **0.05**（`K_eff = max(K, 0.05)`），避免 Kv 过大导致 Jacobian 病态；K 上限由参数上限 100 保证。除 `custom` 与未知类型外，`loss_coefficient` 不参与计算，仅作为 UI 记录与回退值保留。

### 1.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `loss_coefficient` | 有效局部阻力系数 | derived | 1 → 1 |
| `velocity_m_s` | 断面平均流速 | derived | m/s |
| `state.throughput_kg` | 累计通过质量 | state | kg → kg |

`state.throughput_kg` 的 state 键就是 `throughput_kg`，`initialize` 里 `setdefault` 为 `0.0`；稳态只采样不提交，故稳态帧恒为 0。

### 1.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("throughput_kg", 0.0)`。
2. 取 `d = max(diameter_m, 1e-4)`、`rho = max(density_kg_m3, 1e-3)`；`A = πd²/4`。
3. 取 K：`custom` 用 `loss_coefficient`；未知字符串用 `loss_coefficient` 并报 `PF_FITTING_UNKNOWN`；其余查表。再 `K = max(K, 0.05)`（发生截断报 `PF_K_CLAMPED`）。
4. **阀门等效推导**（本文档的核心换算）：
   - 局部阻力：`Δp_K = K·ρ·v²/2`，`v = Q/A`（Q 为 m³/s）⇒ `Δp_K = K·ρ·Q²/(2A²)`。
   - 求解器阀门律：`Δp_v = 1e5·(ρ/1000)·Q_h²/Kv²`，`Q_h = 3600Q`（`solver.py:104-106`）⇒ `Δp_v = 1.296e9·ρ·Q²/Kv²`。
   - 令 `Δp_K ≡ Δp_v`，ρ 与 Q² 同时约去（阀门律自带 ρ/1000 因子，正是这一点让换算式与工质无关）：
     `Kv² = 1.296e9·2A²/K = 2.592e9·A²/K` ⇒ **`Kv = 50911.7·A/√K ≈ 50912·A/√K`**（Kv 单位 m³/h，A 单位 m²）。
   - 示例：`d=0.05`、`K=0.9` ⇒ `A=1.9635e-3 m²`、`Kv=105.37 m³/h`；在 `Δp=1000 Pa`、`ρ=998.2` 下 `m=2.924 kg/s`、`v=1.492 m/s`，且 `K·ρv²/2=1000.01 Pa`，与阀门律一致。
5. 注册关系：`ctx.net.valve(channel="main", kv=Kv, opening=1.0, density_kg_m3=rho)`。`opening` 必须精确 `1.0`；`kv` 必须 `>0`（`models.py:186-191`），上述公式在 `d≥1e-4`、`K≤100` 时 Kv 最小约 4e-5，安全。
6. 派生变量：`ctx.var("loss_coefficient", K)`；`dp = p_in − p_out`（任一为 `None` 时记 0 并报 `PF_PRESSURE_UNKNOWN`），`velocity_m_s = sqrt(2·|dp|/(K·rho))`（与 `|Q|/A` 等价；反向流取正）。
7. `commit_step(ctx, dt_s)`：`ctx.state["throughput_kg"] += abs(ctx.channel("main").mass_flow_kg_s) * dt_s`。不加 `commit_count`：本模块只声明 2 个派生变量和 1 个状态变量。

**为什么不用 `resistance`**：求解器已实现 `Δp = ζ·m|m|/(2ρA²)`（`solver.py:113-115`），`NetworkRelation` 也接受 `kind="resistance"`（必需 `diameter_m` + `loss_coefficient`，`models.py:176-198`），但 `NetworkBuilder` 只有 `pipe/valve/pump/compressor` 四个方法（`runtime.py:57-84`），没有 `resistance()`；手工 `ctx.net.relations.append(NetworkRelation(...))` 需要 import `fn_engine` 内部模块，属 KIT §6.3 的"受控选项 3"，在 Worker 的 `PYTHONPATH` 注入下可用但不稳定，且会绕过 `_add` 的统一构造。另有一处语义差：`resistance` 分支的 `branch_drop` 没有 `ρgh` 项，而阀门律带 `height_m`。**建议**后续给引擎加 `NetworkBuilder.resistance(*, channel, diameter_m, loss_coefficient, density_kg_m3=None, heat_w=0.0)`（3 行，含有限性与 `d>0` 校验）；加好后本模块可改为直接注册物理 K，`Kv` 换算作为旧引擎回退路径按版本号保留。

### 1.6 诊断码

| code | severity | 触发 | message 要点 / 处理 |
| --- | --- | --- | --- |
| `PF_FITTING_UNKNOWN` | warning | `fitting_type` 不在 K 表且非 `custom` | 回退 `loss_coefficient`，提示可用取值 |
| `PF_K_CLAMPED` | info | `K_eff < 0.05` | 已抬到 0.05，给出原 K 与等效 Kv |
| `PF_PRESSURE_UNKNOWN` | info | `p_in`/`p_out` 为 `None` | `velocity_m_s` 记 0；关系仍按 Kv 注册 |

### 1.7 测试用例（独立验证台 `POST /api/v1/modules/test`）

共用条件：`fluid=Water`、`temperature_k=293.15`、`duration_s=0.5`、`dt_s=0.1`；容差：流量/速度相对 1e-3，其余 1e-6。帧键前缀 `D1.`。

| # | 输入 | 期望 |
| --- | --- | --- |
| PF-1 | 默认参数；`inlet=200000`、`outlet=199000` | `main.mass_flow_kg_s≈2.9244`、`velocity_m_s≈1.4921`、`loss_coefficient=0.9`、`main.pressure_drop_pa=1000`、`state.throughput_kg≈1.4622`（5 次提交 ×0.1 s） |
| PF-2 | `fitting_type=custom`、`loss_coefficient=5`、`diameter_m=0.02`、`inlet=202000`、`outlet=200000` | `loss_coefficient=5`、`mass_flow≈0.28074`、`velocity≈0.89524`、`pressure_drop_pa=2000` |
| PF-3 | `fitting_type=custom`、`loss_coefficient=0`、`diameter_m=0.02`、`inlet=201000`、`outlet=200000` | `loss_coefficient=0.05`（下限）、`mass_flow≈1.98514`、`velocity≈6.33029`；诊断含 `PF_K_CLAMPED` |
| PF-4 | `fitting_type="bend"`、`loss_coefficient=2`、`diameter_m=0.02`、`inlet=201000`、`outlet=200000` | `loss_coefficient=2`、`mass_flow≈0.31387`；诊断含 `PF_FITTING_UNKNOWN` |

### 1.8 局限与后续

- K 表是工程定值，不含 Re、相对粗糙度、口径突变面积比与三通分流比修正；倍思鹿的 `PIPECV_ELBOW` 等关联式未复刻。
- 一条通路只表达一个局部阻力；串联多个管件请放多个实例（每个实例都引入一个节点，会略微增加方程规模）。
- 不输出压降/流量派生变量，二者由平台通路变量提供。
- 后续：按倍思鹿口径补 `reducer` 的面积比修正、`tee` 的分流比插值，以及引擎 `resistance()` 落地后改用物理 K。

---

## 2. check_valve（止回阀）

> **版本状态**：本章 §2.1–§2.8 描述 **v1**（`modules/check_valve/`，`version=1`），源码与契约快照保持
> 不变，旧项目继续按 v1 语义运行。**v2**（`modules/check_valve_v2/`，`id=check_valve, version=2`）
> 的语义冻结、方程、发布与验收见 **§5**。v2 修掉了 §2.8 里“反向压差低于开启压差仍反向导通”的语义。

### 2.1 用途与倍思鹿语义

单向导通、反向截止。倍思鹿 `AlgModule/止回阀` 的判据是：`CVF = 0`（关闭）当 `IM0_PRE < EX0_PRE`，否则 `CVF = 1`，随后 `VALVECV_SHUT(..., CVF, CV, RLS, RE)` 并用 `Netlink_Check(0, RLS, CV, DENSITY, DHIGH)` 注册；`CVF` 直接充当开度。本设计保留"用压力方向决定开度"的分段语义，但把开度改成 `opening_ratio` 参数，并增加开启压差 `cracking_pressure_pa`；关闭时交给求解器做**零流量等式约束**，比倍思鹿的极小 CV 更容易收敛。

### 2.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `check_valve` / `止回阀` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model=valve`） |
| 端口 | `in0`（`in`，fluid，required，`fluid`）、`out0`（`out`，fluid，required，`fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="resistance"`，`solver_model="valve"`，`enabled=true` |

### 2.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `kv_m3_h` | number | `50` | `≥ 0.001` | m³/h → m³/h |
| `opening_ratio` | number | `1.0` | `[0, 1]` | 1 → %（scale 0.01） |
| `cracking_pressure_pa` | number | `0` | `≥ 0` | Pa → kPa（scale 1000） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ → kg/m³ |

### 2.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `opening_ratio` | 有效开度（0 表示截止） | derived | 1 → %（0.01） |
| `direction` | 试算压差方向 | derived | 文本：`"forward"` / `"reverse"` |
| `state.closed_steps` | 累计关闭步数 | state | 步 |
| `state.throughput_kg` | 累计通过质量 | state | kg |

`direction` 只描述 `p_out − p_in` 的符号，不代表是否导通；是否导通看 `opening_ratio==0`。若反向压差未达开启压差，`direction="reverse"` 且 `opening_ratio>0`，即允许反向流（见 2.8）。

### 2.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("closed_steps", 0)`；`ctx.state.setdefault("throughput_kg", 0.0)`。
2. 取 `p_in = ctx.port("in0").pressure_pa`、`p_out = ctx.port("out0").pressure_pa`；`d_rev = p_out − p_in`。
3. **冷启动兜底**：任一压力为 `None` 时按**正向**处理（`blocked=False`）并报 `CV_PRESSURE_UNKNOWN`。理由：冷启动/独立 evaluate 可能没有端口压力；若把未知当成反向而写入 `opening=0`，支路立即变成 `flow==0` 约束，压力差不再进入残差，阀门永远打不开，求解会卡在初值上。
4. `blocked = (d_rev is not None and d_rev > cracking_pressure_pa)`；`opening = 0.0 if blocked else min(max(opening_ratio, 0.0), 1.0)`。
5. `ctx.net.valve(channel="main", kv=max(kv_m3_h, 0.001), opening=opening, density_kg_m3=max(density_kg_m3, 1e-3))`。`kv` 必须为正，即使全关也要给正 Kv（`models.py:186-187`）。
6. 变量：`ctx.var("opening_ratio", opening)`；`ctx.var("direction", "reverse" if (d_rev or 0) > 0 else "forward")`。关闭时诊断 `CV_REVERSE_BLOCKED`（info，含压差与开启压差）；反向但未达开启压差时诊断 `CV_REVERSE_BELOW_CRACKING`（warning）。
7. `commit_step(ctx, dt_s)`：用**收敛端口**重判方向（不能沿用 evaluate 的最后一次试算），`opening==0` 时 `closed_steps += 1`；`throughput_kg += abs(ctx.channel("main").mass_flow_kg_s) * dt_s`。
8. 反向关闭时求解器把该支路替换为 `flow==0`，其压差由网络决定、不受关系约束；`main.pressure_drop_pa` 可能是 `-1000 Pa` 这类反向值，属正常。

**收敛提示**：开/关切换对 `d_rev` 不可导，`least_squares` 的有限差分 Jacobian 会在跨阈值时退化。缓解：开启压差取小（0 或工作压差的 1e-2 量级），不要同时用很大的 `kv_m3_h` 配很小的开启压差；若报 `HYDRAULIC_NOT_CONVERGED`，先减小动态步长或放宽初值（warm start 失败时求解器会退回冷启动，`solver.py:365-368`）。

### 2.6 诊断码

| code | severity | 触发 | message 要点 |
| --- | --- | --- | --- |
| `CV_REVERSE_BLOCKED` | info | `p_out − p_in > cracking_pressure_pa` | 反向压差 x Pa > 开启压差 y Pa，opening=0（零流量约束） |
| `CV_REVERSE_BELOW_CRACKING` | warning | `0 < p_out − p_in ≤ cracking_pressure_pa` | 反向导通，未模拟阀瓣/弹簧动力学 |
| `CV_PRESSURE_UNKNOWN` | info | 试算压力缺失 | 按正向处理以避免冷启动锁死 |

### 2.7 测试用例

共用条件：`fluid=Water`、`temperature_k=293.15`、`duration_s=0.3`、`dt_s=0.1`；容差同 §1.7。

| # | 输入 | 期望 |
| --- | --- | --- |
| CV-1 | 默认参数；`inlet=200000`、`outlet=199000` | `main.mass_flow_kg_s≈1.38764`、`opening_ratio=1.0`、`direction="forward"`、`state.closed_steps=0`、`state.throughput_kg≈0.41629` |
| CV-2 | 默认参数；`inlet=199000`、`outlet=200000`（反向 1000 Pa > 开启压差 0） | `main.mass_flow_kg_s=0`（|m|≤1e-8）、`opening_ratio=0.0`、`direction="reverse"`、`state.closed_steps=3`、诊断含 `CV_REVERSE_BLOCKED` |
| CV-3 | `cracking_pressure_pa=2000`；`inlet=199000`、`outlet=200000`（反向 1000 Pa < 开启压差） | `opening_ratio=1.0`、`main.mass_flow_kg_s≈-1.38764`、`direction="reverse"`；诊断含 `CV_REVERSE_BELOW_CRACKING` |
| CV-4 | `opening_ratio=0.5`；`inlet=200000`、`outlet=199000` | `opening_ratio=0.5`、`main.mass_flow_kg_s≈0.69382`、`state.closed_steps=0` |

### 2.8 局限与后续

- 分段判据在 `d_rev` 恰好跨过 `cracking_pressure_pa` 时不可导，数值上可能出现开/关抖动；建议 `cracking_pressure_pa` 小于该支路正常压差的 10%，并避免把开启压差设成与工作压差同量级。
- 反向压差低于开启压差时仍按 `opening_ratio` 反向导通，这是"压力判据 + 零流量约束"模型的固有语义，**不是**可用的防倒流保证。
- 关闭后若把下游子网隔成无压力参考，运行报 "模块通路关系产生了缺少压力参考的子网络"（§0）；需要在该子网保留压力边界或改用内置截止阀 + 边界配置。
- `state.closed_steps` 只统计**被接受**的时间步，稳态运行不提交、恒为 0。
- 后续：开启压差滞环（开启/关闭两个阈值）、泄漏率 `Kv_leak`、阀瓣行程动态。

---

## 3. fan_coil_unit（风机盘管：水侧网络 + 空气侧代数）

### 3.1 用途与倍思鹿语义

水侧是网络中的一条阻力支路，向流体声明 `heat_w`；空气侧**不建网络**，用集总热容与 ε-NTU 代数式耦合。倍思鹿 `AlgModule/风机盘管` 是四端口设备：管程 `in0/out0`（水）与壳程 `in1/out1`（空气）各自是一条 `Netlink_Pipe` 支路（水侧 `PIPECV(..., PL0=SL*8, ...)`，风侧 `PIPECV_capillary(...)`），换热用 `H = 1/(1/H_metal + 1/H_in + 1/H_out)`、`Q = ΔT·H`，并对两侧焓值做 3 次迭代与"温度反超"回滚，要求两侧流量均 > 0.01。本设计把 `H` 降为常量参数 `ua_w_k`，把两侧流量换成"水侧由网络求解、风侧由参数给定"，换热用逆流 ε-NTU 一次算出，不再迭代焓值——**因为 FluidNet 的热力层已经负责 `h_out += heat_w/|m|`**（`thermal.py:426-428`）。

### 3.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `fan_coil_unit` / `风机盘管` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model=pipe`） |
| 端口 | `in0`（`in`，fluid，required，`fluid`）、`out0`（`out`，fluid，required，`fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="resistance"`，`solver_model="pipe"`，`enabled=true` |

空气侧没有端口：模块包只允许 `domain=fluid` 的端口（`compiler.py:365-367`），且风侧压力/流量在本阶段没有物理来源（无风机曲线、无风管网络），因此按参数集总处理，见 3.8。

### 3.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `ua_w_k` | number | `2000` | `≥ 0` | W/K → kW/K（scale 1000） |
| `water_side_diameter_m` | number | `0.02` | `≥ 1e-4` | m → mm（0.001） |
| `water_side_length_m` | number | `5` | `≥ 0` | m → m |
| `roughness_m` | number | `1.5e-6` | `≥ 0` | m → mm（0.001） |
| `air_flow_m3_s` | number | `0.2` | `≥ 0` | m³/s → m³/h（scale 1/3600） |
| `air_inlet_temperature_k` | number | `300.15` | `≥ 1` | K → °C（1 / −273.15） |
| `air_inlet_relative_humidity` | number | `0.5` | `[0, 1]` | 1 → %（0.01） |
| `air_density_kg_m3` | number | `1.2` | `≥ 0.01` | kg/m³ |
| `air_cp_j_kg_k` | number | `1006` | `≥ 100` | J/(kg·K) → kJ/(kg·K)（1000） |
| `water_cp_j_kg_k` | number | `4180` | `≥ 100` | J/(kg·K) → kJ/(kg·K)（1000） |
| `water_inlet_temperature_k` | number | `285.15` | `≥ 1` | K → °C（1 / −273.15） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ |
| `viscosity_pa_s` | number | `0.001` | `≥ 0` | Pa·s → mPa·s（0.001） |

注意：编译期的 `diameter_m`+`roughness_m` 联检（`compiler.py:175-182`）**不会**触发，因为内径 id 是 `water_side_diameter_m`；零/负内径与负粗糙度由本表 `minimum` 兜住，模块内再做一次 clamp（见 3.5）。

### 3.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `heat_flow_w` | 水侧换热量（正=水吸热） | derived | W → kW（1000） |
| `air_outlet_temperature_k` | 空气出口温度 | derived | K → °C（1 / −273.15） |
| `effectiveness` | 换热效能 ε | derived | 1 → 1 |
| `state.thermal_energy_j` | 累计水侧吸热量 | state | J → kJ（1000） |

**`heat_w` 必须由平台别名提供，模块不得 `ctx.var("heat_w", ...)`**：单通路模块的快照会生成 `<I>.heat_w`，其值就是热力层算出的该通路焓流增量（无轴功时等于关系里声明的 `heat_w`，`solver.py:688-694`）；模块再输出同名键会触发 "模块输出不能覆盖网络求解变量"（`solver.py:710-712`）。本实现把模块自算的换热量以 `heat_flow_w` 输出（不重名、可在设备面板单独查看），平台别名 `<I>.heat_w` 仍存在且数值相同；保存前的 `MODULE_OUTPUT_MISSING` 检查只看帧里有没有声明的输出键（`packages.py:136-138`），两者都满足。`thermal=false` 时平台别名按合同缺席，但模块的 `heat_flow_w` 仍是派生输出。

### 3.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("thermal_energy_j", 0.0)`。
2. 取参数并 clamp：`d=max(water_side_diameter_m,1e-4)`、`L=max(water_side_length_m,1e-6)`（`pipe` 关系要求 `length_m>0`，`models.py:186-187`；截断报 `FC_LENGTH_CLAMPED`）、`eps=max(roughness_m,0)`、`rho=max(density_kg_m3,1e-3)`、`mu=max(viscosity_pa_s,1e-6)`（`pipe_drop` 用它除 Re，0 会 `ZeroDivisionError`，`solver.py:68-78`；截断报 `FC_VISCOSITY_FALLBACK`）。
3. **反算水侧流量**：evaluate 读不到流量，用试算压差 `dp = p_in − p_out` 反解与所注册 `pipe` 关系**同一条**摩擦律（层流 `32μLQ/(ρA d²)`、Colebrook `f=(-1.8·log10((ε/d/3.7)^1.11+6.9/Re))^-2`、`Re≤2300` 层流、`2300<Re<4000` 线性混合 `(Re−2300)/1700`）。`dp` 缺失记 0、报 `FC_PRESSURE_UNKNOWN`。反解用二分（`m∈[0,1e4]`，60 次；上限覆盖本模块常规水侧流量，越界按端点取值），收敛时与求解器流量一致到 1e-9 kg/s；这是**平台依赖点**：若求解器摩擦律变更，本反算必须同步（`solver.py:68-78`）。
4. 容量与 ε：`C_w=|m|·cp_w`、`C_a=ρ_a·air_flow_m3_s·cp_a`。仅当 `|m|>1e-6`、`ua_w_k>0`、`C_a>0`（从而 `C_min>0`）时计算 `Cr=C_min/C_max`、`NTU=ua_w_k/C_min` 与 ε；否则跳过（ε=0，见步骤 5），避免除零。
   - `Cr` 极限：`|1−Cr|<1e-9` 时 `ε=NTU/(1+NTU)`；否则逆流 `ε=(1−exp(−NTU(1−Cr)))/(1−Cr·exp(−NTU(1−Cr)))`。
5. `Q=ε·C_min·(T_air,in−T_water,in)`；`heat_w=Q`（正=水吸热/制冷，负=水放热）。以下任一情况强制 `Q=0, ε=0` 并给对应诊断：`|m|≤1e-6`（`FC_ZERO_WATER_FLOW`，避免 `heat_w/m` 爆炸与 `NO_FLOW_HEAT`）、`ua_w_k≤0`（`FC_UA_DISABLED`）、`C_a≤0`（`FC_AIR_FLOW_ZERO`）。
6. 注册：`ctx.net.pipe(channel="main", length_m=L, diameter_m=d, roughness_m=eps, density_kg_m3=rho, viscosity_pa_s=mu, heat_w=Q)`。`heat_w` 由热力层按 `h_out = h_in + Q/|m|` 施加（`thermal.py:426-428`），水出口温度无需模块计算。
7. 变量：`ctx.var("heat_flow_w", Q)`、`ctx.var("air_outlet_temperature_k", T_air,in − Q/C_a)`（`C_a≤0` 时直接给 `T_air,in`）、`ctx.var("effectiveness", ε)`。**不输出 `heat_w`**（由平台别名提供）。
8. `commit_step(ctx, dt_s)`：用 `|m|=abs(ctx.channel("main").mass_flow_kg_s)` 重算同一套 `C_w/ε/Q`（此时流量是真实值，精度高于反算），`ctx.state["thermal_energy_j"] += Q*dt_s`（有符号累计）。
9. 露点提示：用 Magnus 式 `γ=ln(RH)+17.625T/(243.04+T)`、`T_d=243.04γ/(17.625−γ)`（T、T_d 为 °C）估算空气露点；`T_water,in < T_d − 0.5 K` 时报 `FC_CONDENSATION_RISK`（warning）。仅提示，不改 Q。

**数值示例**（默认参数 + `inlet=200000`、`outlet=199550`、`temperature_k=285.15`）：`dp=450 Pa` 反解得 `m=0.10050 kg/s`；`C_w=420.09`、`C_a=241.44`、`Cr=0.5747`、`NTU=8.2836`、`ε=0.98723`；`Q=3575.4 W`；空气出口 `285.342 K`（12.19 °C）；水出口约 `293.66 K`（20.51 °C，由热力层焓方程给出）。

**Cr→1 自检**（验证极限分支；验证台无法恰好命中，建议在 L2 直接调用模块内的 ε 辅助函数）：取 `m=0.0577655 kg/s` 使 `C_w=241.44=C_a`，则 `Cr=1`、`NTU=8.2836`，应得 `ε=NTU/(1+NTU)=0.89229`、`Q=3231.5 W`、空气出口 `286.77 K`。若实现误用 Cr<1 公式，此处会除零或得到 ε≈1。

### 3.6 诊断码

| code | severity | 触发 | message 要点 |
| --- | --- | --- | --- |
| `FC_ZERO_WATER_FLOW` | info | 反算 `|m| ≤ 1e-6 kg/s` | 本帧不换热，`heat_w=0`；风侧仅旁通 |
| `FC_UA_DISABLED` | info | `ua_w_k ≤ 0` | 仅水力阻力，`heat_w=0` |
| `FC_AIR_FLOW_ZERO` | warning | `air_flow_m3_s ≤ 0` 或 `air_density_kg_m3 ≤ 0` | 风侧无热容，`Q=0`；请检查风量/密度参数 |
| `FC_CONDENSATION_RISK` | warning | `T_water,in < T_d − 0.5 K` | 干工况模型，未计冷凝潜热，Q 可能偏小 |
| `FC_LENGTH_CLAMPED` | info | `water_side_length_m < 1e-6` | 已按 1e-6 m 注册，避免 `length_m>0` 校验失败 |
| `FC_VISCOSITY_FALLBACK` | warning | `viscosity_pa_s ≤ 0` | 已按 1e-6 Pa·s 计算，Re 结果不可信 |
| `FC_PRESSURE_UNKNOWN` | info | 端口试算压力缺失 | 按 `dp=0` 处理，本帧 `heat_w=0` |

### 3.7 测试用例

共用条件：`fluid=Water`、`duration_s=0.5`、`dt_s=0.1`；容差：温度 0.3 K、`heat_w` 相对 1e-3、其余同 §1.7。

| # | 输入 | 期望 |
| --- | --- | --- |
| FC-1 | 默认参数；`inlet=200000`、`outlet=199550`、`temperature_k=285.15` | `main.mass_flow_kg_s≈0.10050`、`heat_w≈3575.4`、`effectiveness≈0.98723`、`air_outlet_temperature_k≈285.34`、`out0.temperature_k≈293.66`、`state.thermal_energy_j≈1787.7` |
| FC-2 | `ua_w_k=0`，其余同 FC-1 | 流量与压降同 FC-1；`heat_w=0`、`effectiveness=0`、`air_outlet_temperature_k=300.15`、`state.thermal_energy_j=0`；诊断含 `FC_UA_DISABLED` |
| FC-3 | `inlet=200000`、`outlet=200000`、`temperature_k=285.15` | `main.mass_flow_kg_s≈0`、`heat_w=0`、`effectiveness=0`、`air_outlet_temperature_k=300.15`；诊断含 `FC_ZERO_WATER_FLOW`，且**不得**出现 `NO_FLOW_HEAT` |
| FC-4 | `air_inlet_temperature_k=280.15`，其余同 FC-1 | `heat_w≈−1191.9`（水放热）、`air_outlet_temperature_k≈285.09`、`out0.temperature_k≈282.3`、`effectiveness≈0.98723`、`state.thermal_energy_j≈−596.0` |

### 3.8 边界与后续

- 空气侧不建网络：没有风侧压力节点、风机压头、风管阻力与风量-静压曲线；`air_flow_m3_s` 是给定风量，不是求解结果。
- 干工况：不计冷凝、潜热、析湿与冷凝水盘；`air_inlet_relative_humidity` 只用于露点提示，不进入 ε-NTU。湿工况需加表面湿系数/焓差法，并新增潜热输出变量（须升版）。
- 无风机功耗、无盘管水容量/金属热容、无结霜；`ua_w_k` 是常量，不随水量/风量变化（倍思鹿的 `SHTC_P/SHTC_S` 关联式未复刻）。
- 换热用水侧入口温度取**参数** `water_inlet_temperature_k`，不读端口试算温度（试算温度在 `thermal=false` 时是 293.15 的占位值、在耦合模式来自上一轮物性，不能作为换热基准）。工程上应使该参数与上游边界/工况一致，否则水量热与网络水温会不一致。
- 水出口温度由热力层按 `h_out=h_in+Q/|m|` 得出，模块不声明水出口变量；零流量帧没有 `heat_w`，热力层不会报 `NO_FLOW_HEAT`。
- 后续：湿工况（焓差 + 潜热 + 析湿系数）、风量随档位/静压变化、UA 随流量修正（`UA=UA_rated·(m/m_rated)^n`）、盘管水容量与动态热惯性。

---

## 4. 跨模块约定

### 4.1 命名

- 模块 `id` 用 snake_case 英文：`pipe_fitting` / `check_valve` / `fan_coil_unit`；`label`/`name` 用中文；目录名与 `id` 一致。
- 端口固定 `in0`/`out0`（`direction` 只是标称，不限制反向流）；通路固定 `main`；`relation` 一律 `"resistance"`，`solver_model` 分别为 `valve`/`valve`/`pipe`。
- 变量 id 与 `ctx.var` 键、`ctx.state` 键严格同名；状态变量 id 必须是 `state.<key>`。以下 id 是平台保留键，**不要**声明为派生变量：`mass_flow_kg_s`、`pressure_drop_pa`、`inlet_temperature_k`、`outlet_temperature_k`、`heat_w`；尤其不要把 `heat_w` 写进 `ctx.var`。
- 每个包只暴露 `module:Module`，四个同步方法 `initialize(ctx)` / `evaluate(ctx)` / `commit_step(ctx, dt_s)` / `finalize(ctx)`（KIT §2、§5）。

### 4.2 单位

| 量 | canonical | 显示 | scale / offset |
| --- | --- | --- | --- |
| 温度 | K | °C | 1 / −273.15 |
| 内径、粗糙度、长度 | m | mm（长度可用 m） | 0.001 / 0 |
| 压力、开启压差 | Pa | kPa | 1000 / 0 |
| 质量流量、质量 | kg/s、kg | 同 | 1 / 0 |
| 动力黏度 | Pa·s | mPa·s | 0.001 / 0 |
| 定压比热 | J/(kg·K) | kJ/(kg·K) | 1000 / 0 |
| 热流 `heat_w` | W | kW | 1000 / 0 |
| UA | W/K | kW/K | 1000 / 0 |
| 开度、比例、ε | 1 | % | 0.01 / 0 |
| 能量 | J | kJ | 1000 / 0 |
| 体积流量（空气） | m³/s | m³/h | 1/3600 / 0 |

模块内**禁止**二次换算（不再乘 1000、不再减 273.15）。压力一律绝压。UA 的显示单位按本批规格取 kW/K；内置换热器的 `ua_w_k` 沿用 W/K（`DATA_CONTRACT.md:70`），二者 canonical 相同，只是显示不同。换算示例：面板输入 50（mm）→ canonical 0.05 m；输入 12（°C）→ 285.15 K；输入 2（kW/K）→ 2000 W/K；输入 80（%）→ 0.8。

### 4.3 诊断 code

- 统一 `UPPER_SNAKE_CASE` + 模块前缀：`PF_`（pipe_fitting）、`CV_`（check_valve）、`FC_`（fan_coil_unit）；不得复用内核码（`NO_FLOW_HEAT`、`PARAMETER_RANGE`、`MODULE_OUTPUT_CONFLICT` 等）。
- `error` 只用于"结果不可信"，会中断运行；本批三个模块**不使用 error**，工程包络一律 `warning`、模型假设一律 `info`（KIT §3.6）。
- message 必须含实例/通路、数值与单位、可执行建议；同一 evaluate 内同一 code 只发一次（一帧只保留最后一次 evaluate 的诊断）。

### 4.4 与 MODULE_KIT 的衔接

- 包结构照 KIT §2：`manifest.json` + `module.py` + `README.md`（README 写物理假设、公式、参数/变量表、诊断码、参考算例）；不手写 `content_hash`/`definition_hash`。
- 生命周期照 KIT §5：evaluate 无副作用、只注册关系与派生变量；commit 只在接受步更新 state；`initialize` 自足（跨 run 不恢复）。
- 测试照 KIT §7 四级：L1 契约（`load_module_package` + 双哈希 + 入口四方法）、L2 逻辑（`InProcessModuleRunner` 幂等、关系集合、state 累计）、L3 网络（`compile_project`+`solve_steady/solve_dynamic`+本文件用例）、L4 与倍思鹿/解析解对照（K→Kv 换算误差、能量残差 ≤1e-6）。
- 发布照 KIT §9：首次 `expected_latest_version=0`，版本号 `1.0.0`；保存前试算必须覆盖全部 derived/state 输出；`release.json` 保留试算凭据。
- KIT §6.3 的 `resistance` 结论已落在 §1.5：本批用阀门等效，等引擎补 `NetworkBuilder.resistance()` 后再切换。

### 4.5 平台依赖点（实现时必须知道）

| # | 事实 | 影响 |
| --- | --- | --- |
| 1 | evaluate 无流量（`ctx.channel` 为空、`port.mass_flow=None`） | fan_coil_unit 用试算压差反算流量，且必须与 `solver.pipe_drop` 摩擦律同步 |
| 2 | 单通路 `heat_w` 是平台别名 | 模块输出 `heat_w` 会直接失败；声明保留，值由别名提供 |
| 3 | 关断必须精确 `opening=0.0` | check_valve 的关闭判据不能写成 `1e-9` |
| 4 | 零流量不得带热 | 两个带热/可能零流量的模块都要在低流量时把 `heat_w` 归零 |
| 5 | Python 模块支路不能做隔离保压 | 止回阀关闭后若隔离子网会报缺少压力参考 |
| 6 | 摩擦律/阀门律属于求解器内部实现 | 反算与 Kv 换算均按 `solver.py` 现行公式实现并加注释，引擎升级时回归 L3/L4 |

### 4.6 建议实现顺序

1. `pipe_fitting`：只涉及阀门等效与 K 表，最独立，可先跑通 PF-1～PF-4。
2. `check_valve`：在 pipe_fitting 的阀门构造基础上加方向判据与 state。
3. `fan_coil_unit`：需要反算流量、ε-NTU、`heat_w` 别名与热力层配合，最后做 FC-1～FC-4，并核对 `energy_residual_w`。

### 4.7 本批验收清单（在 KIT §8 基础上追加）

- [ ] 三个 manifest 的 ports/channels 与 §1–§3 的表逐字段一致：端口全覆盖、`relation`/`solver_model` 未被改名、`enabled=true`。
- [ ] 参数/变量 id、默认值、上下限、单位换算与各节表一致；text 参数未声明 unit；`minimum` 覆盖所有除数。
- [ ] evaluate 对每条启用通路恰好返回一条关系；`kv>0`、`0≤opening≤1`，关闭用精确 `0.0`。
- [ ] `fan_coil_unit` 未调用 `ctx.var("heat_w", ...)`，只输出 `heat_flow_w`；帧中 `D1.heat_w` 与 `D1.main.heat_w` 相等，且与 `D1.heat_flow_w` 数值一致；`thermal=false` 时平台别名缺席而运行不报错。
- [ ] 零流量用例（CV-2、FC-3）无 `NO_FLOW_HEAT`、无非有限值，state 全为 JSON 标量。
- [ ] 12 个用例在独立验证台通过（容差按各节），L2 的"两次 evaluate 逐字段相同"成立。
- [ ] 与倍思鹿对照：PF 的 K→Kv 换算在 3 个 DN 上与 `K·ρv²/2` 一致到 2e-5（`50912` 相对精确值 `50911.7` 的舍入量）；FC-1 的 Q 与手算 ε-NTU 一致到 1e-6。
- [ ] 动态运行 `energy_residual_w` 相对全网焓流 ≤1e-6；`state.throughput_kg` 与 `state.thermal_energy_j` 等于对应积分。

---

## 5. check_valve V2：语义冻结与稳定求解（V0–V2）

> 实施日期 2026-10-23，基线 v0.5.0 `a986ca3`。模块包 `modules/check_valve_v2/`（`manifest`：
> `id=check_valve`、`version=2`、包版本 `2.0.0`）；v1 包 `modules/check_valve/`（`version=1`）
> 源码与契约快照**不改写**。独立参考在 `backend/fn_engine/check_valve.py`，验收入口
> `tests/test_check_valve_numerics.py`，实测证据 `docs/numerics/results/V0.md`、`V1.md`、`V2.md`。

### 5.1 用途与冻结结论（V0）

单向导通、反向截止。v2 的物理语义**冻结**为下列四条，不再含糊：

| 项 | 冻结值 / 语义 |
| --- | --- |
| 压差定义 | `Δp = p_in − p_out`（`in0` 减 `out0`，单位 Pa） |
| 正向开启压差 `p_crack_pa` | 只有 `Δp > p_crack` 才导通；默认 `0`（理想二极管：任何正压差都开启，与 v1 默认的前向行为一致） |
| 反向截止 | **精确零流**：`Δp ≤ p_crack`（含全部反向）时 `opening_ratio` 精确为 `0.0`，求解器把它变成 `flow == 0` 等式约束 |
| 泄漏 | **不承诺“有界泄漏”**：选定的语义是精确截止，反向/亚开启区通过质量的声明上界是 **0 kg/s**（只剩求解器质量容差 `mass_tolerance_kg_s`，默认 1e-8 kg/s，它不是物理泄漏参数）。本模型同时**不承诺处处光滑** |
| 迟滞 | `hysteresis_pa` 默认 `0`（无迟滞）。`> 0` 为可选路径，状态只在 accepted 步更新；动态按步推进已自洽，但“同一步内活动集自洽”需要求解器外层活动集（未接入，§5.6）；无论迟滞是否开启，`Δp ≤ 0` 恒关 |
| 光滑性 | 开关点 `Δp = p_crack` 处两支路流量都 → 0，残差**连续（C0）**但左右导数不同：关闭行是 `flow == 0`（不含压力），开启支路在临界点 `∂q/∂Δp → ∞`。这是设计选择，不是待修的缺陷 |

**旧参数语义（v1，不覆写）**：v1 的 `cracking_pressure_pa` 是“**容许反向流的反向压差**”——
当 `0 < p_out − p_in ≤ cracking_pressure_pa` 时阀门仍按正向开度**反向导通**。实测
`cracking_pressure_pa=5000` 时：`Δp=−1 Pa` 反向流 0.0439 kg/s、`Δp=−1000 Pa` 反向流 1.3877 kg/s，
且 `Δp=−4500/−4999 Pa` 处 `least_squares` 停在不收敛点（压力残差 4500/4999 Pa，`gtol` 误判）。
v1 的开/关判据落在 `Δp = −cracking`，那里“开启支路”残差比“关闭支路”多出 `cracking_pressure_pa`
的**跳变**，是旧版临界点附近不稳的根因。v2 不沿用该参数语义；v1 源码与行为保持原样（V1/V2 证据有回归）。

### 5.2 v2 参数（冻结默认值）

| id | 类型 | 默认 | 范围 | 单位 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `kv_m3_h` | number | `50` | `≥ 0.001` | m³/h | 全开流量系数 |
| `p_crack_pa` | number | `0` | `≥ 0` | Pa → kPa（scale 1000） | **正向开启压差**（新增） |
| `opening_ratio` | number | `1.0` | `[0, 1]` | 1 → %（0.01） | 正向最大开度（缩放 Kv） |
| `hysteresis_pa` | number | `0` | `≥ 0` | Pa → kPa（1000） | 迟滞带宽；0 = 无迟滞（新增） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ | 端口密度缺失时的参考密度 |
| `cracking_pressure_pa` | number | `0` | `≥ 0` | Pa → kPa（1000） | **v1 遗留，v2 不参与计算**；非零时发一次 `CHECK_VALVE_LEGACY_PARAMETER`（info） |

参数 id 全部保留（含遗留参数），所以 v1→v2 的升级预览是 `compatible=true`，但会把
`cracking_pressure_pa` 的 label 与 `p_crack_pa`/`hysteresis_pa` 的新增列进 `changes`，由用户确认；
**不会把旧的 `cracking_pressure_pa` 数值静默改释为正向开启压差**（新增参数默认 0，旧值原样保留且不生效）。

### 5.3 变量与方程

| id | source | 语义 |
| --- | --- | --- |
| `opening_ratio` | derived | 有效开度；`0` = 精确截止 |
| `is_open` | derived | 1 = 该次试算/提交时导通 |
| `direction` | derived | `+1`：`Δp > 0`；`−1`：`Δp ≤ 0`（**不**代表是否导通） |
| `state.is_open` | state | 只在**接受步**更新的开闭状态（无迟滞时仅记账） |
| `state.closed_steps` / `state.open_steps` | state | 接受步计数 |
| `state.throughput_kg` | state | `∑|q|·Δt` |
| `state.reverse_throughput_kg` | state | `∑min(q,0)·Δt`，v2 验收要求恒为 0 |

`evaluate` 用既有的 `valve` relation（`kv`、`opening_ratio`、`density_kg_m3`），**不新增 relation kind**，
因此 v1 的求解器路径即可求解。开度构造：

```
opening = 0                                            , Δp ≤ p_crack 或 opening_max = 0
opening = opening_max · sqrt(max(0, 1 − p_crack/Δp))   , Δp > p_crack
```

把 `opening` 代入 `Δp = 1e5·(ρ/1000)·Q|Q|/(Kv·opening)²` 恰好还原独立参考曲线

```
Q [m³/h] = Kv · opening_max · sqrt( (Δp − p_crack) / (1e5·ρ/1000) )
q [kg/s] = Q · ρ / 3600
```

即“开启压差 + 阀门阻力”串联，`Δp → p_crack⁺` 时 `q → 0`，与关闭约束衔接连续。
`opening_ratio == 0` 必须是**精确 0.0**（不能是 `1e-12`），否则求解器会得到约 `1e18` Pa 量级的
假压降；`evaluate` 在 `sqrt` 下溢到 0 时也返回精确 0.0，与 `Δp = p_crack` 处的物理解一致。

`evaluate` 只读参数、试算端口与（仅在 `hysteresis_pa > 0` 时）只读 state，因此对同一试算输入与同一
accepted state 幂等；`commit_step` 才写 `ctx.state`，且只在被接受的子步调用。

### 5.4 独立 Δp–q 参考与验收入口（V0/V1）

- `backend/fn_engine/check_valve.py`：不依赖 numpy/scipy/solver 的解析曲线生成器
  （`reference_mass_flow_kg_s`、`reference_pressure_drop_pa`、`curve_points`）、开关判据
  （`is_open`/`required_opening`）、互补残差（`opening_slack_pa`/`complementarity_residual`）、
  迟滞状态机（`next_open_state`）与方案 (a) 对照（`smooth_*`）。
- 模块自带同一公式的自包含实现（Worker 不 import `fn_engine`），两者由测试逐点对照，不靠人工同步。
- `tests/test_check_valve_numerics.py`：曲线逐点对照、阈值两侧、冷/热启动、泵旁路、并联、
  迟滞纯函数、幂等、动态扫压差、版本升级/回滚、无参考段限制。
- 实测数字见 `docs/numerics/results/V0.md`（语义与曲线）、`V1.md`（方案比较与迭代/RPC）、`V2.md`（发布与动态验收）。

### 5.5 V1 方案比较结论（二选一）

比较了两类方案，**选择方案 (b) 互补/活动集（本实现为关系层互补 + 精确零流量约束）**：

- **(a) 光滑过渡（tanh 门，C∞，有界泄漏）**：没有真正的开启压差（`Δp = p_crack` 处开度已是 0.5，
  实测 `Δp=5001 Pa` 流量 1.5547 kg/s，而 (b) 为 0.0439 kg/s），且门在远离临界点时指数变小，
  `opening ≈ 1e-9` 一类的极小开度把支路压降推到 `1e5+ Pa` 量级：实测 width=500 Pa 时
  `Δp ∈ {1, 0, −1, −1000} Pa` 全部 `HydraulicNotConverged`（其中 −1000 Pa 压力残差 415823 Pa），
  `Δp=1000 Pa` 需 31 次 nfev；width=100 Pa 时 4000 Pa 需 74 次 nfev 且 1000 Pa 以下开度下溢为 0。
  这正是计划里禁止的“用极小开度近似精确关断”。
- **(b) 互补/活动集（精确零流）**：`Δp ≤ p_crack` 直接走求解器既有的 `flow == 0` 约束，反向与
  亚开启区质量精确为 0；开关点放在两支路汇合处，残差连续。实测临界带 nfev：`5001 Pa` 6 次、
  `5000.01 Pa` 10 次、`5000 Pa` 及以下 2 次，均收敛到默认容差，没有靠减小 dt 修稳态。
  代价是 C0（非 C1）与临界点附近的刚度，已在 §5.1 冻结。

### 5.6 可选迟滞与求解器集成提案（V2 条件项，默认不启用）

默认 `hysteresis_pa = 0`，`evaluate` 与 accepted state 无关，现有求解器无需改动。`> 0` 时冻结的
纯转移函数（`backend/fn_engine/check_valve.py`）：

```python
is_open(delta_p, p_crack, hysteresis, was_open):
    Δp ≤ 0 → False                                    # 反向恒关，与迟滞无关
    hysteresis == 0 → Δp > p_crack                    # 静态互补
    was_open False → Δp > p_crack + hysteresis        # 开启阈值抬高
    was_open True  → Δp > max(0, p_crack − hysteresis) # 关闭阈值下移
```

启用 `hysteresis_pa > 0` 后，动态按 accepted 步推进已经自洽：每次 `evaluate` 用上一次接受步的
`is_open` 与当前试算 Δp 判定，`commit_step` 用同一转移函数更新状态。实测（V2 §2）：路径相关符合
迟滞语义，反向始终精确零流，累计反向质量为 0；因此**动态路径不需要求解器改动**。若还需要
“同一步内活动集自洽”（控制步内重解、或稳态从一个可能过期的活动集出发），再接入外层活动集：
一次 `_solve_hydraulics` 收敛后，用收敛压差/流量检查互补性并在同一时间步内翻转 `state.is_open`
后重解，直到活动集稳定（上限 N 次，超限报可诊断错误），只有最终活动集对应的解才交给
`commit_step`。集成提案（签名、插入点、判据、预期迭代）见 `docs/numerics/results/V2.md` §2.3；
本包**未接入**，默认发布参数 `hysteresis_pa = 0`。

### 5.7 发布、兼容升级与回滚

- 发布形态：同 id 新版本目录 `modules/check_valve_v2/`（`version=2`），`release.json` 记录
  `tested=true`、试算条件与发布说明；v1 目录逐字节不动（测试锁定其 `content_hash`）。
- 模块目录 `/api/v1/modules` 取最新版本（check_valve → v2）；`/api/v1/modules/check_valve/versions`
  同时返回 `2.0.0` 与 `1.0.0`，两个版本的源码与契约哈希独立可查。
- 升级：只能显式走 `POST /api/v1/project-upgrades/preview`（`backend/fn_engine/projects.py`），
  预览返回 `changes`（参数/变量/源码变化）与 `compatible`；v1→v2 实测 `compatible=true`，且
  `changes` 里明确列出 `p_crack_pa`、`hysteresis_pa` 新增与 `cracking_pressure_pa` label 变更。
  用户确认后实例参数、参数库与 `package` 绑定一并更新到 `2.0.0`。
- 回滚：预览不写库、失败/拒绝时项目文档逐字段不变（实测 `model_dump()` 前后相等）；已保存的
  旧项目快照继续绑定 v1 定义与源码，可继续 `compile_project` + `solve_steady`（旧行为不变）。
  运行期回滚 = 用 v1 快照重存/重跑，不做自动降级。

### 5.8 已知边界与剩余限制

- **Python 关闭产生无参考段**：若关闭的 Python 支路是某个子网唯一连接，运行报
  `模块通路关系产生了缺少压力参考的子网络`（实测复现）。动态时间步的“被动段保压近似”只看内置
  被动支路，运行期由 Python 模块决定的关断不在其内；需要在关闭后仍保持连接的一侧保留压力边界/
  泵/其它支路。这是关系层活动集的**剩余限制**，要根治需要运行时重建依赖（计划 I5+ 或 D2 范围）。
- `evaluate` 契约拿不到流量，开关判据只能基于压差；流量方向只能由收敛结果事后检查；
  所以“流量为负但压差为正”的病态工况不会在 evaluate 内被发现。
- 热力：关闭支路沿用既有零流量热语义（`NO_FLOW_HEAT` 前提），v2 不输出 `heat_w`。
- `state.closed_steps` 只统计被接受的步；稳态计算不提交，恒为 0。
- 冷/热启动都可能更快：从大流量跳到临界附近时热启动不一定更省（实测 `5001 Pa`：冷 6 次、
  热 11 次 nfev），不宣称 warm 一定更优。
- 可选迟滞尚未默认启用，外层活动集未接入（§5.6）。

