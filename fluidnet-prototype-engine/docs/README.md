# 文档入口

当前维护日期：2026-11-07。功能文档描述行为；验收记录只对标注的源码基线有效，历史覆盖率和性能数字不自动成为当前版本结论。

| 需要了解的内容 | 入口 |
| --- | --- |
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
