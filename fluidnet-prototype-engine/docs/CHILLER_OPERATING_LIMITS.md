# 水冷冷水机组：最小水量保护与低负荷周期平均运行

日期：2026-11-04。对应暖通第二批 E09 的首版增量；厂家性能图、多机调度与真实逐次启停仍未实现。

现有 `water_chiller` 增加两侧最小质量流量和可选最小运行负荷比。全部新参数默认为 0，原项目继续使用原有连续调节模型。`running=0` 关闭制冷和耗电，两条水通路继续按原阻力通流。

## 参数与操作

在新建的水冷冷水机组或“冷水机组与房间风水联算”示例中，打开机组参数：

| 参数 | 显示含义 | 规范单位与范围 | 默认 |
| --- | --- | --- | --- |
| `evaporator_min_flow_kg_s` | 冷冻水最小质量流量 | kg/s，≥0 | 0，不启用此保护 |
| `condenser_min_flow_kg_s` | 冷却水最小质量流量 | kg/s，≥0 | 0，不启用此保护 |
| `minimum_load_ratio` | 最小运行负荷比 | 0–1；界面显示 % | 0，连续调节 |

三个新参数为设备配置，修改后重新创建运行；原有 `running` 和冷冻水出水设定仍可在运行中修改。旧项目和模块快照不自动重写；编译旧定义时，新参数采用 0。新目录生成的三个房间温控示例和标准机房示例已带默认字段，既有示例计算设定没有改变。

可用三回路示例体验周期平均模型：将 `Chiller.minimum_load_ratio` 设为 0.7（界面 70%），其余参数保持默认，做稳态计算。此教学输入下制冷量约 14.842 kW、压缩机平均电功率约 2.460 kW、开机比例约 56.573%，冷冻水平均出水保持 7°C。以上不是厂家标定结果。

## 最小流量保护

当 `running≥0.5`，最终运行点任一侧质量流量小于对应非零阈值时，返回 `CHILLER_EVAPORATOR_LOW_FLOW` 或 `CHILLER_CONDENSER_LOW_FLOW`，注明设备和参数；等于阈值允许运行。保护按运行请求生效，即使当前没有制冷需求也检查。

密度与热力迭代中的候选点不触发该阈值保护，最终收敛点必须通过检查。保护失败拒绝当前子步，不提交新时间、能量累计或模块候选状态，也不通过强制改流量来满足最小水量。默认阈值 0 保留原来的零流量行为：无冷冻水量时不制冷；有制冷需求而无冷却水时拒绝排热工况。

2026-11-04 复核修正了保护检查位置：热力内循环完成不等于水力与物性整体收敛。现在普通水侧（reference/node）和风水联算都在统一 `solve_network` 出口、模块观察与状态接受之前检查两侧最终流量；单独调用机组工作点计算时仍可直接校验给定流量。

保护不添加自动旁通、泵联锁或锁存故障。需要这些策略时应通过真实拓扑与项目控制定义。`running=0` 不执行最小流量检查；停机不会自动关断水路，两侧仍遵守原有正向通流与反流限制。

## 周期平均模型

`minimum_load_ratio>0` 时，先求满足平均冷冻水出水设定的连续调节需求。若所需负荷比低于最小值，另求**最小负荷开机工作点**：

```
Q_on = g_evaporator × (T_evaporator_in − T_evaporating)
Q_on + W_on = g_condenser × (T_condensing − T_condenser_in)
duty = Q_requested / Q_on
Q_average = duty × Q_on
W_average = duty × W_on
```

其中换热导纳 `g = C × (1 − exp(−UA/C))`，开机负荷比表示当前单级循环模型的排量比例。开机工作点仍必须满足原机组温度、排气温度和压比范围；两侧开机出口还要通过各自液体物性检查，不能只检查平均出口来掩盖开机段的无效状态。

平均制冷量、冷凝排热、轴功、电功和制冷剂流量都乘以开机比例。平均两侧焓差与这些功率保持一致，冷凝排热仍等于制冷量加压缩轴功。温度、压力、压比和 COP 对应开机工作点。超过最小负荷时开机比例为 1；满载不足仍使用原 `capacity_limited` 行为。

| 输出 | 含义 |
| --- | --- |
| `compressor_load_ratio` | 开机期间的负荷比，停机为 0 |
| `cycling_ratio` | 周期平均开机比例，停机为 0，连续运行时为 1 |
| `low_load_cycling` | 是否采用低负荷周期平均运行，布尔值 |
| `load_ratio` | 平均负荷比，即开机负荷比 × 开机比例；默认连续模型保持原值 |
| `cooling_power_w`、`electric_power_w` 等功率 | 周期平均值；累计量继续只在已接受子步按功率积分 |

这些字段进入统一变量目录、曲线、批量观察和冻结 HTML/CSV 报告。百分比显示统一由规范比例换算；报告同时保存周期平均模型假设，服务重启读取历史不会重新求解。

该模型假定两侧水泵在开机与停机阶段持续通流，忽略启动损失、待机耗电、水温周期波动和具体周期长度。**它不模拟真实启停时刻、次数、温控回差或最短启停时间。** 当前水回路仍无储量，关闭机组后带持续净热源的闭式回路可能没有代数平衡解；不能把压力参考当成隐藏冷源。逐次启停需要另外接入水侧储热及其接受状态，未在本次实现。

## 实现与验证

- `backend/fn_engine/water_chiller.py`：最终点最小流量保护、最小负荷开机工作点与周期平均输出。
- `backend/fn_engine/air_liquid.py`：用冷却水自身物性检查开机出口，保留错误字段。
- `backend/fn_engine/solver.py`：在水力与物性整体收敛之后统一执行机组最小流量保护，覆盖普通水侧与风水联算。
- `backend/fn_engine/air_catalog.py`、`air_variables.py`：新参数、输出单位和冻结报告假设。
- 不增加新的启停状态；累计量仍由现有 `SimulationSession` 接受事务与 `air_ledger` 提交。

本地验证命令：

```powershell
python -m pytest -q tests/test_water_chiller.py tests/test_chiller_operating_limits.py tests/test_chiller_air_loop.py tests/test_air_room_controls.py
python -m ruff check backend/fn_engine tests/test_chiller_operating_limits.py
python -m mypy --config-file mypy.ini
python scripts/generate_contracts.py --check
python scripts/generate_room_control_examples.py --check
python scripts/generate_hvac_examples.py --check
```

2026-11-04 定向测试：43 passed，34.37 秒；ruff 通过，mypy 93 个源码文件无错误。覆盖最低负荷独立方程解、平均能量守恒、最小负荷阈值连续性、运行范围保护、旧参数缺键兼容、两侧流量阈值、停机真实压降与等焓通流、失败不累计、真实三回路守恒、API 报告与服务重启。90 个生成合同无需修改；三个房间温控与一个标准机房示例仅同步机组目录字段。三个房间温控、七个暖通示例、液体作者示例与暖通设备包的生成物检查均通过。按用户要求，本轮不执行全量回归。

### 最小流量误触发修复复验

新增三条真实网络回归先在修复前全部失败：普通水侧首次物性迭代的冷冻水量为 1.240752151 kg/s，最终应为 1.241668203 kg/s，阈值 1.241210177 kg/s 被提前判为不足；风水示例冷冻水阈值 1.1694 kg/s、冷却水阈值 3.558 kg/s 也因初轮流量较小而误触发。修复后三条均正常收敛，并保留两侧真实不足时的错误字段与接受状态保护。

接受状态回归使用仍处于有效机组热力范围的低流量工况，分别降低冷冻水和冷却水压差：流量低于 1.2 kg/s 门槛时不推进时间、能量累计和最后已接受帧。极低流量若先违反原机组温度/压比范围，仍允许原物理保护先拒绝，不把无效物态强制送到流量保护出口。

本次复验 `python -m pytest -q tests/test_water_chiller.py tests/test_chiller_operating_limits.py tests/test_chiller_air_loop.py --tb=short`：**51 passed，55.65 秒**。包含 reference/node/风水三条路径、两侧最终低流量拒绝及上述误触发回归。改动文件 ruff、`git diff --check` 通过，mypy 93 个源码文件无错误；未运行全量测试。
