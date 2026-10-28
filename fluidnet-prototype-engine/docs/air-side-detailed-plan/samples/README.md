# 目标合同的 JSON 样例

这些文件对应[详细设计](../README.md)，供后续实现和接入照填。已检查 JSON 语法；没有向当前服务提交，也没有运行求解或测试。它们使用拟新增字段/模块，不能把当前 Phase 2a 服务的拒绝当作该功能已支持。

| 文件 | 包络 | 使用方式 |
| --- | --- | --- |
| [air-coil-minimal.project.json](air-coil-minimal.project.json) | 完整规范 Project | 目标服务 POST `/api/v1/projects/validate` 或 `/solve`；需要运行记录时包进 RunRequest.project |
| [air-room.instance.json](air-room.instance.json) | ModuleInstance 片段 | 添加对应模块定义和端口连接后放入 Project.instances |
| [humidifier.instance.json](humidifier.instance.json) | ModuleInstance 片段 | 同上；本例为等焓限幅加湿 |
| [cooling-tower.instance.json](cooling-tower.instance.json) | ModuleInstance 片段 | 放入 Water/liquid 项目；空气边界在设备参数中 |
| [batch-preview.request.json](batch-preview.request.json) | BatchPlanRequest | 项目存在 C1 且修订匹配时，用于批次 preview；扫描温度值是显示单位 °C |

实际发布时从目标目录冻结完整模块定义与版本哈希；不把示例中手写的内置定义替代已保存包的哈希。字段语义以 [02 合同](../02-contracts.md)、请求用法以 [04 API](../04-api-and-sequences.md) 为准。
