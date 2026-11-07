# 文档入口

当前维护日期：2026-11-07。功能文档描述行为；验收记录只对标注的源码基线有效，历史覆盖率和性能数字不自动成为当前版本结论。

| 需要了解的内容 | 入口 |
| --- | --- |
| 本轮架构收尾范围与证据 | [架构后续验收](ARCHITECTURE_FOLLOWUP_ACCEPTANCE.md) |
| 后端类型边界、兼容导入、Worker 依赖 | [模型类型分层](MODEL_LAYERING.md) |
| Runner 与集中接受事务 | [Runner 协议](RUNNER_PROTOCOL.md) |
| 设备定义与展示元数据注册试点 | [设备注册](DEVICE_REGISTRY.md) |
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
