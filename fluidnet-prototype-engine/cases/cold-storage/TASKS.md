# 冷库案例任务与进度

开始日期：2026-10-19。当前阶段：**A1 最小产品链路已完成（2026-10-20），下一阶段 A2 真实制冷循环**。

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
- 完成 B 版详细执行计划：[EXECUTION_PLAN.md](nh3-co2/EXECUTION_PLAN.md)（执行域与模块合同、物理方程、求解与时序、控制、前端、WBS、验证矩阵、数据计划、排期与风险、开放决策）。
- 证据边界：未取得倍思鹿项目文件、参数、初态、控制源码或运行结果；只做架构/工作流对照，不做数值对测；公开截图读数不作为设计点。
- B0 尚未开始（等待 A2–A6）；B0 的设计/数据/验证矩阵可在 A4–A6 期间提前准备。

## 下一步

按 [PLAN.md](PLAN.md) 进入 A2：真实单级制冷循环（四状态点、质量流量、制冷量、压缩功、COP、运行包络与设计工作点），用 A0 独立参考逐项对照，并在独立验证台运行。A1 的保存/重启/浏览器验收基线保持不变。

B 版在 A6 后按 [B 版详细执行计划](nh3-co2/EXECUTION_PLAN.md) 启动 B0；参考层与证据边界见 [倍思鹿案例拆解](nh3-co2/BASELU_CASE.md)。

| 阶段 | 当前状态 | 下一交付 |
| --- | --- | --- |
| A1 最小产品链路 | 已完成（2026-10-20） | 第一个实际可运行的库房动态项目 |
| A2 独立制冷机组 | 未开始 | 产品循环与本目录参考逐项对照 |
| A3 热状态/换热耦合 | 未开始 | 库房与冻结货物、蒸发/冷凝工作点联动 |
| A4 控制与日程 | 未开始 | 七工况实际运行、事件和控制状态 |
| A5 展示与结果交付 | 未开始 | 曲线、指标、对照、报告与录像 |
| A6 案例验收 | 未开始 | 物理/数值/浏览器验证及案例包 |
| B NH₃/CO₂ 扩展 | B0 未开始（参考与执行计划已建立） | A6 后按 [B 版详细执行计划](nh3-co2/EXECUTION_PLAN.md) 启动 B0 |

已保存证据随输入/脚本版本保留。修改参数后使用新输出目录重算，并在本文件记录变化、原因和验收状态。
