# M2-C 映射与验收：倍思鹿 C 类 8 模块 → FluidNet 制冷/冷库执行域

> 日期：2026-10-22。范围：`压缩机`、`蒸发器`、`蒸发式冷凝器`、`罐体卧式`、`罐体立式`、`中间冷却器`、`冷库库房`、`热力膨胀阀`（`BSL_MODULE_MAP.md:69`）。
> 倍思鹿侧只读证据：`F:\beisilu\倍思鹿数值仿真-V5.3\AlgModule\<模块>\code\<模块>_Run.cpp` 与中文根 `.cpp`（GBK；`_Run.cpp` 为 UTF-8）。**未运行任何 `.exe`**，未解 `.Modu/.pjt`。
> FluidNet 侧证据：`refrigeration/{devices,cycle,station,cold_store,examples}.py`、`catalog.py`、`docs/ALGORITHM.md`、`docs/DATA_CONTRACT.md`、`docs/BSL_MODULE_MAP.md`、`docs/MAPPING_A.md`、`tests/test_refrigeration_*.py`、`cases/cold-storage/single-room-minus18/references/workpoints.json`。
> 约束：只新增本文，不改其他文件；不写新设备；未运行全量 pytest。

## 1 目的与口径

### 1.1 本文做什么

C 类八项**必须**落到 `cold_store` / `refrigeration` 执行域（`BSL_MODULE_MAP.md:69`），不能在单相管网里表达。本文只回答：端口/参数/变量能否一一对上、对不上的是哪一条、能否用解析解或现有测试验收。落点全部是已注册模型（`catalog.py:182-475`）：

| 倍思鹿模块 | FluidNet 设备（`solver_model`） | 执行域 | 说明 |
| --- | --- | --- | --- |
| 压缩机 | `refrigerant_compressor` / `condensing_unit` | `refrigeration` / `cold_store` | 站级 / 整机二选一（`catalog.py:383-398`、`:257-313`） |
| 蒸发器 | `air_cooler` / `unit_cooler` | `refrigeration` / `cold_store` | `air_cooler` 属制冷站设备（`catalog.py:447`），`unit_cooler` 才是冷库 A 链冷风机（`:238`） |
| 蒸发式冷凝器 | `evaporative_condenser` | `refrigeration` | 湿球近似（`catalog.py:399-415`） |
| 罐体卧式 | `hp_receiver` | `refrigeration` | `saturated_vessel`，默认 3 m³/2 m（`catalog.py:374-376`） |
| 罐体立式 | `pumped_drum` / `lp_drum` | `refrigeration` | 同名 `saturated_vessel`（`catalog.py:377-382`） |
| 中间冷却器 | `lp_drum` + `cascade_exchanger` | `refrigeration` | 容器 + 复叠换热器组合（`catalog.py:424-435`） |
| 冷库库房 | `storage_room` / `cold_room` | `cold_store` / `refrigeration` | 前者带货物热节点（`catalog.py:193-237`），后者是站内热节点（`:137-160`） |
| 热力膨胀阀 | `expansion_valve` | `refrigeration` | Kv 节流、等焓闪发（`catalog.py:416-423`） |

同一模块对应两个 FluidNet 对象时的**二选一规则**：整机闭式循环走 `condensing_unit`；多容器/多机/复叠的站级走 `refrigerant_compressor` 与各站级设备。两条链不能混在同一个项目里（`cold_store.py:124-125`、`station.py:86-88`）。

### 1.2 数值口径与级别

- 期望值只来自解析式、CoolProp `PropsSI` 独立计算、仓库内已提交参考值（`workpoints.json`）。**不声称与倍思鹿逐位一致**，也不把倍思鹿输出当 oracle。
- 本文数值用内联 Python（CoolProp 7.2.0）复核；`workpoints.json` 由 8.0.0 生成，本地重算相对差 < 1e-9。
- **L1** 纯代数，单次调用或编译+求解即可断言；**L2** 依赖物性或联立迭代，容差放宽；**L3** 需倍思鹿标定或 CI 全量 job（`.github/workflows/ci.yml:14-44` 的 `backend (Python 3.11)`），只登记、不填数值。

### 1.3 命名与单位规则

- 倍思鹿端口为 `IMn_*`（入口槽）/`EXn_*`（出口槽），每槽 6 个标量 `FLOW/PRE/ENTHALPY/TEMP/VOLUME/Q`；槽位顺序由根 `.cpp` 的 `ModulePortGet(n,k)` 决定。
- 罐体/房间状态统一 `BKT_*`；FluidNet 为 `state.pressure_pa/temperature_k/mass_kg/.../level_ratio`（`catalog.py:359-372`）。`state1..4` 是 FluidNet 单级循环四状态点（吸气/排气/冷凝出口/节流出口，`cycle.py:72-98`），不是倍思鹿变量名。
- 单位以 `DATA_CONTRACT.md:51-72` 为准：压力 Pa、温度 K、比焓 J/kg、质量流量 kg/s、开度 1。倍思鹿端口是 MPa/kJ·kg⁻¹/℃/kg·m⁻³，`VOLUME` 是**密度不是体积**（同 `MAPPING_A.md:40`）。

### 1.4 证据边界

`.Modu`/`.pjt` 是 base64 密文（`BSL_MODULE_MAP.md:14`）。结论只建立在可见代码上：端口读取顺序、`ModuleGet/ModuleIntGet` 索引、分支条件，以及只有声明没有定义的 `BKT_CORE/LVL_LI/LVL_HI/PIPECV/PUMPCV`（同 `MAPPING_A.md:44`）。本文不推断 DLL 内部公式。

## 2 通用映射规则

### 2.1 端口域

| 域 | FluidNet 端口 | 压力在哪 | 说明 |
| --- | --- | --- | --- |
| `fluid` | `in0/out0`、`ch0` | 求解器节点 | C 类不进管网 |
| `refrigerant` | `suction/discharge`、`in0/out0`、`vapor/liquid`、`evap_in/evap_out/cond_in/cond_out` | **只在饱和容器**（`station.py:1-7`） | 压缩机、节流阀、冷凝器、容器、复叠、冷风机 |
| `thermal` | `heat`、`cold`、`supply` | 不建压力 | 库房、机组冷量、冷风机热口 |

1. 倍思鹿 `EXn` 在负流量时也承担入口语义（如 `压缩机_Run.cpp:17-42`）；FluidNet 端口方向只是标称，反向由负流量/容器间质量流表达。
2. 制冷站设备不能接出 `fluid` 端口，`compile_station` 拒收流体设备与 Python 模块（`station.py:86-88`）；冷库 A 链只能“机组 → 冷风机 → 库房”（`cold_store.py:149-163`）。一个端口只能连一次，分支必须用 `refrigerant_header`（`station.py:105-106`、`catalog.py:467-470`）。

### 2.2 变量命名：`IM/EX`、`BKT_*`、`state1..4`

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IMn_FLOW` / `EXn_FLOW` | `mass_flow_kg_s` | kg/s，×1 |
| `IMn_PRE` / `EXn_PRE` | `state.pressure_pa`、`pressure_ratio`、`pressure_drop_pa` | MPa→Pa，×1e6 |
| `IMn_ENTHALPY` / `EXn_ENTHALPY` | `state1..4.enthalpy_j_kg`、`liquid/vapor_enthalpy_j_kg` | kJ/kg→J/kg，×1000 |
| `IMn_TEMP` / `EXn_TEMP` | `state.temperature_k`、`discharge_temperature_k`、`evaporating_temperature_k` | ℃→K，+273.15 |
| `IMn_VOLUME` / `EXn_VOLUME` | `liquid/vapor_density_kg_m3` | **密度**，×1 |
| `IMn_Q` / `EXn_Q` | `state.quality`、`outlet_quality` | 0–1；倍思鹿用 `0`/`1` 表示纯液/纯气 |
| `BKT_M` / `BKT_V` | `state.mass_kg` / `param.volume_m3` | 存量与容积 |
| `BKT_LEVEL` | `state.level_ratio`、`state.level_m` | **口径不同，见 3.4/3.5** |
| `POWER`（压缩机） | `shaft_power_w`、`electric_power_w` | 倍思鹿是等熵功，FluidNet 除以 η |

### 2.3 参数索引：`ModuleGet(n)` → `param.<id>`

索引是**代码读取顺序**，不是稳定 ID；`ModuleGet` 里混有输出（`CV/RLS/RE/FLOW_SPD/POWER/FORCE_FLOW/DENSITY/BKT_*` 都是算完写回的量）。八项实测：

| 模块 | double | int | 读取段（中文根 `.cpp`） |
| --- | --- | --- | --- |
| 压缩机 | 15 | 4（`S_T/RUN_S/DN/EN`） | `压缩机.cpp:125-143` |
| 蒸发器 | 10 | 4（`S_T/RUN_S/EN/DN`） | `蒸发器.cpp:120-133` |
| 蒸发式冷凝器 | 10 | 4（`S_T/RUN_S/DN/EN`） | `蒸发式冷凝器.cpp:120-133` |
| 罐体卧式 | 16 | 2 | `罐体卧式.cpp:237-254` |
| 罐体立式 | 16 | 2 | `罐体立式.cpp:223-240` |
| 中间冷却器 | 23 | 3（`S_T/RUN_S/DN`） | `中间冷却器.cpp:232-257` |
| 冷库库房 | 20 | 2 | `冷库库房.cpp:324-345` |
| 热力膨胀阀 | 12 | 2 | `热力膨胀阀.cpp:121-134` |

### 2.4 回路、工质与“两相只在设备内部”

1. 站级回路由 `circuit_fluids` 指定，锚点是任一已连接制冷剂端口；同一回路只允许一种工质（`station.py:186-199`）。
2. 每个压力等级**恰好一个**饱和容器（`station.py:152-168`）；两容器直接相通报 `REFRIGERATION_VESSEL_SHORT`。压缩机与节流阀是“桥”，两端必须不同等级（`station.py:32,169-182`）；复叠两侧必须不同回路（`:180-182`）。
3. 冷风机必须由液泵出口供液（`station.py:211-219`）；冷库 A 链由机组 `cold` 供冷（`cold_store.py:149-159`）。
4. 两相只在设备函数内部：容器 `DmassUmass` 闪蒸（`devices.py:62-76`），压缩机取饱和气、节流阀取饱和液（`devices.py:90,127`）。**没有任何两相支路**（`ALGORITHM.md:369-371,420-422`）。

## 3 八个模块逐项

### 3.1 压缩机 → `refrigerant_compressor`（或 `condensing_unit`）

**倍思鹿语义**

- 两端口：槽位 0=`IM0`（吸气）、1=`EX0`（排气）（根 `.cpp:111-124`）。
- 流量 ≥0 时 `FUD_PH(IM0)` 求熵，再 `FUD_PS(EX0_PRE, entropy)` 得**等熵**排气焓；负流反向（`压缩机_Run.cpp:17-42`）。功率 `POWER=m(EX0_ENTHALPY−IM0_ENTHALPY)`（`:28,41`）：只有等熵功，**没有**等熵/容积/电机效率。
- 内置压力环：`MuBiaoPre>0.1` 时按 `OutPutPre` 与目标比较，每步 `Opening*0.9` 或 `*1.1`，否则 `*1.1`，再夹 [0,1]（`:43-67`）。按字面 `OutPutPre<MuBiaoPre` 时**减小**开度（增益方向与常规压力控制器相反，移植需重定符号）。
- 流量 `FORCE_FLOW=FORCE_VOLUME*ROTATE_SPEED*IM0_VOLUME*0.001*Opening*EN`（`:69`），负值置 0，再 `PIPECV`+`Netlink_Cpsr`（`:95-96`）。

**FluidNet 落点**

`refrigerant_compressor`（`catalog.py:383-398`）：`m=V_d·load·η_vol·ρ_v(p_suc)`，`h2=h1+(h2s−h1)/η_is`，`P_shaft=m(h2−h1)`，`P_el=P_shaft/η_motor`（`devices.py:86-111`、`cycle.py:20-28`）；压比超包络只警告（`devices.py:104-107`）。`condensing_unit` 走 `cycle_point`，另有 `superheat_k/subcooling_k`、`state1..4` 与含排气温度的包络（`cycle.py:78-119`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0_*` / `EX0_*` | `suction` / `discharge`（或 `state1/state2`） | 吸气饱和气、排气 |
| `FORCE_VOLUME` | `param.displacement_m3_s` | 单位待标定（若 L 则 ×0.001） |
| `ROTATE_SPEED` | `param.load_ratio` | FluidNet 无转速，只能比例近似 |
| `Opening` | `param.load_ratio` | 0–1 夹紧后一一对应 |
| `EN`（int） | `param.running` | ≥0.5 为运行（`devices.py:16-17`） |
| `POWER` | `shaft_power_w` | 倍思鹿等熵功，FluidNet 含 η_is |
| 无 | `isentropic_efficiency=0.72`、`volumetric_efficiency=0.8`、`motor_efficiency=0.92` | 目录默认（`catalog.py:389-391`） |

**映射差异与缺口**

1. **效率**：同工况 `m_FN/m_BSL=η_vol=0.8`、`P_FN/P_BSL=1/η_is≈1.389`。数值：NH3、243.15/308.15 K，BSL 给 `FORCE_FLOW=0.083572 kg/s`（`FORCE_VOLUME` 按 L 解读）、等熵功 `24944.80 W`；FluidNet 给 `0.066858 kg/s`、`34645.56 W`。
2. **排量语义**：`×0.001` 与 `ROTATE_SPEED` 的乘积口径不可见；`FORCE_VOLUME` 是 L、m³/h 还是每转排量无法确认，未标定前不能当同一参数。
3. **控制位置**：倍思鹿把压力环写在模块内（每步 ±10%）；FluidNet 交给 PID，设备只读 `load_ratio`（`examples.py:219`）。
4. **排气温度**：站级 `compressor_point` 只检查压比，不检查排气温度；`condensing_unit` 才有 `max_discharge_temperature_k`（`cycle.py:103-119`）。默认 `η_is=0.72`、压比 11.31 时排气 480.15 K，走 A 链会被 `REFRIGERATION_ENVELOPE` 拦下（上限 393.15 K），走 B 链不会。
5. **阻力/性能图**：`PIPECV/Netlink_Cpsr` 的阻力与惯性在站级模型里不存在；螺杆/涡旋性能图、经济器、双级、油冷两边都没有；`CPSRSCREW.cpp` 与中文根差 14 行（`BSL_MODULE_MAP.md:10`）。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| C-1 | L2 | `refrigerant_compressor` 默认；NH3，`p_s=psat(243.15)=119375.60 Pa`、`p_d=psat(308.15)=1349991.70 Pa` | `ρ_v=1.037447`、`m=0.0668577 kg/s`、`h2s=1942095.68`、`h2=2087191.31 J/kg`、`P_shaft=34645.56 W`、`P_el=37658.22 W`、`T2=480.145 K`、`PR=11.3088`，无诊断（`test_refrigeration_devices.py:114-131`） | rel 1e-6 |
| C-2 | L2 | `condensing_unit`，R290，245.15/313.15 K、10 kW，`superheat=5 K`、`subcool=3 K`、`η_is=0.65`、`η_vol=0.75`、`η_m=0.9` | `V_disp=0.013035025 m³/s`、`UA_c=1996.4919 W/K`、`m=0.039694084 kg/s`、`P_shaft=5971.935 W`、`P_el=6635.483 W`、`T2=353.0927 K`、`PR=7.547347`、`q4=0.404439`、`Q_cond=15971.935 W`（`workpoints.json`；本地重算差 <1e-9） | rel 1e-6 |
| C-3 | L1 | 同 C-1，`load_ratio=0.5`；`running=0`；`p_d<p_s` | 流量与轴功精确减半；停机 `(m,P_el,T2)=(0,0,null)`；反向压差抛 `COMPRESSOR_PRESSURE_RATIO`（测试 `:126-141`） | 精确/错误码 |
| C-4 | L3 | 倍思鹿同一边界跑一次 `压缩机.exe`，读 `FORCE_VOLUME/FORCE_FLOW/POWER/EX0_ENTHALPY` | 标定 `FORCE_VOLUME` 后令 `η=1`，复算 `m` 与等熵功应回到 BSL 值；数值待回填，由 CI 全量 job 登记 | 待回填 |

**结论：可映射（设备级）；需参数化（排量单位、效率等价）；压力环与管网阻力暂不可映射。**

### 3.2 蒸发器 → `air_cooler`（站级）/ `unit_cooler`（冷库 A 链）

**倍思鹿语义**

- `EN<0.5`：等焓旁通，`EX0_ENTHALPY=IM0_ENTHALPY` 后查 `FUD_PH(EX0_PRE)`（`蒸发器_Run.cpp:17-39`）。
- `EN≥0.5`：`FUD_SATP(EX0_PRE)` 求饱和温度，**+0.5 K**，再 `FUD_TP` 得出口焓（`:44-56`）；反向同理（`:57-69`）。
- **没有 UA、没有空气侧、没有换热关联式**：只把出口钉在“出口压力对应饱和温度 +0.5 K”。
- 平均量 `DENSITY/MID_PRE/FLOW_VOLUME=3600·m/ρ`（`:74-81`），阻力 `PIPECV`+`Netlink_Pipe`（`:93-94`）。

**FluidNet 落点**

`air_cooler`（`catalog.py:447-466`）三端口 `in0/out0/heat`，`Q=min(UA_eff(T_room−T_evap)⁺, m_supply·h_lv·x_max)`，风机热留在库内（`devices.py:165-182`）。冷库 A 链用 `unit_cooler`：`Q=UA_e(T_room−T_evap)` 与循环联立（`cold_store.py:376-384`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0/EX0` | `in0/out0` | 单通路 |
| `OUTTEMP` | `evaporating_temperature_k` | 倍思鹿输出，FluidNet 由 `p` 饱和温度派生 |
| +0.5 K 过热（硬编码） | `max_outlet_quality` + 循环 `superheat_k` | 复现 0.5 K 须把 `superheat_k` 设为 0.5 |
| 无 | `ua_w_k` | 必须由设计点反算 `UA=Q_rated/(T_room−T_evap)` |
| `EN` | `running` | 语义不同，见缺口 3 |

**映射差异与缺口**

1. **自由度相反**：倍思鹿给定出口状态、换热量由别处决定；FluidNet 给定 UA 与库温、换热量由 `UA·ΔT` 与供液量决定。不补 UA 就无解。
2. **0.5 K 硬编码 vs 5 K 参数**：`superheat_k` 默认 5 K，且库温与蒸发温度差小于过热度时报 `CYCLE_SUPERHEAT_APPROACH`（`cycle.py:137-143`）。R290 额定点把 5 K 改 0.5 K：`m` 由 0.039694084 变 0.040811808（+2.82%），`T2` 由 353.093 变 348.308 K。
3. **`EN=0` 旁通无对应**：`air_cooler` 在 `running=0` 时仍按自然 UA 给 `0.1·UA·ΔT=9600 W`（`devices.py:171-177`），不是等焓旁通；最接近的零换热量对象是 `refrigerant_header`（只做拓扑）。
4. **两相出口**：FluidNet 用干度上限截断供液不足（`devices.py:175-176`），倍思鹿用固定过热；满液式沸腾、干涸、分液不均两边都没有。
5. **阻力**：倍思鹿蒸发器是带 `PIPECV` 的管网元件；FluidNet 冷风机是等压代数设备。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| E-1 | L2 | `air_cooler` 默认（UA=12000 W/K、风机 4000 W、`x_max=0.5`）；CO2 `p=psat(247.15)=1629263.74 Pa`、库温 255.15 K、供液 1 kg/s | `Q=96000 W`、`room_cooling=92000 W`、`x_out=0.325036`、`h_out=237686.94 J/kg`；供液 0.1 kg/s 时 `Q=14767.59 W`、`x_out=0.5`（`test_refrigeration_devices.py:204-223`） | rel 1e-6 |
| E-2 | L2 | `condensing_unit` R290 额定点不变，仅 `superheat_k=0.5` | `state1.t=245.65 K`、`m=0.0408118 kg/s`、`P_shaft=6002.78 W`、`T2=348.308 K`、制冷量仍 10 kW | rel 1e-6 |
| E-3 | L1 | 同 E-1：`superheat 5→0.5` 对照；`running=0` 的旁通等价性 | 5 K → `m=0.0396941`、`T2=353.093 K`；并断言 `air_cooler(running=0)` 仍给 9600 W ≠ 0，旁通不可表达（负向验收） | 精确/rel 1e-9 |
| E-4 | L3 | 倍思鹿 `EN=1` 稳态，读 `OUTTEMP/EX0_ENTHALPY/EX0_FLOW` 与房间温度 | 反算 `UA_eff=m(h_out−h_in)/(T_room−T_evap)`；需倍思鹿侧同时给房间温度，数值待回填 | 待回填 |

**结论：需参数化（UA、过热度）；设备级可映射，`EN=0` 旁通与出口定压语义暂不可验收。**

### 3.3 蒸发式冷凝器 → `evaporative_condenser`

**倍思鹿语义**

- `EN≥0.5`：`FUD_SATP(EX0_PRE)` → `OUTTEMP=T_sat−0.5`，`FUD_TP` 得出口焓（`蒸发式冷凝器_Run.cpp:45-52`），即“出口压力下饱和液 −0.5 K”。
- `EN<0.5`：等焓旁通（`:17-39`）；平均量与阻力同蒸发器（`:71-91`）。
- **没有 UA、湿球、风机、喷淋水**；名字虽是“蒸发式”，代码只做定压饱和液出口。

**FluidNet 落点**

`evaporative_condenser`（`catalog.py:399-415`）：`UA_eff=UA(nat+(1−nat)fan)(flood+(1−flood)rg)`，`Q=UA_eff(T_cond−T_wb)` 保留符号，风机功率随 `fan`（`devices.py:114-122`）。站级把 `Q` 从所在容器内能中扣除（`station.py:278-283`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0/EX0` | `in0/out0` | 排气进、冷凝液出 |
| `OUTTEMP` | `condensing_temperature_k` | 由容器压力反算 |
| 0.5 K 过冷 | `subcooling_k`（仅 `condensing_unit`） | B 链容器是饱和态，无过冷 |
| 无 | `ua_w_k` | 由 `Q_rated/(T_cond−T_wb)` 反算 |
| 无 | `wet_bulb_temperature_k`、`fan_ratio`、`return_gas_ratio` | 倍思鹿无环境与执行器 |
| `PL/DN/CV/RLS/DHIGH` | 无 | 无压降 |

**映射差异与缺口**

1. **已知/未知互换**：倍思鹿给定出口状态、由网络定 `Q`；FluidNet 用 UA 与湿球定 `Q`、由容器定 `T_cond`。不是同一自由度，不能互作期望值。
2. **湿球近似**：`ALGORITHM.md:378-379` 明确“按湿球温差近似，不解喷淋水与空气焓差”；倍思鹿连湿球都没有。喷淋水、结垢、水耗两边都没有。
3. **负排热**：FluidNet 在 `T_cond<T_wb` 时给负值（`devices.py:120-121`，测试 `:156-157`）；倍思鹿无此分支。
4. **过冷**：0.5 K 只能落在 A 链 `subcooling_k`；B 链容器是饱和两相，过冷无处安放。
5. **阻力/惯性**：同 3.2，`PIPECV`/`Netlink_Pipe` 在站级不存在。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| EC-1 | L2 | NH3 `p=psat(308.15)`；默认 UA=40000 W/K、`T_wb=300.15 K`、`fan=1`、`rg=1` | `UA_eff=40000`、`Q=320000 W`、`T_cond=308.15 K`、`fan_power=7500 W`（`test_refrigeration_devices.py:144-157`） | rel 1e-6 |
| EC-2 | L2 | 同 EC-1：`fan=0`；`rg=0`；`fan=0.5,rg=0.5` | `UA_eff=8000/20000/18000`；`Q=64000/160000/144000 W`；`fan=0` 时风机功率 0 | rel 1e-6 |
| EC-3 | L2 | 同 EC-1，`T_wb=310.15 K`（高于冷凝温度） | `Q=−80000 W`，符号保留、不抛错 | rel 1e-6 |
| EC-4 | L3 | 倍思鹿 `EN=1`，读 `OUTTEMP/EX0_Q/EX0_ENTHALPY` 与所在容器压力 | 验证出口是否真为饱和液 −0.5 K，并用 `Q=m(h_in−h_out)` 反算 UA 与湿球当量温差 | 待回填 |

**结论：需参数化（UA、湿球、风机/回气阀）；设备级可映射，倍思鹿“定压出口”语义不可验收。**

### 3.4 罐体卧式 → `hp_receiver`

**倍思鹿语义**

- 几何 `BKT_V=4πSR³/3+πSR²(SL−2SR)`（`罐体卧式_Run.cpp:35`），两端半球封头的卧式圆筒；质量/能量按 5 进 5 出累加并乘 `S_T/1000`（`:38-66`）。
- 调用**不可见**的 `BKT_CORE(M,H,DL,V,Q,MIX,D_M,D_ENTHALPY,D_F,D_H)`（`:76`）；`BKT_D=M/V`，`FUD_DH(D,H)` 反求 `T/p/Q`（`:78-81`）；`M_L=M(1−Q)`（`:92-106`）。
- `LVL_LI(SR,SL,DL,M_L,LEVEL)` 不可见，`BKT_LEVEL=LEVEL/(2R)`（`:107-108`）；`LEVEL<0.03` 时前四个出口给气、`EX4` 给液（`:369-425`），其余按 `LEVEL<0.51` 等阈值切换。
- 静压修正：`IM3_PRE=BKT_PRE+ρg·SR/1e6`、`IM4_PRE=+2SR`（`:228-229`），另一分支用当前 `LEVEL`（`:485`）。10 端口（槽位 0–4 入、5–9 出，根 `.cpp:167-235`），16 double + 2 int（`:237-254`）。

**FluidNet 落点**

`hp_receiver`=`saturated_vessel`（`catalog.py:345-376`）：4 端口 `in0/in1/vapor/liquid`，参数 `volume_m3/height_m/temperature_k/level_ratio/min_level_ratio/max_level_ratio`。`(M,U)` 经 `state_du` 反求 `T/p/q`，液位=液相体积/总容积，`level_m=level_ratio×height`，带外报 `VESSEL_LEVEL_RANGE`（`devices.py:62-83`）。压缩机吸气取 `vapor`、节流阀/液泵取 `liquid`（`station.py:24-26,139-146`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0–IM4` | `in0`/`in1`（+ `refrigerant_header`） | 5 路入口合并，各支路流量不可见 |
| `EX0–EX4` | `vapor`/`liquid` | 压缩机吸气取气、节流阀/泵取液 |
| `BKT_SR/BKT_SL` | `volume_m3` + `height_m` | 几何折成容积与液位高度 |
| `BKT_PRE/BKT_TEMP` | `param.temperature_k` + `state.pressure_pa` | 压力由 `(M,U)` 反求 |
| `BKT_LEVEL` | `state.level_ratio` | **口径不同**，见缺口 2 |
| `BKT_DL/BKT_DV/BKT_Q` | `liquid/vapor_mass_kg`、`quality` | ×1 |
| `D_FT/D_H/MODEL/runtime` | 无 | DLL 输出或模型选择器 |

**映射差异与缺口**

1. **端口 10 vs 4**：必须先把 5 路入口并到 `in0/in1`，再按角色把 5 路出口分成气/液；`REFRIGERATION_PORT_ROLE` 会拒绝把节流阀接到气相口。
2. **液位口径（本文最重要的一处）**：`BKT_LEVEL=LEVEL/(2R)` 是“充液高度/直径”，`level_ratio` 是“液相体积分数”。卧式圆筒两者非线性：`h/D=0.25 ↔ 0.195501`，`h/D=0.05 ↔ 0.018693`；直接当 `level_ratio` 用，5% 充液高度处液相质量高估 **2.675 倍**。
3. **`BKT_CORE` 不可见**：内部可能含闪蒸、含气率与液位修正；FluidNet 是 `state_du` 闪蒸 + 体积分数，中间量不可比。
4. **分层取液丢失**：倍思鹿给不同高度端口加 `ρgΔh`；FluidNet 所有端口同压，也没有“第几路”的概念。
5. **适用带与单容器**：FluidNet 液位带 `[0.05,0.95]` 越带即停（`devices.py:79-83`，测试 `:104-109`）；倍思鹿只在 `LEVEL<0.03` 时翻口气。站级每级只能一个容器（`station.py:152-159`）。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| V-1 | L2 | `hp_receiver`，NH3 308.15 K、V=3 m³、H=2 m、`level=0.62` | `M=1104.8212 kg`、`U=574497634.3 J`；往返 `T=308.15 K`、`p=1349991.70 Pa`、`level=0.62`、`level_m=1.24 m`（测试 `:57-75`） | T abs 1e-6 K、level abs 1e-7 |
| V-2 | L1 | 倍思鹿几何 `SR=0.5 m`、`SL=2 m` | `BKT_V=1.308997 m³`；`volume_m3=1.308997`、`level=0.62` 时液相 0.8116 m³；`h/D=0.25 ↔ 0.195501` | rel 1e-6 |
| V-3 | L1 | 初始 `level_ratio=0.96`；运行中液位越带 | 编译报 `VESSEL_INITIAL_STATE`；运行报 `VESSEL_LEVEL_RANGE` 并保留已接受帧（测试 `:104-109`） | 错误码 |
| V-4 | L3 | 10 端口拓扑 + `BKT_CORE`：同一 `(M,U)` 下比较 `BKT_LEVEL` 与 `level_ratio` 整条曲线 | 需 2 h 倍思鹿运行导出 `BKT_LEVEL/BKT_Q`；本文只给换算关系，不填数值 | 待回填 |

**结论：可映射（容器本体与液位）；需参数化（几何→容积、液位口径）；分层取液与 10 端口暂不可验收。**

### 3.5 罐体立式 → `saturated_vessel`

**倍思鹿语义**

- 几何同 3.4 的圆筒式（`罐体立式_Run.cpp:35`，用 `BKT_SH` 作高度）；`LVL_HI` 求液位（`:107`），`BKT_LEVEL=LEVEL/(2R)`（`:108`）。
- 9 端口：槽位 0–3 为 `IM0–IM3`、4–8 为 `EX0–EX4`（根 `.cpp:160-221`），16 double + 2 int（`:223-240`）。
- 其余算法（`BKT_CORE`、`FUD_DH`、`M_L=M(1−Q)`、气/液切换）与 3.4 同构。

**FluidNet 落点**

同一个 `saturated_vessel`（`catalog.py:345-372`）。立式等截面 `level_m=level_ratio×height_m`（`devices.py:74-75`）；`pumped_drum` 默认 3 m³/2 m、初始液位 0.4（`catalog.py:380-382`），液位带同为 `[0.05,0.95]`。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0–IM3` | `in0`/`in1` | 4 路入口合并 |
| `EX0–EX4` | `vapor`/`liquid` | 按角色 |
| `BKT_SR/BKT_SH` | `volume_m3`/`height_m` | `V=4πR³/3+πR²(H−2R)` |
| `BKT_LEVEL` | `level_ratio` | 差 `H/(2R)` 的尺度，见缺口 1 |
| `BKT_Q/BKT_M/BKT_DL/BKT_DV` | `quality/mass_kg/liquid/vapor_density_kg_m3` | ×1 |

**映射差异与缺口**

1. **同一厂商两种液位口径**：罐体立式与卧式都写 `BKT_LEVEL=LEVEL/(2R)`（`罐体立式.cpp:356`、`罐体卧式.cpp:370`），中间冷却器写 `LEVEL/BKT_SH`（`中间冷却器.cpp:402`）。立式等截面（名义）体积分数应为 `LEVEL/H`，`/(2R)` 版本系统性偏大 `H/(2R)`：V=4 m³、H=2 m 时 `R=0.969944`，满罐 `BKT_LEVEL=1.031`（103.1%）。移植必须以体积分数重算。
2. **端口 9 vs 4**：4 进 5 出合并成 2 进 2 出，失去每一路的独立状态；`BKT_CORE/LVL_HI` 仍是黑盒。
3. **静压分层**：立式罐同样按高度给端口加 `ρgΔh`（与卧式同构的段落）；FluidNet 无。
4. **壁面/环境**：两边都没有容器散热项。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| V-5 | L1 | V=4 m³、H=2 m、`level_ratio=0.4` 与 `0.9` | 反解 `R=0.969944`；`level_m=0.8 m` 与 `1.8 m`；`level_ratio` 往返不变（`devices.py:74-75`） | abs 1e-6 |
| V-6 | L1 | 满罐 `LEVEL=H=2 m`、R=0.969944 | 倍思鹿 `BKT_LEVEL=1.031` vs FluidNet `1.0`，系统偏差 3.1%；换算 `level_ratio=BKT_LEVEL·2R/H` | 数值对照 |
| V-7 | L3 | 9 端口真实拓扑 + 液位曲线 | 需倍思鹿 2 h 运行导出 `BKT_LEVEL`；由 CI 全量 job 登记 | 待回填 |

**结论：可映射（立式等截面液位）；需参数化（`/(2R)` 口径改正、端口合并）；分层取液暂不可验收。**

### 3.6 中间冷却器 → `lp_drum` + `cascade_exchanger`

**倍思鹿语义**

- 9 端口：槽位 0–2=`IM0–IM2`、3–5=`EX0–EX2`、6=`EX3`、7=`IM3`、8=`EX4`（根 `.cpp:169-230`）。`EX3` 是第三个容器出口，`IM3/EX4` 是穿过容器的**盘管**。
- 盘管换热量 `Tra_H=(IM3_ENTHALPY−EX4_ENTHALPY)·EX4_FLOW`（`中间冷却器_Run.cpp:26-29`），并入容器能量（`:93`）；盘管出口被钉在容器饱和温度 `FUD_TP(BKT_TEMP, EX4_PRE)`（`:26`）。
- 容器本体：`BKT_V`（`:67`）、`BKT_CORE`（`:104`）、`FUD_DH`（`:108`）、`LVL_HI` + `BKT_LEVEL=LEVEL/BKT_SH`（`:135-136`）。
- 液位分档：`LEVEL≤H/4`、`≤H/2`、`≤3H/4` 决定三个出口取气还是取液（`:237-326`），同时给 `IM0/IM1/IM2` 加 `ρgH/4, /2, 3H/4` 静压（`:222-229`）。23 double 中 10 个是管网量（`DENSITY/MID_PRE/PL/CV/RLS/FLOW_SPD/DHIGH/RE/FLOW_VOLUME/DN`），不是设备参数（根 `.cpp:246-257`）。

**FluidNet 落点**

`lp_drum`（`catalog.py:377-379`）提供容器；`cascade_exchanger`（`catalog.py:424-435`）四端口 `evap_in/evap_out`（`evaporating`）与 `cond_in/cond_out`（`condensing`），`Q=UA(T_sat,cond−T_sat,evap)`，两侧按潜热折算流量（`devices.py:137-145`）。可执行拓扑见 `examples.py:280-283`（`LP1.liquid→HX1.evap_in`、`CD1.vapor→HX1.cond_in`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0–IM2` / `EX0–EX3` | `lp_drum.in0/in1` / `vapor`、`liquid` | 3 路进、4 路出合并；液位不再改变出口相态 |
| `IM3/EX4`（盘管） | `cascade_exchanger` 一侧 | 另一侧接另一回路 |
| `Tra_H` | `heat_w` | 倍思鹿由焓差，FluidNet 由 UA×ΔT_sat |
| 无 | `ua_w_k` | 必须由设计点反算 |
| `BKT_SR/BKT_SH` | `volume_m3`/`height_m` | 几何 |
| `BKT_LEVEL` | `level_ratio` | 与 3.5 同一口径问题 |
| `ρgH/4` 静压 | 无 | 端口同压 |

**映射差异与缺口**

1. **换热的自由度相反**：倍思鹿 `Q=m_pass(h_in−h_out)` 且出口钉在容器饱和温度；FluidNet `Q=UA·ΔT_sat`。要等价必须先用设计点反算 UA，并接受“出口饱和”假设。
2. **液位分档丢失**：倍思鹿在 H/4、H/2、3H/4 切换“哪个口出气”，FluidNet 端口角色静态（`station.py:24-26`），液位只影响 `level_ratio` 与越带停机。
3. **静压分层丢失**：`IM0/IM1/IM2` 的三个不同压力在 FluidNet 里是同一个容器压力。
4. **中间压力自平衡**：倍思鹿靠网络求解；FluidNet 靠“两个压力等级 + 桥设备”，每级只能一个容器（`station.py:152-168`）。
5. **端口 9 → 4+4**：`IM3/EX4` 与主容器分属不同回路角色，复叠两侧不能同回路（`station.py:180-182`）；`BKT_CORE/LVL_HI` 仍是黑盒。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| IC-1 | L2 | `cascade_exchanger` 默认 UA=45000 W/K；NH3 243.15 K / CO2 247.15 K | `Q=180000 W`、`approach=4 K`、`evaporated=0.132378 kg/s`、`condensed=0.609443 kg/s`（潜热 1359745.75 / 295351.81 J/kg；`test_refrigeration_devices.py:173-183`） | rel 1e-6 |
| IC-2 | L2 | 盘管等价：`m_pass=0.5 kg/s`、`Q=180 kW` | `Δh=360000 J/kg`，即 `Tra_H=m_pass·Δh` 与 `heat_w` 同值；反算 `UA=Q/ΔT_sat` | rel 1e-6 |
| IC-3 | L1 | `lp_drum` 液位 0.3 与 0.8；压缩机吸气、节流阀取液 | 两种液位下 `vapor` 恒气相、`liquid` 恒液相（`station.py:139-146`）；倍思鹿在 `LEVEL≤H/4` 时 `EX0–EX3` 全出气（`:237-282`）→ 负向验收 | 精确 |
| IC-4 | L3 | 两级 NH3、中间 −5 °C（`BSL_MODULE_MAP.md:40`） | 闪发气量与主路出口需倍思鹿运行；本文只登记，数值由 CI 全量 job 回填 | 待回填 |

**结论：需参数化（UA、液位口径、端口合并）；容器 + 复叠可映射，液位分档、静压分层与真正的“中间冷却”暂不可验收。**

### 3.7 冷库库房 → `storage_room` / `cold_room`

**倍思鹿语义**

- 15 个流体端口（槽位 0–7=`IM0–IM7`，8–14=`EX0–EX6`）加 1 个信号口（槽位 15=`EX7`，`OnOff/Analog/Digital/PWM/COM/TCP`，根 `.cpp:212-322`）；信号口只广播 `EX7_OnOff=1`、`EX7_Analog=BKT_TEMP`（`:120-121`）。
- 几何 `BKT_V=BKT_LL·BKT_LH·BKT_LW`（`冷库库房_Run.cpp:38`）——**矩形定容体**；质量/能量按 8 进 7 出累加（`EX7` 被注释，`:47-88`），`D_ENTHALPY=D_ENTHALPY+NUMBER`（`:87`）是唯一内热源；再 `BKT_D=M/V`、`FUD_DH(D,H)` 反求 `T/p/Q`（`:116-119`）。
- 所有进出口的焓/温/密度/干度都赋成容器状态，所有流体端口压力置 `BKT_PRE`（`:131-326`）。
- 参数 20 double + 2 int（根 `.cpp:324-345`）；`InsideTemperature/OutsideTemperature/InsideHumidity/OutsideHumidity/InsidePm25/OutsidePm25` 在 `_Run.cpp` 里**完全没有出现**（只有 `NUMBER` 参与计算），属于未实现的组态字段。

**FluidNet 落点**

`storage_room`（`catalog.py:193-237`）是**热节点**：单 `heat` 入端口，参数含库温初值、等效热容、围护/地面 UA、照明、附加热负荷、货物质量/比热/初温/`UA_g`；方程 `C dT/dt=UA_air(T_amb−T)+UA_floor(T_g−T)+Q_door+Q_light+Q_other+Q_fan+f·Q_defrost+Q_goods−Q_coil`（`cold_store.py:352-397`、`ALGORITHM.md:350-357`）。`cold_room` 是站内更简的热节点（`catalog.py:137-160`、`station.py:309-316`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| 8 进 / 7 出 | 单个 `heat` 入 | 冷库 A 链热端口一对一（`cold_store.py:140-143`） |
| `NUMBER` | `param.heat_input_w` | 内热源 |
| `BKT_LL/LH/LW/BKT_V` | 无 | 房间不是流体容积；UA 由几何×U 值单独给（测试 `:418-420`） |
| `BKT_PRE/BKT_H/BKT_M/BKT_Q` | 无 | 库房没有制冷剂状态 |
| `BKT_TEMP` | `state.temperature_k` | 唯一可直接对齐的状态量 |
| `OutsideTemperature` | `param.ambient_temperature_k` | 室外温度 |
| `EX7` 信号口 | 无 | 冷库域不支持信号端口；需要控制脚本 |

**映射差异与缺口**

1. **物理对象不同**：倍思鹿是“定容两相流体罐 + 一个内热源”，FluidNet 是“空气 + 货物两热节点 + 围护漏热 + 事件”。只有“能量守恒 + 温度”这一层可比，`p/Q` 没有对应物。
2. **热流项缺失**：倍思鹿没有围护 UA、开门、照明、融霜、货物；FluidNet 的 9 类热流在倍思鹿侧只有 `NUMBER`。
3. **端口 15 vs 1**：倍思鹿可多路同时进出并各自带状态；FluidNet 冷库链严格一对一（`cold_store.py:140-163`）。
4. **两相房间不在计划**：`ALGORITHM.md:420-422` 明确“气液两相闭式罐”不在后续计划，不能用 FluidNet 复刻房间内闪蒸。
5. **信号口**：`EX7` 在冷库域无对应，控制只能走 PID/脚本；`BKT_CORE/FUD_DH` 仍是黑盒。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| R-1 | L1 | `storage_room` 默认：`UA_air=46.08 W/K`、`UA_floor=20 W/K`、`T_amb=305.15 K`、`T_g=283.15 K`、无冷量与附加热 | 稳态 `T=(46.08·305.15+20·283.15)/66.08=298.4914 K`；围护净热流 0 W（残差 1.6e-12） | abs 1e-3 K |
| R-2 | L2 | 同 R-1，初温 255.15 K，关门闭库 1 h、无冷量，隐式 Euler 单步 h=60 s | `T'=(C·T+h(UA_air·T_amb+UA_floor·T_g))/(C+h·UA)=255.29273 K`（C=1.2e6 J/K） | abs 1e-3 K |
| R-3 | L2 | 同 R-1，开门事件 `door_heat 5000 W × 600 s`，无冷量 | `ΔT=Q·Δt/C=2.5 K`，叠加在 R-1 稳态起点上 | abs 0.01 K |
| R-4 | L3 | 倍思鹿定容房间：给定 `BKT_V`、`NUMBER`、入口状态，比较 2 h 后 `BKT_TEMP/BKT_PRE` | 只能比“总冷量/温度”且需把房间当黑箱；由 CI 全量 job 登记 | 待回填 |

**结论：需参数化（房间热模型换元）；库房温度层可映射，定容两相房间、15 端口与信号口暂不可验收。**

### 3.8 热力膨胀阀 → `expansion_valve`

**倍思鹿语义**

- 等焓节流：`EX0_ENTHALPY=IM0_ENTHALPY` 后 `FUD_PH(EX0_PRE)`（`热力膨胀阀_Run.cpp:17-27`）。
- 经验式：`CP=0.02005√ρ_in+6.34·EX0_CV`（`:58`）、`AV=(1.9+0.28·TC)·1e-6`（`:60`）、`M_PRE=IM0_CV·m²/CP²/AV²`（`:62`）、`CV=ρ_in·√(DENSITY/M_PRE)`（`:64`）、`EX0_PRE=IM0_PRE−M_PRE`（`:66`）；随后 `PUMPCV`+`Netlink_Valve`（`:73-74`）。
- `TC` 是过热度但**只读不调**：没有“过热度→开度”闭环，`AV` 只随 `TC` 变。12 double + 2 int（根 `.cpp:121-134`）。

**FluidNet 落点**

`expansion_valve`（`catalog.py:416-423`）：`m=Kv·opening·√(1000·ρ_l·Δp/1e5)/3600`，`Δp≤0` 或开度 0 时为零，出口按等焓闪发（`devices.py:125-134`）。站级里它是“桥”，把质量从高压容器搬到低压容器（`station.py:32,271-277`）。

| 倍思鹿 | FluidNet | 换算/说明 |
| --- | --- | --- |
| `IM0` / `EX0` | `in0` / `out0` | 高压饱和液进、低压两相出 |
| `M_PRE` | `pressure_drop_pa` | 输出；倍思鹿也算出来写回 |
| `IM0_CV` / `EX0_CV` | `param.kv_m3_h` | **不同量纲/尺度**，见缺口 2 |
| `TC`（过热度） | 无 | 需外挂 PID 读 `state1` 过热度写 `opening_ratio` |
| `AV`（流通面积） | `param.opening_ratio` | 语义相近但无物理面积 |
| `PUMPCV/RLS/CV/R` | 无 | 无阻力/惯性 |

**映射差异与缺口**

1. **自调特性缺失**：倍思鹿是“过热度→压降”静态经验式；FluidNet 是“开度→Kv→流量”。复现自调必须外挂闭环，设备本身没有过热度输入。
2. **量纲不可用**：取 `ρ=580 kg/m³`、`CV=0.5`、`TC=5 K`、`m=0.05 kg/s`，BSL 式给 `CP=3.6529`、`AV=3.3e-6`、`M_PRE=8.6023e6`；若压力单位是 MPa 则荒谬。反解 `Δp=1.2 MPa` 需 `CV≈0.0697`，说明 `CV` 不是 Kv、公式内嵌未公开尺度，**不能当 oracle**。
3. **压力自由度**：倍思鹿直接算 `EX0_PRE`；FluidNet 的出口压力由下游容器给定，阀门不设定压力。
4. **方向与动态**：两边都只允许正向（`devices.py:130-131`）；MOP、感温包动态两边都没有（`BSL_MODULE_MAP.md:46`）。
5. **阻力**：`PUMPCV` 与 `Netlink_Valve` 的 `RLS` 在 FluidNet 不存在。

**验收算例**

| ID | 级别 | 输入 | 期望 | 容差 |
| --- | --- | --- | --- | --- |
| TX-1 | L2 | NH3，`p_in=psat(308.15)=1349991.70`、`p_out=psat(243.15)=119375.60`、`Kv=1.2`、`opening=0.4` | `Δp=1.230616 MPa`、`m=0.358539 kg/s`、`Q=2.19668 m³/h`、`x_out=0.222327`；反算 `1e5(ρ/1000)Q²/Kv_eff²=Δp`（`test_refrigeration_devices.py:160-170`） | rel 1e-6 |
| TX-2 | L1 | 同 TX-1，`opening=0.2`；`opening=0`；反向压差 | 半开度 `m=0.179269 kg/s`（严格减半）；开度 0 与反向压差均为 0 | rel 1e-9 / 精确 |
| TX-3 | L2 | `Kv=0.6`、`opening=0.5`、NH3 308.15 K 饱和液、`Δp=1.2 MPa` | `ρ_l=587.586`、`m=0.221282 kg/s`、`x_out=0.208729` | rel 1e-6 |
| TX-4 | L3 | 倍思鹿 `TC` 扫描（3/5/8 K）+ 定 `m`，读 `M_PRE/CP/AV` | 标定 `CV` 物理尺度后把 `Δp(m,TC)` 拟合为等效 Kv 曲线；由 CI 全量 job 登记 | 待回填 |

**结论：可映射（Kv×开度、等焓闪发、单向）；需参数化（Kv 与 `CV` 换算）；过热度自调暂不可验收。**

## 4 汇总表

| 模块 | 执行域 | 映射完成度 | 验收算例数 | 阻塞项 | 下一步 |
| --- | --- | --- | --- | --- | --- |
| 压缩机 | `refrigeration`/`cold_store` | 高（设备级） | 4（L1×1、L2×2、L3×1） | 排量单位、效率等价、内置压力环、B 链无排气温度包络 | 做 C-4 标定；C-1/C-3 固化进 `tests/`；补排气温度检查 |
| 蒸发器 | `refrigeration`/`cold_store` | 中（UA 需反算） | 4（L1×1、L2×2、L3×1） | 无换热关联式、0.5 K 硬编码、`EN=0` 旁通无对应 | E-1/E-2 固化；E-4 反算 UA；旁通走 header |
| 蒸发式冷凝器 | `refrigeration` | 中（UA/湿球需反算） | 4（L2×3、L3×1） | 定压出口 vs 定排热、无湿球/风机、B 链无过冷 | EC-1–EC-3 固化；EC-4 标定 UA |
| 罐体卧式 | `refrigeration` | 中高（容器本体） | 4（L1×2、L2×1、L3×1） | 10 端口、`BKT_LEVEL` 口径、分层取液、`BKT_CORE` 黑盒 | V-1–V-3 固化；写 `BKT_LEVEL`→`level_ratio` 换算 |
| 罐体立式 | `refrigeration` | 中（液位口径要改） | 3（L1×2、L3×1） | `/(2R)` 口径、9 端口、静压分层 | V-5/V-6 固化；口径改正进参数化脚本 |
| 中间冷却器 | `refrigeration` | 中低（组合） | 4（L1×1、L2×2、L3×1） | 盘管自由度、液位分档、静压分层、两级中间压力 | IC-1/IC-2 固化；IC-4 交全量 job |
| 冷库库房 | `cold_store`/`refrigeration` | 低（仅温度层） | 4（L1×1、L2×2、L3×1） | 定容两相房间、15 端口、信号口、热流项缺失 | R-1–R-3 固化；房间模型明确为“换元”而非移植 |
| 热力膨胀阀 | `refrigeration` | 中（Kv 节流） | 4（L1×1、L2×2、L3×1） | 过热度自调、`CV` 尺度、出口定压 | TX-1–TX-3 固化；TX-4 标定 `CV` |
| **合计** | — | — | **31**（L1×9、L2×14、L3×8） | — | 23 条可本地/CI 执行，8 条 L3 待标定或全量 job |

## 5 与 NH3CO2ZL 案例的关系

- 本文是**设备级**映射：回答“一台设备落到哪个模型、哪个参数、哪条公式”。系统级验收（NH₃/CO₂ 两库房、五闭环、上层启停）由 `docs/NH3CO2ZL_CASE.md` 承担（另一代理撰写），本文**只引用、不重复**其工况、数值与诊断。
- 两份文档共用同一套可执行拓扑：`station_example()`（`examples.py:248-300`）与 `station_case()`（`examples.py:204-245`）。§3.4/§3.6 的 V-4、IC-2 落在 `HP1`/`LP1`/`HX1` 上，§3.7 的 R-1–R-3 落在冷库 A 链的 `ROOM1` 上。
- 边界划分：本文给“单器件能否验收 + 容差”，案例文档给“整站 2 h/24 h 能量账本与开环方向”。若冲突，**以本文器件级容差为准**，因为整站数字依赖初始液位与控制器整定。本文与 `BSL_MODULE_MAP.md:69` 的 C 类表、`:36-46` 的 8 行主表一致，不改写其人日与优先级。

## 6 风险与假设

1. **DLL 黑盒**：`BKT_CORE`、`LVL_LI`、`LVL_HI`、`PIPECV`、`PUMPCV` 只有声明；本文所有“倍思鹿语义”都停在可见的调用参数与分支，不推断内部关联式。
2. **不声称两相管网**：FluidNet 的两相只在饱和容器与设备函数内部（`devices.py:1-6`、`ALGORITHM.md:420-422`）；本文没有、也不应把倍思鹿的端口两相状态搬进支路。
3. **不以倍思鹿数值为 oracle**：所有期望值来自解析式、`PropsSI` 或 `workpoints.json`；L3 在回填前不得写成结论。
4. **版本与编码分叉**：中文根 `.cpp` 是 GBK、`_Run.cpp` 是 UTF-8；同一模块还有 `_D/_R` 与英文名变体，`压缩机` 一对差 14 行（`BSL_MODULE_MAP.md:10`）。本文行号以中文根 `.cpp` 与 `_Run.cpp` 为准，换版本必须重核。
5. **液位口径是最大的静默误差源**：卧式 `h/D` 与体积分数非线性（5% 高度对应 1.87% 体积），立式 `/(2R)` 与中间冷却器 `/H` 又不一致。照抄 `BKT_LEVEL` 不会报错，只会让质量与液位系统性偏移。
6. **物性差异**：本地 CoolProp 7.2.0、参考值 8.0.0、运行时可用 REFPROP 后端；同一 `p/h` 的 `T`、`cp` 不完全相同，L2 容差已留余量。
7. **默认效率偏低**：`η_is=0.72` 使 NH3 在 243.15 K/PR=11.3 时排气 480 K，超出 `condensing_unit` 的 393.15 K 包络；C-1 只用于设备函数对照，不代表可运行工况。
8. **验收边界**：31 条算例中 23 条可在本地/CI 直接执行，8 条为 L3；本文未运行全量 pytest、未运行任何 `.exe`，“通过”只能在 CI 执行后宣称。
9. **假设清单**：倍思鹿端口单位按 `MAPPING_A.md:72-79` 的 PJTDB 标签；`VOLUME` 为密度；`S_T` 为毫秒级模块步长；`FORCE_VOLUME` 按 L 解读仅用于说明 1.25 倍差，不是结论；`TC` 为蒸发器出口过热度。
