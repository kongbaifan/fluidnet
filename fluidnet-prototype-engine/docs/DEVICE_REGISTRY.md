# 设备注册试点：液体储能与库存设备

2026-11-07。实施基线：`c7410f6`，与本轮 `model_types` 分层兼容。本包只收口五类内置设备的定义注册与展示元数据；设备适用工质、编译、方程计算和状态接受仍由现有物理实现负责。

## 真实调用链

`device_registry.STORAGE_DEVICES` 每项声明模块 ID、延迟加载的定义工厂、端口领域、能力标签、模块库图标和画布符号族。`catalog.builtin_catalog()` 通过 `registered_definitions()` 装配这五项，替代原来的五组直接导入与追加。重复 ID、工厂返回错误 ID/运行类型、端口领域不符会在暴露目录前报错；每次装配仍创建独立定义对象。

独立 `GET /api/v1/catalog/presentation` 返回版本为 `1` 的展示目录。HTTP DTO 位于 `model_types/catalog_presentation.py`；执行模型、SDK 和原有 `CatalogResponse` 均不增加展示字段。读取展示目录不调用定义工厂。

前端启动时加载展示目录，`engine-client.js` 据其注册项纳入模块库，`project-model.js` 将图标和符号族写入界面模块的 `presentation`，`canvas-symbols.js` 优先消费有效符号族。未登记设备继续沿用现有兼容映射和符号推断。已登记的新设备无需为了模块库可见性再改前端型号清单；这不代表新增物理设备无需扩展对应物理域。

| 模块 ID | 定义工厂 | 图标 | 能力标签 |
| --- | --- | --- | --- |
| `closed_buffer_tank` | `buffer_tank.definition` | Database | 固定热质量储热 |
| `hydronic_buffer_tank` | `buffer_tank.hydronic_definition` | Database | 固定热质量储热、风水联算 |
| `gas_expansion_tank` | `expansion_tank.definition` | Database | 质量库存、压力参考 |
| `tower_pool` | `tower_pool.definition` | Database | 质量库存、储热 |
| `coupled_tower_pool` | `coupled_tower_pool.definition` | Droplets | 质量库存、储热、湿接触 |

五项端口领域均为 `fluid`，画布族均为 `tank`。能力标签用于描述登记范围，不是求解器能力校验或任意连接许可；例如湿接触塔池仍由原实现校验纯水与湿空气工况。

## 兼容边界

- 旧后端返回 404/501、未知版本或不完整展示数据时使用原有图标/符号；展示服务失败不妨碍计算目录初始化，并明确提示回退。
- Python 模块不会因 ID 与内置设备重合而继承内置展示登记。图标数据不是可执行 HTML；未知符号族回退到原有推断。
- 现有冻结工程快照保持自身展示。目录元数据只用于库中缺少展示信息的内置模块和后续新快照；创建快照时复制展示，不共享可变对象。
- 模块参数、端口、源码、执行合同和哈希不含展示元数据。物理参数键不会因图标/符号变化而变化。
- 前端旧型号映射作为兼容层暂留；本包未宣称所有设备注册或方程分派均已统一。

## 验证记录

| 检查 | 实测结果 |
| --- | --- |
| 改动前 `generate_contracts.py --check` | 111 文件一致 |
| 五类定义哈希、独立实例、错误登记和 HTTP 元数据隔离；模型分层守卫 | `test_device_registry.py` + `test_model_layering.py`：11 passed |
| 展示目录初始化/错误回退/冻结快照、图标符号、模块服务和参数转换 | 四个 Node 测试文件：31 passed |
| `browser-module-catalog.mjs` | 五类登记图标 + 八个原有参考模块的目录与文档流程通过，无浏览器错误 |
| ruff（新注册实现、DTO、测试）/ mypy（新实现、DTO） | 通过 |
| 更新后 `generate_contracts.py --check` | 111 文件一致 |

新增路由仅让 `contracts/openapi.json` 增加一个路径及 `CatalogPresentationResponse`、`DevicePresentation` 两个 schema，共 124 行。更新前对生成内容作结构断言：去除这三项后与旧 OpenAPI 完全相等；其余 110 个合同生成物未变。测试中的五个预先记录的 `definition_hash` 均保持不变。

本表只陈述本包实际执行结果；完整项目验收结论由本轮统一索引登记。
