# 架构后续交付与验收

日期：2026-11-07。起点为工程画布与第一轮功能拆分提交 `c7410f6`。本轮已完成约定的模型分层、Runner 接口、设备注册试点、第二轮前端拆分和生成物／文档治理。当前代码导航从 [文档入口](README.md) 进入。

## 工作包与结果

| 工作包 | 实现与结果 | 提交 |
| --- | --- | --- |
| 先前画布与第一轮拆分收口 | 工程图符、路由、观察量、视图、工作台交互、设备浮窗、模块服务、动作路由及浏览器分组 | `c7410f6` |
| 模型分层 | 127 类分入 base/module/protocol/domain/run/module_testing/http，旧 `models.py` 保留兼容导入；内部调用改为真实依赖层 | `ddbaf2d` |
| Runner 接口 | InProcessModuleRunner、WorkerProcess、batch.Handle 结构符合 ModuleRunner；集中事务使用同一类型边界，Handle 显式携带 definition | `5da0c39` |
| 设备注册试点 | 五类储量设备定义工厂与展示配置登记；目录、独立 HTTP 元数据接口、前端模块库和画布已有真实调用 | `606ba8b` |
| 第二轮前端拆分 | 作者视图、曲线／运行记录视图、保存／草稿／恢复独立工厂；相关测试改用公开接口 | `529029f` |
| 生成物与文档治理 | 13 个生成器统一只读入口、JSON 语义差异摘要、CI 上传、定向折叠、文档索引和验收模板 | 本记录同批提交 |

`models.py` 的旧 127 类／函数实现体逐一做 AST 比对，全部一致；拆分前后的 Schema、默认值、序列化遗漏与历史导入身份有独立守卫。Worker 导入不再加载 HTTP／Project 聚合层。分层时 111 份合同保持零语义差异。

设备展示端点属于独立新增功能：OpenAPI 增加 `/api/v1/catalog/presentation` 和两个 DTO schema，只有 124 行新增；去掉这三项后与基线结构完全相等，其余 110 个合同文件未改。五类设备的定义哈希保持不变，展示配置不进入模块物理定义。

接受事务继续按 prepare → validate → promote → synchronize 执行，提升阶段没有新增 RPC 或用户代码调用。数值求解器的方程、Jacobian、温启动、容差与计数器未修改；本轮在相关文件中的改动为模型导入迁移。

保存工厂除了迁移既有草稿备份、配额降级及回滚逻辑，还明确检查回执对应的工作区对象和编辑修订。保存期间的新编辑仍保留 dirty；工作区已替换时，晚到的成功或失败不能修改新工作区或声称其已保存。恢复失败会回滚工作区和参数定义表。

## 验证约定

按用户要求，仅执行影响范围内的测试和静态检查，**没有运行全量 pytest、完整浏览器链或新的全量覆盖率统计**。远端 GitHub Actions 本轮未触发；CI 配置检查与本地结果不等于远端全量通过。以下各组含部分重叠，不相加为独立测试总数。

| 范围 | 实际执行入口 | 结果 |
| --- | --- | --- |
| 分层初次兼容 | 模型／冻结 SDK／Worker 启动／运行合同专项，见 [分层记录](MODEL_LAYERING.md) | 82 项通过，127 类型 Schema 保持；该组为分层阶段证据 |
| Runner、集中事务、执行网络 | `python -m pytest tests/test_runner_protocol.py tests/test_module_transactions.py tests/test_module_execution.py tests/test_module_execution_network.py -q` | 54 passed；含三种执行形态的接受／丢弃／重试与故障边界 |
| 设备与分层最终集成 | `python -m pytest tests/test_device_registry.py tests/test_model_layering.py -q` | 11 passed |
| 第二轮前端 | 作者视图、运行视图、workspace-storage、draft-cache、project-model、module-service、run-archive-cache、action-router 八个 Node 文件 | 47 passed |
| 设备元数据前端 | catalog-presentation、canvas-symbols、project-model、module-service 四个 Node 文件 | 31 passed |
| 生成物审查器 | `python -m pytest tests/test_generated_artifacts.py -q` | 8 passed |
| 语法与静态检查 | `npm run check`；`python -m ruff check backend tests scripts modules examples/control_templates` | 全部通过 |
| 后端类型 | `python -m mypy`；`mypy-session.ini`；`mypy-runner.ini` | 分别 150、2、3 文件通过 |
| 生成物一致性 | 12 个非合同生成器分别经统一 `--verify --group`；独立 `generate_contracts.py --check` | 全部通过；111 份合同一致，便携示例未重写 |
| 清单与配置 | `generated_artifacts.py --check`；`browser-groups.mjs --check`；YAML解析；`git diff --check` | 13 生成器；82 浏览器调用／57 文件／9 组／3 helpers；全部通过 |
| 生成差异导航 | `generated_artifacts.py --base c7410f6 --json` | 仅 OpenAPI 一个文件、3 处语义新增 |

`npm run test:ui:frontend-second` 已追加设备展示的 6 项独立测试，用于后续一次执行两类边界；上表保留两个实际执行时的结果，不因脚本清单后来扩大而改写通过数量。新增测试均接入现有主检查入口，Runner 严格类型门及 13 生成器只读校验已接入 CI。

四条真实浏览器流程均已退出成功，页面异常为空：

| 流程 | 验证内容 |
| --- | --- |
| `browser-module-workflow.mjs` | 四类模板契约、验证、发布、实际求解、重载复算、断言失败及源码定位 |
| `browser-workspace.mjs` | 409 冲突、507 写入失败与重试、服务重启中断归档、历史曲线、ZIP 备份与修订恢复 |
| `browser-continuous.mjs` | 无固定终点的连续运行、全程抽稀与停止后 cancelled；本次 23 帧／2.2 s，overview 22 帧 |
| `browser-module-catalog.mjs` | 五类登记图标、八个原有参考模块及文档弹窗 |

浏览器证据使用各原脚本的 `artifacts/` 输出目录。根汇总额外保留 `artifacts/architecture-followup/frontend-check.log` 和 `generated-review.json`，这些运行证据不作为产品输入入库。

## 已明确的边界

- ES Module／import map 已评估，本轮继续用普通脚本和显式依赖注入，未引入 bundler。全局入口、全页重绘和剩余展示动作仍可继续整理；当前工作包没有宣称整个前端已模块化完成。
- 源码切片已清理画布端口、本地草稿和工作区恢复相关测试。剩余参数接受、运行命令和旧湿度迁移测试需随各自职责迁移，未借此重写接受事务。
- 描述表先覆盖五类储量设备的定义与展示。其他设备目录及物理分派保留原路径，工质和连接限制仍以模型真实支持为准；没有承诺新增任意设备只改一个文件。
- Runner 协议统一逐实例接受边界；批量 Worker 的初始化、求值与资源生命周期仍由分片管理。不做 Worker 池化。
- 生成 JSON 仍保留便携交付和冻结来源价值，recipe 和模块源码可直接审查。本轮改善审查入口，不删除所有历史生成文件。
- 培训剧本、评分、外部部署、现场验证不在本轮范围。
