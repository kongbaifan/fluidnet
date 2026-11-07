# 设备定义与展示目录注册

2026-11-07 更新：首批五类储量设备试点基于 `c7410f6`；本轮从 `8cfabe1` 推广至全部 60 个内置设备。设备适用工质、编译、方程计算和状态接受仍由现有物理实现负责。

## 当前完整调用链

`catalog.builtin_catalog()` → `device_registry.BUILTIN_FAMILIES` → 每族定义工厂 → 登记校验 → 60 项有序目录。`catalog.py` 保留历史公共函数和定义辅助函数；原物理合同构造移至内部 `catalog_definitions.py`。流体/暖通共享变量声明补全，但每族只创建一次，不逐设备重复构造全目录，也不跨请求缓存可变定义对象。

| 登记族 | 数量 | 定义来源 |
| --- | ---: | --- |
| fluid | 12 | 原流体、风管、盘管、加湿器、换热器及容积定义 |
| hvac | 9 | air_catalog 的风水设备，补全原有变量声明 |
| storage | 5 | 首批独立储量定义工厂 |
| thermal | 2 | 库房热节点与理想冷源 |
| cold-store | 3 | 库房、冷风机与集总冷凝机组 |
| refrigeration | 29 | 容器、压缩机、冷凝器、节流、供液、流股、DX与热集管 |

每族声明有序成员和展示元数据。定义工厂的实际输出必须与声明顺序完全一致；重复族/ID、漏登记、错误身份或端口领域变化均拒绝。元数据接口只读取登记，不执行物理定义工厂。能力标签仍是描述性可选信息，未声明的设备返回空列表，不能据此允许物理连接。

前端 `project-model.installBuiltinCatalog()` 接收目录和展示元数据，engine-client 不再维护型号可见性白名单。正常新后端路径使用登记信息；旧后端 404/501、未知版本或不完整元数据使用集中在 project-model 的兼容映射。Python 包继续通过 `/modules` 发现，保留其旧图标回退，不被内置元数据覆盖。

压力源/泵/阀等原型设备的已有无 manifest 对象只补展示，不替换参数定义表和库值：`pressure`、`speed`、`opening` 等显示别名不变。规范 manifest 设备使用自身字段。桥接绑定用实际目录通用补全，旧 59 项绑定逐项保持，仅增加此前未在库中暴露的 `closed_volume` 规范绑定。它是现有困液模型的新建模入口，其物理适用限制未放宽。冻结工程快照不随目录刷新改变。

## 首批五类登记（保留试点记录）

`device_registry.STORAGE_DEVICES` 每项声明模块 ID、延迟加载的定义工厂、端口领域、能力标签、模块库图标和画布符号族。`catalog.builtin_catalog()` 通过 `registered_definitions()` 装配这五项，替代原来的五组直接导入与追加。重复 ID、工厂返回错误 ID/运行类型、端口领域不符会在暴露目录前报错；每次装配仍创建独立定义对象。

独立 `GET /api/v1/catalog/presentation` 返回版本为 `1` 的展示目录。HTTP DTO 位于 `model_types/catalog_presentation.py`；执行模型、SDK 和原有 `CatalogResponse` 均不增加展示字段。读取展示目录不调用定义工厂。

前端启动时加载展示目录，`engine-client.js` 委托目录安装入口纳入模块库，`project-model.js` 将图标和符号族写入界面模块的 `presentation`，`canvas-symbols.js` 优先消费有效符号族。未登记的外部包继续沿用现有兼容映射和符号推断。已登记的新设备无需为了模块库可见性再改前端型号清单；这不代表新增物理设备无需扩展对应物理域。

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
- 前端旧型号映射只作为旧后端及 Python 包兼容层暂留。全部内置目录定义已由族注册表装配，物理方程分派仍由原执行域负责。

## 首批试点验证记录

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


## 全目录推广验收

变更前记录全部 60 项的 `definition_hash` 和完整 JSON SHA-256，保存在 `tests/fixtures/catalog-registry.json`，同时冻结旧 59 项原型参数绑定。迁移后完整 JSON、顺序和全部定义哈希一致；旧绑定不变，仅新增 `closed_volume`。不重新生成旧模块或 SDK 合同；111 份合同检查仍一致，OpenAPI 本轮零变化。

| 检查 | 本轮实际结果 |
| --- | --- |
| `python -m pytest tests/test_device_registry.py -q` | 7 项通过；包含全目录基线、独立对象、拒绝错误成员/排序、元数据不调用工厂、59 旧绑定、新容积原型插入参数归一化及编译 |
| `node --test tests/catalog-presentation.test.mjs tests/project-model.test.mjs tests/canvas-symbols.test.mjs tests/module-service.test.mjs` | 33 项通过；包含新型号无需前端 ID、旧别名保留、目录回退、Python 图标、冻结快照与展示隔离 |
| 新目录/注册/桥接/测试 Ruff，目录/注册/桥接四文件 mypy | 通过 |
| `python scripts/generate_contracts.py --check` | 111 文件一致 |

`browser-module-catalog.mjs` 已扩展为对全部 60 个内置目录项逐个检查图标，再验证八个 Python 参考包及文档弹窗；真实浏览器结果由根任务统一登记，本节不将脚本修改当作浏览器已通过。未运行全量测试，未修改数值内核或放宽任何工质/设备连接限制。
