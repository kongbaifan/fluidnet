# M2-A 映射与验收：倍思鹿 A 类 5 模块 → FluidNet 内置模型

> 日期：2026-10-22。范围：`管道通用`、`截止阀`、`泵曲线法`、`管壳式换热器`、`容积型源头` 五个 A 类模块。
> 倍思鹿侧只读证据：`F:\beisilu\倍思鹿数值仿真-V5.3\AlgModule\<模块>\code\<模块>_Run.cpp`、同名根 `.cpp`，以及 `AlgProject/ASDFGHJ|NH3CO2ZL/*_DB.PJTDB`。
> FluidNet 侧证据：`backend/fn_engine/catalog.py`、`compiler.py`、`solver.py`、`thermal.py`，`docs/DATA_CONTRACT.md`、`ALGORITHM.md`、`BASELU_COMPARISON.md`、`BSL_MODULE_MAP.md`。
> 约束：本文只做映射与验收方案，不新增模型、不改其他文件；未运行倍思鹿 exe，未运行全量 pytest。

## 1 目的与口径

### 1.1 本文做什么

M2-A 的产出是「映射表 + 可执行验收算例」，不是新物理实现。五个模块全部落在 FluidNet 已有内置模型上：

| 倍思鹿模块 | FluidNet 模型 | `solver_model` |
| --- | --- | --- |
| 管道通用 | `pipe` | `pipe` |
| 截止阀 | `valve` | `valve` |
| 泵曲线法 | `pump` | `pump_curve` |
| 管壳式换热器 | `exchanger` | `heat_exchanger` |
| 容积型源头 | `source` | `pressure_source` |

验收只回答三个问题：参数能否一一填进去、端口/变量能否对上、在解析解上能否通过。至于倍思鹿内部关系式是否更准，不在本文结论内。

`BSL_MODULE_MAP.md` 的 A 类共 7 项；本批只做指定的 5 项（不含弯管、异径管），后两项在矩阵中落到 Python 包 `pipe_fitting`，不在本文范围。

### 1.2 数值口径与级别

- 期望值一律来自解析解或公开公式，**不声称与倍思鹿逐位一致**，也不把 `.PJTDB` 快照值当期望值（该库自述见 `BASELU_REFERENCE_CASES.md:8-14`）。
- 水力期望用 `reference` 物性常数复核：`ρ=998.275246 kg/m³`、`μ=1.001550e-3 Pa·s`、`g=9.80665 m/s²`（`solver.py:20-22`）。
- 热力期望用 `cp≈4180 J/(kg·K)` 的常数近似，并给出物性库可能造成的偏差；容差相应放宽。
- 级别定义：**L1** 为纯解析、单次编译+求解可断言；**L2** 依赖物性或热力迭代，容差放宽；**L3** 需倍思鹿标定或 CI 全量 job，本文只登记、不填数值。
- 本文所有数值已用内联 Python 复核；公式在每条算例中给出，读者可手算复现。

### 1.3 命名与单位规则

- 倍思鹿端口为 `IMn_*`（第 n 个入口语义槽）与 `EXn_*`（第 n 个出口语义槽），每个端口 6 个标量：`FLOW/PRE/ENTHALPY/TEMP/VOLUME/Q`。
- 倍思鹿模块参数用扁平索引读写：`ModuleGet(n)` 读 double、`ModuleIntGet(n)` 读 int；索引是代码读取顺序，不是稳定 ID。
- FluidNet 变量路径为 `实例.端口.后缀`、`实例.ch0.后缀`、`实例.param.<id>`；单通路设备另有 `实例.<后缀>` 别名（`DATA_CONTRACT.md:76-83`）。
- 单位以 `DATA_CONTRACT.md:51-72` 为准：压力 Pa、温度 K、比焓 J/kg、质量流量 kg/s、开度 1、内径/粗糙度 m。
- 倍思鹿 `VOLUME` 不是体积，而是**密度 kg/m³**：`DENSITY=(IM0_VOLUME+EX0_VOLUME)/2`（`管道通用_Run.cpp:42`），PJTDB 标签也写“密度(Kg/m3)”。这是最容易误映射的一处。

### 1.4 证据边界

倍思鹿的物理关系式大多不在包内：`FudPhyLink.h` 只给出 `PIPECV`、`VALVECV_SHUT`、`PUMPCV`、`SHTC_P`、`PTT_BKT` 的声明（`Lib/debug/FudPhyLink.h:67-104`），网络关系 `Netlink_*` 的声明在 `Lib/debug/MODULEAPILINK.h:45-47`，都没有定义。因此本文只使用**可见的调用参数、分支条件、端口/参数索引**，不推断 DLL 内部公式。`BSL_MODULE_MAP.md:113` 已把这一点列为“求解器黑盒”，本文沿用。

## 2 通用映射规则

### 2.1 端口：`IMn/EXn` → `port id`

端口槽位由根 `.cpp` 的 `ModulePortGet(n, k)` 顺序决定，**不是**按 `IM0,EX0,IM1,EX1…` 的字典序。换热器的槽位就是一个反例：

| 槽位 n | 倍思鹿 | 典型 FluidNet 落点 | 说明 |
| --- | --- | --- | --- |
| 0 | `IM0_*` | `in0` | 主通路入口 |
| 1 | `EX0_*` | `out0` | 主通路出口 |
| 2 | `IM1_*` | `in1` | 第二侧/容器入口 |
| 3 | `EX1_*` | `out1` | 第二侧/容器出口 |
| 4 | `EX2_*` | `out1`（与 `EX1` 合并） | 换热器根 `.cpp:184-189` 槽位 4 是 `EX2` |
| 5 | `IM2_*` | `in1`（与 `IM1` 合并） | 换热器根 `.cpp:191-196` 槽位 5 是 `IM2` |
| 6 | `IM3_*` | 无 | 仅源类 4 进 4 出设备 |
| 7 | `EX3_*` | 无 | 仅源类 4 进 4 出设备 |

规则：

1. 单通路设备（pipe/valve/pump）只用槽位 0/1，映射 `in0/out0`，`ch0` 是唯一通路。
2. 换热器用槽位 0/1 作管程，槽位 2/3 与 4/5 都是壳侧容器接口；FluidNet 只有两个流体端口，必须先用 `junction` 把 `IM1+IM2` 并成 `in1`、`EX1+EX2` 并成 `out1`。
3. `source` 只有 `out0` 一个端口，且编译器强制“压力边界必须只有一个端口”（`compiler.py:361-362`）；倍思鹿源是 4 进 4 出，必须用 `source + junction` 树模拟。
4. 倍思鹿的 `EXn` 在流量为负时也承担入口语义（`管道通用_Run.cpp:16-38` 的符号分支）；FluidNet 端口方向只是标称，反向流由负流量表达，不需要交换端口。

### 2.2 六个标量：变量后缀与换算

| k | 倍思鹿标量 | PJTDB 标签/单位 | FluidNet 后缀 | 换算 |
| --- | --- | --- | --- | --- |
| 0 | `FLOW` | 流量 Kg/S | `mass_flow_kg_s` | ×1 |
| 1 | `PRE` | 压强 MPa | `pressure_pa` | ×1e6 |
| 2 | `ENTHALPY` | 焓值 kJ/kg | `enthalpy_j_kg` | ×1000 |
| 3 | `TEMP` | 温度 ℃ | `temperature_k` | +273.15 |
| 4 | `VOLUME` | 密度 kg/m³ | `density_kg_m3` | ×1（名字是陷阱） |
| 5 | `Q` | 气液两相比例 | `quality` | 0–1 有效；`998`、`-0.0002` 等为哨兵/数值噪声 |

补充：`NH3CO2ZL_DB.PJTDB` 的 `NOD6` 键名直接写着 `IM0_流量(Kg/S)`、`IM0_压强(MPa)`、`IM0_焓值(Kj/Kg)`、`IM0_温度(℃)`、`IM0_密度(Kg/m3)`、`IM0_气液两相比例`，可作为单位证据；`ASDFGHJ` 工程则用 `IM0_WI/IM0_U/IM0_i/IM0_Phase/IM0_Var4/IM0_Var5`，键名随工程版本变化，**不能按字面猜语义**，只能按 k 顺序和根 `.cpp` 的 `ModulePortGet(n,k)` 对齐。

派生量：`volume_flow_m3_h = m/ρ×3600`（`DATA_CONTRACT.md:72`）；倍思鹿 `FLOW_VOLUME=3600*EX0_FLOW/DENSITY`（`管道通用_Run.cpp:49`）口径一致。

### 2.3 参数索引：`ModuleGet(n)` → `param.<id>`

倍思鹿根 `.cpp` 的读取段把参数按顺序抄进全局变量，例如管道 `RLS=ModuleGet(0)` 到 `MODEL=ModuleGet(9)`、`DN=ModuleIntGet(2)`（`管道通用.cpp:119-133`）；截止阀 13 个 double + 3 个 int（`截止阀.cpp:125-140`）；泵 11 个 double + 3 个 int（`泵曲线法.cpp:120-133`）；换热器 31 个 double + 3 个 int（`管壳式换热器.cpp:198-231`）；源 6 个 double + 3 个 int（`容积型源头.cpp:199-207`）。

映射时遵守三条：

1. **`n` 不是 ID**。同一模块的 `_Run.cpp` 与根 `.cpp` 行号不同，但索引顺序一致；`_D/_R` 变体可能分叉，不能把索引写进 FluidNet 合同。
2. **`ModuleGet` 里混有输出**。`RLS`、`CV`、`RE`、`FLOW_SPD`、`MID_PRE`、`FLOW_VOLUME`、`H_LAST`、`H_in/H_out` 都是模块算完后 `ModuleSet` 写回的量，不是用户参数；只有根 `.cpp` 中在计算段之前被读取、且语义为几何/设定值的才是参数。
3. **参数身份取 PJTDB 键名**。例如 `PL` 是长度、`DN` 是公称直径、`BKT_SL` 是筒长、`PIPENB` 是管数；FluidNet 侧改名为 `length_m`、`diameter_m` 等，映射表逐项给出。

已核对的五个对象（键集来自 `NH3CO2ZL_DB.PJTDB`；fixture 见 `BASELU_REFERENCE_CASES.md:52-64`）：

| 模块 | PJTDB 对象 | 键数 | 依据/用途 |
| --- | --- | --- | --- |
| 管道通用 | `MOD0` | 29 | `RLS/PL/CV/DHIGH/FLOW_SPD/DN`，fixture `baselu-nh3co2zl-mod0-pipe` |
| 截止阀 | `MOD7` | 32 | `VSPACT/VSPACT3D/AUTO/LF/DN`，fixture `...-mod7-valve` |
| 泵曲线法 | `MOD8` | 30 | `CURVE_A/CURVE_B/R/EN/A/B/C`，fixture `...-mod8-pump` |
| 管壳式换热器 | `MOD210` | 80 | 6 端口 + `BKT_*/H_LAST/PIPENB`，fixture `...-mod210-heat-exchanger` |
| 容积型源头 | `MOD82` | 67 | `IM0–IM3/EX0–EX3` + `BKT_PRE/H/TEMP/VOLUME/Q`；无 fixture，本文直接读 DB |

### 2.4 `.PJTDB` 四元数组的解读与限制

标量在 PJTDB 中统一存成 `[值, 参数A, 参数B, 0]`。实测 `NH3CO2ZL_DB.PJTDB` 有 14,080 个这样的数组，索引 1/2 在**整库内按变量种类重复**：

| 变量种类 | 最常见的 `(A,B)` | 出现次数 | 解读 |
| --- | --- | --- | --- |
| `PRE` | `(0.95, 0.101325)` | 451 | 引擎侧压力影子/上一轮值，不是对象边界 |
| `TEMP` | `(-41.504, -25.001)` | 195 | 同上，跨对象复用 |
| `Q` | `(0.184935, 998.0)` | 195 | `998` 是“单相/不适用”哨兵 |
| `VOLUME` | `(121.874, 1.424)` | 195 | 密度影子值 |
| `ENTHALPY` | `(170.0, 374.1452)` | 221 | 焓影子值 |
| `DN` | `(150, 150)` | — | 整数参数三槽同值 |

结论：索引 0 是当前值，索引 1/2 是**全局影子/历史槽**，不能当对象自身的上下限或初值；索引 3 保留为 0。限制有三条：

1. 无法从四元数组判断一个量是输入参数还是输出，必须回到根 `.cpp` 的读写顺序。
2. 无法从四元数组恢复单位；单位靠键名标签和代码量纲，且 `ASDFGHJ` 与 `NH3CO2ZL` 键名不同。
3. 快照不保证收敛（`BASELU_REFERENCE_CASES.md:123-128`），不能作数值期望；本文只用它做键集/单位/端口对照。

### 2.5 边界与初值

- 倍思鹿把边界放在模块内部：源用 `BKT_PRE`/`BKT_H` 定 p/h，换热器用 `BKT_*` 定容器存量；FluidNet 用独立的 `source`（p/T）和 `tank`（液位/温度）对象，边界是网络的显式节点。
- 倍思鹿的端口初值来自 `.PJTDB` 快照；FluidNet 稳态求解不需要初值，动态运行由 `tank`/`thermal_cells` 的状态给出。
- 移植时不要把 PJTDB 的端口值写成 FluidNet 的边界；它们只是同一拓扑的上一时刻快照，写进边界会改变问题。

## 3 五个模块逐项

### 3.1 管道通用 → `pipe`

**倍思鹿语义**

- 入口/出口对称：`IM0_FLOW=EX0_FLOW`；流量 ≥0 时把 `IM0` 的焓和组分抄到 `EX0` 并在 `EX0_PRE` 下查 `FUD_PH`，否则反向（`管道通用_Run.cpp:16-38`）。
- 平均密度 `DENSITY=(IM0_VOLUME+EX0_VOLUME)/2`，体积流量 `3600*EX0_FLOW/DENSITY`（`:42-49`）。
- 阻力计算调用 `PIPECV(temp,DENSITY,MIX,EX0_FLOW,DN,PL,CV,RLS,FLOW_SPD,RE)`（`:61`），再把 `Netlink_Pipe(0,RLS,CV,DENSITY,DHIGH)` 注册进网络（`:64`）。
- 根 `.cpp` 的输入是 `PL`（长度 m）与 `DN`（int，mm），`RLS/CV/RE/FLOW_SPD` 是 `PIPECV` 的输出（`管道通用.cpp:119-133`）。`MODEL` 是模型选择器，快照中为 0。

**FluidNet 落点**

内置 `pipe` 参数（`catalog.py:41-50`）：`length_m`、`diameter_m`、`roughness_m`、`heat_loss_ua_w_k`、`ambient_temperature_k`、`thermal_cells`、`wall_heat_capacity_j_k`。水力式在 `solver.py:68-78`，散热/热容在 `thermal.py:412-423`。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0_FLOW`/`EX0_FLOW` | `ch0.mass_flow_kg_s`（别名 `mass_flow_kg_s`） | kg/s，正方向 `in0→out0`，与倍思鹿一致 |
| `IM0_PRE`/`EX0_PRE` | `in0.pressure_pa`/`out0.pressure_pa` | ×1e6 |
| `IM0_ENTHALPY`/`EX0_ENTHALPY` | `in0.enthalpy_j_kg`/`out0.enthalpy_j_kg` | ×1000 |
| `IM0_TEMP`/`EX0_TEMP` | `in0.temperature_k`/`out0.temperature_k` | +273.15 |
| `IM0_VOLUME`/`EX0_VOLUME` | `in0.density_kg_m3`/`out0.density_kg_m3` | 密度，×1 |
| `IM0_Q`/`EX0_Q` | `in0.quality`/`out0.quality` | 0–1；998 视为空 |
| `PL` | `param.length_m` | m，×1 |
| `DN` | `param.diameter_m` | mm→m，×0.001 |
| `RLS`、`CV` | `ch0.pressure_drop_pa`、`ch0.volume_flow_m3_h` | 输出，不是参数；不要回填 |
| `RE`、`FLOW_SPD`、`MID_PRE`、`FLOW_VOLUME` | 无同名变量 | 由 FluidNet 端口/通路变量替代 |
| 无 | `param.roughness_m` | 默认 45 µm；倍思鹿可见参数中没有粗糙度 |
| 无 | `param.heat_loss_ua_w_k`、`ambient_temperature_k` | 默认 0 / 293.15 K；倍思鹿管模块不算散热 |
| 无 | `thermal_cells`、`wall_heat_capacity_j_k` | 默认 0，即无热惯性 |
| `DHIGH` | 无 | `catalog.py` 没有 `height_m`；`solver.py:108` 的 `params.get('height_m',0)` 永远取 0。`DHIGH` 按命名理解为位差项，语义待确认 |

**映射差异与缺口**

1. `PIPECV` 只有声明（`FudPhyLink.h:72`），内部摩擦关联式、两相修正、`RLS` 惯性项不可见；FluidNet 用层流 + Haaland + 2300–4000 线性过渡（`solver.py:71-78`），两者不可能逐位一致。
2. 倍思鹿没有可见的粗糙度参数，`RLS` 是网络组装用的阻力系数，不是可移植的物理参数；若把 `RLS` 当输入会重复计入摩擦。
3. 位差项 `DHIGH` 参与 `Netlink_Pipe`（`MODULEAPILINK.h:45`）；FluidNet 内置 `pipe` 没有标高参数，当前恒为 0。这是明确缺口，但 `DHIGH` 的精确语义只能从 DLL 行为确认。
4. 倍思鹿用 `FUD_PH` 支持两相端口状态，FluidNet 管网只允许与边界一致的单相，进入两相报 `PHASE_UNSUPPORTED`（`ALGORITHM.md:208`）。
5. 倍思鹿的 `S_T`（ms）是模块时间步，驱动的是一阶惯性；FluidNet `thermal_cells` 是空间热容分段，二者不是同一离散。

**验收算例**

| ID | 级别 | 输入（Project 关键参数/边界） | 期望（公式+数值） | 容差 |
| --- | --- | --- | --- | --- |
| P-1 | L1 | `pipe`: d=0.025 m、L=10 m、ε=45 µm、UA=0、cells=0；B1=300000 Pa、B2=299970.982 Pa | 层流：`Δp=128μLQ/(πd⁴)`；Q=0.1 m³/h → m=0.0277299 kg/s，Re=1410，Δp=29.018 Pa | ±0.5% 或 ±0.05 Pa |
| P-2 | L1 | 同上 d=0.05 m、L=30 m；B1=300000 Pa、B2=286555.191 Pa | Re=70504，Haaland `f=0.022431`，`Δp=f·L/D·m·abs(m)/(2ρA²)`=13444.81 Pa；m=2.77299 kg/s（Q=10 m³/h），v=1.4147 m/s | ±1% |
| P-3 | L2 | d=0.05 m、L=50 m、UA=50 W/K、ambient=293.15 K；B1 温度 333.15 K、B1=300000 Pa、B2=299017.207 Pa（B2 只作压力参考，温度取 293.15 K，不参与断言） | m=0.5 kg/s；`T_out=T_amb+(T_in−T_amb)e^{−UA/(m·cp)}`=293.15+40·e^(−50/2090)=332.204 K；ΔT=−0.946 K；散热≈1.98 kW；断言 `P1.ch0.outlet_temperature_k`（支路出口流，混合前） | ±0.1 K 或 ±3% |
| P-4 | L3 | `thermal_cells=4`、`wall_heat_capacity_j_k=5e5`，动态 600 s、步长 1 s，入口温度阶跃 333→353 K | 无闭合解析解（4 单元 + 壁面热容）；由 CI 全量 job 记录时间常数与稳态终值后回填 | 待回填 |

**结论：可映射**（水力、散热、热容分段均可），需参数化粗糙度/UA；`DHIGH` 与两相暂不可映射。

### 3.2 截止阀 → `valve`

**倍思鹿语义**

- 同样先做流量符号分支（`截止阀_Run.cpp:18-40`）；`IM0_FLOW=EX0_FLOW`。
- `AUTO` 是开度速率控制：`AUTO<-0.5` 每步减 0.005，`AUTO>0.5` 每步加 0.005，随后夹到 [0,1]（`:46-61`）。
- `LF=0`、`TEMP001=1+LF=1`（`:69-72`）；`VTYPE=2` 固定为等百分比：`TEMP002=pow(ALF,VSPACT-1)`，`CVF=(TEMP002+LF)/TEMP001-1/ALF`，`ALF=100` 硬编码（`:78-96`）。
- 调用 `VALVECV_SHUT(temp,DENSITY,MIX,EX0_FLOW,DN,CVF,CV,RLS,RE)`（`:113`），再 `Netlink_Valve(0,RLS,CV,CVF,DENSITY,DHIGH)`（`:114`）。
- 根 `.cpp` 参数 13 个 double：`VSPACT`、`VSPACT3D`、`AUTO`、`LF`、`DENSITY`、`MID_PRE`、`FLOW_VOLUME`、`RLS`、`FLOW_SPD`、`CV`、`DHIGH`、`RE`、`MODEL`，加 `DN`（`截止阀.cpp:125-140`）。`VSPACT3D` 的百分比换算在代码里被注释掉（`截止阀_Run.cpp:45`），实际只用 `VSPACT`。

**FluidNet 落点**

内置 `valve` 只有 `opening_ratio`（0–1）与 `kv_m3_h`（`catalog.py:37-40`）；压降式 `Δp=1e5·(ρ/1000)·Q|Q|/Kv_eff²`、`Kv_eff=Kv·opening`（`solver.py:104-106`，`ALGORITHM.md:28-36`）；开度 0 时编译为 `closed` 支路（`compiler.py:446-447`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `VSPACT` | `param.opening_ratio` | 0–1，直接对应 |
| `VSPACT3D` | `param.opening_ratio = VSPACT3D/100` | 仅当项目按百分比存值；代码未使用该量 |
| `CV`（`VALVECV_SHUT` 输出） | `param.kv_m3_h` | 需阀门样本的 Kv；`CVF→Kv` 的换算在 DLL 内，不可见 |
| `DN` | 无 | FluidNet 阀没有通径参数，压降只由 Kv 决定 |
| `LF` | 无 | 代码强制 0；FluidNet 也不设泄漏 |
| `AUTO` | 无内置 | 用 PID/控制脚本实现开度斜坡 |
| `Q`（m³/h） | `ch0.volume_flow_m3_h` | 由 m/ρ 派生 |
| `RLS`、`RE`、`FLOW_SPD` | 无同名 | 由求解器输出替代 |

**映射差异与缺口**

1. **特性曲线**：倍思鹿固定等百分比、`ALF=100`、`LF=0`；`CVF(1.0)=0.99`、`CVF(0.5)=0.09`、`CVF(0.1)=0.00585`。FluidNet 开度与 Kv 线性，50% 开度就是 50% Kv；在相同 Δp 下归一化流量为 0.09 vs 0.5，差 5.6 倍。这是本文最重要的量化缺口。
2. `CVF` 是无量纲当量流通面积，`Kv` 是有量纲流量系数；二者之间的换算依赖 `DN` 和 `VALVECV_SHUT` 内部几何，包内不可见（`FudPhyLink.h:81`）。
3. 倍思鹿的 `AUTO` 是每步 ±0.005 的速率限制，不是位置式控制；FluidNet 用 PID 可以达到类似效果，但不是内置行为。
4. 0% 开度：两边都给出零流量；FluidNet 走 `closed` 分支，且要求关闭阀两侧子网各自有压力参考（`compiler.py:450-457`），倍思鹿没有这个编译期检查。
5. 反向流：两边都按同一平方律反号；倍思鹿只在焓赋值时分支，不改变阻力式。
6. 两边都没有闪蒸/汽蚀模型；`MODEL` 选择器在倍思鹿可见代码中未参与计算。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| V-1 | L1 | `valve`: Kv=16、opening=1.0；B1=300000 Pa、B2=200000 Pa | `Q=Kv√(Δp·1000/(1e5·ρ))=16.0138 m³/h`；m=4.44061 kg/s | ±0.5% |
| V-2 | L1 | 同上，opening=0.5 | `Kv_eff=8`；Q=8.00691 m³/h；m=2.22031 kg/s（与 V-1 成 2:1） | ±0.5% |
| V-3 | L1 | 同上，opening=0；两侧各接一个 source | `closed=True`，m=0（`abs(m)≤1e-8`）；去掉下游 source 时编译报 `PRESSURE_REFERENCE_MISSING` | 精确 0 / 错误码 |
| V-4 | L3 | 倍思鹿等百分比：VSPACT=0.5、ALF=100；FluidNet 取 opening=0.09 | CVF(0.5)=0.09；若用 Kv=16、Δp=0.1 MPa，则 Q=1.4412 m³/h、m=0.399655 kg/s；但 CVF→Kv 的基准未知，需倍思鹿标定 | 待回填 |

**结论：可映射**（Kv×线性开度、正反流、0% 零流量）；**等百分比特性需参数化或 Python 模块**，当前不可验收。

### 3.3 泵曲线法 → `pump`

**倍思鹿语义**

- 入口夹紧：`CURVE_A<1e-6` 置 1e-6，`CURVE_B<0.1` 置 0.1（`泵曲线法_Run.cpp:17-24`）。
- `EN>0.5` 时组装二次曲线：`C=−CURVE_A/CURVE_B²`、`B=0`、`A=CURVE_A`；否则 `A=B=C=0`（`:25-37`）。
- `S_T<1` 置 10（`:39-42`）；按流量符号查 `FUD_PH`；`DPRE=EX0_PRE−IM0_PRE`（`:88`）。
- 调用 `PUMPCV(temp,DENSITY,MIX,EX0_FLOW,R,CV,RLS)`（`:92`），再 `Netlink_Pump(0,RLS,1e8,DENSITY,A,B,C)`（`:93`）。
- 根 `.cpp` 参数：`CURVE_A`、`CURVE_B`、`DPRE`、`DENSITY`、`R`、`CV`、`RLS`、`MODEL`、`C`、`B`、`A`，int `S_T`、`RUN_S`、`EN`（`泵曲线法.cpp:120-133`）。

**FluidNet 落点**

内置 `pump` 参数：`head_curve`（`[Q_m3_h, H_m]` 点列）、`speed_ratio`、`efficiency_ratio`（`catalog.py:31-36`）。曲线校验要求首点 Q=0、末点 H=0、流量严格递增、扬程严格递减（`compiler.py:166-172`）。工作点式：`H(Q,s)=s²·H_nom(Q/s)`、`Δp=−ρgH`（`solver.py:81-91,109-112`）；轴功 `P=−Δp·(m/ρ)/η`（`solver.py:415-433`）；超出曲线或反转报错（`solver.py:392-398`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `CURVE_A` | `head_curve[0][1]` | 关死点压升；`H₀=Δp₀/(ρg)`，单位待标定 |
| `CURVE_B` | `head_curve[-1][0]` | 零扬程流量，m³/h |
| `A`、`B`、`C` | 曲线点列 | `Δp(Q)=A+BQ+CQ²`，采样 3 点以上 |
| `EN` | 无 | 关闭泵没有内置表达；`speed_ratio=0` 会报错 |
| `R` | 无 | 语义不明（可能是内阻或半径），不作映射 |
| `DPRE` | `ch0.pressure_drop_pa` | 输出，不是参数 |
| 无 | `speed_ratio` | 倍思鹿没有转速输入，只能取 1.0 |
| 无 | `efficiency_ratio` | 倍思鹿不算效率/轴功；必须补设备效率 |

**映射差异与缺口**

1. 倍思鹿用二次压升曲线 `A+BQ+CQ²`，FluidNet 用离散 `[Q,H]` 点线性插值；采样会引入曲线误差，且 `CURVE_A` 的单位（Pa/MPa/bar）无法从包内确认，单位错会使 `H₀` 差几个数量级。
2. 倍思鹿没有转速量，`PUMPCV` 的 `R` 语义不明；FluidNet 的相似律 `s²` 没有倍思鹿对照，只能做自洽验收。
3. 倍思鹿没有效率参数，也不输出轴功；FluidNet 默认 `η=0.75`，因此“轴功”只能与手算比，不能与倍思鹿比。
4. `EN=0` 时 `A=B=C=0`，泵退化为零压升支路；FluidNet 的泵必须有合法曲线，且 `speed_ratio>0`，无“停机”状态。要么用关闭阀/旁通表达，要么新增状态参数。
5. FluidNet 拒绝反向流和曲线外工作点；倍思鹿对负扬程/超流量没有可见的保护分支，可能外推。
6. `PUMPCV` 声明在 `FudPhyLink.h:96`，`Netlink_Pump` 声明在 `MODULEAPILINK.h:46`，都没有定义；内部阻力/惯性不可见。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| M-1 | L1 | `pump`: curve `[[0,20],[10,18],[20,12],[30,0]]`、s=1、η=0.75；B1=200000 Pa、B2=317476.831 Pa | 要求 H=12 m → Q=20 m³/h；m=5.54597 kg/s；`P_shaft=ρgH·(Q/3600)/η`=870.20 W | ±0.5% 或 ±1 W |
| M-2 | L1 | 同上，s=0.8，B2 不变 | `H=s²H_nom(Q/s)`：Q=5 m³/h、H=12 m；m=1.38649 kg/s；P=217.55 W | ±0.5% 或 ±1 W |
| M-3 | L1 | 同上，B2=150000 Pa（低于入口）；或 `speed_ratio=0` | 前者要求负扬程，工作点 Q>30 m³/h，预期求解失败并报“超出泵曲线范围”（`ValueError`）；后者抛“停泵阻力模型尚未定义”。若前者改为不收敛，测试也应判失败并记录，不能当通过 | 错误码/消息 |
| M-4 | L3 | 倍思鹿 `MOD8` 快照：CURVE_A=0.1、CURVE_B=10、R=0.06、EN=0；映射为 `[[0,H₀],[5,0.75H₀],[10,0]]` | 若 CURVE_A 为 MPa，水侧 `H₀=0.1e6/(998.275·9.80665)=10.214 m`；若为 bar 则 1.021 m。单位未定，需一次倍思鹿标定（同泵同流量读 `EX0_PRE−IM0_PRE`）回填 | 待回填 |

**结论：可映射**（曲线采样 + 相似律 + 轴功）；**需参数化**（`CURVE_A` 单位、`EN`、效率），`R` 暂不可映射。

### 3.4 管壳式换热器 → `exchanger`

**倍思鹿语义**

- 这是一个**带管束的容器**，不是纯两侧换热器：根 `.cpp` 读 6 个端口——槽位 0/1 是 `IM0/EX0`（管程），槽位 2–5 是 `IM1/EX1/EX2/IM2`（壳侧容器两进两出）（`管壳式换热器.cpp:156-197`）。
- 容器体积由几何算：`BKT_V=(4πR³/3)+πR²(L−2R)`（`_Run.cpp:73`），`PR=DN0/2000`（`:48`），管束面积 `SPIN=2π·PR·BKT_SL·PIPENB`、`SPO=2π(PR+0.0025)·BKT_SL·PIPENB`（`:110-111`）。
- 热阻串联：`H_metal=SPIN·160/0.0025`、`H_out=5000·SPO`、`H_in=SHTC_P(...)·SPIN`、`H_LAST=1/(1/H_metal+1/H_in+1/H_out)`（`:119-121,175-182`）。
- 每一步换热量 `mid_TRANSFER=D_T·H_LAST/1000`，管程焓减、容器焓增，做 10 次内迭代并处理“换过头”回退（`:166-267`）。
- 管程阻力另走 `PIPECV`，`CV_Zong=CV0·PIPENB·0.5`，最后 `Netlink_Pipe(0,RLS0,CV_Zong,DENSITY0,DHIGH0)`（`:503-505`）。
- 容器状态 `BKT_M/BKT_H/BKT_TEMP/BKT_PRE/BKT_Q/BKT_LEVEL` 及 4 个容器端口在 `:277-468` 回写。

**FluidNet 落点**

内置 `exchanger`：4 端口 `in0/out0/in1/out1`，参数 `ua_w_k`、`loss_coefficient`、`diameter_m`，`thermal_model='epsilon_ntu'`（`catalog.py:51-56`）。热力层用 ε–NTU：`C=w·cp`、`C_r=C_min/C_max`、`NTU=UA/C_min`；标称逆流，单侧反向按顺流（`thermal.py:430-443`，`ALGORITHM.md:174-184`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0/EX0` | `in0/out0`（`ch0`） | 管程 |
| `IM1/EX1` + `IM2/EX2` | `in1/out1`（`ch1`） | 先用 `junction` 合并两进两出 |
| `H_LAST` | `param.ua_w_k` | 单位 W/K，可直接作 UA 的近似 |
| `PIPENB`、`DN0`、`PR`、`SPIN`、`SPO` | 无 | FluidNet 不建几何，UA 为集总值 |
| `BKT_V`、`BKT_M`、`BKT_LEVEL`、`BKT_Q` | 无 | 无容器存量/液位；需另加 `tank` 或自定义模块 |
| `CV0/RLS0/FLOW_SPD0` | `param.loss_coefficient`、`diameter_m` | 两侧共用 K 与 d，无法表达管束因子 0.5 |
| `S_T` | 无 | 倍思鹿是动态推进；FluidNet 为稳态换热 |
| `H_in/H_out/H_metal` | 无 | 已折算进 UA，不单独暴露 |

**映射差异与缺口**

1. **端口数 6 vs 4**：壳侧是两进两出，必须合并；合并后每个壳侧支路的流量/温度不再单独可见。
2. **容器存量与液位**：倍思鹿在模块内维护 `BKT_M/BKT_H/BKT_V/BKT_LEVEL`，FluidNet 换热器没有质量/能量存储。`BSL_MODULE_MAP.md:124` 已明确要求“拆成 exchanger + 容器两个合同对象”，本文沿用；当前没有闭式两相容器可拆。
3. **换热算法不同**：倍思鹿是“10 步行进 + 容器能量 + 串联热阻”，FluidNet 是一次 ε–NTU 线性化迭代；两者的出口温度不能互作期望值。
4. **UA 来源不同**：倍思鹿由 `SHTC_P`（隐藏）+ 金属 160 W/(m·K) + 外侧 5000 W/(m²·K) 串并联得到；FluidNet 的 UA 是用户输入。把 `H_LAST` 填进 `ua_w_k` 只是“同一量纲的近似”，不是同一算法。
5. **相变/壳侧两相**：倍思鹿用 `BKT_Q`、`BKT_DL/DV`、`ENTHALPY_DL/DV` 描述容器两相；FluidNet 管网只支持单相，进入两相报 `PHASE_UNSUPPORTED`。
6. **逆流/顺流**：这是 FluidNet 的显式能力（按两侧流量符号判断），倍思鹿没有“布置”概念，只有“管程向容器放热”的 `D_T` 方向；因此只能用 ε–NTU 手算验收，不能与倍思鹿对照。
7. FluidNet 两侧共用同一个 `K` 和 `d`（`ALGORITHM.md:69-77`），不能表达管程/壳程不同阻力。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| HX-1 | L2 | `exchanger`: UA=1000 W/K、K=5、d=0.04；热侧 0.6 kg/s、338.15 K，B1=300000 Pa→B2=299429.084 Pa；冷侧 0.3 kg/s、298.15 K，B3=300000 Pa→B4=299857.271 Pa；两侧同向 | `C_h=2508`、`C_c=1254`、`C_r=0.5`、`NTU=0.797448`；逆流 `ε=0.494910`；`Q=εC_minΔT=24824.7 W`；`T_h,out=55.102 ℃`、`T_c,out=44.796 ℃` | ±2% 或 ±0.5 K |
| HX-2 | L2 | 同 HX-1，但把冷侧接成 `source→out1`（300000 Pa）、`in1→sink`（299857.271 Pa）（ch1 流量为负） | 单侧反向 → 顺流：`ε=(1−e^{−NTU(1+C_r)})/(1+C_r)=0.465100`；Q=23329.4 W；`T_h,out=55.698 ℃`、`T_c,out=43.604 ℃`；且 Q_顺 < Q_逆 | ±2% 或 ±0.5 K |
| HX-3 | L2 | UA=2000 W/K；两侧均 0.6 kg/s（常 cp 下 `C_r=1`；实际 cp 差使 `C_r≈0.9985`，ε 变化 <0.1%）；热侧 338.15 K、B1=300000 Pa→B2=299429.084 Pa；冷侧 298.15 K、B3=300000 Pa→B4=299429.084 Pa | `NTU=0.797448`；`ε≈NTU/(1+NTU)=0.443656`；Q≈44507.5 W；两侧出口约 47.254/42.746 ℃ | ±2% 或 ±0.5 K |
| HX-4 | L2 | UA=0；两侧 0.6/0.3 kg/s，边界同 HX-1 | 热力：Q=0，`ch0/ch1` 出口温度=入口温度；水力：热侧 `Δp=5·0.6²/(2ρA²)=570.916 Pa`，冷侧 142.729 Pa。另建 UA>0 且一侧零流量的附加算例，应给 `THERMAL_EXCHANGER_NO_FLOW` | ±3% 或 ±1 Pa |

**结论：需参数化**（UA、两侧 K/d、端口合并）；**壳侧容器/相变/液位暂不可验收**，换热本身可按 ε–NTU 验收（L2）。

### 3.5 容积型源头 → `source`

**倍思鹿语义**

- 源是**定 p/h 库**：`BKT_PRE≤0` 置 0.01 MPa，`BKT_H≤0` 置 80（`容积型源头_Run.cpp:13-20`），然后 `FUD_PH(BKT_PRE,BKT_H,...)` 反算 `BKT_TEMP/BKT_VOLUME/BKT_Q`（`:21-22`）。
- 4 进 4 出：流量 <0 的入口端口、流量 ≥0 的出口端口都被赋成同一组 `BKT_H/TEMP/VOLUME/Q`（`:24-111`）；所有 8 个端口压力都置 `BKT_PRE`（`:113-120`）。
- 根 `.cpp` 参数：`BKT_PRE`、`BKT_H`、`BKT_TEMP`、`BKT_VOLUME`、`BKT_Q`、`MODEL`，int `S_T`、`RUN_S`、`midType`（`容积型源头.cpp:199-207`）；端口槽位 0–3 为 `IM0–IM3`、4–7 为 `EX0–EX3`（`:143-197`）。

**FluidNet 落点**

内置 `source`：单端口 `out0`、参数 `pressure_pa`（默认 201325 Pa）与 `temperature_k`（默认 293.15 K）（`catalog.py:23-27`）。编译器强制单端口（`compiler.py:361-362`）、同节点压力/温度冲突检查（`:405-418`）、每个子网必须有压力参考（`:450-457`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `BKT_PRE` | `param.pressure_pa` | MPa→Pa，×1e6 |
| `BKT_H` | 无直接参数 | 先用 `T(p,h)` 反算温度，再填 `temperature_k` |
| `BKT_TEMP` | `param.temperature_k` | 倍思鹿是输出，FluidNet 是输入（因果反转） |
| `BKT_VOLUME`/`BKT_Q` | `out0.density_kg_m3`/`out0.quality` | 由物性服务派生 |
| 4 进 4 出 | `out0` + `junction` 树 | 编译器不允许第二个端口 |
| `midType` | 无 | 仅自增并在 1–4 间回绕，`PjtWarningSet` 被注释（`:121-130`） |
| `MODEL` | 无 | 快照中为 0 |

**映射差异与缺口**

1. **单端口 vs 8 端口**：`BOUNDARY_PORT_COUNT` 是硬错误；只能 `source→junction` 再分成多路。分流后每路的端口状态不再有独立变量，只有 `out0.*`。
2. **p/h 边界 vs p/T 边界**：倍思鹿给定 `BKT_H`，温度是算出来的；FluidNet 给定温度，焓是算出来的。移植时必须先用物性服务做 `T(p,h)` 反算，且只能在单相区做；两相 `h` 无法表达。
3. **静默夹紧 vs 显式报错**：倍思鹿把非正 p/h 夹到 0.01 MPa/80 kJ/kg；FluidNet 对越界报 `PARAMETER_RANGE`，对相态不符报 `PHASE_UNSUPPORTED`，不会静默改边界。
4. 倍思鹿 8 个端口可同时“供/吸”；FluidNet 的单个 `source` 也能吸流（反向流），但所有支路共用同一节点，无法区分“第几路”。
5. 每个连通子网必须有压力参考；关闭阀可能把下游隔成无参考子网并报 `PRESSURE_REFERENCE_MISSING`（`MODULES_P0.md:185` 有同样提醒）。
6. 同节点两个 `source` 压力不同报 `BOUNDARY_CONFLICT`，温度不同报 `BOUNDARY_TEMPERATURE_CONFLICT`；倍思鹿没有等价检查。
7. 倍思鹿源没有流量上限，FluidNet 边界也由网络决定流量；这一点语义一致。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| S-1 | L1 | `source` 600000 Pa/293.15 K → `pipe` d=0.025 m、L=10 m、ε=45 µm → `source` 500000 Pa/293.15 K | 压差 100 kPa；m=2.22654 kg/s（Q=8.02938 m³/h），Re=113221；上游节点 p=600000 Pa，源端口 T=293.15 K | ±1% 或 ±100 Pa |
| S-2 | L1 | 三种非法拓扑：(a) 关阀隔离下游且无源；(b) 同节点 600/500 kPa 两个源；(c) 同节点 600 kPa、293.15/303.15 K 两个源 | (a) `PRESSURE_REFERENCE_MISSING`；(b) `BOUNDARY_CONFLICT`；(c) `BOUNDARY_TEMPERATURE_CONFLICT` | 错误码 |
| S-3 | L1 | 一个 600 kPa 源 → J1；J1→(J2, V1)；J2→(V2, V3)；三台阀 Kv=16、100%，阀后各接 500 kPa 源 | 每个支路 `Q=16.0138 m³/h`、m=4.44061 kg/s；总 m=13.3218 kg/s；三个分支流量相等 | ±1% |
| S-4 | L2 | 定焓库：p=0.6 MPa、h=400 kJ/kg（水），用 `T(p,h)` 反算 `temperature_k` | CoolProp 反算 T=95.3606 ℃=368.5106 K；用该温度作 `source` 边界，端口 `enthalpy_j_kg` 应回到 400000 J/kg（±0.1%） | ±0.1 K 或 ±0.1% |

**结论：需参数化**（h→T 反算、端口合并）；**原生定焓边界、多端口、两相暂不可验收**。

## 4 汇总表

| 模块 | 映射完成度 | 验收算例数 | 阻塞项 | 下一步 |
| --- | --- | --- | --- | --- |
| 管道通用 | 高（水力/散热/热容） | 4（L1×2、L2×1、L3×1） | 粗糙度、`DHIGH`、`PIPECV` 黑盒、两相 | 补粗糙度标定；把 P-1/P-2 落成 CI 单测；P-4 交全量 job |
| 截止阀 | 中（Kv×线性开度） | 4（L1×3、L3×1） | 等百分比曲线、`CVF→Kv`、`AUTO` 速率 | 先按 V-1–V-3 固化；等百分比走参数化或 Python 模块 |
| 泵曲线法 | 中（曲线+相似律+轴功） | 4（L1×3、L3×1） | `CURVE_A` 单位、`EN`、效率、`R` | 做一次倍思鹿泵标定；补 `EN=0` 的替代拓扑 |
| 管壳式换热器 | 中低（仅两侧稳态换热） | 4（L2×4） | 6 端口/容器存量、相变、UA 来源、管束阻力 | 拆 `exchanger + tank`；先验收 HX-1–HX-4 |
| 容积型源头 | 中（p/T 单端口） | 4（L1×3、L2×1） | 8 端口、h 边界、两相、端口变量 | 写 junction 适配模板；补 `T(p,h)` 工具 |
| **合计** | — | **20** | — | 17 条可本地/CI 执行，3 条 L3 待标定或全量 job |

## 5 与矩阵及其他文档的关系

- 本文是 `BSL_MODULE_MAP.md` A 类主表的细化，对应第 1 行（管道通用）、第 4 行（截止阀）、第 7 行（泵曲线法）、第 10 行（管壳式换热器）、第 19 行（容积型源头）；A 类汇总见该文第 67 行，关键说明见第 113–126 行。本文不改写矩阵的优先级与人日。
- 与 `MODULES_P0.md`：该文第 185 行的“关阀后下游无压力参考”与本文 V-3/S-2 是同一约束；P0 的局部阻力 K 表口径不适用于本文的直管与阀门。
- 与 `MODULES_P1.md`：第 225 行明确内置 `pump`（矩阵第 7 行）与 `pump_variable_speed` 的分工；本文只验收内置 `pump`，不覆盖变物性内迭代。
- 与 `BASELU_REFERENCE_CASES.md`：该文 10 个 fixture 只作输入快照与契约对照，`expected_snapshot.convergence_verified=false`；本文不把 fixture 数值当期望，L3 若要用快照，必须先补 `measured_values`（该文第 85–94 行）。
- 与 `ALGORITHM.md` / `DATA_CONTRACT.md`：公式与单位以这两份为准；本文新增的只是“倍思鹿 → FluidNet”的字段对照和算例。
- 与 `BASELU_COMPARISON.md`：该文的“求解器黑盒、两相未支持、7 类内置模型是旧基线”三点继续有效；本文的 5 个模块都在当前 22 个模型范围内。
- 与 `DELIVERABLES.md` / `ROADMAP.md`：M2-A 是文档阶段，不改变交付物清单；真正落地需要把 17 条 L1/L2 写进 `tests/`，本文不创建测试文件。

## 6 风险与假设

1. **DLL 黑盒**：`PIPECV`、`VALVECV_SHUT`、`PUMPCV`、`SHTC_P`、`PTT_BKT`、`Netlink_*` 只有声明（`FudPhyLink.h` / `MODULEAPILINK.h`），没有定义；任何“复刻倍思鹿关联式”的说法都缺证据。本文只映射可见参数与分支。
2. **单位靠推断**：PJTDB 的 MPa/kJ·kg⁻¹/℃/mm 来自键名标签与量纲一致性，不是可读契约；`ASDFGHJ` 的 `WI/U/i/Phase/Var4/Var5` 又换了一套键名。移植前必须逐工程核对，不能全局套用。
3. **四元数组不是参数表**：索引 1/2 是全局影子值（同变量种类在整库重复数百次），不能当上下限、初值或容差；索引 0 也可能非收敛。
4. **版本分叉**：同一模块有中文/英文根 `.cpp` 与 `_D/_R` 变体，行为可能不同（`BSL_MODULE_MAP.md:10-13`）；本文行号以中文根 `.cpp` 与 `_Run.cpp` 为准，换版本需重核。
5. **物性差异**：倍思鹿用 `FUD_PH`，FluidNet 用 CoolProp/REFPROP；同一 p/h 的 T、cp 不完全相同。L2 容差已为此放宽，但仍可能出现 1–2% 的出口温度差。
6. **热力容差与线性化**：FluidNet 的 ε–NTU 在每轮对 `T(h)` 线性化（`ALGORITHM.md:184`），大温差/近相变时与手算偏差会放大；HX 算例只在水单相、常物性附近有效。
7. **验收边界**：本文只登记 17 条可执行算例与 3 条 L3；未运行全量 pytest、未运行倍思鹿 exe，因此“通过”只能在 CI 执行后宣称。L3 数值在回填前不得写成结论。
8. **假设清单**：水为单相液体；`reference` 物性常数按 `solver.py:20-22`；`cp=4180 J/(kg·K)` 仅用于手算；泵效率取目录默认 0.75；换热器两侧 K/d 相同；`CURVE_A` 的单位待标定。
