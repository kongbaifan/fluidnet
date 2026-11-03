# FluidNet 当前架构图与核心时序

核对日期：**2026-11-03（北京时间）**。源码基线：`7424576`；引擎声明版本 `0.5.0`。本页描述当前开发源码，包含暖通基础设备、标准机房、理想测点、多画布连接及自定义压降接口；不等同于 2026-10-22 的 v0.5.0 发布包范围。

项目由浏览器 Studio、单个 Python 服务、独立代码 Worker 和本机存储组成。**画布是编辑视图，物理回路由端口连通性决定；多个画布归一化为一个 Project，再选择对应的执行域。** 内置设备由主进程计算，Python 设备返回网络关系；全网求解和状态接受仍由主进程负责。

建议先读前四张架构图，再按需要查看六张时序图。进程、存储与源码导航见 [架构索引](ARCHITECTURE_MAP.md)。

| 图 | 要回答的问题 | 图片与可编辑源码 |
| --- | --- | --- |
| 1. 系统总览 | 界面、引擎、Worker 和数据存在哪里？ | [SVG](diagrams/architecture.svg) · [PNG](diagrams/architecture.png) · [Mermaid](diagrams/architecture.mmd) |
| 2. 多画布与计算项目 | 拆页后如何保持同一网络、保存和导入？ | [SVG](diagrams/architecture-project-model.svg) · [PNG](diagrams/architecture-project-model.png) · [Mermaid](diagrams/architecture-project-model.mmd) |
| 3. 执行域分派 | 项目由哪套模型编译和计算？ | [SVG](diagrams/architecture-execution-domains.svg) · [PNG](diagrams/architecture-execution-domains.png) · [Mermaid](diagrams/architecture-execution-domains.mmd) |
| 4. 暖通设备与测点 | 设备包、组合、机房示例和仪表如何接入引擎？ | [SVG](diagrams/architecture-hvac.svg) · [PNG](diagrams/architecture-hvac.png) · [Mermaid](diagrams/architecture-hvac.mmd) |
| 5. 后台运行 | 运行、命令、帧发布与归档何时发生？ | [SVG](diagrams/sequence-run.svg) · [PNG](diagrams/sequence-run.png) · [Mermaid](diagrams/sequence-run.mmd) |
| 6. 模块接受事务 | 用户代码的候选状态何时真正生效？ | [SVG](diagrams/sequence-module-worker.svg) · [PNG](diagrams/sequence-module-worker.png) · [Mermaid](diagrams/sequence-module-worker.mmd) |
| 7. 房间温控与风水联算 | 控制、水力、热湿迭代如何协作？ | [SVG](diagrams/sequence-air-water-control.svg) · [PNG](diagrams/sequence-air-water-control.png) · [Mermaid](diagrams/sequence-air-water-control.mmd) |
| 8. 制冷站与液体热耦合 | 制冷剂容器和液体盘管如何交换热量？ | [SVG](diagrams/sequence-thermal-coupling.svg) · [PNG](diagrams/sequence-thermal-coupling.png) · [Mermaid](diagrams/sequence-thermal-coupling.mmd) |
| 9. 模块开发与发布 | 草稿怎样变成不可变版本并绑定项目？ | [SVG](diagrams/sequence-module-release.svg) · [PNG](diagrams/sequence-module-release.png) · [Mermaid](diagrams/sequence-module-release.mmd) |
| 10. 保存与批量工况 | 修订冲突、固定快照和批次结果如何管理？ | [SVG](diagrams/sequence-workspace-batch.svg) · [PNG](diagrams/sequence-workspace-batch.png) · [Mermaid](diagrams/sequence-workspace-batch.mmd) |

图中实线为调用或数据流；虚线为生成、绑定或配置依赖。主服务内的方框是职责划分，不代表独立服务。第 4 图单独区分开发时生成链路与运行链路。

## 1. 组件、进程及存储架构

<!-- diagram: architecture -->

```mermaid
flowchart TB
  subgraph CLIENT["客户端"]
    UI["浏览器 Studio<br/>建模 · 模块 · 控制 · 结果"]
    EXT["外部客户端<br/>Python / JavaScript / 三维界面"]
  end
  subgraph MAIN["单个 Python 服务进程"]
    API["FastAPI 接入层<br/>静态页面 · 鉴权 · REST / WS"]
    AUTHOR["模块平台<br/>目录 · 验证台 · 不可变版本"]
    BATCH["批量工况<br/>BatchService · 顺序调度"]
    RUN["编译与运行编排<br/>compiler · RunManager · sessions"]
    NUM["数值内核与物性<br/>水力 · 热力 · 湿空气 · 制冷<br/>NumPy / SciPy / CoolProp"]
    TX["代码执行与接受事务<br/>runtime / batch / control<br/>主进程确认候选状态"]
    RESULT["统一结果与归档<br/>RunFrame · 测点 · 曲线<br/>后台归档线程"]
    API --> AUTHOR
    API --> RUN
    API --> BATCH --> RUN
    AUTHOR -->|真实试算| RUN
    RUN --> NUM
    NUM --> TX
    RUN -->|控制与状态| TX
    RUN --> RESULT
  end
  WORKER["独立 Python Worker 子进程<br/>设备代码 / 控制脚本"]
  DB[("SQLite 工作区<br/>项目修订 · 运行 · 批次")]
  PKG[("模块版本目录<br/>合同 · 源码 · 验证证据")]
  UI -->|HTTP / 增量轮询| API
  EXT -->|REST / 变量订阅| API
  TX <-->|JSON RPC| WORKER
  API -->|保存项目| DB
  BATCH -->|固定快照与结果| DB
  RESULT -->|持久确认| DB
  AUTHOR <-->|发布 / 加载| PKG
  classDef client fill:#eaf4ff,stroke:#79a4cc;
  classDef worker fill:#fff4df,stroke:#c7a255;
  classDef data fill:#eaf6ef,stroke:#80aa90;
  class UI,EXT client;
  class WORKER worker;
  class DB,PKG data;
```

Studio 通过 HTTP 增量轮询读取运行历史和状态；WebSocket 提供外部变量订阅。规范化、编译、数值计算、物性和模块状态接受都在主服务进程内。稳态直接进入求解器，动态由五类会话推进；后台运行使用一个调度线程和两个计算线程，批量工况依次提交到同一个 `RunManager`。

内置设备不经过 Python 设备 Worker；组合模块先展开成叶子设备，再按各叶子的运行类型执行。设备 Worker 可按实例分片，控制脚本使用独立执行器。Worker 隔离进程与生命周期，尚不是操作系统权限沙箱。REFPROP 是可选的本地物性后端。CLI 的 `--headless` 关闭前端挂载，保留 API。

模块版本在文件目录持久化，项目、运行和批次由 SQLite 保存。普通帧通过 `_ArchiveWriter` 合并落盘，保存回执与运行持久确认的具体边界见第 5、10 图。归档 Studio、旧便携包及 `output/` 概念稿不在当前启动链路中。

依据：[api.py](../backend/fn_engine/api.py)、[jobs.py](../backend/fn_engine/jobs.py)、[sessions.py](../backend/fn_engine/sessions.py)、[batches.py](../backend/fn_engine/batches.py)、[runtime.py](../backend/fn_engine/runtime.py)、[control.py](../backend/fn_engine/control.py)。

## 2. 多画布、项目合同与保存

<!-- diagram: architecture-project-model -->

```mermaid
flowchart TB
  subgraph BROWSER["浏览器"]
    STATE["项目编辑状态<br/>pages：设备 / 布局 / 连接<br/>已应用参数 + 草稿 + 模块快照"]
    LINKS["项目级连接工具<br/>project-links.js<br/>占用检查 · 移页 · 跳转 · 删除"]
    ADAPTER["计算请求适配<br/>engine-client.js<br/>选择项目与已应用参数"]
    SAVE["保存与导入导出<br/>project-services.js<br/>modeling-workflows.js"]
    LINKS -->|编辑同一连接集合| STATE
    STATE --> ADAPTER
    STATE <-->|界面项目文档| SAVE
  end
  subgraph SERVER["Python 服务"]
    BRIDGE["原型归一化<br/>bridge.normalize_prototype_export<br/>合并各页设备与连接，转换单位"]
    PROJECT["规范 Project 合同<br/>instances + connections<br/>模块快照 · 控制 · 工况 · 测点"]
    COMPILE["compile_project<br/>按端口连接构建网络<br/>展开组合并选择物理执行域"]
    RUN["统一运行与 RunFrame<br/>同一运行 ID / 时间轴<br/>变量按设备 ID 定位"]
    BRIDGE --> PROJECT --> COMPILE --> RUN
  end
  DB[("SQLite<br/>工作区 / 单项目修订")]
  ADAPTER -->|POST /prototype/normalize| BRIDGE
  SAVE <-->|保存 / 载入 / 修订恢复| DB
  PROJECT -.->|规范 JSON：按 page_id 恢复分组| SAVE
  RUN -->|轮询帧，更新各页读数| STATE
  classDef data fill:#eaf6ef,stroke:#80aa90;
  class PROJECT,DB data;
```

跨页连接沿用 `[连接ID, 起点设备, 起点端口, 终点设备, 终点端口]`，只在起点画布的 `edges` 中存储一次；另一端的连接标记由同一条记录派生。`project-links.js` 在整个项目内检索端口、移页并调整连接存放位置。界面最多八张画布，每页最多 64 台设备。

归一化汇总全部画布后形成同一个 `Project`，`page_id` 保留界面分组信息；压力节点、工质回路和参考边界由连接及设备合同确定。**移页不新增边界、不复制设备，也不单独启动求解。** 编辑拓扑或移页先停止运行；运行中切页与跳转复用已有运行。

保存链路与计算链路分开：单项目格式保存名称、布局、草稿及模块等绑定；规范 Project JSON 保留 `page_id` 和跨页连接，导入时按 `page_id` 分组，但不保证恢复全部界面信息。图中的数据库读写经 FastAPI / `WorkspaceStore` 完成。恢复或替换同 ID 项目前，浏览器先备份该项目及其绑定，再应用服务器结果；修订冲突返回 409。

依据：[project-links.js](../frontend/project-links.js)、[engine-client.js](../frontend/engine-client.js)、[project-services.js](../frontend/project-services.js)、[modeling-workflows.js](../frontend/modeling-workflows.js)、[bridge.py](../backend/fn_engine/bridge.py)、[多画布说明](CROSS_PAGE_CONNECTIONS.md)。

## 3. 编译与五类执行域

<!-- diagram: architecture-execution-domains -->

```mermaid
flowchart TB
  P["已应用参数 + 固定模块定义 + 工况<br/>规范 Project 合同"] --> C["compile_project<br/>作者角色与测点校验<br/>组合展开与执行域分派"]
  C --> F["fluid 默认路径<br/>compiler + 可选 air_compile<br/>自定义压降仅用于普通单相"]
  C --> T["thermal<br/>refrigeration/compile"]
  C --> A["cold_store<br/>refrigeration/cold_store"]
  C --> R["refrigeration<br/>refrigeration/station"]
  C --> K["coupled · thermal_couplings<br/>refrigeration/coupling"]
  F --> FS["SimulationSession<br/>水箱、管段热容、困液、房间热湿状态"]
  T --> TS["ThermalSession<br/>理想冷源 + 库房热平衡"]
  A --> AS["ColdStoreSession<br/>冷库 A · 库房/货物 + R290 机组"]
  R --> RS["StationSession<br/>集总制冷站 · 容器质量/内能"]
  K --> KS["CoupledStationSession<br/>制冷站 + 无储量液体网络"]
  FS --> H["solver + thermal<br/>单相水力、焓输运、换热与储热"]
  FS --> AIR["air_transport + air_liquid<br/>空气/冷冻水/冷却水联合迭代<br/>水盘管、冷水机组、房间、湿冷却塔"]
  RS --> RM["制冷作者适配 module_adapter<br/>等焓节流角色 · schema v4"]
  KS --> LM["液体作者适配 liquid_modules<br/>当前范围：无储量阀门/局部阻力"]
  KS --> H
  TS --> OUT["统一 RunFrame / 控制命令<br/>归档与报告"]
  AS --> OUT
  H --> OUT
  AIR --> OUT
  RM --> OUT
  LM --> OUT
```

| 执行域 | 编译与会话 | 当前边界 |
| --- | --- | --- |
| `fluid`（默认路径） | `compile_project` → `SimulationSession` | 单相流体；湿空气与风水三回路仍走此路径。普通 `CompiledNetwork` 没有单独的 `execution_domain='fluid'` 字段，由会话工厂默认分支处理 |
| `thermal` | `compile_thermal_project` → `ThermalSession` | 理想冷源与库房热模型 |
| `cold_store` | `compile_cold_store` → `ColdStoreSession` | 冷库 A，库房/货物热节点与机组状态机 |
| `refrigeration` | `compile_station` → `StationSession` | 集总制冷站；schema v4 作者模块目前仅支持节流角色 |
| `coupled` | `compile_coupled_project` → `CoupledStationSession` | 最多两条盘管关系，关联同一个饱和制冷剂容器；液体侧无物理储量 |

分派见 [compiler.py](../backend/fn_engine/compiler.py) 和 [sessions.py](../backend/fn_engine/sessions.py)。风水三回路和 `thermal_couplings` 是不同路径：前者在一个湿空气/液体网络中联合求解，后者在集总制冷站的隐式试算中嵌套液体网络。制冷作者角色 `refrigeration.isenthalpic_throttle.v1` 当前不能放入湿空气、普通流体或 `coupled` 项目。组合模块已由 [composites.py](../backend/fn_engine/composites.py) 展开并校验子版本。

自定义压降 `net.pressure_drop`（SDK 0.8.0）仅开放普通单相网络中的被动、无独立储量设备；湿空气／风水、冷库、制冷站与热耦合不接受此新关系。理想测点支持单相与风水路径，组合展开前校验，公开变量映射后计算。详见 [自定义压降](CUSTOM_PRESSURE_DROP.md)及第 4 图。

## 4. 暖通设备、标准机房与理想测点

<!-- diagram: architecture-hvac -->

```mermaid
flowchart TB
  subgraph BUILD["开发时生成设备"]
    SOURCE["hvac_basic.py<br/>基础设备与组合模板定义"]
    GENERATE["generate_hvac_modules.py<br/>生成 / --check 一致性检查"]
    SOURCE --> GENERATE
  end
  PACKS[("modules/ 设备包<br/>manifest.json + module.py")]
  EXAMPLES["hvac_examples.py 示例工厂<br/>开发与运行共用<br/>七个组网项目与控制配置"]
  JSON[("可导入的示例 JSON<br/>examples/hvac-basic/")]
  GENERATE -.->|生成设备包| PACKS
  EXAMPLES -.->|生成脚本 / --check| JSON
  PACKS -->|加载合同与固定源码| EXAMPLES
  subgraph RUNTIME["编译与运行"]
    PROJECT["建模项目 / 暖通示例<br/>设备实例 · 模块快照<br/>controllers / control_scripts / measurements"]
    COMPILE["compiler + composites<br/>校验测点与端口，展开组合<br/>映射公开参数、端口及变量"]
    SOLVE["稳态 solver / 动态 SimulationSession<br/>内置设备 + Python 叶子设备<br/>水力、热力与风水联合求解"]
    PUBLIC["composites.map_frame<br/>将叶子结果映射到公开设备变量"]
    METERS["measurements.apply_measurements<br/>取值 / 两点差 / 体积流量 / 热功率"]
    RESULTS["RunFrame：measurement.*<br/>仪表 · 曲线 · 归档<br/>风侧冻结 CSV / HTML 报告"]
    CONTROL["PID / 控制脚本 Worker<br/>按采样读取已接受变量<br/>写入允许的运行参数"]
    PROJECT --> COMPILE --> SOLVE --> PUBLIC --> METERS --> RESULTS
    PROJECT -.->|动态运行控制配置| CONTROL
    CONTROL -->|参数提案与校验| SOLVE
    RESULTS -->|已接受反馈| CONTROL
  end
  PACKS -->|目录 / 拖入 / 版本绑定| PROJECT
  EXAMPLES -->|示例 API| PROJECT
  JSON -.->|导入| PROJECT
  classDef data fill:#eaf6ef,stroke:#80aa90;
  class PACKS,JSON,RESULTS data;
```

`hvac_basic.py` 是生成来源，设备执行时加载 `modules/` 内的包。异径管等手写设备包同样通过目录加载。空调箱、新风机组、风机盘管、分集水器和定压补水等组合先由 `composites` 展开；生成脚本的 `--check` 保证受管理包与示例文件一致。

理想测点在编译前按公开设备合同检查引用和单位，结果先经过组合变量映射，再计算 `measurement.<id>`。测点不添加阻力、储量或网络方程；输入无效时输出空值和诊断，不补零。当前支持普通单相及风水联算项目，不支持集总制冷站或 `thermal_couplings` 项目。仪表读数保留在 trend 历史，风侧报告使用冻结测点目录和运行帧。

标准机房 `hvac-basic-plant` 的三条物理回路如下，全部走 `fluid` 默认路径：

| 回路 | 连接与耦合 |
| --- | --- |
| 空气 | 新风／回风混合 → 过滤 → 两台水盘管串联 → 风机 → 房间 → 回风／排风 |
| 冷冻水 | 泵 → 冷水机组蒸发侧 → 过滤器／异径管／关断阀 → 分水器 → 两条“平衡阀 + 水盘管”并联支路 → 集水器 → 泵 |
| 冷却水 | 泵 → 冷水机组冷凝侧 → 冷却塔 → 泵 |

机房、末端和空气画布是同一系统的视图分组，不与三条物理回路一一对应。标准机房验收覆盖稳态、调阀、报告及保存重载；房间自动温控和工作／备用泵联锁分别由专用示例验证，不代表该机房示例已包含完整多机群控。

依据：[hvac_basic.py](../backend/fn_engine/hvac_basic.py)、[hvac_examples.py](../backend/fn_engine/hvac_examples.py)、[composites.py](../backend/fn_engine/composites.py)、[measurements.py](../backend/fn_engine/measurements.py)、[solver.py](../backend/fn_engine/solver.py)、[simulation.py](../backend/fn_engine/simulation.py)、[air_variables.py](../backend/fn_engine/air_variables.py)、[标准机房](HVAC_STANDARD_PLANT.md)。

## 5. 后台运行、命令、发布与归档时序

<!-- diagram: sequence-run -->

```mermaid
sequenceDiagram
  autonumber
  actor U as Studio / 外部客户端
  participant A as FastAPI
  participant J as RunManager
  participant C as compiler / sessions
  participant S as 执行域会话
  participant D as 归档线程 / SQLite
  U->>A: POST /api/v1/projects/validate
  A->>C: compile_project(Project)
  C-->>A: 拓扑与合同诊断
  A-->>U: 校验结果
  U->>A: POST /api/v1/runs?background=true
  A->>J: submit(固定 RunRequest)
  J->>D: 保存初始运行记录
  A-->>U: HTTP 202 + run_id
  J->>C: 应用工况，编译并 create_session
  C-->>J: 对应物理域会话
  J->>S: initialize
  S-->>J: t=0 RunFrame
  J->>D: 初始帧与运行状态持久确认
  opt 运行控制或整批参数写入
    U->>A: POST /runs/id/command 或 /variables
    A->>J: 校验命令标识并入队
    J->>D: 回执持久化
    A-->>U: accepted 回执
  end
  loop 每个输出帧
    J->>S: 帧边界应用命令，再 advance
    Note over J,S: 暂停、继续、单步、停止复用同一会话
    S->>S: 控制采样、候选求解、接受一个或多个子步
    S-->>J: RunFrame，含 sequence 与参数修订
    J->>J: 更新最新帧、窗口历史、概览与事件
    J-)D: 普通帧排队，由归档线程合并写入
    U->>A: GET history / events / overview
    A->>J: 读取运行记录
    A-->>U: 增量历史、状态、命令回执
    opt 外部变量订阅
      A-->>U: WS /runs/id/stream 推送最新选定变量
    end
  end
  J->>S: 完成、停止或失败时 close
  S->>S: finalize，回收设备及控制 Worker
  J->>D: 终态及未结算回执持久确认
  Note over J,D: 重启后可读档案；未结束运行标为 interrupted
```

`POST /api/v1/projects/{project_id}/runs` 也会启动后台运行，先读取指定保存修订再归一化。同步 `/runs` 在请求中计算并返回，动态最多 2001 帧。普通帧异步归档，命令及关键状态边界等待落盘；返回计算帧不表示该帧已确认落盘。重启后需新建运行，尚不支持续算。

依据：[api.py](../backend/fn_engine/api.py)、[jobs.py](../backend/fn_engine/jobs.py)、[storage.py](../backend/fn_engine/storage.py)。

## 6. Python 模块候选状态与接受事务时序

<!-- diagram: sequence-module-worker -->

```mermaid
sequenceDiagram
  autonumber
  participant S as 会话 / 求解器
  participant T as 主进程 ModuleStepTransaction
  participant R as runtime / batch RPC
  participant W as Worker 中的用户模块
  S->>R: 创建实例执行器
  R->>W: initialize(ctx)
  loop 同一物理步的数值试算
    S->>R: evaluate(trial_ports, accepted_state, 可选 trial_channels)
    R->>W: evaluate，只读已接受状态
    W-->>R: 通路关系、观察量及诊断
    R-->>S: 组装全网方程所需关系
    S->>S: 求解压力、流量、热状态与残差
  end
  S->>T: 按 step_id 收集所有实例候选
  T->>R: prepare_step(收敛结果, dt)
  R->>W: 在候选副本执行 commit_step
  W-->>R: 候选 state / variables / 修订 / 双哈希
  R-->>T: 模块候选
  S->>S: 构造候选整帧及控制、物理状态
  S->>T: validate 完整性、修订、哈希、JSON 有限值
  alt 接受前校验失败
    S->>T: discard
    T->>R: 丢弃候选
    S->>S: 回滚控制，保留上一已接受状态
  else 接受前校验通过
    S->>T: promote
    T->>T: 主进程更新所有实例 state 与 revision
    S->>S: 接受物理状态、控制状态和账本
    S->>T: synchronize
    T->>R: 同步已接受候选
    R->>W: 更新 Worker 状态镜像
    alt 同步失败
      R-->>S: MODULE_SYNC_FAILED，子步已接受
      S->>S: 保留接受帧，停止运行并清理
    else 同步成功
      S->>S: 继续后续子步或发布输出帧
    end
  end
  S->>R: 结束时 finalize / close
  R->>W: finalize(ctx)，回收进程
```

接受点由主进程掌握，`commit_step` 生成候选不等于立刻接受；`promote()` 内不执行 RPC 或用户代码。接受前失败可丢弃候选，接受后的同步失败则保留该状态并停止。扩展热力、观察和求导回调按模块能力声明执行，图中省略可选调用。声明 `net.pressure_drop` 的普通单相模块还接收当前试算通路流量；流量参与缓存键和方程依赖，`observe` 才读取最终收敛结果。

依据：[module_transactions.py](../backend/fn_engine/module_transactions.py)、[simulation.py](../backend/fn_engine/simulation.py)、[runtime.py](../backend/fn_engine/runtime.py)、[refrigeration/station.py](../backend/fn_engine/refrigeration/station.py)。

## 7. 房间自动温控与风水三回路时序

<!-- diagram: sequence-air-water-control -->

```mermaid
sequenceDiagram
  autonumber
  participant S as SimulationSession
  participant C as 控制脚本 Worker / PID
  participant H as solver / air_transport
  participant X as air_liquid / 设备模型
  participant P as CoolProp 物性
  participant F as 接受状态 / RunFrame
  Note over S,F: 三回路属于 fluid 默认路径；房间有热湿储量
  loop 帧内推进，步长对齐控制采样边界
    S->>S: 保存控制与参数回滚点
    S->>C: 到采样时刻，读取当前已接受变量
    C-->>S: 脚本提案；PID 算出水阀 opening_ratio
    S->>S: 整批校验可写目标与所有权，构造候选参数
    S->>H: _trial(h)，传入房间上一接受状态
    loop 水力与热湿物性外迭代
      H->>P: 按空气/冷冻水/冷却水回路查询物性
      P-->>H: rho / mu / h / 含湿量等
      H->>H: 求各回路压力与流量，空气按干空气连续性
      H->>X: 用同一候选状态计算水盘管与冷水机组
      X-->>H: 盘管冷凝与水侧热量；机组冷量、排热与功率
      H->>X: 房间隐式热湿推进；湿冷却塔换热与水耗
      X-->>H: 候选房间状态、设备量及守恒残差
      H->>H: 更新焓/湿量输运，检查温度/湿量/密度收敛
    end
    H-->>S: 收敛结果或失败诊断
    alt 候选求解或接受前校验失败
      S->>S: 丢弃候选，回滚；可重试错误按条件缩步
    else 候选整帧与模块事务校验通过
      S->>F: 一次接受物理状态、控制提案及累计账本
      Note over S,F: air_ledger 按接受 dt 累计冷凝水、水耗、电能
    end
  end
  S->>F: 映射公开变量与理想测点，发布同一 RunFrame
  Note over S,F: 变量统一驱动画布、控制曲线、归档及冻结报告
```

房间示例用 `Room.state.temperature_k` 反馈到 `WaterValve.opening_ratio`。房间有真实热湿动态，两个水回路无储量；盘管与机组通过 `air_liquid.coupled_device_results` 在同一候选状态中换热。示例脚本在 600 s 控制边界改变负荷或目标，600 s 帧仍是变化前值，630 s 帧包含变化后值。报告读取冻结变量目录和已保存接受帧，不重新求解。

依据：[simulation.py](../backend/fn_engine/simulation.py)、[air_transport.py](../backend/fn_engine/air_transport.py)、[air_liquid.py](../backend/fn_engine/air_liquid.py)、[air_ledger.py](../backend/fn_engine/air_ledger.py)、[房间温控说明](ROOM_TEMPERATURE_CONTROL.md)。

## 8. 制冷站与液体盘管热耦合时序

<!-- diagram: sequence-thermal-coupling -->

```mermaid
sequenceDiagram
  autonumber
  participant S as CoupledStationSession
  participant V as 集总容器 / 制冷设备
  participant L as 液体网络 solver / thermal
  participant W as 液体作者阀门 Worker
  participant T as 接受事务 / 平台账本
  S->>S: 固定控制段参数与已接受模块状态
  loop 隐式状态试算；可选整步/半步误差估计
    S->>V: 由候选 M、U 反求容器温度与压力
    V-->>S: 制冷质量流、能量流及饱和温度
    S->>L: 以当前容器温度求解无储量液体网络
    opt 含液体侧 Python 阀门或局部阻力
      loop 水力残差评估
        L->>W: evaluate，同一已接受 state
        W-->>L: 无附加热流的阀门/阻力关系
      end
    end
    L->>L: 盘管 epsilon-NTU 与液体焓输运
    L-->>S: 液体流量、焓差与各盘管热量
    S->>V: 各盘管热量求和，进入同一容器能量方程
    S->>S: 检查隐式残差、相态、液位与可选时间误差
    S->>T: 按误差接受内部步暂存质量与热量账本
  end
  Note over S,T: 内部账本在段内暂存；整段失败一并回滚
  S->>T: 完整控制段结束，收集模块候选 commit_step
  T->>W: prepare_step(段 dt, 最终收敛通路)
  W-->>T: 候选状态与已声明观察量
  S->>S: 校验整段候选帧
  alt 段接受前失败
    S->>T: 丢弃候选并回滚整段状态与账本
  else 段接受通过
    S->>T: promote 模块状态，再 synchronize Worker
    S->>S: 输出制冷站、液体、作者版本及 coupling 变量
  end
```

最多两条耦合关系，绑定同一饱和容器；同一液体通路不得重复绑定。液体作者设备支持声明事务能力的无储量单通路阀门/局部阻力，不支持泵、主动供热或独立物理储量。平台累计通过质量按实际接受的内部步积分，作者 `commit_step` 按完整控制段执行；整步/半步误差试算不触发模块提交。

依据：[coupling.py](../backend/fn_engine/refrigeration/coupling.py)、[liquid_modules.py](../backend/fn_engine/refrigeration/liquid_modules.py)、[station.py](../backend/fn_engine/refrigeration/station.py)、[使用说明](COUPLED_LIQUID_MODULES.md)。

## 9. 模块开发、发布与项目绑定时序

<!-- diagram: sequence-module-release -->

```mermaid
sequenceDiagram
  autonumber
  actor U as Studio 模块编辑器
  participant A as FastAPI / ModuleStore
  participant B as 校验器 / 真实验证台
  participant W as 独立 Worker
  participant D as 模块版本目录 / 项目
  U->>U: 编辑合同、源码、端口、参数与输出草稿
  U->>A: POST /modules/validate 或 /modules/test
  A->>B: 合同、语法、能力与执行域检查
  B->>W: 加载并试算草稿，执行生命周期
  W-->>B: 关系、状态与诊断
  B-->>U: 经 API 返回结果
  U->>A: POST /modules/versions + expected_latest_version
  A->>A: 持锁检查最新版本，分配新版本
  A->>B: 重新校验，规范源码并计算双哈希
  B->>W: 用有效测试条件再次真实试算
  W-->>B: 结果与输出
  B-->>A: 校验声明输出，生成验证凭据
  alt 冲突、校验失败或试算失败
    A-->>U: 错误诊断；草稿继续保留
  else 验证通过
    A->>D: 临时目录写入 manifest / source / release
    A->>D: 原子重命名为新的 vN 目录
    A-->>U: 新版本、双哈希及验证证据
    U->>D: 插入项目，保存完整定义和 ModulePackageRef
    Note over U,D: 发布新版本不会自动替换已有项目绑定
    U->>A: 显式预览兼容升级，保存项目新修订
    A->>D: 更新项目绑定；可从项目修订回退
  end
```

普通流体、制冷节流及热耦合液体作者模块复用模块平台，验证台按合同选择执行路径。同一项目同一模块 ID 固定一个版本；支持显式兼容升级与修订回退。源码哈希和定义哈希分别校验源码、合同与绑定一致性。

依据：[packages.py](../backend/fn_engine/packages.py)、[bench.py](../backend/fn_engine/bench.py)、[refrigeration/bench.py](../backend/fn_engine/refrigeration/bench.py)、[projects.py](../backend/fn_engine/projects.py)。

## 10. 项目可靠保存与批量工况时序

<!-- diagram: sequence-workspace-batch -->

```mermaid
sequenceDiagram
  autonumber
  actor U as Studio
  participant A as FastAPI
  participant D as SQLite 工作区 / BatchStore
  participant B as BatchService
  participant J as RunManager
  U->>A: 保存项目/工作区 + 预期修订
  A->>D: 事务保存全部画布、跨页连接、草稿及固定绑定
  alt 修订冲突
    D-->>A: 修订冲突
    A-->>U: HTTP 409，保留本地草稿
  else 保存成功
    D-->>A: 新修订
    A-->>U: 确认保存成功
  end
  U->>A: POST /projects/id/batches/preview
  A->>B: prepare(保存修订、工况、观察量)
  B->>D: 读取已保存项目
  B->>B: 归一化并编译各工况，计算快照/预览哈希
  B-->>U: 经 API 返回预览与来源信息
  U->>A: 创建批次 + request_id + preview_hash
  A->>B: 检查幂等标识及预览是否仍有效
  B->>D: 冻结 Project、模块、控制源码与工况
  U->>A: POST /batches/id/start
  A->>B: 启动批次
  loop 按顺序运行各工况
    B->>D: 取得下一项及固定快照
    B->>J: submit(固定修订与 scenario_id)
    J->>J: 编译、运行、接受子步与发布结果
    J->>D: 归档运行，终态捕获批次结果
    B->>D: 确认结果/诊断/曲线后继续下一项
  end
  U->>A: 查看批次、曲线或导出 CSV
  A->>D: 读取独立批次结果
  D-->>A: 比较数据
  A-->>U: 可重复查看的结果
```

恢复或替换项目时，浏览器先保留该项目文档及模块、型号和曲线绑定，不复制整个工作区；跨页连接随项目文档保存。

每批最多 20 个工况、16 个观察变量，固定保存修订、模块与控制快照后顺序运行。批次结果独立于普通运行最近 20 条终态记录的保留策略。预览校验合同与拓扑，不保证数值收敛；数值失败会保存为对应工况的失败结果。工作区支持 ZIP 备份与恢复到新目录；中断运行不能续算，批次可重新运行未完成项。

依据：[batches.py](../backend/fn_engine/batches.py)、[batch_api.py](../backend/fn_engine/batch_api.py)、[batch_store.py](../backend/fn_engine/batch_store.py)、[storage.py](../backend/fn_engine/storage.py)。

## 11. 更新与导出

本文件中的 Mermaid 块是图的维护源。命令提取每个 `diagram` 标记后的图，导出同名 `.mmd`、`.svg` 和 `.png`：

```powershell
cd fluidnet-prototype-engine
node scripts/render_architecture_diagrams.mjs
```

使用项目已有 Playwright 和本机 Edge；首次下载固定版本 Mermaid 11.12.2 到项目 `tmp/architecture-render/`。离线时可传 `--mermaid-js <本地 mermaid.min.js 路径>`。SVG 适合放大与排版，PNG 可直接插入文档。当前共四张架构图、六张时序图；图数由文档标记自动发现，导出文件名保持稳定。

线程、存储与源码导航见 [架构索引](ARCHITECTURE_MAP.md)。本次验证范围为源码调用链核对、Mermaid 实际渲染、图片检查和文档链接检查；不代表重新执行全量物理或浏览器回归。

本轮更新：以 `7424576` 为基线刷新日期与入口；补充多画布计算投影、暖通设备生成与运行链路、组合结果和测点的先后顺序、自定义压降的适用域；统一十张图的导航与导出。
