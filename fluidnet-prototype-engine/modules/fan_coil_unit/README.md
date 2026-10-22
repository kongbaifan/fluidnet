# 风机盘管机组参考模块

水路按圆管阻力关系注册到 `main` 通路，空气侧用 ε-NTU 法计算换热量：

```text
C_w = m_w·cp_w
C_a = V̇_air·ρ_air·cp_air
C_min = min(C_w, C_a)，C_r = C_min/C_max，NTU = UA/C_min
ε = (1 − e^(−NTU(1−C_r))) / (1 − C_r·e^(−NTU(1−C_r)))   （C_r < 1）
Q = ε·C_min·(T_air,in − T_water)
```

- 水侧流量、密度、比热和温度优先取 `in0` 端口值，缺失时回退同名参数。
- `evaluate()` 拿不到端口流量，用试算压差按与求解器相同的 `pipe_drop` 摩擦律二分反解水侧流量；`commit_step()` 用收敛后的真实流量重算。
- 任一侧热容或 UA 不大于零时 `heat_w = 0`，但仍注册管道关系。
- `evaluate()` 输出 `heat_flow_w`（水侧换热量，平台另有单通路别名 `<实例>.heat_w`）、`air_outlet_temperature_k`（`T_air,in − Q/C_a`）和 `effectiveness`；`commit_step()` 累计 `state.thermal_energy_j`。模块不输出 `heat_w`，避免覆盖求解器变量。
- 空气湿度参数用于露点提示，当前按干空气显热计算（干工况）。
