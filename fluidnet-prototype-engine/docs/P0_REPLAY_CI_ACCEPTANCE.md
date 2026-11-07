# P0 回放修复与日常 CI 验收

日期：2026-11-07。基于已合并的 `cab1752`，在同一个工作树的 `codex/replay-and-fast-ci` 分支实施。P0-1 提交 `f95a3fc`；P0-2 以包含本记录的提交为准。这里的 P0 编号指本轮回放收尾与 CI 分层，前序模型分层、设备注册的交付见[文档索引](README.md)。

## 变更

- P0-1：保留用户对回放面板的简化，修复迟到归档导航、旧回调忙状态和归档请求干扰正在执行的回调；增加导航代次，覆盖离开后返回同一页面的情况。改为原生 ES Module，删除最后一个回放 adapter 和遗留全局工厂。
- P0-2：自动 CI 执行静态、SDK、合同、固定事务核心、受影响后端专项与代表浏览器流程；完整覆盖率、CPU 矩阵和全部浏览器参数变体迁入只允许手动触发的 `ci-full.yml`。完整检查配置保留，覆盖率 floor 仍为 85%。[CI 检查说明](CI_CHECKS.md)列出范围与执行入口。
- 新增工作流结构与真实 PowerShell 汇总测试，确保上游失败、取消、跳过均无法让汇总变绿。无比较基线的当前计划选择全部 6 类后端快速专项和 17 条浏览器调用，明确登记延后的 68 条。
- 快速后端验收发现既有测试手写的 76 条路由已过期：此前已新增 `/projects/{project_id}/batch-options` 并写入 OpenAPI，实际为 77 条。改为核对登记合同中的路径/方法集合，并拒绝重复路由；未修改接口或生成合同来迎合测试。

## 证据

本机日志保留在 `artifacts/p0-replay-ci/`（忽略入库）。表内次数有重叠，不能相加当作独立测试总量。

| 命令或流程 | 本轮实际结果 | 日志 |
| --- | --- | --- |
| 修复前回放单测 | 5 项中 3 通过、2 失败，复现迟到归档与忙状态问题 | `replay-before.log` |
| 回放与模块入口专项 | 11 项通过，随后也被整体轻量单元入口覆盖 | `replay-after.log` |
| `npm run check` | 前端及 CI 脚本语法通过 | `frontend-syntax.log` |
| `npm run test:ui` | 289 项通过，约 3.89 s；包括 22 项分组/范围/执行器测试 | `frontend-units.log` |
| 新计划的 `--run-backend`（所有快速专项） | 250 项中 249 通过、1 旧路由计数断言失败，109.19 s；不是全量 pytest | `backend-quick.log` |
| 路由断言修复后，3 个 API 合同测试加工作流测试 | 10 项通过，7.93 s；未重复已经通过的其余专项 | `contracts-ci-after.log` |
| 新计划的 `--run-browser --group workflows` | 设备参数事务、失败复现两条通过；延迟归档响应未夺回导航，页面异常均为空 | `browser-quick-workflows.log` |
| `browser-module-loading.mjs` | 44 个原生模块、无重复请求、无 FluidNet 工厂、无回放全局工厂，失败提示可见，页面异常为空 | `module-loading.log` |
| `python scripts/generated_artifacts.py --verify` | 13 个生成器全部只读校验通过，包括 111 份合同 | `generated-verify.log` |
| `ruff check backend tests scripts modules examples/control_templates`、清单校验与 `git diff --check` | 通过 | 本轮命令输出 |

## 剩余边界

按用户要求，本轮不运行全量后端覆盖率、完整 BLAS 矩阵和完整浏览器链。没有触发远程 Actions，因此没有远端耗时或远端全绿结论；自动与手动触发规则已通过本地结构检查和实际汇总脚本执行验证。

工作流在本地提交，推送并合并默认分支后才会成为仓库默认行为。工作树数量保持 1；用户的 `beisilu/` 和 `output/device-panel-concept-*` 文件未纳入这些提交。前序验收记录保留原基线，新入口注明当前状态。
