# 通用计算适配层

FluidNet 在 `fn_engine.adapters` 中提供统一的计算入口，供网页、桌面程序、设备选型工具和其他服务复用。业务程序负责自己的建筑、楼层、订单或设备数据，把需要计算的部分映射为适配器输入；FluidNet 负责单位转换、参数校验、调用算法和结果封装。

Python 与 HTTP 使用同一个 `AdapterRegistry`。首批适配器调用现有 `fn_sdk`、物性服务、编译器、稳态求解器和模块设计 Worker。扩展新业务只需注册输入模型、输出模型和同步处理函数。

## 入口和首批能力

| 入口 | 用途 |
| --- | --- |
| `GET /api/v1/adapters` | 返回 `contract_version: 1` 和当前实例的全部适配器、版本、JSON Schema、可用单位 |
| `GET /api/v1/adapters/{adapter_id}?version=1` | 查询一个明确版本的输入和输出定义 |
| `POST /api/v1/adapters/execute` | 执行一次同步计算，返回结果或结构化错误 |
| `default_registry().execute(request)` | Python 进程内调用，采用同一份请求和结果合同 |

以下 16 项能力的初始版本均为 `1`。括号内为省略单位声明时使用的规范单位；完整必填项、默认值和范围以发现接口为准。

| `adapter_id` | 输入 | 输出 |
| --- | --- | --- |
| `hydraulics.pipe_pressure_drop` | 质量流量、密度、动力黏度、长度、内径、可选粗糙度 | 圆管单相沿程压降 `pressure_drop`（Pa） |
| `hydraulics.local_pressure_drop` | 质量流量、密度、内径、局部阻力系数 K | 局部压降 `pressure_drop`（Pa） |
| `hydraulics.valve_pressure_drop` | 质量流量、密度、Kv、开度 | 阀门压降 `pressure_drop`（Pa） |
| `hydraulics.kv_from_loss_coefficient` | 内径、局部阻力系数 K | `kv`（m3/h） |
| `hydraulics.mass_to_volume_flow` | 质量流量（kg/s）、密度（kg/m3） | `volume_flow`（m3/h） |
| `hydraulics.volume_to_mass_flow` | 体积流量（m3/h）、密度（kg/m3） | `mass_flow`（kg/s） |
| `thermal.heat_exchanger_effectiveness` | `ua`、`capacity_a`、`capacity_b`（W/K）；可选 `counterflow` | 单相显热 ε–NTU 效率 `effectiveness`（1） |
| `properties.fluid_state_pt` | 绝对压力（Pa）、温度（K）、可选原生 `FluidConfig` | 嵌套原生 `FluidState`，保持原单位 |
| `properties.moist_air` | `input_mode`、绝对压力及温度/含湿量/相对湿度/焓的对应组合 | 温度、含湿量、相对湿度、干空气焓、密度、露点和湿球温度 |
| `network.validate` | `project`：原生 `Project` 对象 | 原生 `ValidationResponse`，含 `valid` 和诊断 |
| `network.solve_steady` | `project`：原生 `Project` 对象 | 原生 `RunFrame`，不创建运行历史 |
| `modules.design` | 原生 `ModuleDesignRequest` 的字段 | 原生 `ModuleDesignResponse` 参数建议，不保存或应用 |
| `hydronics.design` | 通用树形管段、末端热流、水温/温差、管径与泵阀目录 | 设计水量、管径、环路阻力、额外平衡需求和有来源的泵阀候选 |
| `hydronics.design_cases` | 2～8 个具名工况，各含完整 `HydronicDesignInput`，共用同一管路几何与内径目录 | 逐段共用管径、各工况初选管径与决定工况、按共用管径复算的完整工况结果 |
| `ventilation.requirements` | 区域列表：面积、层高、人数、人均新风量和机械换气次数 | 每区两种需求、采用量和决定条件，及逐区取大后的汇总 |
| `airflow.duct_design` | 指定末端风量的树形风管、圆形/矩形内尺寸目录、空气状态及选管限值 | 流量汇总、尺寸、流速、分项总压损失、最不利路径、平衡需求及风机全压/功率估算 |

管道压降不包含局部阻力或高差；压降和流量保留方向符号。Kv 单相计算要求开度大于零。`network.validate` 成功完成检查但发现工程问题时返回 HTTP 200 和 `outputs.valid=false`，调用方必须读取该字段。

`hydronics.design` 使用 `HydronicDesignInput`/`HydronicDesignOutput`，独立 Schema 位于 `contracts/hydronic-design-*.schema.json`。输入没有建筑或房间类型：`segments` 通过 `id/parent_id` 构成一棵树，仅叶节点填写 `heat_load_w` 和末端阀压降，内部节点汇总热流。`length_m` 与 `local_loss_coefficient` 均为供回水合计。其他业务可将自己的负荷和布置映射成此结构。

该计算以设计流量选择管径，用现有单相纯水物性与 SDK 压降求最不利路径；闭式系统不加静扬程。非最不利末端的 `balancing_pressure_drop_pa` 是待实现的平衡需求，不表示未平衡管网已经满足设计流量。超出管径目录能力时返回 `feasible=false` 并暂停泵推荐，调用方必须读取该标志。无负荷时不选泵。泵仅在曲线标明的流量区间内插值，返回设计流量处的固定转速曲线点，不求实际泵网交点；效率是整体电到水效率。阀门按 `Kv ≤ Kvs ≤ 2Kv` 择小匹配，设计 Kv 不能直接当作执行器开度。

目录由调用方传入；泵和阀均要求 `data_kind`（`example` 或 `manufacturer`）及 `source`。这些来源标记是调用方声明，不代表引擎审核。引擎不内置任何真实厂商数据，示例业务可维护自己的目录。

### 多工况共用管路

`hydronics.design_cases` 使用 `HydronicCasesInput`/`HydronicCasesOutput`，独立 Schema 位于 `contracts/hydronic-cases-*.schema.json`。`inputs.cases` 的每项为 `{id, name, inputs}`，工况编号不可重复；不限制为制冷/供热，其他业务可提供不同设计条件。各工况的管段编号、上级关系、管长、局部 K、指定 DN、粗糙度以及 DN 与实际内径的对应关系必须一致，列表顺序可不同。热流、水温、温差、设备与阀压降、校核限值及设备目录可分别设置。

算法先调用单工况设计分别初选，再逐段按**实际内径**取最大需求，用选定的共用 DN 重新计算所有工况。复算会更新流速、比摩阻、沿程与局部损失、最不利路径、额外平衡需求和泵阀候选。指定 DN 原样保留并校核，不能满足时不自动放大。原有 `hydronics.design` 的合同与行为不变。

输出 `shared_pipes` 中的 `minimum_dn_by_case` 是各工况初选值（指定管径时是指定值；超限时是目录最大内径的尝试值，仍需检查 `feasible`），`governing_cases` 给出达到最大内径需求且有负荷的工况。`cases[].design` 是使用共用管径复算后的完整结果；顶层 `feasible` 为所有工况管路校核的合取，不表示存在同一台合格的共用泵或同一组阀门。调用方必须逐工况检查候选设备，不得拼接不同工况的最大流量与最大扬程。

下面的 Python 示例可直接执行，HTTP 使用同样的请求体：

```python
from fn_engine.adapters import default_registry

pipe = {"id": "terminal", "name": "末端回路", "parent_id": None,
        "length_m": 40.0, "local_loss_coefficient": 5.0}
common = {"pipe_sizes": [{"dn": 20, "inner_diameter_m": 0.0217},
                         {"dn": 25, "inner_diameter_m": 0.0273},
                         {"dn": 32, "inner_diameter_m": 0.0359}]}
result = default_registry().execute({
    "adapter_id": "hydronics.design_cases",
    "version": 1,
    "inputs": {"cases": [
        {"id": "case_a", "name": "设计条件 A", "inputs": {
            **common, "temperature_k": 282.65, "temperature_difference_k": 5.0,
            "segments": [{**pipe, "heat_load_w": 12000.0}]}},
        {"id": "case_b", "name": "设计条件 B", "inputs": {
            **common, "temperature_k": 313.15, "temperature_difference_k": 10.0,
            "segments": [{**pipe, "heat_load_w": 18000.0}]}}
    ]},
})
print(result.outputs["shared_pipes"])
```

此示例未提供泵阀目录，只进行管路校核。所有嵌套字段仍按字段名所示单位传入，多工况模型不接受嵌套路径单位转换。

湿空气模式分别为 `ptw`（`temperature` + `humidity_ratio`）、`ptrh`（`temperature` + `relative_humidity`）、`phw`（`enthalpy_dry_air` + `humidity_ratio`），每次只提供对应组合。干空气的露点未定义时为 `null`。

### 新风与低压风管

`ventilation.requirements` 接受 `zones`，每区包含 `id/name/area_m2/height_m/people/per_person_m3_h/air_changes_h`。逐区计算 `max(people × per_person_m3_h, area_m2 × height_m × air_changes_h)` 再汇总。两种需求不相加，也不先汇总后取大；调用方应将渗透量与机械新风区分。所有规范取值由调用方确定，适配器不内置用途分类或规范合规判定。Schema 为 `contracts/ventilation-*.schema.json`。

`airflow.duct_design` 使用 `DuctDesignInput`/`DuctDesignOutput`，Schema 为 `contracts/duct-design-*.schema.json`。仅叶节点填写实际计算状态下的 `flow_m3_h`，内部节点汇总下游风量。几何为单路送风或排风树；管长为**单程**。`duct_sizes` 的圆形规格填写 `diameter_m`，矩形填写 `width_m/height_m`，另一形状字段应省略。矩形高度保持输入方向，不自动旋转。每段 `fixed_size_id` 可指定规格，也可省略自动选择。

自动按真实截面积递增试选，同时检查流速、比摩阻、安装限高和最大宽高比（至多 4）。圆管使用实际内径，矩形使用真实面积计算速度、水力直径 `2ab/(a+b)` 计算沿程阻力。矩形层流采用截面 Poiseuille 修正，Re 2300～4000 与 SDK Haaland 模型线性过渡；湍流按水力直径近似。物性由指定温度和绝对压力下的干空气取得，不含结露或热湿过程。

`equipment_pressure_drop_pa` 为设计流量处的设备及风口**全压损失**，应包含实际入口、出口损失；局部 K 采用该管段平均速度作为参考。系统阻力取最大根到末端路径，较短路径返回待实现的平衡阻力。`required_fan_total_pressure_pa` 加上 `pressure_margin_ratio`，不能直接用作机外静压；`estimated_input_power_kw` 按 `VΔp/η` 估算，η 为整体电到风效率。这里没有匹配风机曲线或求实际风网流量分配。

`feasible=false` 表示有尺寸/速度/比摩阻超限，或所需压升超过输入绝对压力的 5%（不适用低压定密度假设）；此时功率估算为 `null`，压力只作诊断。零风量时所有管路及设备压降为零，不推荐风机。调用方可独立使用任一个适配器；不依赖建筑、楼层或暖通业务对象。

```python
from fn_engine.adapters import default_registry

registry = default_registry()
fresh = registry.execute({
    "adapter_id": "ventilation.requirements",
    "inputs": {"zones": [
        {"id": "a", "name": "区域 A", "area_m2": 20.0, "height_m": 3.0,
         "people": 10, "per_person_m3_h": 30.0, "air_changes_h": 1.0},
        {"id": "b", "name": "区域 B", "area_m2": 40.0, "height_m": 3.0,
         "people": 5, "per_person_m3_h": 30.0, "air_changes_h": 2.0}
    ]},
})
ducts = registry.execute({
    "adapter_id": "airflow.duct_design",
    "inputs": {
        "duct_sizes": [
            {"id": "250x200", "name": "250 × 200", "shape": "rectangular", "width_m": 0.25, "height_m": 0.2},
            {"id": "400x200", "name": "400 × 200", "shape": "rectangular", "width_m": 0.4, "height_m": 0.2}
        ],
        "segments": [
            {"id": "main", "name": "总管", "shape": "rectangular", "equipment_pressure_drop_pa": 150.0},
            *[{"id": z["id"], "name": z["name"], "parent_id": "main", "shape": "rectangular",
               "flow_m3_h": z["design_flow_m3_h"], "equipment_pressure_drop_pa": 30.0}
              for z in fresh.outputs["zones"]]
        ],
    },
})
print(fresh.outputs["total_flow_m3_h"])  # 540 m³/h
print(ducts.outputs["required_fan_total_pressure_pa"])
```

## 请求和结果

向 `POST /api/v1/adapters/execute` 发送：

```json
{
  "adapter_id": "hydraulics.pipe_pressure_drop",
  "version": 1,
  "request_id": "external-app-3",
  "inputs": {
    "mass_flow": 1,
    "density": 1000,
    "viscosity": 1,
    "length": 10,
    "diameter": 50,
    "roughness": 0.045
  },
  "input_units": {"viscosity": "mPa.s", "diameter": "mm", "roughness": "mm"},
  "output_units": {"pressure_drop": "kPa"}
}
```

成功结果约为：

```json
{
  "adapter_id": "hydraulics.pipe_pressure_drop",
  "version": 1,
  "request_id": "external-app-3",
  "engine_version": "0.5.0",
  "outputs": {"pressure_drop": 0.678985754306627},
  "output_units": {"pressure_drop": "kPa"}
}
```

`version` 省略时固定使用 `1`，不会自动选择最新版本。`request_id` 可省略、最多 128 字符，仅用于关联请求与结果；相同 ID 的重复请求会重新计算，不提供幂等去重或持久历史。适配器 ID 是点分隔的小写名称，如 `electrical.consumption`。相同 ID 的不同版本可以并存，重复注册同一 ID 和版本会报错。

## 单位和数据边界

发现结果的 `input_schema`、`output_schema` 描述**规范单位下**的模型，包括默认值和范围。处理顺序是：输入单位转换 → 输入模型校验 → 计算 → 输出模型校验 → 输出单位转换。例如效率的规范范围是 0～1；请求 `%` 后，结果按 0～100 表示。

`input_units` 只对明确提供的顶层数值生效；默认值使用规范单位。`output_units` 只改变已声明输出字段的显示单位，返回值会列出所有可转换输出的实际单位。可用单位从每个字段的 `accepted_units` 读取，大小写和写法必须一致：

| 物理量 | 支持的单位 |
| --- | --- |
| 长度 | `m`、`mm`、`cm` |
| 压力/压差 | `Pa`、`kPa`、`MPa`、`bar` |
| 绝对温度 | `K`、`degC`、`°C`、`degF`、`°F` |
| 温差（供扩展适配器使用） | `K`、`delta_degC`、`delta_degF` |
| 质量流量 | `kg/s`、`kg/h`、`g/s` |
| 体积流量 | `m3/s`、`m3/h`、`L/s`、`L/min` |
| 密度 | `kg/m3`、`g/cm3` |
| 动力黏度 | `Pa.s`、`mPa.s`、`cP` |
| 功率/热流 | `W`、`kW` |
| 热导/热容流率 | `W/K`、`kW/K` |
| 比例 | `1`、`%` |
| 含湿量 | `kg/kg_da`、`g/kg_da` |
| 干空气比焓 | `J/kg_da`、`kJ/kg_da` |
| Kv | `m3/h` |

压力单位转换不推断表压与绝对压力；物性输入必须提供绝对压力。质量流量与体积流量需要密度，由专用适配器转换。绝对温度有零点偏移，温差使用独立规则。`kg_da` 明确表示干空气质量。

嵌套的 `Project`、`FluidConfig`、`FluidState`、`RunFrame` 和模块参数保留原生合同与单位。`project.instances...` 或 `state.temperature_k` 这样的嵌套单位路径会被拒绝。需要转换业务对象时，由调用方或专门注册的业务适配器显式完成映射。

请求包络禁止未知字段、非 JSON 对象和非有限数值。内置标量输入模型禁止用字符串或布尔值充当数字；嵌套原生模型沿用自己的校验规则。处理函数收到输入的独立副本。

## Python 使用与新业务扩展

源码目录中先设置 `$env:PYTHONPATH = 'backend'`，或通过项目现有安装方式安装依赖：

```python
from fn_engine.adapters import default_registry

registry = default_registry()
description = registry.describe("hydraulics.mass_to_volume_flow", version=1)
result = registry.execute({
    "adapter_id": "hydraulics.mass_to_volume_flow",
    "inputs": {"mass_flow": 1.0, "density": 1000.0},
    "output_units": {"volume_flow": "L/s"},
})
print(result.outputs)  # {'volume_flow': 1.0}
```

下面是独立于流体业务的电功率计算例子。保存为 `business_app.py`，即可用 `python -m uvicorn business_app:app --host 127.0.0.1 --port 8798` 启动自定义服务：

```python
from pydantic import Field
from fn_engine.adapters import AdapterDefinition, AdapterModel, UnitRule, default_registry
from fn_engine.api import create_app

class ElectricalInput(AdapterModel):
    power: float = Field(ge=0)
    efficiency: float = Field(gt=0, le=1)

class ElectricalOutput(AdapterModel):
    consumed_power: float

def consumption(values: ElectricalInput) -> dict[str, float]:
    return {"consumed_power": values.power / values.efficiency}

registry = default_registry()
registry.register(AdapterDefinition(
    adapter_id="electrical.consumption",
    version=1,
    description="由有效功率和效率计算输入功率。",
    input_model=ElectricalInput,
    output_model=ElectricalOutput,
    handler=consumption,
    input_units={"power": UnitRule("power", "W"), "efficiency": UnitRule("ratio", "1")},
    output_units={"consumed_power": UnitRule("power", "W")},
))
app = create_app(adapter_registry=registry)
```

通过同一执行接口提交 `power=5`（kW）、`efficiency=80`（%），请求输出 `consumed_power` 为 kW，得到 `6.25`。注册发生在宿主启动阶段；每个应用拥有自己的注册表，新增适配器不需要修改路由。需要只开放选定能力时，可以从空的 `AdapterRegistry()` 开始注册。处理函数为同步函数，输入输出可使用自己的 Pydantic 模型；推荐继承 `AdapterModel` 获得严格校验。

适配器版本标识其字段、单位约定与语义，破坏兼容性的改动应登记新版本。它不冻结底层算法二进制；结果同时提供 `engine_version`，严格复算还应固定部署源码版本。发现接口的 `contract_version` 标识适配层包络的版本，与单项适配器版本分开。

## 错误与访问权限

适配器校验和计算错误采用以下结构；Python 调用抛出 `AdapterError`，从 `error.status` 与 `error.detail` 读取相同内容：

```json
{
  "detail": {
    "code": "ADAPTER_UNIT_INVALID",
    "message": "mass_flow 不支持单位 'm3/h'；可用：kg/s, kg/h, g/s",
    "adapter_id": "hydraulics.mass_to_volume_flow",
    "version": 1,
    "request_id": "external-app-3",
    "field": "input_units.mass_flow",
    "diagnostics": []
  }
}
```

| 错误码 | HTTP | 含义 |
| --- | --- | --- |
| `ADAPTER_NOT_FOUND` | 404 | 适配器或版本不存在 |
| `ADAPTER_INPUT_INVALID` | 422 | 包络或输入字段校验失败 |
| `ADAPTER_UNIT_INVALID` | 422 | 未声明、不可兼容或无法转换的单位 |
| `ADAPTER_CALCULATION_FAILED` | 422 | 原生计算失败；可用时保留 `diagnostics` 中的原始诊断码 |
| `ADAPTER_INTERNAL_ERROR` | 500 | 未预期的处理函数异常，详情记录在服务日志 |
| `ADAPTER_OUTPUT_INVALID` | 500 | 处理函数返回值不符合输出模型或无法形成有限 JSON |

权限沿用现有宿主配置：发现接口需要 read 权限，执行接口需要 control 权限；启用认证时携带 `Authorization: Bearer <token>`。401/403 继续使用已有 `AUTH_REQUIRED`/`AUTH_SCOPE` 错误包络。自定义宿主也可通过 `create_app(auth=..., cors_origins=..., adapter_registry=...)` 使用相同设置。

该层处理一次性同步计算。动态运行、项目保存、运行历史、变量写入与订阅继续使用[现有运行 API](API.md)。`modules.design` 的代码仍在现有 Worker 中执行，部署权限边界沿用原服务。

## 示例与验证

[可运行客户端](../examples/external_clients/calculation_adapters.py) 同时提供标准库 HTTP 调用和进程内调用：

```powershell
# 不启动服务，直接使用本地注册表。
$env:PYTHONPATH = 'backend'
python examples/external_clients/calculation_adapters.py --local

# 服务启动后，通过 HTTP 使用同样的请求。
python examples/external_clients/calculation_adapters.py
```

HTTP 模式读取 `FLUIDNET_URL`（默认 `http://127.0.0.1:8798`）和可选的 `FLUIDNET_TOKEN`。入口 JSON Schema 位于 `contracts/adapter-*.schema.json`，OpenAPI 位于 `contracts/openapi.json`，单项能力的模型通过发现接口提供。

回归测试入口为 `tests/test_adapters.py`、`tests/test_adapter_api.py`、`tests/test_hydronic_design.py` 与 `tests/test_airduct_design.py`，已加入快速 CI。覆盖独立物理算式、单位边界、注册与版本隔离、跨业务扩展、Python/HTTP 一致性、原生管网/模块设计、认证，以及多工况水管复算、新风逐区取大、圆/矩形风管摩阻、路径守恒与尺寸超限。模型与 OpenAPI 通过 `scripts/generate_contracts.py` 生成和检查。
