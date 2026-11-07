# 日常检查与手动完整验收

2026-11-07。P0-2 将 `.github/workflows/ci.yml` 的自动检查与 `ci-full.yml` 的完整验收分开。日常通过只证明选定范围通过，不代表全引擎覆盖率或全部浏览器流程通过。工作流修改合并到默认分支后才会成为默认 CI 行为。

| 范围 | 自动 `ci.yml` | 手动 `ci-full.yml` |
| --- | --- | --- |
| 触发 | PR、推送 master；同分支旧执行会取消 | 仅 `workflow_dispatch`；无定时、push、PR 或调用触发 |
| SDK | 严格类型、lint、独立测试和 SDK 覆盖率 | 相同 |
| 引擎静态与合同 | ruff、mypy、会话/Runner 严格类型、全部登记生成器只读校验 | 相同 |
| 后端运行测试 | 固定协议/接受事务/模型分层/API 合同/CI 门禁/生成物可移植性，加受影响领域专项 | 全部 pytest；覆盖率 floor 仍为 85% |
| 数值矩阵 | 当前运行环境，无额外 CPU 矩阵 | 默认/Haswell 全量矩阵及 Haswell/Sandybridge 数值对照 |
| 前端静态与单元 | 语法检查、全部轻量前端单元测试 | 相同 |
| 浏览器 | 固定 6 条跨域 smoke，加相关分组的代表流程 | 全部登记的 85 条调用、9 组、全部参数变体 |
| 汇总 | `ci quick` 等待 SDK、后端和前端均成功 | 后端完整矩阵与 `frontend full (Node 24 + Edge)` 分别报告 |

## 日常范围选择

`scripts/ci-quick.json` 是经过登记的专项清单，`scripts/ci-quick.mjs` 负责选择、校验和执行。后端固定核心每次执行；领域专项包括水力、热力、暖通、制冷、运行会话和模块。浏览器沿用 `browser-impact.mjs` 的影响面分组，再从各组选取代表流程；直接改动浏览器脚本时额外加入该入口的首个参数变体。

共享或未知文件、增加/删除/重命名、无法读取 Git 比较基线时，范围扩大到全部快速专项。没有有效比较基线时当前选择 17 条浏览器调用；不会由兜底逻辑悄悄启动全部 85 条。直接修改多个浏览器脚本时，选取数可能超过 17，但完整变体仍由手动工作流承担。

PR 用 base/head 的实际提交计算 merge-base 后比较；master 推送用 before/head。日常上传 `ci-quick-plan.json`，包含提交身份、选择理由、实际测试 ID、浏览器矩阵与延后的 ID。后端和浏览器下载同一份计划，执行前校验：不能插入清单之外的 pytest 目标、遗漏固定 smoke、重复组、伪造矩阵或延后清单。

原 `frontend (Node 24 + Edge)` 汇总名称继续保留，当前含义是日常前端范围。新增 `ci quick` 汇总 SDK、后端、前端；任一失败、取消或跳过都拒绝通过。后端日常名称为 `backend quick (Python 3.11)`，配置 required checks 时应选当前日常检查，不能要求仅手动运行的完整矩阵。浏览器组仍最多并行 3 组，CI 失败最多重试一次，恢复通过仍给出 warning。

## 本地入口

在 `fluidnet-prototype-engine/` 执行；生成计划不启动测试，也不依赖 Python 包已安装。

```powershell
npm run check:ci-quick
npm run test:ui:ci
node scripts/ci-quick.mjs --base <base-commit> --head HEAD --output artifacts/ci-quick-plan.json
# 没有比较基线时显式生成全部快速专项：
node scripts/ci-quick.mjs --output artifacts/ci-quick-plan.json
node scripts/ci-quick.mjs --run-backend --plan artifacts/ci-quick-plan.json
node scripts/ci-quick.mjs --run-browser --plan artifacts/ci-quick-plan.json --group workflows
```

本地浏览器执行默认不重试；只有明确加 `--ci` 才启用 CI 重试行为。`--run-*` 必须提供已保存计划；更改清单后应重新生成。后端执行前安装 `requirements-dev.txt`；浏览器执行前安装 `requirements.txt` 和 `npm ci`，沿用 Edge 与临时服务 harness。

GitHub Actions 的 `ci-full` 通过 “Run workflow” 手动启动。该工作流始终选全部组，不复用日常的裁剪计划。现有 `npm run test:browser` 也仍是本地完整前端入口，应在明确需要完整验收时使用。本轮实际检查结果在[P0 验收](P0_REPLAY_CI_ACCEPTANCE.md)，配置正确不等于远程 Actions 已运行。
