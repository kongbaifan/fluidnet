# 设备面板与机组运行范围扩展验收

日期：2026-11-04。开发分支：`codex/device-panel-and-chiller-controls`，基线 `a165ece`。本轮按用户要求只做定向检查，没有触发或运行全量回归。

## 交付

1. AR-7／NUM-1：核实已有完整 CI 全部成功，登记精确提交、检查编号、后端覆盖率及通过数量。此结果仅对应原架构代码基线。
2. 设备面板：总览、参数与型号、全部变量、连接四个页签；真实结果来源及过期提示；常用参数复用草稿／预览／应用事务；冻结控制归属；区分已应用设置与采样值。展示代码提取到 `frontend/device-panel.js`。
3. 机组首版运行范围：最小冷冻水／冷却水流量保护、停机等焓通流、可选低负荷周期平均运行；默认关闭新增限制以兼容既有项目。实际逐次启停与储热模型仍需后续专项。

## 实际检查

| 范围 | 命令或入口 | 结果 |
| --- | --- | --- |
| 面板单元行为 | `node --test tests/device-panel.test.mjs` | 4 passed：冻结脚本归属、手动 PID、设置／采样／草稿分离 |
| 既有 UI 单元行为 | 原 `npm run test:ui` 清单 | 52 passed；随后将新增 4 项纳入清单 |
| 新面板浏览器 | `node tests/browser-device-panel.mjs` | 通过：未计算占位、真实读数、编辑焦点、取消预览、过期提示、复算、页签、保存重载 |
| 既有浏览器定向 | `browser-smoke.mjs`、`browser-run-control.mjs`、`browser-platform.mjs`、`browser-cross-page.mjs`、`browser-pid.mjs` | 通过，无页面错误 |
| 机组／空气联算定向 | `python -m pytest -q tests/test_water_chiller.py tests/test_chiller_operating_limits.py tests/test_chiller_air_loop.py tests/test_air_room_controls.py` | 43 passed，34.37 s |
| 静态检查 | 前端语法；后端 ruff；mypy | 通过，mypy 93 个文件 |
| 生成物 | 90 份合同；房间温控、暖通、液体作者示例与暖通模块检查 | 通过；4 个示例只同步机组目录定义 |

新面板截图：`artifacts/device-panel-overview-1080p.png`（1920×1080、DPR=1），已实际查看，停靠面板、输入、页签和底部操作均完整可见。截图和临时测试工作区不纳入源码版本。

本轮没有合并 PR #8，没有覆盖用户工作区或原 `output/device-panel-concept*` 设计稿。新功能未取得完整 CI 结论，以上只表示记录的定向范围通过。

使用说明：[设备面板](DEVICE_PANEL.md)、[机组运行范围](CHILLER_OPERATING_LIMITS.md)。

## 后续审查修复

整体审查进一步发现库值应用未走后台事务及流量保护触发位置错误；均已修复并增加定向回归。绑定版本查看与接口示例也已改正，实际证据见[整体审查修复](PROJECT_REVIEW_FIXES.md)。前述首次检查范围不能代替这些新增边界验证。
