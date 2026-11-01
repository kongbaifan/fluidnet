# FluidNet 最新架构图与时序图

核对日期：**2026-10-31（北京时间）**。源码基线：`11db224`，引擎声明版本 `0.5.0`。覆盖该提交已实现的风水联算、制冷作者模块、热耦合液体作者设备和房间自动温控；版本号不表示这些能力都属于 10 月 22 日的发布包。

范围为当前开发项目 `fluidnet-prototype-engine/`。归档 Studio、旧便携包和交互原型不在启动链路中。同一进程内的组件按职责拆分，箭头表示调用或数据流。

| 图 | 内容 | 图片与可编辑源码 |
| --- | --- | --- |
| 1 | 组件、进程及存储架构 | [SVG](diagrams/architecture.svg) · [PNG](diagrams/architecture.png) · [Mermaid](diagrams/architecture.mmd) |
| 2 | 编译与五类执行域 | [SVG](diagrams/architecture-execution-domains.svg) · [PNG](diagrams/architecture-execution-domains.png) · [Mermaid](diagrams/architecture-execution-domains.mmd) |
| 3 | 后台运行、命令、发布与归档 | [SVG](diagrams/sequence-run.svg) · [PNG](diagrams/sequence-run.png) · [Mermaid](diagrams/sequence-run.mmd) |
| 4 | Python 模块候选状态与接受事务 | [SVG](diagrams/sequence-module-worker.svg) · [PNG](diagrams/sequence-module-worker.png) · [Mermaid](diagrams/sequence-module-worker.mmd) |
| 5 | 房间温控与空气/冷冻水/冷却水联算 | [SVG](diagrams/sequence-air-water-control.svg) · [PNG](diagrams/sequence-air-water-control.png) · [Mermaid](diagrams/sequence-air-water-control.mmd) |
| 6 | 制冷站与液体盘管热耦合 | [SVG](diagrams/sequence-thermal-coupling.svg) · [PNG](diagrams/sequence-thermal-coupling.png) · [Mermaid](diagrams/sequence-thermal-coupling.mmd) |
| 7 | 模块开发、发布与项目绑定 | [SVG](diagrams/sequence-module-release.svg) · [PNG](diagrams/sequence-module-release.png) · [Mermaid](diagrams/sequence-module-release.mmd) |
| 8 | 项目可靠保存与批量工况 | [SVG](diagrams/sequence-workspace-batch.svg) · [PNG](diagrams/sequence-workspace-batch.png) · [Mermaid](diagrams/sequence-workspace-batch.mmd) |

## 1. 组件、进程及存储架构

<!-- diagram: architecture -->

```mermaid
flowchart TB
  subgraph CLIENT["客户端"]
    UI["浏览器 Studio<br/>engine-client / project-services / 功能脚本<br/>画布、模块、控制、风系统、批量、结果"]
    EXTERNAL["外部调用方<br/>Python / JavaScript / Unity 等<br/>规范 Project JSON"]
  end
  subgraph MAIN["单个 Python 服务进程"]
    API["FastAPI · api / air_api / batch_api<br/>静态前端、鉴权、REST、变量订阅<br/>bridge / models · 归一化与合同校验"]
    AUTHOR["模块平台<br/>目录、模板、设计函数、验证台、不可变版本"]
    BATCH["BatchService<br/>固定修订与快照 · 工况顺序执行"]
    RUN["同步 compute_run / 后台 RunManager<br/>调度线程 + 2 个计算线程"]
    COMPILER["compiler + composites<br/>展开组合、校验拓扑、分派执行域"]
    SESSION["sessions.create_session<br/>五类会话、PID、参数修订、控制采样"]
    NUM["数值计算<br/>水力 / 焓输运 / 湿空气 / 制冷 / 热耦合"]
    PROP["properties + moist_air<br/>CoolProp · 按回路物性<br/>可选外部 REFPROP"]
    TX["module_transactions + runtime / batch<br/>候选校验、主进程接受、管道 RPC"]
    RECORD["RunFrame 与内存运行记录<br/>最新帧、窗口历史、抽稀概览、事件与回执"]
    WRITER["归档写线程 _ArchiveWriter<br/>帧合并落盘 · 关键边界等待确认"]
    API --> AUTHOR
    API --> BATCH --> RUN
    API --> RUN --> COMPILER
    COMPILER --> SESSION --> NUM
    SESSION --> TX
    NUM --> TX
    NUM --> PROP
    SESSION --> RECORD
    RUN --> RECORD --> WRITER
  end
  subgraph CHILD["独立 Python 子进程"]
    MW["设备模块 Worker<br/>initialize / evaluate / commit_step / finalize<br/>及声明的扩展回调"]
    CW["控制脚本 Worker<br/>initialize / step / finalize"]
  end
  subgraph DATA["本机持久化与备份"]
    DB[("SQLite 工作区<br/>项目与修订、运行档案、独立批次结果")]
    PKG[("模块版本目录<br/>manifest / module / design / release / evidence")]
  end
  UI -->|HTTP JSON / 增量轮询| API
  EXTERNAL -->|REST / 变量 stream| API
  TX -->|行式 JSON RPC| MW
  SESSION -->|控制提案 RPC| CW
  AUTHOR -->|保存及发现版本| PKG
  AUTHOR -->|验证台复用| COMPILER
  WRITER --> DB
```

Studio 当前通过 HTTP 增量轮询读取历史和状态；WebSocket 是已有的外部变量订阅接口。API 和 BatchService 还直接访问 SQLite 保存工作区、项目和批次。模块验证台复用编译、会话及 Worker。编译、调度、数值和物性服务都在主服务进程内。CLI 可用 `--headless` 关闭前端，继续提供计算 API。Worker 提供进程与生命周期隔离，尚不是操作系统权限沙箱。

依据：[api.py](../backend/fn_engine/api.py)、[jobs.py](../backend/fn_engine/jobs.py)、[batches.py](../backend/fn_engine/batches.py)、[engine-client.js](../frontend/engine-client.js)。

## 2. 编译与五类执行域

<!-- diagram: architecture-execution-domains -->

```mermaid
flowchart TB
  P["已应用参数 + 固定模块定义 + 工况<br/>规范 Project 合同"] --> C["compile_project<br/>作者角色检查、组合展开与执行域分派"]
  C --> F["fluid 默认路径<br/>compiler + 可选 air_compile"]
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
  TS --> OUT["统一 RunFrame / 控制命令 / 归档与报告"]
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

## 3. 后台运行、命令、发布与归档时序

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

## 4. Python 模块候选状态与接受事务时序

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
    S->>R: evaluate(trial_ports, accepted_state)
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

接受点由主进程掌握，`commit_step` 生成候选不等于立刻接受；`promote()` 内不执行 RPC 或用户代码。接受前失败可丢弃候选，接受后的同步失败则保留该状态并停止。扩展热力、观察和求导回调按模块能力声明执行，图中省略可选调用。

依据：[module_transactions.py](../backend/fn_engine/module_transactions.py)、[simulation.py](../backend/fn_engine/simulation.py)、[runtime.py](../backend/fn_engine/runtime.py)、[refrigeration/station.py](../backend/fn_engine/refrigeration/station.py)。

## 5. 房间自动温控与风水三回路时序

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
  S->>F: 到输出时刻发布同一 RunFrame
  Note over S,F: 变量统一驱动画布、控制曲线、归档及冻结报告
```

房间示例用 `Room.state.temperature_k` 反馈到 `WaterValve.opening_ratio`。房间有真实热湿动态，两个水回路无储量；盘管与机组通过 `air_liquid.coupled_device_results` 在同一候选状态中换热。示例脚本在 600 s 控制边界改变负荷或目标，600 s 帧仍是变化前值，630 s 帧包含变化后值。报告读取冻结变量目录和已保存接受帧，不重新求解。

依据：[simulation.py](../backend/fn_engine/simulation.py)、[air_transport.py](../backend/fn_engine/air_transport.py)、[air_liquid.py](../backend/fn_engine/air_liquid.py)、[air_ledger.py](../backend/fn_engine/air_ledger.py)、[房间温控说明](ROOM_TEMPERATURE_CONTROL.md)。

## 6. 制冷站与液体盘管热耦合时序

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

## 7. 模块开发、发布与项目绑定时序

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

## 8. 项目可靠保存与批量工况时序

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
  A->>D: 事务保存画布、草稿、源码、绑定及控制
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

每批最多 20 个工况、16 个观察变量，固定保存修订、模块与控制快照后顺序运行。批次结果独立于普通运行最近 20 条终态记录的保留策略。预览校验合同与拓扑，不保证数值收敛；数值失败会保存为对应工况的失败结果。工作区支持 ZIP 备份与恢复到新目录；中断运行不能续算，批次可重新运行未完成项。

依据：[batches.py](../backend/fn_engine/batches.py)、[batch_api.py](../backend/fn_engine/batch_api.py)、[batch_store.py](../backend/fn_engine/batch_store.py)、[storage.py](../backend/fn_engine/storage.py)。

## 9. 更新与导出

本文件中的 Mermaid 块是图的维护源。命令提取每个 `diagram` 标记后的图，导出同名 `.mmd`、`.svg` 和 `.png`：

```powershell
cd fluidnet-prototype-engine
node scripts/render_architecture_diagrams.mjs
```

使用项目已有 Playwright 和本机 Edge；首次下载固定版本 Mermaid 11.12.2 到项目 `tmp/architecture-render/`。离线时可传 `--mermaid-js <本地 mermaid.min.js 路径>`。SVG 适合放大与排版，PNG 可直接插入文档。

线程、存储与源码导航见 [架构索引](ARCHITECTURE_MAP.md)。本次验证范围为源码调用链核对、Mermaid 实际渲染、图片检查和文档链接检查；不代表重新执行全量物理或浏览器回归。
