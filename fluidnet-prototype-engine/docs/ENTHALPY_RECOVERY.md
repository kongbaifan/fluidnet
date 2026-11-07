# 四口全热回收器：成对水汽与焓通量

模块 `enthalpy_recovery` 为内置新模型，四口分别是 `exhaust_in/out`（排风）和 `supply_in/out`（新风）。两路都是湿空气，各自独立连线、压力参考与干空气质量流；内部只交换显热和水汽，没有干空气漏风或混合。

当前 Python `air.pass_through.v1` 协议只允许湿量透传，`ModuleThermalResponse` 只携带热源。因此本设备没有更改普通作者模块合同，也没有在 `observe` 伪造含湿量；它通过专用 `RecoveryResult(exhaust: AirDeviceResult, supply: AirDeviceResult)` 同时返回两股真实出口状态及成对源汇，直接参与湿空气固定点和守恒账。

## 合同与首版范围

| 参数 | 默认值 | 单位／权限 |
| --- | --- | --- |
| `sensible_effectiveness` | 0.65 | 0–1，显示百分比，静态 |
| `moisture_effectiveness` | 0.5 | 0–1，显示百分比，静态 |
| `bypass_ratio` | 0 | 0–1，运行可写，等效交换旁通而非额外流路 |
| `diameter_m` / `secondary_diameter_m` | 0.4 / 0.4 | m，显示mm，排风／新风独立通路 |
| `loss_coefficient` / `secondary_loss_coefficient` | 2 / 2 | 两侧独立阻力K |

仅适用于 `moist_air=true`、Air/gas、热力开启、node物性耦合及湿空气合同版本1。两路不得通过外部连线并成同一风路。每个通路允许反流，传热函数读取真实上游状态，不依赖设备编号。零流一侧时两侧交换均为0；全旁通时热量与湿量迁移均为0。

固定有效度是教学模型参数，不是厂家试验值，也不含转轮转速、膜面积、吸附等温线或蓄湿/蓄热状态。不处理液态凝水、结霜/除霜；所有端口需不低于0°C，出口过饱和明确拒绝。当前不保证任意一对显热/湿量有效度在全部入口条件下可行；越过温度夹点的组合报错，不裁剪温度/湿量以掩盖守恒错误。

## 方程与符号

设两路干空气流量为 (m_e,m_s)，入口温度、含湿量和干空气基准焓为 (T,w,h)，旁通比例为 (b)：

\[
C_e=m_e c_{p,e},\quad C_s=m_s c_{p,s},
\]
\[
Q_s=(1-b)\varepsilon_s\min(C_e,C_s)(T_e-T_s),
\]
\[
J=(1-b)\varepsilon_w\min(m_e,m_s)(w_e-w_s).
\]

J正值表示排风向新风传湿，负值反向。水汽通量携带供湿侧入口温度下的水汽比焓 (h_v(T_{donor}))，使用现湿空气层统一参考焓：

\[
Q=Q_s+J h_v(T_{donor}).
\]

真实出口同时由质量、能量得到：

\[
w_{e,out}=w_e-J/m_e,\quad w_{s,out}=w_s+J/m_s,
\]
\[
h_{e,out}=h_e-Q/m_e,\quad h_{s,out}=h_s+Q/m_s.
\]

随后由出口压力和 (h,w) 反求温度、密度、相对湿度等物性，不能独立指定一个满足显示的出口温度。空气输运每路干空气不变，混合物质量随水分迁移相应变化；两路湿量源汇为−J/+J，总焓源汇为−Q/+Q，因此整个设备的总水汽和总能量净源均为0。没有液态排水口，`water_removed`保持0，避免错计排水焓。

夹点范围纳入原入口温度及其按实际出口压力等焓变化后的温度，避免零交换时实际气体微小温变被误判为热越界。夹点检查在最终收敛点执行；物性层不能接受过饱和状态，候选出现凝结时会停止并给出适用域诊断。

诊断：`RECOVERY_CONDENSATION_UNSUPPORTED`（出口过饱和）、`RECOVERY_FROST_UNSUPPORTED`（低于0°C）、`RECOVERY_PINCH_RANGE`（固定有效度越过夹点）、`RECOVERY_CIRCUITS`（两路未隔离）、`MOIST_AIR_REQUIRED`（错误执行域）。

## 输出、累计与验证

输出显热、水汽携带焓、总焓传递、水汽迁移、两侧真实出口温度/含湿量及独立水汽/焓残差。`state.transferred_energy_j`、`state.transferred_water_kg` 只在接受步累计，保留传递方向；失败试算不累计。没有内部物理存量。

`tests/test_enthalpy_recovery.py` 的11项定向验收覆盖：等/不等风量、双向温湿梯度、零流、旁通、显式源汇与独立出口账、真实网络各股干空气守恒、总水/焓闭合、反流、凝结/霜/域拒绝、运行旁通与接受累计。`examples/hvac-expansion/enthalpy-recovery.recipe.json` 和 `.project.json` 给出可从空白组装的5设备4连接参考。

普通显热回收包 `air_recovery_sensible` 继续保留；新设备没有修改它的版本或湿量透传语义。设备与网络通过记录不替代浏览器实际完成证据，整体路线验收单独登记。
