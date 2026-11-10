# 文档入口

当前维护日期：2026-11-10。当前目标是聚焦设备组网与运行仿真，把建模、运行、调参和结果查看做稳定、做容易理解；实施顺序与完成标准统一见下方完整计划。功能文档描述行为；验收记录只对标注的源码基线有效，历史覆盖率和性能数字不自动成为当前版本结论。

| 需要了解的内容 | 入口 |
| --- | --- |
| 多业务统一计算、单位转换、能力发现与自定义适配器 | [通用计算适配层](CALCULATION_ADAPTERS.md) |
| 从范围收敛、建模运行到保存复用与源码交付的当前顺序 | [完整实施计划（2026-11-10）](MODULE_PRODUCT_ROADMAP.md) |
| 新建设备模块、放入空白画布、连接运行与保存复用 | [模块搭建流程](MODULE_ASSEMBLY_WORKFLOW.md) |
| 泵曲线点表、常用设备面板、单库房搭建与实际缺口 | [常用设备整理](COMMON_DEVICE_GUIDE.md) |
| 2026-11-08 底层补全进度、实际边界和可导入工程 | [总验收](FOUNDATION_COMPLETION.md)、[五个参考工程](../examples/foundation/README.md)、[时间步](TIMESTEP_DOMAIN_COMPLETION.md)、[作者本构](AUTHOR_CONSTITUTIVE.md)、[冷库过程](COLD_STORE_PROCESSES.md) |
| 大型多库房冷库示范、公开来源和设备缺口 | [设计与缺口记录](LARGE_COLD_STORE_DESIGN.md)、[工程文件与运行方法](../examples/large-cold-store/README.md) |
| 六库简单温控、保存导入收尾及 500t 材料核对 | [实用性验证](LARGE_COLD_STORE_USABILITY.md)、[500t 复算核对](RECALC_500T_REVIEW.md) |
| 回放遗留修复与日常 CI 收尾 | [P0 验收](P0_REPLAY_CI_ACCEPTANCE.md)、[日常与完整 CI](CI_CHECKS.md) |
| 架构剩余工作最终收尾 | [AC-1～AC-5验收](ARCHITECTURE_COMPLETION_ACCEPTANCE.md)、[Worker测量决策](WORKER_PRESTART_DECISION.md) |
| 本轮交互、目录推广和代表工程 | [交互与工程交付验收](INTERACTION_DELIVERY_ACCEPTANCE.md)、[代表工程详细证据](REPRESENTATIVE_PROJECT_ACCEPTANCE.md) |
| 本轮架构收尾范围与证据 | [架构后续验收](ARCHITECTURE_FOLLOWUP_ACCEPTANCE.md) |
| 后端类型边界、兼容导入、Worker 依赖 | [模型类型分层](MODEL_LAYERING.md) |
| Runner 与集中接受事务 | [Runner 协议](RUNNER_PROTOCOL.md) |
| 全部 60 类内置设备定义与展示注册 | [设备注册](DEVICE_REGISTRY.md) |
| 参数应用、旧工作区补全与迁移 | [交互边界](INTERACTION_BOUNDARIES.md) |
| 实时运行命令、轮询与迟到回包 | [运行命令边界](RUN_COMMAND_BOUNDARY.md) |
| 局部刷新、运行叠加性能与 DOM 保持 | [工作台局部刷新](WORKBENCH_LOCAL_REFRESH.md) |
| 前端功能职责、依赖与 ES Module 取舍 | [前端功能边界](FRONTEND_FEATURE_BOUNDARIES.md) |
| 工程画布、实测及物理结果展示 | [工程画布](ENGINEERING_CANVAS.md) |
| 浏览器测试清单与 CI 分组 | [前端 CI 分组](FRONTEND_CI_GROUPS.md) |
| 生成物来源、校验和审查摘要 | [生成物治理](GENERATED_ARTIFACTS.md) |
| 新增验收记录 | [验收模板](ACCEPTANCE_TEMPLATE.md) |
| 前端运行、保存及后端接入合同 | [后端接入](../frontend/BACKEND_INTEGRATION.md) |
| 公开 SDK、自主作者流程 | [平台扩展计划](PLATFORM_EXTENSION_PLAN.md) |
| 制冷与暖通设备整体交付 | [设备交付](EQUIPMENT_PROGRAM_DELIVERY.md)、[P1 验收](P1_DELIVERY.md) |
| 原会话架构整理历史 | [原整理计划](ARCHITECTURE_REFACTOR_PLAN.md)、[原验收](ARCHITECTURE_REFACTOR_ACCEPTANCE.md) |
| 数值性能证据 | [数值索引](numerics/README.md) |

本轮新增开发沿用原生 JavaScript、现有物理求解与接受事务；培训功能暂缓。当前进行的重构不改写历史验收记录。
