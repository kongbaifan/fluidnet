# J0–J3 证据：内置关系解析 Jacobian

- 日期：2026-10-23；基线 v0.5.0 `a986ca3`。
- 测试：`python -m pytest -q tests/test_hydraulic_derivatives.py tests/test_analytic_jacobian.py` → **61 + 12 passed**。
- 代码：`backend/fn_engine/hydraulic_derivatives.py`（值 + 导数同源，`solver` 只从这里导入物理公式）；
  `solver.py::_solve_hydraulics` 内置解析 Jacobian 与自动回退；开关 `SolverOptions.analytic_jacobian`（默认 `True`）。

## 1. J0/J1：导数与自适应中心差分对照

`tests/test_hydraulic_derivatives.py`（61 项）覆盖：

| 关系 | 覆盖点 | 结果 |
| --- | --- | --- |
| 阀门 | 正/反向、不同 Kv、开度、高差常量项、q=0 数学极限 | 相对误差 ≤1e-5（非拐点） |
| 阻力 | 正/反向 | ≤1e-5 |
| 层流管 | Re=100/1000 | ≤2e-5 |
| 过渡带 | Re=2600/3150（线性混合段） | ≤2e-5 |
| 湍流 Haaland | Re=1.2e4…2.5e5，粗糙度 0/1.5e-6/4.5e-4/3e-3 | ≤1e-5 |
| 过渡带边界 | Re=2300 / 4000 单侧差分 | 与实现约定一致（进入湍流段） |
| 泵曲线 | 各段内点、拐点、曲线外线性外推、speed=0.7/1.0/1.3 | 值逐位一致，段内 ≤1e-4 |

分段约定（写进模块文档字符串）：
- `Re=2300` 取右导数（含混合项），`Re=4000` 取湍流导数；
- 泵曲线拐点取右段斜率，曲线外沿用原线性外推；
- `q·|q|` 项在 q=0 处导数为 0（数学极限）。

## 2. J2：解析路径与计数

实测（`solve_hydraulics`，管道串联链，3 次取中位数，单进程，Windows + Python 3.11）：

| 未知量 | 方法 | 解析 | nfev | 真实残差调用 | 扰动调用 | 墙钟 ms |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 19 | dense | 否 | 7 | 140 | 133 | 22.5 |
| 19 | dense | 是 | 7 | **7** | **0** | 10.3 |
| 59 | dense | 否 | 6 | 360 | 354 | 104.0 |
| 59 | dense | 是 | 6 | **6** | **0** | 24.1 |
| 119 | dense | 否 | 7 | 840 | 833 | 340.6 |
| 119 | dense | 是 | 7 | **7** | **0** | 77.8 |
| 599 | dense | 否 | 6 | 3600 | 3594 | 4895.9 |
| 599 | dense | 是 | 6 | **6** | **0** | 634.2 |
| 239 | sparse | 否 | 7 | 42 | 35 | 160.2 |
| 239 | sparse | 是 | 7 | **7** | **0** | 99.8 |
| 599 | sparse | 否 | 7 | 42 | 35 | 299.7 |
| 599 | sparse | 是 | 7 | **7** | **0** | 230.7 |

结论：纯内置路径的 Jacobian 扰动调用降为 0（这正是旧 `iterations` 字段漏掉的缺口）；
dense 在大网络上的端到端收益约 **7×**（599 未知量 4.90 s → 0.63 s），sparse 约 1.2–1.6×。
`auto` 在 599 未知量选 sparse，因此实际收益取决于规模。

解析 Jacobian 与有限差分的逐元素对照（`test_jacobian_matches_finite_difference`，取 least_squares
每次调用的解析矩阵与 2-point 差分）：最差相对偏差 **7.3e-8**（水箱净流入列、压力列、支路列全含）。

## 3. 启用条件与回退（J2 验收）

| 网络 | jacobian_mode | 原因 |
| --- | --- | --- |
| 纯内置（阀/管/泵/阻力/换热器通路/水箱） | `analytic` | 纯内置关系 |
| 含 Python 模块 | `finite_difference` | 端口关系可能依赖全部试算压力，保留有限差分 |
| 显式 `analytic_jacobian=False` | `finite_difference` | 显式关闭 |
| 未来的未注册内置模型 | `finite_difference`（防御分支） | 编译器白名单目前使该分支不可达，保留为安全网 |

`RunFrame.solve_summary` 始终记录 `jacobian_mode`/`jacobian_reason`，以及 S1 的方法选择。

## 4. J3：回归与默认策略

解析路径默认开启（纯内置网络）。回归断言：
- `water-net` / `heat-loop` / `tank-control` 三个原型项目：解析 vs 有限差分逐变量相对差 ≤1e-6；
- steady + `property_coupling='node'`：一致；
- 关闭阀（`opening_ratio=0`）仍产生 `flow==0` 约束行，解析行导数 1；
- 水箱隐式步：压力对净流入的 `dt·g/A` 耦合项必须出现在支路行（缺了会假收敛，曾在本包内被差分对照抓出）。

未覆盖：混合解析/数值（Python 模块）Jacobian 的完整链式依赖，按计划列为后续候选。
