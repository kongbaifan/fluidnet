# 等百分比调节阀参考模块

`main` 通路向求解器注册一条 `valve` 阻力关系。`evaluate()` 复刻倍思鹿
`截止阀_Run.cpp:78-96` 的等百分比特性：

```text
CVF = (ALF^(opening-1) + LF) / (1 + LF) - 1/ALF     # 结果夹到 ≥ 0
kv_eff = kv_rated · CVF
```

- `ALF`（`rangeability_alf`，默认 100）是可调比：`opening=1` 时 `CVF=1-1/ALF=0.99`，
  `opening=0` 时 `CVF=1/ALF-1/ALF=0`。
- `LF`（`leakage_fraction`，默认 0）是泄漏系数；倍思鹿代码里强制 `LF=0`，
  这里保留参数以便标定时做敏感性分析。`LF` 只抬高低开度段，不改变全开点。
- 阀门关系按 `kv_eff = kv_rated·CVF`、`opening=1` 提交；`opening≤0` 或
  `CVF≤1e-9` 时按 `opening=0` 提交。求解器把零开度阀门支路当作零流量约束，
  因此 0% 开度是**精确零流量**，不是小泄漏。
- 密度优先取 `in0` 端口值，缺失时回退参数 `density_kg_m3`。
- `commit_step()` 用收敛流量累计 `state.throughput_kg`。

## 与内置线性 `valve` 的差异

内置阀门按 `kv_eff = kv_rated·opening` 线性缩放；本模块在相同开度下给出等百分比
`CVF`。`ALF=100` 时：

| opening | CVF | 相对内置线性阀门的 Kv 比 |
| --- | --- | --- |
| 1.0 | 0.990000 | 0.990 |
| 0.5 | 0.090000 | 0.900 |
| 0.1 | 0.005849 | 0.585 |

相同压差、无其他阻力时，50% 开度流量约为全开的 `0.09`（内置线性阀为 `0.5`），
相差约 5.6 倍。这正是 `docs/MAPPING_A.md` V-4 记录的量化缺口。

## 参数（canonical）

| 参数 | 默认 | 范围 | 说明 |
| --- | --- | --- | --- |
| `kv_m3_h` | 16 | ≥0.001 | 额定流量系数 Kv（m³/h） |
| `opening_ratio` | 0.5 | [0,1] | 阀门开度 |
| `rangeability_alf` | 100 | [1,1000] | 可调比 ALF |
| `leakage_fraction` | 0 | [0,0.5] | 泄漏系数 LF |
| `density_kg_m3` | 998.2 | ≥1 | 参考密度 kg/m³ |

## 变量

`cvf`（1）、`effective_kv_m3_h`（m³/h）、`state.throughput_kg`（kg）。

## 公式来源

- 曲线与夹紧：`倍思鹿源码/截止阀_Run.cpp:78-96`。
- 倍思鹿侧 `ALF=100` 硬编码、`LF=0`：`截止阀_Run.cpp:69-72`。
- FluidNet 阀门压降式：`backend/fn_engine/solver.py` 的 `branch_drop`，
  `Δp = 1e5·(ρ/1000)·Q|Q|/Kv_eff²`。
- 映射记录：`docs/MAPPING_A.md` §3.2 与 V-4。

## 已知边界

- 不包含执行器速率限制（倍思鹿 `AUTO` 每步 ±0.005 的开度斜坡）与回差/滞环；
  需要时用 PID 或 Python 控制脚本在参数层实现。
- `CVF → Kv` 的基准沿用 `kv_m3_h` 参数，倍思鹿 `VALVECV_SHUT` 内部的
  `DN`/几何换算不可见；实际 Kv 仍需一次倍思鹿标定（V-4 待回填）。
- 不含闪蒸/汽蚀、两相与可压缩修正；反向流仍按同一平方律反号。
- `LF` 只是曲线参数，不代表可计算的外部泄漏流量。
