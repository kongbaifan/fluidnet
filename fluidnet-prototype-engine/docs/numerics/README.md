# 数值性能与物理能力专项：证据索引

本目录是 [NUMERICS_OPTIMIZATION_PLAN](../NUMERICS_OPTIMIZATION_PLAN.md) 的执行证据。
每个文件对应一个工作包或一组工作包，记录**实测**命令、数字、适用/拒绝条件与未完成项；
原始结果在忽略提交的 `artifacts/numerics/`，这里只放精简、可追溯的摘要。

## 1. 怎么读

- 每个包的状态以证据文件为准：`已验证` / `部分验证（列出未覆盖）` / `未达标`。
- 任何“目标值”都来自计划草案；只有证据文件里的数字才是实测结果，不把计划阈值当已实现能力。
- 所有性能数字都是**单机、固定提交、单进程单线程**的实测；跨机器不可直接比较。
- 复现入口：`python -m pytest -q <对应 tests 文件>`；性能矩阵见 `docs/NUMERICS_BASELINE.md` 与 `scripts/`。

## 2. 索引

| 包 | 证据 | 一句话结论 |
| --- | --- | --- |
| B0 | [B0.md](results/B0.md)、[B0_COUNTERS.md](B0_COUNTERS.md) | 真实残差/Jacobian/RPC 计数与旧 `iterations` 缺口已可观测 |
| B1–B3 | [B1.md](results/B1.md)、[B2.md](results/B2.md)、[B3.md](results/B3.md) | 6 类拓扑 × 小中大样例、动态场景与固定环境基线 |
| W0–W2 | [W0.md](results/W0.md)、[W1.md](results/W1.md)、[W2.md](results/W2.md) | Worker 启动分解与消 eager import 的实测收益 |
| S0–S2 | [S0.md](results/S0.md)、[S1.md](results/S1.md)、[S2.md](results/S2.md) | auto 稀疏选择（阈值 64/0.45）、一次可诊断回退、新项目默认 auto |
| J0–J3 | [J.md](results/J.md) | 纯内置解析 Jacobian：扰动调用归零，dense 大网络约 7× |
| C0–C3 | [C0.md](results/C0.md)、[C1.md](results/C1.md)、[C2.md](results/C2.md)、[C3.md](results/C3.md) | 串联压缩：1000 串联 1999→1 未知量，端到端约 141×；默认关闭 |
| D0–D2 | [D0.md](results/D0.md)、[D1.md](results/D1.md)、[D2.md](results/D2.md) | 分块/整网结果一致；大网络 1.45–2.38×，小模型回退，默认关闭 |
| V0–V2 | [V0.md](results/V0.md)、[V1.md](results/V1.md)、[V2.md](results/V2.md) | 止回阀 v2：反向精确零流、开关点连续；默认无迟滞 |
| L0–L2 | [L1.md](results/L1.md) | 热力 Picard 自适应阻尼慢例 −67% 迭代；node 外循环加速无收益，保持默认 |
| A0–A4 | [A0.md](results/A0.md)、[A1.md](results/A1.md)、[A2.md](results/A2.md)、[A3.md](results/A3.md)、[A4.md](results/A4.md) | Euler 步长误差控制：理想热模型 + 冷库 B；默认关闭 |
| I0–I4 | [I0.md](results/I0.md)、[I1.md](results/I1.md)、[I2.md](results/I2.md)、[I3.md](results/I3.md)、[I4.md](results/I4.md) | 单容积封闭原型；不是“完整隔离段功能” |
| X/G | [X.md](results/X.md) | X0 线程并行无收益停止；X1/X2/G0 无立项证据 |
| R0/R1 | [R0_CROSSCHECK.md](results/R0_CROSSCHECK.md)、[R1.md](results/R1.md) | 旧项目交叉核验、全量回归 835 passed / 覆盖率 90.94% |

## 3. 默认行为一览（v0.6）

| 开关 | 默认 | 影响 |
| --- | --- | --- |
| `SolverOptions.hydraulic_method` | 旧项目 `dense`；新建项目 `auto` | auto 按未知量与稀疏度选 dense/sparse |
| `SolverOptions.analytic_jacobian` | `True` | 纯内置网络解析 Jacobian；Python 混合自动有限差分 |
| `SolverOptions.series_compression` | `False` | 串联压缩，结果与常规路径一致（3.1 差值门） |
| `SolverOptions.hydraulic_blocks` | `False` | 依赖安全分块；大网络有收益、小模型有回退 |
| `SolverOptions.thermal_acceleration` | `'none'` | `adaptive`/`aitken` 为试验模式 |
| `SolverOptions.coupling_acceleration` | `'none'` | 本轮未证明收益，保留试验选项 |
| `SolverOptions.time_step.enabled` | `False` | 仅理想热模型与冷库 B 支持；其他执行域显式拒绝 |
| `SolverOptions.hydraulic_diagnostics` | `False` | 打开后帧里多 `solve_counters`，数值不变 |

## 4. 维护规则

- 新增/修改工作包时同步更新本索引与对应证据；未运行的结果写“未运行”，不写推算值。
- 证据文件里的数字若因后续改动失效，标注失效日期与原因，不静默保留旧结论。
