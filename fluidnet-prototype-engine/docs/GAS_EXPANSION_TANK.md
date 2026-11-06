# 气垫膨胀罐：等温气体与真实液体储量（H08）

2026-11-05。`gas_expansion_tank` 是普通液体网络的两口储量节点，气液压力由液体质量、液体物性和固定质量气体共同决定。原有开式水箱保持原压力公式；该设备使用独立 `ExpansionStorage` 策略。

## 压力与能量

罐体总容积为 V，空罐预充绝对压力为 p₀；固定质量气体与恒温热浴相连，理想等温关系为 C = p₀V。水侧采用真实液体密度：

```text
p × Vgas = C
M / rho(p,h) + Vgas = V
M_new = M_old + dt × net_inflow
```

液体内部能量为 `U=M·u(p,h)`，不能用固定热质量 buffer 的焓储能替代。每步采用隐式流股能量与气体精确等温功：

```text
U_new − U_old = dt × (Σ m_in h_in − Σ m_out h_out + Q_input − Q_loss) + Wgas
Wgas = C × ln(Vgas_new / Vgas_old)
```

充水压缩气垫时 Wgas 为负，表示液体向气体做功；排水膨胀时为正，表示气体向液体做功。理想气体温度不变、内能不变，气体从等温热浴吸收的热量等于 Wgas，明确属于系统外部能量边界；没有把压缩功藏到未声明冷源。气体等温是理想假设，未模拟换热速率、膜片弹性、气体溶解、静压高度或真实气体行为。

压力与质量在水力步内共同求解，液体焓与密度通过 node 外迭代更新；最终同时检查液体压力、体积和温度相容。充水会增加质量和压力、减少气垫体积；相同质量升温时，液体膨胀也改变气垫和压力。液体体积须保持在总容积的 0.1%–99%，液体须保持单相；越界拒绝，不以钳制质量或压力伪造解。

## 使用范围

参数包括 `volume_m3`、`precharge_pressure_pa`、`initial_liquid_fraction`、`temperature_k`、`heat_input_w`、`heat_loss_ua_w_k` 和 `ambient_temperature_k`。首版两水口处在同一压力节点、内部充分混合；可在连接中增加管道或阀门控制充排水。

仅支持普通液体域、`thermal=true`、`property_coupling=node` 的动态运行。稳态报 `EXPANSION_DYNAMIC_REQUIRED`；湿空气／风水联算、关闭热力或 reference 模式报 `EXPANSION_DOMAIN_UNSUPPORTED`。不能与同一节点的固定压力边界直接相连；容器自身就是动态压力参考。制冷热耦合仍受原液体侧无储量范围限制。

状态输出为 `state.mass_kg`、`state.volume_m3`、`state.gas_volume_m3`、`state.pressure_pa`、`state.temperature_k`、`state.internal_energy_j`、`state.gas_work_j`、`state.net_inflow_kg_s`。`gas_work_j` 是从初态至当前的累计气体功／热浴向气体累计供热；不与水侧外部加热重复累计。候选只在现有仿真接受事务成功后提交，失败帧回滚保留原质量和焓。

## 示例与本轮证据

[充水压升项目](../examples/hvac-expansion/gas-expansion-fill.project.json)使用 0.1 m³ 罐体、150 kPa 空罐预充、40% 初始液体，初始气液压力 250 kPa；两端压力边界 270/250 kPa，经细管接入。动态 300 s、输出间隔 30 s 的 11 帧全部有效，最终液体质量 42.2298 kg、压力 259.977 kPa、气垫体积 0.0576974 m³。最终水力压力残差约 `1e-8 Pa`，质量残差约 `2.4e-18 kg/s`。

```powershell
$env:PYTHONPATH = 'backend'
python -m pytest -q tests/test_expansion_tank.py tests/test_closed_buffer_tank.py
python -m ruff check backend/fn_engine/expansion_tank.py backend/fn_engine/expansion_example.py tests/test_expansion_tank.py
```

H08 新增 4 项与 H07 共 12 项定向测试通过；ruff 通过。覆盖独立流股/液体内能/气体功核算、质量与 pV、定质量热膨胀压力响应、压力导数、排水、拒帧回滚以及稳态/reference/体积边界拒绝。本轮不代表全量验收或真实产品选型。
