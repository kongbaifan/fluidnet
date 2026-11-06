# 闭式缓冲水箱：固定热质量充分混合（H07）

2026-11-05。新设备 `closed_buffer_tank` 是普通单相液体域的双口动态储热模型。它有独立的固定热质量、初温、热源和环境散热参数，水力只由接口内径和局部阻力 K 决定；没有借用管长和管径来伪装水箱容量。

## 物理与压力约定

`mass_kg` 是用户显式指定的固定液体热质量。双口质量流量相等，流向可反转，出口温度等于箱内充分混合温度。压力由外部水力网络决定；该设备不提供压力参考、不储存净流入质量、不模拟气垫、液位、分层或热膨胀。此版本不同时声明严格定几何体积与随物性变化的密度；若按容积估算质量，应由用户用设计密度乘容积后填写。

储热采用不可压缩液体的显热近似 `E = M·h`，忽略压力功。比焓在当前出流口水压下转换温度，适用于水力压差对液体显热影响较小的工程场景。`state.stored_energy_j` 的绝对值依赖物性焓基准，比较储能应取同一运行的差值，不把它称为严格刚性容器内能。初始温度和整个候选步都必须处于用户声明的温度区间和单相液体范围。

隐式 Euler 的每步独立能量式为：

```text
M × (h_new − h_old) / dt
  = abs(mdot) × (h_in − h_new) + Q_input − UA × (T_new − T_ambient)
```

停流时输运项归零，箱内液体继续吸收外部加热或向环境散热。停流的管口不产生虚构质量输运；此时读取 `state.temperature_k` 查看箱内温度，零流量外侧节点沿用引擎的停滞节点语义。

## 初始帧、接受与范围

初始帧固定为声明的初温，不提前消耗一段仿真时间，储热功率显示 0；初态可以尚未达到热平衡。此后每个候选步从上一次接受的比焓出发。候选根、热力迭代和帧预览都不修改已接受状态；只有现有 `_accept` 事务成功后，才提升新的混合比焓。失败和重试不重复计算累计变化。

首版仅支持启用热力的普通 `fluid` 动态运行。稳态明确报 `BUFFER_DYNAMIC_REQUIRED`，湿空气／风水联算或关闭热力报 `BUFFER_DOMAIN_UNSUPPORTED`；制冷站液体热耦合仍按原储量限制拒绝。没有放开风水联算的水侧储热，也没有将该设备用作膨胀罐。

参数：`mass_kg`、`temperature_k`、`minimum_temperature_k`、`maximum_temperature_k`、`heat_loss_ua_w_k`、`ambient_temperature_k`、`heat_input_w`、`loss_coefficient`、`diameter_m`。环境温度和外部加热可以运行中调整；固定质量与初态须在新运行前设定。

输出：`state.temperature_k`、`state.mass_kg`、`state.enthalpy_j_kg`、`state.stored_energy_j`、`state.stored_power_w`、`ambient_heat_loss_w`、`energy_residual_w`，以及正常的两口压力、流量和物性。项目 JSON 保存参数及初态；重载复算仍新建运行，未新增跨重启接续原仿真。

## 示例与验证

- [热水混合规范项目](../examples/hvac-expansion/closed-buffer-mixing.project.json)／[组装清单](../examples/hvac-expansion/closed-buffer-mixing.recipe.json)：100 kg、初温 20°C，40 K 温差的入口与 10 W/K 环境散热。
- [停流散热规范项目](../examples/hvac-expansion/closed-buffer-cooling.project.json)／[组装清单](../examples/hvac-expansion/closed-buffer-cooling.recipe.json)：100 kg、初温 40°C，100 W/K 散热到 20°C；关闭隔离阀形成精确零流量。

两例各运行 300 s、输出间隔 30 s，均得到 11 个有效帧；最终混合温度分别约 59.553°C 和 38.619°C，最大独立储热方程残差均低于 `5.3e-7 W`。

```powershell
$env:PYTHONPATH = 'backend'
python -m pytest -q tests/test_closed_buffer_tank.py
python -m pytest -q tests/test_states.py tests/test_thermal.py
python -m mypy --config-file mypy.ini
```

H07 新增 8 项定向测试通过：常比热独立解析解、正反流守恒、停流散热、闭合循环储存泵热且无隐含冷源、候选及拒帧回滚、越界保留接受态、域与物态拒绝。闭合循环的高精度能量核算显式采用 `thermal_tolerance_k=1e-9`。相关旧储热／热力测试 56 项通过；mypy 107 个文件无问题。本轮没有运行全量测试。
