# FluidNet

当前项目是 [FluidNet Prototype Engine](fluidnet-prototype-engine/README.md)：可编程流体模块平台，包含 Pydantic 契约、网络水力求解、独立 Worker 和模块版本管理。启动、使用和开发说明见该目录。

2026-10-29 源码进展：风系统完整主线已接通，包含湿空气联合求解、房间热湿动态、冷却塔水耗、中文结果页与报告、旧项目迁移和批量方案。见[使用说明](fluidnet-prototype-engine/docs/AIR_SIDE_USER_GUIDE.md)及[实施验收](fluidnet-prototype-engine/docs/AIR_SIDE_IMPLEMENTATION_ACCEPTANCE.md)。

当前发布版本 **v0.5.0（2026-10-22）**：冷库 A 版单库房案例（A0–A6）、B 版 NH₃/CO₂ 集总制冷站案例（B0–B3）与倍思鹿模块开发套件 v1 已交付；发布说明见 [RELEASE_NOTES](fluidnet-prototype-engine/docs/RELEASE_NOTES.md)，许可证见 [LICENSE](LICENSE)。

| 目录 | 内容 |
| --- | --- |
| `fluidnet-prototype-engine/` | 当前开发项目 |
| `archive/fluidnet-studio-v0.2/` | 已归档的 FluidNet Studio v0.2.0 源码（标签 `fluidnet-studio-v0.2.0`），不再开发 |
| `output/` | 交互原型（引擎前端的来源）、倍思鹿对照与算法评审报告 |
| `V1.1多线程并行流体网络计算算法优缺点及调用说明.pdf` | 倍思鹿 NET 引擎参考资料 |

`dist/` 中的 v0.2 便携包和其中的用户 `workspace` 未纳入版本库，归档时保持原位。
