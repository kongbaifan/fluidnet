# 冷却塔池真实储量：H09 设计卡

后续已实现[湿接触与真实池体联算](COUPLED_TOWER_POOL.md)：新增独立 `coupled_tower_pool`，蒸发改由湿空气增湿量计算，补排水仍为真实水口。下文保留先交付的外给损失 `tower_pool` 范围，两种模型不重复扣同一蒸发或热量。

2026-11-05。首版目标是普通 fluid 域的开式充分混合水池，接真实补水、排污、回水和出水；显式积分液体质量和热储量。现有 `cooling_tower_moist` 的蒸发／飘水／排污输出目前是设备账目，不能直接作为已经存在的水池或第二份质量源汇。

## 首版范围

采用独立 `tower_pool` 状态模型，复用开式水箱的液位静压关系 `p_bottom=p_surface+gM/A`，但增加独立的外部质量源汇：蒸发 `m_evap`、飘水 `m_drift`。补水和排污都由普通网络通路及阀门真实计算，不能把液位控制器请求流量当作实际补水。

蒸发量由用户显式输入，首版实际采用水池温度下的饱和水蒸气焓；它表示离开水面的理想蒸气流股，不把池面总压力当作蒸气分压。水侧液体出口仍取充分混合比焓。飘水取水池液体比焓。液池能量：

```text
dM/dt = Σm_in − Σm_out − m_evap − m_drift
d(Mh)/dt = Σm_in h_in − Σm_out h_pool − m_evap h_vapor − m_drift h_pool + Q_external
```

对液体蒸发潜热、带走的水蒸气焓以及外给排热功率必须逐项说明，不能同时扣除相同湿塔蒸发潜热两次。水池当前无湿空气回路，不能将该版称为湿空气冷却塔联算。

## 求解挂接

水力储量未知量仍为液体质量变化率 `r=dM/dt`，质量行改为 `Σq_in − m_evap − m_drift − r = 0`。热力混合行需同步带上蒸发／飘水项和更新后的库存，特别是蒸发扣除的质量不能再次通过混合行隐式扣热。压力由新库存得到；对低水位越界拒绝，不凭空补水或钳制液位。

候选质量、焓、累计蒸发/飘水账与控制参数修改须在同一接受事务中提升；失败缩步不重复累计。不能只在输出页扣水而不进入水力质量方程。多进口原始水箱只有双口，需明确定义池体口布局并验证所有口的真实质量流量。

## 验收

1. 无连接换水时，库存降低量等于蒸发+飘水积分，液位静压同步降低。
2. 有补水时，水池质量增加量等于实际进出口+外部损失积分；控制请求不充当边界。
3. 独立整体能量账包含蒸气焓、液体飘水焓与实际补排流股，不能只检查内部同一公式。
4. 零蒸发／零飘水严格退化到既有开式水箱数值行为；拒绝与回滚不丢失库存。
5. 湿空气项目明确拒绝该首版；后续真正塔池联算需要对原湿塔接口重定义水侧来回流和总能量账后再开放。

## 首版实现与实际证据

已实现独立 `tower_pool.py`、四水口目录设备 `tower_pool` 以及 `tower_pool_example(makeup=False/True)`。固定 `evaporation_kg_s`、`drift_kg_s` 进入水力质量行，蒸气／液滴带走焓进入储热方程；两项不设为运行中可写，累计量由已接受仿真时间精确积分，因此候选或拒帧不会增加累计蒸发。水池热模型沿用不可压缩开式池体的焓库存近似，不声称为密闭容器精确内能。

已输出真实液位、质量、库存变化率、蒸发／飘水累计质量、蒸气／飘水焓流。`heat_input_w` 只表示独立外部热源，不应重复输入已由蒸气流股带走的潜热。该模型不连接既有 `cooling_tower_moist`：首版 pure Water、fluid 动态以外明确拒绝；湿空气模型的排热、水耗和风机模型保持原用途。

- [无补水蒸发](../examples/hvac-expansion/tower-pool-evaporation.project.json)／[清单](../examples/hvac-expansion/tower-pool-evaporation.recipe.json)：四水阀关闭，蒸发 0.001 kg/s、飘水 0.0001 kg/s。300 s 库存 995.653806→995.323806 kg，减少恰为 0.33 kg，池温 30→29.8248°C。
- [真实补水与排污](../examples/hvac-expansion/tower-pool-makeup.project.json)／[清单](../examples/hvac-expansion/tower-pool-makeup.recipe.json)：补水阀和排污阀接实际压力边界，流量由管网求得。300 s 库存增至 996.887709 kg；补水量未由目标水位或控制命令伪造。

两例均有 11 个有效输出帧，最终质量残差分别约 `2.8e-17`／`3.2e-28 kg/s`。4 项 H09 测试逐步独立核对质量与液体库存焓差、蒸气焓、实际补排流股、失败帧回滚及稳态拒绝。

```powershell
$env:PYTHONPATH = 'backend'
python -m pytest -q tests/test_closed_buffer_tank.py tests/test_expansion_tank.py tests/test_tower_pool.py tests/test_states.py tests/test_thermal.py
python -m mypy --config-file mypy.ini
```

该阶段 H07/H08/H09 和相关原储量／热力回归 **72 项通过**；mypy 121 个文件无问题，相关 ruff 通过。该阶段尚未完成湿空气塔池联合质量热湿求解，因此此处只登记 fluid 外给损失池体范围；后续联合模型见[湿接触塔池](COUPLED_TOWER_POOL.md)。
