# P1 模块详细设计：cooling_tower / fan / pump_variable_speed

> 适用 `fluidnet-prototype-engine` 0.4.10，`schema_version = 1`。合同唯一来源是 `backend/fn_engine/models.py`（Pydantic v2），本文与之冲突时以模型为准。
> 本文只定义三个 Python 模块包的**行为与接口**；实现落在 `modules/<id>/{manifest.json,module.py,README.md}`，`design.py` 本批不需要。
> 前置阅读：`docs/MODULE_KIT.md`（下称 KIT）、`docs/MODULES_P0.md`（下称 P0）、`modules/programmable_valve/*`、`modules/fan_coil_unit/*`。
> 表头约定：`canonical → display（scale / offset）`；参数默认值、上下限、模块内拿到的值**一律 canonical**。
> 实现状态（2026-10-22）：三个包已在 `modules/{cooling_tower,fan,pump_variable_speed}/` 落地，`tests/test_bsl_modules_p1.py` 7 项通过（与 P0 合计 14 项）。本文与实现一致；若后续骨架变更，以本文接口表为准并同步实现。

## 接口总览

| 模块 | 端口（均 fluid，required） | 通路 | relation / solver_model | 参数 | 派生变量 | 状态变量 | 用例 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cooling_tower` | `in0` → `out0` | `main` | `resistance` / `pipe` | 13 | `heat_flow_w`（平台别名 `heat_w`）、`water_outlet_temperature_k`、`air_outlet_temperature_k`、`effectiveness`、`approach_k` | `state.thermal_energy_j` | 3 |
| `fan` | `in0` → `out0` | `main` | `pump_curve` / `pump` | 7 | `pressure_rise_pa`、`shaft_power_w`、`electric_power_w` | `state.shaft_energy_j`、`state.electric_energy_j` | 3 |
| `pump_variable_speed` | `in0` → `out0` | `main` | `pump_curve` / `pump` | 7 | `pump_head_m`、`shaft_power_w`、`electric_power_w` | `state.shaft_energy_j`、`state.electric_energy_j` | 3 |

\* 平台会为单通路实例生成 `<I>.heat_w` 别名；本批与 P0 的 `fan_coil_unit` 保持一致，模块用 `heat_flow_w` 显式输出水侧换热量，**不输出** `heat_w`，两者数值应相等。三个包合计 **9 个设计用例**（CT-1..3 / FAN-1..3 / PVS-1..3），与 P0 的 12 个用例格式一致。

## 0. 三个模块共同的前提

- evaluate 里 `ctx.channel()` 恒为空值、`ctx.port(p).mass_flow_kg_s` 恒为 `None`；只有 `commit_step` 能读真实流量与压差（`runtime.py:111-112`、`solver.py:225-232`、`:850-856`）。
- evaluate 收到深拷贝：改 `ctx.state` 不生效，只有 `commit_step` 的修改会提交（`runtime.py:198-199`、`:206-211`）。
- 每条启用通路必须**恰好**返回一条关系，`channel` 与 `ChannelSpec.id` 同名；关系集合先校验、error 诊断后抛出（`solver.py:257-265`）。
- `relation="pump_curve"` 的模块必须注册 `kind="pump"` 的关系；`NetworkRelation` 对曲线有硬校验（`models.py:192-198`），`solver.pump_head` 按相似律缩放，工作点超出 `[0, 末点流量×speed_ratio]` 或出现反向流时求解器直接报错（`solver.py:81-91`、`:392-398`）。
- Python 模块的 pump/compressor 关系**没有效率字段**：求解器把这些通路的轴功取为 `−Δp·m/ρ` 并计入流体焓（`solver.py:415-433`、`thermal.py:424-428`）。模块声明的 `heat_w` 是在此之外**额外**的热，故 fan/pump 一律传 `heat_w=0`，否则重复计热。
- `curve` 类型参数不能声明 `unit`（`models.py:73-74`），模块收到的点对是 canonical 数值；编译期只对 **id 恰为 `head_curve`** 的参数做 `CURVE_INVALID` 校验（`compiler.py:166-172`），`pressure_curve` 必须由模块自行归一化。
- 平台只为**单通路**实例生成 `<I>.heat_w` 等别名（`solver.py:693-694`）；`<I>.shaft_power_w` 只给内置泵生成，Python 模块的同名输出不会被平台占用（`solver.py:695-696`）。
- 冷却塔必须开热力层（`solver.thermal=true`）；fan 可以开热力层（轴功会加热空气），但三个模块的气侧/水侧都**不做两相**，也不做湿空气焓差。

---

## 1. cooling_tower（冷却塔）

### 1.1 用途与倍思鹿语义

水在塔内与空气直接接触降温，水侧是管网中的一条阻力支路，向流体声明**负的** `heat_w`（水放热）；空气侧不建网络，用集总热容 + 逆流 ε-NTU 与湿球温度代数耦合。倍思鹿 `AlgModule/冷却塔`（矩阵第 13 行）在 `FANRUN ≥ 0.5` 分支把出口比焓硬编码为 `134.1818 kJ/kg`（约 32 °C 水），风机停转才等焓旁通，属演示级行为（`BSL_MODULE_MAP.md` §4.2）；FluidNet 只保留其“逼近度/湿球”语义，用 ε-NTU 与显热平衡重写，不复刻硬编码，也不反推其填料关联式。

### 1.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `cooling_tower` / `冷却塔` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model="pipe"`） |
| 端口 | `in0`（`in`，fluid，required，`fluid`）、`out0`（`out`，fluid，required，`fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="resistance"`，`solver_model="pipe"`，`enabled=true` |

空气侧没有端口：模块包只允许 `domain=fluid`（`compiler.py:365-367`），且风侧没有压力/流量来源；`air_flow_m3_s` 是给定风量而不是求解结果（与 P0 `fan_coil_unit` 同口径）。

### 1.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `ua_w_k` | number | `20000` | `≥ 0` | W/K → kW/K（scale 0.001） |
| `water_side_diameter_m` | number | `0.1` | `≥ 1e-4` | m → mm（0.001） |
| `water_side_length_m` | number | `2` | `≥ 0` | m → m |
| `roughness_m` | number | `1.5e-6` | `≥ 0` | m → mm（0.001） |
| `air_flow_m3_s` | number | `3.0` | `≥ 0` | m³/s → m³/h（1/3600） |
| `air_inlet_temperature_k` | number | `300.15` | `≥ 1` | K → °C（1 / −273.15） |
| `air_inlet_relative_humidity` | number | `0.5` | `[0, 1]` | 1 → %（0.01） |
| `air_wet_bulb_temperature_k` | number | `300.15` | `≥ 1` | K → °C（1 / −273.15） |
| `air_density_kg_m3` | number | `1.15` | `≥ 0.01` | kg/m³ |
| `air_cp_j_kg_k` | number | `1006` | `≥ 100` | J/(kg·K) → kJ/(kg·K)（1000） |
| `water_cp_j_kg_k` | number | `4180` | `≥ 100` | J/(kg·K) → kJ/(kg·K)（1000） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ |
| `viscosity_pa_s` | number | `0.001` | `≥ 0` | Pa·s → mPa·s（0.001） |

`air_inlet_relative_humidity` 只作登记与后续湿工况提示，本模型**不**用它算潜热；湿球温度由独立参数给出（平台没有湿球物性换算，KIT §4 明确对数/分段量不进线性换算）。编译期的 `diameter_m`+`roughness_m` 联检不会触发（id 是 `water_side_diameter_m`），零/负值由本表下限与模块内 clamp 共同兜住。

### 1.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `heat_flow_w` | 水侧换热量（负=水放热） | derived | W → kW（1000） |
| `water_outlet_temperature_k` | 水出口温度 | derived | K → °C（1 / −273.15） |
| `air_outlet_temperature_k` | 空气出口干球温度 | derived | K → °C（1 / −273.15） |
| `effectiveness` | 换热效能 ε | derived | 1 → %（0.01） |
| `approach_k` | 逼近度 `T_water,out − T_wb` | derived | K → K（温差无 offset） |
| `state.thermal_energy_j` | 累计水侧换热量（负=放热） | state | J → kJ（1000） |

**`heat_w` 与 `heat_flow_w` 的落地方式**：单通路实例的帧里，平台会生成 `<I>.heat_w` 与 `<I>.main.heat_w`（`solver.py:688-694`），其值是该通路焓流增量；本模块注册的是 `pipe` 关系（无轴功、无标高），所以它严格等于关系里声明的 `heat_w=−Q`。模块若再 `ctx.var("heat_w", ...)` 会命中“模块输出不能覆盖网络求解变量”（`solver.py:710-712`），因此 manifest 声明并输出 `heat_flow_w`，平台别名 `heat_w` 保留、数值与 `heat_flow_w` 相同。这样 `thermal=false` 时模块仍能给出代数换热量；`MODULE_OUTPUT_MISSING` 只检查声明的输出键（`packages.py:136-138`），`heat_flow_w` 已满足。P0 的 `fan_coil_unit` 采用同一命名约定，两批口径一致。

### 1.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("thermal_energy_j", 0.0)`。
2. 取参数并 clamp：`d=max(water_side_diameter_m,1e-4)`；`L=max(water_side_length_m,1e-6)`（`pipe` 要求 `length_m>0`，`models.py:186-187`；被截断报 `CT_LENGTH_CLAMPED`）；`ε=max(roughness_m,0)`；`ρ=max(density_kg_m3,1e-3)`；`μ=max(viscosity_pa_s,1e-6)`（`pipe_drop` 用它除 Re，0 会除零，`solver.py:68-78`；被截断报 `CT_VISCOSITY_FALLBACK`）；`cp_w=max(water_cp_j_kg_k,100)`、`cp_a=max(air_cp_j_kg_k,100)`、`ρ_a=max(air_density_kg_m3,0.01)`、`V_a=max(air_flow_m3_s,0)`、`UA=max(ua_w_k,0)`。
3. **反解水侧流量**（端口优先）：若 `inlet.mass_flow_kg_s` 非空（commit 的收敛端口就是），`m=|mass_flow|`；否则用试算压差 `dp=|p_in−p_out|`，对**与 `solver.pipe_drop` 逐行相同**的 `_pipe_drop` 在 `m∈[0,1e4] kg/s` 上二分 80 次（层流 `32μLm/(ρAd²)`、Colebrook、`Re≤2300` 层流、`2300<Re<4000` 线性混合 `(Re−2300)/1700`，`solver.py:68-78`）；端口压力缺失记 `m=0` 并报 `CT_PRESSURE_UNKNOWN`。反解与注册关系**使用同一组参数 ρ/μ**（不取端口物性），否则水力迭代里流量会来回漂移。
4. 水入口温度：`T_in = inlet.temperature_k`；为 `None` 时取 `T_wb` 并报 `CT_INLET_TEMPERATURE_UNKNOWN`（此时 `Q=0`）。不新增 `water_inlet_temperature_k` 参数，保持既定接口。
5. 容量：`C_w=|m|·cp_w`、`C_a=ρ_a·V_a·cp_a`、`C_min=min(C_w,C_a)`、`C_max=max(C_w,C_a)`；仅当 `|m|>1e-6`、`UA>0`、`C_a>0`、`C_min>0` 时继续，否则 `Q=0, ε=0` 并给对应诊断（§1.6）。
6. ε-NTU（逆流）：`Cr=C_min/C_max`、`NTU=UA/C_min`；`|1−Cr|<1e-9` 时 `ε=NTU/(1+NTU)`，否则 `ε=(1−exp(−NTU(1−Cr)))/(1−Cr·exp(−NTU(1−Cr)))`；把 ε 截到 `[0,1)` 防浮点越界。
7. 换热量：`ΔT=max(0, T_in−T_wb)`（`T_in≤T_wb` 时 `Q=0` 并报 `CT_WATER_BELOW_WET_BULB`，避免把“水被加热”写进冷却塔账本）；`Q=ε·C_min·ΔT`；`heat_w=−Q`（水放热）。派生量：`T_w,out=T_in−Q/C_w`、`T_a,out=T_air,in+Q/C_a`、`approach=T_w,out−T_wb`。
8. 注册关系：**始终** `ctx.net.pipe(channel="main", length_m=L, diameter_m=d, roughness_m=ε, density_kg_m3=ρ, viscosity_pa_s=μ, heat_w=heat_w)`；零流量/零 UA 时 `heat_w=0`，因此不会触发 `NO_FLOW_HEAT`（`thermal.py:243-249`）。热力层按 `h_out=h_in+heat_w/|m|` 施加（`thermal.py:426-428`），水出口温度由平台焓方程给出，模块变量只是代数校核值。
9. 输出：`ctx.var("heat_flow_w", heat_w)`、`ctx.var("water_outlet_temperature_k", …)`、`air_outlet_temperature_k`、`effectiveness`、`approach_k`；**不输出 `heat_w`**；每帧一次 `CT_LATENT_IGNORED`（info）。
10. `commit_step`：用收敛端口重算步骤 2–7（此时流量是真实值），`ctx.state["thermal_energy_j"] += heat_w*dt_s`（有符号累计，负=塔从水中取热）。

**数值自检（Cr→1 极限分支）**：取 `m=C_a/cp_w=3470.7/4180=0.830311 kg/s`，则 `Cr=1`、`NTU=5.762526`，应得 `ε=NTU/(1+NTU)=0.852126`、`Q=29574.75 W`、`T_a,out=308.671 K`。若实现误用 `Cr<1` 公式，此处会得到 `ε≈1` 或除零。

### 1.6 诊断码

| code | severity | 触发 | message 要点 / 处理 |
| --- | --- | --- | --- |
| `CT_LATENT_IGNORED` | info | 每次 evaluate | 干空气显热模型：未计蒸发潜热、水耗、飘水与填料关联式，Q 仅作显热近似 |
| `CT_ZERO_WATER_FLOW` | info | `|m| ≤ 1e-6 kg/s` | 本帧不换热，`heat_w=0`；避免 `heat_w/m` 爆炸与 `NO_FLOW_HEAT` |
| `CT_UA_DISABLED` | info | `ua_w_k ≤ 0` | 仅水力阻力，`heat_w=0`、`ε=0` |
| `CT_AIR_FLOW_ZERO` | warning | `air_flow_m3_s ≤ 0` 或 `air_density_kg_m3 ≤ 0` | 风侧无热容，`Q=0`；请检查风量/密度 |
| `CT_WATER_BELOW_WET_BULB` | warning | `T_in ≤ T_wb` | 按不换热处理（Q=0），逼近度无物理意义 |
| `CT_PRESSURE_UNKNOWN` | info | 试算压力缺失 | 流量记 0，本帧不换热 |
| `CT_INLET_TEMPERATURE_UNKNOWN` | info | 入口温度缺失 | 入口温度按湿球温度处理，本帧不换热 |
| `CT_VISCOSITY_FALLBACK` | warning | `viscosity_pa_s ≤ 0` | 已按 1e-6 Pa·s 计算，Re 与压降不可信 |
| `CT_LENGTH_CLAMPED` | info | `water_side_length_m < 1e-6` | 已按 1e-6 m 注册，避免 `length_m>0` 校验失败 |

### 1.7 测试用例（独立验证台 `POST /api/v1/modules/test`）

共用条件：`fluid=Water`、`temperature_k=310.15`、`duration_s=0.5`、`dt_s=0.1`；取**最终帧**（commit 已覆盖派生量）；容差：流量相对 1e-3、温度/逼近度 0.3 K、`heat_flow_w`/能量相对 1e-3、ε 绝对 1e-6。帧键前缀 `D1.`；帧里 `D1.heat_w`（平台别名）与 `D1.heat_flow_w`（模块输出）应相等。

| # | 输入 | 期望 |
| --- | --- | --- |
| CT-1 | 默认参数，`water_side_diameter_m=0.025`；`inlet=200000`、`outlet=197500` | `main.mass_flow_kg_s≈0.833405`（3.006 m³/h）、`heat_flow_w≈−29621.4`、`effectiveness≈0.853472`、`water_outlet_temperature_k≈301.647`、`air_outlet_temperature_k≈308.685`、`approach_k≈1.497`、`state.thermal_energy_j≈−14810.7`；`D1.heat_w==D1.main.heat_w==D1.heat_flow_w`；诊断含 `CT_LATENT_IGNORED` |
| CT-2 | `ua_w_k=0`，其余同 CT-1 | 流量与压降同 CT-1；`heat_flow_w=0`、`effectiveness=0`、`water_outlet_temperature_k=310.15`、`air_outlet_temperature_k=300.15`、`approach_k=10.0`、`state.thermal_energy_j=0`；诊断含 `CT_UA_DISABLED`、`CT_LATENT_IGNORED` |
| CT-3 | `inlet=200000`、`outlet=200000`，其余同 CT-1 | `main.mass_flow_kg_s≈0`（|m|≤1e-8）、`heat_flow_w=0`、`effectiveness=0`、`water_outlet_temperature_k=310.15`、`approach_k=10.0`、`state.thermal_energy_j=0`；诊断含 `CT_ZERO_WATER_FLOW`，且**不得**出现 `NO_FLOW_HEAT` |

### 1.8 局限与后续

- 干空气显热模型：不计蒸发潜热、水耗/补水、飘水、填料高度与淋水密度；`air_inlet_relative_humidity` 不进入 ε-NTU。湿球温度是外部输入，不是由干球+湿度反算。
- 冷源温度取湿球温度近似，等价于“填料无限高、空气出口饱和”的极限；实际塔的逼近度由填料特性（`KaV/L`）决定，本模型只能用 UA 拟合。
- 空气侧不建网络：无风机曲线、风管阻力、风量—静压耦合；`air_flow_m3_s` 是给定值。风机功耗请另接 `fan` 实例或按参数计入外部账。
- 水侧密度/黏度取参数而与水温解耦（约 20 °C 水）；37 °C 时密度偏低约 0.5%，压降随之偏差同量级。这样做是为了让“反解”和“注册关系”使用同一组数，保证收敛。
- `heat_flow_w` 是模块自算值，`thermal=false` 时仍可用；平台别名 `heat_w` 依赖 `thermal=true`，缺席时只影响别名键。
- 冷却塔的入口水温是网络反馈量：推荐 `solver.property_coupling="node"`，让 `T_in` 在耦合迭代中收敛；默认 `reference` 模式下入口温度取初值/边界值，`Q` 与网络温度无反馈（`solver.py:569-606`）。
- 后续：湿工况（空气焓差 + 潜热 + 水耗）、`UA` 随风量/水量修正、逼近度反算填料特性、风机与塔一体建模。

---

## 2. fan（风机）

### 2.1 用途与倍思鹿语义

风机是气体管路上的压升元件：把厂商“体积流量—静压”曲线换算成扬程曲线，交给求解器的泵关系求解工作点；模块补效率、轴功率、电功率与能量账本。倍思鹿 `AlgModule/风机`（矩阵第 9 行）以风量—静压曲线 + 气体密度 + 风机热为核心，FluidNet 的 `pump` 关系只认扬程曲线，所以 `H=Δp/(ρg)` 是语义桥；这也意味着“风机热”在本模型中由求解器自动按轴功注入，不需要模块再声明热。

### 2.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `fan` / `风机` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model="pump"`） |
| 端口 | `in0`（`in`，fluid，required，`fluid`）、`out0`（`out`，fluid，required，`fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="pump_curve"`，`solver_model="pump"`，`enabled=true` |

端口 `domain` 仍是 `fluid`；气体由项目 `FluidConfig`（如 `Air`）决定，模块不声明气体领域。`solver_model` 是自由字符串，Python 模块跳过 `CHANNEL_MODEL_INVALID`，这里写 `pump` 与关系 kind 一致。

### 2.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `pressure_curve` | curve | `[[0,300],[2000,250],[4000,120],[5000,0]]` | 见 §2.5 归一化 | 点对 `[m³/h, Pa]`（curve 不能声明 unit） |
| `speed_ratio` | number | `1.0` | `[0.05, 2]`，`runtime=true` | 1 → 倍（1） |
| `efficiency` | number | `0.6` | `[0.05, 1]` | 1 → %（0.01） |
| `motor_efficiency` | number | `0.9` | `[0.05, 1]` | 1 → %（0.01） |
| `air_density_kg_m3` | number | `1.2` | `≥ 0.01` | kg/m³ |
| `air_viscosity_pa_s` | number | `1.8e-5` | `≥ 0` | Pa·s → mPa·s（0.001）；仅登记，当前不参与计算 |
| `nominal_flow_m3_h` | number | `2000` | `≥ 0` | m³/h → m³/h |

`g` 不暴露，模块内取常量 `9.80665`（与 `solver.GRAVITY` 一致）。`speed_ratio` 设 `runtime=true`，允许 PID/日程在运行中改转速（KIT §3.4）；`pressure_curve` 是不可写曲线。

### 2.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `pressure_rise_pa` | 风机压升（设计点 / 收敛点） | derived | Pa → kPa（1000） |
| `shaft_power_w` | 轴功率 | derived | W → kW（1000） |
| `electric_power_w` | 电功率 | derived | W → kW（1000） |
| `state.shaft_energy_j` | 累计轴功 | state | J → kJ（1000） |
| `state.electric_energy_j` | 累计电功 | state | J → kJ（1000） |

`<I>.shaft_power_w` 的平台别名只给内置泵（`solver.py:695-696`），Python 模块安全使用该 id；`pressure_rise_pa` 与平台的 `main.pressure_drop_pa`（=p_in−p_out，风机为负）不重名。

### 2.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("shaft_energy_j", 0.0)`、`ctx.state.setdefault("electric_energy_j", 0.0)`。
2. clamp：`s∈[0.05,2]`（越界报 `FAN_SPEED_CLAMPED`）、`η∈[0.05,1]`、`η_m∈[0.05,1]`（报 `FAN_EFFICIENCY_CLAMPED`）、`ρ=max(air_density_kg_m3,0.01)`。
3. **压力曲线归一化**（每次 evaluate 都做，纯函数）：逐点校验 `[q, Δp]` 为两个有限数，否则 `FAN_CURVE_INVALID`（error，按默认曲线注册关系后再报错，保证诊断可见）；按 q 升序排序、`q<0` 取 0、`Δp<0` 取 0、同 q 去重（保最后一点）；若剩余点 <2 或所有 Δp 都为 0 → `FAN_CURVE_INVALID`。首点 q 若非 0 则置 0（保留其 Δp），末点 Δp 若非 0 则置 0，均报 `FAN_CURVE_CLIPPED`（warning）。
4. 换算扬程：`H_i=Δp_i/(ρ·g)`。从倒数第二点向前做单调包络：若 `H_i ≤ H_{i+1}`，取 `H_i=H_{i+1}+δ`（`δ=max(1e-6, 1e-6·H_{i+1})`）并报 `FAN_CURVE_CLIPPED`；输出 `list[list[float]]`（必须是 `list` 而非 tuple，`models.py:195` 要求）。
5. 设计点（evaluate 没有真实流量）：`Q_n=nominal_flow_m3_h`、`x=Q_n/s`；在归一化曲线上线性插值（`x` 超出末点取末点 H=0 并报 `FAN_NOMINAL_CLAMPED`，info）；`Δp_n=ρ·g·s²·H(x)`、`P_hyd,n=Δp_n·Q_n/3600`、`P_shaft,n=P_hyd,n/η`、`P_elec,n=P_shaft,n/η_m`。
6. 注册：`ctx.net.pump(channel="main", head_curve=H, speed_ratio=s, density_kg_m3=ρ, heat_w=0.0)`。相似律由求解器处理（`solver.py:81-91`、`:109-112`）；`heat_w=0` 是因为该关系的轴功已由求解器计入流体焓（`solver.py:424-432`、`thermal.py:424-428`），重复声明会翻倍。
7. evaluate 输出：`ctx.var("pressure_rise_pa", Δp_n)`、`shaft_power_w=P_shaft,n`、`electric_power_w=P_elec,n`。首帧/稳态帧看到的是**设计点**值；动态帧会被 commit 覆盖。
8. `commit_step`：`m=|channel("main").mass_flow_kg_s|`、`Δp=|channel("main").pressure_drop_pa|`；`P_hyd=Δp·m/ρ`、`P_shaft=P_hyd/η`、`P_elec=P_shaft/η_m`；`ctx.state["shaft_energy_j"] += P_shaft·dt_s`、`electric_energy_j += P_elec·dt_s`；`ctx.var("pressure_rise_pa", Δp)`、`shaft_power_w`、`electric_power_w`（用收敛值覆盖设计点，避免帧自相矛盾）。
9. 效率为定值：不建模效率随流量/转速变化，也不建模失速区（见 §2.8）。

**换算示例**（默认曲线、`ρ=1.2`）：扬程点 `[25.4929, 21.2441, 10.1972, 0] m`；`Q=2000 m³/h` 时 `Δp=250 Pa`、`m=0.666667 kg/s`、`P_hyd=138.89 W`、`P_shaft=231.48 W`、`P_elec=257.20 W`。

### 2.6 诊断码

| code | severity | 触发 | message 要点 / 处理 |
| --- | --- | --- | --- |
| `FAN_CURVE_CLIPPED` | warning | 首点流量归零/末点压升归零/相邻点不严格递减 | 已按归一化曲线注册，给出改动点与原值 |
| `FAN_CURVE_INVALID` | error | 点结构非法、可用点 <2、所有压升为 0 | 结果不可信；先按默认曲线注册关系再报错，运行失败 |
| `FAN_NOMINAL_CLAMPED` | info | `nominal_flow_m3_h/s` 超出曲线末点 | 设计点压升按 0（末点）报出；请检查设计流量 |
| `FAN_SPEED_CLAMPED` | warning | `speed_ratio` 超出 `[0.05,2]` | 已截断，给出原值与相似律影响 |
| `FAN_EFFICIENCY_CLAMPED` | warning | `efficiency`/`motor_efficiency` 超出 `[0.05,1]` | 已截断；电功率按截断值计算 |

### 2.7 测试用例

共用条件：`fluid=Air`、`temperature_k=293.15`、`duration_s=0.5`、`dt_s=0.1`；取**最终帧**；容差：流量相对 2e-3（风机工作点对 1 Pa 压力容差较敏感）、功率/能量相对 1e-3、压升 0.5 Pa。

| # | 输入 | 期望 |
| --- | --- | --- |
| FAN-1 | 默认参数；`inlet=101325`、`outlet=101575`（Δp=250 Pa） | `main.mass_flow_kg_s≈0.666667`（2000 m³/h）、`pressure_rise_pa=250`、`shaft_power_w≈231.48`、`electric_power_w≈257.20`、`state.shaft_energy_j≈115.74`、`state.electric_energy_j≈128.60`；无 `FAN_CURVE_CLIPPED` |
| FAN-2 | `speed_ratio=0.8`；`inlet=101325`、`outlet=101464.2`（Δp=139.2 Pa） | `main.mass_flow_kg_s≈0.666667`（2000 m³/h，压升按 `s²·Δp_curve(Q_n/s)` 折算）、`pressure_rise_pa≈139.2`、`shaft_power_w≈128.89`、`electric_power_w≈143.21`、`state.shaft_energy_j≈64.44`、`state.electric_energy_j≈71.60` |
| FAN-3 | `pressure_curve=[[0,300],[2000,250],[4000,120],[5000,80]]`、`nominal_flow_m3_h=4000`；`inlet=101325`、`outlet=101445`（Δp=120 Pa） | 诊断含 `FAN_CURVE_CLIPPED`（末点 80→0 Pa）；`pressure_rise_pa=120`、`main.mass_flow_kg_s≈1.333333`（4000 m³/h）、`shaft_power_w≈222.22`、`electric_power_w≈246.91`、`state.shaft_energy_j≈111.11`、`state.electric_energy_j≈123.46` |

### 2.8 局限与后续

- 气体按不可压、单相处理：`Δp` 仅数百 Pa，密度变化对压升的影响远小于 1%；不做压缩性修正。`air_viscosity_pa_s` 当前只登记，`pump` 关系不使用它，**不得**据此声称做了雷诺修正。
- 密度取参数常量：热力层算出的空气温升不会反馈到扬程曲线（关系里带 `density_kg_m3` 覆盖，`solver.py:100-112`）；高温/高海拔工况需人工改密度。
- 效率是定值，不含效率—流量曲线、电机变频效率、皮带/轴承损失随负载变化；电功率=轴功/η_motor。
- 只把流体获得的**水力功**计入空气焓；`(P_elec−P_hyd)` 的损失作为外部热源，不进入气流。若后续要把电机/风机损失也注入气流，应把该差值写入 `heat_w` 并升版（会改变能量残差口径）。
- 不建模噪声、失速/喘振区、风量—静压曲线的滞回；求解器在反向流或曲线外工作点直接报错（`solver.py:392-398`），这是有意的硬边界。
- 后续：效率曲线、变频器效率、气体密度随温度/压力修正、风机与风管/冷却塔的一体化。

---

## 3. pump_variable_speed（泵·变速）

### 3.1 用途与倍思鹿语义

在管网中提供可变转速的离心泵压升，并补齐效率、轴功率、电功率与能量账本。倍思鹿 `AlgModule/泵迭代法`（矩阵第 8 行）的核心是**变物性内迭代**（`FUD_TRNPRP`）与由压差反解转速；FluidNet 的变物性由 `solver.property_coupling="node"` 的外层耦合承担（`solver.py:583-606`），本模块**不实现也不声称实现** `FUD_TRNPRP`，只做“泵曲线 + 相似律 + 效率/电功率/变速 + 账本”。这也是本模块与内置 `pump`（矩阵第 7 行“泵曲线法”）的分工：内置泵已经能算扬程与轴功，本模块的价值在可写转速、效率链与累计能量。

### 3.2 端口、通路与 manifest 关键字段

| 项 | 值 |
| --- | --- |
| `id` / `name` / `category` | `pump_variable_speed` / `变速泵` / `倍思鹿参考模块` |
| `entrypoint` / `source_format` / `solver_model` | `module:Module` / `python-v1` / `generic`（通路 `solver_model="pump"`） |
| 端口 | `in0`（`in`，fluid，required，`fluid`）、`out0`（`out`，fluid，required，`fluid`） |
| 通路 | `main`：`in0 → out0`，`relation="pump_curve"`，`solver_model="pump"`，`enabled=true` |

### 3.3 参数

| id | 类型 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- | --- |
| `head_curve` | curve | `[[0,20],[10,18],[20,12],[30,0]]` | 首点 x=0、末点 y=0、x 递增、y 严格递减 | 点对 `[m³/h, mH₂O]`（curve 不能声明 unit） |
| `speed_ratio` | number | `1.0` | `[0.05, 2]`，`runtime=true` | 1 → 倍（1） |
| `efficiency` | number | `0.7` | `[0.05, 1]` | 1 → %（0.01） |
| `motor_efficiency` | number | `0.9` | `[0.05, 1]` | 1 → %（0.01） |
| `density_kg_m3` | number | `998.2` | `≥ 1` | kg/m³ |
| `viscosity_pa_s` | number | `0.001` | `≥ 0` | Pa·s → mPa·s（0.001） |
| `nominal_flow_m3_h` | number | `10` | `≥ 0` | m³/h → m³/h |

参数 id 恰为 `head_curve`，因此编译期会走 `CURVE_INVALID` 校验（`compiler.py:166-172`）；模块内仍保留一次防御性校验，供直接 API/手工调用。`speed_ratio` 可写是“变速”的接口面；改值走 `set`/PID/日程，模块在 evaluate 里自然读到新值。

### 3.4 变量

| id | label | source | 单位 |
| --- | --- | --- | --- |
| `pump_head_m` | 泵扬程（设计点 / 收敛点） | derived | m → m |
| `shaft_power_w` | 轴功率 | derived | W → kW（1000） |
| `electric_power_w` | 电功率 | derived | W → kW（1000） |
| `state.shaft_energy_j` | 累计轴功 | state | J → kJ（1000） |
| `state.electric_energy_j` | 累计电功 | state | J → kJ（1000） |

### 3.5 方程与实现步骤

1. `initialize`：`ctx.state.setdefault("shaft_energy_j", 0.0)`、`ctx.state.setdefault("electric_energy_j", 0.0)`。
2. clamp：`s∈[0.05,2]`（`PVS_SPEED_CLAMPED`）、`η∈[0.05,1]`、`η_m∈[0.05,1]`（`PVS_EFFICIENCY_CLAMPED`）、`ρ=max(density_kg_m3,1)`。
3. 曲线防御：把 `head_curve` 规整成 `list[list[float]]`，校验 `≥2` 点、首点 x=0、末点 y=0、x 严格递增、y 严格递减、全非负；不满足报 `PVS_CURVE_INVALID`（error，先按默认曲线注册再报错）。正常情况下此分支不可达，编译期已拦截。
4. 设计点（evaluate）：`Q_n=nominal_flow_m3_h`、`x=Q_n/s`；线性插值得 `H_curve(x)`，`x` 超出末点时取末点（0 m）并报 `PVS_NOMINAL_CLAMPED`（info）；`H_n=s²·H_curve(x)`；`P_hyd,n=ρ·g·H_n·Q_n/3600`、`P_shaft,n=P_hyd,n/η`、`P_elec,n=P_shaft,n/η_m`。
5. 注册：`ctx.net.pump(channel="main", head_curve=H, speed_ratio=s, density_kg_m3=ρ, heat_w=0.0)`。相似律 `H=s²·H(Q/s)` 由 `solver.pump_head` 统一处理（`solver.py:81-91`）；`heat_w=0` 的理由同 §2.5 步骤 6。
6. evaluate 输出：`ctx.var("pump_head_m", H_n)`、`shaft_power_w=P_shaft,n`、`electric_power_w=P_elec,n`；首帧/稳态帧看到设计点，动态帧被 commit 覆盖。
7. `commit_step`：`m=|channel("main").mass_flow_kg_s|`、`Δp=|channel("main").pressure_drop_pa|`；`H=Δp/(ρ·g)`、`P_hyd=Δp·m/ρ`、`P_shaft=P_hyd/η`、`P_elec=P_shaft/η_m`；累计两本账；`ctx.var("pump_head_m", H)`、`shaft_power_w`、`electric_power_w`。零流量时 `H` 可以是关死点扬程、两个功率均为 0。
8. 变速语义：改变 `speed_ratio` 后求解器按相似律重新求工作点；模块不反解转速，也不做“由目标压差迭代转速”的闭环（那属于控制器/PID）。

**数值示例**（默认曲线、`s=1`、工作点 `Q=20 m³/h`）：`H=12 m`、`Δp=117467.98 Pa`、`m=5.54556 kg/s`、`P_hyd=652.60 W`、`P_shaft=932.29 W`、`P_elec=1035.87 W`。

### 3.6 诊断码

| code | severity | 触发 | message 要点 / 处理 |
| --- | --- | --- | --- |
| `PVS_CURVE_INVALID` | error | 曲线结构非法（编译期通常已拦） | 结果不可信；按默认曲线注册后报错，运行失败 |
| `PVS_SPEED_CLAMPED` | warning | `speed_ratio` 超出 `[0.05,2]` | 已截断；给出原值与相似律影响 |
| `PVS_EFFICIENCY_CLAMPED` | warning | `efficiency`/`motor_efficiency` 超出 `[0.05,1]` | 已截断；电功率按截断值计算 |
| `PVS_NOMINAL_CLAMPED` | info | `nominal_flow_m3_h/s` 超出曲线末点 | 设计点扬程按 0 m 报出；请检查设计流量 |

### 3.7 测试用例

共用条件：`fluid=Water`、`temperature_k=293.15`、`duration_s=0.5`、`dt_s=0.1`；取**最终帧**；容差：流量相对 1e-3、扬程 1e-3 m、功率/能量相对 1e-3。

| # | 输入 | 期望 |
| --- | --- | --- |
| PVS-1 | 默认参数；`inlet=200000`、`outlet=317467.98`（H=12 m） | `main.mass_flow_kg_s≈5.54556`（20 m³/h）、`pump_head_m=12.0`、`shaft_power_w≈932.29`、`electric_power_w≈1035.87`、`state.shaft_energy_j≈466.14`、`state.electric_energy_j≈517.94` |
| PVS-2 | `speed_ratio=0.8`；`inlet=200000`、`outlet=303371.82`（H=10.56 m） | `main.mass_flow_kg_s≈2.77278`（10 m³/h，相似律 `s²·H(10/0.8)`）、`pump_head_m≈10.56`、`shaft_power_w≈410.21`、`electric_power_w≈455.78`、`state.shaft_energy_j≈205.10`、`state.electric_energy_j≈227.89` |
| PVS-3 | `efficiency=0.5`、`motor_efficiency=0.8`，其余同 PVS-1 | 流量/扬程同 PVS-1；`shaft_power_w≈1305.20`、`electric_power_w≈1631.50`、`state.shaft_energy_j≈652.60`、`state.electric_energy_j≈815.75` |

### 3.8 局限与后续

- **不实现 `FUD_TRNPRP`**：倍思鹿的泵内变物性迭代在 FluidNet 由 `property_coupling="node"` 的外层耦合承担；本模块只做效率链、变速与账本。把“泵曲线 + 节点物性耦合”说成“泵迭代法已复刻”是不准确的。
- 效率定值，不含效率—流量曲线、汽蚀（NPSH）、黏性修正（30% 乙二醇等变物性工况的工作点会偏）；`viscosity_pa_s` 当前只登记，`pump` 关系不使用。
- 不建模反转/飞轮效应、启停瞬态、最小流量保护与再循环；求解器拒绝反向流与曲线外工作点（`solver.py:392-398`）。
- 电功率按 `P_shaft/η_motor` 估算，不含变频器损耗、功率因数与电网侧账本；只有水力功进入流体焓，损失在网外。
- 后续：效率曲线（`η(Q/s)`）、NPSH 校核、由目标压差反解转速的内环（作为控制器而非模块）、与泵曲线法内置模型的口径对照。

---

## 4. 本批与 P0 的差异

| 维度 | P0（pipe_fitting / check_valve / fan_coil_unit） | P1（本批） |
| --- | --- | --- |
| 关系类型 | 全部 `resistance`（`valve`/`pipe`） | 新增 `pump_curve`/`pump`（fan、变速泵）；冷却塔仍 `resistance`/`pipe` |
| 求解器面 | 阀门平方律、Darcy 摩擦律 | 追加 `pump_head` 相似律、曲线硬校验、泵工作点越界拒绝、轴功注入焓 |
| `heat_w` 处理 | FC 用 `heat_flow_w` 回避平台别名 | 冷却塔同样用 `heat_flow_w`；平台别名 `heat_w` 保留，两批口径一致（§1.4） |
| 曲线参数 | 无 | 首次引入 `curve`：无 unit；只有 id=`head_curve` 走编译期校验，`pressure_curve` 由模块归一化 |
| evaluate 流量 | FC 用试算压差反解 | 仅冷却塔反解；fan/泵 evaluate 用 `nominal_flow_m3_h` 设计点 |
| 能量账 | `thermal_energy_j` 一本账 | fan/泵增加 `shaft_energy_j`、`electric_energy_j`，且与平台注入的轴功区分 |
| 诊断 | 三个模块都不使用 error | fan/泵的曲线结构性非法允许一个 error（结果不可信） |
| 测试规模 | 12 个用例 | 9 个用例；风机/泵用例的出口压力高于入口（压升），冷却塔仍是降压 |

补充：P0 的 `fan_coil_unit` 为水侧 `pipe` + 空气侧 ε-NTU，本批冷却塔是“水侧 `pipe` + 空气侧 ε-NTU”的同类结构，差别在冷源（进风干球 vs 湿球）与热流符号（水吸热 vs 水放热）；两者都不建空气网络。

## 5. 平台依赖点（实现时必须知道）

### 5.1 `solver.pipe_drop` 同律反解

冷却塔 evaluate 的流量反解必须与 `solver.pipe_drop` **逐行同律**：层流 `32μLm/(ρAd²)`、湍流 Colebrook `f=(-1.8·log10((ε/d/3.7)^1.11+6.9/Re))^-2`、`Re≤2300` 取层流、`2300<Re<4000` 用 `(Re−2300)/1700` 线性混合（`solver.py:68-78`）。反解用二分（`m∈[0,1e4]`、80 次），容差 1e-9 kg/s 量级。**若求解器摩擦律或过渡区改了，冷却塔的 Q 与水量反馈必须同步改**；这是本批最脆的耦合点。注册关系与反解共用参数 ρ/μ，避免“反解一套、求解另一套”。

### 5.2 `pump` 曲线校验与工作点边界

`NetworkRelation(kind="pump")` 要求：`head_curve` ≥2 点、首点 x=0、末点 y=0、x 严格递增、y 严格递减、全非负（`models.py:192-198`）；`speed_ratio>0`。`compiler.validated_parameters` 只对参数 id `head_curve` 做同样的校验并报 `CURVE_INVALID`（`compiler.py:166-172`）——**风机的 `pressure_curve` 不在其中**，所以 §2.5 的归一化是合同要求，不是可选优化。求解器还会拒绝反向流与超出 `末点流量×speed_ratio` 的工作点（`solver.py:392-398`，抛 `ValueError`），因此：
- 风机曲线末点必须为 0 Pa，否则换算出的 H 末点非 0，关系构造直接 `ValueError`；
- 变速泵的转速不能把工作点推出曲线；调低转速时流量上限按 `s` 缩小；
- 曲线首点必须是 0 流量，否则 `NetworkRelation` 拒绝；fan 的归一化负责把首点搬到 0。

### 5.3 气体单相网络与轴功注入

fan 走 `fluid` 端口的单相气体（`Air` 等），网络仍按不可压单相求解：没有两相、没有湿空气、没有压缩性；`thermal` 层对气体做同一套焓输运与单相校验（`thermal.py:190-202`）。`pump`/`compressor` 关系的轴功被求解器取为 `−Δp·m/ρ` 并作为流体焓增（`solver.py:415-433`、`thermal.py:427-428`），所以：
- fan/pump 的 `heat_w` 必须为 0，否则同一份能量计两次；
- 模块的 `shaft_power_w` 是“流体获得的轴功 / 效率”，平台帧里的 `<I>.heat_w` 只是其中的水力部分（`P_hyd`），二者不应相等；
- 冷却塔没有轴功关系，`heat_w` 就是全部热流，`D1.heat_w` 与 `−Q` 一致。

## 6. 验收 checklist（在 KIT §8 与 P0 §4.7 基础上追加）

- [ ] **接口锁定**：三个 manifest 的端口、通路、参数/变量 id、默认值、上下限、单位与本文件逐字段一致；`relation`/`solver_model` 未被改名（`resistance`/`pipe`、`pump_curve`/`pump`、`pump_curve`/`pump`）；通路 `enabled=true`。
- [ ] **合同**：端口全 `fluid` 且被 `main` 覆盖；关系集合 == 启用通路集合；`head_curve` 首点 0、末点 0、严格单调；fan 的 `pressure_curve` 经归一化后才进 `ctx.net.pump`，且点是 `list` 不是 tuple。
- [ ] **单位**：全部 canonical、无二次换算；温度只用 `−273.15` offset；温差（`approach_k`）无 offset；curve 无 unit；UA 显示 kW/K、功率显示 kW、能量显示 kJ。
- [ ] **冷却塔**：`evaluate` 未调用 `ctx.var("heat_w", …)`；`thermal=true` 的帧里 `D1.heat_w == D1.main.heat_w ≈ −Q`；CT-3 零流量无 `NO_FLOW_HEAT`、无非有限值；`CT_LATENT_IGNORED` 每帧存在。
- [ ] **风机**：末点非 0 的压力曲线被截断并报 `FAN_CURVE_CLIPPED`；FAN-2 的相似律压升 `s²·Δp(Q/s)` 与手算一致；`speed_ratio` 运行中可写且下一帧生效；`heat_w=0`，平台别名 `<I>.heat_w > 0` 只代表水力功。
- [ ] **变速泵**：`head_curve` 通过编译期 `CURVE_INVALID`；PVS-2 工作点 `s²·H(Q/s)` 成立；功率取收敛通道而非设计点；`state.*_energy_j` 等于 `∫P dt`；零流量时功率为 0 且扬程为关死点。
- [ ] **数值**：9 个设计用例在独立验证台按各节容差通过；两个 evaluate 逐字段相同（幂等、无副作用）；`commit_step` 只在接受步改 state；state 全为 JSON 标量且 < 64 KiB。
- [ ] **能量**：冷却塔动态 `energy_residual_w` 相对全网焓流 ≤1e-6；风机带轴功时同样成立；`state.thermal_energy_j ≈ −∫Q dt`、两本电/轴账 ≈ `∫P dt`。
- [ ] **边界**：`ua_w_k=0`、零水量、零风量、`T_in≤T_wb`、端口压力缺失都不抛裸异常，先诊断再取安全值；所有除数（`C_w`、`C_a`、`C_min`、`ρ`、`s`）有 `minimum` 或运行时防御。
- [ ] **发布**：首次 `expected_latest_version=0`、版本 `1.0.0`；保存前试算覆盖全部 derived/state 输出（含命名的 `heat_w` 别名）；`release.json` 含 3 个用例的输入与容差；旧项目快照不受影响。
