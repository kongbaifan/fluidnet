# R0 交叉核验：浏览器回归 + 旧项目（v0.5.0）兼容

- 工作包：R0 核心（旧项目兼容交叉核验）+ 前端浏览器回归；不改后端数值代码。
- 实施日期：2026-10-23。
- 对照基线：**v0.5.0 `a986ca3`** 的 `contracts/reference-project.json` / `contracts/reference-result.json`
  （用 `git show a986ca3:./contracts/...` 提取；工作树里的同名契约已在后续提交重生成，见 §4）。
- 当前引擎：`98ec24b`（B0/S0/S1/J/L/V 已合入）+ 工作树中并行任务（A/D/I/C）的未提交改动。
  本核验走旧项目默认开关（C/D/A 均关闭、`thermal_acceleration='none'`），因此不受这些未提交特性影响；
  仍如实标注测量窗口。
- 环境：Windows、Python 3.11.0、scipy 1.17.1、CoolProp 8.0.0、原生线程 1；Node 24.16.0、
  Playwright 1.64.0（chromium-1217）。

## 1. 浏览器回归（`npm run test:browser`）

- 命令与结果：`npm run test:browser` → **EXIT=0**；`package.json` 中 14 个脚本全部执行，
  每个脚本输出的 `errors` 均为空（14/14 通过，0 条失败）。仓库 `tests/browser-*.mjs` 共 15 个文件，
  其中 `browser-server.mjs` 是共享的启动/端口辅助模块，不被 `test:browser` 直接执行。
- 覆盖脚本：smoke、platform、authoring、run-control、pid、continuous、multifluid、auth、
  workspace、workflows、archive-migration、cold-storage、cold-storage-station、module-catalog。
- Lead 新增的两条事件行已存在于 `frontend/engine-client.js`：
  - `engine-client.js:559-564`：从帧的 `solve_summary` 拼 `求解：requested method，未知量 matrix_size，Jacobian jacobian_mode。`
  - `engine-client.js:566-568`：仅 `metrics.timestep_adaptive` 为真时拼 `内部步长 …；本帧接受…拒绝…局部时间离散误差范数最大…`。
- **无需修改任何 `tests/browser-*.mjs` 断言**：没有脚本对事件列表做精确匹配而失败；事件相关用例
  （run-control / workflows / continuous）的 `errors` 均为空，原“压力残差/质量残差”行未被破坏。
  本文件只做记录，未改动浏览器用例。

## 2. 旧项目 JSON 解析与缺省字段（R0 核心 1）

`Project.model_validate(json.loads(a986ca3 版 reference-project.json))` 直接成功；v0.5.0 契约里
**不存在**的新字段按当前模型默认值补齐：

| 字段 | v0.5.0 契约 | 当前解析结果 | 说明 |
| --- | --- | --- | --- |
| `solver.hydraulic_method` | `"dense"` | `"dense"` | 旧默认保持 |
| `solver.analytic_jacobian` | 缺字段 | `True` | J 新字段，默认开启（另可用 `False` 回到 FD，见 §3） |
| `solver.series_compression` | 缺字段 | `False` | C 默认关闭 |
| `solver.hydraulic_blocks` | 缺字段 | `False` | D 默认关闭 |
| `solver.hydraulic_diagnostics` | 缺字段 | `False` | B0 默认关闭 |
| `solver.thermal_acceleration` | 缺字段 | `"none"` | L 默认等价 v0.5.0 固定阻尼 |
| `solver.coupling_acceleration` | 缺字段 | `"none"` | 同上 |
| `solver.time_step.enabled` | 缺字段 | `False` | A 默认关闭（固定 `dynamic_step_s`） |

编译并稳态求解成功：`status='converged'`、`valid=True`、`time_s=0`、诊断仅 1 条
`HYDRAULIC_SCOPE`（info，v0.5.0 就存在的范围说明），无 error。

## 3. 逐变量与 v0.5.0 参考结果比较（R0 核心 2）

对 `reference-result.json`（a986ca3 版，`solve_steady` 生成的 RunFrame）的 `variables` 逐键比较：
233 个数值变量（另有 18 个 `None`，如 `*.quality`，两侧同为 `None`）；键集合 **无缺失、无新增**；
非数值变量无不一致。容差：流量 `1e-8 + 1e-6·|q|`、压力 `1 Pa + 1e-8·|p|`、温度 `1e-5 K`；
体积流量/功率/其它变量按 `1e-6 + 1e-6·|ref|` 归类（计划 §3.1 未单列，作为保守补充，单独列组）。

| 变量组 | 个数 | 最大绝对偏差 | 最大偏差/门限 | 超差数 | 最差键 |
| --- | ---: | ---: | ---: | ---: | --- |
| 压力 | 40 | 5.82e-11 Pa | 5.8e-11 | **0** | `N1.in0.pressure_pa` |
| 温度 | 42 | 1.14e-12 K | 1.14e-7 | **0** | `N1.in0.temperature_k` |
| 质量流量 | 28 | 8.88e-16 kg/s | 1.66e-10 | **0** | `B1.out0.mass_flow_kg_s` |
| 体积流量 | 10 | 3.55e-15 m³/h | 1.68e-10 | **0** | `P1.ch0.volume_flow_m3_h` |
| 功率/热量/物性（其它） | 107 | 1.69e-9 | 4.03e-7 | **0** | `L2.in0.specific_heat_j_kg_k` |
| 比例/计数（其它） | 6 | 0 | 0 | **0** | — |

**233 个数值变量 0 个超差**；最大值只有门限的 4.03e-7（约 250 万倍余量）。

指标（`metrics`）同名键对照：

| 指标 | v0.5.0 参考 | 当前 | 差 |
| --- | ---: | ---: | ---: |
| `iterations` | 7 | 7 | 0 |
| `thermal_iterations` | 1 | 1 | 0 |
| `coupling_iterations` | 1 | 1 | 0 |
| `node_count` / `branch_count` | 5 / 5 | 5 / 5 | 0 |
| `pressure_residual_pa` | 1.019e-10 | 4.366e-11 | 5.8e-11 |
| `mass_residual_kg_s` | 4.44e-16 | 0.0 | 4.44e-16 |
| `energy_residual_w` | 3.36e-10 | 1.03e-10 | 2.3e-10 |
| `reference_heat_w` | 0 | 0 | 0 |

`metrics` 新增键 `matrix_size`/`matrix_nnz`、帧新增 `solve_summary`/`solve_counters` 均为**附加字段**
（旧读取方按可选字段处理；浏览器回归覆盖）。

## 4. 差异归因：解析 Jacobian 默认开启

把 `analytic_jacobian` 显式设为 `False`（旧 FD 路径）后，当前引擎与 v0.5.0 参考结果**逐变量完全相同**
（最大偏差 **0**，所有数值变量与指标一致）。默认（`analytic_jacobian=True`）时只有末位差异，且集中在
由物性服务求值得到的量（`specific_heat_j_kg_k` 等）：

| 键 | 当前 | v0.5.0 参考 | 绝对差 |
| --- | ---: | ---: | ---: |
| `V2.out0.specific_heat_j_kg_k` | 4183.809167085273 | 4183.809167083586 | 1.69e-9 |
| `L2.in0.specific_heat_j_kg_k` | 4183.809167085273 | 4183.809167083586 | 1.69e-9 |
| `L1.in0.specific_heat_j_kg_k` | 4183.759505996000 | 4183.759505995448 | 5.51e-10 |

结论：**差异来自 J2 解析 Jacobian 的默认开启**（收敛路径末位不同 → 物性服务在几乎相同但非逐位相同的
`p/T` 上求值），不是物理模型变化；残差本身（1e-10 Pa / 1e-16 kg/s 量级）与之同量级，远低于求解容差
（0.1 Pa / 1e-7 kg/s）与计划 §3.1 门。若需要与 v0.5.0 **逐位一致**，显式 `analytic_jacobian=False`
即可复现（本表实测 0 差异）。

## 5. 契约重生成的漂移（背景）

工作树里的 `contracts/reference-project.json`/`reference-result.json` 在提交 `2f54a35`（B0/S）被
重新生成：`a986ca3` 版 vs `2f54a35` 版 **reference-result 逐变量完全相同**（本核验复算：0 超差），
差异只在项目 JSON 的 solver 键（补了 `hydraulic_diagnostics`、`time_step`）与帧 schema 的可选字段。
所以“旧项目 → 新契约”的数值漂移仅来自 §4 的解析 Jacobian，而不是契约重生成。

## 6. 开关组合（旧项目 JSON 上改 SolverOptions）

在同一份 v0.5.0 项目上依次改开关，全部 `solve_steady` 成功：

| 组 | 配置 | 状态 | vars | vs 旧默认最大偏差 | vs v0.5.0 参考超差数 | matrix_size / nnz |
| --- | --- | --- | ---: | ---: | ---: | --- |
| A | 旧默认（analytic=True，C/D off） | converged | 233 | 0 | 0 | 8 / 64 |
| B | `analytic_jacobian=False` | converged | 233 | 1.69e-9（物性末位） | **0（与参考逐位相同）** | 8 / 64 |
| C | `series_compression=True` | converged | 233 | 1.04e-9（物性末位） | 0 | **4 / 9**（压缩 2 条链，未知量 8→4） |
| D | `hydraulic_blocks=True` | converged | 233 | 0 | 0 | 8 / 64（该拓扑单块，无拆分） |
| E | 新开关显式关闭 + `thermal_acceleration='none'`、`coupling_acceleration='none'` | converged | 233 | 0 | 0 | 8 / 64 |

C 组在参考项目（B1→泵→N1 分两路阀+管→N2→B2）上识别出 2 条串联链（V1+L1、V2+L2），
未知量 8→4（3 个未定压节点 + 5 支路 → 1 个锚点压力 + 3 条约化支路），与未压缩解在 §3.1 门内一致（上表 0 超差）。

## 7. 结论

- R0 旧项目兼容：**通过**。旧 JSON 可直接 `Project.model_validate`，缺字段按旧默认补齐；当前引擎重算与
  v0.5.0 参考结果 233/233 数值变量在计划 §3.1 门内（0 超差），指标一致；唯一偏差源为
  **解析 Jacobian 默认开启**，显式关闭即逐位复现旧结果。
- 前端浏览器回归：**14/14 通过**（EXIT=0，`errors` 全空）；新增 `求解：`/`内部步长` 事件未破坏断言，
  未改任何 browser 用例。

## 8. 未运行 / 限制

- 参考契约只有 `solve_steady` 一帧，没有动态帧参考；本次未对照动态时间序列。
- `time_step.enabled=True` 在旧水力项目上未运行（A 特性仅冷库域接入；本核验只验证旧项目缺省关闭）。
- 非水单工质、多工质参考项目未纳入本次交叉核验。
- 浏览器断言未逐字校验新增事件文案（只验证了原事件序列与 `errors` 为空）；若产品要求“事件数量上限”
  之类语义，需要 Lead 决定，本核验未发现此类失败。

## 9. 复现命令

```powershell
# 浏览器回归（需要 Playwright chromium，已安装）
npm run test:browser

# 取 v0.5.0 旧契约（工作树同名文件已被后续提交重生成）
git show a986ca3:./contracts/reference-project.json > tmp/r0/reference-project-v050.json
git show a986ca3:./contracts/reference-result.json > tmp/r0/reference-result-v050.json
```

交叉核验脚本（保存为 `tmp/r0_crosscheck.py` 后 `python tmp/r0_crosscheck.py`；核心逻辑）：

```python
import json, sys
sys.path.insert(0, 'backend')
from fn_engine.models import Project
from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady

def load(path): return json.loads(open(path, encoding='utf-8').read())
old = load('tmp/r0/reference-project-v050.json')
reference = {k: float(v) for k, v in load('tmp/r0/reference-result-v050.json')['variables'].items()
             if isinstance(v, (int, float)) and not isinstance(v, bool)}
project = Project.model_validate(old)
frame = solve_steady(compile_project(project))
current = {k: float(v) for k, v in frame.variables.items()
           if isinstance(v, (int, float)) and not isinstance(v, bool)}

def tol(key, ref):
    if key.endswith('pressure_pa'): return 1.0 + 1e-8 * abs(ref)
    if key.endswith('temperature_k'): return 1e-5
    if key.endswith('mass_flow_kg_s'): return 1e-8 + 1e-6 * abs(ref)
    return 1e-6 + 1e-6 * abs(ref)

over = [(k, abs(current[k] - reference[k]), tol(k, reference[k]))
        for k in reference if k in current and abs(current[k] - reference[k]) > tol(k, reference[k])]
print('numeric', len(reference), 'over', len(over), 'missing', set(reference) - set(current))
# analytic_jacobian=False 再跑一遍，可与 v0.5.0 参考逐位一致（本核验实测差 0）
```

2026-10-23 本机实测：`npm run test:browser` → EXIT=0（14/14）；交叉核验 233 个数值变量 0 超差，
最大偏差/门限 = 4.03e-7（`L2.in0.specific_heat_j_kg_k`）；`analytic_jacobian=False` 时与 v0.5.0
参考逐变量差 0。
