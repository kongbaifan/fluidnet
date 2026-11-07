# 前端功能拆分：工作台、作者界面、运行视图与保存边界

当前状态（2026-11-07）：失败复现现已直接导出 ES Module，最后一个 `module-replay-adapter.js` 已移除。原有本地简化界面保留；本页末尾 AC-3 段落中的兼容例外与两项失败是修复前记录，已由[回放修复](MODULE_FAILURE_REPLAY.md#前端请求归属与模块入口)收尾。

更新日期：2026-11-07。第一轮（2026-11-06）在工程画布基础上提取工作台、浮窗、模块服务与动作分派；第二轮继续提取作者视图、运行视图与工作区保存／恢复。沿用原生 JavaScript 及依赖注入，ES Module 评估结论见下文。培训暂缓；后端模型分层独立验收。

## 已实施的边界

| 功能 | 独立入口 | 归属 |
| --- | --- | --- |
| 工作台交互 | `workspace-interactions.js` / `FluidNetWorkspaceInteractions.create()` | 单一指针捕获、节点拖动、端口拖线、Shift多选/框选、平移、模块拖放、工作台快捷键；作者端口和浮窗手势按域委托 |
| 设备浮窗 | `device-windows.js` / `FluidNetDeviceWindows.create()` | 打开关闭、前后顺序、置顶、停靠、最小化/最大化、页签、拖动缩放、项目隔离的位置保存、浮层渲染 |
| 模块服务 | `module-service.js` / `createModuleService()` | 定义构造、冻结插入、校验、设计、发布、版本载入、设备组宿主测试上下文 |
| 动作分派 | `action-router.js` / `FluidNetActionRouter.create()` | 精确动作优先、功能前缀分派、重复注册拒绝、未知动作回落、同步/异步错误统一报告 |

`studio.js`负责组装这些入口、公共页面/对话框和尚未迁出的功能，保留少量旧函数名薄适配。`engine-client.js`继续提供原公开方法名，模块方法委托module-service，运行传输和参数事务保留原位置。调用者无需改成另一套engine API。

工作台通过明确的canvas/selection/editor/windows/charts/shell接口协作；浮窗只接收窗口列表、位置存储、DOM容器、内容和反馈接口；模块服务接收模块/验证台访问器、请求和规范转换回调。没有向新模块传入整个studio命名空间，也没有建立第二份项目或运行状态。

## 保持的行为

- 项目JSON、模块发布版本/双哈希、显示单位、模型参数、库值和草稿来源合同保持原语义。
- 设备窗口只改变展示状态。参数应用的身份票据、并发锁、后端回执、晚到草稿和性能资料提交仍由原事务入口管理。
- 模块发布仍验证提交的候选定义；保存等待期间的新草稿保留，宿主工况和冻结项目定义不被模块库新版本覆盖。
- 运行轮询、物理求解、接受事务、后端DTO和Worker生命周期不在本轮迁移范围。
- 单一手势以项目/画布/实例对象确认归属；同ID对象替换后不能继续写入。浮窗票据独立检查当前项目和窗口对象。
- Esc或pointercancel结束已移动的手势时，保留最后可见几何并登记未保存状态；过期对象不提交。撤销仍能恢复移动前快照。取消尚未完成的接线或框选不产生新连接。
- 动作精确注册优先于前缀，`canvas-tab`不会被画布显示功能吞掉。未迁移的动作继续由现有shell处理。

迁移开始时 `studio.js`为3222行/427930字节，结束时3076行/415298字节；`engine-client.js`从929行/66415字节降至772行/54086字节。文件大小只作记录，验收依据是职责、公开接口和行为，未宣称整个前端已经完全拆分。

## 测试与CI

新增公开接口测试：action-router、workspace-interactions、device-windows、module-service、browser-groups。`canvas-port-access.test.mjs`改为直接调用canvas-symbols的几何接口，不再从studio文本切取函数。几何命中逻辑只有一个实现，画布与测试共用。

第一轮结束时仍有 5 个测试文件依赖源码切片。第二轮已将 draft-cache 和 project-model 中的草稿／恢复测试切换到公开接口；目前剩余 completed-run-control、device-application、source-humidity-migration 三个文件，对应运行命令、参数接受和旧字段迁移，继续随所属功能迁移处理。

浏览器执行由 [统一分组清单](FRONTEND_CI_GROUPS.md) 管理：82次调用、57个可执行文件、9个组，明确豁免3个辅助文件。全部旧命令参数保留，P1/工程画布/前序forward新流程纳入主CI。CI最多并行3组，组内顺序运行；固定跨域smoke始终执行。暂不做按路径省略集成测试。

SDK/后端CI保留原内容，前端required-check名称保留，只有静态/单测和所有浏览器组成功才通过。远端Actions尚未由本轮运行，不能把配置核验当作远端通过。各组45分钟预算仍需首轮远端实测检验。

## 第一轮定向验收

```powershell
npm run test:ui:frontend-boundaries
npm run check
node scripts/browser-groups.mjs --check
node scripts/browser-groups.mjs --matrix
node scripts/browser-groups.mjs --run --case smoke --case open-refrigeration-groups
node scripts/browser-groups.mjs --run --case device-windows
```

相关单测最终99项通过；涵盖新模块公开接口、迁移适配、项目/帧归属、设备参数事务及批量参数、跨页编辑和档案缓存。语法、CI清单、YAML和差异格式检查通过。

本轮分别执行的7个浏览器流程：

| 流程 | 验证内容 |
| --- | --- |
| `browser-module-workflow.mjs` | 四类模板、契约、验证、发布、运行、重载、断言与失败复现 |
| `browser-device-panel.mjs` | 原设备面板调参/应用、页签、保存重载与真实数值响应 |
| `browser-device-windows.mjs` | 拖动/缩放、停靠、置顶、最小化/最大化、关闭重开、离页隐藏、保存重载及Esc结束拖动后的保存 |
| `browser-project-editing.mjs` | 30/100/300分页面项目、Shift选择、框选、跨页、撤销重做、保存/导出和断网草稿恢复 |
| `browser-canvas-symbols.mjs` | 作者端口拖动、图形发布/冻结、旋转接线、库草稿隔离、导入与重载 |
| `browser-smoke.mjs` | 新分组执行器启动真实浏览器，基础水力运行与阀位应用 |
| `browser-open-refrigeration-groups.mjs` | 新执行器覆盖开放组发布、宿主验证、真实公开端口接线、双副本与重载 |

以上浏览器流程页面异常均为空；未执行完整浏览器链或全量pytest。前序画布性能记录保留为对应源码哈希时的测量，不把本轮功能回归当作新的性能承诺。

后端模型分层、Runner 协议和设备元数据注册另列独立工作包；下文登记第二轮前端交付。


## 第二轮功能边界

| 独立入口 | 职责与依赖 | 保留在 shell／服务中的行为 |
| --- | --- | --- |
| `module-editor-view.js` / `FluidNetModuleEditorView.create()` | 模块编辑页面、端口图、变量／库值／型号／代码／契约／通路与验证证据展示；通过访问器读取当前草稿，接收格式化工具及三个导航动作 | 参数编辑、设计结果确认、校验、发布与版本加载继续使用现有事务和 module-service |
| `run-results-view.js` / `FluidNetRunResultsView.create()` | 曲线、运行记录、归档详情与观察变量视图；接收当前运行、历史记录、图表样式与图表注册回调，四个展示动作精确注册 | 运行控制、请求／轮询、历史帧归属、归档存取与报告生成继续使用现有服务 |
| `workspace-storage.js` / `FluidNetWorkspaceStorage.create()` | 草稿持久化、服务端保存锁和回执、配额降级、替换前备份及失败回滚 | `studio.js` 持有工作区和界面状态，通过 read/write 及状态回调提供所有权；数据归一化和工作区替换仍复用 project-model／project-state |

视图不持有第二份工程、模块或运行对象。访问器保证切换当前模块／项目后不会继续展示旧闭包对象。作者变量表只展示启用的通路绑定，发布证据同时匹配定义哈希与源码哈希。运行视图接收已归属的真实帧；数据缺口保持曲线断开，归档观察量不出现当前工程的删除控件。

保存使用一个进行中锁；请求发出后发生新编辑时保留 dirty，保存回执只更新发起请求时的工作区对象。工作区已替换时，旧请求成功或失败均不能覆盖新工作区。配额降级仅裁剪序列化副本；失败保留内存草稿。恢复在备份失败时回滚状态与参数定义表。

第二轮将 17 个作者展示函数、4 个曲线／记录展示函数和工作区存储逻辑移出 `studio.js`；剩余函数名是薄适配。第二轮结束时 studio 为 2866 行／367041 字节（第一轮结束为 3076 行／415298 字节）。这不代表全页 DOM 重绘、所有编辑动作或全局命名空间已全部消除。

## ES Module 评估结论

本轮保留 classic script 加载，暂不切换 `type="module"` 或 import map。当前界面及独立功能测试都通过 window 工厂组装，SDK／引擎调用、初始化回调与浏览器测试依赖该入口；单纯修改 script type 不能消除这些依赖。import map 解决模块路径映射，不负责解除全局注册与初始化顺序。

若后续单独实施，应先将叶子模块改为显式导出，由单一入口负责组合；短期保留兼容外观，迁移测试加载器后再移除 window 名称，并验证页面启动、服务静态 MIME、直接入口、故障提示和恢复流程。该工作与当前功能拆分分开验收，仍无需引入 bundler。本轮三个新文件均已登记 index.html 顺序、语法检查及针对性单测入口，没有加入构建步骤。

## 第二轮定向验收

```powershell
npm run test:ui:frontend-second
npm run check
node scripts/browser-groups.mjs --check
$env:PYTHONPATH='backend'
node tests/browser-module-workflow.mjs
node tests/browser-workspace.mjs
node tests/browser-continuous.mjs
```

2026-11-07：47 项针对性单测通过，包括作者／运行视图的新公开接口测试、保存锁／迟到回执、草稿恢复回滚、配额降级、模块发布草稿隔离、真实档案缓存与动作分派。新增测试接入 `test:ui`；新增脚本接入 `check`。语法检查和浏览器清单校验通过，清单仍为 82 次调用／57 个可执行文件／9 组／3 个辅助文件。

浏览器验证：模块工作流的阻力、泵、换热器、有状态模块四种模板均完成契约编辑、验证、发布、真实求解和重载复算；断言失败与源码定位流程通过。工作区流程验证 409 保存冲突、507 写入失败与重试、重启后的运行中断归档、历史曲线、备份与修订恢复；连续运行流程验证 duration_s=null、持续采样、全程抽稀曲线接口与停止后 cancelled：本次 23 帧／2.2 s、overview 22 帧。三条流程页面异常均为空。

本节仅记录本轮针对性验收，不将第一轮记录或旧 CI 结论视为当前提交的全量通过。

## 后续交互边界交付

2026-11-07 第三轮补齐 `device-application.js`、`workspace-normalization.js` 和 `run-commands.js`。参数确认、运行命令与旧湿度迁移的三个测试都已改用公开工厂，不再按字符串切取 `studio.js` 或 `engine-client.js`。对应实现和回包归属详见[参数与迁移](INTERACTION_BOUNDARIES.md)、[运行命令](RUN_COMMAND_BOUNDARY.md)。

非结构工作台操作、运行生命周期与图表更新由[局部刷新边界](WORKBENCH_LOCAL_REFRESH.md)处理。这里不声称所有页面均无完整渲染；结构变化和切页面仍保留原渲染入口。设备目录从五类试点推广到60类内置模型，前端可见性和图标登记使用后端目录，兼容回退保留。实际测试与两套工程验收从[交付记录](INTERACTION_DELIVERY_ACCEPTANCE.md)查阅。

## AC-2：原生模块加载（2026-11-07）

前述 classic script 是阶段决策。当前 `index.html` 仅加载 `bootstrap.js`，由动态导入 `studio.js` 启动；41个原全局工厂改成命名导出，消费者显式 import。设备选型与性能资料的循环引用保持延迟到调用时读取，由浏览器原生模块链接处理。未增加 bundler 或 import map（相对路径已足够）。

用户原有未提交 `module-replay.js` 不改写，专用 `module-replay-adapter.js` 接收其唯一 legacy 全局。它是已记录的兼容边界，不能宣称整个应用零全局。其他 `FluidNet*` 全局在浏览器中为零。

40份隔离单测加载代码迁移到 Node 原生 `SourceTextModule` 链接器，使用 Node 24.9+ 和 `--experimental-vm-modules`；不切片/改写模块源码。真实浏览器测试通过 dynamic import 使用公开模块。参数批测试先前漏加载选型检查，现真实导入会拒绝不匹配模块版本，断言按生产语义修正。

定向入口 `npm run test:ui:modules` 256项通过。真实浏览器 module-loading 验证45脚本、无重复请求、正确MIME、零FluidNet全局与失败提示；目录60设备、工作区冲突/恢复和作者流程通过。运行控制结果见最终验收。

一次全部前端轻量单测发现用户原有 replay 改动触发2个既有失败（迟到归档导航、旧复现忙状态）；同一测试针对已提交HEAD源码5项全通过。该文件字节哈希保持不变，未为使门禁变绿覆盖用户修改。没有运行全量后端或完整浏览器链。
