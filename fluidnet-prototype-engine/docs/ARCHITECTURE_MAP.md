# FluidNet 完整架构图

按当前源码核对：版本 **0.4.6**，基线提交 `5c05c79` 加本轮工作区修改，日期 **2026-10-15**。主体为 `fluidnet-prototype-engine/`；根目录 README 已将 `archive/fluidnet-studio-v0.2/` 标为归档项目。

系统采用浏览器前端、单个 Python 服务和用户模块 Worker 子进程的结构。前端与 API 同源，由 FastAPI 同时提供；网络编译、任务调度和数值求解都在服务进程内。下面的箭头分别按图示表示调用、数据流或生命周期，不代表每个方框都是独立服务。

## 1. 系统总览

```mermaid
flowchart TB
  UI["浏览器 Studio<br/>index.html + studio.js<br/>画布、模块、参数、PID、变量与曲线"]
  LOCAL[("浏览器存储<br/>项目 / 草稿 / 保存结果 / 标签页令牌")]
  ADAPTER["engine-client.js + project-services.js<br/>请求、运行控制、历史轮询与单位映射"]
  EXT["外部调用方<br/>三维界面 / 数字孪生 / 网关"]
  API["api.py + auth.py · FastAPI<br/>REST / WebSocket / 静态页面<br/>令牌权限与 CORS"]
  CONTRACT["输入与契约<br/>bridge.py 原型归一化<br/>models.py 严格 Pydantic 模型"]
  MODULES["模块平台<br/>catalog.py / packages.py<br/>module_validation.py / bench.py"]
  DISK[("模块版本目录<br/>manifest.json / module.py / release.json")]
  RUN["运行编排<br/>同步 compute_run / 后台 RunManager"]
  COMPILE["compiler.py<br/>校验、压力节点、支路、工质回路"]
  EXEC["执行层<br/>稳态 solve_steady / 动态 SimulationSession<br/>水箱、管道热容、PID、参数修订"]
  SOLVE["solver.py + thermal.py<br/>水力、焓输运、换热与能量校核"]
  RPC["runtime.py + batch.py<br/>Worker 生命周期与批量 RPC"]
  WORKER["独立 Worker 子进程<br/>worker.py → 用户 module.py<br/>四阶段生命周期与 ctx SDK"]
  PROP["properties.py + CoolProp<br/>按回路物性、缓存与线程隔离<br/>可选 REFPROP 外部安装"]
  RESULTS[("内存与 SQLite 运行记录<br/>最新帧 / 历史 / 全程曲线 / 事件 / 回执")]

  WORKSPACE[("storage.py · SQLite<br/>完整工作区与最近 5 修订")]
  CONTROL["control.py · 独立 Worker<br/>initialize / step / finalize"]
  API <--> WORKSPACE
  EXEC <--> CONTROL
  LOCAL <--> UI
  UI <--> ADAPTER
  ADAPTER <-->|HTTP JSON| API
  EXT <-->|REST / WebSocket| API
  API --> CONTRACT --> RUN
  API --> MODULES --> DISK
  RUN --> COMPILE --> EXEC
  EXEC --> SOLVE
  EXEC --> RESULTS
  SOLVE <--> RPC
  RPC <-->|行式 JSON 管道| WORKER
  SOLVE --> PROP
```

图中 FastAPI、模块平台、编译器、运行编排、求解器和运行记录都位于主服务进程内。结果由 API 提供给访问端；模块独立验证复用编译器、求解器和 Worker。令牌哈希另存于 `.runtime/tokens.json`。

`properties.py` 同时被主服务和 Worker 导入；它不是单独的网络服务。内置设备直接进入求解器，自定义 Python 模块通过 `ctx.net.*` 返回关系，再由同一个全网求解器计算压力与流量。

## 2. 启动、进程与并发

```mermaid
flowchart LR
  START["start.ps1<br/>准备 Python 环境"] --> CLI["python -m fn_engine serve<br/>__main__.py → cli.main"]
  CLI --> APP["uvicorn + create_app<br/>默认 127.0.0.1:8798"]
  APP --> STATIC["StaticFiles 挂载 frontend/<br/>project-services.js → engine-client.js<br/>studio.js 随后创建客户端"]
  APP --> HTTP["FastAPI 请求处理<br/>同步求解 / 模块校验与试算"]
  APP --> SCHED["RunManager<br/>1 个调度线程"]
  SCHED --> POOL["2 个计算线程<br/>每次推进一个运行的一帧"]
  POOL --> SESSIONS["动态 SimulationSession<br/>最多 20 个活动后台运行<br/>暂停会话不占计算线程"]
  SESSIONS --> RUNNERS["Python 模块执行器"]
  HTTP --> RUNNERS
  RUNNERS --> SINGLE["单实例或关闭批处理<br/>每实例一个 Worker"]
  RUNNERS --> BATCH["多实例且启用批处理<br/>按 module_parallelism 分片"]
  BATCH --> SHARDS["每片一个 Worker<br/>片内顺序执行、片间可并行<br/>实例状态各自保存"]
```

- `module_parallelism` 默认 1，可设置 1–16；`batch_modules` 默认开启。两个后台计算线程与模块 Worker 并行度是两层不同的配置。
- Worker 是独立 Python 进程，通过管道 RPC 通信，默认单次响应超时 10 秒。正常结束调用 `finalize`，失败或超时关闭进程。
- 服务默认本机访问。对外监听时强制令牌认证；跨域来源显式配置。TLS 可以由外部反向代理提供。

依据：[cli.py](../backend/fn_engine/cli.py)、[api.py](../backend/fn_engine/api.py)、[jobs.py](../backend/fn_engine/jobs.py)、[runtime.py](../backend/fn_engine/runtime.py)、[batch.py](../backend/fn_engine/batch.py)。

## 3. 网络编译与数值求解

```mermaid
flowchart TB
  RAW["原型活动项目<br/>已应用 params + 项目固定模块快照"] --> BRIDGE["bridge.normalize_prototype_export<br/>字段与单位转换"]
  DIRECT["外部规范 Project JSON"] --> PROJECT
  BRIDGE --> PROJECT["Pydantic Project<br/>实例、连接、模块、工况、PID、工质、求解选项"]
  PROJECT --> SCENARIO["apply_scenario<br/>在项目副本上应用工况覆盖"]
  SCENARIO --> VALIDATE["compile_project<br/>参数、端口、通路、模型与版本双哈希校验"]
  VALIDATE --> TOPO["拓扑编译<br/>连接端口并查集合并 → 压力节点<br/>内部通路 → 计算支路"]
  TOPO --> FLUID["按连接和启用通路划分工质回路<br/>分配物性服务、验证温度和相态<br/>校验各水力子网络压力参考"]
  FLUID --> NET["CompiledNetwork<br/>节点 / 支路 / 参数 / 边界 / 水箱 / 工质映射"]
  NET --> MODE{运行模式}
  MODE -->|稳态| STEADY["solve_steady"]
  MODE -->|动态| SESSION["SimulationSession<br/>准稳态序列；含水箱或管道热容时用隐式 Euler"]
  STEADY --> NETWORK["solve_network<br/>使用上一成功解热启动"]
  SESSION --> NETWORK

  subgraph NUMERICS[单次网络求解]
    HYD["水力层 · solver.py<br/>支路压差关系 + 节点质量守恒<br/>水箱状态约束 / 零流量约束<br/>SciPy least_squares；dense 或 sparse"]
    EVAL["Python evaluate<br/>试算端口与只读状态 → NetworkRelation"]
    THERMAL["热力层 · thermal.py<br/>迎风传焓、节点混合、泵轴功、散热<br/>换热器 ε–NTU、水箱与管道储热<br/>稀疏焓方程与非线性迭代"]
    CHECK["收敛与物理校核<br/>压差残差、质量残差、能量残差、相态"]
    HYD <-->|每次数值评估| EVAL
    HYD -->|压力、流量、关系| THERMAL
    THERMAL -.->|仅 node 耦合：更新支路密度和黏度| HYD
    THERMAL --> CHECK
  end

  NETWORK --> HYD
  HYD -->|thermal=false| CHECK
  CHECK --> FRAME["RunFrame<br/>变量 + metrics + diagnostics<br/>time_s + sequence + parameter_revision"]
```

默认 `property_coupling='reference'`：每个回路采用固定参考密度、黏度完成水力求解，再计算热力。`node` 模式在外循环中把热力结果更新为支路物性后重新求解；物性在单轮水力迭代内冻结。默认水力算法是 `dense`，大网络可选择 `sparse`。

工质回路与水力连通分量不同：工质回路按启用的内部通路划分，阀门关闭不会把工质回路分开；压力参考检查则考虑阀门是否关闭。换热器两侧可以使用不同工质，只传热、不混合。

物性经 `CoolProp.AbstractState` 查询；普通后端按线程隔离状态并缓存。REFPROP 调用受锁保护，每种工质首次使用前用临时子进程探测其文件兼容性。

依据：[bridge.py](../backend/fn_engine/bridge.py)、[compiler.py](../backend/fn_engine/compiler.py)、[solver.py](../backend/fn_engine/solver.py)、[thermal.py](../backend/fn_engine/thermal.py)、[properties.py](../backend/fn_engine/properties.py)。

## 4. 动态运行与控制时序

```mermaid
sequenceDiagram
  participant C as Studio 或外部客户端
  participant A as FastAPI
  participant J as RunManager
  participant S as SimulationSession
  participant N as 水力与热力求解器
  participant W as Python Worker

  C->>A: POST /runs?background=true + RunRequest
  A->>J: submit：复制请求、创建运行记录
  A-->>C: 202 + run_id
  J->>J: 应用工况、编译网络
  J->>S: 创建会话并 initialize
  S->>W: initialize：参数、工质、实例状态
  S->>N: 初始网络求解
  N->>W: evaluate（可多次）
  W-->>N: NetworkRelation、变量、诊断
  N-->>S: 初始收敛解
  S-->>J: 初始化 PID，发布 t=0 帧

  opt 运行控制或写参数
    C->>A: command / variables
    A->>J: 入队，按 command_id 去重
    A-->>C: accepted 回执
  end

  loop 每个发布帧
    J->>S: 帧边界应用命令；advance
    Note over J,S: 命令回执更新为 applied / rejected
    loop 帧内子步，必要时对齐 PID 采样时刻
      S->>S: PID 采样；写入 runtime 参数；构造当前网络
      S->>N: 热启动求解；状态设备用隐式 Euler
      loop 数值迭代
        N->>W: evaluate：trial_ports + readonly_state
        W-->>N: 关系与输出；不提交实例状态
      end
      alt 可重试的状态步失败
        N-->>S: 未收敛或物性错误
        S->>S: 子步减半后重试
      else 子步成功
        N-->>S: 收敛压力、流量、焓与状态
        S->>W: commit_step：收敛结果 + 实际 dt
        W-->>S: 已提交状态与输出
        S->>S: 接受子步、更新水箱及管段状态
      end
    end
    S-->>J: RunFrame
    J->>J: 发布最新帧、窗口历史、抽稀全程曲线
    C->>A: Studio 增量读取 history / events / overview
    A->>J: 读取内存记录
    A-->>C: 新帧、事件、命令回执
    opt 外部客户端订阅
      A-->>C: WebSocket 推送最新帧的所选变量
    end
  end

  J->>S: 完成、停止、异常或服务关闭
  S->>W: finalize / close
  J->>J: 写入终态；保留已接受历史
```

- 一帧可包含多个成功子步；`commit_step` 对每个成功子步调用一次，失败试算不提交。单步、暂停和恢复复用同一会话与模块状态。
- 同步动态接口同样使用 `SimulationSession`，但在请求内一次执行完毕；最多返回 2001 帧。持续运行必须使用后台接口。
- 后台 `fast` 尽快推进，`realtime` 按 `dt_s / speed_ratio` 调度。暂停释放计算线程，仍保留会话和 Worker。
- `/variables` 批量写入在同一帧边界统一校验和应用，成功时生成一个参数修订号；可写目标为 runtime 参数和 PID 设定。
- 水箱排空或满箱会定位事件时刻、停止运行并保留已接受帧。运行中被阀门隔离的被动管段可保压，含泵或 Python 模块的隔离段会报错。
- Studio 当前使用 HTTP 轮询更新运行界面。WebSocket 已实现，面向后台运行的变量订阅；慢客户端只取得最新帧，可通过 `sequence` 识别跳帧。

依据：[jobs.py](../backend/fn_engine/jobs.py)、[simulation.py](../backend/fn_engine/simulation.py)、[controllers.py](../backend/fn_engine/controllers.py)、[engine-client.js](../frontend/engine-client.js)、[api.py](../backend/fn_engine/api.py)。

## 5. 自定义模块开发、发布与绑定

```mermaid
flowchart TB
  EDIT["Studio 模块编辑器<br/>源码、参数、端口、内部通路、输出变量"] --> DRAFT["浏览器草稿"]
  DRAFT --> VALIDATE["POST /modules/validate<br/>Pydantic + Python 语法 + Worker 入口检查"]
  DRAFT --> TEST["POST /modules/test<br/>bench.run_module_test"]
  TEST --> BOUNDARY["每条启用通路配一对压力边界<br/>多通路在同一个网络中求解"]
  BOUNDARY --> LIFE["复用 compiler + solver + Worker<br/>initialize → evaluate → commit_step → finalize"]
  LIFE --> REPORT["结果帧、模块关系、状态、哈希与诊断"]

  DRAFT --> SAVE["POST /modules/versions<br/>ModuleStore.save"]
  SAVE --> VERSION["检查 expected_latest_version<br/>新版本递增，旧版本不可覆盖"]
  VERSION --> RECHECK["重新校验当前提交内容"]
  RECHECK --> HASH["生成源码哈希与定义哈希"]
  HASH --> TRIAL["独立试算并核对声明输出"]
  TRIAL --> ATOMIC["临时目录写入后原子重命名"]
  ATOMIC --> DISK[(".runtime/module-packages/module-id/vN/<br/>manifest.json + module.py + release.json")]
  SEED[("modules/<br/>只读示例包")] --> CATALOG["模块目录与版本列表"]
  DISK --> CATALOG
  CATALOG --> INSERT["拖入项目 / 创建管网算例"]
  INSERT --> PIN["项目完整 ModuleDefinition 快照<br/>实例绑定 ModulePackageRef<br/>模块 ID + 版本 + 双哈希"]
  PIN --> RUN["项目运行<br/>校验绑定后执行固定版本"]
```

编辑草稿用于独立试算；项目运行使用插入时固定的保存版本。发布新版不会改变已有项目。同一项目内同一模块 ID 固定一个版本，目前没有项目内版本迁移或同 ID 多版本混用。

`ctx.net` 支持声明管道、阀门、泵和指定质量流量的压缩机关系；`ctx.fluid` / `ctx.fluid_at(port)` 查询项目或端口回路物性。Worker 负责执行模块代码与保存实例状态，全网方程仍由主服务求解器组装和求解。独立进程提供生命周期隔离，并非操作系统权限沙箱。

依据：[module_validation.py](../backend/fn_engine/module_validation.py)、[bench.py](../backend/fn_engine/bench.py)、[packages.py](../backend/fn_engine/packages.py)、[runtime.py](../backend/fn_engine/runtime.py)、[worker.py](../backend/fn_engine/worker.py)。

## 6. 数据合同与持久化

```mermaid
flowchart LR
  MODULE["ModuleDefinition<br/>参数、端口、通路、变量、源码与版本"] --> PROJECT["Project<br/>模块快照、实例、连接、工况、PID、回路工质"]
  REF["ModulePackageRef<br/>模块 ID、版本、源码哈希、定义哈希"] --> INSTANCE["ModuleInstance<br/>参数、草稿、型号、库值与画布位置"]
  INSTANCE --> PROJECT
  PROJECT --> REQUEST["RunRequest<br/>模式、时长、步长、节奏、历史配置"]
  REQUEST --> RECORD["运行记录（内存与 SQLite）<br/>请求快照、状态、最新帧、历史与事件"]
  FRAME["RunFrame<br/>variables / diagnostics / metrics<br/>time_s / sequence / parameter_revision"] --> RECORD
  MODEL["models.py<br/>严格 Pydantic 模型"] -.-> MODULE
  MODEL -.-> PROJECT
  MODEL -.-> REQUEST
  MODEL -.-> FRAME
  MODEL --> GEN["scripts/generate_contracts.py"]
  GEN --> CONTRACTS["contracts/<br/>JSON Schema / OpenAPI / 参考项目与结果"]
```

| 数据 | 所在位置 | 生命周期与用途 |
| --- | --- | --- |
| 项目、模块编辑草稿、已保存的运行结果 | 浏览器 `localStorage` 草稿备份与服务端工作区，主键 `fluidnet-prototype-engine-v1` | 保存/刷新恢复；原型 JSON 导入导出；全程抽稀数据不写入该存储 |
| 界面偏好 | 浏览器 `localStorage`，键后缀 `-ui` | 主题、页签等 |
| 浏览器访问令牌 | `sessionStorage` | 当前标签页使用，由请求头携带 |
| 内置 Python 示例模块 | `modules/programmable_valve/` | 随源码提供的种子版本，不被发布操作覆盖 |
| 用户发布模块 | 项目 `.runtime/module-packages/` | 可用 `FLUIDNET_MODULE_STORE` 指定目录；服务重启后保留 |
| 令牌记录 | 项目 `.runtime/tokens.json` | 可用 `FLUIDNET_TOKEN_FILE` 指定；只保存令牌哈希及元数据 |
| 同步运行记录 | `api.py` 内的 `OrderedDict` | 内存中保留最近 20 条；启用 data_root 时归档到 SQLite，重启可读 |
| 后台运行记录与会话 | `RunManager.jobs` / `SimulationSession` | 最多 20 个活动运行，另保留最近 20 个终态记录；重启后可查看归档，未结束运行标为 interrupted |
| 后台历史 | 运行记录中的滚动窗口 | 默认 2001 帧，可配 10–20001；会话自身只保留最近 8 帧 |
| 全程曲线 | 内存与 SQLite overview | 按 2000 点阈值加倍抽稀步距；查询时补入末帧 |
| 事件与已结算命令回执 | 后台运行记录 | 各受 1000 条限制，避免长时间运行无限增长 |
| 接口合同和参考算例 | `contracts/` | 从可执行模型及接口生成的开发资料，不作为运行数据库 |
| REFPROP DLL 与工质文件 | 外部安装目录或 `FLUIDNET_REFPROP_PATH` | 通过 CoolProp 的 REFPROP 后端调用；根目录同名资料不代表已自动接入 |

变量使用稳定的实例 ID 路径，例如 `V1.ch0.mass_flow_kg_s`、`T1.state.level_m`、`V1.param.opening_ratio`、`controller.pid1.output`。显示单位转换由前端适配器完成，计算合同使用规范单位。

## 7. 代码导航与当前边界

| 层次 | 主要源码 |
| --- | --- |
| 页面、画布、模块编辑、曲线 | [frontend/index.html](../frontend/index.html)、[studio.js](../frontend/studio.js) |
| API 适配、版本绑定、真实数据映射 | [engine-client.js](../frontend/engine-client.js) |
| 启动和接入 | [cli.py](../backend/fn_engine/cli.py)、[api.py](../backend/fn_engine/api.py)、[auth.py](../backend/fn_engine/auth.py) |
| 契约、目录、归一化、编译 | [models.py](../backend/fn_engine/models.py)、[catalog.py](../backend/fn_engine/catalog.py)、[bridge.py](../backend/fn_engine/bridge.py)、[compiler.py](../backend/fn_engine/compiler.py) |
| 任务、动态状态和控制 | [jobs.py](../backend/fn_engine/jobs.py)、[simulation.py](../backend/fn_engine/simulation.py)、[controllers.py](../backend/fn_engine/controllers.py) |
| 数值算法与物性 | [solver.py](../backend/fn_engine/solver.py)、[thermal.py](../backend/fn_engine/thermal.py)、[properties.py](../backend/fn_engine/properties.py) |
| 模块执行与版本 | [runtime.py](../backend/fn_engine/runtime.py)、[worker.py](../backend/fn_engine/worker.py)、[batch.py](../backend/fn_engine/batch.py)、[packages.py](../backend/fn_engine/packages.py) |
| 模块验证 | [module_validation.py](../backend/fn_engine/module_validation.py)、[bench.py](../backend/fn_engine/bench.py) |
| 示例、合同生成、性能评估 | [examples.py](../backend/fn_engine/examples.py)、[generate_contracts.py](../scripts/generate_contracts.py)、[benchmark_scaling.py](../scripts/benchmark_scaling.py) |
| 回归与端到端验证 | `tests/test_*.py` 覆盖物理、状态、接口、版本、工质和并发；`tests/browser-*.mjs` 使用 Playwright 验证页面工作流 |

当前可计算的内置模型包括压力源、连接节点、泵、阀门、管道、双侧换热器和开式水箱，以及版本化 Python 模块与项目级 PID。动态部分包含水箱质量/焓和分段管道热容；不计算水锤、完整可压缩流动或管网内两相流。模块物性查询可使用显式两相状态接口。

Python 项目控制脚本已接通采样执行和独立 Worker；串口演示、原型自定义变量等部分入口仍为编辑或预览。未支持的模型进入求解器时会被拒绝；组合设备只有已经展开为普通实例和连接的项目可计算，递归组合定义展开尚未实现。

项目新增本地 SQLite 工作区与运行归档，没有外部消息队列或分布式调度依赖。Node/Playwright 用于前端检查与浏览器测试，不是线上前端服务。归档 Studio、旧版 `dist/`、`output/` 原型和算法参考资料不属于当前引擎的启动链路。

本图以源码为准：旧文档中“WebSocket 待实现”“一个项目只用一种流体”和前端脚本加载顺序等描述与当前实现有差异，已在这里按实际行为呈现。


本轮补充：`storage.py` 持久化完整工作区（最近 5 修订）、请求/最新帧/事件、最近窗口和全程抽稀；`control.py` 由 `worker.py` 调度 initialize/step/finalize，SimulationSession 在下一接受子步提交控制状态。前端新增 project-services.js，提供工作区版本冲突检测、控制预览和运行归档查看。具体合同见 API.md 与 DATA_CONTRACT.md。
