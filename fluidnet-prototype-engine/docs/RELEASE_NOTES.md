# FluidNet 版本发布说明

## 未发布：数值性能与物理能力专项（2026-10-23）

基线 v0.5.0（`a986ca3`）。逐包证据与复现命令见 [证据索引](numerics/README.md)；
计划与验收依据见 [NUMERICS_OPTIMIZATION_PLAN](NUMERICS_OPTIMIZATION_PLAN.md)（已更新为执行状态）。

### 默认行为变化（只有两处）

- **新建项目默认 `hydraulic_method='auto'`**：按真实未知量与 Jacobian 稀疏度自动选 dense/sparse
  （阈值：未知量 ≥64 且稀疏度 ≤0.45 用 sparse；≥3000 未知量强制 sparse）。旧项目缺字段仍为 `dense`，
  显式请求永不被覆盖，auto 失败只允许一次可诊断回退。
- **纯内置网络默认解析 Jacobian**（`analytic_jacobian=True`）：阀门/管道/泵/阻力/换热器通路/水箱的
  解析导数，Jacobian 扰动调用降为 0；含 Python 模块的网络自动保留有限差分并在帧里说明原因。
  退化用例（零流量驻点假收敛）会一次性回退有限差分并记录原因。

### 新增能力（默认关闭或限定范围）

- **C 串联压缩**（`series_compression`，默认关）：1000 串联未知量 1999→1，端到端实测约 141×；
  结果与常规路径满足 3.1 差值门，`solution` 保持原网络布局。默认关闭，待更大范围回归后再定默认。
- **D 依赖安全分块**（`hydraulic_blocks`，默认关）：块/整网结果一致；静态多独立分量大网络 1.45–2.38×，
  但小模型回退 1.03–4.03×，因此不设为默认。
- **A 时间步误差控制**（`SolverOptions.time_step.enabled`，默认关）：Euler step-doubling + 按类别归一化，
  首轮支持理想热模型与冷库 B；四场景对固定 1 s 参考误差远低于计划门限；其他执行域显式拒绝。
- **I0–I4 单容积困液原型**（新内置模块 `closed_volume`）：定容 `state_du` 求 p/T、同温管壁储能、
  能量账本；只支持“初始即关闭”的单一均匀纯水容积。**不是完整隔离段功能**，开闭周期属 I5–I9。
- **V 止回阀 v2**：同 id 新版本 `2.0.0`（`modules/check_valve_v2`），反向精确零流、开关点残差连续；
  v1 源码与项目绑定不变。
- **L 迭代加速**：`thermal_acceleration='adaptive'/'aitken'` 为试验模式，慢例迭代 −67%；
  `coupling_acceleration` 实测无收益，保留试验选项，默认均为 `none`。

### 观测与基准

- `SolverOptions.hydraulic_diagnostics`（默认关）：帧里增加 `solve_counters`（真实残差调用、Jacobian 扰动、
  RPC 批次/实例、分项计时），数值不变。`RunFrame.solve_summary` 始终记录请求/实际方法、矩阵规模、选择原因与
  Jacobian 模式；两个字段都是新增可选字段，旧读取路径不受影响。
- 新增样例工厂/动态场景/基线与比较器脚本，以及 `docs/NUMERICS_BASELINE.md`。

### 兼容与升级

- 契约已重建（51 文件，`generate_contracts.py --check` 通过）；`SolverOptions` 新增字段全部有旧默认，
  旧项目/快照/工作区可继续打开，无需数据迁移。
- mypy 仍为 advisory；本轮把新模块的 advisory 错误清零（全仓低于 v0.5.0 的 40 条基线）。
- 未实现并明确排除：通用管网/冷库 A 的误差控制（X1/X2）、多容积与开闭周期（I5–I9）、分块并行（X0 实测无线程收益）、
  可变密度长输（G0 无案例）。

## v0.5.0（2026-10-22）

本版本是冷库案例 A/B 与倍思鹿模块套件的第一个里程碑发布。

### 主要更新

- **A 版冷库案例（A0–A6 完成）**：单库房 −18 °C 冻结物储藏案例，含单级 R290 循环（四状态点、排量/冷凝器 UA 反算、运行包络）、库房与货物两个热节点、冷风机、开门/入库/室外温度/电融霜日程、最小开停机与回差温控、8 个预置工况、机组工作点验证、HTML 报告/CSV 与两次运行对照。证据见 `cases/cold-storage/single-room-minus18/results/`。
- **B 版 NH₃/CO₂ 集总制冷站案例（B0–B3 完成）**：两库房、4 台 NH₃ 压缩机、3 个 `(M,U)` 闭式容器、蒸发式冷凝器、节流阀、复叠换热器、CO₂ 液泵与冷风机；五闭环（压缩机载量、贮液器压力、液位、库温、供液泵）+ 上层启停/负荷分配，输入目标蒸发/冷凝压力即可自运行；4 个验收工况（额定、负荷阶跃、改目标压力、湿球变化）。证据见 `cases/cold-storage/nh3-co2/station/results/`。
- **倍思鹿模块开发套件 v1**：8 个 Python 模块包（管件、止回阀、风机盘管、冷却塔、风机、变速泵、毛细管、等百分比阀）+ 2 个控制脚本模板；34 模块映射矩阵（A/B/C/D）、M1/M2 映射文档、NH3CO2ZL 工程画像、参考算例库与 `.PJTDB` 提取脚本；新增 `.github/workflows/bsl-modules.yml` 快速门禁与 artifact 打包。见 `DELIVERABLES.md`。
- **M2-L3 标定**：已完成 P-4（管道动态热容）、V-4（等百分比阀）、M-4（泵曲线单位）；其余 8 项待倍思鹿实测数据回填，R-4 因合同缺口阻塞（`docs/M2_L3_CALIBRATION.md`）。
- **M3 模块目录 UI**：`/api/v1/modules` 自动发现 8 个参考模块，模块库分类、参考模块徽章、参数/端口/变量/通路说明弹窗；浏览器回归纳入 `test:browser`（`docs/M3_MODULE_CATALOG_UI.md`）。
- **CI**：保留全量 `ci.yml`（backend + frontend）并新增 `bsl-modules.yml`（模块/控制模板快速门禁）；两个工作流均配置 concurrency。

### 升级说明

- 版本号从 0.4.10 升到 0.5.0；Pydantic 合同、项目/工作区 schema 与运行归档格式保持兼容，无需数据迁移。
- `contracts/` 已重新生成（OpenAPI 版本号同步为 0.5.0）。
- 旧项目、旧工作区和备份可继续打开；新增执行域（`thermal`、`refrigeration`、`cold_store`）只影响使用对应端口/设备的项目。

### 验证

- 后端：`pytest` 全量 **532 passed**，覆盖率 **90.77%**（门禁 85%）；mypy advisory 40 条基线不变；ruff 通过。
- 前端：14 个浏览器脚本 + 5 个前端 JS 语法检查通过。
- 契约：51 个 JSON Schema/OpenAPI 文件与生成器一致（`generate_contracts.py --check`）。
- 模块套件：21 项模块/模板回归 + 9 项 L3 集成 + 6 项标定 + 10 项目录契约（本机与 CI `bsl-modules` job）。
- 冷库 A/B：独立参考、质量/能量账本、步长敏感性与场景验收记录见 `cases/cold-storage/`。

### 已知边界

- 管网内两相流、水锤、完整可压缩瞬态、CFD 气流组织仍不在支持范围；制冷剂两相计算只在设备内部、按单相端口建模。
- 冷库工程校核（C 阶段）与 M4 真实试用需要厂家/现场数据，尚未开始；24 h 墙钟持续运行复核仍为 failed（历史遗留），M3 Windows 离线便携包尚未交付。
- 倍思鹿模块套件为架构/工作流对照与映射，不与倍思鹿做数值精度对测；参考算例快照不是收敛验收基准。

### 相关文档

- 案例计划与进度：`cases/cold-storage/PLAN.md`、`cases/cold-storage/TASKS.md`
- 模块套件交付说明：`DELIVERABLES.md`、`docs/MODULE_KIT.md`、`docs/BSL_MODULE_MAP.md`
- 验收记录：`docs/TRIAL_ACCEPTANCE.md`、`cases/cold-storage/*/results/`
