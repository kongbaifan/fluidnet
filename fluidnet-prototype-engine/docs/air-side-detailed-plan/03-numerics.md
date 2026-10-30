# 03 数值算法、物理口径与设备行为

> 实施更新（2026-10-29）：本页保留初始设计依据；对应功能已落地。实际文件、接口和验证见[实施记录](IMPLEMENTATION_LOG.md)及[完整验收](../AIR_SIDE_IMPLEMENTATION_ACCEPTANCE.md)。原“本次不运行测试”描述的是 10 月 28 日的文档任务。

本文给出目标算法。独立物理参考用于确认字段含义，所列误差门槛尚未实测。

## 1. 物性入口与基准

正式路径使用 `HAPropsSI`。所需映射：T/P/W 为干球温度/总压/含湿量；H 为每 kg 干空气的焓，Hha 为每 kg 湿空气的焓；V/Vha 为相应质量基准的比容；R 为相对湿度，D/B 为露点/湿球温度，M 为黏度。接口单位依据 [CoolProp 官方湿空气文档](https://coolprop.org/fluid_properties/HumidAir.html#table-of-inputs-outputs-to-hapropssi)。

```python
# 目标适配方式示意，不在本次任务中执行。
h_da = HAPropsSI("H", "T", T, "P", p, "W", w)
h_total = HAPropsSI("Hha", "T", T, "P", p, "W", w)
rho = 1.0 / HAPropsSI("Vha", "T", T, "P", p, "W", w)
T = HAPropsSI("T", "P", p, "H", h_da, "W", w)
```

服务先验证产品包络、有限性和饱和边界，再调用物性库；异常转换为可定位的 `AIR_PROPERTY_RANGE` 或 `AIR_PROPERTY_FAILURE`。不把库调用失败转成默认 20°C/零湿度。

教学近似公式只能作为独立手算与对照：

```text
w = 0.622 * pv / (p - pv)
pv = p*w/(0.622+w)
RH ≈ pv/psat(T)
h_da ≈ 1006*(T-273.15) + w*(2501000 + 1860*(T-273.15))
```

不能用 `w/wsat` 代替相对湿度。正式计算以物性服务结果为准；近似公式的常数不构成已验证精度声明。

水分源/凝水/补水采用同一公开工程焓参考：`h_l(T)=4180*(T−273.15)` J/kg，`h_v(T)=2501000+1860*(T−273.15)` J/kg。它们是本教学模型的明确近似；不能混入 CoolProp 水工质未经参考态平移的绝对焓。冷却塔循环水进出用同一水物性服务的焓差，外部水源统一平移到上述参考；实施时设置参考态对账用例，验证各源汇不会凭参考偏置产生热量。

## 2. 三种质量量必须分开

```text
m_da          = 干空气质量流量 [kg_da/s]
m_v           = m_da*w [kg水/s]
m_total       = m_da*(1+w) [kg湿空气/s]
Q_volume      = m_total/rho_total = m_da*Vda [m³/s]
enthalpy_flux = m_da*h_da = m_total*h_total [W]
```

湿空气水力未知量使用 m_da，节点连续性为 `Σm_da_in−Σm_da_out=0`。支路压损使用实际总质量流量、当地密度和黏度；上游状态随流向选择。加湿/除湿支路的两端 m_total 可以不同，m_da 必须一致。

管阻/局阻的计算基准选取设备声明的压损截面：普通无源汇通路使用上游体积流量；盘管/加湿器同样以入口截面定义 K。Reynolds 数使用当地湿空气密度、速度和黏度。雅可比导数对 m_da 求导，在冻结 w 的水力内迭代中带上 `(1+w_up)` 的链式因子。

风机曲线的横轴为其模块声明的实际体积流量，不能把 m_da 直接传给旧质量流量关系。风机新增版本适配入口总质量与实际体积流量。SDK 水力回调、独立验证台和规模优化必须使用同一转换函数。

## 3. 热湿输运

### 3.1 节点混合

无储存节点，按实际流向收集流股：

```text
w_node = Σ(m_da_in*w_stream_out) / Σm_da_in
h_node = Σ(m_da_in*h_stream_out) / Σm_da_in
T_node = state_phw(p_node, h_node, w_node).temperature_k
```

不能直接按总湿空气质量平均 w，也不能只平均温度。边界供入流股使用边界 T/w；离开网络的流股使用到达该边界的设备出口 h/w。回流时重新判定上游，不能继续沿用名义 in0。

零流量的孤立节点只有可用初态/状态容积时保留状态，并标注 stagnant；否则返回 `AIR_STATE_UNDERDETERMINED`，不发布伪造的有效状态。仅有固定压力但无实际补气的闭环，不把边界湿度当作无限水分源；需要房间状态或合法的流入边界。湿度线性系统欠约束时返回 `MOISTURE_REFERENCE_MISSING`。

### 3.2 联合迭代

1. 从上一接受状态热启动 p/m_da/h/w；首次使用边界和房间初态。
2. 固定当前 w、密度、黏度、设备分区，求解水力。
3. 按流向计算设备候选出口 h/w、显热/潜热、水分源汇和外部热量。
4. 装配节点 h/w 方程以及房间隐式状态方程。
5. 求解候选 h/w，计算未松弛缺陷；更新干/湿盘管分区和加湿限幅状态。
6. 应用有界松弛；校验饱和与物性；回传新密度/黏度并重复。
7. 同时满足温度、w、密度、压力、质量残差和设备状态稳定后，执行独立全网守恒检查。
8. 成功后返回候选完整解，交给事务接受；任何失败不发布成有效结果。

盘管 wet/dry 判定必须使用**本次迭代实际入口 w/T**，不能以初始化边界 w 判定一次后永久固定。数组 `node_w` 长度 n，`branch_w_out` 长度 m；并联网络允许 m>n。

默认不启用加速器。若后续开启 Aitken/自适应松弛，设备分区切换或拓扑/阀状态变化时清空加速历史。

## 4. 表冷器

初版为规定 ADP 和 BF 的教学模型，不预测冷水侧工作点。若入口不高于表面温度，设备旁通（active=false），不自动变成加热器。

设实际入口为 `(p,T_i,w_i,h_i)`，`T_adp` 为盘管表面温度，BF∈[0,1]。

### 4.1 干工况

当 `w_i≤ws(T_adp,p_out)`：

```text
w_o = w_i
T_o = T_adp + BF*(T_i-T_adp)
h_o = h(p_out,T_o,w_o)
condensate = 0
```

### 4.2 湿工况

当入口露点高于 T_adp 且温度需要降低：

```text
w_adp = ws(T_adp,p_out)
h_adp = h(p_out,T_adp,w_adp)
w_o = BF*w_i + (1-BF)*w_adp
h_o = BF*h_i + (1-BF)*h_adp
T_o = T(p_out,h_o,w_o)
condensate = m_da*(w_i-w_o)
```

湿工况使用 h/w 直线混合后反算 T，不能同时再强制一条与物性非线性不一致的 T 线性公式。

```text
Q_air = m_da*(h_i-h_o)
H_cond = condensate*h_l(T_adp)
Q_cooling = Q_air-H_cond
heat_w = -Q_cooling
```

账本：空气入口焓流 = 空气出口焓流 + 凝水焓流 + 冷源移走热量。

显潜热分解采用明确约定：先在入口温度去湿，再按出口 w 降温。取 `h_mid=h(p_out,T_i,w_o)`，则 `Q_sensible=m_da*(h_mid-h_o)`，`Q_latent=Q_air-Q_sensible`。该定义保证总和等于 Q_air；干工况强制 latent=0、sensible=Q_air。`SHR=Q_sensible/Q_air`，Q_air 小于能量绝对容差时为 null。

BF=1 或零流量时全部热量、凝水为 0，SHR=null；零流量不积累水。表面低于 273.15 K 拒绝，不用本模型模拟结霜。非零反向流拒绝。

## 5. 加湿器

请求加湿量 `Δw_req`，先求不超饱和的最大 `Δw_max`，再按 saturation_action 决定限幅或报错。

- adiabatic：`h_o=h_i`，`w_o=w_i+Δw`，反求 T_o；求解 `RH(p_o,h_i,w_o)=1` 得可行上限。
- isothermal：`T_o=T_i`，`w_o=w_i+Δw`；上限为 `ws(T_i,p_o)−w_i`；补热 `Q=m_da*(h_o−h_i)`。
- 实际加湿量 `m_add=m_da*Δw`；请求量 `m_req=m_da*Δw_req`；两者差异必须可读，limited=true 时有定位警告。
- `saturation_action=error` 超限返回 `HUMIDIFIER_SATURATION_LIMIT`；limit 则输出真实达到的状态。
- 零流量时 m_add/Q 全为零；负 Δw、未知 mode、不支持方向明确拒绝。

限幅用同一物性服务的有界根求解，不能粗暴把 RH 截为 1 而不修改 w、T、热量。等焓模型注水的参考焓为 0；若未来增加真实水温/蒸汽模型，必须新增 mode/合同和源焓，不能悄悄改变 adiabatic 的含义。

## 6. AHU 其他设备

混合箱是三端口理想混合节点。`fresh_air_fraction=m_da_fresh/(m_da_fresh+m_da_return)`；分母为零返回 null，输入/输出方向不满足模型时诊断失败。三通局阻用独立 duct_fitting，混合箱本身不额外叠加压损。

过滤器：

```text
Δp = sign(Q)*clean_pressure_drop_pa
     *(1+(loaded_drop_multiplier-1)*loading_ratio)
     *(abs(Q)/rated_volume_flow_m3_s)^2
```

再热器/风机不改变 w。风机进入空气的功率遵守原模块声明的效率边界，轴功、电功和传入流体功不混为一项；同一功率不能既由水力关系又由热回调重复加入。

## 7. 房间动态

采用固定有效干空气存量、完全混合、低速准稳态压力的单区模型。初始化：

```text
M_da = rho(initial_p,initial_T,initial_w)*volume/(1+initial_w)
M_v = M_da*w
E = M_da*h_da(T,w) + C_additional*(T-273.15)
```

M_da 在本次运行固定；volume 是初态有效存量参数，不承诺动态过程中严格满足密度×固定几何体积。房间压力由风管网络求解，不增加声学或可压缩容积方程。UI/报告必须显示这一假设。

状态未知量为 h_da、w；T 由物性反算。对每个子步采用隐式 Euler：

```text
(M_da*w_new-M_da*w_old)/dt
  = Σm_da_in*w_in - Σm_da_out*w_new
    + m_inf*(w_outdoor-w_new) + moisture_load

(E_new-E_old)/dt
  = Σm_da_in*h_in - Σm_da_out*h_new
    + m_inf*(h_outdoor-h_new)
    + UA*(T_outdoor-T_new) + sensible_load
    + moisture_load*h_v(T_source)
```

渗透模型默认等量干空气进/出；它不改变房间压力网络流量，不与真实新风流重复计算。围护只传显热。房间湿度过饱和时失败，提示增加除湿/排风或修正负荷；没有墙体凝水模型时不凭空消失超出的水分。

稳态模式将左侧存储率置零求平衡，不直接返回 initial_T/w。无通风且持续散湿的房间无稳态解，返回 `AIR_ROOM_NO_STEADY_STATE`。

房间候选状态、设备累计量与控制状态一同接受；失败子步减半时恢复到同一旧状态。累计量采用每个接受子步的后向 Euler 通量乘 dt，并与该状态更新一致。

## 8. 冷却塔水耗

采用内置“湿空气接触效能 + 补水水池平衡”教学模型，不将原干工况冷却塔改名后当作新模型。水侧循环流量 m_w 进出相等；蒸发/飘水/排污由等量补水补足，空气为规定入口流股。

空气干流量：`m_da=Q_air/Vda_air_in`。对候选出水温度 T_wo：

```text
T_film = (T_wi+T_wo)/2
h_a_out = h_a_in + effectiveness*(h_sat(T_film)-h_a_in)
w_a_out = w_a_in + effectiveness*(w_sat(T_film)-w_a_in)
E = m_da*(w_a_out-w_a_in)             # 蒸发
D = drift_fraction*m_w               # 飘水
B = max(E/(COC-1)-D, 0)               # 排污
M = E+D+B                            # 补水
```

在可行温度区间内求以下能量方程根：

```text
m_w*h_wi + M*h_makeup + m_da*h_a_in
  = m_w*h_wo + (D+B)*h_wo + m_da*h_a_out
```

所有液水焓以相同参考态表达。空气出口用 h/w 反算 T 并检查非过饱和；蒸发必须非负。预期只冷却工况：入口湿球不低于水温或没有可行根时输出 `TOWER_OPERATING_POINT_INFEASIBLE`，不捏造负水耗。零风量/零水流/零效能用旁通结果。

`heat_rejected_w=m_w*(h_wi-h_wo)`；与空气焓增之差由补水/排液能量解释。`approach=T_wo−T_wb_air_in`。实际浓缩倍数 `1+E/(B+D)`；分母为零返回 null。飘水过大导致无法达到目标 COC 时输出实际值与 `TOWER_CONCENTRATION_LIMITED` 警告。

此模型不能作为填料设计或厂家选型模型；效果参数必须在报告保留。未知根或过饱和不通过放宽能量门槛解决。

## 9. 独立守恒校核

水分账必须从外边界流股、独立源项和存量变化计算，不能只把设备公式代回自身形成恒等式：

```text
R_water = Σ边界流入(m_da*w) - Σ边界流出(m_da*w)
          + Σ加湿 + Σ房间散湿 + Σ平衡渗透水分净流入
          - Σ凝水 - Σ房间水蒸气存量变化率
```

能量账包含边界湿空气焓流、外部热量、风机入流体功、液水/水蒸气源焓、凝水携出焓和房间储能变化；每一项有唯一所有者，严禁双计。全网与每个房间/塔分别核算。

通过条件：`abs(R) ≤ atol + rtol*max(sum(abs(terms)), physical_scale)`；水分 physical_scale=1e-6 kg/s，能量 physical_scale=1 W。干空气逐节点残差还需小于 solver.mass_tolerance。使用独立的出口流股 w/h，不能在吸收边界使用用户配置的入口状态。

数值误差容差与物理模型误差分开。当前 Phase 2a 湿空气统一放宽到 1% 的能量容差应删除；近似模型不能靠容差掩盖单位或漏项。

## 10. 特殊条件与错误处理

| 条件 | 目标行为 |
| --- | --- |
| w<0 或非有限状态 | 失败；不无条件 max(w,0) |
| 仅在舍入容差内轻微负值 | 允许归零，但记录校正量并纳入守恒误差；超过 w 容差拒绝 |
| RH>1 的普通节点 | 失败；只允许加湿器在明确限幅路径修正出口 |
| 冷却后经过散热风管继续跨饱和 | 失败；不自动建立未实现的风管凝水模型 |
| 多节点闭环湿度无参考 | 编译/求解阶段明确拒绝 |
| 湿空气模式关闭热力层 | 编译失败 |
| 非 Air 工质、混合液体回路 | 编译失败；液体塔项目走独立路径 |
| 模块湿空气能力缺失 | 启动前失败，指明实例/版本 |
| 非法参数运行写入 | 整批拒绝，保留先前已接受解 |
| 子步不收敛 | 仅对可重试数值错误减半；合同/方向/工况错误直接失败 |
| 运行最终失败 | 保留最后接受状态及历史，最后错误帧 valid=false |
