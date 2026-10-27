# 算法域缺口补齐验收

日期：2026-10-27。基线：`codex/development-consistency` 工作区（HEAD `e5a90ce` + 本轮未提交的热耦合／双盘管改动）。范围仅算法域：不涉及 Unity、前端交互、打包发版、课堂并发与鉴权。

## 交付

| 工作项 | 交付内容 | 合同／物理边界 |
| --- | --- | --- |
| 电加热器 | 新增内置模型 `heater`（「电加热器」）：`heat_input_w` 按质量流量折算比焓升，`heat_w`、`param.heat_input_w`、端口温压焓可读取；`runtime` 允许运行中改功率 | 理想加热段：无储热、无热损、无相变；零流量拒绝加热（`NO_FLOW_HEAT`）；水力按局部阻力，`loss_coefficient=0`（默认）表示不产生附加压降 |
| 多支路饱和容器 | 新增 `hp_receiver_multi`（高压贮液器，四进口）与 `lp_drum_multi`（低压循环桶，四进口）；`compile_station` 的参考合同按模块 ID 匹配，压力等级归并按端口集合而不再假设四端口布局 | 集总模型只有一个压力等级：多出口同相态没有额外物理意义，分支仍用集管；多余进口可不连接；沿用液位适用区、两相集总与每等级一个容器的约束 |
| 双盘管 | 代码与测试已在工作区：合同上限两条、同一液体通路不得重复绑定、两条须关联同一饱和容器；`topology=parallel`（同回路双支路）与 `topology=independent`（水与乙二醇独立回路）两个参考系统、界面入口与 UI 合同测试 | 逐盘管热量、共同容器能量累计、反向流、关闭通路、历史绑定均由 `tests/test_dual_thermal_coupling.py` 覆盖；总热量见 `metrics.coupling_heat_w` / `metrics.coupling_heat_energy_j` |
| 健康检查 | `capabilities` 新增 `dual_thermal_coupling`、`heater`、`multi_inlet_vessels` | 严格模型 `HealthCapabilities` 已扩展并重新生成契约 |

## 未交付：热力膨胀阀过热度自调

本轮核对后**明确不实现**，原因不是工期，而是当前模型没有可测的过热度状态：

- B 域蒸发器（`air_cooler`）为泵供液／满液式，出口干度被 `max_outlet_quality` 限制，出口为饱和两相，没有过热段；
- 复叠换热器 `cascade_exchanger` 与低压桶按饱和处理，吸气为饱和蒸气，过热度恒为 0；
- A 域 `condensing_unit` 把「压缩—冷凝—节流—蒸发」合成为一个设备，`superheat_k` 只是固定的设计参数，不是可调节结果。

因此「热力膨胀阀按过热度自调开度」必须先有直接膨胀（DX）蒸发器的出口过热物理，再谈 PID/内置调节。建议后续单独立项：新增 DX 蒸发器（过热段 + 供液量由阀决定）约 6–8 人日，随后复用现有 PID 框架（测量变量 `superheat_k`、目标 `expansion_valve.opening_ratio`）即可，不需要新的控制内核。本轮不把该项登记为完成。

## 验证

| 检查 | 结果 |
| --- | --- |
| 定向后端回归 | 136 项通过（40.12 s）：`test_heater`、`test_multi_port_vessel`、`test_refrigeration_station`、`test_thermal_coupling`、`test_dual_thermal_coupling`、`test_contracts_and_physics`、`test_continuous` |
| 静态检查 | `ruff check backend tests scripts modules examples/control_templates examples/external_clients` 通过 |
| 类型检查 | `mypy --config-file mypy.ini`：62 个源文件零错误 |
| 契约 | 重新生成后 `generate_contracts.py --check`：67 个文件一致 |
| 未执行 | 全量 pytest 与浏览器回归未跑（用户明确不跑全量；前端未改动，浏览器脚本不属于本轮范围） |

新增专项测试：`tests/test_heater.py`（4 项：加热/冷却的比焓与能量残差、零流量拒绝、运行参数合同）、`tests/test_multi_port_vessel.py`（2 项：多进口归并同一压力等级、两台冷凝器汇入同一容器后运行与回路质量守恒）。

## 复现

在 `fluidnet-prototype-engine` 目录执行：

```powershell
python -m pytest tests/test_heater.py tests/test_multi_port_vessel.py tests/test_refrigeration_station.py `
  tests/test_thermal_coupling.py tests/test_dual_thermal_coupling.py tests/test_contracts_and_physics.py tests/test_continuous.py -q
python -m ruff check backend tests scripts modules examples/control_templates examples/external_clients
python -m mypy --config-file mypy.ini
python scripts/generate_contracts.py --check
```

## 已知边界

- 加热器不计算表面散热、效率与相变；负功率表示冷却，但仍受单相约束，进入两相会以 `PHASE_UNSUPPORTED` 拒绝。
- 多支路容器只增加进口；所有出口仍为单一 `vapor` / `liquid`，需要多出口时用集管。
- 双盘管仍是两条上限、同一容器；两条以上或不同容器的盘管尚未支持。
