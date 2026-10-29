# FluidNet 架构图与时序图

日期：2026-10-27。基线：`codex/development-consistency` 分支提交 `2bf8391`（含热耦合单/双盘管、无界面运行、电加热器与多支路饱和容器）。

本文按当前源码重画**组件架构**与**关键时序**，面向「Unity 组态 → 平台计算」的教学使用方式。历史版本的整体架构（v0.4.6，2026-10-15）仍见 [ARCHITECTURE_MAP](ARCHITECTURE_MAP.md)；两者冲突时以本文与源码为准。图中箭头表示调用、数据流或生命周期，不代表每个方框都是独立服务。

## 1. 组件架构图

```mermaid
flowchart TB
  subgraph CLIENT["客户端层"]
    UNITY["Unity 组态界面<br/>学生搭建拓扑<br/>导出规范 Project JSON"]
    STUDIO["浏览器 Studio<br/>画布 / 模块 / PID / 曲线"]
    SDK["外部客户端示例<br/>Python / JavaScript"]
  end

  subgraph EDGE["接入层（同源，默认 127.0.0.1:8798）"]
    API["api.py · FastAPI<br/>REST + WebSocket<br/>studio / headless 两种模式"]
    AUTH["auth.py<br/>read / control 令牌"]
    BRIDGE["bridge.py<br/>原型归一化、单位转换"]
    MODELS["models.py<br/>严格 Pydantic 合同"]
  end

  subgraph ORCH["编排层"]
    RUN["RunManager<br/>1 个调度线程 + 2 个计算线程<br/>最多 20 个活动后台运行"]
    SYNC["同步运行入口<br/>POST /api/v1/runs"]
    ARCHIVE["运行归档<br/>最近 2001 帧 + 全程抽稀"]
  end

  subgraph COMPILE["编译层 · compiler.py"]
    DISPATCH{"执行域分派"}
    C_FLUID["单相流体网络<br/>压力节点 / 支路 / 工质回路"]
    C_COUPLED["耦合项目<br/>refrigeration/coupling.py"]
    C_STORE["冷库 A<br/>refrigeration/compile.py"]
    C_STATION["集总制冷站 B<br/>refrigeration/station.py"]
  end

  subgraph NUM["数值层"]
    HYD["solver.py · 水力<br/>SciPy least_squares<br/>dense / sparse / auto（S0–S2）<br/>解析 Jacobian（J0–J3）· B0 真实调用计数"]
    PLAN["hydraulic_plan.py<br/>受限串联支路压缩 C0–C3<br/>（默认关闭）"]
    PART["partition.py<br/>依赖安全分块 D0–D2<br/>（默认关闭）"]
    THM["thermal.py · 热力<br/>迎风焓输运 / 隐式 Euler / ε–NTU<br/>Picard 加速 L0–L2（默认关闭）<br/>能量残差校核"]
    STEP["timestep.py<br/>Euler 时间误差接受 A0–A4<br/>（默认关闭）"]
    TRAP["trapped.py<br/>困液定容原型 I0–I4<br/>（限定范围）"]
    CV["check_valve.py<br/>止回阀 V0–V2<br/>参考曲线 / 迟滞 / 互补残差"]
    MODNUM["module_phases.py / module_performance.py<br/>模块热力回调 · 混合求导<br/>有界纯函数缓存"]
    PROP["properties.py<br/>CoolProp HEOS / IF97 / INCOMP<br/>可选 REFPROP<br/>按回路服务 · 缓存 · 线程隔离"]
  end

  subgraph EXEC["执行域会话"]
    S_NET["单相网络会话<br/>水箱 / 管段热容 / PID / 参数修订"]
    S_STORE["冷库 A 会话<br/>库房 + 货物热节点、机组状态机"]
    S_STATION["制冷站 B 会话<br/>容器 (M,U) 隐式推进、五闭环控制"]
    S_COUPLED["双盘管联算会话<br/>容器 ↔ 二次液体网络隐式交叉求解"]
  end

  subgraph MODULE["可编程运行时"]
    RT["runtime.py / batch.py<br/>行式 JSON 管道 RPC"]
    W_MOD["用户设备模块 Worker<br/>initialize → evaluate → commit_step → finalize"]
    W_CTRL["控制脚本 Worker<br/>initialize → step → finalize"]
  end

  subgraph STORE["存储"]
    WS[("storage.py · SQLite<br/>工作区 / 项目 / 最近 5 修订")]
    MODDIR[("模块版本目录<br/>manifest.json / module.py / 双哈希")]
  end

  UNITY -->|"REST：validate / runs / variables"| API
  STUDIO -->|"REST + WS"| API
  SDK -->|"REST + WS"| API
  API --- AUTH
  API --> BRIDGE --> MODELS
  API --> SYNC
  API --> RUN
  RUN --> MODELS
  RUN --> DISPATCH
  SYNC --> DISPATCH
  DISPATCH --> C_FLUID
  DISPATCH --> C_COUPLED
  DISPATCH --> C_STORE
  DISPATCH --> C_STATION
  C_FLUID --> S_NET
  C_STORE --> S_STORE
  C_STATION --> S_STATION
  C_COUPLED --> S_COUPLED
  S_NET --> HYD
  S_NET --> THM
  S_STATION --> THM
  S_COUPLED --> THM
  S_COUPLED --> HYD
  HYD --> PLAN
  HYD --> PART
  HYD --> PROP
  THM --> PROP
  HYD --> MODNUM
  THM --> MODNUM
  S_NET --> STEP
  S_STATION --> STEP
  S_COUPLED --> STEP
  S_NET --> TRAP
  HYD -.->|"独立参考路径"| CV
  HYD --> RT
  THM --> RT
  RT --> W_MOD
  RT --> W_CTRL
  RUN --> ARCHIVE
  API --> WS
  API --> MODDIR
  ARCHIVE --> WS
```

要点：

- **一个 Python 服务进程**承担 API、编译、调度与求解；Python 模块与控制脚本在独立 Worker 子进程中执行。
- **执行域由编译器分派**：项目含 `thermal_couplings` → 联算；含 `refrigerant` 端口 → 集总制冷站；含 `thermal` 端口 → 冷库 A；其余为单相流体网络。
- 教学场景中 Unity 只需实现三个 REST 调用（校验、启动、读结果/订阅），算法细节全部在平台内。
- 物性、模块版本与运行归档都在平台侧，客户端不持有求解状态。

### 1.1 数值层细目

| 模块 | 证据系列 | 作用 | 默认 |
| --- | --- | --- | --- |
| `solver.py` | B0、S0–S2、J0–J3 | `least_squares` 水力求解、auto 稀疏选择、纯内置解析 Jacobian、真实残差/Jacobian/RPC 计数 | 解析 Jacobian 开；新建项目 `auto`，旧项目 `dense` |
| `hydraulic_plan.py` | C0–C3 | 受限串联支路压缩与原变量回算 | 关闭（`series_compression=False`） |
| `partition.py` | D0–D2 | 依赖安全的水力分块求解 | 关闭（`hydraulic_blocks=False`） |
| `thermal.py` | L0–L2 | 节点焓输运、隐式 Euler 储热、ε–NTU、能量残差校核、Picard 阻尼加速 | 加速 `none` |
| `timestep.py` | A0–A4 | 整步/两个半步试算、误差归一化与接受/拒绝 | 关闭（`time_step` 未启用） |
| `trapped.py` | I0–I4 | 单容积刚性封闭液腔原型（HEOS 纯水单相） | 仅显式 `closed_volume`，非通用隔离段 |
| `check_valve.py` | V0–V2 | 止回阀解析曲线、开关判据、迟滞状态机与互补残差（独立参考路径） | 求解器不直接调用 |
| `module_phases.py` / `module_performance.py` | 模块系统 | 模块热力回调、混合求导、有界纯函数缓存与端口读取追踪 | 随模块启停 |
| `properties.py` | — | CoolProp HEOS/IF97/INCOMP、可选 REFPROP、按回路物性服务、缓存与线程隔离 | — |

Worker 冷启动优化（W0–W2）属于可编程运行时的启动路径，不在本层；证据与默认开关见 [数值专项证据索引](numerics/README.md)。

![组件架构图（PNG）](diagrams/architecture.png)

## 2. 时序图 A：一次运行（Unity 拓扑 → 平台结果）

```mermaid
sequenceDiagram
  autonumber
  participant U as Unity 客户端
  participant A as FastAPI (api.py)
  participant C as 编译器 (compiler.py)
  participant R as RunManager
  participant S as 执行域会话
  participant N as 水力 + 热力求解
  participant P as 物性服务
  participant D as 存储 / 归档

  U->>A: POST /api/v1/projects/validate（完整拓扑）
  A->>C: compile_project(Project)
  C-->>A: 回路 / 诊断 / 错误码
  A-->>U: 校验结果（可定位到设备与端口）

  U->>A: POST /api/v1/runs?background=true（或 /projects/{id}/runs）
  A->>A: 严格合同校验 + 令牌鉴权
  A->>R: submit(RunRequest)
  R-->>A: run_id（HTTP 202）
  A-->>U: run_id

  R->>C: 编译（固定项目修订、模块快照与工质）
  C->>S: 创建会话（按执行域分派）
  R->>D: 记录运行元数据与请求快照

  loop 每一帧（稳态求解或动态推进）
    S->>N: 水力求解（流量 / 压力）
    N->>P: 按回路查询物性
    P-->>N: 密度 / 黏度 / 焓 / 温度
    S->>N: 热力求解（焓输运、换热、能量残差）
    N-->>S: 帧变量 / 指标 / 诊断
    S->>D: 发布帧（内存窗口 + 归档抽稀）
    U->>A: GET /runs/{id}/variables 或 WS /events
    A-->>U: 当前帧 / 结束状态
  end

  U->>A: POST /runs/{id}/command（pause / resume / step / set / stop）
  A->>R: 命令在当前帧结束后生效
  R->>S: 应用到同一 run_id
  S-->>D: 终态记录（已接受历史保留）
```

![一次运行时序（PNG）](diagrams/sequence-run.png)

## 3. 时序图 B：双盘管热耦合隐式联算

```mermaid
sequenceDiagram
  autonumber
  participant S as CoupledStationSession
  participant V as 饱和制冷剂容器 LP1
  participant L as 二次侧无储量液体网络
  participant C1 as 盘管 HX1
  participant C2 as 盘管 HX2

  Note over S: 每个隐式步 / Newton 迭代内重复，未收敛的试算不提交
  S->>V: 以试算 (M, U) 反求饱和温度与压力
  S->>L: 用当前饱和温度求解二次侧网络
  L-->>S: 各盘管流量、上游温度、出口焓
  S->>C1: ε–NTU 计算换热量与有效度
  S->>C2: ε–NTU 计算换热量与有效度
  C1-->>S: heat_w / 出液温度 / 方程残差
  C2-->>S: heat_w / 出液温度 / 方程残差
  S->>V: 两盘管热量以相反符号写入同一容器能量方程（求和）
  S->>S: 检查质量 / 能量残差与容器液位适用区
  S->>S: 接受子步：提交状态、累计 heat_energy_j 与能量账
  Note over S: 输出 coupling.HX1.* / coupling.HX2.* 与 metrics.coupling_heat_w（两盘管之和）
```

边界：最多两条耦合，须绑定同一个饱和容器，同一液体通路不能重复绑定；液体侧无储热、无 Python 设备模块；两条以上的盘管与不同容器尚未支持。

![双盘管联算时序（PNG）](diagrams/sequence-thermal-coupling.png)

## 4. 时序图 C：Python 模块与控制脚本的生命周期

```mermaid
sequenceDiagram
  autonumber
  participant S as 求解器 / 会话
  participant R as runtime.py (RPC)
  participant W as Worker 子进程
  participant M as 用户 module.py

  S->>R: 启动（单实例或按并行度分片）
  R->>W: 行式 JSON RPC
  W->>M: initialize(ctx)
  loop 同一子步内的多次迭代
    S->>R: evaluate(端口状态)
    R->>M: evaluate(ctx)
    M-->>S: 通路关系（阻力 / 压升 / 强制流量）
  end
  alt 子步被接受
    S->>R: commit_step
    R->>M: commit_step(ctx)
  else 子步失败或超时
    S->>R: 丢弃本次结果（不提交状态）
    R->>W: 关闭进程并记录诊断
  end
  S->>R: 结束
  R->>M: finalize(ctx)
  W-->>R: 进程退出，Worker 回收
```

控制脚本使用同一 Worker 机制，但按仿真采样周期执行 `initialize / step / finalize`，写入先暂存、整批校验后再应用到下一子步。

![模块 Worker 时序（PNG）](diagrams/sequence-module-worker.png)

## 5. 接口与执行域对照

| 执行域 | 编译器入口 | 会话 | 教学用途 |
| --- | --- | --- | --- |
| 单相流体网络 | `compile_project` | 网络会话（水箱/管段热容/PID） | 泵阀管网、换热器、加热器、水系统 |
| 冷库 A（`cold_store`） | `refrigeration/compile.py` | 库房 + 货物热节点会话 | −18 °C 单库房、机组启停与融霜 |
| 集总制冷站 B（`refrigerant`） | `refrigeration/station.py` | 容器 (M,U) 隐式推进会 | NH₃/CO₂ 制冷站、多支路容器、冷风机 |
| 双盘管联算 | `refrigeration/coupling.py` | 容器 ↔ 二次液体网络交叉求解 | 制冷站与水/乙二醇回路换热 |

客户端可用的主要端点：`POST /api/v1/projects/validate`、`POST /api/v1/runs`、`POST /api/v1/projects/{id}/runs`、`GET /api/v1/runs/{id}/variables`、`GET /api/v1/runs/{id}/history`、`WS /api/v1/runs/{id}/stream`、`GET /api/v1/runs/{id}/events`、`POST /api/v1/runs/{id}/command`，以及示例 `GET /api/v1/examples/{name}`。

## 6. 说明

- 图中组件均按源码核对：域分派见 [compiler.py](../backend/fn_engine/compiler.py)，调度与线程见 [jobs.py](../backend/fn_engine/jobs.py)，会话工厂见 [sessions.py](../backend/fn_engine/sessions.py)，联算见 [coupling.py](../backend/fn_engine/refrigeration/coupling.py)。
- 本文件为 Mermaid 文本，GitHub / GitLab / VS Code 可直接渲染；需要 PNG/SVG 时可用 `@mermaid-js/mermaid-cli` 导出。
- 架构细节（启动、并发、存储、契约）仍以 [ARCHITECTURE_MAP](ARCHITECTURE_MAP.md) 与 [API](API.md)、[数据合同](DATA_CONTRACT.md) 为准。

## 风侧合同 1 的实际调用链（2026-10-29）

湿空气仍是 fluid 执行域。编译器复用既有节点/支路映射并调用 `air_compile`；`solver._solve_network` 调度 `air_transport.solve_air_network`，在水力与 h/w 输运之间反馈物性。`air_devices`、`air_room` 和 `cooling_tower_moist` 只返回候选值；`air_ledger` 随 `SimulationSession._accept` 一次提交累计量。

```mermaid
flowchart LR
  UI["Studio 风系统页 / 外部客户端"] --> API["api.py + air_api.py"]
  API --> C["compiler.py + air_compile.py"]
  C --> S["solver.py / air_transport.py"]
  S <--> P["CoolProp 湿空气服务"]
  S --> D["盘管 / 加湿器 / 房间 / 冷却塔"]
  S --> W["原 Worker 四阶段协议"]
  D --> A["SimulationSession 接受子步"]
  A --> L["air_ledger 累计量"]
  A --> F["同一 RunFrame"]
  F --> DB["RunManager / SQLite 归档"]
  DB --> R["冻结变量目录 / CSV / HTML"]
  R --> UI
```

运行创建时固定 `air_metadata`（物性版本、质量基准、项目摘要、变量目录与假设），沿用现有 JSON 存储事务。报告直接读取已保存的帧和目录，不执行编译或数值求解。新旧模块通过 SDK 0.6.0 能力声明区分，旧 RPC 过滤新增字段。详细行为及验证见 [风侧实施验收](AIR_SIDE_IMPLEMENTATION_ACCEPTANCE.md)。
