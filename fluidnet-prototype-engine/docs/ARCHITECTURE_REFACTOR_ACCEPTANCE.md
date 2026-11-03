# 架构整理验收与迁移记录

代码原始基线：`7424576`；架构文档检查点：`676fdcd`。本轮工作分支 `codex/architecture-refactor`，执行计划见 [ARCHITECTURE_REFACTOR_PLAN.md](ARCHITECTURE_REFACTOR_PLAN.md)。

## AR-0 基线

- Python 3.11.0；Node 24.15.0；Edge 157.0.4341.36。核心依赖为 FastAPI 0.137.1、Pydantic 2.13.4、NumPy 2.3.2、SciPy 1.17.1、CoolProp 8.0.0，测试使用 pytest 8.4.1。
- 原始基线 [CI](https://github.com/kongbaifan/fluidnet/actions/runs/41608687342) 的前端两次在 `browser-module-assertions.mjs:47` 等待保存响应超时；[模块 CI](https://github.com/kongbaifan/fluidnet/actions/runs/41608687518) 通过。后端远端状态在最终验收时再记录。
- 本地原始基线：计划 F/S 后端专项 233 项通过，耗时 374.95 秒；UI 32 项通过；语法、ruff、mypy、合同与扩展示例一致性检查通过。
- 数值快照：普通流体、理想热系统、冷库 A、集总制冷站、制冷液体热耦合及多画布机房，各记录 0、5、10 秒共三帧。输入摘要、模块版本与双哈希、公开变量、守恒指标、诊断代码和参数修订保存在 [baseline-numerics.json](architecture-refactor/baseline-numerics.json)。采集脚本为 [architecture_snapshot.py](../scripts/architecture_snapshot.py)。

### 原有保存失败的根因与修复

连续创建、保存并重载较大的作者模块项目后，自动载入工作区会先备份本地副本；浏览器存储额度不足时备份失败。原流程因此中止服务初始化，后续计算仍可调用，但保存一直被本地 `ready=false` 拒绝，甚至不会发送 HTTP 请求。原始 CI 与本地均复现。

修复保持“备份失败就不替换本地草稿”：服务仍完成连接，保留客户端原来的工作区及项目修订，并显示备份失败提示。随后保存继续携带原修订，远端有并发修改时仍返回 409；不采用未载入的远端修订。其他合同或载入错误继续拒绝。

新增三个服务行为测试覆盖同修订保存、并发修订保护和非备份错误。修复后 UI 35 项通过，完整 `browser-module-workflow.mjs` 通过；项目工作流、旧档案迁移、工作区、运行控制、跨页管网和三页标准机房六个浏览器流程均通过；失败诊断新增保存提示，便于辨别无请求和 HTTP 失败。

本地原始日志位于 `artifacts/architecture-refactor/`，该目录不纳入 Git。此处仅记录实际完成项，不以历史全量数字替代本轮检查。

## 迁移清单

| 范围 | 原入口／调用者 | 目标入口 | 行为证据 | 状态 |
| --- | --- | --- | --- | --- |
| manifest、参数、显示单位 | studio: manifestFields / manifestParamSpecs / manifestParamDefaults；engine: manifestParamDef / moduleFromManifest / testParameters / runDesign | project-model | 项目交换、参数类型、作者模块验证 | AR-1 已迁移 |
| 项目文档、导入与升级 | services: projectDocument / exchangeDocument / upgradeDocument | project-model；服务层保留 HTTP 与固定版本准备 | project-exchange / browser-workflows / browser-refrigeration-projects | AR-1 已迁移 |
| 项目替换与恢复 | studio: restoreWorkspace / replaceState / import；workflows: applyDocument | project-state | 工作区修订、并发冲突、失败草稿、导入替换 | 待迁移 |
| 参数草稿和应用 | studio: 参数输入／库值／设备型号应用；engine: applyParameters / command | project-state | 批量参数、运行应用、草稿保存及撤销 | 待迁移 |
| 拓扑编辑 | studio: 插入／删除／连接／移页／复制与 remember/undo；links 工具 | project-state + project-links | 跨页、删除、撤销重做与重算 | 待迁移 |
| 当前与历史运行 | engine: applyRow / command / pollLive / confirmArchiveCache；studio: receiveArchives / showArchive | project-run-state | 迟到响应、增量帧、档案确认与历史 | 待迁移 |
| 公共参数、控制与资源 | SimulationSession: 参数命令、PID／脚本、检查点、close | SessionBase + 物理钩子 | 控制、事务、困液、停止与部分初始化失败 | 待迁移 |
| 热／制冷会话继承 | ThermalSession / ColdStoreSession / StationSession / CoupledStationSession | 非流体公共基类，保留域内步进 | 五域基线与失败回滚 | 待迁移 |
| 调度与预览 | jobs 的会话访问；API `_control()` 与 `scripts.pending` | RunSession 协议及显式预览方法 | 后台运行、控制预览及类型门禁 | 待迁移 |

## 后续包记录

AR-2～AR-7 待实施。各包完成后在此添加提交、实际检查和剩余问题，并同步迁移清单与计划进度。

## AR-1 项目转换

新增纯转换模块 `project-model.js`，集中 manifest、显示单位、参数默认值、项目文档、规范导入和升级转换。服务层保留 HTTP 校验与固定版本准备；现有脚本加载及测试宿主同步加载新模块。

验证：38 项 UI 单元测试；项目工作流、制冷项目导入／升级／回退、完整模块作者流程、参数整批写入四个浏览器流程通过；语法检查通过。新增单位测试覆盖温度与温差、开度、功率、体积流量及非数值参数。
