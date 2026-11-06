# 风冷冷凝器：环境空气边界与有限风量换热

新增模块与求解模型均为 `air_cooled_condenser`，界面名称“风冷冷凝器”。它用于集总制冷站：`in0` 为排气进口，`out0` 为冷凝液出口，两端属于同一个制冷剂高压等级，排热进入该等级的容器能量方程。空气侧是用户指定的环境边界，没有空气端口，也不接入湿空气或风管网络。

本轮提供设备物理关系与公开合同，不含厂家性能表、换热面积选型、制冷剂管路压降、过热气冷却段、过冷段、实际风机工作点或盘管储热。制冷剂温度取压力等级的饱和温度；模块名称不意味着已经解析实际冷凝流动。

## 参数与单位

| 参数 | 引擎默认值 | 界面显示 | 运行中修改 | 含义 |
| --- | --- | --- | --- | --- |
| `ua_w_k` | 4000 W/K | 4 kW/K | 否 | 强制风侧盘管 UA；本版假定恒定，不随风速、物性或结霜改变 |
| `rated_air_mass_flow_kg_s` | 5 kg/s | 5 kg/s | 否 | 额定有效掠过换热面的空气质量流量，假定已排除旁通 |
| `air_specific_heat_j_kg_k` | 1006 J/(kg·K) | 1.006 kJ/(kg·K) | 否 | 空气定压比热，用户给定的常数 |
| `air_inlet_temperature_k` | 303.15 K | 30°C | 是 | 环境进风干球温度，不使用湿球温度 |
| `fan_ratio` | 1 | 100% | 是 | 风机转速比，范围 0–1；0 表示停风 |
| `fan_power_w` | 1000 W | 1 kW | 否 | 额定风机电功率 |
| `natural_ua_w_k` | 0 W/K | 0 kW/K | 否 | 独立自然散热通道，默认关闭；启用后在所有转速下并联存在 |

UA、自然导热系数、风机功率必须非负；额定风量、比热与绝对温度必须为正，所有数值必须有限。超速工况拒绝，未用裁剪掩盖越界值。压力或物性无效时按既有设备错误传播，由调用方附加设备标识。

`natural_ua_w_k` 不属于已声明强制风流量的空气通道，不计入强制风出口温度；它代表另一个与环境直接交换热量的通道。若输入的 UA 已包含整机自然散热，则应保持该参数为 0，避免重复计算。额定值是可复算的教学假设，不是厂家标定数据。

## 换热与功率关系

设风机转速比为 (r)，制冷剂饱和温度为 (T_s)，环境干球温度为 (T_a)：

\[
\dot m_a = \dot m_{a,rated} r,\qquad
C_a=\dot m_a c_{p,a},\qquad
\Delta T=T_s-T_a.
\]

当 (C_a>0) 时，制冷剂侧近似等温相变，空气侧一维能量关系为

\[
C_a\,dT_a=(T_s-T_a)\,d(UA).
\]

从入口到出口积分可得

\[
NTU=\frac{UA}{C_a},\quad
\varepsilon=1-e^{-NTU},\quad
G_f=\varepsilon C_a,\quad
Q_f=G_f\Delta T,\quad
T_{a,out}=T_a+\varepsilon\Delta T.
\]

因此无自然通道时，排热受空气热容量流率限制，即使 UA 极大，出口温度也不能越过制冷剂饱和温度。实现使用 `-expm1(-NTU)`，避免很小 NTU 时 `1-exp(-NTU)` 的相减消失。零强制风量时 (G_f=Q_f=0)，出口温度返回 `None`：没有流出的空气，不能显示成一股温度已知的风流。

自然通道与净排热分别为

\[
Q_n=G_n\Delta T,\qquad Q=Q_f+Q_n,\qquad
G_{effective}=G_f+G_n.
\]

所有换热量保留符号。环境温度高于制冷剂饱和温度时 (Q<0)，表示环境向制冷剂加热；不会把它截成 0 或宣称仍在冷凝。`reverse_heat_flow=1` 明示这种状态。两侧温差为 0 时换热为 0，风机仍可能耗电。

风机关系为

\[
P_{fan}=P_{fan,rated} r^3.
\]

这里采用固定系统条件下的相似律近似，未解风机曲线与系统阻力。恒定 UA 与线性掠过风量也是本版明确的简化；因此本模型不适合直接据此选型或预测未经标定的低速换热。风机电功率全部计入环境能量损失，未加到制冷剂排热中，也未加到所报“盘管出风温度”中；该温度是风机热之外的换热盘管出口温度。

## 输出与整站接入

入口为 `refrigeration.air_condenser.condenser_duty(service, params, pressure_pa)`，纯函数返回以下派生量，固定清单见同文件 `OUTPUT_KEYS`：

| 输出 | 引擎单位 | 含义 |
| --- | --- | --- |
| `heat_rejection_w` | W | 净排热，正值从制冷剂排向环境 |
| `effective_ua_w_k` | W/K | 强制风有效导热系数与自然导热系数之和 |
| `forced_heat_w` / `natural_heat_w` | W | 两条环境换热通道的带符号热量 |
| `condensing_temperature_k` | K | 制冷剂饱和温度 |
| `air_inlet_temperature_k` / `air_outlet_temperature_k` | K | 环境入口与强制风盘管出口温度；停风时出口为空 |
| `air_mass_flow_kg_s` | kg/s | 有效掠过风量 |
| `air_capacity_rate_w_k` | W/K | 空气热容量流率 |
| `effectiveness` | 1 | 强制风换热有效度，停风为 0 |
| `approach_k` | K | 饱和温度减入口干球温度，可为负 |
| `fan_power_w` | W | 风机电功率 |
| `reverse_heat_flow` | 1 | 1 表示净换热反向，0 表示非反向 |

合同另声明 `state.heat_rejected_j`、`state.fan_energy_j`。设备函数不推进任何状态，不自行累计能量，也不返回这些累计量；整站只能在接受的时间步按已有账本累计，候选迭代和失败重试不能累加。累计净排热保留负值，风机电量非负。

`definition()` 返回模块合同，其内部延迟导入目录辅助函数以避免循环依赖；标准 `param.*` 变量由目录统一补入。整站接入应对所属压力等级执行 `dU/dt -= heat_rejection_w`，外界边界账采用同一符号；不人为创建一条未经求解的制冷剂质量流。停风仍保留该设备原有制冷剂拓扑。

## 方法依据与设备验证

方法核对日期：2026-11-05。Lawrence Berkeley National Laboratory 的官方 Buildings 库源码 [`epsilon_ntuZ.mo`](https://github.com/lbl-srg/modelica-buildings/blob/master/Buildings/Fluid/HeatExchangers/BaseClasses/epsilon_ntuZ.mo) 中 `ConstantTemperaturePhaseChange` 分支给出 `eps = 1 - exp(-NTU)`，与上面的空气微元能量推导一致。这里仅核对等温相变侧换热方法，并未复用该库的整机模型或声称厂家精度。

设备定向命令：

```powershell
python -m pytest -q tests/test_air_cooled_condenser.py
python -m ruff check backend/fn_engine/refrigeration/air_condenser.py tests/test_air_cooled_condenser.py
python -m mypy backend/fn_engine/refrigeration/air_condenser.py
```

测试覆盖 R134a 与氨的真实饱和温度、独立 RK4 空气微元能量积分、空气侧能量账、有限风量上限、小 NTU、零 UA、停风及自然换热连续性、立方风机功率、反向换热、无效输入、重复候选计算不累计状态，以及合同默认值与显示单位。整站网络与报告验收由新设备整合记录单独登记，不用设备级通过替代。
