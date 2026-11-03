# 架构整理验收与迁移记录

代码原始基线：`7424576`；架构文档检查点：`676fdcd`。本轮工作分支 `codex/architecture-refactor`，执行计划见 [ARCHITECTURE_REFACTOR_PLAN.md](ARCHITECTURE_REFACTOR_PLAN.md)。

## AR-0 基线

- Python 3.11.0；Node 24.15.0；Edge 157.0.4341.36。核心依赖为 FastAPI 0.137.1、Pydantic 2.13.4、NumPy 2.3.2、SciPy 1.17.1、CoolProp 8.0.0，测试使用 pytest 8.4.1。
- 原始基线 [CI](https://github.com/kongbaifan/fluidnet/actions/runs/41608687342) 的前端两次在 `browser-module-assertions.mjs:47` 等待保存响应超时；[模块 CI](https://github.com/kongbaifan/fluidnet/actions/runs/41608687518) 通过。原始后端与 SDK CI 最终通过，原始前端失败已由 AR-0 独立修复。
- 本地原始基线：计划 F/S 后端专项 233 项通过，耗时 374.95 秒；UI 32 项通过；语法、ruff、mypy、合同与扩展示例一致性检查通过。
- 数值快照：普通流体、理想热系统、冷库 A、集总制冷站、制冷液体热耦合及多画布机房，各记录 0、5、10 秒共三帧。输入摘要、模块版本与双哈希、公开变量、守恒指标、诊断代码和参数修订保存在 [baseline-numerics.json](architecture-refactor/baseline-numerics.json)。采集脚本为 [architecture_snapshot.py](../scripts/architecture_snapshot.py)。

### 原有保存失败的根因与修复

连续创建、保存并重载较大的作者模块项目后，自动载入工作区会先备份本地副本；浏览器存储额度不足时备份失败。原流程因此中止服务初始化，后续计算仍可调用，但保存一直被本地 `ready=false` 拒绝，甚至不会发送 HTTP 请求。原始 CI 与本地均复现。

修复保持“备份失败就不替换本地草稿”：服务仍完成连接，保留客户端原来的工作区及项目修订，并显示备份失败提示。随后保存继续携带原修订，远端有并发修改时仍返回 409；不采用未载入的远端修订。其他合同或载入错误继续拒绝。

新增三个服务行为测试覆盖同修订保存、并发修订保护和非备份错误。修复后 UI 35 项通过，完整 `browser-module-workflow.mjs` 通过；项目工作流、旧档案迁移、工作区、运行控制、跨页管网和三页标准机房六个浏览器流程均通过；失败诊断新增保存提示，便于辨别无请求和 HTTP 失败。

本地原始日志位于 `artifacts/architecture-refactor/`，该目录不纳入 Git。此处仅记录实际完成项，不以历史全量数字替代本轮检查。

## 迁移清单

| 范围 | 原入口／调用者 | 目标入口 | 行为证据 | 状态 |
| --- | --- | --- | --- | --- |
| manifest、参数、显示单位 | studio: manifestFields / manifestParamSpecs / manifestParamDefaults；engine: manifestParamDef / moduleFromManifest / testParameters / runDesign | project-model | 项目交换、参数类型、作者模块验证 | AR-1 已迁移 |
| 项目文档、导入与升级 | services: projectDocument / exchangeDocument / upgradeDocument | project-model；服务层保留 HTTP 与固定版本准备 | project-exchange / browser-workflows / browser-refrigeration-projects | AR-1 已迁移 |
| 项目替换与恢复 | studio: restoreWorkspace / replaceState / import；workflows: applyDocument | project-state | 工作区修订、并发冲突、失败草稿、导入替换 | AR-2 已迁移 |
| 参数草稿和应用 | studio: 参数输入／库值／设备型号应用；engine: applyParameters / command | project-state | 批量参数、运行应用、草稿保存及撤销 | AR-2 已迁移 |
| 拓扑编辑 | studio: 插入／删除／连接／移页／复制与 remember/undo；links 工具 | project-state + project-links | 跨页、删除、撤销重做与重算 | AR-2 已迁移 |
| 当前与历史运行 | engine: applyRow / command / pollLive / confirmArchiveCache；studio: receiveArchives / showArchive | project-run-state | 迟到响应、增量帧、档案确认与历史 | AR-3 已迁移 |
| 公共参数、控制与资源 | SimulationSession: 参数命令、PID／脚本、检查点、close | SessionBase + 物理钩子 | 控制、事务、困液、停止与部分初始化失败 | AR-4 已迁移 |
| 热／制冷会话继承 | ThermalSession / ColdStoreSession / StationSession / CoupledStationSession | 非流体公共基类，保留域内步进 | 五域基线与失败回滚 | AR-5 已迁移 |
| 调度与预览 | jobs 的会话访问；API `_control()` 与 `scripts.pending` | RunSession 协议及显式预览方法 | 后台运行、控制预览及类型门禁 | AR-6 已迁移 |

## 后续包记录

AR-7 完整门禁见文末及 PR #8。各包完成后在此添加提交、实际检查和剩余问题，并同步迁移清单与计划进度。

## AR-1 项目转换

新增纯转换模块 `project-model.js`，集中 manifest、显示单位、参数默认值、项目文档、规范导入和升级转换。服务层保留 HTTP 校验与固定版本准备；现有脚本加载及测试宿主同步加载新模块。

验证：38 项 UI 单元测试；项目工作流、制冷项目导入／升级／回退、完整模块作者流程、参数整批写入四个浏览器流程通过；语法检查通过。新增单位测试覆盖温度与温差、开度、功率、体积流量及非数值参数。

## AR-2 项目编辑状态

新增 `project-state.js`：集中项目文档合并、工作区替换回滚、参数草稿／确认值、设备与画布插入、跨页连接操作和画布快照恢复。节点写入拒绝被替换的对象；撤销记录绑定项目 ID；导入失败同时恢复参数定义缓存。初始化／规范化阶段的新对象构造仍由原有工厂负责，其他编辑器的模块草稿不在本包迁移范围。

验证：45 项 UI 测试；跨页管网、项目工作流、工作区、参数整批写入、热耦合建模、旧档案迁移和多画布机房七个浏览器流程通过。新增测试覆盖待应用草稿独立、批量参数与自定义变量、旧引用拒绝、失败连接保留、跨项目撤销拒绝、失败替换回滚与其他项目草稿保护。

## AR-3 运行与历史状态

新增 `project-run-state.js`，集中结果归属、帧合并、结果过期标识、归档缓存确认与历史记录构造。异步回调绑定项目对象及运行对象，不仅比较可复用的 ID；轮询不会将旧结果重新标记为当前配置；保存参数回执只在对应配置仍一致时推进结果标识。旧档案列表不会停止请求发出后新建的运行。

验证：51 项 UI 测试，含一个真实适配器延迟响应测试；运行控制、持续运行、参数批次、旧档案迁移、工作区和跨页管网六个浏览器流程通过。

## AR-4 公共会话基础

提取 `SessionBase`：参数路由、PID／脚本所有权、参数修订、公共控制检查点和关闭流程；流体实例接入基类，困液开阀检查、湿空气校验、支路开闭与热输入副作用保留为流体钩子。参数路由显式遍历完整目标集；当前公开组合合同仍是一对一映射，未开放新合同能力。

验证：113 项控制／状态／事务回归、9 项公共边界与组合测试、19 项后台运行测试通过；六个代表项目的输入身份、模块哈希、公开变量和守恒指标与基线一致。新增测试覆盖非法末项不产生部分写入、两个公开参数到真实 Worker 的生效及设备关闭异常时控制执行器仍恰好关闭一次。ruff 与现有 mypy 通过。

## AR-5 热／制冷会话迁移

`ThermalSession` 直接继承公共基类；冷库、集总制冷站与热耦合保留自己的热步进及接受事务。删除为继承而补的 `trapped` 占位状态。液体联算通过自身参数钩子维护内置阀门支路开闭并回滚，未将该职责放入公共层。

验证：115 项热／制冷／控制／接受回归通过；公共边界四项单独复验通过，其中新增理想热系统在没有流体支路／储量占位字段时的控制运行；六例数值与模块身份一致。控制脚本、冷库 A、制冷站和液体作者四个浏览器流程通过，覆盖版本、报告、导入及重启复算。ruff、mypy 与 90 项生成合同一致性通过。

## AR-6 显式会话接口与类型门禁

补齐 `RunSession` 的帧、报告变量、命令、快照和预览接口，调度使用公开报告变量属性。API 改调用 `preview_control`，不再读取会话的私有控制方法和待接受提案；预览返回分离副本，修改返回值不会污染待接受状态。

公共基类、网络／资源协议、控制检查点和工厂接口已注解；`mypy-session.ini` 对两个接口文件启用 strict，允许调用尚未注解的既有编译器／Worker 函数，并以 silent 模式分析其导入类型，不扩大旧物理模块的检查范围。此门禁已加入 CI。

验证：49 项公共边界／控制／事务／运行测试通过；调度公开属性修改后，26 项历史和运行测试复验通过；控制脚本浏览器通过。新增提案副本及未知脚本无副作用测试。严格类型、全引擎现有 mypy、ruff 与 90 个合同文件一致性通过。

## AR-7 完整验收门禁

实现代码基线：`8563631`，评审与完整检查入口：[PR #8](https://github.com/kongbaifan/fluidnet/pull/8)、[CI 检查](https://github.com/kongbaifan/fluidnet/pull/8/checks)。对应代码提交下的后端覆盖率、全量浏览器链、SDK 与模块检查共同决定完整验收结论；本地定向通过不替代完整 CI。

最终核对补齐了运行中 PID 编辑的本地确认：同一项目的控制配置写入按顺序确认，再更新本地配置和结果标识；其他未确认的配置变更仍保持结果过期。新增浏览器断言覆盖目标、手动模式、输出值与结果配置标识一致，PID 与房间控制工作流通过。冻结概览绑定复用已有值，避免在每次帧合并时重新计算。

本地完整检查范围：前端语法与 52 项单元测试、全引擎 ruff／mypy、公共会话 strict mypy、SDK strict mypy、90 个合同与扩展示例一致性、六例数值对照、十张图的实际渲染及文档链接。原始日志位于 `artifacts/architecture-refactor/`。完整 CI 的运行 ID、结论及覆盖率记录在 PR 的验收说明，避免把未完成的远端检查提前记为通过。

所有迁移清单项已有实现与定向证据；本轮没有更改外部数据合同、物理算法或已取消的产品专项。后续功能开发继续以当前图集及各模型的适用范围为准。

### 完整 CI 发现的启动保存竞态

首轮完整 [CI 41623440184](https://github.com/kongbaifan/fluidnet/actions/runs/41623440184) 在加热器流程的首次保存等待失败。延迟目录响应后，本地稳定复现“工作区尚未连接”。保存现在等待初始化完成后再捕获当前工作区快照，独立锁覆盖等待及发送阶段，连续点击只提交一次。加热器测试增加受控启动延迟、重复点击及服务端完整目录快照检查；修复后加热器全流程和工作区 409／507／重启恢复复验通过。完整 CI 随 `8563631` 及配套文档重新执行。

### 排队控制写入的运行归属

最终异步边界核对补充了排队场景：第一项控制命令等待期间替换运行，第二项旧命令不得发给新运行。新适配器测试在修复前观测到两次请求；写入改为入队时绑定运行后，仅发出原有请求，两项旧操作均以取消响应结束，新运行和本地控制值保持不变。前端单元测试现为 52 项通过。
