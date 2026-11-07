# 用独立设备模块搭建冷库

日期：2026-11-04。本轮提供可以从空白画布逐个放置、填写参数并连接的模块基线，复用已有制冷站设备算法。组网由设备合同与实际端口连接决定，不要求 `station_case`、固定实例 ID、固定库房数量或其上层控制脚本。

首个基线是 **R134a 单工质泵供液冷库**：一台压缩机、一个冷凝器、高低压两个容器、节流阀、液泵、冷风机和库房，共八个独立设备。它用于验证模块能组装、能计算、能保存以及结果遵守守恒；不是厂家选型实例，也不是 NH₃/CO₂ 复叠案例的完整替代品。

## 可复用模块

| 模块 ID | 作用与主要端口 | 本轮范围 |
| --- | --- | --- |
| `refrigerant_compressor` | `suction` 吸气 → `discharge` 排气；排量、载量决定质量流量 | 连接两压力等级，吸气为低压容器饱和气 |
| `evaporative_condenser` | `in0` → `out0`；按湿球温差和有效 UA 排热 | 同一高压等级，不计算喷淋水及空气网络 |
| `hp_receiver` | `in0/in1` 进流，`liquid/vapor` 相别出口 | M/U 动态存量决定饱和压力与液位 |
| `lp_drum` | `in0/in1` 供液与湿回气，`vapor` 去压缩机，`liquid` 去泵 | 同上；非固定压力边界 |
| `expansion_valve` | `in0` 高压液 → `out0` 低压闪发流 | 等焓节流，Kv 和开度，单向流动 |
| `refrigerant_pump` | `in0` 饱和液 → `out0` 供液 | 质量流量随转速变化；泵功进入制冷剂 |
| `air_cooler` | `in0` 供液 → `out0` 湿回气，`heat` 连接库房 | UA 换热受供液量与最大出口干度限制，扣除风机热后给出库房净冷量 |
| `cold_room` | `heat` 接收一个冷风机的净冷量 | 等效热容、围护传热、附加负荷，计算平均库温 |
| `refrigerant_header` | 四个 `in0…in3`、四个 `out0…out3` | 同一压力等级内分汇流，用于并联压缩机与多库支路 |
| `cascade_exchanger` | `evap_in/evap_out` 接 NH₃ 低压侧，`cond_in/cond_out` 接 CO₂ 侧 | 两回路只交换热量，按饱和温差与 UA 求热量 |
| `pumped_drum` | `in0/in1` 回流，`vapor` 去复叠冷凝侧，`liquid` 去液泵 | CO₂ 饱和储量；不能与 NH₃ 共用流体端口 |

这些模块可重复放置和改名。连接端口决定归属，模块名称、画布位置和设备列表顺序不影响物理关系。跨压力等级必须经压缩机或节流阀；每个压力等级只容纳一个饱和容器；同一供液集管上的冷风机按各自供液阀开度分流，当前不是逐支路水力压降平衡模型。

本轮保留**一个冷风机对应一个库房**的热端口合同。不支持一个库房同时接多台冷风机；也不允许冷风机热端口连另一冷风机或库房连库房。非法连接给编译诊断，不继续到计算阶段产生未归属设备或 `KeyError`。通过修改端口必连标志也不能绕过这一配对规则。

## 从空白组装八个设备

选择单回路 R134a。按下表逐个插入模块；参数输入以目录的显示单位为准，例如 248.15 K 在界面填 −25°C、载量 0.75 填 75%。完整规范值及显示换算依据模块合同，不把规范 JSON 的 K、m³/s 直接当成界面 °C、m³/h。

组装清单：`examples/refrigeration-modular/single-room.recipe.json`。它只包含工质、设备实例、规范参数、位置与连接，不包含模块定义快照或隐藏求解状态。对应 `single-room.project.json` 是方便导入的完整规范项目，导入本身不作为“从空白组装”的证明。

| 实例 | 模块 | 教学设计输入 |
| --- | --- | --- |
| `Low` | `lp_drum` | 0.6 m³，−25°C，初始液位 40% |
| `High` | `hp_receiver` | 0.3 m³，35°C，初始液位 50% |
| `Compressor` | `refrigerant_compressor` | 载量 75%，排量按当前设计热负荷反算，详见 recipe |
| `Condenser` | `evaporative_condenser` | 湿球 20°C，风机/喷淋功率 300 W，有效 UA 按设计排热反算 |
| `Valve` | `expansion_valve` | 开度 50%，Kv 按高低压差和压缩机设计流量反算 |
| `Pump` | `refrigerant_pump` | 额定流量 0.12 kg/s，压升 80 kPa，转速 100% |
| `Cooler` | `air_cooler` | 满风 UA 约 771.429 W/K，风机 400 W |
| `Room` | `cold_room` | −18°C，热容 2 MJ/K，围护负荷 2780 W + 附加负荷 2220 W |

九条连接：

1. `Low.vapor → Compressor.suction`
2. `Compressor.discharge → Condenser.in0`
3. `Condenser.out0 → High.in0`
4. `High.liquid → Valve.in0`
5. `Valve.out0 → Low.in0`
6. `Low.liquid → Pump.in0`
7. `Pump.out0 → Cooler.in0`
8. `Cooler.out0 → Low.in1`
9. `Cooler.heat → Room.heat`

首次选择动态计算，时长 600 s，输出间隔 60 s，内部步长 10 s。此组初值按设计点平衡，库温保持约 −18°C；这不是恒温控制器的效果。提高 `Room.heat_input_w` 后库温会变化，压力与能量响应由容器和热容计算。要做恒温、压力调节或多机启停，应另外添加公开 PID／项目控制，不能把设备模块默认行为当成已配置控制。

## 复制扩展

`two-room.recipe.json` / `two-room.project.json` 给出两库房、两台压缩机的 15 设备、18 连接变体。复制冷风机时也复制其库房，并通过 `Supply`、`Return` 集管连接供回液；复制压缩机通过 `Suction`、`Discharge` 集管连接高低压侧。每库负荷仍为 5 kW，示例据总负荷调整泵流量、容器容积、冷凝 UA、阀 Kv 和压缩机总排量。

Python 工厂 `fn_engine.refrigeration.modular_examples.modular_room_example(room_count, compressor_count)` 支持 1–4 库、1–4 台压缩机，分别对应单组四进四出集管容量。这是示例工厂的布局范围，不是编译器新增的全局设备数量限制。生成的项目全部是普通模块实例与连接，修改或重命名不需再次调用工厂。

HTTP 示例入口：`GET /api/v1/examples/refrigeration-modular-room`、`GET /api/v1/examples/refrigeration-modular-two-room`。运行继续使用现有 `/api/v1/runs`；设备输出及端口键按实际实例 ID 生成，报告读取已接受帧与固定项目快照。

## 扩展到 NH₃/CO₂ 复叠

`cascade.recipe.json` / `cascade.project.json` 在同一单库骨架上增加两个独立模块：`Secondary`（`pumped_drum`，CO₂ 储液器）和 `Cascade`（`cascade_exchanger`，复叠换热器）。共 10 设备、13 连接，没有调用 `station_case()` 或附加固定案例控制。

高低压氨侧使用原来的压缩机、冷凝器、贮液器与节流阀。原有液泵／冷风机改接 CO₂ 储液器：`Secondary.liquid → Pump.in0`，`Cooler.out0 → Secondary.in0`。新增四条连接：

1. `Low.liquid → Cascade.evap_in`
2. `Cascade.evap_out → Low.in1`
3. `Secondary.vapor → Cascade.cond_in`
4. `Cascade.cond_out → Secondary.in1`

工质分别绑定 `Low.in0`（Ammonia）与 `Secondary.in0`（CarbonDioxide），recipe 的 `circuit_fluids` 保留这两个锚点。两个回路不互换质量，CO₂ 液泵吸热和库房负荷由复叠换热器传到 NH₃ 低压容器，再由压缩机／冷凝器排出。

设计初值：NH₃ 蒸发 −30°C、冷凝 25°C，CO₂ 饱和温度 −25°C，库房 −18°C、净负荷 5 kW，环境湿球 20°C。低压／高压／CO₂ 容积分别 0.6／0.3／0.6 m³。压缩机排量、阀 Kv、复叠 UA 与冷凝 UA 根据这些输入和独立回路热平衡反算。600 s 基线保持约 119.376 kPa 吸气、1.00269 MPa 冷凝及 1.68274 MPa CO₂ 压力，复叠传热约 5.42024 kW，压缩机电功率约 2.33797 kW；这是教学设计点，不是倍思鹿原工程的参数复现，也不代表真实机组选型性能。

Python 入口 `modular_cascade_example()`，HTTP 入口 `GET /api/v1/examples/refrigeration-modular-cascade`。复制／改名时同步连接端点和工质锚点即可，不要求上述示例 ID。当前例子不含双级、融霜、制冷剂管网压降或固定五闭环控制；这些未实现部分不会由添加一个复叠模块自动获得。

## 物理与验收边界

该回路使用集总 `refrigeration` 执行域，已有两个 `(M,U)` 容器和库房热容。不依赖暖通风水域尚未实现的水侧储热。本轮没有增加管网两相压降、直接膨胀蒸发器及过热度调阀、冷凝器持液、双级压缩、融霜或厂家性能图；液位始终须在饱和容器适用范围内。

设计计算由模块基础关系反算：压缩机净制冷效应覆盖冷风机制冷剂吸热与泵功，冷凝器排出制冷量和压缩轴功；电机损失排向机房。设计输入保留 10 位有效数字以减少平台之间的生成差异。源码与 JSON 在定向测试中校验一致。

验证包括从 recipe 和目录重新构建、单／双库、单／双压缩机独立组合、任意实例 ID 与重排连接、整套复制为两个独立回路、负荷扰动、质量与独立能量账本、非法热端口诊断，以及 API 运行和冻结报告。前端从空白真实放置／连线验证由本轮前端记录另行登记。只运行相关定向检查，不运行全量回归。

2026-11-04 定向结果：`python -m pytest -q tests/test_refrigeration_modular.py tests/test_refrigeration_station.py -k 'modular or topology_rules or example_compiles or fluid_and_initial_state_rules' --tb=short` 得到 **25 passed，18 deselected，4.65 秒**。包含新增 10 条模块组装测试以及旧制冷站拓扑／初态诊断兼容检查。相关文件 ruff 通过，mypy 94 个源码文件无错误。600 s 单库／双库基线的总质量残差均为 0，累计能量残差分别约 0.000252 J／0.00410 J，库温保持 255.15 K。

NH₃/CO₂ 增量复验：`python -m pytest -q tests/test_refrigeration_modular.py --tb=short` 得到 **13 passed，4.89 秒**；包含从目录和 recipe 组装复叠、任意实例 ID／顺序、两个回路质量守恒、复叠两侧能量平衡及新 API 入口。600 s 氨／CO₂ 质量残差分别为 0／0，累计能量残差约 0.000406 J，库温 255.15 K。相关文件 ruff 和 mypy 再次通过，没有扩大全量回归。

## 2026-11-05 设备模型扩展

新增卧式圆筒贮液器 `horizontal_receiver`、卧式圆筒低压循环桶 `horizontal_drum` 与风冷冷凝器 `air_cooled_condenser`。这三个模块可替换组装回路内对应设备，保持其制冷剂端口连接；其参数和模型与旧设备独立注册。

卧式容器输入内径与直筒长度，体积分数不等于高度比例；风冷冷凝器使用环境干球温度和有限空气热容量流率，不把蒸发式冷凝器的湿球UA直接当成风冷UA。具体模型见[卧式容器](HORIZONTAL_VESSELS.md)、[风冷冷凝器](AIR_COOLED_CONDENSER.md)。组装清单与规范项目：`examples/refrigeration-modular/air-cooled.recipe.json`、`air-cooled.project.json`，API `GET /api/v1/examples/refrigeration-modular-air-cooled`。

本轮没有新增控制模板，未扩展DX过热度调节、中冷器或融霜；默认旧设备合同与已存项目保持原语义。扩展记录见 [REFRIGERATION_EQUIPMENT_EXPANSION.md](REFRIGERATION_EQUIPMENT_EXPANSION.md)。

后续制冷与暖通设备的缺口、批次和项目交付标准已集中到[设备模型路线](REFRIGERATION_HVAC_EQUIPMENT_ROADMAP.md)，以模型可复用和从空白组装验收为准。
