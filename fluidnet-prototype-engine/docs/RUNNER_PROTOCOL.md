# 模块 Runner 的共同接口

2026-11-07。`runner_protocol.ModuleRunner` 为现有三种执行形态建立结构类型约束，`ModuleStepTransaction` 接受 `Mapping[str, ModuleRunner]`，并显式标注请求、候选、返回值和状态。接受步仍由一个父进程事务负责准备、校验、提升和同步。

| 实现 | 共同边界 | 保留的区别 |
| --- | --- | --- |
| `InProcessModuleRunner` | definition、state、修订、执行身份、prepare／commit／synchronize／discard／phase | 实际执行模块回调，保留候选 digest、时间和重试记账 |
| `WorkerProcess` | 同上 | 通过独立进程 JSON RPC 调用，管理该进程生命周期 |
| `batch.Handle` | 同上 | 按实例 ID 使用共享分片；初始化、批量 evaluate 和关闭由 Handle／BatchRunners／Worker 协作完成 |

Handle 现在显式持有创建时的模块 definition，事务校验不再穿透 `worker._definitions`。结构类型门验证三种实现都满足共同接口，同时验证进程内记账字段满足 `LocalAcceptanceState`。该附加协议只是既有字段的类型说明，不引入用户可实现的接受回调。

`ModuleRunner` 只声明真正共享的逐实例调用边界。初始化、求值和关闭没有强行变成相同方法：批量求值属于分片，关闭一个实例也不等于关闭其共享 Worker。原有直接 `commit_step` 调用入口保留，网络求解仍使用集中事务；没有把本地和 RPC 传输合并成基类，也没有改变数值算法、缓存或 Worker 创建策略。

事务顺序保持为：

1. `prepare` 收集各实例候选，运行回调或 RPC 只出现在原有准备路径中。
2. `validate` 先检查集合、修订、子步身份、时间、双哈希及候选 JSON 状态。
3. `promote` 只写父进程权威状态、修订和既有本地记账，不执行 RPC 或模块回调。
4. `synchronize` 同步已接受候选；失败仍报告 `MODULE_SYNC_FAILED` 并保留接受标记。接受前丢弃候选、不可用 Worker 强制关闭的路径保持原样。

新增 `tests/test_runner_protocol.py` 对三种执行形态分别验证：准备／丢弃不修改权威状态；提升期间禁止 RPC 和用户回调；接受后重试幂等；下一个子步正常推进；过期候选在修改任何权威状态前被拒绝。原有网络事务失败注入继续覆盖多模块回滚、控制状态恢复、Worker 故障和接受后同步失败。

本次实际验证：

```powershell
python -m pytest tests/test_runner_protocol.py tests/test_module_transactions.py tests/test_module_execution.py tests/test_module_execution_network.py -q
# 54 passed in 41.21s

python -m mypy --config-file mypy-runner.ini
# Success: no issues found in 3 source files

python -m mypy
# Success: no issues found in 150 source files
```

`mypy-runner.ini` 对协议、静态结构匹配样例 `runner_typing.py` 和集中事务启用严格类型检查；现有未注解依赖允许调用，不扩大成整个数值内核的类型改造。结构匹配样例不被运行路径导入。CI 执行该命令，新增测试也由现有 pytest 发现机制纳入。

类型分层和 JSON 合同兼容性见 [模型类型分层](MODEL_LAYERING.md)，本轮总验收见 [架构后续验收](ARCHITECTURE_FOLLOWUP_ACCEPTANCE.md)。
