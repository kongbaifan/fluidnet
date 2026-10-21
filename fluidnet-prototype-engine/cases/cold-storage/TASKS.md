# 冷库案例任务与进度

开始日期：2026-10-19。当前阶段：**A 版（A0–A6）与 B 版（B0–B3）均已完成（2026-10-21）**；后续为工程校核（C，需厂家/现场数据）。

## A0：参数、工况、独立基准与接口

| 任务 | 状态 | 交付与证据 |
| --- | --- | --- |
| A0-01 建立案例目录和集中计划 | 已完成 | [README.md](README.md)、[PLAN.md](PLAN.md)，原文档路径保留导航入口 |
| A0-02 固定单库房 v1 参数和来源 | 已完成（示范假设） | [parameters.json](single-room-minus18/parameters.json)、[sources.json](single-room-minus18/sources.json)，全部使用规范单位 |
| A0-03 固定七组工况及事件时间表 | 已完成（输入） | [scenarios.json](single-room-minus18/scenarios.json)，日程/事件校验通过，产品执行待 A3/A4 |
| A0-04 独立制冷循环参考 | 已完成 | [verify_reference.py](tools/verify_reference.py)直接按热力方程查询 CoolProp；四工作点、30 项物理检查通过 |
| A0-05 固定派生设计量 | 已完成（假设下） | [workpoints.json](single-room-minus18/references/workpoints.json)：排量和冷凝器 UA 由额定点一次反算，其他工作点保持排量 |
| A0-06 热连接、模型与会话合同 | 已完成（A1 落地） | [refrigeration/compile.py](../../backend/fn_engine/refrigeration/compile.py) 定义 thermal 域、两设备端口/参数/变量、热连接校验与诊断；[refrigeration/session.py](../../backend/fn_engine/refrigeration/session.py) 与 [sessions.py](../../backend/fn_engine/sessions.py) 定义会话协议与会话工厂；既有流体项目编译路径不变 |
| A0-07 验证/发布及归一化入口设计 | 已完成（A1 落地） | [bridge.py](../../backend/fn_engine/bridge.py) 的 `PARAMETER_BINDINGS`、`THERMAL_SCOPE` 与热项目步长上限；`GET /api/v1/examples/cold-storage`；health `cold_room_ideal_source`；前端按 thermal 端口注入模块；保存、重启读取和浏览器验收见 A1 |

## A1：最小产品链路（2026-10-20 完成）

目标：库房热节点 + 理想恒容量冷源贯通真实页面、会话、曲线、保存和重启读取；理想冷源明确标注并仅作中间开发基准。

| 任务 | 状态 | 交付与证据 |
| --- | --- | --- |
| 后端热执行域 | 已完成 | `Domain.thermal`；`cold_room`（等效热容、围护漏热、附加热负荷）与 `ideal_cold_source`（指定容量，不算循环/压缩功/COP，帧诊断 `COLD_ROOM_IDEAL_SOURCE`）；`compile_project` 按端口域选择热编译分支 |
| 状态与会话 | 已完成 | `ThermalSession` 继承公共会话的参数/控制/命令协议，库房温度隐式 Euler，能量账本 `state.external_energy_j` / `state.cooling_energy_j` / `metrics.energy_residual_*`；`sessions.create_session` 供同步运行、后台运行和控制预览共用 |
| 公共接口 | 已完成 | `/runs`、`/runs/{id}/command`、`/runs/{id}/history`、归档、备份与重启恢复对热项目沿用同一响应模型；health 增加 `supported_domains` 的 `thermal` 与 `capabilities.cold_room_ideal_source`；契约文件 49 个与源码一致 |
| 前端案例 | 已完成 | [cold-storage.js](../../frontend/cold-storage.js)：项目页一键创建案例、库房指标（库温/冷却功率/累计冷量）、三条曲线绑定；画布显示传热系统与热端口；设备窗口可改参数并应用 |
| 自动化验收 | 已完成 | [test_refrigeration_a1.py](../../tests/test_refrigeration_a1.py) 16 项（解析解、步长一阶收敛、能量账本、契约拒绝、控制方向、原子写入、失败回滚、保存/重启复算、24 h 有界历史、API 控制）；[browser-cold-storage.mjs](../../tests/browser-cold-storage.mjs) 覆盖创建→运行→指标/曲线→改参数重算→保存→服务重启读取与同帧复算 |

## 2026-10-19 实测

CoolProp 8.0.0、Python 3.11.0。详细数值、全部检查及输入/脚本哈希见 [A0 验证报告](single-room-minus18/references/VALIDATION.md)。

- 七组日程输入通过校验，事件 ID、时间、类型、冻结物温度和融霜时长均已核对。
- 四个独立循环工作点的热力检查通过，围护漏热为 2864 W。
- 额定假设点：制冷量 10.0000 kW，压缩机电功率 6.6355 kW，机组 COP 1.5070；数值不含两台风机的 0.50 kW 电功率。
- 额定反算排量 46.9261 m³/h，冷凝器设计 UA 1996.4919 W/K；高冷凝、较低蒸发和半容量点保持相同排量。
- 参考核对 `--check` 与 ruff 通过；验证结果是 A0 独立工作点，不计为 A2 产品模型或 A6 完整案例验收。
- 另通过 5 项异常/保护验证：拒绝效率大于 1、超出运行日程的事件、未冻结入库货物、包络外循环点，以及覆盖已有参考目录；覆盖拒绝后原证据内容未变。
- 已核对案例及导航文档的本地链接、代码围栏和 Git 空白检查。

## 2026-10-20 实测

Python 3.11.0、CoolProp 8.0.0、Node 24 + Edge。A1 验收证据：

- `python cases/cold-storage/tools/verify_reference.py --check` 复跑通过：30 项检查、7 组工况、围护漏热 2864 W。
- `python -m pytest -q`：**390 passed**（含 A1 专项 16 项，基线 374 项全部保持通过）；`--cov=fn_engine` 总覆盖率 **88.7%**（门禁 85%）。
- `python -m ruff check backend frontend tests cases`、`python scripts/generate_contracts.py --check`（49 个契约文件）与 `npm run check` 通过。
- 页面链路实测：项目页创建案例 → 运行 2 h 仿真时间完成 241 帧 → 库温 −18.000 °C、冷却功率 2.864 kW、累计冷量 8.305 kWh；同屏曲线显示库温；把附加热负荷改为 1 kW 并应用后重算，库温仍为 −18.000 °C、冷却功率升至 3.864 kW；保存工作区后硬停服务、全新浏览器上下文读取案例，重启后归档帧与再次复算帧逐变量一致。
- 24 h fast 运行、七组工况、货物热状态、真实循环、能耗与控制日程尚未在 A1 实现，按阶段表在 A2–A4 验收。

## 已知边界（A1）

- 只支持“库房热节点 + 理想恒容量冷源”的一对一热连接；不含货物热节点、冷风机、制冷循环、电功率/COP 与融霜。
- 冷源容量比例由 PID 或运行命令调整，理想冷源输出不保证与实际蒸发温度/冷凝能力匹配；数值只用于开发基准。
- 热项目使用独立执行域，暂不支持与流体网络混合求解；同一项目内仍走原有单域执行路径。
- 画布沿用通用设备图元，热设备的专用符号与预设视图在 A5 完善。

## 2026-10-20 B 版准备

- 完成倍思鹿公开案例的集中拆解：[BASELU_CASE.md](nh3-co2/BASELU_CASE.md)（拓扑、设备清单、五闭环+上层控制、作者声明的简化、证据分级与 B0 数据缺口）。
- 完成 B 版执行计划初稿（B0–B6、61–89 人日），随后按截图冻结完整设备清单（中值 78 人日），提交 `57373cb`、`3dc1674`。
- 用户复核原文深度后收缩 B 范围（2026-10-20）：原文物理只到“强制流量、非定压罐体”层次，主体是五闭环 + 上层启停，结果只有“输入两个压力目标即可长时间稳定自运行”一句；初稿的两相网络还与 ALGORITHM“管网两相不做”冲突。现改为集总制冷站（4 台单级压缩机、3 个 `(M,U)` 容器、2 库房，共 8 个状态）+ 五闭环/上层控制，去掉双级、乙二醇、融霜、16 页画布；B0–B3 共 20–31 人日。依据见[案例拆解第 11 节](nh3-co2/BASELU_CASE.md#11-b-范围2026-10-20按原文深度收缩)与 [B 版执行计划](nh3-co2/EXECUTION_PLAN.md)。
- 证据边界：未取得倍思鹿项目文件、参数、初态、控制源码或运行结果；只做架构/工作流对照，不做数值对测；公开截图读数不作为设计点。
- B0 尚未开始；硬依赖只有 A1（已完成）与 A2 的压缩机/物性查询方式，开工时间按阶段顺序。

## 2026-10-20 B1 设备层（用户要求先做设备）

用户要求“先按照计划做出设备来，毕竟是通过设备搭建系统的”，B1 先于 A2 开始，只做设备层。

| 任务 | 状态 | 交付与证据 |
| --- | --- | --- |
| 制冷站端口域与设备目录 | 已完成 | `Domain.refrigerant`；`refrigeration_catalog()` 10 台内置设备（高压贮液器、低压循环桶、泵供液储液器、压缩机、蒸发式冷凝器、电磁节流阀、复叠换热器、液泵、冷风机、集管），合同见 [DATA_CONTRACT](../../docs/DATA_CONTRACT.md#冷库-b-制冷站设备2026-10-20设备层) |
| 设备物理 | 已完成 | [refrigeration/devices.py](../../backend/fn_engine/refrigeration/devices.py)：容器 `(M,U,V)` 经新增 `state_du` 反求压力/液位，压缩机、冷凝器、节流阀、复叠、液泵、冷风机为代数关系；方程见 [ALGORITHM](../../docs/ALGORITHM.md#冷库-b-集总制冷站设备2026-10-20设备层) |
| 逐台独立核对 | 已完成 | [test_refrigeration_devices.py](../../tests/test_refrigeration_devices.py) 29 项，全部对照 CoolProp `PropsSI` 独立计算 |
| 页面可放置与连接 | 已完成 | 模块库“制冷站设备”分组；多端口设备端口分开排列；可选端口不再被“检查连接”判为未连接；制冷剂端口要求出口接入口 |
| 系统连接校验、8 状态推进与会话 | 已完成（同日，见下节） | [refrigeration/station.py](../../backend/fn_engine/refrigeration/station.py) |

默认参数（工程假设，B0 再定）下单台压缩机在 −30/35 °C 时制冷量约 70.7 kW、电功率 37.7 kW、排气温度约 207 °C（单级、未计油冷），压比 11.3；三台运行时冷凝负荷约 316 kW，与冷凝器默认 320 kW 排热匹配。

实测：`python -m pytest -q --cov=fn_engine` **419 passed**（新增 29 项），覆盖率 **89.0%**；ruff 通过，mypy 仍为基线 40 条；契约重新生成（10 个文件各增加 `refrigerant` 枚举）；`npm run check` 与 12 个浏览器脚本通过。另用临时 Playwright 脚本在页面放置低压循环桶、压缩机、贮液器：4 个端口位置互不重叠，`vapor→suction` 可连、出口接出口被拒，“检查连接”返回 `REFRIGERATION_STATION_PENDING`，页面无脚本错误。

## 2026-10-20 B1 系统层

设备连成系统后可以运行：`compile_station` 由连接推出流股节点 → 压力等级（每级一个容器）→ 制冷剂回路，`StationSession` 对容器 `(M,U)` 与库房温度做隐式 Euler（牛顿法、雅可比跨步复用、失败子步减半），控制、命令、后台运行与 A1 共用会话协议。规则与方程见 [ALGORITHM 制冷站系统层](../../docs/ALGORITHM.md#制冷站系统层refrigerationstationpy执行域-refrigeration)，合同见 [DATA_CONTRACT](../../docs/DATA_CONTRACT.md#冷库-b-制冷站设备2026-10-20设备层)。

示例 [station_example](../../backend/fn_engine/refrigeration/examples.py)：4 台压缩机（3 台 80% 载量）、冷凝器、贮液器、节流阀（40%）、低压桶、复叠换热器、CO₂ 储液器与液泵、两台冷风机与两间相同库房（各 30 kW 附加负荷），NH₃/CO₂ 两回路。参数为工程假设，未接控制。

实测（[test_refrigeration_station.py](../../tests/test_refrigeration_station.py) 32 项，其中拓扑规则 12 项）：

- 拓扑：12 种不支持的连接/合同各报对应诊断码；不设回路工质时报 `VESSEL_INITIAL_STATE`（项目工质水无法在 −30 °C 饱和），不静默回退。
- 帧内设备关系按帧中容器压力用 `PropsSI` 重算一致（压缩机流量、压比、复叠换热量、冷凝温度、冷风机换热、泵流量分配、容器净流入）。
- 2 h 运行：由设备累计计数独立复算的能量账本差 0.037 J（交换量 3.4×10⁹ J），两回路存量相对变化 < 1e-12；内部步长 20/10/5 s 末值误差比 2.00（一阶收敛）。
- 九组执行器开环方向全部符合物理；其中单库冷风机风量减半时 CO₂ 饱和温度降 1.3 K、另一库反而更冷，是共用冷源的正确耦合。
- 运行中写参数下一步生效、非 runtime 参数被拒；液位越带停止并保留已接受帧；PID 可接在压缩机载量上；原型导出归一化后结果一致；API 后台运行可暂停/写参数/恢复，`/projects/validate` 返回 NH₃、CO₂ 两回路，稳态请求报 `REFRIGERATION_DYNAMIC_REQUIRED`。
- 性能：12 h fast 运行约 23 s（本机）。开环示例约 15.7 h 时高压贮液器液位到 95% 停止——无液位控制时存量在贮液器累积，属预期，B2 的闭环 3 处理。
- 全量 `pytest` **451 passed**，覆盖率 **89.4%**；ruff 通过，mypy 基线 40 不变；契约重新生成（health 增加 `refrigeration_station`）；`npm run check` 与 12 个浏览器脚本通过。页面上还没有一键创建入口，尚未做制冷站的页面级运行验收（B3）。

## 2026-10-21 A2–A6：A 版完成

用户要求“把 A 做完”。开工前决定：B1 系统层先单独提交（`76a1bfc`）；A5 的演示录像不做（从完成清单划掉）；三台设备按 PLAN 3.1 做成 thermal 域独立设备，压缩/物性函数与 B1 共用。

| 阶段 | 交付 | 证据 |
| --- | --- | --- |
| A2 循环与验证台 | [refrigeration/cycle.py](../../backend/fn_engine/refrigeration/cycle.py)：四状态点、额定点一次反算排量与冷凝器 UA、运行范围检查；B1 压缩机改用同一 `compress`/`displaced_flow`。`POST /api/v1/cold-store/workpoint` 与页面“机组工作点” | 四个工作点与 A0 独立参考逐项相对差 < 1e−9，排量、UA 完全一致 |
| A3 库房/货物/冷风机耦合 | 设备 `storage_room`、`unit_cooler`、`condensing_unit`（执行域 `cold_store`，[refrigeration/cold_store.py](../../backend/fn_engine/refrigeration/cold_store.py)）；库房与货物隐式 Euler，蒸发/冷凝温度牛顿联立 | 闭合库房守恒 < 1e−3 J；耦合帧按独立参考重算一致；独立账本残差 < 1 J；步长 5/2.5/1.25 s 关键指标差 ≤ 0.1 K、电量 ≤ 1% |
| A4 控制与日程 | `Project.events` / `Scenario.events`（开门、入库、室外温度、电融霜）；最小开/停机状态机、融霜相序与挂起；温控脚本（回差启停 + PI 容量）；示例 8 个工况 | 事件一次性执行、最小开停机不缩短、融霜相序、重试不重复计数、越界停止均有测试 |
| A5 展示与结果交付 | [frontend/cold-storage.js](../../frontend/cold-storage.js)：一键创建、指标面板、工况运行、负荷日程编辑、机组工作点、运行报告/CSV、策略对照；[refrigeration/report.py](../../backend/fn_engine/refrigeration/report.py) 生成报告与公平性检查 | 浏览器验收覆盖创建 → 运行 → 单步中改参数 → 改日程重算 → 导出 → 对照 → 保存 → 重启复算 |
| A6 案例验收 | [scripts/verify_cold_storage.py](../../scripts/verify_cold_storage.py)（全新工作区跑完全部工况并出案例包）、`soak_workspace.py --case cold-store` | [VALIDATION-A.md](single-room-minus18/results/VALIDATION-A.md)、[a6-20261021/](single-room-minus18/results/a6-20261021/) |

主要实测（详见 VALIDATION-A）：降温到 −18 °C 19.6 min；A-S01～A-S05 保温期无超温，库温在 −18.53…−17.46 °C；开门峰值 −17.51 °C、0.5 min 恢复；入库后货温 65.5 min 回到入库前温度；室外 38 °C 时冷凝 40.0 → 46.0 °C、COP 1.507 → 1.327；融霜峰值 −15.0 °C、约 6 min 恢复；A-S07 稳定在约 −14.3 °C 并报能力不足。A-S05 公平性一致，变容量比定容量启停省 6.51% 电，但低负荷时持续出现 `CYCLE_SUPERHEAT_APPROACH`，这个数字不作为工程结论。24 h 快算 33–55 s。

测试：全量 `pytest` **478 passed**（新增 `test_refrigeration_cold_store.py` 27 项），覆盖率 **90%**；ruff 通过，mypy 基线 40 不变；契约 51 个文件（新增工作点请求/响应，`Project`/`Scenario` 增加 `events`，health 增加 `cold_store_cycle`）；`npm run check` 与 12 个浏览器脚本通过。另修：`validated_parameters` 不再每次调用重建整个内置目录（每次控制写入从约 7 ms 降到可忽略）；画布属性的“介质”不再固定显示液态水。

2 h 墙钟稳定性（`soak_workspace.py --case cold-store`）：354 条暂停/单步/继续命令全部生效、0 错误、约 61 h 仿真时间，内存 297→305 MB，停止后 Worker 0。

范围外：录像（用户决定不做）；离线双击运行的发行包（PLAN 5.4 注明另计）；连续 24 h 墙钟服务承诺（PLAN 5.3 要求单独修复遗留问题后重验）。

## 2026-10-21 B0、B2、B3：B 版完成

用户要求“B 做完”。B0：[station/parameters.json](nh3-co2/station/parameters.json) 与只调用 PropsSI 的 [verify_station_reference.py](nh3-co2/tools/verify_station_reference.py)，由目标蒸发 110 kPa / 冷凝 1.35 MPa 反求全部执行器（9 项检查，全站能量平衡残差 1.5e−7 W）。B2：示例 `station_case()`（5 个 PID + 上层 Python 脚本），日程新增通用 `set_variable` 事件（冷库与制冷站共用，[refrigeration/schedule.py](../../backend/fn_engine/refrigeration/schedule.py)）。B3：项目页「NH₃/CO₂ 冷库案例」、指标面板、目标压力修改、运行报告与 CSV。

闭环 2/3 与原文对调（回气阀调贮液器压力、节流阀保液位），依据是 B1 开环：节流阀 0.4 → 0.6 时 2 h 内贮液器液位 0.61 → 0.30、压力只变 1%。

| 场景 | 结果 |
| --- | --- |
| B-S01 额定 24 h | 稳态与 B0 独立设计点一致（载量 0.8261、电功率 115.000 kW），库温偏离 0 |
| B-S02 负荷阶跃 | 6.5 h 增开 1 台、14.2 h 减停 1 台，库温最大偏离 0.73 K 后回到 −18.00 °C |
| B-S03 改目标压力 | 蒸发 110 → 125 kPa、冷凝 1.35 → 1.20 MPa 平稳跟踪，电功率 115.0 → 105.2 kW |
| B-S04 湿球变化 | 冷凝器风机 1 → ½ → 1，稳定后贮液器压力 ≤ 0.5%，过渡最大偏离 46 kPa |

四个场景 NH₃/CO₂ 存量残差 0、能量账本残差 ≤ 5 J、需求满足度 100%；24 h 快算 33–47 s。新增 `test_refrigeration_station_control.py` 8 项、`browser-cold-storage-station.mjs`、`scripts/verify_station.py`；验收记录 [VALIDATION-B](nh3-co2/station/results/VALIDATION-B.md)。

## 下一步

B2：在 `station_example` 上接五闭环 + 上层启停（Python 项目控制 + PID），按执行计划第 4 节四个场景验收。

A、B 两个示范案例均已完成。下一步只有在取得厂家或现场数据后才进入工程校核（PLAN 第 7 章，C）；策略研究（浮动蒸发/冷凝压力、机组调度）按 PLAN 7.3 单独估算。

| 阶段 | 当前状态 | 下一交付 |
| --- | --- | --- |
| A1 最小产品链路 | 已完成（2026-10-20） | 第一个实际可运行的库房动态项目 |
| A2 独立制冷机组 | 已完成（2026-10-21） | — |
| A3 热状态/换热耦合 | 已完成（2026-10-21） | — |
| A4 控制与日程 | 已完成（2026-10-21） | — |
| A5 展示与结果交付 | 已完成（2026-10-21；录像按用户决定不做） | — |
| A6 案例验收 | 已完成（2026-10-21） | 有厂家/现场数据后进入工程校核（C） |
| B NH₃/CO₂ 扩展 | 已完成（B0–B3，2026-10-21） | 有数据后工程校核（C） |

已保存证据随输入/脚本版本保留。修改参数后使用新输出目录重算，并在本文件记录变化、原因和验收状态。
