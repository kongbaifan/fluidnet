# FluidNet 数值优化基线报告（NUMERICS_BASELINE）

- 本文登记 **B3 固定环境完整基线**：v0.5.0 快照 `a986ca3` 的冷启动 5 次 / 热跑 7 次实测。
- 生成日期：2026-10-23。原始结果：`artifacts/numerics/a986ca3/B3/baseline.json`（gitignore，不入库）。
- 本文件只写新测数据；历史基准（v0.5.0 发布记录里的 532 tests / 旧 scaling 单次观测）不混入本表，仅作对照说明。

## 1. 固定配置

| 项 | 值 |
| --- | --- |
| 提交 | `a986ca3bbd05a5132c92b9ce5f5321d06bb6da7b`（v0.5.0，detached worktree，无未提交改动） |
| Python | 3.11.0（Windows） |
| 依赖 | numpy 2.3.2 / scipy 1.17.1 / pydantic 2.13.4 / fastapi 0.137.1 / uvicorn 0.49.0 / psutil 7.2.2 / CoolProp 8.0.0 |
| 硬件 | AMD64 Family 25 Model 80 Stepping 0，8 物理核 / 16 逻辑核，17.0 GB 内存 |
| 原生线程 | 1（OPENBLAS/OMP/MKL 均固定为 1；`benchmark_scaling.measure` 逐次采样进程树 RSS） |
| 物性后端 | CoolProp 8.0.0；REFPROP 本机可用（`C:\Program Files (x86)\REFPROP`），基线未使用 REFPROP 工质 |
| 进程/Worker 数 | 每个用例按用例配置启动；Python 实例走 `WorkerProcess` 子进程 |
| 重复次数 | 冷启 5 次（新进程）/ 热跑 7 次（同进程预热 1 次后）；例外见 §4 |
| 失败数 | 20/20 用例通过，冷+热样本失败数均为 0 |
| 原始结果哈希 | `raw_result_sha256 = 2d4a7e1f610df41c…`（完整值见 JSON） |
| 测量时机器负载 | CPU 31.1%、内存 86.9%、同时 8 个 Python 进程（并行工作流）；见 §5 噪声说明 |

文件哈希登记（基线快照）：`solver.py 5ff3018e…`、`worker.py 92ad908a…`、`runtime.py 29526fd5…`、
`control.py 14e0e50b…`、`thermal.py 72e1cd61…`、`models.py 93dd15aa…`、`bench.py 98938be5…`、
`properties.py 1010676e…`（完整哈希在 JSON `environment.file_sha256`）。

## 2. 复测方式（单个清单）

```powershell
# 在 v0.5.0 快照 worktree（artifacts/numerics/baseline-tree/fluidnet-prototype-engine）根目录：
$env:PYTHONPATH = '<同目录>\backend'
python <主仓库>\scripts\numerics_baseline.py --output artifacts/numerics/a986ca3/B3/baseline.json

# 只列用例 / 只跑子集：
python scripts/numerics_baseline.py --list
python scripts/numerics_baseline.py --only series,python-batch --output <path>
```

脚本只写 `--output` 指定路径（通常为 gitignore 的 `artifacts/`），不改用户工作区。子进程输出落临时文件
而不是管道：模块 Worker 是孙进程，管道句柄被继承时 `capture_output` 可能等不到 EOF。

## 3. 实测结果（矩阵级 `measure()` 墙钟，单位 s）

冷启列 = 新进程内 compile→solve 的**测量段**中位数（5 次）；`进程墙钟` = 直接子进程整体墙钟中位
（含解释器启动与 import，约 3.5–4 s，不做性能结论）。热跑列 = 预热 1 次后 7 次中位数。

| 用例 | 实例 | 冷启中位 | 冷启 min–max | 热跑中位 | 热跑 min–max | 进程墙钟（冷） |
| --- | ---: | ---: | --- | ---: | --- | ---: |
| topology/series/small | 100 | 0.430 | 0.424–0.450 | 0.334 | 0.267–0.344 | 3.97 |
| topology/series/medium | 500 | 1.894 | 1.645–2.335 | 1.705 | 1.389–2.351 | 5.46 |
| topology/series/large | 1000 | 3.992 | 3.517–4.257 | 3.504 | 2.917–4.222 | 7.54 |
| topology/parallel/small | 12 | 0.169 | 0.104–0.226 | 0.089 | 0.086–0.131 | 3.80 |
| topology/parallel/medium | 52 | 0.228 | 0.182–0.321 | 0.237 | 0.195–0.348 | 3.86 |
| topology/mesh/small | 23 | 0.181 | 0.137–0.192 | 0.139 | 0.108–0.160 | 3.79 |
| topology/mesh/medium | 98 | 0.406 | 0.318–0.530 | 0.313 | 0.284–0.412 | 4.02 |
| topology/components/small | 10 | 0.124 | 0.101–0.139 | 0.096 | 0.060–0.142 | 3.98 |
| topology/components/medium | 52 | 0.191 | 0.148–0.281 | 0.179 | 0.132–0.186 | 3.60 |
| topology/thermal-dual-loop/small | 9 | 0.104 | 0.099–0.149 | 0.090 | 0.048–0.125 | 3.67 |
| topology/thermal-dual-loop/medium | 21 | 0.147 | 0.130–0.174 | 0.098 | 0.076–0.117 | 3.70 |
| topology/python-multiport/small | 8（4 Python） | 2.472 | 2.347–2.798 | 2.646 | 2.271–3.015 | 6.11 |
| legacy/series-100-dense | 100 | 0.807 | 0.731–1.391 | 0.757 | 0.704–0.825 | 3.95 |
| legacy/series-500-dense | 500 | 23.611 | 单次 | 23.516 | 单次 | 26.53 |
| legacy/series-100-sparse | 100 | 0.391 | 0.359–0.425 | 0.243 | 0.239–0.260 | 3.80 |
| legacy/series-500-sparse | 500 | 1.389 | 1.295–1.598 | 1.812 | 1.622–2.669 | 4.65 |
| legacy/series-1000-sparse | 1000 | 3.681 | 3.454–4.889 | 3.746 | 3.052–3.959 | 7.46 |
| legacy/python-batch-25-b1w1 | 30（7 Python） | 2.664 | 2.537–2.733 | 2.640 | 2.367–2.956 | 6.09 |
| legacy/python-batch-100-b1w1 | 30（29 Python） | 2.903 | 2.615–3.047 | 2.800 | 2.575–3.061 | 6.44 |
| legacy/python-batch-100-b1w2 | 30（29 Python） | 4.573 | 4.220–4.886 | 5.160 | 4.351–5.720 | 7.62 |

说明：

- 每个用例的完整分项（compile/solve/hydraulic/thermal/RPC/serialize/peak RSS/残差/迭代数）都在 JSON 的
  `cases[*].cold/hot.*` 里；RPC 总和跨 Worker 求和且与水力时间重叠，不可直接相加。
- 历史对照：计划 §2 记录的“100 实例、195 未知量”与本次 `series/small` 的规模一致（195 未知量），
  但历史数值是单次微测，本表不把它当作基线。
- **dense 500 的 23.6 s 与 sparse 500 的 ~1.4–1.8 s 是本基线最重要的分母差异**：v0.5.0 的逐变量
  数值 Jacobian 成本随未知量快速增长；J/S 专项应以此为分母对照。

## 4. 协议例外与未运行项

| 项 | 处理 | 原因 |
| --- | --- | --- |
| `legacy/series-500-dense` | 冷 1 次 / 热 1 次 | 单次 23.6 s，完整 5+7 会独占机器数分钟；JSON 里 `repeats` 已标注 |
| `legacy/series-1000-dense` | **未运行** | v0.5.0 数值 Jacobian 单次 >11 分钟（共享机实测），不适合作为可用基线；dense 规模外推留给 S/J 证据 |
| `python-multiport/medium` 与大档 | **未运行** | 16 个 Python 实例顺序启动 Worker，单次 ~8 s，完整协议数分钟且只反映 Worker 启动；由 W0/W1 单独剖析 |
| 冷库 A/B | 不在 B3 矩阵 | 由 B2 单独计时（冷启动子进程 + 热重复），见 `docs/numerics/results/B2.md` |
| 浏览器 64 实例/页 | 未运行 | 本包只做后端数值基线；浏览器限制仍按既有验收 |

## 5. 噪声与解释边界

- 测量期间机器同时有并行工作流（Lead 的 S/J 改造、Valve/A 专项 agent 的验证脚本），
  `environment.cpu_load` 记录为 CPU 31.1% / 内存 86.9% / 8 个 Python 进程。绝对墙钟只能作为
  **同机相对对照**，不满足“独占固定环境”的严格条件；min–max 区间已如实保留。
- `python-batch-100-b1w2` 冷 4.57 s / 热 5.16 s 高于 b1w1，与 v0.5.0 的批量 Worker 调度开销有关，
  本基线不做因果判断；W0/W1 会单独拆解 Worker 启动成本。
- 热跑并不总是快于冷启（如 series-500-sparse），因为热跑仍会在每次 solve 内新建 Python 模块
  Worker；差异主要来自属性缓存与 import 缓存，量级受并行负载影响。
- 本基线没有打开 B0 的 `hydraulic_diagnostics` 计数开关（v0.5.0 没有该字段）；RPC 次数来自
  `measure()` 对 `WorkerProcess._request` 的计时包装，真实残差/Jacobian 扰动计数要在改造后
  当前树上用 B0 开关另跑，已登记在 §6。

## 6. 改造后 A/B 计划

1. C/D/I 落盘、机器空闲窗口里，用同一 `scripts/numerics_baseline.py` 在当前工作树重跑同一矩阵；
2. 报告 `analytic_jacobian` / `hydraulic_method`（requested vs effective）/ `matrix_size` 等求解摘要字段
   （B0 计数开关打开时）；
3. 按计划 §3.2：先过成功率与残差门，再比较中位数；小模型回退门 ≤10%，超过时复测并保留旧路径；
4. 若改造后结果与 v0.5.0 相对差超过 1e-6，先报差异，不直接改断言。

状态：**待 C/D/I 完成后执行**（本文日期时 v0.5.0 基线已落盘；改造后矩阵与 A/B 结论未运行）。

