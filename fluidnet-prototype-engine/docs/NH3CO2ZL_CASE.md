# NH3CO2ZL 工程案例映射（M2-C 第二部分）

> 范围：把倍思鹿 `NH3CO2ZL` 工程（63 节点 / 222 模块）映射为 FluidNet 的
> `station_case`（NH₃/CO₂ 集总制冷站，`backend/fn_engine/refrigeration/examples.py`），
> 说明可迁移与不可迁移的内容，并给出一个不依赖原拓扑的“最小可运行替代方案”。
> 本文只读取倍思鹿资料包，不运行其可执行程序，也不修改资料包内文件。

## 1. 结论摘要

- **可以迁移**：对象类别与数量、设备几何/容积、稳态工况点（蒸发与冷凝压力/温度、
  质量流量、功率、COP）、控制目标值（库温、泵压）。这些量在 PJTDB 里有明确数值。
- **不能迁移**：连接拓扑。`.pjt` 与 `.Modu` 是加密二进制，PJTDB 只有 `NOD*`/`MOD*`/
  `PjtVarValue` 三类键且**没有任何字符串值**，没有端口、连接、相邻对象或模块归属字段。
  94 个“管道通用”和 54 个“截止阀”对象因此无法还原端点。
- **推荐路径**：不导入原拓扑，而是以 `station_case()` 为种子工程，用 PJTDB 提取的
  参数与额定点做**工况对齐**；`cold_store`（`room_example`）只适合单库房快速验证，
  无法表达 NH₃/CO₂ 复叠与泵供液。
- **两相边界**：倍思鹿把两相状态留在设备内部（`EX0_X` 干度数组），FluidNet 同样只在
  饱和容器内查询两相（`devices.py` 顶部注释），管网本身仍是单相。
- **数量对不上**：PJTDB 有 7 台压缩机、6 个房间开关、3 个库房对象，`station_case`
  只有 K1–K4、ROOM1–ROOM2，必须先定聚合规则再谈“对齐”。

## 2. 数据来源与可复现性

| 项 | 值 |
| --- | --- |
| 工程库 | `AlgProject/NH3CO2ZL/NH3CO2ZL_DB.PJTDB`（明文 JSON，1,094,573 字节） |
| 模块签名 | `AlgModule/<模块>/<模块>.cpp` 中 `void runing()` 之前的全局变量声明 |
| 提取脚本 | `scripts/extract_nh3co2zl_parameters.py`（argparse，默认自动定位资料包） |
| fixture | `tests/fixtures/nh3co2zl/parameters.json`（1,626,500 字节，UTF-8） |
| 复现 | `python scripts/extract_nh3co2zl_parameters.py` |
| SHA256 | `940276B0AB806930DFFE7683BDD35229B86E31E092B05F354D788725A6F11225` |

脚本不 `import extract_baselu_cases`，只复刻其解析思路（同一套 `runing()` 前全局变量
识别规则），因此两个提取器可以各自演进。连续运行两次输出字节完全一致；`module_guess`、
`summary`、`caveats` 的顺序都由键名或数字序号排序决定，不含时间戳与绝对路径。
`source` 字段是相对资料包根的 POSIX 路径，脚本默认路径由仓库相对位置推导并可用
`--source` / `FLUIDNET_BEISILU_SOURCE` 覆盖，不写死盘符。

## 3. PJTDB 事实画像

### 3.1 对象与模块匹配

`best_match` 用“MOD 变量键集合”与“模块根 .cpp 全局变量签名”的 Jaccard 主分 +
签名覆盖率次分排序，并列时按模块名取首个并把全部并列候选写入 `caveats`。

| module_guess | 对象数 | 示例对象 | 备注 |
| --- | ---: | --- | --- |
| 管道通用 | 94 | MOD0, MOD14, MOD15 | 29 键，精确匹配 |
| 截止阀 | 54 | MOD7, MOD17, MOD19 | 32/33 键，缺 `sdd`，score=0.9697 |
| 风机盘管 | 28 | MOD42, MOD43, MOD48 | 72 键，冷风机候选 |
| 压缩机 | 7 | MOD1–MOD6, MOD161 | 35 键，精确匹配 |
| 风机盘管控制 | 7 | MOD71, MOD300–MOD305 | 40 键，控制/温控器候选 |
| 止回阀 | 6 | MOD10, MOD11, MOD38 | 25 键 |
| 泵曲线法 | 6 | MOD8, MOD9, MOD32 | 30 键 |
| 毛细节流阀 | 5 | MOD67, MOD77, MOD196 | 31 键，节流类唯一命中 |
| 罐体卧式 | 5 | MOD46, MOD89, MOD90 | 91 键，容器 |
| 冷库库房 | 3 | MOD53, MOD145, MOD157 | 136 键 |
| 蒸发器 | 3 | MOD12, MOD13, MOD245 | 与“蒸发式冷凝器”签名相同；按温差看 MOD12/13 是冷凝器 |
| 管壳式换热器 | 2 | MOD210, MOD211 | 80 键 |
| 中间冷却器 | 1 | MOD52 | 93 键 |
| 容积型源头 | 1 | MOD82 | 67 键，边界源 |
| 蒸发式冷凝器 | 0 | — | 签名与“蒸发器”完全相同，无法区分 |
| 热力膨胀阀 | 0 | — | 签名含 `AV/CP/TC/EX0_CV`，本工程无对象 |
| 罐体立式 | 0 | — | 本工程只用卧式罐 |

合计 222 个对象；168 个对象的键集与模块签名精确相等（score=1.0），其余由
“截止阀缺键”和“蒸发器并列”两类情况构成。工程级 `PjtVarValue` 另有 44 个变量：

| 变量 | 值 | 用途解读 |
| --- | --- | --- |
| `HuanJingTemp` | 35 °C | 室外环境温度 |
| `ChangdiTemp` | 10 °C | 场地/土壤温度 |
| `YueTai` | 10 °C | 疑似湿球温度（待确认） |
| `RoomTemo1/2` | −17 °C | 库房温控设定 |
| `COP` | 4.3 | 工程级性能指标 |
| `PumpBar1–6` | 14（单位待确认） | 泵压/扬程指示 |
| `RoomOnOff1–6` | 1 | 6 个房间的启停状态 |

`NOD*` 对象只保存 `IM0..7_*`、`EX0..7_*`、`PRE/VW/HW/HMIN/TW` 等集总端口变量，
与 `MOD*` 之间没有引用字段，因此“哪个模块挂在哪个节点”也一并丢失。

各类对象的变量规模差别很大，这本身就是“能不能用键集合做匹配”的依据：

| 类别 | 键数 | 关键键（节选） | 读法 |
| --- | ---: | --- | --- |
| 管道通用 | 29 | `IM0_FLOW/PRE/TEMP`、`DN`、`RLS` | 单相管段水力/热力 |
| 截止阀 / 止回阀 | 33 / 25 | `CV`、`VSPACT`、`DN`、`FLOW_VOLUME` | 阀门开度与阻力 |
| 压缩机 | 35 | `POWER`、`ROTATE_SPEED`、`FORCE_VOLUME`、`FORCE_FLOW` | 强制流量压缩机 |
| 蒸发器 / 蒸发式冷凝器 | 30 | `EX0_PRE/TEMP/FLOW`、`PL`、`OUTTEMP` | 换热器（两相在内部） |
| 毛细节流阀 | 31 | `CV`、`Target_PRE`、`OutPutPRE`、`PL` | 节流 |
| 罐体卧式 | 91 | `BKT_V/H/LEVEL/PRE/TEMP/M`、`BKT_DL/DV` | 集总饱和容器 |
| 冷库库房 | 136 | `BKT_LL/LW/LH/V`、`RoomTemo` 相关键 | 库房热节点 |
| 风机盘管 | 72 | `H_in/H_out/H_metal`、`SH/SL/SW`、`PIPENB` | 冷风机（泵供液） |
| 风机盘管控制 | 40 | `MubiaoTemp`、`IM2_OnOff/Analog` | 温控器/控制阀 |
| 泵曲线法 | 30 | `CURVE_A/B`、`R`、`DPRE` | 泵曲线 |
| 管壳式换热器 | 80 | `BKT_*`、`H_in/H_out/H_metal` | 满液式换热器 |
| 中间冷却器 | 93 | `BKT_*`、`EX*`、`MIX1` | 中冷器（候选复叠） |

### 3.2 拓扑为什么不可恢复

1. `.pjt` 文件首字节为 `G8sjjUgsolggJg37QRty…`，不是 JSON；`AlgModule/*.Modu`
   同样以 `VFeLG8qh…` 开头，34 个模块文件全部是加密二进制。
2. PJTDB 顶层只有 `NOD0–62`、`MOD0–221`、`PjtVarValue`；递归扫描全库，
   **字符串值数量为 0**，即没有对象名、位号、管道编号、端口名或邻接关系。
3. `MOD` 的变量是组件内部状态（进出口集总量 + 计算量），没有 `IN/OUT` 端口索引，
   也没有 `MOD_x → MOD_y` 的字段。
4. 结论：可以回答“这个工程里有多少台压缩机、某台多大容积”，不能回答“哪台压缩机
   接到哪根排气管”。这正是本案例选择 `station_case` 种子工程而不是导入模型的原因。

### 3.3 两相只在设备内部

- 倍思鹿侧：`EX0_X`/`IM0_X` 是 8 分量的相分数数组，干度只出现在组件端口；
  `EX0_Q`/`IM0_Q` 里 `-998`/`998` 是“不适用/单相”哨兵值。
- FluidNet 侧：`devices.py` 规定“压力只存在于饱和容器”，`station.py` 明确
  管网不做两相流（`ALGORITHM.md` 把网络两相流列为范围外）。
- 交叉验证（本次核对过的 3 条事实之一）：`MOD46` 的 `BKT_PRE=1.0698 MPa` 对应
  NH₃ 饱和温度 27.118 °C，与 `BKT_TEMP=27.119 °C` 一致；`MOD195` 的
  `BKT_PRE=1.7218 MPa` 对应 CO₂ 饱和温度 −24.284 °C，与 `BKT_TEMP=−24.284 °C`
  一致；`MOD89` 的 `0.1212 MPa` 对应 NH₃ −29.72 °C，与 `IM0_TEMP=−29.69 °C` 一致。
  这说明**压力单位是 MPa(a)、温度单位是 °C**，且容器对象自带饱和态。
- 一个数据陷阱：CO₂ 三相点为 0.518 MPa，凡出现 0.101/0.285 MPa 的对象都只能按
  NH₃ 解读（0.285 MPa ↔ NH₃ −10.48 °C），不能当作 CO₂ 回路状态。

### 3.4 参数清洗规则（使用 fixture 前必读）

1. `EX0_Q/IM0_Q` 里的 `±998` 是“不适用/单相”哨兵值，不是干度；冷库库房与蒸发器
   对象都出现过，统计前必须剔除。
2. `0.101325 MPa` 是标准大气压填充值（未连接/未投运端口），不是 0.1 MPa 的量级巧合。
3. `S_T`、`RUN_S`、`EN`、`MODEL` 是启用/运行标志，语义未确认，不能当物理量参与计算。
4. 流量为 `1e-5`、`-1e-8`、`0` 的对象（如 MOD33、MOD200）应判为未投运，不参与聚合。
5. `MOD161.IM0_TEMP[0]=973.99 °C` 明显越界（该对象其余键仍匹配“压缩机”），整对象剔除。
6. 所有压力按 MPa(a) 解读、温度按 °C 解读；这一点已被 §3.3 的饱和态交叉验证支持。

## 4. 可迁移与不可迁移

| 内容 | 判断 | 理由 |
| --- | --- | --- |
| 设备类别、数量、对象键 | 可迁移 | `summary` 与 `objects[*].module_guess` |
| 容器容积、液位、饱和温度/压力 | 可迁移 | `BKT_V/BKT_LEVEL/BKT_PRE/BKT_TEMP`，已用 CoolProp 校验 |
| 库房尺寸（长×宽×高） | 可迁移 | `BKT_LL/BKT_LW/BKT_LH`，如 90×10×8 m |
| 稳态工况点（蒸发/冷凝压力、流量、功率） | 可迁移（需清洗） | 压缩机 `IM0_*`、`POWER`、`EX0_FLOW` |
| 控制目标值 | 可迁移 | `RoomTemo1/2`、`YueTai`、`PumpBar` |
| 连接拓扑、管径网络 | 不可迁移 | 加密文件 + 无连接字段 |
| 逐点变量快照作为验收基准 | 不可迁移 | 未验证收敛，存在哨兵值与异常值 |
| 两相管网求解 | 不可迁移 | FluidNet 管网只做单相 |
| PID 增益、启停时序、联锁逻辑 | 不可迁移 | PJTDB 只存目标值，无控制器参数 |
| 围护 UA、货物热参数、融霜策略 | 不可迁移 | PJTDB 未给出 |

## 5. 映射表：倍思鹿对象 → `station_case` 实例

`station_case()` 的实例集合是 K1–K4、EC1、EV1、HP1、LP1、CD1、HX1、PU1、
AC1/AC2、ROOM1/ROOM2 以及 5 个集管。下表给出建议映射；数值列中“反算”表示由
PJTDB 的质量流量/功率/温差推得，“假设”表示 PJTDB 无值、暂用种子工程默认值。

| 倍思鹿类别（对象数） | FluidNet 实例 | FluidNet 参数 | 取值 / 来源 |
| --- | --- | --- | --- |
| 压缩机（7，其中 6 台有效） | K1–K4（聚合） | `displacement_m3_s` | 0.092/0.097/0.091/0.092 m³/s（反算：`IM0_FLOW ÷ (ρ_sat × 0.8)`，ρ=1.05 kg/m³ @0.121 MPa） |
|  |  | `running` / `load_ratio` | 1 / 1.0（假设；`FORCE_VOLUME=3.11` 单位不明，见 §6.3） |
|  |  | `max_pressure_ratio` | 8.7（=1.05/0.121，PJTDB 压力比） |
|  |  | `isentropic/volumetric/motor_efficiency` | 0.72/0.8/0.92（种子默认，PJTDB 无值） |
| 蒸发式冷凝器（module_guess=0；MOD12/13 人工推断为冷凝器） | EC1 | `ua_w_k` | ≈43 kW/K（反算：712 kW ÷ (26.5−10) K；种子默认 40 kW/K） |
|  |  | `wet_bulb_temperature_k` | 283.15 K（`YueTai=10 °C`，湿球含义待确认） |
|  |  | `fan_ratio` / `return_gas_ratio` | 1.0 / 0.739（假设，沿用 B0 设计点） |
|  |  | `fan_power_w` | 7500 W（假设，种子默认） |
| 毛细节流阀（5）/ 截止阀（54） | EV1 | `kv_m3_h` | 待定：`CV=0.0145`（MOD77）定义不明，不可直接当 Kv；可用 0.270 kg/s 实测流量反算 |
|  |  | `opening_ratio` | 0.388（假设，沿用 B0 设计点） |
| 罐体卧式（5） | HP1 | `volume_m3` / `height_m` / `level_ratio` / `temperature_k` | 5.000 m³ / 0.487 m（语义待确认）/ 0.527 / 300.27 K（MOD46，27.12 °C，1.0698 MPa） |
|  | LP1 | 同上 | 5.629 m³ / 0.212 m / 0.650 / 243.46 K（MOD89，−29.69 °C，0.1212 MPa） |
|  | CD1 | 同上 | 14.137 m³ / 0.175 m / 0.321 / 248.87 K（MOD195，−24.28 °C，1.7218 MPa，CO₂） |
|  | HP1/LP1/CD1 | `min/max_level_ratio` | 0.05/0.95（假设；PJTDB 只存当前液位） |
| 冷库库房（3） | ROOM1 | `heat_capacity_j_k` / UA | 2.0e7 J/K；墙/顶/地 900/450/250 W/K（假设，PJTDB 无 UA） |
|  | ROOM1 | `temperature_k` / `setpoint_temperature_k` | 273.83 K（0.68 °C 初值）/ 248.15 K（−25 °C，MOD53 `BKT_TEMP[1]`） |
|  | ROOM2 | 同上 | 257.03 K（−16.12 °C）/ 257.26 K（−15.89 °C，MOD145，81,000 m³） |
|  | ROOM1/2 | `heat_input_w` | 15000 W（假设，B0 设计点） |
| 风机盘管（28） | AC1/AC2 | `ua_w_k` | 待定：PJTDB 无空气侧 UA；按 28 台分摊额定制冷量估算 |
|  |  | `fan_power_w` / `fan_ratio` | 4000 W（假设）/ 0.6（B0 设计点） |
|  |  | `max_outlet_quality` / `supply_valve_ratio` | 0.5 / 1.0（假设） |
| 风机盘管控制（7） | `PIDController` + `STATION_CONTROL` | 设定值 | 吸气 121 kPa、冷凝 1050 kPa、液位 0.527、库温 256.15 K（−17 °C，`RoomTemo`） |
|  |  | `kp/ki/sample_s` | 种子默认（−2e-5、−2e-5/300 等）/ 10 s；PJTDB 无增益 |
| 泵曲线法（6） | PU1 | `rated_mass_flow_kg_s` | 待定：`EX0_FLOW=2.465` 单位不明（m³/h 或 kg/s） |
|  |  | `rated_pressure_rise_pa` | 1.4 MPa（若 `PumpBar=14 bar` 成立；待确认） |
|  |  | `speed_ratio` / `efficiency_ratio` | 0.72（B0）/ 0.45（种子默认） |
| 管壳式换热器（2）/ 中间冷却器（1） | HX1（候选） | `ua_w_k` | 待定：可作复叠换热器，但两对象温差与流向需人工指认 |

聚合规则必须先定：7 台压缩机中 MOD1–MOD4（冷量 103–111 kW、功率 24.8–26.6 kW）映射
K1–K4，MOD5（2.2 kW 功率、27 kW 冷量）与 MOD6（19.7 kW，−10.5 °C 中温）目前没有对应
实例，建议要么并入 K1–K4 的 `load_ratio`，要么显式标注“未建模”；3 个库房对象只能映射
2 个 ROOM，28 台冷风机只能映射 2 台 AC，都是**降阶**而不是等价。

`cold_store` 备选：若只关心库温与冷量、不关心 NH₃/CO₂ 复叠，`room_example()` 的
`storage_room + unit_cooler + condensing_unit` 更简单，且自带货物/融霜/启停状态机；
但 `condensing_unit` 是单工质单级循环，无法表达本工程的 NH₃ 低温级 + CO₂ 泵供液
双回路，因此本案例主推 `station_case`。

### 5.1 代表性对象抽样（人工核对用）

| 对象 | 类别 | 关键变量与值 | 读法 |
| --- | --- | --- | --- |
| MOD1 | 压缩机 | `IM0_TEMP=-29.687 °C`、`IM0_PRE=0.1211 MPa`、`IM0_FLOW=0.0775 kg/s`、`POWER=25.264 kW`、`ROTATE_SPEED=100`、`FORCE_VOLUME=3.11` | 低温级单机，冷量约 105 kW |
| MOD12 | 蒸发器（并列，推断为冷凝器） | `IM0_TEMP=116.77 °C`、`EX0_TEMP=25.09 °C`、`EX0_PRE=1.0699 MPa`、`EX0_FLOW=0.2089 kg/s` | 过热排气→过冷液，符合冷凝器 |
| MOD77 | 毛细节流阀 | `IM0_PRE=1.0674 MPa` → `EX0_PRE=0.1229 MPa`、`IM0_FLOW=0.2697 kg/s`、`EX0_Q=0.0648`、`CV=0.0145` | NH₃ 节流，压差约 0.94 MPa |
| MOD46 | 罐体卧式 | `BKT_V=5.000 m³`、`BKT_LEVEL=0.527`、`BKT_PRE=1.0698 MPa`、`BKT_TEMP=27.12 °C` | 高压贮液器 |
| MOD53 | 冷库库房 | `BKT_LL/LW/LH=90/10/8 m`、`BKT_V=7200 m³`、`BKT_TEMP=0.68 °C`、目标 −25 °C | 大库降温工况 |
| MOD71 | 风机盘管控制 | `MubiaoTemp=-10 °C`、`IM0_Analog=26.32`、`EX0_OnOff=1` | 温控器目标值 |
| MOD42 | 风机盘管 | `H_in=2708.6`、`H_out=16000`、`PIPENB=16`、`SH/SL=0.4/0.6` | 焓与管数，空气侧 UA 未直接给出 |

**冷凝器归属的推断**：MOD12/MOD13 是 116.77 °C 过热气体进、25.09 °C 过冷液出
（1.0699 MPa 下 NH₃ 饱和温度 27.12 °C），只能是冷凝器，极可能对应“蒸发式冷凝器”
模块；MOD245 是 −33.3 °C、接近零流量，符合低温蒸发器。因此“蒸发式冷凝器”在
`module_guess` 计数里是 0，但人工可判定的冷凝器对象是 2 台（MOD12/MOD13），
映射到 EC1 时应按 2 台合并 UA 处理。这一判断需要倍思鹿侧确认，不能由脚本自动完成。

## 6. 最小可运行替代方案

### 6.1 原则

不导入原拓扑，不做“数值等价”声明；用 `station_case()` 自带的合法拓扑承载
PJTDB 的参数与工况点，把差异限定在“参数与边界”这一层。

### 6.2 步骤

1. 生成 fixture：`python scripts/extract_nh3co2zl_parameters.py`；
   确认 222 个对象、`summary` 计数与 §3.1 一致。
2. 取种子：`station_case()`（`examples.py`），保留五闭环 + 上层启停脚本，
   不删设备、不改端口，避免触发 `compile_station` 的拓扑校验。
3. 覆盖实例参数：按 §5 表写入 K1–K4、EC1、EV1、HP1、LP1、CD1、HX1、PU1、
   AC1/AC2、ROOM1/ROOM2；数值先按“反算值优先、假设值兜底”的顺序落地。
4. 工况对齐：`controller.suction.setpoint=121000 Pa`、
   `controller.head.setpoint=1050000 Pa`、库温设定 256.15 K、湿球 283.15 K。
5. 初始状态：HP1 5.0 m³/0.527/300.27 K、LP1 5.63 m³/0.65/243.46 K、
   CD1 14.14 m³/0.321/248.87 K；若触发 `VESSEL_INITIAL_STATE` 或
   `VESSEL_PHASE_RANGE`，先把液位收到 (0.05, 0.95) 内再重试。
6. 运行 B-S01（额定负荷 24 h）先做 6 h 快速判断，再跑满 24 h；记录
   `frames[-1].variables` 与 `metrics`（含 `mass_residual_kg_circuit0`、
   `energy_residual_j`、`electric_power_w`）。
7. 按 §6.4 验收；不通过时优先改 `load_ratio`、`ua_w_k`、`heat_input_w` 这三个
   最不确定的参数，不动拓扑。
8. 把本轮实际覆盖值与差异写回交付记录，作为下一次迭代的基线。

### 6.3 需要人工确认的参数

1. `FORCE_VOLUME=3.11` 的单位：按 0.0775 kg/s 与 ρ=1.05 kg/m³ 反算排量约 332 m³/h，
   若把 3.11 读成 m³/h 则相差约 100 倍，读成 m³/min 才只差约 1.8 倍；单位必须确认。
2. `ROTATE_SPEED=100/50` 是 Hz、r/min 还是百分比。
3. `POWER` 是轴功还是电功率（直接影响 COP 分母；`PjtVarValue.COP=4.3` 更接近
   电功率口径）。
4. `CV` 是 Kv 还是 Cv；毛细节流阀 `CV=0.000167`（MOD67）到 `CV=0.0145`（MOD77）
   与截止阀 `CV=2.595` 量级相差多个数量级。
5. `BKT_H` 的语义：5 m³ 卧式罐的 `BKT_H=0.487` 不可能是罐高，可能是液位高度或
   直径；`height_m` 必须按几何重算。
6. 库房 `BKT_LL/LW/LH` 的单位（m 还是 mm）与围护 UA（PJTDB 无）。
7. `YueTai=10 °C` 是否就是湿球温度；`ChangdiTemp=10 °C` 是场地还是地温。
8. `PumpBar1–6=14` 的单位（bar? m?）与对应泵的额定流量。
9. MOD12/MOD13/MOD245 的模型归属：本文按 116.77→25.09 °C 判 MOD12/13 为冷凝器、
   按 −33.3 °C 判 MOD245 为蒸发器，但签名并列，需倍思鹿侧确认。
10. 28 台风机盘管中哪些在运行、对应哪个库房（PJTDB 无归属）。

### 6.4 验收指标与容差

参考值来自 PJTDB 快照与饱和态反算，**不是厂家性能保证**；容差是本阶段工程判断，
必须在拿到实测/铭牌数据后重新协商。

| 指标 | 参考值 | 验收目标 | 容差 |
| --- | --- | --- | --- |
| 吸气压力 | 0.121 MPa（MOD1） | 与参考一致 | ±10 kPa |
| 冷凝压力 | 1.05–1.07 MPa（MOD12/MOD46） | 与参考一致 | ±50 kPa |
| 总制冷量 | 5.88e5 W（6 台压缩机吸气量 × 潜热上限估算）；仅 4 台低温机为 4.25e5 W | 落在 4.25e5–5.88e5 W | ±15% |
| 压缩机电功率 | 1.238e5 W（`POWER` 求和） | 与参考一致 | ±15% |
| COP | 4.3（`PjtVarValue`）/ 4.75（上限估算） | 4.3–4.8 | ±10% |
| 库温（−17 °C 库） | 256.15 K | 稳态偏差 | ±0.5 K |
| 库温（−25 °C 库） | 248.15 K | 稳态偏差 | ±0.5 K |
| 质量/能量守恒 | — | 引擎不变量 | `mass_residual_kg_circuit0` / `energy_residual_j` < 1e-8 |

注意：库温“降温时间”、融霜周期、启停次数没有 PJTDB 参考值，不列入本轮验收；
制冷量与功耗的容差按“集总模型 vs 逐点模型”的经验差距取 ±15%，不得对外表述为
“与倍思鹿数值等价”。

## 7. 阻塞项与下一步

| 阻塞项 | 影响 | 解除方式 |
| --- | --- | --- |
| 拓扑不可恢复（加密 + 无连接字段） | 无法自动生成 `connections`，只能人工搭种子拓扑 | 倍思鹿侧导出节点-模块连接表（CSV/XML）或提供未加密模型；否则永久按“降阶替代方案”交付 |
| 单位/量纲未确认 | `FORCE_VOLUME/CV/BKT_H/POWER/PumpBar` 五个口径都可能错 | 建立“变量-单位-来源-校验方式”清单，逐项用 CoolProp 或铭牌核对 |
| 两相边界 | CO₂ 侧出现低于三相点（0.518 MPa）的 0.101/0.285 MPa 值 | 先判定工质回路，再决定这些对象是否作废 |
| 对象数量不匹配 | 7 压机 / 3 库房 / 6 房间开关 vs 4 / 2 / 2 | 明确聚合与“未建模”标注规则，写进交付记录 |
| 快照未收敛 | 不能当验收基准；MOD161 出现 `IM0_TEMP=973.99 °C` | 只用类别、量级与工况点，不逐点复现；异常对象单列 |
| 控制器参数缺失 | PID 只能重新整定 | 用 B-S01 稳态反推 `kp/ki`，并记录整定过程 |

下一步（按优先级）：

1. 向倍思鹿侧索取拓扑导出（哪怕只是“模块-模块”邻接表），这是唯一能消除
   §3.2 阻塞的输入。
2. 完成单位核对表：对每个数值变量标注单位、来源、校验方式；优先 `FORCE_VOLUME`、
   `CV`、`BKT_H`、`POWER`。
3. 用饱和态一致性做自动筛查：对每个 `MOD` 检查 `BKT_PRE ↔ BKT_TEMP`、
   `IM0_PRE ↔ IM0_TEMP` 是否满足 CoolProp 饱和关系，把 `998/-998` 哨兵值与
   越界对象（如 MOD161）列入清洗名单。
4. 在 fixture 之上加一层“参数映射”（对象类别 → FluidNet 参数名），本次不实现，
   避免把映射规则硬编码进提取器。
5. 跑通 §6 的最小替代方案并归档 B-S01 结果，形成 M2-C 的验收记录。
6. 两相边界写进 `DATA_CONTRACT`/`ALGORITHM`（本文不改这两份文档，避免与并行任务冲突）。

### 7.1 误用提示

- 不要把 222 个对象直接当成 222 台 FluidNet 设备：94 根管道、54 个截止阀在
  `station_case` 里没有对应实例（管网被集总为集管与容器）。
- 不要把 `summary` 里的 0 读成“工程里没有冷凝器/膨胀阀”：冷凝器藏在并列组
  （MOD12/13），膨胀阀职责由毛细节流阀承担。
- 不要把 fixture 的变量值逐点对比当作回归基准：它是保存槽位快照，未验证收敛。
- 不要因为 `station_case` 能跑通就宣称复现了倍思鹿结果：拓扑、聚合层级与两相
  边界都不同，本方案只做工况对齐与量级对照。

## 附录 A：fixture 结构

```json
{
  "project": "NH3CO2ZL",
  "source": "AlgProject/NH3CO2ZL/NH3CO2ZL_DB.PJTDB",
  "objects": [{"key": "MOD1", "module_guess": "压缩机", "score": 1.0, "variables": {}}],
  "summary": {"压缩机": 7, "蒸发式冷凝器": 0, "...": 0},
  "topology_available": false,
  "provenance": "PJTDB 保存槽位快照；未运行倍思鹿；...",
  "caveats": ["同签名候选...", "以下对象存在明显越界..."]
}
```

`objects` 按 MOD 数字序号排序；`variables` 的键按字典序；`AryDoubleN/AryIntN`
包装已展开为列表。`summary` 显式包含 0 计数的必需类别（蒸发式冷凝器、热力膨胀阀、
罐体立式），便于文档直接引用而不触发 `KeyError`。

## 附录 B：校验命令

```powershell
python scripts/extract_nh3co2zl_parameters.py
python -c "import json; d=json.load(open('tests/fixtures/nh3co2zl/parameters.json', encoding='utf-8')); print(len(d['objects']), d['summary'])"
ruff check scripts/extract_nh3co2zl_parameters.py
```

校验结果：`json.load` 通过（222 个对象、17 个 summary 键、计数合计 222）；
`ruff check` 全绿；连续两次运行 fixture 的 SHA256 相同。
