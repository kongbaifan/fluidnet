# 核心流程与源码交付记录

维护日期：2026-11-12。产品源码基线为 `edb8c2df49cd4e9a408e6a65e90e18a1fcd43414`，位于 `codex/large-multi-room-cold-store`；当前文档收尾在该基线上完成。实施范围见[完整计划](MODULE_PRODUCT_ROADMAP.md)，正常操作见[使用步骤](CORE_WORKFLOW_GUIDE.md)。

后续说明：同日用户确认开展[界面说明清理](INTERFACE_COPY_CLEANUP.md)，后续前端已在此基线上变化。下文哈希与 25 次界面运行属于清理前的原验收，不能当作清理后已重新通过浏览器复验。

## 已完成的技术范围

2026-11-11 的核心流程修复和验证已经提交、推送。2026-11-12 核对当前产品文件与该批验证的哈希，并将实际进度写回计划。以下数据来自原验收，不计作今天新跑的浏览器或单元测试。

| 范围 | 证据与结果 | 对应入口 |
| --- | --- | --- |
| 工作台与参数控制 | 设备入口、待应用修改、运行反馈；PID 非法输入、初始配置与运行采样、脚本归属和确认写入已修复 | `frontend/studio.js`、`frontend/device-panel.js`、`frontend/cold-room-controls.js` |
| A：泵阀管网 | 5 设备、4 连接的空白组装及内置示例；调阀、调泵速、真实读数与曲线、保存重载、复制和导入复算通过 | `node tests/browser-core-workflow.mjs --case water` |
| B：单库房 | 3 设备、2 连接的已有模板；自动降温、增载、手动停机、−9/−18°C 目标变化、曲线及文件往返通过 | `node tests/browser-core-workflow.mjs --case cold-room` |
| C：51 设备六库 | 72 连接、4 页、19 PID；逐页定位、只修改 F01 目标、六库状态与总功率、曲线及文件往返通过 | `node tests/browser-core-workflow.mjs --case six-room` |
| 结果与恢复边界 | 历史曲线与参数来源、迟到档案/帧、结果过期、断连及恢复、保存并发/409/507/容量路径共 20 项通过 | `node tests/browser-results-boundaries.mjs` |
| 最终定向检查 | 前端单元 382 项、后端专项 82 项、131 份合同；语法及 CI 清单检查通过 | 原日志及 `artifacts/core-workflow/summary.json` |

三个代表场景合计 25 次界面运行、12 条重开/复制/导入复算路径、2925 项数值比较；记录的最大绝对和相对误差均为 0。这个结论仅适用于固定输入和短程操作，不能外推为任意设备、工况或长期模型精度。

原机器证据位于 `artifacts/core-workflow/`：`summary.json`、`representative-summary.json`、`parameter-audit.json`、`results-audit.json` 和三个场景的 `evidence.json`。这些是本机产物，Git 不附带；克隆仓库后可用表中已跟踪的测试入口生成新的证据，不应把缺失产物解释为本地已复验。

原验证记录覆盖 239 个前后端产品文件，SHA-256 为 `64aea18e615bfb2cda9ffe0cc361eaef7c368754f5f4160642fe41aa1ad1bd39`。原记录的准备提交是 `3ff6905`，发布字段确认对应变更形成提交 `edb8c2d`，且提交树匹配验证源码；不能只用准备提交号判断验收失效。

### 复跑入口的环境

在 `fluidnet-prototype-engine` 目录按[启动步骤](CORE_WORKFLOW_GUIDE.md#启动)安装 Python 依赖，另准备 Node 24.9 或更高版本和本机 Edge。测试会调用 PATH 中的 `python`，应在已激活的 `.venv` 中运行；也可只在当前 PowerShell 会话中设置：

```powershell
$env:Path = (Resolve-Path .venv\Scripts).Path + [IO.Path]::PathSeparator + $env:Path
python --version
npm ci
node tests/browser-core-workflow.mjs --case water
node tests/browser-core-workflow.mjs --case cold-room
node tests/browser-core-workflow.mjs --case six-room
node tests/browser-parameter-controls.mjs
node tests/browser-results-boundaries.mjs
```

这些脚本创建临时服务及隔离工作区，并输出本次运行的证据。按实际改动选择相应范围，完整验证入口见[开发说明](../README.md#验证)。上面是复现命令，本次文档收尾未执行这组浏览器测试。

## 本次交付收尾

- 同步当前计划的阶段状态，并分别记录技术证据、文档交付和用户反馈。
- 提供 A/B/C 的入口、短程运行设置、调参观察、保存复制和文件往返步骤。
- 修正当前使用说明中的保存按钮、计算节奏入口和跨重启续算描述。
- 首次启动说明明确选择 Python 3.11，避免 PATH 中旧 Python 创建不兼容环境。现有 3.11 环境启动独立服务成功；本次没有重新安装全部依赖，也没有验证干净机器安装。

本次检查确认 239 个产品文件与原验收哈希一致，三个场景记录及测试源码、六库规范工程、参数与恢复审计也一致；修改文档的本地链接、标题锚点和 Git 差异空白检查通过。本机结果保存为 `artifacts/source-delivery-review-20261112/delivery-audit.json`。本次为文档改动，未重复执行已通过且未受影响的功能测试。

## 未执行与后置项

| 项目 | 状态 | 影响与下一步 |
| --- | --- | --- |
| 2026-11-12 新增界面复验 | 未执行 | 独立服务启动后，浏览器权限检查拒绝本地演示地址；不据此新增通过记录 |
| 独立用户按使用说明试用 | 待反馈 | 技术记录不能证明用户无需帮助即可使用；按使用步骤 A → B → C 记录卡点后处理 |
| 126 设备完整运行日 | 待验证 | `examples/large-cold-store/continuous-validation-summary.json` 为 `pending`；完整仿真日、事件物理与恢复等价另行验收 |
| 主导航与专用案例入口进一步收敛 | 后置便利项 | 当前入口可达；使用步骤提供明确路径，实际试用若仍难找再处理 |
| 空白单库房自动生成温控脚本 | 后置便利项 | 已有 −18°C 模板自带脚本可直接使用；手工空白组装仍需显式配置控制 |
| 所有历史设备包装的观察入口推广 | 超出已验收范围 | 本轮只确认代表泵、阀及单库房/六库读数，不宣称所有旧包装已补齐 |

代表场景范围内原审计发现的参数与结果问题均已修复并验证。安装包、发版、现场标定和 24 小时墙钟专项沿用本轮范围约定；用户试用与 126 设备完整运行日仍保持独立待办。
