# 1080p 基线与批量工况验收

日期：2026-10-28。范围为用户确认的前两项：**1920×1080 基线，以及批量工况、独立结果存档、方案比较和 CSV 导出**。六个工作包均已实现并完成下列定向验收。操作说明见[批量工况与方案比较](SCENARIO_BATCHES.md)。

## 交付

| 工作包 | 结果 |
| --- | --- |
| FHD-1 | 公共 `FHD_CONTEXT` 统一视口、屏幕尺寸和 DPR；22 个既有浏览器脚本完成迁移，新截图为真实可见的 1920×1080，并保存环境元数据 |
| FHD-2 | 泵阀、加热器、旧工况／版本工作流、单盘管和双盘管在统一尺寸下复验；参数编辑、保存与重启复算通过 |
| BATCH-1 | 数据库升级到版本 3；批次独立保存项目、模块／控制脚本快照、末值和曲线，结果随运行终态在同一事务落盘 |
| BATCH-2 | 显式数值列表、等间距序列和已有工况选择；显示单位转换、范围检查、预览、重复提交保护 |
| BATCH-3 | 一个活动批次、顺序执行、普通失败后继续、取消剩余项、停止当前项、服务重启后从冻结输入重试；保留已完成项和运行来源 |
| COMP-1 | 多工况结果表、最多四条同变量曲线、来源查看、独立历史重开和 CSV；失败／缺失结果不填成零 |

前端新增“批量”页面和建模工具栏入口。预览按钮固定在参数面板底部；普通模型说明与错误诊断分别呈现。新工作不包含 DX、过热度自调或其他分辨率适配。

## 最终验证

环境：Windows、Python 3.11、Node 24、Edge 157。浏览器自动化视口 **1920×1080**，DPR **1**。所有功能测试采用临时工作区。

| 检查 | 结果 |
| --- | --- |
| 定向后端回归 | **99 项通过，60.88 s**：批次、项目工作流、控制／存储、备份、已保存项目运行及合同／物理测试 |
| 批次专项 | 上述回归中 **14 项**，覆盖单位、输入校验、冻结源码、重复提交、求解失败、取消、中断恢复、存档清理、存储故障和曲线边界 |
| 前端关系合同 | `npm run test:ui`：**6 项通过** |
| 浏览器 | **6 个脚本通过**：smoke、heater、workflows、thermal-coupling-modeling、dual-thermal-coupling、scenario-batches；页面脚本错误均为 0 |
| 契约 | `generate_contracts.py --check`：**75 个文件一致**；新增批次路由有严格响应模型，CSV 按其真实媒体类型声明；路由检查涵盖 included router |
| 静态检查 | ruff 通过；mypy 按项目配置检查 **66 个文件无错误**；`npm run check` 通过 |

本轮没有运行全量 pytest 或完整浏览器套件，不把历史全量结果计为本轮结果。中断测试中的长仿真时长用于确保任务仍在运行，随后立即停止或重启服务，不是 24 小时稳定性测试。

### 行为证据

- 五个阀开度工况与逐项独立求解的流量、泵功一致；加热器 2／5 kW 分别进入引擎为 2000／5000 W。
- 批次创建后改变项目、模块版本及控制源码，批次仍使用原快照。清理旧的五个项目修订、二十条运行记录后，重启仍可读取相同批次末值与曲线。
- 浏览器实际完成生成、预览、运行、四曲线比较、CSV 下载、已有工况选择、删除普通运行后的重启读取，以及运行中终止服务、继续未完成项和取消操作。
- 存储故障注入暴露并修复了“把落盘失败当普通计算失败继续队列”的问题：现在停止派发，将受影响项保留为可重试中断项。事务注入验证普通运行终态与批次结果共同提交或回滚。
- 3001 点输入验证曲线保存不超过 2000 点且保留首尾；版本 1／2 工作区升级与已有项目保存通过回归。

## 原始记录

- 后端：`artifacts/batches-regression-tests.xml`。
- 最终浏览器日志：`artifacts/batches-final-browser-*.log`。
- 预览：`artifacts/batches-preview-1080p.png`。
- 比较：`artifacts/batches-comparison-1080p.png`。
- 已有工况：`artifacts/batches-existing-scenarios-1080p.png`。
- 重启读取：`artifacts/batches-restart-1080p.png`。
- 中断与取消：`artifacts/batches-interrupted-1080p.png`、`artifacts/batches-cancelled-1080p.png`。
- 每张新截图旁的 `.png.json` 记录实际视口、像素比、浏览器版本、时间和页面地址。

## 复验命令

在项目目录依次执行：

```powershell
python -m pytest tests/test_batches.py tests/test_project_workflows.py tests/test_controls_storage.py tests/test_backup.py tests/test_saved_project_runs.py tests/test_contracts_and_physics.py -q --junitxml=artifacts/batches-regression-tests.xml
npm run test:ui
node tests/browser-smoke.mjs
node tests/browser-heater.mjs
node tests/browser-workflows.mjs
node tests/browser-thermal-coupling-modeling.mjs
node tests/browser-dual-thermal-coupling.mjs
npm run test:browser:batches
python -m ruff check backend tests/test_batches.py tests/test_project_workflows.py tests/test_contracts_and_physics.py scripts/generate_contracts.py
python -m mypy --config-file mypy.ini
python scripts/generate_contracts.py --check
npm run check
```
