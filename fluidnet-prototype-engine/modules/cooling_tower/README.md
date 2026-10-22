# 冷却塔参考模块

水侧按圆管阻力关系注册到 `main` 通路，空气侧以**进风湿球温度**为冷源，用逆流 ε-NTU 法计算换热量：

```text
C_w = m_w·cp_w
C_a = V̇_air·ρ_air·cp_air
C_min = min(C_w, C_a)，C_r = C_min/C_max，NTU = UA/C_min
ε = (1 − e^(−NTU(1−C_r))) / (1 − C_r·e^(−NTU(1−C_r)))   （C_r < 1）
ε = NTU/(1+NTU)                                        （C_r = 1）
Q = ε·C_min·(T_water,in − T_wb)
```

- 水侧流量优先取 `in0` 端口质量流量；`evaluate()` 中流量为 `None` 时，用试算压差按与求解器相同的 `pipe_drop` 摩擦律二分反解（函数由 `fan_coil_unit` 复制，注释已标注与 `solver.py` 同步）。
- 进水温度优先取 `in0` 端口温度，缺失时回退进风干球温度；水/空气密度、比热缺失时回退同名参数。
- 输出量：`heat_flow_w = −Q`（水侧换热量，负=水放热）、`water_outlet_temperature_k = T_in − Q/C_w`、`air_outlet_temperature_k = T_air,in + Q/C_a`、`effectiveness`、`approach_k = T_water,out − T_wb`。
- 水侧热流通过 `ctx.net.pipe(..., heat_w=heat_flow_w)` 施加到出口焓；模块**不输出** `heat_w`，避免覆盖平台为单通路实例生成的 `<实例>.heat_w` 别名。
- `commit_step()` 用收敛通路流量重算 Q，并累计 `state.thermal_energy_j += heat_flow_w·dt`（负值）。
- 零水流量 / UA≤0 / 风量为零时 `heat_flow_w = 0`，但仍注册管道关系，变量保持齐全。

## 参数（canonical）

| 参数 | 默认 | 范围 | 单位 |
| --- | --- | --- | --- |
| `ua_w_k` | 20000 | ≥0 | W/K（显示 kW/K） |
| `water_side_diameter_m` | 0.1 | ≥1e-4 | m（显示 mm） |
| `water_side_length_m` | 2 | ≥0 | m |
| `roughness_m` | 1.5e-6 | ≥0 | m（显示 mm） |
| `air_flow_m3_s` | 3 | ≥0 | m³/s |
| `air_inlet_temperature_k` | 300.15 | ≥1 | K（显示 °C） |
| `air_inlet_relative_humidity` | 0.5 | [0,1] | 1（显示 %） |
| `air_wet_bulb_temperature_k` | 300.15 | ≥1 | K（显示 °C） |
| `air_density_kg_m3` | 1.15 | ≥0.01 | kg/m³ |
| `air_cp_j_kg_k` | 1006 | ≥100 | J/(kg·K) |
| `water_cp_j_kg_k` | 4180 | ≥100 | J/(kg·K) |
| `density_kg_m3` | 998.2 | ≥1 | kg/m³ |
| `viscosity_pa_s` | 0.001 | ≥0 | Pa·s（显示 mPa·s） |

## 诊断码

| code | severity | 含义 |
| --- | --- | --- |
| `CT_LATENT_IGNORED` | info | 干空气显热模型，未计蒸发潜热 |
| `CT_ZERO_WATER_FLOW` | warning | 水侧流量 ≤1e-6 kg/s，本帧不换热 |
| `CT_UA_DISABLED` | warning | UA ≤0，仅水力阻力 |
| `CT_AIR_FLOW_ZERO` | warning | 风量或空气密度 ≤0，风侧无热容 |
| `CT_PRESSURE_UNKNOWN` | warning | 端口压力缺失，无法反解流量 |

## 已知边界

- 干工况显热模型：以湿球温度为冷源，但未计蒸发潜热与水损失；高湿/高温差工况出水温度偏保守。
- `air_inlet_relative_humidity` 当前仅作输入记录，未参与传热计算。
- 变物性不在此模块内迭代，由平台 `property_coupling='node'` 承担。

## 参考算例

`m_w = 3 kg/s`、`T_water,in = 310.15 K`、`T_wb = 300.15 K`、`V̇_air = 3 m³/s`、`UA = 20000 W/K`：

```text
C_w = 12540 W/K，C_a = 3470.7 W/K，C_r = 0.2768，NTU = 5.763
ε ≈ 0.9888，Q ≈ 34.3 kW
heat_flow_w ≈ −34316 W，T_water,out ≈ 307.41 K，approach ≈ 7.26 K
```
