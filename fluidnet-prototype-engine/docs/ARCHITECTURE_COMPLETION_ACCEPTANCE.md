# 架构剩余工作最终验收

2026-11-07，起点 `8dfb853`。完成用户批准的AC-1～AC-5，代码提交见下表；沿用现有主工作树，没有新建工作树。没有推送、触发远端CI或执行全量pytest/完整浏览器链。一次轻量前端单测全入口用于检查模块加载影响，后续执行明确的定向入口。

## 交付与提交

| 包 | 结果 | 提交 |
| --- | --- | --- |
| AC-1 CI影响范围 | 固定smoke，叶子/浏览器入口按组选择；未知、共享、身份变化或比较失败回退全组；保留汇总门，上传理由 | `ad645bb`、`7d0b7e4` |
| AC-2 前端模块 | 41工厂显式导出，统一bootstrap，40份隔离加载代码迁原生ESM；真实浏览器45脚本无重复加载，零FluidNet全局 | `94413b3`、`7d0b7e4` |
| AC-3 物理分派试点 | 7种水力关系合并值/导数/通路/直接模型登记，13计算体AST一致、98冻结数值/导数快照相等 | `1a2ffe5` |
| AC-4 画布热点 | 每帧复用设备模块，参数身份与上下文减少重复扫描，DOM和草稿保持；四规模前后测量 | `4c6dbf8` |
| AC-5 Worker决定 | 当前启动、首次物性、12个冷热生命周期、内存和退出测量；总时间无明显收益，保留按需创建 | `ee7c193` |

前端采用相对路径原生模块，不需要import map/bundler。Node开发/测试要求24.9+，VM隔离测试入口明确带 `--experimental-vm-modules`。生产页面不使用VM测试加载器。原Runner传输差异、冻结JSON、单页64台和跨域物理限制保留。设备分派为单相水力试点，未宣称所有热/制冷/储量执行路径都完成注册化。

## 实际验证

各组有交叉，不能相加为独立总数。

| 入口 | 结果 |
| --- | --- |
| `npm run test:ui:modules` | 最终258项通过；覆盖全部本轮迁移的公开模块及交互、保存、参数、模型边界 |
| `node --test tests/browser-impact.test.mjs tests/browser-groups.test.mjs` | 最终14项通过；真实Git重命名、未知/共享回退、变体选择与原执行器 |
| `pytest tests/test_hydraulic_dispatch.py tests/test_hydraulic_derivatives.py tests/test_analytic_jacobian.py tests/test_device_registry.py -q` | 182项通过 |
| `pytest tests/test_worker_startup.py -q` | 10项通过，12.76 s |
| ruff / mypy | 全范围ruff通过；mypy151文件通过 |
| `generate_contracts.py --check` | 111合同一致；设备目录专项完整JSON/哈希/顺序保持 |
| 语法 / 清单 / diff | npm check、清单85调用/58文件/9组/3helpers、git diff --check通过 |
| Worker实验 | 四类启动与两个整网首步均零失败；冷热每组3样本，12生命周期结果/状态一致，无残留子进程 |

本轮实际通过的9个浏览器入口：

- module-loading：独立模块导入、MIME、无重复请求、直达workbench、依赖503可见提示。
- module-catalog：60内置设备图标及8参考模块。
- workspace：409/507、草稿恢复、服务重启中断与归档。
- module-workflow：四种作者模板、发布、验证、源码断言和重载复算。
- run-control：最终0.5s停止，11帧停止后不增长；趋势61帧/30partial；3参数写入、2接受、1拒绝。
- device-transactions：曲线单独应用、库值确认、控制接管拒绝与冻结版本。
- hvac-plant：调阀支路1 3.417191793→1.678946311 m³/h，支路2 4.427214165→5.409520578；重载相等，能量残差绝对值小于0.006 W。
- refrigeration-modular：空白8设备/9连接、60s动态，108数值按六位小数重载对照；冻结模块、曲线、HTML/CSV通过。
- canvas-performance --live：30/64/100/300规模全部交互、焦点、DOM身份、运行转换断言通过，单页上限64。

浏览器页面异常均为空。性能另有300台带Profiler前后两次采样；不能把带Profiler数据作为最终帧率。没有重跑cold-store cascade/equipment、HVAC multi-page等其他变体，也没有把本地定向结果视为远端CI成功。

## 性能结论

无Profiler运行叠加的300台分页样本，p95约27.8→20.8ms、最大间隔62.5→41.6ms、长任务1→0；30台p95则7.1→13.9ms，保留噪声和未改善项。采样窗口受自动化/宿主调度影响，仅说明本机该流程，不能保证复杂工程或1000台同屏表现。[详细性能记录](WORKBENCH_LOCAL_REFRESH.md)附所有规模与热点数据。

Worker普通首步约0.576s，预启动后请求首步0.017s，但预启动+请求总0.586s；需物性模块1.614s→1.040s，总1.602s。预启动把成本移到空闲期，未证明跑批吞吐改善；没有启用生产池化。[决策记录](WORKER_PRESTART_DECISION.md)给出可复现入口、内存和隔离范围。

## 工作区已知问题与保护

用户原有未提交 `frontend/module-replay.js` 没有修改/暂存。原始SHA256 `2e191c24d95be262833ca645d7cc80d4cbd0764be516baa3b4c2defbe39c5d35` 最终核对一致；模块迁移仅增加adapter。此文件对应两个既有前端回归失败：离开记录页后迟到归档会导航回验证台；旧复现可能保留忙状态。一次全部轻量单测当时为271通过/2失败；相同5个replay测试读取已提交源码时5项全通过，故不能宣称当前带用户改动的整个工作区所有测试通过。没有删除断言或覆盖该文件以消除失败。

用户的 `beisilu/` 和 `output/device-panel-concept-*` 保留。最终无本轮未提交功能代码。原始日志、性能JSON、AST对照与源码身份在 `artifacts/architecture-completion/`，不作为产品输入入库。文档以本次范围和对应基线为准，历史全量数字不替代当前验证。
