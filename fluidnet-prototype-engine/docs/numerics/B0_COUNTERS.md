# B0：水力求解调用计数语义与轻量观测器

状态：已实现（`SolverOptions.hydraulic_diagnostics`，默认 `False`）。

## 1. 为什么需要它

`HydraulicResult.iterations` 一直来自 SciPy `least_squares` 的 `result.nfev`。按 SciPy 对 `trf`
方法的约定，`nfev` **不统计数值 Jacobian 的扰动调用**，因此它既不能当“真实残差调用”，也不能
说明优化去掉了多少工作。前次微测里 dense 1176 次 / sparse 42 次真实残差调用对应的 `nfev` 只有
6 / 7，就是这条缺口。B0 把缺口显式记账，并保持 `iterations` 原语义不变（历史报告仍可对照）。

## 2. 字段语义（`HydraulicResult.counters`，dict）

`hydraulic_diagnostics=False`（默认）时 `counters is None`，求解路径与 v0.5.0 完全一致，
不做逐调用计时。打开后 `counters` 含下列键：

| 键 | 单位 | 含义 |
| --- | --- | --- |
| `nfev` | 次 | SciPy `trf` 报告的基础函数调用数；**不含** Jacobian 扰动 |
| `njev` | 次 | SciPy 报告的 Jacobian 形成次数 |
| `residual_calls` | 次 | `physical_residual` 的真实调用总数（基础 + 扰动） |
| `perturbation_calls` | 次 | `residual_calls - nfev`，即旧指标漏掉的 Jacobian 扰动调用 |
| `solver_attempts` | 次 | `least_squares` 启动次数（温启动失败后的冷启动重试会计入） |
| `rpc_batches` | 次 | 模块 evaluate 的 RPC 批次数 |
| `rpc_instances` | 次 | 实际 evaluate RPC 内的实例次数（不含父进程缓存命中） |
| `parent_cache_hits` | 次 | 父进程直接复用的模块实例结果数，不发生 RPC |
| `worker_requests` | 次 | 相关 Worker 实际收发的 RPC 总数（含 initialize/parameters/commit_step） |
| `module_evaluations` | 次 | 模块 evaluate 轮数（原 `iteration_id`） |
| `timing_s` | s | 分项墙钟：`residual`、`least_squares`、`solve_total` |

## 3. 两种 RPC 单位必须分开

- 批量 Worker（`batch_modules=True` 且 Python 实例 >1）：一次 `evaluate` 里每个有未命中实例的分片发**一个**
  `batch` RPC，`rpc_batches` 记非空分片数、`rpc_instances` 记这些分片实际发送的实例数。
- 逐实例 Worker：每个实例一次 RPC，`rpc_batches == rpc_instances`。

比较跨配置的“RPC 次数”使用 `rpc_batches`。2026-10-25 起按实际非空分片统计，多分片一次求值可能产生多个 RPC；全部命中父进程缓存时记 0。`worker_requests` 保留 Worker 生命周期累计值，跨帧比较时取差值。

## 4. 计时口径

- `timing_s['residual']` 与 `timing_s['least_squares']` **重叠**（least_squares 内部就是残差调用），
  不能相加；`solve_total` 覆盖整个 `_solve_hydraulics`，包含上面两项。
- 线性子问题（LSMR）与 Jacobian 组装没有单独打点：SciPy 把它们放在 `least_squares` 内部，
  拆分会引入额外计时开销并污染被测路径。J2 的自写解析 Jacobian 才可能单独计时。
- 该开关只用于证据采集，不进入默认运行路径；证据报告必须写清开关状态。
