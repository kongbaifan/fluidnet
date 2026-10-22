# 变速水泵参考模块

水泵按 `pump_curve` 关系注册到 `main` 通路，扬程-流量曲线与转速比交给求解器联立：

```text
ctx.net.pump(head_curve=H(Q), speed_ratio=n, density_kg_m3=ρ)
```

- `evaluate()` 校验 `head_curve`：至少 2 点、首点流量为 0、末点扬程为 0、流量严格递增、扬程严格递减且非负；非法时诊断 `PUMP_CURVE_INVALID` 并回退默认曲线 `[[0,20],[10,18],[20,12],[30,0]]`。
- 无流量信息时，`pump_head_m` 按额定流量插值：`Q_curve = nominal_flow/speed_ratio`，`H = interp(Q_curve)·speed_ratio²`（与 `solver.pump_head` 的相似律一致）；`shaft_power_w`/`electric_power_w` 在 evaluate 中给 0。
- `commit_step()` 用收敛通路流量与压差计算：

```text
P_hyd  = |Δp|·|m| / ρ
P_shaft = P_hyd / η_pump
P_elec  = P_shaft / η_motor
state.shaft_energy_j    += P_shaft·dt
state.electric_energy_j += P_elec·dt
pump_head_m = |Δp| / (ρ·g)
```

并把 `pump_head_m`、`shaft_power_w`、`electric_power_w` 写入提交变量。

## 参数（canonical）

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `head_curve` | `[[0,20],[10,18],[20,12],[30,0]]` | — | 流量 m³/h，扬程 m |
| `nominal_flow_m3_h` | 10 | ≥0 | 额定流量 m³/h |
| `speed_ratio` | 1.0 | [0.05, 2] | 转速比 |
| `efficiency` | 0.7 | [0.05, 1] | 水泵效率 |
| `motor_efficiency` | 0.9 | [0.05, 1] | 电机效率 |
| `density_kg_m3` | 998.2 | ≥1 | 水参考密度 kg/m³ |
| `viscosity_pa_s` | 0.001 | ≥0 | 水动力黏度 Pa·s |

## 变量

`pump_head_m`（m）、`shaft_power_w`（W）、`electric_power_w`（W）、`state.shaft_energy_j`（J）、`state.electric_energy_j`（J）。

## 诊断码

| code | severity | 含义 |
| --- | --- | --- |
| `PUMP_CURVE_INVALID` | warning | 扬程曲线不满足校验，已回退默认曲线 |

## 已知边界

- 本模块是通用变速泵参考实现，**不包含**倍思鹿 `FUD_TRNPRP` 专用修正；变物性/变密度迭代由平台 `property_coupling='node'` 承担。
- 效率为定值，未建模效率随流量/转速变化的曲线。
- 转速比低于下限 0.05 或高于 2 时按 `[0.05, 2]` 截断，避免泵关系 `speed_ratio > 0` 校验失败。

## 参考算例

默认参数、`m = 2 kg/s`、`Δp = 150 kPa`、`dt = 2 s`：

```text
P_hyd = 150000·2/998.2 = 300.54 W
P_shaft = 300.54/0.7 = 429.34 W
P_elec  = 429.34/0.9 = 477.05 W
state.electric_energy_j = 954.10 J（> state.shaft_energy_j = 858.69 J）
```
