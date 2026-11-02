# FluidNet

当前项目是 [FluidNet Prototype Engine](fluidnet-prototype-engine/README.md)：可编程流体模块平台，包含 Pydantic 契约、网络水力求解、独立 Worker 和模块版本管理。启动、使用和开发说明见该目录。

当前源码的[架构图与核心时序图（2026-10-31）](fluidnet-prototype-engine/docs/ARCHITECTURE_AND_SEQUENCE.md)覆盖五类执行域、风水三回路与房间温控、模块接受事务、版本发布和批量工况，附 SVG、PNG 与可编辑 Mermaid 源码。

2026-10-29 源码进展：风系统完整主线已接通，包含湿空气联合求解、房间热湿动态、冷却塔水耗、中文结果页与报告、旧项目迁移和批量方案。见[使用说明](fluidnet-prototype-engine/docs/AIR_SIDE_USER_GUIDE.md)及[实施验收](fluidnet-prototype-engine/docs/AIR_SIDE_IMPLEMENTATION_ACCEPTANCE.md)。

同日后续已接通真实水盘管、水冷冷水机组和空气/冷冻水/冷却水三个回路的[完整联算示例](fluidnet-prototype-engine/docs/CHILLER_AIR_LOOP.md)，本轮检查状态见[联算验收](fluidnet-prototype-engine/docs/CHILLER_AIR_LOOP_ACCEPTANCE.md)。

2026-10-30 后续新增[热耦合液体侧 Python 作者设备](fluidnet-prototype-engine/docs/COUPLED_LIQUID_MODULES.md)与[房间自动温控](fluidnet-prototype-engine/docs/ROOM_TEMPERATURE_CONTROL.md)：可编辑水阀参与制冷站联算，三回路房间案例支持自动调阀、负荷变化和目标温度变化。两条主线已完成，最终检查与证据见[综合验收](fluidnet-prototype-engine/docs/COUPLED_MODULES_ROOM_CONTROL_ACCEPTANCE.md)。

2026-11-02 源码进展：新增[暖通基础设备与理想测点](fluidnet-prototype-engine/docs/HVAC_BASIC_EQUIPMENT.md)——异径管、水侧三通、分水器／集水器（2/4/6/8 支路）、手动平衡阀、关断阀、Y 型过滤器、三通调节阀、含停机阻力的循环水泵和带开启／关闭压差的止回阀，配合项目级仪表测点（两点差值、体积流量、热功率）与四个组网示例；核对清单见[补全清单](fluidnet-prototype-engine/docs/HVAC_BASIC_EQUIPMENT_CHECKLIST.md)，证据见[验收记录](fluidnet-prototype-engine/docs/HVAC_BASIC_EQUIPMENT_ACCEPTANCE.md)。

当前发布版本 **v0.5.0（2026-10-22）**：冷库 A 版单库房案例（A0–A6）、B 版 NH₃/CO₂ 集总制冷站案例（B0–B3）与倍思鹿模块开发套件 v1 已交付；发布说明见 [RELEASE_NOTES](fluidnet-prototype-engine/docs/RELEASE_NOTES.md)，许可证见 [LICENSE](LICENSE)。

| 目录 | 内容 |
| --- | --- |
| `fluidnet-prototype-engine/` | 当前开发项目 |
| `archive/fluidnet-studio-v0.2/` | 已归档的 FluidNet Studio v0.2.0 源码（标签 `fluidnet-studio-v0.2.0`），不再开发 |
| `output/` | 交互原型（引擎前端的来源）、倍思鹿对照与算法评审报告 |
| `V1.1多线程并行流体网络计算算法优缺点及调用说明.pdf` | 倍思鹿 NET 引擎参考资料 |

`dist/` 中的 v0.2 便携包和其中的用户 `workspace` 未纳入版本库，归档时保持原位。
