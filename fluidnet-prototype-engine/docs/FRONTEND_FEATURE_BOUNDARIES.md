# 前端功能拆分：工作台、浮窗与模块服务

日期：2026-11-06。本轮在已完成工程画布基础上提取功能职责，同时收口测试入口和浏览器CI清单。沿用原生JavaScript及依赖注入，不引入ES Module/import map/bundler，不包含培训或后端模型分层。

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

尚未迁移的运行命令、参数事务、本地草稿、工作区恢复和旧字段迁移测试仍有源码切片；对应5个测试文件列为后续随所属功能迁移的范围，不以本轮为由重新拆开接受事务。

浏览器执行由 [统一分组清单](FRONTEND_CI_GROUPS.md) 管理：82次调用、57个可执行文件、9个组，明确豁免3个辅助文件。全部旧命令参数保留，P1/工程画布/前序forward新流程纳入主CI。CI最多并行3组，组内顺序运行；固定跨域smoke始终执行。暂不做按路径省略集成测试。

SDK/后端CI保留原内容，前端required-check名称保留，只有静态/单测和所有浏览器组成功才通过。远端Actions尚未由本轮运行，不能把配置核验当作远端通过。各组45分钟预算仍需首轮远端实测检验。

## 本轮定向验收

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

后续可分别评估剩余页面/动作职责与ES Module加载迁移；后端模型分层、Runner协议和设备元数据注册另列独立工作包。培训继续暂缓。
