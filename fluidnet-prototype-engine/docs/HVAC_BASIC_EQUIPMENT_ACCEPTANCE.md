# 暖通基础设备与理想测点：验收记录

> 验收日期：2026-11-02 ｜ 第一批功能提交：`ea567fe`；本次收尾基线：`d89e2e2`
> 使用与设计说明见[暖通基础设备与理想测点](HVAC_BASIC_EQUIPMENT.md)；需求来源见[暖通设备补全清单](HVAC_BASIC_EQUIPMENT_CHECKLIST.md)。

## 1. 交付范围

| 类别 | 内容 |
| --- | --- |
| 设备模块（16 个包，`modules/`） | `pipe_reducer`、`water_tee`、`water_header_2/4/6/8`、`water_collector_2/4/6/8`、`water_balancing_valve`、`water_shutoff_valve`、`water_strainer`、`water_three_way_valve`、`hvac_water_pump`、`hvac_check_valve` |
| 设备定义与组合 | `backend/fn_engine/hvac_basic.py`（设备定义 + 冻结组合展开）、`scripts/generate_hvac_modules.py`（包与清单的一致性来源） |
| 示例 | `backend/fn_engine/hvac_examples.py`、`examples/hvac-basic/*.project.json`、`scripts/generate_hvac_examples.py` |
| 理想测点 | `backend/fn_engine/measurements.py`、`MeasurementSpec`（`models.py`）、编译期校验（`compiler.py`）、运行期求值（`solver.py` / `simulation.py`）、`trend` 历史保留（`jobs.py`）、模块版本迁移改写引用（`migrations.py`）、原型归一化（`bridge.py`）、风侧变量描述（`air_variables.py`） |
| 界面 | 控制页“仪表与测点”面板（新增／编辑／移除、实时读数、加入曲线）、测点进入 PID 反馈选项与项目变量表、风系统页七个暖通示例入口、工作区模块数上限调整（64→256） |
| 契约与门禁 | `contracts/` 重新生成；`package.json` 与 `.github/workflows/ci.yml` 加入两个暖通生成脚本的 `--check` |

## 2. 验证结果

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 暖通专项测试 | `python -m pytest tests/test_hvac_equipment.py tests/test_hvac_reducer.py tests/test_hvac_templates.py -q` | **84 passed**（本次重跑 148.33 s） |
| 基础设备浏览器回归 | `node tests/browser-hvac-equipment.mjs` | **通过**：模块目录 72 个模块自动发现、创建水力平衡示例、测点读数、差值测点、PID 反馈、曲线、机房联锁模板载入、保存重载保留 4 个测点，`pageerror` 为空 |
| 标准机房浏览器验收 | `node tests/browser-hvac-plant.mjs` | **通过**：界面创建双盘管三回路案例、稳态运行、独立水侧质量／热平衡、仪表与 HTML／CSV 报告、平衡阀 80%→40% 调节、保存重载后复算一致，`pageerror` 为空（详见第 7 节） |
| 类型检查 | `python -m mypy` | 92 个源文件无问题 |
| Lint | `python -m ruff check backend tests scripts modules examples/control_templates` | All checks passed |
| 契约一致性 | `python scripts/generate_contracts.py --check` | 90 个文件一致（本轮已重新生成 `contracts/`） |
| 设备包一致性 | `python scripts/generate_hvac_modules.py --check` | HVAC equipment packages consistent |
| 示例快照一致性 | `python scripts/generate_hvac_examples.py --check` | 7 HVAC examples verified |
| 前端语法 | `npm run check` | 通过（含两个暖通浏览器脚本） |
| 历史全量后端回归 | `python -m pytest -q --cov=fn_engine` | 见第 5 节；本次收尾未重跑全量 |

## 3. 关键数值（本机实测）

| 场景 | 结论 |
| --- | --- |
| 异径管（100→50 mm，突变） | 正流 K=0.375、反流 K=0.5625，与独立小口径损失参考一致（相对误差 1e-12），质量残差 < 1e-7 kg/s |
| 异径管（渐变，包角 30°） | 正流 K=0.15529、反流 K=0.37852；稠密与稀疏两种求解方法结果一致 |
| 异径管互换 | 交换进出口管径与反向连接等价（质量流量等值反号） |
| 手动平衡阀 | 50% 开度按特性曲线给出有效流通比 0.4（线性阀为 0.5）；0% 开度精确零流量 |
| 关断阀 | 开度 < 0.5 时为 0（两位操作），≥ 0.5 时全开 |
| Y 型过滤器 | 额定 10 m³/h、干净压降 5000 Pa；污堵 50% → 10000 Pa，100% → 15000 Pa |
| 循环水泵停机 | 按 `stopped_loss_coefficient=20`、DN50 的被动阻力通流，正反向对称，电功率为 0 |
| 止回阀 | 正向压差 > 1000 Pa 导通、< 500 Pa 关闭；1500 → 750 → 400 → 750 Pa 序列中 750 Pa 保持开启（迟滞）、400 Pa 关闭且之后 750 Pa 仍保持关闭，状态在接受步提交，反向严格零流量 |
| 三通调节阀混流 | 两路各半时混合水温 25.0 °C；三端口质量守恒 < 1e-7 kg/s、焓守恒 < 0.02 W，全网能量残差 5.8e-11 W |
| 两支路水力平衡示例 | 支路体积流量 10.1 / 11.2 m³/h（需求 10 m³/h 级），供回水压差 78.2 kPa，测点读数与帧变量一致 |
| 泵切换示例 | 5 s 后工作泵与备用泵互换：停泵支路零流量、止回阀关闭、参考口无隐含补水，电能账本与逐帧功率求和一致（相对误差 1e-8） |
| 双盘管冷水机房示例 | 冷冻水总流量 2.179 kg/s；机组冷量 14.12 kW = 两台盘管热量 + 冷冻水泵功；冷却塔排热 15.82 kW = 冷凝热 + 冷却水泵功；第二盘管水侧热功率测点 4.66 kW |
| 测点校验 | 未知引用、单位与计算类型不符、两点差值单位不同、显示单位带偏移均以 `MEASUREMENT_INVALID` 拒绝；运行期缺失/NaN/溢出输入返回 `null` + `MEASUREMENT_UNAVAILABLE`，重复调用不累积诊断 |
| 空调箱与房间送风 | 送风 16.6 °C、约 3324 m³/h，房间稳定在 18.6 °C；盘管制冷量 7.37 kW 与独立水侧 `m·Δh` 一致（相对误差 1e-6），冷冻水温升 11.6 K，送风含湿量低于回风 |
| 新风机组／风机盘管模板 | 305.15 K、14 g/kg 进风被降到低于进风 5 K 以上且含湿量下降；冷冻水侧吸热升温，全网能量残差 < 0.05 W、质量残差 < 1e-7 kg/s |
| 定压补水 | 泄漏 0.02／0.1／0.6 开度对应补水 0.078／0.397／3.10 m³/h，补水与泄漏相对差 < 0.02%；止回阀累计质量随运行增加，阀位只取全开或最小开度两种 |
| 机房联锁 | 2 s 压差确认后 1 号泵单独运行（流量 > 0.5 kg/s），10 s 后切换到 2 号泵且 1 号泵流量 < 1e-6 kg/s；扬程不足工况在确认窗口后两台泵停止、`phase='tripped'`、流量 < 1e-3 kg/s |
| 组合端口湿空气字段 | 组合外端口在湿空气回路上公开含湿量、干空气与水蒸气质量流量，测点可直接绑定送风含湿量（此前组合只映射压力/温度/焓/流量/密度等基础字段） |

## 4. 本轮修复的问题

1. 暖通专项测试最初 25 项失败，全部来自测试与平台既有契约不一致，已按平台语义修正：
   - 端口物性字段（`density_kg_m3`、`enthalpy_j_kg` 等）只在 `SolverOptions.thermal=True` 时进入运行帧（`solver.THERMAL_ONLY_SUFFIXES`）；相关用例改为开启热力层后再按端口密度校核流量。
   - `CompilationError` 只暴露 `.diagnostic.code`，测试改为读取该属性。
   - `RunFrame` 字段为 `status/valid/time_s/...`；NaN 帧无法通过模型校验，改为 `model_construct` 直接构造以覆盖非有限值保护。
2. `hvac-water-balance` 示例的两个“体积流量”测点原本恒为 `null`：示例关闭了热力层，而体积流量需要端口密度。现已为该示例开启热力层，测点读数恢复（见第 3 节）。

## 5. 全量回归

以下为基础设备与理想测点提交 `3cea2f3` 的历史全量记录，由 `c503fc1` 补录，早于成套模板、定压补水与联锁提交 `ea567fe`。本次收尾重新执行了第 2 节的 84 项暖通专项、两个浏览器脚本及类型／Lint／生成一致性检查；此处的覆盖率不代表当前全部改动的重测结果。

`python -m pytest -q --cov=fn_engine`（本机 Python 3.11，单进程）：

```text
1855 passed, 5 warnings in 2170.99s (0:36:10)
TOTAL 15811 语句，覆盖率 90.75%（门禁 85%）
Required test coverage of 85.0% reached.
```

本轮新增文件覆盖率：`measurements.py` 92%、`hvac_examples.py` 99%；`hvac_basic.py` 为 0%——它只是 16 个设备包的生成来源，由 `scripts/generate_hvac_modules.py --check` 在 CI 中保证与 `modules/` 一致，运行时不导入。

## 6. 复现命令

```powershell
cd fluidnet-prototype-engine
python -m pytest tests/test_hvac_equipment.py tests/test_hvac_reducer.py tests/test_hvac_templates.py -q
python -m ruff check backend tests scripts modules examples/control_templates
python -m mypy
python scripts/generate_contracts.py --check
python scripts/generate_hvac_modules.py --check
python scripts/generate_hvac_examples.py --check
npm run check
$env:PYTHONPATH='backend'; npm run test:browser:hvac
```

## 7. 标准机房主流程收尾（2026-11-02）

操作见[标准机房基础案例](HVAC_STANDARD_PLANT.md)。复用现有 `hvac-basic-plant`，本次新增完整浏览器验收和操作说明，并清理 `hvac_examples.py` 中三项未使用的联锁阈值常量；控制脚本自己的压差阈值与时序仍为唯一配置来源。

| 仪表 | 基准（阀 1 为 80%） | 阀 1 调到 40% | 保存重载后 |
| --- | --- | --- | --- |
| 支路 1 / m³/h | 3.417192 | 1.678946 | 1.678946 |
| 支路 2 / m³/h | 4.427214 | 5.409521 | 5.409521 |
| 供回水压差 / kPa | 14.669836 | 21.901980 | 21.901980 |
| 第二盘管热功率 / kW | 4.661873 | 5.517035 | 5.517035 |

三个接受结果均独立核算水量和热量。支路质量残差为零；冷冻水热平衡最大误差 `0.00532 W`，冷却水最大误差 `0.00344 W`。两个压力参考口无隐含补水，参考输入热量为零。保存重载前后项目摘要相同，四个仪表复算一致。

证据：`artifacts/hvac-plant-validation.json`、`hvac-plant.project.json`、`hvac-plant.prototype.json`、`hvac-plant-report.html/csv` 与 `hvac-plant-*-1080p.png`。新增脚本已接入 `package.json` 的 `test:browser`、`check` 和专项 `test:browser:hvac`；既有 CI 从同一清单执行并收集产物。
