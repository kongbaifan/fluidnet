# 02 字段字典与数据合同

> 实施更新（2026-10-29）：本页保留初始设计依据；对应功能已落地。实际文件、接口和验证见[实施记录](IMPLEMENTATION_LOG.md)及[完整验收](../AIR_SIDE_IMPLEMENTATION_ACCEPTANCE.md)。原“本次不运行测试”描述的是 10 月 28 日的文档任务。

本文所有“新增/目标”字段均为拟实施定义。现有公共对象只列本轮必需字段；完整既有字段仍以 `models.py` 和 `contracts/` 为准。02、03、04 中的同名字段必须完全一致。

## 1. 全局约定

- JSON 名称用 `snake_case`；数值必须有限，禁止 NaN/Infinity。未知字段拒绝，遵循现有 `StrictModel`。
- 标识符沿用 `^[A-Za-z][A-Za-z0-9_-]{0,80}$`；项目 id 沿用现有 Project 校验，不额外收紧历史 id。
- 引擎使用 Pa、K、s、W、J、kg/s；压力为绝对压力。界面默认 kPa、°C、%、g/kg_da、kW。
- `humidity_ratio_kg_kg` 为 kg 水蒸气/kg 干空气，简称 w；`relative_humidity` 为 0–1，不能把 50 当 50%。
- 后缀 `_dry_air` 表示以干空气质量为基准；无该后缀的既有通用比焓、质量流量仍以当地混合物总质量计。
- 端口流量**流入设备为正**；通路流量按 input_port→output_port 为正。通路反向时“入口/出口”指实际流向；端口名不交换。
- 不适用/物理上无定义的派生值输出 null，并在变量目录声明 nullable；不能填 0 或 Infinity。
- 设备参数下表 `R` 表示可在运行中通过命令修改；`S` 表示只允许新建运行前修改。所有输出只读。
- `UnitSpec` 保持既有公式：canonical = (display − display_offset) × display_scale；display = canonical/display_scale + display_offset。

| quantity | canonical_unit | display_unit | display_scale | display_offset |
| --- | --- | --- | ---: | ---: |
| temperature | K | °C | 1 | -273.15 |
| pressure | Pa | kPa | 1000 | 0 |
| ratio（RH） | 1 | % | 0.01 | 0 |
| humidity_ratio | kg/kg_da | g/kg_da | 0.001 | 0 |
| specific_enthalpy_dry_air | J/kg_da | kJ/kg_da | 1000 | 0 |
| mass_flow | kg/s | kg/s | 1 | 0 |
| dry_air_mass_flow | kg_da/s | kg_da/s | 1 | 0 |
| power | W | kW | 1000 | 0 |
| volume_flow | m3/s | m3/h | 1/3600 | 0 |

`1/3600` 在实际 JSON 写为有限十进制 `0.0002777777777777778`。旧 `volume_flow_m3_h` 已经以 m³/h 输出，不能再乘 3600。

## 2. Project 与求解选项

### 2.1 规范项目结构

| 路径 | 类型/默认 | 写法与限制 |
| --- | --- | --- |
| `schema_version` | 1 | 本轮保持 1；新增字段向前读取兼容，旧服务仍可能拒绝新字段 |
| `id` / `name` | string/必填 | 稳定项目标识/显示名 |
| `fluid` | FluidConfig | 湿空气网络 `backend=coolprop, fluid=Air, phase_policy=gas` |
| `modules` | ModuleDefinition[]/[] | 必须包含全部实例引用的固定定义 |
| `instances` | ModuleInstance[]/[] | 现有限制最多 1000 |
| `connections` | Connection[]/[] | 端点使用 instance_id+port_id |
| `solver.moist_air` | bool/false | Phase 2a 已有；false 完全走原干工质路径 |
| `solver.moist_air_options` | MoistAirOptions/null | 新增；开启时必须显式提供包含 contract_version=1 的对象，其余子字段可用默认；关闭时必须 null/缺省 |
| `solver.thermal` | bool/true | 湿空气必须 true |
| `solver.property_coupling` | reference/node；原默认 reference | 湿空气必须显式 node，模板自动设置；外部非法组合拒绝 |
| `circuit_fluids` | CircuitFluid[]/[] | Phase 2 湿空气项目只允许同种 Air/gas 回路；水回路另建项目 |
| `selected_variables` | string[]/[] | 既有限制 64；使用完整稳定变量键 |
| `controllers` / `control_scripts` | 原类型/[] | 复用既有单写入者和采样规则 |
| `events` | 原类型/[] | 本轮不扩展冷库专属事件合同；房间负荷变化用参数命令/控制脚本 |

`fluid.composition` 不承载 w；保持空对象。湿空气包含水蒸气但不创建 `Air&Water` CoolProp 流体字符串。单独液体项目中的新冷却塔内部使用湿空气服务，项目的 `solver.moist_air` 仍为 false。

已有 Phase 2a 湿空气项目没有 options 时，不自动解释为新质量基准。新运行 API 返回 `AIR_CONTRACT_VERSION_REQUIRED`；原型导入/项目升级界面生成显式迁移预览，确认后保存新修订。旧历史记录仍按旧格式读取，不受新运行校验影响。

### 2.2 MoistAirOptions（拟新增对象，全部 S）

| 字段 | 类型 | 默认 | 范围/规则 |
| --- | --- | --- | --- |
| `contract_version` | Literal[1] | 1 | 拒绝未知版本 |
| `property_backend` | Literal["coolprop_ha"] | coolprop_ha | 无静默近似回退 |
| `humidity_tolerance_kg_kg` | float | 1e-8 | >0，≤1e-3；w 固定点缺陷阈值 |
| `max_iterations` | int | 60 | 1–500；一次热湿固定点迭代上限 |
| `relaxation` | float | 0.7 | (0,1]；初版固定松弛 |
| `moisture_atol_kg_s` | float | 1e-9 | >0；水分守恒绝对容差 |
| `moisture_rtol` | float | 1e-6 | >0，≤1e-3 |
| `energy_atol_w` | float | 1e-3 | >0；包含凝水/补水焓的能量绝对容差 |
| `energy_rtol` | float | 1e-6 | >0，≤1e-3 |
| `flow_zero_tolerance_kg_s` | float | 1e-10 | >0，≤1e-6；干空气输运的零流量判定 |
| `supersaturation_policy` | Literal["error"] | error | 普通节点不携带雾滴，拒绝过饱和 |

保持 `SolverOptions.mass_tolerance_kg_s` 字段名；在湿空气连续性方程中单位解释为 kg_da/s，并在 solve_summary 记录 `continuity_basis=dry_air`。其他网络仍为总质量。外部质量变量没有改单位。

湿空气输入包络为本产品拟定范围：`253.15≤T≤333.15 K`、`60000≤p≤120000 Pa`、`0≤w≤0.05`，并且不超过饱和值；该范围不是 CoolProp 的全部适用域。盘管、房间和塔另有更窄边界。流动必须在低速单相适用范围，局部实际速度超过 30 m/s 发警告，超过 100 m/s 拒绝。

```json
{
  "moist_air": true,
  "thermal": true,
  "property_coupling": "node",
  "moist_air_options": {
    "contract_version": 1,
    "property_backend": "coolprop_ha",
    "humidity_tolerance_kg_kg": 1e-8,
    "max_iterations": 60,
    "relaxation": 0.7,
    "moisture_atol_kg_s": 1e-9,
    "moisture_rtol": 1e-6,
    "energy_atol_w": 0.001,
    "energy_rtol": 1e-6,
    "flow_zero_tolerance_kg_s": 1e-10,
    "supersaturation_policy": "error"
  }
}
```

## 3. 状态与模块协议

### 3.1 FluidState 与 PortState

新增字段全部默认 null；干工质响应默认省略新 null 字段，避免扩大旧包络。湿空气已接受状态必须填完整必需量。

| 字段 | 类型 | 单位 | 湿空气语义 |
| --- | --- | --- | --- |
| `pressure_pa` | float | Pa | 当地绝压 |
| `temperature_k` | float | K | 干球温度 |
| `enthalpy_j_kg` | float | J/kg 湿空气 | `h_da/(1+w)`；修正 Phase 2a 把 h_da 填入此字段的行为 |
| `density_kg_m3` | float | kg 湿空气/m³ | `1/Vha` |
| `viscosity_pa_s` | float | Pa·s | 湿空气动力黏度 |
| `specific_heat_j_kg_k` | float | J/(kg 湿空气·K) | 混合物基准 cp |
| `humidity_ratio_kg_kg` | float/null | kg/kg_da | Phase 2a 已有，目标 0–0.05 且不超饱和 |
| `relative_humidity` | float/null | 1 | 新增；[0,1]，超界处理见 03 |
| `enthalpy_j_kg_dry_air` | float/null | J/kg_da | 新增；湿空气热输运基准 |
| `specific_heat_j_kg_dry_air_k` | float/null | J/(kg_da·K) | 新增；与通用 cp 不混用 |
| `dew_point_k` | float/null | K | 新增；w=0 时 null，不填写 273.15 |
| `wet_bulb_k` | float/null | K | 新增；物性库可返回时填写，否则 null+诊断 |
| `mass_flow_kg_s` | float/null，仅 PortState | kg/s 湿空气 | 端口实际总质量流量 |
| `dry_air_mass_flow_kg_s` | float/null，仅 PortState | kg_da/s | 新增；与 mass_flow 同符号 |
| `water_vapor_mass_flow_kg_s` | float/null，仅 PortState | kg 水/s | 新增；`m_da*w` |
| `phase` / `quality` | 原字段 | — | FluidState.phase="gas"；quality=null |
| `composition` | dict | 质量分数 | `{"Air":1/(1+w),"Water":w/(1+w)}`；合计 1，不反写 FluidConfig |

`temperature_k` 等字段在 PortState 仍允许试算阶段为 null；湿空气的完整状态只有在物性构造完成后承诺。新的 nullable 元数据不能掩盖已接受帧缺少必需状态的问题。

### 3.2 ChannelState / ChannelResult 扩展

在引擎模型与 fn_sdk 协议中同步新增以下可选字段，旧 Worker 不接收。通路反向时全部流量符号仍按声明方向。

| 字段 | 类型/默认 | 意义 |
| --- | --- | --- |
| `dry_air_mass_flow_kg_s` | float/null | 通路干空气流量 |
| `inlet_mass_flow_kg_s` | float/null | 实际上游湿空气流量，按通路方向带符号 |
| `outlet_mass_flow_kg_s` | float/null | 实际下游湿空气流量，按通路方向带符号 |
| `mass_flow_kg_s` | 原 float | 明确等于入口总质量流量，不强求加湿器两端总质量相等 |
| `pressure_drop_pa` | 原 float | 声明起点压力−终点压力 |
| `heat_w` | 原 float | 设备传入空气的非质量携带热量，正值为加热；凝水/注水焓另记账 |

新增 SDK 能力示例（这是 manifest 片段，不是完整模块）：

```json
{
  "schema_version": 3,
  "runtime": "python",
  "sdk": {
    "api_version": "0.6.0",
    "capabilities": ["lifecycle.v1", "state.json.v1", "air.properties.v1", "air.pass_through.v1"],
    "state_contract_version": 1
  }
}
```

具体风机还需保留原有 net.* 等能力。`air.pass_through.v1` 不允许改变 w；设备的新增湿度字段不构成写权限。

## 4. 内置设备参数

以下表格列出本轮设备全部新增或专用参数。公共实例字段仍为 id、module_id、name、page_id、position、rotation、parameters、draft_parameters、banks、model_id、model_version、package；只有 parameters 中已应用值进入求解。

### 4.1 压力边界 `source`

端口 `out0`，可反向；只有向网络供气时使用指定 T/w，吸收网络流量时使用抵达边界的流股状态。

| 参数 | 类型 | 湿空气模板默认 | 校验 | 写入 |
| --- | --- | ---: | --- | --- |
| `pressure_pa` | float | 101325 | 60000–120000；原 catalog 通用默认不全局改写 | R |
| `temperature_k` | float | 293.15 | 253.15–333.15 | R |
| `humidity_ratio_kg_kg` | float | 0.008 | 0–0.05 且 w≤ws(T,p) | R |

同节点多个供气边界的 p/T/w 必须在既定容差内一致。运行中改变 p/T/w 时整批校验，单独降温导致过饱和应拒绝；组合写入可同时降低 w。

界面可以选择 RH 输入，但保存与运行唯一真值为 w；用户修改 T/p 后，默认保持 w，RH 随之重算。若选择“按 RH 重算含湿量”，必须显式生成新的 w 草稿，不保存两套互相矛盾的输入。

### 4.2 表冷器 `cooling_coil`

内置 `solver_model=cooling_coil`，两个 fluid 端口 `in0/out0`，通路 `ch0` 为 resistance。无储能，正向制冷，反向非零流量报错。

| 参数 | 类型 | 默认 | 范围/解释 | 写入 |
| --- | --- | ---: | --- | --- |
| `coil_surface_temperature_k` | float | 285.15 | 273.15–323.15；机器露点/等效表面温度，禁止结霜区 | R |
| `bypass_factor` | float | 0.15 | [0,1]；1 完全旁通，0 理想接触 | R |
| `loss_coefficient` | float | 2.0 | ≥0；仅压损，零阻力环另作拓扑检查 | S |
| `diameter_m` | float | 0.4 | (0,10]；压损面积对应直径 | S |

目标默认 K=2.0 与当前 Phase 2a 的 K=0 不同；新目录版本使用新默认，旧项目保存的显式 K 不覆盖。单器件压力驱动示例必须有非零阻力。

### 4.3 加湿器 `humidifier`

端口/通路同上，正向运行。`mode` 在 ParameterSpec 中仍为 text，由编译器枚举校验；现有 ParameterSpec 没有 enum 字段，不能直接添加未知字段。

| 参数 | 类型 | 默认 | 范围/解释 | 写入 |
| --- | --- | --- | --- | --- |
| `mode` | text | adiabatic | 仅 adiabatic/isothermal | S |
| `moisture_addition_kg_kg` | float | 0.002 | [0,0.05]；每 kg_da 请求加入水量 | R |
| `saturation_action` | text | limit | limit/error；过饱和时限幅或拒绝 | S |
| `loss_coefficient` | float | 1.0 | ≥0 | S |
| `diameter_m` | float | 0.4 | (0,10] | S |

adiabatic 为教学“等焓加湿”，注入水采用 0°C 液水参考焓，热量为 0；不把它宣称为任意实际喷淋水温模型。isothermal 为受控等温加湿，输出维持等温所需热量，不假设蒸汽设备效率。

### 4.4 混合箱 `air_mixing_box`

内置 `solver_model=air_mixing_box`，端口 `fresh_in`、`return_in`、`supply_out`；同一压力节点，无内部通路和压损。无专用数值参数；新风比例由上游阻力和风机决定。`fresh_in/return_in` 为入、`supply_out` 为出；反向工况拒绝。三端口全部 required=true。比例控制通过上游风阀完成。

### 4.5 过滤器 `air_filter`

内置 resistance，`in0/out0/ch0`；允许反向，压损为奇函数，w/h 透传。

| 参数 | 类型 | 默认 | 范围 | 写入 |
| --- | --- | ---: | --- | --- |
| `rated_volume_flow_m3_s` | float | 1.0 | >0，≤100 | S |
| `clean_pressure_drop_pa` | float | 100 | >0，≤10000 | S |
| `loading_ratio` | float | 0 | [0,1]；0 干净，1 达设计污堵 | R |
| `loaded_drop_multiplier` | float | 2.0 | [1,20] | S |

### 4.6 再热器、风机、风阀与风管

再热器复用内置 `heater`，输入参数为 **`heat_input_w`**（不是输出变量 `heat_w`），默认 1000 W、可运行写入；正值加热，负值冷却。其他参数保留 `loss_coefficient=0`（S，≥0）、`diameter_m=0.04`（S，≥0.001 m）。湿空气下 w 不变，`h_da_out=h_da_in+Q/m_da`。零流量且 Q≠0 拒绝；冷却跨过饱和也拒绝，除湿应使用 cooling_coil。

风机/风阀/风口/管件保留原参数 ID，发布 SDK 0.6.0 兼容版本。风机的密度折算须使用实际入口状态；历史固定密度参数保留在旧版本。新版本新增 `density_mode`（text，默认 state，仅 state/reference，S）；reference 模式显式使用原 `air_density_kg_m3` 并输出假设警告。压力—体积流量曲线的坐标定义必须在模块说明中固定，不能把质量流量当体积流量传入。

### 4.7 房间 `air_room`

内置 `solver_model=air_room, state_model=moist_air_room`。端口 `supply_in/return_out` 合并为同一压力节点，不创建阻力支路；房间压力由网络求解，必须有通向压力参考的连通路径。正向以完全混合房间处理，反向流动报错。

| 参数 | 类型 | 默认 | 范围/意义 | 写入 |
| --- | --- | ---: | --- | --- |
| `volume_m3` | float | 100 | (0,1e6]；只用于初始化有效干空气存量 | S |
| `initial_temperature_k` | float | 299.15 | 273.15–323.15 | S |
| `initial_humidity_ratio_kg_kg` | float | 0.010 | [0,0.05] 且初态未过饱和 | S |
| `initial_pressure_pa` | float | 101325 | 60000–120000；仅用于初态存量，不是固定压力边界 | S |
| `additional_heat_capacity_j_k` | float | 1e6 | [0,1e12]；围护/家具的等效显热容 | S |
| `envelope_ua_w_k` | float | 100 | ≥0 | S |
| `outdoor_temperature_k` | float | 308.15 | 253.15–333.15 | R |
| `outdoor_humidity_ratio_kg_kg` | float | 0.014 | [0,0.05] 且未过饱和 | R |
| `infiltration_dry_air_kg_s` | float | 0 | [0,100]；等量进/出的平衡渗透 | R |
| `sensible_load_w` | float | 1000 | [-1e7,1e7]；正值向房间加热 | R |
| `moisture_load_kg_s` | float | 0.0001 | [0,10]；人员/货物等水蒸气源 | R |
| `moisture_source_temperature_k` | float | 307.15 | 273.15–333.15；新增蒸汽的焓参考温度 | R |

不另加 latent_load_w，避免与 moisture_load 重复计入潜热。新风已由真实风管进入时，不再重复填写相同 infiltration。房间不接受温湿度直接变量写入；调负荷或设备参数后求解状态。

### 4.8 冷却塔 `cooling_tower_moist`

新的内置模型，水侧 `in0/out0/ch0`；项目为纯液态 Water。空气为设备内部规定流量的外界流股，当前不提供空气端口，不宣称已与风管网络联立。相较原 cooling_tower 使用新 ID，保留原模块。

| 参数 | 类型 | 默认 | 范围/意义 | 写入 |
| --- | --- | ---: | --- | --- |
| `air_temperature_k` | float | 303.15 | 273.15–323.15 | R |
| `air_pressure_pa` | float | 101325 | 60000–120000 | S |
| `air_humidity_ratio_kg_kg` | float | 0.014 | [0,0.05] 且未过饱和 | R |
| `air_volume_flow_m3_s` | float | 3 | [0,1000]；实际入口体积流量 | R |
| `contact_effectiveness` | float | 0.7 | [0,1]；教学接触效能，非厂家 KaV/L | R |
| `cycles_of_concentration` | float | 3 | (1,100]；目标浓缩倍数 | R |
| `drift_fraction` | float | 0.0002 | [0,0.01]；相对于循环水流量 | S |
| `makeup_temperature_k` | float | 293.15 | 273.15–323.15 | R |
| `loss_coefficient` | float | 2 | ≥0；水侧压损 | S |
| `diameter_m` | float | 0.05 | (0,2] | S |

`cycles_of_concentration` 为 R，写入时与其他参数整批校验。水侧只支持正向、入口温度 273.15–333.15 K；零水流或零风量时输出旁通结果、水耗全零。塔水池补水维持水侧进出循环质量相等，补水/排污的焓必须进能量账。

## 5. 输出变量完整命名

端口键为 `<instance>.<port>.<field>`；单通路设备提供 `<instance>.<field>`，多通路使用 `<instance>.<channel>.<field>`。实例 id 来自实际项目，禁止写死 C1/F1。

### 5.1 所有湿空气端口

输出 3.1 中的 pressure、temperature、enthalpy、density、viscosity、specific_heat、humidity_ratio、relative_humidity、enthalpy_dry_air、cp_dry_air、dew_point、wet_bulb、mass_flow、dry_air_mass_flow、water_vapor_mass_flow。`composition/phase` 留在结构化状态，不展成数值曲线；quality=null 不列为风侧默认观察量。

### 5.2 通路与设备

| 模块/前缀 | 输出字段 | 单位/定义 |
| --- | --- | --- |
| 所有风侧通路 | `mass_flow_kg_s`, `dry_air_mass_flow_kg_s`, `inlet_mass_flow_kg_s`, `outlet_mass_flow_kg_s` | 见 3.2 |
| 所有风侧通路 | `volume_flow_m3_h`, `pressure_drop_pa`, `heat_w` | 实际入口体积流量；带符号；heat_w 正向空气加热 |
| 表冷器 | `total_heat_w` | 空气焓减少率，正为冷却 |
| 表冷器 | `sensible_heat_w`, `latent_heat_w`, `condensate_kg_s`, `shr` | W、W、kg/s、1；分解公式见 03；无冷却 shr=null |
| 表冷器 | `cooling_load_w`, `condensate_enthalpy_flow_w` | 冷源实际移走热量、凝水携出焓流；二者和=total_heat_w |
| 表冷器 | `outlet_humidity_ratio_kg_kg`, `wet`, `active` | kg/kg_da、bool、bool |
| 表冷器 | `state.condensate_kg`, `state.cooling_energy_j` | 动态累计量；稳态不输出 state.* |
| 加湿器 | `requested_moisture_kg_s`, `moisture_addition_kg_s`, `limited`, `heat_w` | 请求/实际加水、bool、补热 W |
| 加湿器 | `state.water_added_kg`, `state.heating_energy_j` | 动态累计 |
| 混合箱 | `fresh_air_fraction`, `dry_air_mass_residual_kg_s` | 按干空气流量计算；总流量零时比例 null |
| 过滤器 | `pressure_drop_pa`, `loading_ratio` | 实际压损/参数映射 |
| 房间 | `state.temperature_k`, `state.humidity_ratio_kg_kg`, `state.relative_humidity` | K、kg/kg_da、1 |
| 房间 | `state.dry_air_mass_kg`, `state.water_vapor_mass_kg`, `state.stored_energy_j` | kg_da、kg 水、相对规定参考态的 J |
| 房间 | `sensible_load_w`, `moisture_load_kg_s`, `envelope_heat_w`, `infiltration_heat_w`, `infiltration_moisture_kg_s` | 单位按后缀；传入房间为正 |
| 房间 | `state.moisture_added_kg`, `state.load_energy_j` | 动态累计，不由导出曲线积分 |
| 冷却塔 | `heat_rejected_w`, `water_outlet_temperature_k`, `air_outlet_temperature_k`, `air_outlet_humidity_ratio_kg_kg`, `approach_k` | 排热为正；approach=T水出−T湿球入 |
| 冷却塔 | `evaporation_kg_s`, `drift_kg_s`, `blowdown_kg_s`, `makeup_kg_s` | 四项水耗，非负 |
| 冷却塔 | `achieved_concentration_ratio`, `water_residual_kg_s`, `energy_residual_w` | 无蒸发/无排液时浓缩倍数 null |
| 冷却塔 | `state.evaporated_kg`, `state.drift_kg`, `state.blowdown_kg`, `state.makeup_kg`, `state.heat_rejected_j` | 动态累计 |

参数输出统一 `<instance>.param.<parameter_id>`。可写性依据参数 runtime，不依据变量名猜测。凝水/房间/塔的状态不能通过 variables API 直接覆盖。

### 5.3 RunFrame.metrics（新增，全部数值）

| 字段 | 单位 | 意义 |
| --- | --- | --- |
| `air_transport_iterations` | 次 | 最后一次接受求解的内迭代次数 |
| `humidity_defect_max_kg_kg` | kg/kg_da | 未松弛固定点缺陷最大值 |
| `dry_air_mass_residual_kg_s` | kg_da/s | 全网节点连续性最大绝对残差 |
| `moisture_residual_kg_s` | kg 水/s | 按外边界与源汇独立计算的有符号水分残差 |
| `energy_residual_w` | W | 复用现有键，补齐所有源汇和存储 |
| `condensate_kg_s` | kg 水/s | 全网盘管凝水总量 |
| `humidifier_moisture_kg_s` | kg 水/s | 全网实际加湿量 |
| `room_moisture_storage_rate_kg_s` | kg 水/s | 所有房间本子步水蒸气存量变化率；稳态为 0 |

`RunFrame.solve_summary` 新增 `air_contract_version=1`、`continuity_basis="dry_air"`、`public_mass_basis="humid_air"`、`thermal_basis="dry_air"`、`moist_air_backend="coolprop_ha"`。非湿空气不增加这些键。

## 6. 变量元数据与运行来源

### 6.1 AirVariableDescriptor（拟新增）

| 字段 | 类型/默认 | 约束 |
| --- | --- | --- |
| `key` | string/必填 | 完整变量键，项目内唯一 |
| `label` | string/必填 | 中文显示名 |
| `instance_id` | string/必填 | 对应真实设备 |
| `port_id` | string/null | 端口量填写 |
| `channel_id` | string/null | 通路量填写 |
| `value_type` | number/boolean/text | 与帧值一致 |
| `quantity` | string/必填 | 物理量种类 |
| `unit` | UnitSpec/null | number 必填，boolean/text 为 null |
| `mass_basis` | none/mixture/dry_air/water | 质量相关量必须标明基准 |
| `source` | parameter/port/state/derived/system | 沿用现有概念 |
| `writable` | bool/false | 仅 runtime 参数为 true |
| `nullable` | bool/false | 例如 shr、dew_point 可为 true |
| `available_in` | steady/dynamic 的数组 | 动态累计量只含 dynamic |
| `contract_version` | Literal[1]/1 | 目录语义版本 |

### 6.2 AirVariableCatalogResponse

`contract_version:int=1`、`project_id:string`、`run_id:string|null=null`、`project_revision:int|null=null`、`variables:AirVariableDescriptor[]`、`diagnostics:Diagnostic[]=[]`。项目预览目录无 run_id；运行目录来自运行创建时快照，不能被当前项目重命名覆盖。

### 6.3 运行级 air_metadata（新增持久化 JSON）

| 字段 | 类型 | 内容 |
| --- | --- | --- |
| `contract_version` | 1 | 固定 |
| `engine_version` | string | 运行时引擎版本 |
| `property_backend` | string | coolprop_ha |
| `property_version` | string | 实际安装 CoolProp 版本，不写死为文档版本 |
| `continuity_basis` | dry_air | 固定 |
| `enthalpy_basis` | dry_air | 热湿输运基准 |
| `project_snapshot_hash` | 64 位小写 SHA-256 | 规范快照摘要 |
| `variable_catalog` | AirVariableDescriptor[] | 冻结目录 |
| `assumptions` | string[] | 有效存量房间、外部 ADP 冷源、教学塔模型等 |

元数据不重复塞进每一帧。RunRecordResponse 新增 `air_metadata:dict|null`，旧运行为 null。反序列化须容忍旧记录缺少该字段。

## 7. 健康能力字段

现有 `capabilities.air_duct` 保留。`capabilities.moist_air` 继续表示存在湿空气基础能力，不能用它区分 Phase 2a 与本方案；增加 `moist_air_contract_version:int|null`、`wet_cooling_coil:bool`、`air_humidifier:bool`、`ahu_components:bool`、`air_room:bool`、`cooling_tower_moist:bool`、`air_variable_catalog:bool`、`air_reports:bool`。全部新布尔默认 false，只有对应验收门槛满足才设 true；本方案客户端必须检查 `moist_air_contract_version==1`，旧 Phase 2a 缺此字段时显示需升级。

Python 模块兼容能力由模块自身 sdk 声明；health 的 true 不能替代模块能力协商。Studio 用这些字段显示功能入口，不用引擎版本字符串猜测功能。

## 8. 前端项目文档扩展

原型沿用 `project.solverOptions` 保存规范 SolverOptions，不新建另一套 moistAir 物理配置。显示输入只在编辑草稿中存在。

拟新增 `project.airSideView`（UI 配置，不进规范 Project）：

| 字段 | 类型/默认 | 约束 |
| --- | --- | --- |
| `schema` | 1 | 固定 |
| `selected_instance_ids` | string[]/[] | 最多 100，删除设备时去除无效 id |
| `observed_keys` | string[]/[] | 最多 64，按元数据验证 |
| `active_tab` | distribution/psychrometrics/moisture/compare | 默认 distribution |
| `reference_pressure_pa` | float/101325 | 仅状态图网格参考；点本身仍用真实压力 |
| `comparison_run_ids` | string[]/[] | 最多 4，同一变量、基准和兼容合同才可叠加 |
| `source_fingerprint` | string/null | 最后绑定的项目已应用配置摘要，用于结果过期判断 |

此字段随 ProjectDocument/工作区保存；bridge 显式跳过，不会被 StrictModel 当作规范 Project 新字段。
