# 止回阀参考模块 v2（语义修正版）

`manifest.json`：`id=check_valve`、`version=2`（包版本 `2.0.0`）。v1 包 `modules/check_valve/` 保持原样，
本目录是**同 id 的新版本**，旧项目快照仍绑定 v1 定义与源码。冻结语义见
[`docs/MODULES_P0.md`](../../docs/MODULES_P0.md) §5；证据见 `docs/numerics/results/V0.md`、
`V1.md`、`V2.md`。

## 物理假设与方程

压差定义 **Δp = p_in − p_out**（`in0` 减 `out0`）。

| 条件 | 行为 |
| --- | --- |
| Δp ≤ p_crack（含全部反向 Δp ≤ 0） | `opening_ratio = 0.0`（精确 0），求解器把 `main` 通路变成 `flow == 0` 等式约束 → **反向/亚开启区通过质量精确为 0** |
| Δp > p_crack | `opening = opening_max · sqrt(1 − p_crack/Δp)`，`main` 通路按 `valve` 关系求解 |

`opening` 的构造让阀门关系正好等价于“开启压差 + 阀门阻力”串联的物理曲线：

```
Q [m³/h] = Kv · opening_max · sqrt( (Δp − p_crack) / (1e5 · ρ/1000) )
```

（`solver.branch_drop` 的 `valve` 分支为 `Δp = 1e5·(ρ/1000)·Q|Q|/Kv_eff²`，`Kv_eff = Kv·opening`。）

开关点 Δp = p_crack 处两侧流量都趋于 0，**残差连续（C0）**；但左、右导数不同（关闭行不含压力，
开启支路 `∂q/∂Δp → ∞`），模型**不承诺处处光滑**，也**不承诺**临界点附近迭代数最少。

## 参数

| id | 默认 | 单位 | 语义 |
| --- | --- | --- | --- |
| `kv_m3_h` | 50 | m³/h | 全开流量系数 |
| `p_crack_pa` | 0 | Pa（显示 kPa） | **正向开启压差**，Δp 必须大于它才导通 |
| `opening_ratio` | 1.0 | [0,1] | 正向最大开度（缩放 Kv） |
| `hysteresis_pa` | 0 | Pa | 迟滞带宽；0 = 无迟滞（默认）。> 0 为可选路径，见下 |
| `density_kg_m3` | 998.2 | kg/m³ | 端口密度缺失时的参考密度 |
| `cracking_pressure_pa` | 0 | Pa | **v1 遗留参数，v2 不参与计算**；非零时发一次 info 提示 |

旧参数语义（v1，不覆写）：`cracking_pressure_pa` 表示“容许反向流的反向压差”——
`0 < p_out − p_in ≤ cracking_pressure_pa` 时阀门仍按正向开度**反向导通**。实测在
`cracking_pressure_pa=5000`、反向 1000 Pa 时反向流量 1.39 kg/s，并在反向 4500/4999 Pa 处
`least_squares` 停在不收敛点（详见 `docs/numerics/results/V1.md`）。v2 不沿用该语义。

## 变量

| id | source | 语义 |
| --- | --- | --- |
| `opening_ratio` | derived（evaluate/commit） | 有效开度，`0` = 精确截止 |
| `is_open` | derived（evaluate/commit） | 1 = 该次试算/提交时导通 |
| `direction` | derived | +1：Δp > 0；−1：Δp ≤ 0（**不**代表是否导通） |
| `state.is_open` | state | 仅接受步更新的开闭状态（无迟滞时只是记账） |
| `state.closed_steps` / `state.open_steps` | state | 接受步计数 |
| `state.throughput_kg` | state | ∑|q|·dt |
| `state.reverse_throughput_kg` | state | ∑min(q,0)·dt，V2 验收要求保持 0 |

## 诊断码

| code | severity | 场景 |
| --- | --- | --- |
| `CHECK_VALVE_LEGACY_PARAMETER` | info | `cracking_pressure_pa ≠ 0` 且尚未提示过：v2 不采用该参数 |

## 迟滞（可选，默认关闭）

`hysteresis_pa = 0` 时 `evaluate` 只依赖试算 Δp（与 accepted state 无关），因此幂等、无需
求解器改动。`hysteresis_pa > 0` 时改为读取 `state.is_open` 并在整个试算中保持活动集，需要
求解器外层活动集（按“求解 → 检查互补 → 翻转 → 重解”收敛后再提交）；在未接入外层活动集前
单独使用会出现一步滞后。无论迟滞是否开启，**Δp ≤ 0 恒关**，反向精确零流不受影响。

## 已知边界

- 关闭后若把下游隔成无压力参考的子网，运行会报 `模块通路关系产生了缺少压力参考的子网络`；
  动态时间步的被动段保压近似只覆盖内置被动支路，不含 Python 支路的运行期关断。
- `evaluate` 契约拿不到流量，开关判据只能基于压差；流量方向只能由求解结果事后检查。
- 临界点 Δp → p_crack⁺ 时开度趋于 0，`nfev` 会上升（实测 5000.01 Pa：10 次；5001 Pa：6 次；
  5000 Pa 及以下 2 次），但不靠减小 dt 修复稳态。
- 冷启动与热启动都可能更快：从大流量跳到临界附近时热启动不一定更省。

## 参考算例

`kv_m3_h=50`、`p_crack_pa=5000`、水 ρ≈998.275 kg/m³：

| Δp | 实测 q | 解析参考 |
| --- | --- | --- |
| 20000 Pa | 5.37450269 kg/s | 5.3745… |
| 10000 Pa | 3.10297057 kg/s | 3.1029… |
| 5001 Pa | 0.04388263 kg/s | 0.0438810… |
| 5000.01 Pa | 0.00438826 kg/s | 0.0043881… |
| ≤ 5000 Pa（含反向） | 0（精确） | 0 |

`tests/test_check_valve_numerics.py` 用 `backend/fn_engine/check_valve.py` 的独立解析曲线逐点对照，
并记录迭代次数与 RPC。
