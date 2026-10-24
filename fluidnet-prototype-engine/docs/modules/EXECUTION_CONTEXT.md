# SDK 0.3.0：时间、阶段与执行身份

S3 增加只读的 `ctx.time_s`、`ctx.phase` 和 `ctx.execution`，不改变四个生命周期方法的参数。新合同可声明 SDK `0.3.0` 和能力 `context.execution.v1`；旧 SDK/合同继续可用，不改写种子模块或已保存源码。

## 1. 阶段与时间

`ctx.time_s` 和 `ctx.phase` 分别是 `ctx.execution.time_s/phase` 的便捷入口。时间单位为仿真秒，不是墙钟时间。

| phase | time_s | 端口 / 通路来源 | state_data |
| --- | --- | --- | --- |
| `initialize` | 新执行会话的起点 0 | 均不可用 | `initial`：传给初始化的状态 |
| `evaluate` | 本次请求的目标时间，可重复或重新试算 | 通常为试算端口；台架收敛后复核调用明确标为 converged；通路结果不可用 | `input_copy`：输入状态的副本，不接受其写入 |
| `commit_step` | 本次候选子步的结束时间 | 实际提供的收敛端口/通路；缺少映射时不可用 | `candidate`：上一次模块状态的工作副本 |
| `finalize` | 最近一次成功模块提交的时间；只有初始化时为 0，初始化未成功时可为 None | 均不可用，不返回最后试算的端口作为已接受值 | `module_committed`；初始化未成功时为 `initial` |
| `manual` | None | 来源未由宿主标定 | `unavailable` |

`manual` 是旧代码直接构造引擎 `ModuleContext` 时的兼容默认值；正常生命周期由宿主设置。SDK 的 Protocol 仍不应直接实例化。

`execution.port_data` 为 `unavailable/trial/converged`，`channel_data` 为 `unavailable/converged`。即使旧 `ctx.channel(name)` 回退返回零对象，`unavailable` 也不代表已有零流解。作者还应检查映射中是否存在声明名称，并检查具体物理量的 None。数据来源标记描述提供方的语义，不替代物理收敛校验。

`commit_step` 收到收敛量不等于整个子步已经接受。状态和输入映射的原有可变性、提交顺序继续沿用；S3 只冻结元数据对象，没有增加输入深度冻结或状态事务。

## 2. ExecutionInfo 字段

| 字段 | 语义 |
| --- | --- |
| `phase`, `time_s` | 上述回调阶段和仿真时间 |
| `run_id` | 模块执行会话标识；标准网络路径的同组实例/分片共享，创建新会话时重新生成；它不是 API 运行档案的 run_id |
| `instance_id` | 回调所属实际实例；单 Worker 和批量 Worker 均使用实例 ID，不借用模块定义 ID |
| `request_id` | 本次回调请求标识；普通宿主调用逐次生成，重放显式元数据可保留原值 |
| `step_id` | 本次求解尝试的标识；同一次网络求解的残差、分块/串联处理、物性外循环和对应提交共享；重新试算会生成新值，即使目标时间相同。initialize/finalize 不属于某次试算，始终为 None |
| `iteration_id` | evaluate 请求原有的水力迭代编号；其他回调为 None。物性外循环中可能重置，不能当作全局请求身份 |
| `dt_s` | commit_step 的正子步长度；其他回调为 None |
| `accepted_time_s` | 协调者最近完成的接受边界时间；未知或初始边界尚未建立时为 None，不是当前回调已经接受的回执 |
| `port_data`, `channel_data`, `state_data` | 上表的数据来源 |

普通宿主标识使用不透明 UUID 字符串。它们用于追踪关联，不进入设备物理公式或纯函数缓存键。相同参数、输入状态和目标时间的纯关系应保持一致，即使请求标识不同。

独立直接回调、手写 RPC 或手工上下文没有协调者提供完整身份时，step_id/accepted_time_s 等可为 None。原始 RPC 的 run_id 由调用方提供；调用方应保持同一会话的身份一致。S3 没有请求去重、修订冲突或幂等接受协议，重复提交仍按旧执行路径调用；这些属于 T 组。

## 3. 接受边界与失败

动态会话在初始帧建立后记录接受时间 0；在现有 `_accept` 完成后推进该时间。独立验证台在帧检查通过、加入历史后记录接受时间。单次直接求解和直接 Worker 调用没有完整会话协调者时不凭空生成接受回执。

试算期间的 `accepted_time_s` 保持上一个边界。候选提交内仍读取上一个接受时间，提交结束本身不会推进它。丢弃一次试算后再次求解，即使时间相同也具有不同 step_id；若最终采用先前保存的求解结果，提交恢复那份结果的 step_id，避免关联到最后一次被丢弃的探测。

**水位标记不提供状态快照或回滚。** 当前两个模块顺序提交时，若第二个失败，第一个模块的本地状态仍可能已推进，而会话接受时间保持原值。例如 finalize 的模块提交时间为 0.5、accepted_time_s 为 0，准确表示本地提交与全局边界存在差异，不能据此声称已有原子接受。统一候选状态和失败恢复仍待 T0–T4。

finalize 不把最后一次失败/未接受的试算时间当成提交时间，也不暴露其端口值。finalize 仍沿用原有的正常/尽力清理行为，Worker 超时或强制终止时不保证执行该回调。

## 4. 兼容与验证入口

InitializeRequest、EvaluateRequest、CommitStepRequest 增加可选 `context`，缺省不写入序列化 JSON；旧请求仍可加载。phase/time/iteration/dt 由宿主动作及请求本身生成，context 只携带请求/子步身份、接受时间及端口来源，不接受调用方覆盖 phase。模块合同 schema 1/2、默认解释和哈希函数不变。

批量 finalize 按各实例传递元数据；新增身份关联不增加 RPC 次数。没有迁移旧源码、增加物性查询或改变求解容差。协议模型和字段定义可查看生成的 `module-request-context.schema.json`、`module-execution-info.schema.json`。

```powershell
python -m mypy --config-file mypy-sdk.ini
python -m pytest -q tests/test_module_execution.py tests/test_module_execution_network.py
```

未发布的 [timed_valve.py](../../examples/module_sdk/timed_valve.py) 使用当前时间构造纯关系、仅在 commit_step 累计次数。正式模块版本发布仍留到 S4。实际命令、结果和限制见 [S3 实施证据](results/S3.md)。
