# 06 完整示例、前端行为与字段映射

以下是**目标实现后的合同示例**，不是当前服务已经接受的输入，也没有在本轮运行求解。示例数值用于说明如何填写字段；验收结果需在实施阶段生成。

## 1. 最小完整湿盘管 Project

这是可作为请求体保存的完整 JSON：包含两个压力边界、一台盘管、所有引用的内置模块定义与连接，不依赖把 `modules` 留空后由服务端猜目录。省略的公共字段采用 Pydantic 默认。

```json
{
  "schema_version": 1,
  "id": "air-coil-minimal",
  "name": "湿盘管最小算例",
  "description": "规定入口状态、盘管表面温度和旁通系数；冷源为外部规定条件",
  "fluid": {"backend": "coolprop", "fluid": "Air", "phase_policy": "gas"},
  "solver": {
    "thermal": true,
    "moist_air": true,
    "property_coupling": "node",
    "hydraulic_method": "dense",
    "analytic_jacobian": false,
    "moist_air_options": {"contract_version": 1, "property_backend": "coolprop_ha"}
  },
  "modules": [
    {
      "schema_version": 1,
      "id": "source",
      "name": "压力边界",
      "version": 2,
      "runtime": "builtin",
      "solver_model": "pressure_source",
      "ports": [{"id": "out0", "label": "边界端口", "domain": "fluid", "direction": "bidirectional"}],
      "parameters": [
        {"id": "pressure_pa", "label": "绝对压力", "default": 101325, "minimum": 60000, "maximum": 120000, "runtime": true,
          "unit": {"quantity": "pressure", "canonical_unit": "Pa", "display_unit": "kPa", "display_scale": 1000}},
        {"id": "temperature_k", "label": "温度", "default": 293.15, "minimum": 253.15, "maximum": 333.15, "runtime": true,
          "unit": {"quantity": "temperature", "canonical_unit": "K", "display_unit": "°C", "display_offset": -273.15}},
        {"id": "humidity_ratio_kg_kg", "label": "含湿量", "default": 0.008, "minimum": 0, "maximum": 0.05, "runtime": true,
          "unit": {"quantity": "humidity_ratio", "canonical_unit": "kg/kg_da", "display_unit": "g/kg_da", "display_scale": 0.001}}
      ]
    },
    {
      "schema_version": 1,
      "id": "cooling_coil",
      "name": "湿工况表冷器",
      "version": 1,
      "runtime": "builtin",
      "solver_model": "cooling_coil",
      "ports": [
        {"id": "in0", "label": "入口", "domain": "fluid", "direction": "in"},
        {"id": "out0", "label": "出口", "domain": "fluid", "direction": "out"}
      ],
      "channels": [{"id": "ch0", "name": "空气通路", "input_port": "in0", "output_port": "out0", "relation": "resistance", "solver_model": "resistance"}],
      "parameters": [
        {"id": "coil_surface_temperature_k", "label": "机器露点", "default": 285.15, "minimum": 273.15, "maximum": 323.15, "runtime": true,
          "unit": {"quantity": "temperature", "canonical_unit": "K", "display_unit": "°C", "display_offset": -273.15}},
        {"id": "bypass_factor", "label": "旁通系数", "default": 0.15, "minimum": 0, "maximum": 1, "runtime": true,
          "unit": {"quantity": "ratio", "canonical_unit": "1", "display_unit": "1"}},
        {"id": "loss_coefficient", "label": "阻力系数", "default": 2, "minimum": 0,
          "unit": {"quantity": "ratio", "canonical_unit": "1", "display_unit": "1"}},
        {"id": "diameter_m", "label": "截面直径", "default": 0.4, "minimum": 0.001, "maximum": 10,
          "unit": {"quantity": "length", "canonical_unit": "m", "display_unit": "mm", "display_scale": 0.001}}
      ]
    }
  ],
  "instances": [
    {"id": "B1", "module_id": "source", "name": "入口边界", "position": {"x": 120, "y": 240},
      "parameters": {"pressure_pa": 101425, "temperature_k": 303.15, "humidity_ratio_kg_kg": 0.014}},
    {"id": "C1", "module_id": "cooling_coil", "name": "表冷器", "position": {"x": 420, "y": 240},
      "parameters": {"coil_surface_temperature_k": 285.15, "bypass_factor": 0.15, "loss_coefficient": 2, "diameter_m": 0.4}},
    {"id": "B2", "module_id": "source", "name": "出口压力边界", "position": {"x": 720, "y": 240},
      "parameters": {"pressure_pa": 101325, "temperature_k": 293.15, "humidity_ratio_kg_kg": 0.008}}
  ],
  "connections": [
    {"id": "e1", "source": {"instance_id": "B1", "port_id": "out0"}, "target": {"instance_id": "C1", "port_id": "in0"}},
    {"id": "e2", "source": {"instance_id": "C1", "port_id": "out0"}, "target": {"instance_id": "B2", "port_id": "out0"}}
  ],
  "selected_variables": ["C1.out0.temperature_k", "C1.out0.relative_humidity", "C1.condensate_kg_s", "C1.cooling_load_w"]
}
```

示例内 source.version=2 表示本方案定义的目标版本；实际交付应从目标 catalog 冻结完整定义与哈希，不拿此手写简化定义替代已签名模块包。当前内置定义无 Python package，因此不填 `package/content_hash` 假值。新目录中的内置 VariableSpec 由 02 的统一目录生成，示例省略它们不改变物理输入。

调用顺序：POST `/projects/validate` 提交该 Project；成功后 POST `/solve` 可得到一帧。需要历史/报告时把它放到 `RunRequest.project`，POST `/runs?background=true`，再读取 run_id。不要在 JSON 中写 `...` 或 `${project}` 占位后当作实际请求。

## 2. 最小客户端组装示意

以下是后续文档中的可用客户端样例形式，当前仅保存代码文本，不执行网络请求。它从目标服务读取目录并固定所需模块，避免复制大量目录字段。

```javascript
async function createWetCoilRun(baseUrl, token, projectInput) {
  const headers = {"Content-Type": "application/json"};
  if (token) headers.Authorization = `Bearer ${token}`;
  async function request(path, body) {
    const response = await fetch(baseUrl + "/api/v1" + path, {
      method: body === undefined ? "GET" : "POST",
      headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(payload.detail));
    return payload;
  }
  const health = await request("/health");
  if (health.capabilities.moist_air_contract_version !== 1 || !health.capabilities.wet_cooling_coil)
    throw new Error("服务尚未支持本合同版本的湿盘管");
  const catalog = await request("/catalog");
  const used = new Set(projectInput.instances.map(x => x.module_id));
  const modules = catalog.modules.filter(x => used.has(x.id));
  if (modules.length !== used.size) throw new Error("目录缺少所需内置模块");
  const project = {...projectInput, modules};
  const checked = await request("/projects/validate", project);
  if (!checked.valid) throw new Error(JSON.stringify(checked.diagnostics));
  return request("/runs?background=true", {project, mode: "steady"});
}
```

完整实现还需处理后台 failed、轮询期限与停止/订阅释放，复用已有外部客户端示例，不在 UI 中复制第二套运行状态机。

## 3. 六个交付示例

| `/examples/{name}` 新名称 | 拓扑 | 用途/观察键 |
| --- | --- | --- |
| `air-coil-wet` | 入口边界→盘管→出口边界 | 干湿切换、凝水、SHR、冷量 |
| `air-mixing` | 新风/回风各经阻力→混合箱→出口阻力→边界 | dry-air 加权混合、新风比例 |
| `ahu-wet` | 两路混合→过滤→湿盘管→再热→加湿→风机→送风边界 | AHU 状态点全过程 |
| `ahu-room` | AHU 送风→房间→回风分流；部分排风，部分回到混合箱 | 房间温湿度、散湿/渗透负荷；必须有压力参考 |
| `air-parallel-wet` | 风机后两支路盘管/过滤器→汇合 | m>n、风量分配、跨支路混合 |
| `cooling-tower-moist` | 水压边界→塔→回水压力边界；空气为塔内部边界 | 排热、逼近度、四项水耗 |

每个示例交付：规范 Project JSON、原型可导入版本、参数来源/教学假设、独立参考计算说明、期望行为和适用范围。六个例子是功能验收算例，不恢复已取消的完整课程产品封装。

## 4. 典型设备参数填写

### 4.1 房间实例

```json
{
  "id": "R1", "module_id": "air_room", "name": "单区房间",
  "parameters": {
    "volume_m3": 100,
    "initial_temperature_k": 299.15,
    "initial_humidity_ratio_kg_kg": 0.010,
    "initial_pressure_pa": 101325,
    "additional_heat_capacity_j_k": 1000000,
    "envelope_ua_w_k": 100,
    "outdoor_temperature_k": 308.15,
    "outdoor_humidity_ratio_kg_kg": 0.014,
    "infiltration_dry_air_kg_s": 0.01,
    "sensible_load_w": 1000,
    "moisture_load_kg_s": 0.0001,
    "moisture_source_temperature_k": 307.15
  }
}
```

这是实例片段，必须和 air_room 模块定义及 supply_in/return_out 连接一同加入 Project，不能单独当作运行请求。

### 4.2 加湿器实例

```json
{
  "id": "H1", "module_id": "humidifier", "name": "等焓加湿器",
  "parameters": {
    "mode": "adiabatic",
    "moisture_addition_kg_kg": 0.002,
    "saturation_action": "limit",
    "loss_coefficient": 1,
    "diameter_m": 0.4
  }
}
```

### 4.3 冷却塔实例

```json
{
  "id": "CT1", "module_id": "cooling_tower_moist", "name": "湿空气冷却塔",
  "parameters": {
    "air_temperature_k": 303.15,
    "air_pressure_pa": 101325,
    "air_humidity_ratio_kg_kg": 0.014,
    "air_volume_flow_m3_s": 3,
    "contact_effectiveness": 0.7,
    "cycles_of_concentration": 3,
    "drift_fraction": 0.0002,
    "makeup_temperature_k": 293.15,
    "loss_coefficient": 2,
    "diameter_m": 0.05
  }
}
```

塔项目使用 Water/liquid、moist_air=false；其空气边界来自上述 parameters，不在水项目放空气 source。

## 5. 批量工况请求

POST `/projects/ahu-example/batches/preview`；参数扫描 values 是**显示单位**，和普通运行变量写入使用规范单位不同。这里机器露点 8/10/12/14 的单位是 °C，由服务端用保存版本的 UnitSpec 转成 K。

```json
{
  "revision": 7,
  "sweep": {
    "instance_id": "C1",
    "parameter_id": "coil_surface_temperature_k",
    "values": [8.0, 10.0, 12.0, 14.0]
  },
  "variables": [
    "C1.out0.temperature_k",
    "C1.out0.relative_humidity",
    "C1.condensate_kg_s",
    "C1.cooling_load_w"
  ],
  "options": {"mode": "steady", "duration_s": 60, "dt_s": 1}
}
```

创建时复用该主体并增加 `request_id`、服务端返回的 `preview_hash`、`name`，发送 POST `/projects/ahu-example/batches`。不能自行编造 preview_hash。选择已有工况时填写 scenario_ids 并省略 sweep，二者互斥。

批次仍用原路由获取状态、取消和导出。CSV 说明输入列为显示单位、结果列按各变量 UnitSpec 标注；禁止在同一列混写 °C 和 K。

## 6. 前端页面与布局

唯一设计视口为 1920×1080。`air-side.js` 由 index.html 在 engine-client/project-services 之后、studio.js 之前加载；通过现有注册入口挂载，避免依赖 DOM 尚未创建时立即查询节点。

```text
顶部：项目名 / 已保存修订 / 当前运行 / 状态 / 结果是否过期
左栏：实际设备列表与筛选（风管、风机、盘管、房间、塔）
中部：风量分配 | 热湿状态 | 凝水与水耗 | 方案比较
右栏：选中设备的参数与本帧变量，明确已应用值/草稿值
底部：曲线、图例、当前时间、诊断摘要与完整诊断入口
```

| 页面/组件 | 字段与行为 | 错误/空状态 |
| --- | --- | --- |
| 项目物性配置 | 湿空气开关；显示 Air/gas、thermal/node 联动；不隐藏联动结果 | 后端能力不足禁用并说明 |
| 边界输入 | T、p、w；可辅助用 RH 查询转换，规范保存只用 w | 饱和冲突定位边界参数 |
| 设备参数 | 根据 ParameterSpec 生成控件；text 枚举用已注册选项，不新增伪 enum 字段 | 非法值保留草稿，应用失败不覆盖 |
| 风量表 | 设备、入口/出口总流量、干空气流量、实际体积流量、压差 | 零流量为 0；不适用为“—” |
| 热湿状态图 | T 为横轴、w 为纵轴，服务端网格，实际端口点；点标识与压力提示 | 数据缺失不补点，连线只连实际拓扑相邻点 |
| 风机工作点 | 该运行固定曲线与当前实际体积流量/压升 | 固定密度近似给出假设提示 |
| 盘管指标 | 显热、潜热、冷源负荷、凝水、SHR、干/湿状态 | SHR=null 显示“无冷却负荷” |
| 加湿器指标 | 请求、实际加水量、限幅状态、补热 | 限幅原因可点击定位 |
| 房间指标 | T/RH/w、负荷、存量、累计量 | 未完成状态步不显示为有效结果 |
| 冷却塔指标 | 出水温度、逼近度、蒸发/飘水/排污/补水 | 不可行工作点显示错误而非 0 |
| 曲线 | 由用户选择的完整变量键与目录单位驱动 | 缺帧断线；抽稀标注 stride |
| 方案比较 | 同变量、同质量基准、兼容合同，最多 4 条 | 版本不兼容时并列表，不叠成同一物理曲线 |
| 报告导出 | 从选中运行 id 下载 | 运行未终止或无帧显示服务器错误 |

## 7. 数据映射与唯一来源

| 前端数据 | 规范/服务端来源 | 保存位置 |
| --- | --- | --- |
| 湿空气物理配置 | SolverOptions.moist_air/moist_air_options | 原型 owner.solverOptions |
| 边界显示含湿量 | parameters.humidity_ratio_kg_kg 经 UnitSpec | 已应用/草稿分别保存 |
| RH 辅助编辑 | POST air/properties 返回 w | 仅转换后的 w 进入物理参数 |
| 设备列表与端口 | 当前/运行固定 ModuleDefinition | 模块快照 |
| 结果字段/单位/可写性 | AirVariableCatalogResponse | 按运行 id 缓存；目录存档 |
| 当前值与时间 | 同一 RunFrame 或 VariableValues | 内存展示，历史由服务端存档 |
| 图表/选中设备/参考图压 | airSideView | ProjectDocument/工作区 |
| 报告数字 | 运行存档及目录 | 导出文件，不回写当前项目 |

运行时参数只改当前会话的 parameter_revision；若希望保存为项目默认，需要走既有参数应用/保存工作流，不让运行脚本隐式改项目文档。

## 8. 结果过期与并发规则

1. 原型草稿变化显示“有未应用修改”；已应用物理参数、拓扑、模块版本、工质、求解选项变化后，当前工程结果标记过期。
2. 运行中接受参数命令由 parameter_revision 标识，新帧随新参数产生；旧帧保留原 revision。
3. 布局位置、颜色、页面折叠变化不改变物理 fingerprint，不触发数值过期。
4. 历史运行属于固定快照，项目当前修改不使历史数值失效；历史页面显示其来源修订。
5. 删除设备前显示引用影响；删除后清理当前绑定，撤销恢复绑定；历史 id 不重写。
6. 切换项目/运行时取消旧 fetch/订阅；返回结果需核对请求所属 run_id/fingerprint。
7. 保存冲突 409 时保留本地草稿并沿用现有“导出/载入服务器”流程，禁止自动覆盖远端新修订。

## 9. 文档与实现检查清单

- 参数面板、规范 JSON、独立验证台、批量工况的单位区别是否写清。
- 空值、无流量、无冷却、限幅、反向、过饱和是否有明确显示。
- 结果页、CSV、HTML、REST/WS 是否用同一目录及同一接受帧。
- ProjectDocument 和规范 Project 是否保持不同包络，避免导入保存混用。
- 每个入口是否检查服务端 capability，不能仅有菜单而没有真实后端能力。
