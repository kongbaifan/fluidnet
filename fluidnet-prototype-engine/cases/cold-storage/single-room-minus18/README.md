# −18°C 冻结物储藏库

案例 ID：`single-room-minus18-v1`。当前阶段：A0–A6 已完成；产品验收结果见 [results/VALIDATION-A.md](results/VALIDATION-A.md)，进度见 [TASKS.md](../TASKS.md)。

采用 10 m × 8 m × 4 m 库房、R290 单级制冷、空气/内部构件与冻结货物两个热节点。参数统一为 K、Pa、W、J、kg、m、s；显示和报告可换算为 °C、kW、kWh。A1 产品链路只接入库房热节点与理想冷源；货物热节点、真实循环与冷风机在 A2/A3 接入。

| 文件 | 内容 |
| --- | --- |
| [parameters.json](parameters.json) | 几何、围护结构、热容、机组额定点、效率、控制与融霜参数 |
| [scenarios.json](scenarios.json) | A-S01～A-S07：降温、开门、入货、高环境、控制对照、电融霜与能力不足 |
| [sources.json](sources.json) | 每组参数的来源、假设和适用边界 |
| [references/workpoints.json](references/workpoints.json) | 独立循环工作点、四状态点、固定排量和冷凝器设计 UA |
| [references/VALIDATION.md](references/VALIDATION.md) | 实测验证结果、环境、输入/脚本哈希与下一步 |

已有货物与新增货物均处于冻结显热范围。开门用等效附加热负荷，电融霜按预定时间施加热量；不以当前输入推断湿度、霜量或食品冻结过程。

日程事件使用半开区间 `[time_s, time_s + duration_s)`；环境温度事件在该时刻起持续生效。货物事件按同类冻结物的能量混合计算，加入质量后货物 UA 按质量比例更新。融霜包括加热、滴水等待和恢复；两个状态期间停止制冷和库内风机。事件调度、状态机与子步回退已在 A3/A4 实现（`refrigeration/cold_store.py`）。

独立参考验证额定工作点，并在相同排量下计算较低蒸发温度、高冷凝温度、半容量工作点。高冷凝点是模型压力测试，不能作为 A-S04 库房动态结果；A-S04 的蒸发/冷凝温度在产品运行中与冷风机、室外温度联立求解。

从项目根目录核对已保存的参考：

```powershell
python cases/cold-storage/tools/verify_reference.py --check
```

需要重建时选择一个新的输出目录，脚本拒绝覆盖已有目录：

```powershell
python cases/cold-storage/tools/verify_reference.py --output cases/cold-storage/single-room-minus18/references-r2
```

参数或计算方法发生变化时递增输入版本，保留旧验证证据，并在 [TASKS.md](../TASKS.md)记录原因。A0 的热连接、会话和状态合同已随 A1 落地（thermal 执行域、会话工厂与统一运行接口，见 [TASKS.md](../TASKS.md) 的 A0-06/A0-07）；后续产品循环与热状态实现应与本参考独立核对。
