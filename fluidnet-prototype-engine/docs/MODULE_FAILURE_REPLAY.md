# 模块失败输入与独立复现

2026-11-05。模块失败复现使用当时的冻结源码、参数、工质、回调前受管理状态、端口、通路和执行身份，在新的独立Worker执行一次相同阶段。它不会重算整张网络，也不推进原运行或覆盖发布版本。

## 输入与执行

`runtime._invoke`在执行模块代码之前复制真实输入，在回调异常或主动error诊断时形成`format_version=1`、`capture_kind=callback_input`快照。失败代码即使修改参数、端口或状态，快照仍使用调用前值。`execution`保留phase、time_s、dt_s、iteration_id、request_id、step_id、accepted_time_s及端口/通路来源标记。

支持initialize、evaluate、thermal、observe、jacobian、commit_step；制冷节流evaluate保留类型化流股输入。后续阶段不会重新执行initialize，以免清空当时的状态。commit_step只在一次性Worker中求候选，不向原运行提交。

快照最多2MiB，状态沿用64KiB和深度/容器上限。超限、无效或无法序列化的输入不给出可执行快照，原失败诊断继续返回。源码加载失败、Worker超时、全网不收敛、候选协议验证错误及finalize没有此类完整回调快照时，不用最后接受帧代替。

此功能复现公共回调输入，不恢复用户代码的self属性历史、全局可变数据、随机源、外部文件或网络状态；这些因素会导致失败未重现。`matched_failure=false`明确保留这种差异，不把“执行完成”当成修复成功或整网验证通过。

## API

| 端点 | 请求和结果 |
| --- | --- |
| `POST /api/v1/modules/replay` | `ModuleReplayRequest`，`{"replay":快照}`。200返回`ModuleReplayResponse`；无效/旧格式/哈希不符/不支持阶段返回422 |
| `GET /api/v1/runs/{run_id}/module-failure` | `ModuleFailureResponse`，包含run_id、replay或null、原末帧diagnostics；原档案不存在返回404 |

复现响应包含status（failed/completed）、matched_failure、execution、源码/定义哈希、diagnostics和result（variables、state、relations、heat_w、derivatives及可选refrigeration）。matched_failure按错误码、消息、源码文件/行和phase比较；回调失败时不把半成品输出当作有效结果。

进入Worker前重新验证冻结定义和两项哈希、阶段能力、dt及JSON上限。Worker使用现有进程/超时/回收机制；不调用原运行的initialize/finalize，不发布模块、修改项目或产生新项目运行记录。读取快照遵守已有read权限，POST执行遵守已有control权限。

同步与后台项目失败都只在终态档案保存一份快照。常规运行详情和每帧历史不重复携带；服务重启后通过专门端点读取。异常包装保留原始cause链，查询它寻找失败回调；不会从接受帧重建一个虚构的失败输入。

发布/独立验证失败的HTTP错误仍保留现有`detail.replay`，新增字段向后兼容导出消费方。旧导出没有版本和调用前捕获标记，不能证明输入未被失败代码修改，因此精确复现接口明确拒绝旧格式。

## 验证

`tests/test_module_replay.py`覆盖六阶段实际回调的输入、失败前状态、失败候选与接受时刻区别、独立Worker、原运行不变、同步/后台归档与重启、冻结源码、哈希篡改/旧格式/超大状态拒绝、制冷类型化流股及主动error诊断。与现有`test_module_diagnostics.py`、`test_module_transactions.py`合并定向验证35项通过（37.21s），检验原诊断与全步接受约束。未运行全量pytest或全量浏览器测试。
