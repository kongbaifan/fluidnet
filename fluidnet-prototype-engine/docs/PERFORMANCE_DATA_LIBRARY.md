# 设备性能资料库

2026-11-06。资料库接收用户提供的泵扬程、风机压升及效率曲线。导入校验不等于厂家标定、性能认证或现场验证。项目不代填厂家数据；仓库附带的曲线仅供教学与操作演示。

## 文件与单位合同

文件必须为 UTF-8（允许 BOM），不超过 2 MiB，包含 2 至 20000 个点。CSV 首行须有且仅有两个唯一列名，缺省 `flow,value`；导入表可显式指定其他列名。每行恰有两个有限数值。JSON 接受 `[[0,30],[10,20],[20,0]]` 或仅含 `points` 字段的对象；元数据统一在导入表填写。重复 JSON 字段、空值、布尔值、非有限数、公式、乱序或重复横坐标均拒绝。程序不求值电子表格公式，不自动排序、去重、补点或外推。

| kind | 纵轴输入单位 | 保存的规范纵轴 |
| --- | --- | --- |
| pump_head | m | m |
| fan_pressure | Pa、kPa | Pa |
| efficiency | 1、% | 1，且 0 < η ≤ 1 |

横轴仅接受 `m3/h`、`m3/s`、`L/s`，规范横轴为 `m3/h`。流量非负且严格递增。非效率纵轴须非负；非单调曲线允许存档并带警告，直接应用到单调选型算法时会拒绝。

导入元数据包括稳定 `id`、名称、资料类型、格式、原文件名、原文件完整字节的 `content_base64`、横纵轴单位、来源说明，以及参考工质、正的有限参考密度（kg/m³）和转速（rpm）。`manufacturer` 和 `model_name` 可空，不推测厂家。可选 `valid_flow_min/max` 使用输入流量单位，必须位于资料点范围内，且下限小于上限。缺省使用完整点范围。

## 版本、存储与追溯

`POST /api/v1/performance-data/preview` 只解析返回 `source_points`、`points_m3_h`、规范单位、有效范围、警告和哈希。`POST .../versions` 保存不可变版本，首版 `expected_latest_version=0`，追加版本必须传当前末版号；版本冲突返回 409，绝不覆盖旧版。一个 ID 的资料类型不能改变。失败事务不留下半个版本。

每版保存完整导入声明、原字节、原始/规范点、UTC 创建时间、版本号和两类 SHA-256：`source_hash` 对应原文件字节；`content_hash` 对应排序、紧凑 JSON 编码的导入声明（包括原字节，排除乐观并发字段 `expected_latest_version`）。读取时重新解析并比对原文件、元数据、规范点及哈希；检测不一致后报存储完整性错误，不静默修复。

配置 `create_app(data_root=...)` 或使用项目正常 `serve` 启动后，版本保存在同一工作区 SQLite 的 `performance_versions` 表，复用锁和事务，因此正常重启及现有工作区 ZIP 备份/恢复均包含资料。测试直接 `create_app()` 时资料仅驻内存；列表的 `persistent` 明确返回该区别。数据库哈希用于检测意外修改，不是对抗具有数据库写权限者的数字签名。

| 接口 | 作用 |
| --- | --- |
| GET /api/v1/performance-data | 全部版本摘要及 persistent 状态 |
| POST /api/v1/performance-data/preview | 解析、单位换算与校验 |
| POST /api/v1/performance-data/versions | 原子追加不可变版本 |
| GET /api/v1/performance-data/{id}/versions/{version} | 指定版本完整资料 |
| GET /api/v1/performance-data/{id}/versions/{version}/export | 原始文件逐字节导出 |
| GET /api/v1/performance-data/compare | 按 left_id/left_version/right_id/right_version 对照 |
| POST /api/v1/performance-data/proposal | 对指定冻结模块、参数及当前草稿生成应用预览 |

对照只有在资料类型、规范单位、参考工质、密度、转速相同且有效区间相交时才计算差值。采样网格取共同有效区间内两曲线横坐标并集及区间端点，执行分段线性插值，无外推；参考条件不同则仅并列展示并解释原因，不假定相似定律成立。

## 应用到设备草稿

`proposal` 传入 `id/version/module/parameter_id/fluid` 与规范当前 `parameters`。`references` 可传当前配套参数的 `{id,version,content_hash}`；后端校验该引用、资料类型、当前曲线内容以及参考工质/密度/转速一致性。返回建议 `parameters`、完整 `provenance` 和警告，不写工程、运行实例或设备型号。

目前仅已审核算法的源代码 SHA-256 与以下映射匹配才自动生成建议，模块改写后即使 ID 或参数同名也不推断单位：`design_pump.head_curve`、`pump_variable_speed.head_curve`、`design_fan.pressure_curve` 及 `design_pump/design_fan/fan_performance.efficiency_curve`。`fan_performance` 没有资料参考密度参数，直接压升曲线导入拒绝；使用 `design_fan` 时参考密度随曲线共同提出修改。

现有性能算法要求曲线从零流量到零扬程/压升、纵轴严格递减。资料库可以存储更一般的数据，但不能表达完整有效范围的算法应用会明确拒绝。效率曲线必须从零流量覆盖配套性能曲线全部横轴范围；扩大性能范围前可先应用覆盖更广的效率曲线。不得用裁剪、虚构零点或外推规避。

参考 rpm 记录为源曲线的名义转速。当前设备使用 `speed_ratio`，没有绝对 rpm 基准；因此后端不自动根据 rpm 缩放曲线。界面须明确确认名义基准并使替换仅进入草稿，随后重新选型和验收，不能沿用旧选型结果。有效 provenance 应随设备型号保存，参数被手工改动后不得继续声称与该原资料完全一致。

## 界面使用与来源状态

模块页的“性能资料库”可导入、查看、比较版本及导出原文件；设备面板“参数与型号 → 性能资料”可以指定目标曲线和项目/回路设计工质。新增版本预填所选旧版的单位、CSV列名、有效范围与参考条件，仍需选择新文件并确认预览。应用预览显示参数差异，并确认资料 rpm 对应 `speed_ratio=1` 的基准。

“填入设备草稿”只写 `performanceDataDraft`；“预览并应用”成功后才提交为 `performanceData`。即使点完全相同、仅版本或来源不同，也保留一项待应用差异。等待运行确认期间新填的草稿保留，拒绝写入不提交来源。资料来源按已发布模块哈希、曲线及参考密度校验，手动改曲线后不再显示为原资料。

“保存为型号”按当前值或草稿保存完整曲线、文本与对应来源，型号版本保留快照；设计函数生成的型号也保留输入资料来源。插入/套用/批量套用型号核对模块版本，来源随正式参数应用提交。完整工程、工作区保存及重新载入保留两类来源状态；原始文件字节在资料库及工作区数据库备份中保留。

## 定向验收结果

2026-11-06：后端资料库 21 项通过；前端资料状态、单设备异步应用、选型、开放组工况及批量应用的相关测试通过。`node tests/browser-performance-data.mjs` 在 Edge、1920×1080、DPR 1 验证实际文件上传、非法输入及取消不落库、CSV/JSON 三个不可变版本、规范曲线比较、原文件逐字节导出、冻结定义、草稿应用、设计型号与直接保存型号、版本编辑、插入和重载，以及同点新来源必须显式应用。浏览器无未处理异常；`artifacts/performance-comparison-1080p.png` 和 `artifacts/performance-device-1080p.png` 为本地截图（不纳入版本控制）。

`python -m pytest -q tests/test_performance_data.py` 覆盖单位换算、文件拒绝、重启与逐字节导出、版本冲突、并发提交、注入写失败回滚、篡改拒绝、现有备份恢复、只读应用预览、算法与配套范围/引用/参考条件校验。另运行该实现和测试文件的 Ruff、实现文件 mypy。按用户要求不运行全量测试。
