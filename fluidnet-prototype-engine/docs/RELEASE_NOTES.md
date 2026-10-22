# FluidNet 版本发布说明

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
