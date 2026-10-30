# 风机参考模块

风机按 `pump_curve` 关系注册到 `main` 通路：把风压-风量曲线换算为空气柱扬程曲线，由求解器与管网联立。

```text
H(Q) = p(Q) / (ρ_air·g)          g = 9.80665 m/s²
ctx.net.pump(head_curve=H, speed_ratio=n, density_kg_m3=ρ_air)
```

- `evaluate()` 校验 `pressure_curve`：至少 2 点、首点流量为 0、流量严格递增、压力严格递减且非负；非法时诊断 `FAN_CURVE_INVALID` 并回退默认曲线 `[[0,300],[2000,250],[4000,120],[5000,0]]`。
- 末点压力不为 0 时强制末点扬程为 0（满足泵曲线“零流量到零扬程”的求解约束），并诊断 `FAN_CURVE_CLIPPED`。
- 无流量信息时，`pressure_rise_pa` 按额定风量插值曲线：`Q_curve = nominal_flow/speed_ratio`，`p = interp(Q_curve)·speed_ratio²`；`shaft_power_w`/`electric_power_w` 在 evaluate 中给 0。
- `commit_step()` 用收敛通路流量与压差计算：

```text
P_hyd  = |Δp|·|m| / ρ_air
P_shaft = P_hyd / η_fan
P_elec  = P_shaft / η_motor
state.shaft_energy_j    += P_shaft·dt
state.electric_energy_j += P_elec·dt
```

并把 `shaft_power_w`、`electric_power_w`（以及实测 `pressure_rise_pa`）写入提交变量。

## 参数（canonical）

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `pressure_curve` | `[[0,300],[2000,250],[4000,120],[5000,0]]` | — | 流量 m³/h，压力 Pa |
| `nominal_flow_m3_h` | 2000 | ≥0 | 额定风量 m³/h |
| `speed_ratio` | 1.0 | [0.05, 2] | 转速比 |
| `efficiency` | 0.6 | [0.05, 1] | 风机效率 |
| `motor_efficiency` | 0.9 | [0.05, 1] | 电机效率 |
| `air_density_kg_m3` | 1.2 | ≥0.01 | 空气密度 kg/m³ |
| `air_viscosity_pa_s` | 1.8e-5 | ≥0 | 空气动力黏度 Pa·s |

## 变量

`pressure_rise_pa`（Pa）、`shaft_power_w`（W）、`electric_power_w`（W）、`state.shaft_energy_j`（J）、`state.electric_energy_j`（J）。

## 诊断码

| code | severity | 含义 |
| --- | --- | --- |
| `FAN_CURVE_INVALID` | warning | 曲线不满足校验，已回退默认曲线 |
| `FAN_CURVE_CLIPPED` | warning | 末点压力非 0，已强制末点扬程为 0 |

## 已知边界

- 空气密度/黏度按参数常量处理，不做随温度/压力的变物性迭代（由平台 `property_coupling` 承担）。
- `nominal_flow_m3_h` 仅用于 evaluate 阶段的压力显示，能量累计始终使用收敛流量与压差。
- 风机效率、电机效率为定值，未建模部分负荷曲线。

## 参考算例

默认参数、`m = 1 kg/s`、`Δp = 300 Pa`、`dt = 2 s`：

```text
P_hyd = 300·1/1.2 = 250 W
P_shaft = 250/0.6 = 416.67 W
P_elec  = 416.67/0.9 = 462.96 W
state.electric_energy_j = 925.93 J（> state.shaft_energy_j = 833.33 J）
```
