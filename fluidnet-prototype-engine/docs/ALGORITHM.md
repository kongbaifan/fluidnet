# 算法设计与实现边界

## 当前实现：稳态水力

输入为经过类型校验的 Project。所有计算使用绝对 Pa、kg/s、m。默认 `property_coupling='reference'` 时，液态水的水力物性固定为参考值（密度约 998.275 kg/m³，动力黏度约 1.0016e-3 Pa·s），边界温度只进入热力层，不改变水力结果；`'node'` 模式见下文「水力—热力耦合」。

编译顺序：

1. 合并模块目录默认值与实例已应用参数，按注册模型校验数值和范围。
2. 检查流体领域、必需端口、重复连接、通路与端口覆盖；未知算法不得退化成默认阻力。
3. 用并查集合并外部连接端口，以及 junction 的内部端口，形成等压节点。
4. 将 enabled 通路转换成有向支路；source 转换成固定绝对压力。
5. 检查同一节点的边界压力冲突，拒绝支路短接。
6. 按非关闭支路划分子网络，每个子网络必须有压力参考。关闭阀门两侧的压力也必须可以确定。

每个自由压力节点有一个压力未知量，每条支路有一个质量流量未知量。方向由通路 input_port → output_port 定义。

```text
支路： p_start - p_end - Δp(m) = 0
节点： Σ流入 m - Σ流出 m = 0
边界： p = p_boundary
```

节点守恒不施加于给定压力节点；边界自动提供或吸收净流量。in/out 仅为端口的标称方向，不阻止反向流。

## 支路关系

### 阀门

```text
Kv_eff = Kv × opening_ratio
Q = m / ρ × 3600                      [m³/h]
Δp = 100000 × (ρ/1000) × Q|Q| / Kv_eff²
```

开度与有效 Kv 暂按线性关系，不声称已实现等百分比阀特性。开度为零时改用 `m = 0`，不设置隐含泄漏量。

### 管道

```text
A = πD²/4
v = m/(ρA)
Re = |m|D/(μA)
Δp = f × L/D × m|m|/(2ρA²)
```

Re ≤ 2300 使用层流式 `Δp = 32μLm/(ρAD²)`；Re ≥ 4000 使用 Haaland 近似：

```text
f = [-1.8 log10((ε/D/3.7)^1.11 + 6.9/Re)]^-2
```

过渡区域对两种压降线性插值。这是明确的工程近似；水力关系暂不含内置管道的高程项、入口损失或可压缩性。粗糙度实际参与计算，相对粗糙度限定不大于 0.05。管道散热只影响焓，见「热力层」。

### 泵

曲线点为 `[Q_m3_h, H_m]`，要求从零流量开始、流量严格递增、扬程严格递减、末点扬程为零。区间内线性插值。

```text
H(Q,s) = s² × H_nominal(Q/s)
Δp = -ρgH
P_shaft = (-Δp) × (m/ρ) / efficiency_ratio
```

数值迭代可暂时线性延拓以定位根，但最终工作点超出有效曲线范围即失败。反向流和零转速模型尚未定义，不返回伪造结果。热力层把 `P_shaft` 全部计入流体焓升。

目录示例曲线为 `[[0,20],[10,18],[20,12],[30,0]]`。它用于内置算例联调，不是实际设备的试验曲线；真实工程应提交设备自身的 head_curve。

### 双侧换热器

ch0 与 ch1 分别使用各自的节点和流量，当前共用定义中的 K 和等效直径：

```text
Δp_side = K × m_side|m_side| / (2ρA²)
```

两侧流量不会互相覆盖。UA 不改变水力关系，在热力层按逆流 ε–NTU 计算两侧换热量与出口温度。只有 `SolverOptions.thermal=False` 时才返回 `THERMAL_NOT_SOLVED`，此时不产生出口温度。

## 求解与验收

使用 SciPy `least_squares`，压力变量与支路压力残差按 100000 Pa 缩放；节点质量残差按 1 kg/s 缩放，显式指定 `x_scale='jac'`。库的优化终止不等于物理合格，最终分别检查：

- 最大支路压力残差 ≤ pressure_tolerance_pa。
- 最大自由节点质量残差以及关阀流量误差 ≤ mass_tolerance_kg_s。
- 所有未知量有限，所有绝对压力为正，泵工作点在定义域内。

记录 `pressure_residual_pa`、`mass_residual_kg_s`、`iterations`（函数评估次数）、节点数和支路数；热力层另记 `thermal_iterations`、`coupling_iterations`、`energy_residual_w`、`reference_heat_w`。默认使用稠密数值 Jacobian。`SolverOptions.hydraulic_method='sparse'` 时按拓扑声明 Jacobian 结构（每条支路只依赖两端节点、Python 模块依赖其全部端口节点），信赖域子问题用 LSMR；`test_scaling.py` 检查三个原型算例两种方法逐变量一致。`scripts/benchmark_scaling.py` 在单原生线程下测量纯管道串联网络的稳态求解（本机 AMD Family 25 一次实测中位数）：

| 实例数 | dense | sparse |
| --- | --- | --- |
| 100 | 0.63 s | 0.25 s |
| 500 | 18.6 s | 0.95 s |
| 1000 | 103.9 s | 2.33 s |

这是一个结构简单的串联网络，不代表环状网络或含 Python 模块时的性能；连通分块尚未实现。

## 当前准稳态序列（没有状态设备的项目）

POST /runs 的 dynamic 模式产生 `0, dt, 2dt, …, duration` 序列，最后一个时刻准确截到 duration（同步最多 2001 帧；后台运行不限，也可以不设时长持续运行），返回 DYNAMIC_QUASI_STEADY。每一帧都完整求解一次水力与热力，不复用上一帧的结果；从第 2 帧起以上一帧的水力解、节点焓（`node` 模式还有支路物性）作为初值（热启动）。热启动只是初值：上一帧流量接近零的支路改从冷启动值 0.1 kg/s 起算（`q·|q|` 关系在零点斜率为零，否则阀门由关到开的帧会停在 gtol）；热启动仍未收敛时自动再按冷启动求解一次，两次都失败才报未收敛。请求不包含随时间变化的边界和参数，所以只有当 Python 模块的 `evaluate` 读取了 `state` 或 `time_s` 时，帧与帧之间的结果才会不同。

实测（原型示例网络）：热启动把每帧水力函数评估次数从 8 次降到 1 次；2001 帧在 `reference` 与 `node` 模式下都约 2.5–2.8 s。每个端口多出 5 个热力变量后，water-net 2001 帧完整历史序列化为 JSON 约 22.7 MB（每帧 247 个变量）；`thermal=False` 时不输出热力变量，约 11.9 MB（每帧 127 个）。运行记录在内存中保留最近 20 次。v0.3.1 起可用 `RunRequest.history='trend'`：只有约 50 个关键帧保留全部变量，其余帧只存曲线变量和模块状态，同一运行约 1.74 MB（见 API 文档“历史瘦身”）。

本节只适用于没有状态设备的项目；含水箱的项目改走下一节的隐式时间推进，帧时刻相同，但诊断为 `DYNAMIC_IMPLICIT_EULER`。v0.4 起没有状态设备的项目结果与 0.3.1 逐键一致。

每帧温度是该时刻的稳态代数解，不含管道热容等热惯性。v0.4.2 起前端的动态项目是一个后台会话：运行、单步、暂停、应用参数都作用于同一个 run_id，单步推进一帧且状态连续，不再新建运行（见 API 文档“运行生命周期与控制”）。运行中修改的参数从下一子步生效。准稳态序列仍不代表热惯性或流体动量的瞬态方程。

## 开式水箱与隐式时间推进（v0.4）

内置 `tank`（`solver_model='tank'`，`state_model='open_tank'`）是完全混合的开式水箱。两个端口都可选，与连接节点一样并成一个网络节点。状态是质量 M 和比焓 h：

```text
p_bottom = p_surface + g·M/A           （与密度无关）
level    = M / (ρ(p_bottom, h)·A)
```

参数：`level_m` 初始液位、`area_m2`、`height_m` 罐高（满箱液位）、`surface_pressure_pa`（默认 101325）、`temperature_k` 初始温度、`heat_input_w`、`heat_loss_ua_w_k`、`ambient_temperature_k`。编译期由初始液位求初始质量：`p = p_s + ρ(p, T)·g·level` 是不动点，6 次迭代到机器精度，所以第 0 帧的液位、底部压力和温度与参数一致。初始状态必须是液相（`PHASE_UNSUPPORTED`），`level_m` 不能超过 `height_m`。水箱本身是压力参考，同一节点上不能再有压力边界或第二个水箱（`STORAGE_CONFLICT`）；只由水箱提供压力参考的闭合回路可以求解。

**稳态与第 0 帧**：水箱按初始状态的固定压力、固定温度处理，相当于液位不变的大容器，诊断 `STEADY_TANK_AS_RESERVOIR`（仅稳态）。`state.net_inflow_kg_s` 是液位变化趋势。

**隐式 Euler 步**（从已接受状态 M_old、h_old 推进 h 秒）：

- 水力：水箱节点的未知量改为净流入 r（kg/s），平衡行为 `Σq_in − r = 0`，压力由 `p = p_s + g/A·(M_old + h·r)` 给出。不用压力作未知量，因为同一质量误差换成压力约为 `g·h/A` 倍，验收容差会小到 1e-14 Pa。水箱与网络在同一次 `least_squares` 中强耦合，未知量个数不变。
- 热力：水箱节点作为储能节点，行方程

  ```text
  h·(M_old/h_step + Σin w) = M_old·h_old/h_step + Σin w·h_in + Q_heater − UA·(T − T_amb)
  ```

  散热项按 `T ≈ h/cp + offset` 线性化，进入已有的 Picard 迭代。水箱作为温度种子，经过水箱的闭合回路不再需要 `THERMAL_REFERENCE_FROM_BOUNDARY`；无流动的水箱也照常更新（只有加热和散热）。质量为零且无流入的水箱保持上一焓值。
- 校核：每个水箱单独检查储能方程残差（相对 1e-6，加上 `10·UA·thermal_tolerance_k` 的线性化余量）；全网能量残差改为 `boundary_in + Σheat_w + reference_heat − Σ水箱净焓流`。帧指标另含 `storage_mass_rate_kg_s` 与 `storage_power_w`（`Σin w·h_in − Σout w·h + Q − UA·(T − T_amb)`）。
- 接受后 `M = M_old + h·r`，`h` 取热力解；热力层关闭时水箱温度保持初始值，`storage_power_w` 不输出。

**子步与重试**：输出帧仍是 `0, dt, …, duration`。每帧先试一个完整步；水力未收敛、热力/耦合未收敛、相态或物性失败时步长减半重试，最多 `SolverOptions.max_step_halvings`（默认 6）次，仍失败报 `STEP_NOT_CONVERGED`。模块错误、泵曲线越界等不是步长能解决的问题，不重试。失败的试算不改变任何状态；Python 模块在每个被接受的子步后 `commit_step`，`dt_s` 是实际子步长。

**液位事件**：试算步得到 M < 0（`TANK_EMPTY`）或液位 > 罐高（`TANK_FULL`）时，在该子步内二分步长到 `1e-6·dt`，接受仍在范围内的最大步，补发一帧事件时刻（不在 dt 网格上）的结果，然后以 failed 结束运行，保留全部已接受帧。

精度：一阶，未做局部截断误差估计；测试用线性 ODE 验证 dt 减半误差约减半。诊断 `DYNAMIC_IMPLICIT_EULER`（info）写明这一点。

## 管道热容（v0.4.1）

内置管道新增 `thermal_cells`（整数 0–50，默认 0）和 `wall_heat_capacity_j_k`（管壁热容 J/K，默认 0）。`thermal_cells=0` 就是 0.3 的代数管道，结果不变。N > 0 时管道分成 N 个完全混合的单元，每个单元的储能质量为 `M = ρ_up·V/N + C_wall/(N·cp_up)`（物性取上风节点，迭代中冻结），换热导纳 `G = UA/(N·cp_up)`。沿流向逐个单元：

```text
h_i·(M/dt + w + G) = M/dt·h_i,old + w·h_(i−1) + G·h_env
```

每个单元都是上风焓的线性函数，所以出口仍是 `a·h_up + c`，直接替换 `relations_for` 里该支路的关系，不改变节点方程。`h_env` 与代数管道相同：同相时取 `h(p_down, T_amb)`，跨相时只计显热。位能项加在出口。反向流时按相反顺序遍历单元，单元数组始终按 in0→out0 存放。

- 稳态与第 0 帧：`M/dt` 项去掉，单元处于 N 段串联的稳态分布，出口 `h_env + (h_in − h_env)·(w/(w + G))^N`。N → ∞ 时趋于代数管道的指数解，误差约与 1/N 成正比（25 段时 60 °C 进水、UA 2000 W/K 的例子约差 0.007 K）。输入不变的动态运行因此保持在第 0 帧的分布上。
- 无流动的管段：稳态取起点节点的焓；隐式步中各单元只与环境换热，`h_i = (M/dt·h_i,old + G·h_env)/(M/dt + G)`。
- 储热功率 `state.stored_power_w = Σ M·(h_i − h_i,old)/dt`。绝热管段的支路 `heat_w` 恰好等于 `−stored_power_w`；帧指标 `storage_power_w` 把水箱与管段一起计入。`state.mean_temperature_k` 按两端压力平均值把各单元焓换算成温度后取平均。
- 只要有管段的 `thermal_cells > 0` 且热力层开启，动态运行就走隐式时间推进（与水箱相同的子步、减半与诊断）；热力层关闭时管道热容不计算，运行仍是准稳态，也不输出两个 state 变量。

## 热力层（`SolverOptions.thermal=True`，默认开启）

做法参考倍思鹿教程：端口以**压力 + 比焓**为状态。网络先解压力和流量，再按收敛流量的方向把焓从上风侧传到下风侧，其余物性由压力和焓查得。每条支路按流量符号确定上风端 `up` 与下风端 `down`，`w = |m|`；未知量为节点焓 `h[n]`。

### 支路出口焓

| 支路 | 关系 |
| --- | --- |
| 内置阀门、局部阻力 | 等焓 `h_out = h_up` |
| 内置管道 | `h_out = h_env + (h_up − h_env)·exp(−UA/(w·cp))`；`h_env = h(p_down, T_ambient)`；UA=0（默认）为等焓 |
| 内置泵 | `h_out = h_up + P_shaft / w`，轴功全部进入流体 |
| 内置换热器 ch0/ch1 | 逆流 ε–NTU，见下 |
| Python 模块通路 | `h_out = h_up + (heat_w + P_shaft) / w`；默认 `heat_w=0` 即等焓。`w` 不大于零流量阈值而 `heat_w≠0` 报 `NO_FLOW_HEAT` |
| Python `pump`/`compressor` 关系 | `P_shaft = Δp·w/ρ`（水力功率；关系不带效率，损失由模块用 `heat_w` 另行声明） |
| 关系或参数带 `height_m` | 另加 `−g·Δz`（沿流向升高时焓减小），与水力关系一致 |

管道 `cp` 取上风状态。`UA` 为参数 `heat_loss_ua_w_k`，环境温度为 `ambient_temperature_k`。管道散热只对内置管道生效；Python 模块用 `ctx.net.*(heat_w=...)` 自行声明吸放热。

液态水节流按等焓处理，出口压力较低，所以温度会略升：water-net 中 V1 出口比泵出口高约 0.02 K。这是真实的物性结果，不是数值误差。

### 换热器（ε–NTU，标称逆流）

```text
C_a = w_a·cp_a,  C_b = w_b·cp_b          cp 取各侧上风状态
C_min = min(C_a,C_b); C_r = C_min/C_max; NTU = UA/C_min
逆流：ε = (1-exp(-NTU(1-C_r))) / (1-C_r·exp(-NTU(1-C_r)))；C_r = 1 时 ε = NTU/(1+NTU)
顺流：ε = (1-exp(-NTU(1+C_r))) / (1+C_r)
Q = ε·C_min·(T_in,a − T_in,b)            a 侧 −Q/w_a，b 侧 +Q/w_b
```

a 为 ch0，b 为 ch1。标称布置为逆流；只有一侧流向反转时两股流同向，改用顺流公式，两侧都反转仍为逆流。热侧、冷侧由两侧入口温度决定，`Q` 符号随之变化；流向反转后按新的上风端重新取入口。`UA ≤ 0` 时不换热；任一侧流量不大于零流量阈值时 `Q = 0`，给 `THERMAL_EXCHANGER_NO_FLOW` 提示。两侧换热量等值反号。`T` 对 `h` 的关系在当前状态附近线性化（`T ≈ h/cp + 偏置`），所以 `Q` 在每轮线性方程中是节点焓的线性函数。

heat-loop 示例（UA = 2000 W/K，`reference` 模式）：热侧 65.002 → 62.741 °C，冷侧 25.002 → 27.307 °C，换热量约 75.4 kW，全网能量残差约 1e-10 W。与归档 v0.2 内核（IF97）同参数对照，出口温度相差 5.8 mK 与 2.2 mK，换热量相对差约 6e-5。

### 节点混合与边界

节点方程采用混合形式，对角元取到达该节点的流量：

```text
h_n·(Σ流入 w + 补给 q_b) = Σ流入 w·h_out + 补给 q_b·h_b
```

流出支路和汇入边界都带走 `h_n`。用流入而不用流出写对角元，是因为关阀等情况下流出量会差一个质量残差（约 1e-11 kg/s），流出形式会让方程病态。

零流量阈值为 `max(1e-12, mass_tolerance_kg_s)`：流量不大于阈值、关闭或开度为零的支路不传递焓。压力边界的净交换量等于该节点支路流量的代数和，不大于 `mass_tolerance_kg_s × 节点数` 的视为数值噪声。向网络补给时 `h_b = h(p, T_boundary)`；吸收时不约束节点焓。

- 同一节点两个压力边界温度不同：编译期 `BOUNDARY_TEMPERATURE_CONFLICT`（仅 `thermal=True` 时检查）。
- 没有任何流动经过的停滞节点（如关阀支路两侧）：保持初值，即本节点的边界温度；没有时取所在水力连通分量中第一个边界的温度，再没有时取 293.15 K。给 `THERMAL_STAGNANT_NODE` 提示。
- 闭合回路：从补给边界和有散热的管道出口出发沿流向做可达性搜索。搜索不到的节点按强连通分量分组，对没有外部来流的每个分量，固定其中一个节点的焓为参考温度，优先选压力边界节点。给 `THERMAL_REFERENCE_FROM_BOUNDARY` 警告，该参考点为维持平衡而吸收或放出的热量记入 `metrics.reference_heat_w`（负值为移出）。只有泵、没有散热的闭合回路中，`reference_heat_w` 正好等于负的泵轴功率，泵热不会被静默吞掉。分量内连可作参考的边界温度都没有时报 `THERMAL_REFERENCE_MISSING`。

### 求解与校核

沿用归档 v0.2 热力层的做法组装稀疏线性方程，用 `spsolve` 求解。只有等焓、泵和 `heat_w` 的网络是线性的，一次求解即得结果。有换热器或散热管道时需要迭代：每轮用当前焓求各节点 T 与 cp，重建关系再求解；第一轮直接采用新解，之后新旧值按 0.7/0.3 阻尼。`max|Δh|/cp < thermal_tolerance_k`（默认 1e-6 K）时收敛；超过 `max_thermal_iterations`（默认 50）报 `THERMAL_NOT_CONVERGED`。矩阵奇异报 `THERMAL_REFERENCE_MISSING`，解不是有限数报 `THERMAL_NOT_FINITE`。

收敛后每个节点和每股出口流用压力和焓查一次物性。进入两相，或者进入与所在水力连通分量的压力边界不同的单相（例如液态回路汽化成气相），报 `PHASE_UNSUPPORTED` 并带实例 ID。允许的相态按连通分量分别取自该分量的边界状态：纯空气等单相气体网络同样可以计算，另一条无关的气相管线也不会让液态回路被误判为合法的过热蒸汽（其水力仍按液态密度计算）。

能量校核：补给焓流 − 汇入焓流 + Σ 各支路 `w·(h_out − h_in)`（即散热、泵轴功、`heat_w`、换热和位能的合计）+ `reference_heat_w`，结果记为 `metrics.energy_residual_w`。其绝对值超过 1e-6 × 全网焓流规模时报 `THERMAL_ENERGY_IMBALANCE`。

### 端口与通路取值

- 按实际流向作为出口的端口：该支路出口流在节点混合前的状态。反向流时是标称的 `in` 端口。
- 向网络补给的压力边界端口：边界给定状态。
- 其余端口（入口、连接节点、吸收流量的压力边界）：所在节点的混合状态。吸收边界端口显示的是到达那里的流体温度，例如 water-net 的 `B2.out0.temperature_k` 约为 293.196 K，包含泵温升；边界设定值仍在 `B2.param.temperature_k`。
- 每条通路另给 `inlet_temperature_k`（上风侧节点）、`outlet_temperature_k`（下风侧出口流）和 `heat_w`。`heat_w = w·(h_out − h_in)` 是流体焓流增量，包含换热、轴功和位能，不只是吸热量；变量 ID 保持 `heat_w` 以免破坏已有引用，显示名为“流体焓流增量（换热+轴功+位能）”。

## 水力—热力耦合

`SolverOptions.property_coupling` 决定物性是否回到水力求解：

| 模式 | 流程 | 用途 |
| --- | --- | --- |
| `reference`（默认） | 水力一次（参考常数 ρ、μ）→ 热力一次 | 单向。水力结果与接入热力层之前一致，回归基准 3.582677 / 2.346313 kg/s 不变 |
| `node`（可选） | 支路 ρ、μ 初值取参考值；循环「水力 → 热力 → 支路物性取上下游节点平均」 | 双向。变温、变密度工况 |

`node` 模式参考倍思鹿的轮间更新：网络求解期间物性冻结，下一轮再用新的压力和焓更新，不在 Newton 的每次函数评估中调用物性库。支路物性取上下游节点平均，对应教程中的 `DENSITY = (IM0_VOLUME + EX0_VOLUME) / 2`。`max|Δρ/ρ| < coupling_density_rtol`（默认 1e-6）且 `max|ΔT| < thermal_tolerance_k` 时收敛；超过 `max_coupling_iterations`（默认 20）报 `COUPLING_NOT_CONVERGED`。

heat-loop 示例：`node` 模式下热侧 65 °C 水的密度、黏度回到水力，热侧流量为 7.784 kg/s，`reference` 模式为 7.901 kg/s；耦合 4 轮收敛。

Python 模块的 `evaluate` 试算端口：
- `reference` 模式：T、h 取热力初值（所在分量的边界温度、边界压力），ρ、μ 仍为参考常数，保证水力结果与接入热力层之前一致。
- `node` 模式：上一轮冻结的节点 T、h、ρ、μ、cp；第一轮用热力初值。

`commit_step` 的 `converged_ports` 两种模式都给收敛后的完整端口状态，含温度、焓、密度、黏度、比热、干度和流量。模块在关系中显式提交的密度或黏度在水力关系中优先。

`thermal=False` 完全走接入热力层之前的路径：水力结果相同，端口温度取实例参数 `temperature_k`（压力边界为给定温度，其余为空），其余热力变量不出现在帧中（键集合与 0.2 相同，只多了管道两个新参数），换热器返回 `THERMAL_NOT_SOLVED`，不检查边界温度冲突。

## 物性服务

`properties.py` 使用 CoolProp `AbstractState`，一次 flash 读取 h、ρ、μ、cp、k、s、u、cv、声速、相态和干度，不再每项物性调用一次 `PropsSI`。AbstractState 带内部状态，后台运行有 2 个线程，因此每个线程各持一份。服务实例按 `(backend, 解析后的工质, phase_policy)` 缓存；查询结果按解析后的工质和输入缓存（同一工质的不同相态策略共用，`Water` 与 `HEOS::Water` 视为同一工质），返回副本，调用方修改不影响后续结果。

工质字符串（v0.3.1，v0.4.4 增加 REFPROP）：

| 写法 | 含义 |
| --- | --- |
| `Water`、`Ammonia`、`R134a` | 默认 HEOS 后端（CoolProp 纯工质） |
| `HEOS::R134a`、`IF97::Water` | 显式后端；IF97 只支持水 |
| `INCOMP::MEG[0.3]` | 不可压溶液，方括号为质量分数（此例为 30 % 乙二醇水溶液） |
| `REFPROP::WATER`、`REFPROP::R134A` | REFPROP 纯质（v0.4.4，名称用 REFPROP 的工质文件名） |
| `REFPROP::R407C.MIX` | REFPROP 预定义混合物 |
| `REFPROP::R32[0.5]&R125[0.5]` | REFPROP 按组分混合；比例按 `FluidConfig.reference` 解释（`mass` 默认，`mole` 摩尔分数），和必须为 1 |
| `A&B`、`HEOS::Water[0.5]` | 报 `COMPOSITION_UNSUPPORTED`（HEOS 混合物尚未接入；混合物请用 REFPROP） |

REFPROP（v0.4.4）：用户自备 NIST 许可的 REFPROP，`REFPRP64.DLL` 和同版本的 `fluids/`、`mixtures/` 放在默认安装目录 `C:\Program Files (x86)\REFPROP` 或环境变量 `FLUIDNET_REFPROP_PATH` 指定的目录；软件不附带也不提交这些文件。经 CoolProp 的 REFPROP 后端调用（本机验证 9.1），与其他后端同一接口，Python 模块的 `ctx.fluid` 照常可用。

- 版本保护：DLL 读到其他版本的工质文件会在 Fortran 内直接终止进程（实测 9.1 DLL + 10 工质文件 `forrtl severe 59`）。因此每种 REFPROP 工质第一次使用前，先在一个临时子进程里加载一次；子进程失败只报 `PROPERTY_FAILURE`，服务继续运行。Worker 进程在 API 进程编译之后启动，不再重复探测。
- 线程：DLL 只有一份全局工质设置，所有 REFPROP 调用经同一把锁串行；不同工质交替查询结果不串。
- 混合物相态：REFPROP 后端对混合物没有 `phase()`，按干度判断：Q < 0 液相，0 ≤ Q ≤ 1 两相（含饱和线），Q > 1 气相；温度、压力都超过临界值为超临界。非共沸混合物的泡点与露点不同（R407C 在 1 MPa 下温度滑移约 5.6 K），`saturation_t/p` 给泡点，露点用 `state_pq(p, 1)`。
- 输运性质：REFPROP 对部分工质和混合物没有黏度、导热方程（如氨水），这时这两项为 `None`，不算失败；但管网水力需要黏度，参考状态没有黏度的工质在求解时报 `PROPERTY_FAILURE`。
- 纯质与 CoolProp HEOS 基本一致：水、CO₂、R134a 的密度相对差 < 1e-12，氨约 2e-5（方程版本不同）。`REFPROP::WATER` 不算“纯水”的固定参考物性，水力参考物性按 REFPROP 计算，所以和 `Water` 的结果有 1e-5 量级的差别。
- 单次 PT flash 约 36 µs（加锁后）；每种工质首次使用多约 1 s（探测子进程）。

INCOMP 溶液没有 `phase()`，一律按液相；它没有饱和状态，`state_pq/state_tq/saturation_*` 报 `PROPERTY_FAILURE`；声速为 `None`。

查询方法：`state_pt(p,T)`、`state_ph(p,h)`、`state_ps(p,s)`（等熵压缩等）、`state_pq(p,Q)`、`state_tq(T,Q)`、`saturation_t(p)`、`saturation_p(T)`、`limits()` 与湿空气 `humid_air(T,p,rh)`（含湿量、露点、湿球、单位干空气焓；只给模块用，不进网络）。Python 模块通过 `ctx.fluid` 直接调用。饱和查询是显式的两相请求，不受 `phase_policy` 约束。两相区内部（0 < Q < 1）黏度、导热、cp、cv、声速为 `None`；饱和线上（Q = 0 或 1）这些量按 CoolProp 给出。

`limits()` 返回 `t_min_k`、`t_max_k`、`p_max_pa`（未知为 `None`）。水为 273.16–2000 K，液氨 195.5–725 K；INCOMP 的下限取凝固点（CoolProp 不直接提供，按 1 atm 二分求得，MEG30 约 −14.58 °C），没有压力上限。

编译期按项目工质检查范围，取代旧的固定 1–90 °C：

- 工质字符串无效：`FLUID_UNKNOWN`（未知名称）或上表对应码，`field='fluid'`。查询时遇到未知工质仍报 `PROPERTY_FAILURE`。
- 压力边界温度、管道环境温度超出 `limits()`，或边界压力超过 `p_max_pa`：`PARAMETER_RANGE`，消息写明工质和允许范围。
- 压力边界状态违反 `phase_policy`：沿用 `PHASE_UNSUPPORTED`。
- 水边界必须是液相（`reference` 模式水力按液态水常数计算）：例如 2.5 bar、150 °C 报 `PHASE_UNSUPPORTED`（与热力层相态检查同码）；95 °C 在该压力下为液相，可以计算。这一检查只在 `thermal=True` 时进行，`thermal=False` 保持 0.3.0 的行为。
- 所有纯水写法（`Water`、`water`、`HEOS::Water`、`IF97::Water`）在 `reference` 模式下都用同一组参考常数，水力结果完全相同。
- `reference` 模式只用一个参考密度：任一节点密度与参考值相差超过 2% 时给 `REFERENCE_DENSITY_DEVIATION` 警告（例如 95 °C 热水 961.9 kg/m³，偏离 3.6%），提示需要时改用 `property_coupling='node'`。
- 管道环境温度与流体不在同一相态时（例如 1.2 bar 水管外 150 °C 环境），散热只按显热计算：`h_env ≈ h_up + cp·(T_amb − T_up)`，不把汽化潜热算作可传递热量。

实测单次查询（水）：`state_pt` 未命中缓存约 37 µs（v0.3.1 每次多读 s、u、cv、声速后约 49 µs）、命中约 2.5 µs，`state_ph` 未命中约 115 µs（压力—焓 flash 需要迭代）；原先每项一次 `PropsSI` 的 `state_pt` 约 564 µs。

`state_ph` 直接用压力和焓求解（`HmassP_INPUTS`），不再先反算温度再按压力和温度查询。两相时 `phase='twophase'`、`quality ∈ [0,1]`；单相时 CoolProp 给出 Q=-1，映射为 `None`。两相状态下 CoolProp 的黏度、导热系数和定压比热只是单侧值，三者都置为 `None`。压力不大于零或输入非有限报 `PROPERTY_RANGE`。

| `phase_policy` | 拒绝 |
| --- | --- |
| `single_phase`（默认） | 两相 |
| `liquid` | 含气相的状态与两相 |
| `gas` | 含液相的状态与两相 |
| `any` | 不拒绝，供模块代码查询两相状态 |

网络流动的相态另由热力层按边界相态检查（见上文）。默认 `reference` 模式下水力用常数，热力层本身调用 CoolProp。HEOS 与归档 v0.2 使用的 IF97 存在约 1e-4 量级的相对差，只影响两者对照的容差。

## PID 控制器（v0.4.2）

PID 是项目级对象（`Project.controllers`），不进入网络方程。每个控制器读一个帧变量 y，写一个 `runtime=true` 的数值参数 u：

  e = setpoint − y
  u = clamp(kp·e + I + kd·D, minimum, maximum)
  I ← I + ki·e·Δt（条件积分：增长只到恰好饱和的值，饱和后反向误差立即退出饱和）
  D ← D + α·(−Δy/Δt − D)，α = Δt / (sample_s + Δt)（微分作用在测量值上，一阶滤波）

- 采样：t=0 在初始解上采样一次，此后每 `sample_s` 一次。时间推进把子步截到采样时刻，所以采样总落在已接受的状态上；两次采样之间输出零阶保持。
- 生效：采样后的输出在下一子步开始前写入参数（阀门开度为 0 时同时把支路设为关闭），已发布的帧不改。
- 失败的试算（子步减半重试）不触发采样，PID 的时钟、积分和微分都不前进。
- 第一次采样和手自动切换无扰：把积分设成使输出等于当前值。手动时输出 `manual_output`，积分跟踪，切回自动不跳变。
- 运行中 `controller` 命令可改 setpoint、mode、manual_output，下一子步立即重新采样。

验收：液位示例纯比例控制的静差与阀门特性的解析平衡点一致（`test_pid.py`）；PI 控制液位收敛到 1.5 ± 0.005 m，温控示例收敛到 30 ± 0.2 °C 且输出始终在限幅内。

## 运行中隔离的被动管段（v0.4.2）

参考倍思鹿 V1.1 说明“两阀均关闭后压力转换为容积性质”。运行中阀门关闭可能产生没有压力参考的子网络。每个子步重新做连通性检查：这样的子网络如果只含管道、阀门、阻力和换热器，就把其中 ID 最小的节点固定为上一接受步的压力和温度。零流量下整个子网络压力相等，温度由管道热容和散热照常演化，不计算液体热膨胀引起的压力变化；诊断 `ISOLATED_PRESSURE_HELD`。重新开阀后从保持的压力继续。含泵或 Python 模块的隔离子网络报 `ISOLATED_ACTIVE_NETWORK`；编译期就没有压力参考的子网络仍报 `PRESSURE_REFERENCE_MISSING`。

## 多工质（v0.4.5）

编译器在端口节点上再做一次并查集：连接、节点和水箱已经并到同一节点，再并上每个设备启用的内部通路（不看阀门开度）。每个连通块是一个回路，回路按最小节点号编号。工质只通过换热器这类“两侧无通路”的设备接触，所以每条支路都在一个回路内。

- 水力：`reference` 模式下每个回路一对参考密度/黏度，参考压力取该回路压力边界和水箱初始压力的平均，参考温度取该回路第一个带温度参数的设备；支路用所在回路的值。`node` 模式本来就按支路取两端节点物性。
- 热力：每个节点用所在回路工质的物性服务（边界状态、焓→温度、管道环境、闭合回路参考）。换热器 ε–NTU 的两侧热容量率各用各的比热，能量残差仍按焓流全网校核。
- 编译期范围检查、水箱初始质量与液位事件都用设备所在回路的工质；同一回路只允许一种相态族的规则不变。
- 所有回路工质相同时走原来的单工质路径。

## 后续状态算法（未实现）

尚未实现：管网内两相流（均相模型、相变换热器、闭式两相罐）。

不在计划内：管道流动惯性（倍思鹿 `RLS`）、两位式滞环控制、气垫或气液两相闭式罐、满箱溢流与空箱断流的切换、BDF2 或时间误差控制、Python 模块自定义微分状态、两相水力、完整可压缩气体网络、混合物、相变和水锤。
