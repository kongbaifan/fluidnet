# 参数应用与工作区规范化边界

2026-11-07。继前两轮功能拆分后，本包迁出设备参数确认和旧工作区规范化，保留项目数据结构、运行命令、物理单位以及服务器接受事务。实现仍使用普通脚本与显式依赖注入。

## 设备参数应用

`frontend/device-application.js` 提供 `FluidNetDeviceApplication.create()`。实例暴露 `capture(node, values, bank)`、`apply(owner, node, application)` 和 `isPending(node)`；`studio.js` 的旧函数名仅作适配。

预览记录原项目／运行票据、当前已应用参数、性能资料来源、型号草稿身份和待确认值。确认前核对票据、设备对象和原值，并通过实例级锁拒绝重复提交。运行中写入仍调用既有引擎 `applyParameters`，等待其完整确认；离线应用仍先记录撤销，再通过 `project-state` 写入。

确认后的参数、性能来源、型号及自定义变量遵循原语义。请求等待期间用户输入的新参数／自定义值／型号草稿保留，失败不改已应用值或来源；锁在成功或失败后都释放。没有把界面参数确认与物理模块的 prepare／promote 接受点合并。

依赖明确为当前状态访问器、项目与运行状态操作、模块／变量适配、引擎参数应用入口、性能来源服务及撤销／展示回调。不读取 DOM，不持有第二份项目状态。

## 工作区规范化

`frontend/workspace-normalization.js` 提供 `FluidNetWorkspaceNormalization.create()`，其公开入口包括 `normalize(data)`、`backfillBuiltinParams(data)`、`normalizeGroups(data)` 和 `normalizePythonSource(module)`。调用方注入参数定义表、模板生成器、模块变量适配、项目快照／控制规范化及连接归位函数。

该模块在**传入的数据对象**上进行补全，并根据 manifest 更新注入的参数定义表；没有文件、HTTP、浏览器存储或 DOM 操作，也不持有当前工作区。`studio.js` 仅负责组装依赖、传入当前状态和调整失效的分类选择。恢复失败时，工作区与参数定义表的回滚仍由已存在的 `workspace-storage` 负责。

保留的规则包括：

- 缺失运行 history／events／values、页缩放与平移、图表配置、模块分组和 Python 参数默认值的兼容补全。
- 仅识别已知旧模板的源码迁移；手改代码和 Python 模块包保持原内容。
- 仅修复明确的 `g/kg_da` 与默认值 `8` 的旧含湿量指纹；合法的规范单位值不再换算。
- 冻结工程的模块快照不会跟随库中旧湿度修复；非法未知数据留给正常校验，不能静默替换成合法值。
- 项目快照、控制规范化、实例变量检查和连接归位保留原调用顺序；同一已规范化工作区再次调用保持幂等。

新脚本需在 `studio.js` 前加载；工厂间没有新增全局初始化顺序依赖。

## 定向验证

```powershell
node --check frontend/device-application.js
node --check frontend/workspace-normalization.js
node --check frontend/studio.js
node --test tests/device-application.test.mjs tests/source-humidity-migration.test.mjs tests/workspace-normalization.test.mjs
```

本包实际结果为 **21 项通过**：原 11 项断言全部保留；增加过期设备／预览拒绝、型号与自定义草稿并发、离线撤销顺序、失败后解锁、旧型号／库值修复与冻结快照保护，以及完整工作区规范化、幂等、控制变量别名、缺失历史、模板代码和分类兼容。

两个旧测试文件不再切取 `studio.js` 源码；均通过工厂接口调用。同样复用实际 `engine-client`、`run-commands` 和项目状态模块检验确认链路。这里的 Node 结果不冒充真实浏览器工程验收；浏览器集成由本轮统一验收记录登记。
