# 实时运行命令边界

2026-11-07。`frontend/run-commands.js` 的 `FluidNetRunCommands.create()` 接管实时运行创建、命令回执确认、增量轮询和全程曲线读取。`engine-client.js` 保留原来的 `command`、`confirmedCommand`、`loadOverview`、`overview` 公开入口，以惰性工厂组装所需依赖。普通稳态计算、旧回放和模块验证台仍走原路径。

## 依赖与所有权

新工厂接收工作区访问器、HTTP 请求、`project-run-state`、参数身份计算、规范化／快照组装、帧转换和 UI 通知回调。HTTP 鉴权、模块目录与单位转换没有在工厂中复制。工程及运行对象继续由现有状态层持有，工厂仅持有在途请求和抽稀曲线缓存。

`index.html` 在 `engine-client.js` 前加载 `run-commands.js`。工厂不会在模块加载时读工作区、访问 DOM 或启动计时器。命令轮询维持原来的最多 200 次、每次 50 ms 等待，不重发已提交命令；参数应用依然以匹配的 applied 事件为确认依据。

## 异步边界

- 轮询按运行对象合并：并发 tick 和命令确认共用同一个在途请求。新运行即使复用旧运行 ID，也不被旧对象的在途请求阻塞。
- 命令收到 applied 事件后等待帧轮询结束，再向调用方返回回执；旧实现以 Set 标识在途请求时会直接返回，现在会等待同一 Promise。参数是否进入本地已应用状态，仍由现有参数事务决定。
- 每个请求阶段核对原工程和运行对象。旧记录、旧帧、迟到的 command/event 响应不能应用到替换后的运行；过期连接错误也不覆盖当前提示。
- 全程曲线按运行对象合并请求；成功和失败两条路径均检查归属。服务端过期时只记录当前运行的 overview 错误，原窗口历史仍保留。
- 创建运行保持单请求锁，规范化前后继续核对参数身份；取消信号已触发时，即使模拟传输仍返回成功，也不会接入迟到运行。这里没有新增后端取消协议，不把本地取消等同于服务端已经停止。
- 对已结束运行点击停止，只关闭本地任务状态，继续保留档案 ID、历史帧和未应用草稿。后端返回 `RUN_ALREADY_FINISHED` 时先按原流程同步终态，再处理本地停止或下一次运行。

普通采样帧仍调用 `refresh`；运行状态改变调用工厂注入的 `render`。engine-client 通过 `ui.refreshRun || ui.render` 接线，工作台提供局部生命周期更新，其他页面沿用原刷新。帧合并、完整／趋势帧选择、终态、诊断、参数修订和 accepted 状态规则都继续使用 `project-run-state.js`，没有修改数值求解或后端接受事务。

## 验证

`completed-run-control.test.mjs` 已从源码切片改为直接构造公开工厂。`run-commands.test.mjs` 验证共享轮询、同 ID 新对象隔离、迟到错误、命令等待在途帧、回执／事件归属、拒绝与有界确认、overview 回退、新运行单请求与取消信号、规范化期间编辑拒绝。测试通过注入延迟和请求确定地覆盖竞态，不等待真实计时器。

```powershell
node --test tests/completed-run-control.test.mjs tests/run-commands.test.mjs tests/project-run-state.test.mjs tests/parameter-batch.test.mjs tests/project-overview.test.mjs tests/run-archive-cache.test.mjs
```

本组 49 项通过；新实现与 engine-client 语法检查通过。共享测试夹具为 `tests/run-commands-fixture.mjs`。修改的参数批量和运行状态测试仅补新工厂的加载；原行为断言保留。浏览器工程流程由本轮总验收统一执行，避免并行求解干扰性能测量。
