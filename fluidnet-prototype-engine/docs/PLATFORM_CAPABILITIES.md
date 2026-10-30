# 自主建模能力与执行范围（PF-0）

核对日期：2026-10-30。起始代码基线：`802b4c5`。本文按实际编译与执行入口区分能力；设备出现在模块库，不表示能放入所有类型的项目。后续制冷扩展按 [PF/RF 计划](PLATFORM_EXTENSION_PLAN.md) 单独推进。

## 执行范围

| 项目类型 | 内置设备与物理状态 | Python 作者设备、组合 | 当前限制及原因 | 源码与验证入口 |
| --- | --- | --- | --- | --- |
| 普通单相流体网络 | 管道、局部阻力、泵阀、单相换热等；水箱、管段热容与受限困液状态已有实现 | Python 水力、热力、观察与接受回调已接通；普通流体端口组合可递归展开 | 端口、工质、状态模型及适用工况需通过编译检查。Python JSON 累计状态不是隐式水箱或管内储热模型 | [compiler.py](../backend/fn_engine/compiler.py)、[module_phases.py](../backend/fn_engine/module_phases.py)、[模块执行测试](../tests/test_module_execution_network.py)、[作用范围测试](../tests/test_module_scope.py) |
| 湿空气与风水联算 | 湿空气输运、房间热湿状态、冷却塔、真实水盘管、水冷机组及两个独立水回路 | 空气侧 Python 模块须声明 SDK `air.pass_through.v1`；有真实 Worker 与验证台测试 | 风侧透传模块不能自动视为任意热湿处理设备。液体侧仍按各模型限制检查；风水联算拒绝水箱、困液和管段分布热容。跨侧自定义热湿设备不在本轮验收范围 | [compiler.py](../backend/fn_engine/compiler.py)、[air_compile.py](../backend/fn_engine/air_compile.py)、[湿空气协议测试](../tests/test_air_module_protocol.py)、[三回路测试](../tests/test_chiller_air_loop.py) |
| A1 库房热系统（`thermal`） | 库房热节点、理想冷源 | 只接受注册内置模型，不开放 Python 或组合设备 | 有界的热节点方程及端口合同；作者适配入口尚未实现 | [compile.py](../backend/fn_engine/refrigeration/compile.py)、[A1 测试](../tests/test_refrigeration_a1.py) |
| A 版冷库（`cold_store`） | 冻结货物库房、冷风机、单级机组；货温、库温及设备日程/开停状态 | 只接受注册内置模型 | 拓扑和设备角色绑定现有联立模型；作者设备合同与事务适配尚未实现 | [cold_store.py](../backend/fn_engine/refrigeration/cold_store.py)、[冷库路线图](COLD_STORAGE_ROADMAP.md) |
| B 版集总制冷站（`refrigeration`） | 压缩机、饱和容器、节流、液泵、换热设备、集管与库房；容器质量/内能和库温 | 内置模型和 schema 4 作者节流角色均可运行；正式 Worker、守恒流股、固定/自适应步接受及独立制冷验证台已接通 | 仅动态积分，独立稳态入口明确拒绝。现有编译器验证端口角色、压力等级、容器取相和参数合同。RF-2/RF-3 支持节流角色的正常运行、验证和发布；RF-4 已完成项目版本、报告及批量闭环，PF-2 全阶段验收已通过 | [station.py](../backend/fn_engine/refrigeration/station.py)、[制冷站测试](../tests/test_refrigeration_station.py) |
| 制冷站与液体热耦合（`coupled`） | 单相无储量内置网络与集总制冷站之间交换热量 | 液体侧拒绝 Python；制冷站侧沿用内置模型限制；组合展开不能绕过这些检查 | 最多两条关系，绑定同一饱和容器。液体侧拒绝水箱、困液和管段热容；额外状态需解决嵌套求解、跨域积分和失败回滚 | [coupling.py](../backend/fn_engine/refrigeration/coupling.py)、[热耦合测试](../tests/test_thermal_coupling.py) |

普通流体与湿空气共用流体编译器；湿空气由 `solver.moist_air` 配置，并不是可以任意填写的独立设备执行域。当前公共 SDK 最高版本为 0.7.0，旧版本按其原有能力集合校验，见 [module_contracts.py](../backend/fn_engine/module_contracts.py)。声明一个能力或修改 `solver_model` 不会自动获得对应执行适配。

## 作者、组合、控制与数据

| 能力 | 已有实现与需要遵守的边界 | 源码与证据 |
| --- | --- | --- |
| 从模板编写设备 | 阻力、泵/风机、双侧换热、受管理状态及制冷等焓节流五类模板；契约、源码、参数显示单位、测试组合与作者预期值可编辑 | [module_templates.py](../backend/fn_engine/module_templates.py)、[四类模板浏览器流程](../tests/browser-module-workflow.mjs) |
| 独立验证及发布 | 真实边界构网并执行 Worker；普通模块每通路使用独立端口，制冷角色使用饱和液体入口与定压出口；保存版本重新试算并验证输出。作者预期值通过不等于现场标定 | [bench.py](../backend/fn_engine/bench.py)、[packages.py](../backend/fn_engine/packages.py)、[版本测试](../tests/test_module_versions.py) |
| 组合封装 | 画布选取设备生成草稿，发布后插入；原设备保留。仅普通流体端口；压力边界留在组合外。深度上限 8、展开实例上限 1000 | [composites.py](../backend/fn_engine/composites.py)、[组合测试](../tests/test_module_composites.py)、[组合物理测试](../tests/test_module_composite_physics.py) |
| 组合版本 | 子定义内嵌，固定整数版本和源码/定义双哈希；公开参数及外端口一对一映射。同一项目不能同时展开同一模块 ID 的不同版本 | [composites.py](../backend/fn_engine/composites.py)、[模块开发指南](modules/DEVELOPMENT_GUIDE.md) |
| PID 与 Python 控制 | 引用实际项目的实例、可采样变量和 `runtime && writable` 参数；控制脚本只能访问声明的输入输出；历史脚本字符串迁移须由作者提供新源码 | [control.py](../backend/fn_engine/control.py)、[compiler.py](../backend/fn_engine/compiler.py)、[迁移测试](../tests/test_module_migrations.py) |
| 候选与接受状态 | Worker 求值使用已接受状态副本；接受前验证候选身份、版本、状态和输出；失败步不提升累计量。OS 进程隔离不等同于操作系统安全沙箱 | [module_transactions.py](../backend/fn_engine/module_transactions.py)、[事务测试](../tests/test_module_transactions.py)、[模块开发指南](modules/DEVELOPMENT_GUIDE.md) |
| 项目版本与复算 | 精确模块快照、项目修订、显式升级/映射、回退、规范/原型转换和单项目导入导出；历史运行使用冻结输入 | [projects.py](../backend/fn_engine/projects.py)、[project-services.js](../frontend/project-services.js)、[工作流浏览器测试](../tests/browser-workflows.mjs) |
| 结果与工况 | 冻结运行目录、报告、独立批次存档和最多四条对比曲线已有实现。作者编号及观察变量必须来自实际项目或历史快照 | [批量验收](FHD_BATCH_ACCEPTANCE.md)、[PF-1 作者流程测试](../tests/browser-platform-authoring.mjs) |

## 本轮发现与处理

已有 43 项模板、版本、迁移、组合和适用范围回归通过；四模板浏览器流程通过。其原有流程多从示例入口建立项目，PF-1 新增空白画布与生成实例 ID 的完整验收。

该验收复现了默认曲线仍显示固定 `P1/V1/V2`、自定义编号没有默认概览曲线的问题；源码核对还发现设备结果温度读取项目概览温度。PF-1 修复默认曲线按实际设备/通路绑定、历史概览按冻结项目解释、设备温度按自身出口读取，并移除空白项目预置的示例控制引用；另修复含连字符的组合公开端口被前端导入检查误拒绝的问题。实现和最终执行结果登记在 [首批验收](PLATFORM_AUTHORING_ACCEPTANCE.md)。

RF-0 已完成[独立实验验证](REFRIGERATION_EXTENSION_DESIGN.md)，RF-1 已交付[正式合同、SDK 与编译/Worker 接口](REFRIGERATION_MODULE_CONTRACT.md)；RF-2/RF-3 已接通[正式节流模块运行与验证发布](REFRIGERATION_MODULE_EXECUTION.md)。RF-4 已完成[项目闭环](REFRIGERATION_PROJECT_ACCEPTANCE.md)，PF-2 [全阶段验收](PLATFORM_EXTENSION_ACCEPTANCE.md)已通过；热耦合液体侧作者设备、水侧储热及机组启停保持原范围。
