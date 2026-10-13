# 原型与后端接入

前端来源为当前 Studio 原型，保留 HTML/CSS 布局与交互。原单文件内的 JavaScript 已移入 studio.js，新增 engine-client.js；index.html 依次加载二者。

已完成的映射：

1. 启动读取 /health、/catalog 和 /modules；内置目录与版本化 Python 模块包合并到模块库，清单参数和版本/哈希同步到原型控件。
2. 检查连接提交原型活动项目到 /prototype/normalize，再调用 /projects/validate。
3. 稳态调用 /runs。health 报告 `live_runs` 时，动态项目的运行/单步创建一个后台会话（`execution_mode` 默认 realtime，单步时 `start_paused`，`history:'trend'`），之后的运行、单步、暂停、停止和运行中“应用参数”都是对同一 run_id 的命令；前端等待命令的 applied/rejected 事件，并用 `history?offset=` 增量拉取新帧。会话结束（completed/failed/cancelled/interrupted）后清空 `runId`。勾选“持续运行”时 `duration_s=null`；浏览器只保留最近 2001 行（`LIVE_ROWS`），曲线页“全程（抽稀）”读 `/runs/{id}/overview`，运行中每 2 秒刷新一次，抽稀数据不写入 localStorage。
4. 暂停/停止先调用后端 `POST /runs/{run_id}/command`(仅后台运行),再停止本地回放;独立验证台没有后台 `run_id`,只停本地回放;已暂停的项目运行继续时额外调用 `resume` 同步后端。无进行中的后台任务时只停止本地回放。改动已应用参数后重新提交运行。
5. 每帧保留 canonical 规范变量字典，并映射到原型变量表的显示单位及 sampleKey。
6. 主系统演示 sampleStep/sampleHistory 已移除。初始演示记录为空，不从公式构造伪造流量或温度。
7. 本地存储使用 fluidnet-prototype-engine-v1，与原型原有 storage key 分开。

后台 `run_id` 记录在 `owner.run.runId`,暂停/停止据此取消真实任务;控制端点返回 404/501 时降级为仅本地回放,并在事件中说明。后台轮询有 3000 次或 300 秒双重上限,先到者生效,超时把该次前端运行标为失败并给出原因。

绘图保留原型的主管、A 路、B 路快捷观察，对应 P1/V1/V2 的真实单通路变量；其他设备从“全部变量”加入观察。前端端口流量按照标称方向显示，后端端口流量统一按流入设备为正。

热力层的端口变量映射到原型端口变量槽：`TEMP`←`temperature_k`（°C）、`ENTHALPY`←`enthalpy_j_kg`（kJ/kg）、`VOLUME`←`density_kg_m3`、`Q`←`quality`；组分 `X` 不映射。密度与干度是状态量，不随标称流向取反。总览温度和各设备 `OUT_TEMP` 读取 `out0.temperature_k`。求解器关闭热力（`SolverOptions.thermal=false`）时这些值为 null，曲线留空。原型管道新增 `heatLoss`（散热 UA，W/K，默认 0 即绝热）与 `ambient`（环境温度，°C，默认 20），分别绑定 `heat_loss_ua_w_k` 和 `ambient_temperature_k`，单位按目录 UnitSpec 换算；旧存档在载入时按默认值补齐这两个参数及对应变量、库值和型号参数。热力诊断（THERMAL_*、COUPLING_NOT_CONVERGED、PHASE_UNSUPPORTED）与其他诊断一样按 message 显示在诊断面板。

历史瘦身：完整动态运行请求 `history:'trend'`，`trend_variables` 由 `engine-client.js` 的 `trendVariables(owner)` 生成——总览固定键 `P1/V1/V2.mass_flow_kg_s`（仅当该节点存在且只有一条启用通路，即有无前缀别名）、`P1.out0.pressure_pa`、`P1.out0.temperature_k`（仅当 P1 有流体端口 out0），加上 `state.charts.extra` 中属于当前项目的变量（经 `canonicalKeyOf` 换成规范键；旧式 `X.OUT_FLOW/PRE/TEMP` 绑定按同样规则换算），去重后最多 256 个。后端拒绝未知变量（`TREND_VARIABLE_UNKNOWN`）时自动以完整历史重跑一次。后端在关键帧之间的帧标 `full=false`，`rowFromFrame` 记为 `row.partial`：曲线和总览照常读取；设备面板、画布读数和“全部变量”经 studio `panelRow()` 取最近一个完整行，并在画布状态与设备窗口底部显示“回放：显示最近关键帧”。末帧始终完整，所以运行结束后面板显示的是最终结果。

介质：项目设置“默认介质”可选 water、air、ammonia、co2、r134a、meg30，bridge 的 `PROTOTYPE_MEDIA` 映射为 CoolProp 工质（`meg30`→`INCOMP::MEG[0.3]`）写入 `Project.fluid`；一个项目只用一种流体。压力边界温度与管道环境温度的原型控件范围放宽到 −100…400 °C，按工质的范围检查由计算服务完成。

独立验证台已对接 `/modules/test`：Python 模块的每条启用通路各接一组真实压力边界并一次求解，返回 Worker 的 evaluate 关系、模块变量、commit_step 状态、源码哈希和历史帧。设备面板与验证台按 `value_type` 渲染数值、布尔、文本和曲线参数，曲线使用 JSON 点对数组。项目中的 Python 模块同样在独立 Worker 中执行；每个实例在一次动态运行内复用同一个 Worker，成功时间步提交一次，异常或超时统一回收。

Python 包代码页的检查调用后端 `/modules/validate`，包含完整语法、Pydantic 和 Worker 入口校验；内置原型代码仍保留轻量预览。控制脚本、串口以及未实现的热力/状态模型不进入当前物理求解。

PID（v0.4.2）：「控制」页的 PID 面板写入项目的 `controllers`，归一化时原样进入 `Project.controllers`。反馈变量下拉列出目录中可采样的变量，执行参数下拉只列出 `runtime` 可写数值参数。“液位示例”“温控示例”从 `GET /api/v1/examples/{level|temperature}` 生成新项目。运行中只有设定值、手自动和手动输出可改（`controller` 命令），其余字段禁用。

新建模块使用 Python 包模板；变量属性页可编辑数值参数与输出，契约与版本页可修改完整 JSON、保存备注、查看历史并载入版本。`POST /modules/versions` 会重新试算当前提交内容，成功后更新可插入版本。保存期间继续输入会保留为后续草稿。

模块的 `publishedManifest` 表示可插入的保存版本，正在编辑的 source/contractDraft 不进入项目求解。项目 `moduleSnapshots` 固定完整定义，实例携带 `package` 引用。设备参数、端口和变量面板读取项目快照，避免库中新版参数覆盖旧项目。原型保存/导出包含快照；归一化优先使用快照并由编译器检查双哈希。浏览器草稿保存与磁盘模块版本保存是两个明确动作。

水箱（v0.4）：`PARAM_DEFS.tank` 增加罐高、初始水温、加热功率、散热 UA 和环境温度，经 `PARAMETER_BINDINGS.tank` 映射到规范参数；`STATE_VARIABLES.tank` 把 `<实例>.state.level_m` 等引擎状态量作为 runtime 变量（`canonicalId`）放进设备变量表，可加入曲线并随 trend 历史保留。旧的本地存档由 `backfillBuiltinParams` 补齐新参数与状态变量。运行以 `TANK_EMPTY`/`TANK_FULL`/`STEP_NOT_CONVERGED` 停止时，前端回放已算出的帧并在事件中给出停止原因。

管道热容（v0.4.1）：`PARAM_DEFS.pipe` 增加热容分段数和管壁热容（kJ/K），绑定 `thermal_cells`、`wall_heat_capacity_j_k`；`STATE_VARIABLES.pipe` 提供管内平均温度和储热功率，只有分段数大于 0 时后端才输出，否则曲线显示为空。

后续可把剩余 UI 描述完全迁移为目录驱动；不需要重写画布与设备编辑器。

工质（v0.4.4）：项目设置 → 介质配置新增“物性字符串”和“组分比例基准”，保存为原型项目的 `fluid`、`fluidReference`；非空时替代下拉的默认介质，归一化后进入 `FluidConfig.fluid/reference`。提示文字根据 health 的 `capabilities.refprop.installed` 显示是否检测到 REFPROP。
