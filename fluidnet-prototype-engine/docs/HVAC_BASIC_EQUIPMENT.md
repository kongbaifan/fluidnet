# 暖通基础设备与理想测点

> 更新日期：2026-11-02 ｜ 源码基线：`31f1da9` + 本轮新增
> 相关文档：[补全清单](HVAC_BASIC_EQUIPMENT_CHECKLIST.md)、[验收记录](HVAC_BASIC_EQUIPMENT_ACCEPTANCE.md)、[模块开发套件](MODULE_KIT.md)

本轮把标准冷水机房与末端组网需要的基础设备做成了可直接拖入画布的模块，并新增了“理想测点”（仪表）：测点读取同一运行帧的已有变量，参与 PID 反馈、趋势曲线和报告，但不向网络增加方程。

## 1. 新增设备

全部设备属于模块库分类 **暖通基础设备**（`category='暖通基础设备'`），由 `modules/` 种子包提供，服务启动即自动进入 `/api/v1/modules`。查询、配方和端口见各自 `manifest.json`。

| 模块 ID | 名称 | 端口 | 主要参数 | 主要变量 |
| --- | --- | --- | --- | --- |
| `pipe_reducer` | 异径管（渐缩／渐扩） | in0 / out0 | `inlet_diameter_m`、`outlet_diameter_m`、`transition_length_m`、`profile`（`sudden`/`gradual`）、`loss_multiplier` | `loss_coefficient`、`pressure_loss_pa`、`inlet_velocity_m_s`、`outlet_velocity_m_s`、`is_contraction`、`state.throughput_kg` |
| `water_tee` | 水侧三通 | common / branch1 / branch2 | 各支路 `*_loss_coefficient`、各支路 `*_diameter_m`、`Node_elevation_m` | 各端口质量流量、节点压力、合计压差 |
| `water_header_2/4/6/8` | 分水器（2/4/6/8 支路） | common / branch1…N | 各支路阻力系数与管径、`Common_loss_coefficient` | 各支路质量流量、`state.throughput_kg` |
| `water_collector_2/4/6/8` | 集水器（2/4/6/8 支路） | 与分水器同构，方向相反 | 同上 | 同上 |
| `water_balancing_valve` | 手动平衡阀 | in0 / out0 | `opening_ratio`、`kv_m3_h`、`characteristic_curve`（位置—相对流通能力）、`operation_mode`（`modulating`/`on_off`） | `effective_opening`、`actual_drop_pa`、`actual_volume_flow_m3_h`、`state.throughput_kg` |
| `water_shutoff_valve` | 蝶阀／球阀（关断阀） | in0 / out0 | 同平衡阀，另有 `valve_type` 型号备注；默认 `operation_mode='on_off'` | 同上 |
| `water_strainer` | Y 型过滤器／除污器 | in0 / out0 | `diameter_m`、`rated_flow_m3_h`、`clean_pressure_drop_pa`、`loading_ratio`、`loaded_multiplier` | `loss_coefficient`、`actual_drop_pa`、`state.throughput_kg` |
| `water_three_way_valve` | 三通调节阀（分流／混流） | common / a / b | `Valve_opening_ratio`（A 路开度，B 路互补）、`Valve_kv_m3_h`、各支路阻力与管径 | `a_flow_kg_s`、`b_flow_kg_s`、`state.throughput_kg` |
| `hvac_water_pump` | 循环水泵（含停机阻力） | in0 / out0 | `running`、`speed_ratio`、`head_curve`（m³/h—m）、`efficiency_ratio`、`motor_efficiency`、`diameter_m`、`stopped_loss_coefficient` | `is_running`、`pump_shaft_power_w`、`electric_power_w`、`state.electric_energy_j`、`state.throughput_kg` |
| `hvac_check_valve` | 止回阀（开启／关闭压差） | in0 / out0 | `kv_m3_h`、`opening_pressure_pa`、`closing_pressure_pa` | `flowing`、`state.is_open`、`state.throughput_kg` |

约定：

- 参数和变量都按引擎 SI 单位计算；界面上按 `display_unit` 显示（如 kPa、m³/h、kW、%）。`opening_ratio`、`loading_ratio` 等比例参数在界面按百分比编辑。
- 运行中可改的参数声明 `runtime=True`：平衡阀／关断阀开度、泵启停与转速比、过滤器污堵比例、三通阀开度。其余为静态参数，需停止运行后修改。
- 阀门用 `Kv × 开度` 关系，0% 开度为精确零流量；`characteristic_curve` 必须覆盖 0→1 且单调不减，否则模块初始化报错。
- 分水器／集水器／三通是**组合模块**：内部展开为“阻力元件 + 理想汇合节点”，支路阻力系数置 0 即为理想同压模式。公共口与各支路口在展开后仍是公开端口，参数在前端可直接编辑。
- 泵停机时不再是“泵曲线”，而是按 `stopped_loss_coefficient` 与内径计算的被动通流阻力，因此停泵、备用泵切换和并联泵工况能由真实网络求解，不靠特判。

## 2. 理想测点（仪表）

`Project.measurements` 是项目级测点列表，最多 64 个；每个测点有 `id`、`label`、`kind`、`sources` 和一个结果单位。

| `kind` | 输入个数与顺序 | 计算 | 结果单位 |
| --- | --- | --- | --- |
| `value` | 1 | 直接读取 | 与被测变量相同 |
| `difference` | 2 | 第一点减第二点 | 与两个输入相同（必须同单位） |
| `volume_flow` | 2 | 质量流量 ÷ 密度 | 固定 m³/s（界面可显示 m³/h） |
| `thermal_power` | 3 | 质量流量 ×（出口比焓 − 入口比焓） | 固定 W（界面可显示 kW） |

- 可绑定变量：设备的可采样数值变量（非参数），端口字段 `pressure_pa`、`temperature_k`、`mass_flow_kg_s`、`density_kg_m3`、`enthalpy_j_kg`，以及通路的 `mass_flow_kg_s`。
- 编译期校验：未知引用、单位与计算类型不符、两点差值单位不同、计算测点的显示单位带偏移，都会以 `MEASUREMENT_INVALID` 拒绝项目；重复 ID 或占用 `measurement` 命名空间同样拒绝。
- 运行期：结果写入帧变量 `measurement.<id>`。任一输入缺失、为 NaN/Inf 或非数值时，结果为 `null` 并附 `MEASUREMENT_UNAVAILABLE` 诊断，**不以零值代替**。
- 测点只读取已接受帧，不增加网络方程，因此不改变水力／热力结果。
- 测点可直接作为 PID 的反馈变量（`measurement.<id>`），也可加入曲线、写入报告和归档；`trend` 瘦身历史始终保留测点帧。
- 作用域限制：目前只支持单相水力及风水联算项目；带热耦合（`thermal_couplings`）或非流体域端口的项目会以 `MEASUREMENT_DOMAIN_UNSUPPORTED` 拒绝。
- **端口物性只在打开热力层（`solver.thermal=True`）时进入运行帧**。因此绑定端口密度／比焓的测点（`volume_flow`、`thermal_power`）要求项目开启热力层；纯水力项目里这类测点会得到 `null` 和诊断，而不是估算值。示例 `hvac-water-balance` 因此开启热力层。

界面：控制页“仪表与测点”面板可新增／编辑／移除测点（单点测量、两点差值、体积流量、热功率），显示当前运行读数，并可直接“加入曲线”。运行中禁用编辑；被控制器或脚本使用的测点不允许删除。

## 3. 示例

风系统页 → “创建风侧示例”可一键创建四个暖通基础示例（`examples/hvac-basic/*.project.json` 是同一内容的可移植快照，由 `scripts/generate_hvac_examples.py` 生成）：

| 示例 | 内容 | 验证要点 |
| --- | --- | --- |
| `hvac-water-balance` | 泵 → 过滤器 → 异径管 → 分水器 → 两台平衡阀 + 两条不同阻力支路 → 集水器 | 支路体积流量、供回水压差测点；平衡阀开度改为场景 |
| `hvac-three-way-mixing` | 冷／热两路经三通调节阀混合后回水 | 三端口质量与焓守恒；混合水温测点；三个工况（冷路全开／各半／热路全开） |
| `hvac-pump-switch` | 分水器 → 两台泵 + 止回阀 → 集水器 → 负荷管段，Python 脚本 5 s 切换工作泵 | 停泵支路零流量、止回阀关闭、电能账本只结算一次 |
| `hvac-basic-plant` | 冷水机组 + 冷冻水泵 + 冷却水泵 + 冷却塔 + 双盘管 + 分集水器 + 过滤器 + 异径管 + 关断阀 | 三回路流量平衡、机组冷量 = 盘管热量 + 泵功、冷却塔排热 = 冷凝热 + 泵功 |

## 4. 当前限制

- 设备默认参数是教学假设：Kv、曲线、效率、额定压降都要按厂家资料填写后才能用于工程结论。
- 过滤器污堵只改变阻力，不产生堵塞事件；止回阀为“开启压差／关闭压差”的互补状态，反向严格截止，但未模拟阀芯动力学与撞击噪声。
- 三通阀两通路按互补开度分配；未模拟执行器动作时间、关断泄漏与厂家快开曲线。
- 泵效率按定值折算，未接入效率—流量曲线；风机不在本轮范围内。
- 分水器／集水器为集中阻力模型，不反映各支路间真实的三维分流与静压恢复。
- 测点是理想仪表：无测量误差、无采样延迟。
- 未实现的设备（膨胀罐、安全泄压、自动平衡阀／PICV、VAV 等）仍登记在[补全清单](HVAC_BASIC_EQUIPMENT_CHECKLIST.md)的“按需”一栏。

## 5. 验证入口

```powershell
python -m pytest tests/test_hvac_equipment.py tests/test_hvac_reducer.py -q
python scripts/generate_hvac_modules.py --check
python scripts/generate_hvac_examples.py --check
node tests/browser-hvac-equipment.mjs    # 需 playwright + Edge
```

数值与证据见[验收记录](HVAC_BASIC_EQUIPMENT_ACCEPTANCE.md)。
