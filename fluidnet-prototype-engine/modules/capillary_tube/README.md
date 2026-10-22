# 毛细管（毛细节流阀）参考模块

单相液体近似下的细长管节流元件：把 `in0 → out0` 建成一条 `pipe` 阻力支路，
由平台按 Darcy–Weisbach + 层流/湍流混合摩擦律求解流量与压降，并输出流通面积、
平均流速与累计通过质量。

```text
A   = π·d²/4
Re  = |m|·d/(μ·A)
层流  Δp = 32·μ·L·m/(ρ·A·d²)
湍流  f  = [−1.8·log10((ε/d/3.7)^1.11 + 6.9/Re)]⁻²
      Δp = f·(L/d)·m·|m|/(2·ρ·A²)
2300 < Re < 4000：层流与湍流按 (Re−2300)/1700 线性插值
```

`evaluate()` 只注册 `main` 通路并输出 `flow_area_m2`、`mean_velocity_m_s`；
`commit_step()` 用收敛流量累计 `state.throughput_kg`。

## 参数（canonical 单位）

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `diameter_m` | `0.0015` m | `[1e-4, 0.05]` m | 内径，显示单位 mm |
| `length_m` | `1.5` m | `[0, 100]` m | 长度 |
| `roughness_m` | `1.5e-6` m | `[0, 1e-3]` m | 绝对粗糙度，显示单位 mm |
| `density_kg_m3` | `998.2` kg/m³ | `≥ 1` | 参考密度；`in0` 端口给密度时优先用端口值 |
| `viscosity_pa_s` | `0.001` Pa·s | `≥ 0` | 动力黏度；`in0` 端口给黏度时优先用端口值 |

## 变量

| 变量 | 来源 | 说明 |
| --- | --- | --- |
| `flow_area_m2` | derived | 按内径计算的流通面积 |
| `mean_velocity_m_s` | derived | 平均流速 `|m|/(ρ·A)` |
| `state.throughput_kg` | state | `Σ|m|·dt`，累计通过质量 |

## 边界与诊断

- **单相边界**：本模块只表达单相液体。两相壅塞、闪发、沿程蒸发和出口干度都不在
  模型内；`heat_w` 固定为 0（绝热）。每次 `evaluate()` 都会发一条
  `CAP_TWO_PHASE_UNSUPPORTED(info)`，提示当前结果只适用于单相液体工况。
- 运行防御：`d` 截断到 `≥ 1e-4 m`，`L` 截断到 `≥ 1e-6 m`，`ε ≥ 0`，
  `ρ ≥ 1e-3 kg/m³`，`μ ≥ 1e-6 Pa·s`。

| 诊断码 | 级别 | 触发条件 |
| --- | --- | --- |
| `CAP_TWO_PHASE_UNSUPPORTED` | info | 每次 `evaluate()`（模型假设提示） |
| `CAP_LENGTH_CLAMPED` | warning | `length_m < 1e-6`，按 `1e-6` 计算（例如长度设为 0） |
| `CAP_VISCOSITY_FALLBACK` | warning | 有效黏度 `≤ 0`，按 `1e-6 Pa·s` 计算 |
| `CAP_PRESSURE_UNKNOWN` | warning | 端口 `mass_flow` 与压力都缺失，`mean_velocity_m_s = 0` |

- `evaluate()` 里端口 `mass_flow_kg_s` 通常为 `None`：此时用试算压差
  `p_in − p_out` 按与 `solver.pipe_drop` 相同的摩擦律二分反解 `|m|`（`_pipe_drop`
  是同步副本，改求解器时必须同步），再折算流速。给了端口流量则直接优先用它。

## 与倍思鹿“毛细节流阀”的差异

倍思鹿 `AlgModule/毛细节流阀` 面向制冷剂节流：入口为高压过冷/饱和液，节流后进入
两相区，模块内部用物性库反求闪发后的干度、出口熵/焓与两相壅塞流量。FluidNet 的
管网求解与热力输运只支持与回路边界一致的单相，因此这里**不移植闪发与壅塞模型**，
只用同几何的细长管阻力关系做“单相液体近似”：

- 可以对齐的量：给定单相液体流量时的压降、平均流速、通过质量；
- 不能对齐的量：出口干度、闪发率、两相壅塞流量、节流后的温度；
- 制冷剂回路中若入口已是两相或压降后跨相，本模块只保留水力阻力，结果仅作趋势参考，
  应以 `CAP_TWO_PHASE_UNSUPPORTED` 诊断与冷库/制冷执行域的内置设备为准。

## 参考算例

默认几何（φ1.5 mm × 1.5 m，水，`ρ=998.2`、`μ=0.001`）：

- 质量流量 `0.02 kg/s` → `flow_area_m2 = 1.7671e-6 m²`，`mean_velocity_m_s ≈ 11.34 m/s`，
  `Re ≈ 1.7e4`（湍流区）；
- 质量流量 `0.0005 kg/s` → `Re ≈ 424`（层流区），压差约 `6.05 kPa`；
  `commit_step(dt=2 s, m=0.02 kg/s)` → `state.throughput_kg = 0.04 kg`。
