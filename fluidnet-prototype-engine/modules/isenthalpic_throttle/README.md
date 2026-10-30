# Python 等焓节流阀

本模块使用公共 `fn_sdk` 编写，声明 schema 4 的 `refrigeration.isenthalpic_throttle.v1` 角色。平台独立 Worker 执行 [module.py](module.py)，[manifest.json](manifest.json) 声明端口、参数和结果。

在模块库选择“新建模块 → 制冷等焓节流阀”可生成自定义标识的副本。无需修改引擎目录、求解器或前端设备 ID 清单。完整操作见 [制冷作者运行与验证台](../../docs/REFRIGERATION_MODULE_EXECUTION.md)。

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `kv_m3_h` | 额定 Kv，运行时固定，单位 m³/h | 0.6 |
| `opening_ratio` | 开度，规范值 0–1，界面显示百分比，可运行时写入 | 0.5 |
| `characteristic` | `linear` 或 `equal_percentage`，运行时固定 | `linear` |
| `rangeability` | 等百分比可调比，大于 1，运行时固定 | 50 |

线性有效 Kv 为 `Kv × a`；等百分比为 `Kv × (R**a − 1) / (R − 1)`，全关断为零，全开度为额定值。源代码用 `expm1` 改善小开度数值精度。

设备只支持饱和容器液相取液后的单向等焓节流；无正压差时流量为零。平台决定流股焓值和容器质量/能量记账。它不包含壅塞、两相管路压降、过热度控制或独立物理储量。

`state.accepted_segments` 是作者受管理状态，每个成功接受段增加一次；`state.transferred_mass_kg` 由平台对子步流量积分，作者不能自行覆盖。`evaluate` 只能读取已接受状态副本，不能用求值次数累计物理量。

独立验证默认使用 Ammonia 的 1.35 MPa 饱和液体入口和 0.11 MPa 出口；温度由压力确定。CO2 示例可用入口 3.5 MPa、出口 2.5 MPa。输出包括质量流量、有效 Kv、压差、出口干度、两端状态及累计通过质量。
