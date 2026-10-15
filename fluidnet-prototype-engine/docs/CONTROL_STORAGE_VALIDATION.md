# Python 控制与可靠保存验收

日期：2026-10-15。代码为 `5c05c79` 基线加当前工作区修改，尚未形成发行包。

## 已验收行为

- 控制页提供 Python 模板、启用开关、周期与声明输入/输出；旧 Lua 文本保留并禁用。
- 独立 Worker 执行 initialize/step/finalize；真实预览返回拟写入值，动态运行实际应用控制输出。
- 控制按仿真时间采样；失败子步复用提案，接受后提交状态；支持 PID 设定值，禁止多个控制者覆盖同一目标。
- 非法输入、参数越界、脚本异常、超时和非有限状态均产生诊断；保留已接受历史并回收 Worker。
- 保存完整原型工作区到 SQLite，确认成功后才显示已保存；保存失败保留本地草稿，陈旧页面返回 409。
- 工作区保留最近 5 个修订；运行保留请求、脚本哈希、参数/状态变量、诊断、事件、最近窗口和全程抽稀。
- 强制终止服务后，在没有原浏览器缓存的新环境恢复项目；未结束运行标为 interrupted，未确认命令标为拒绝。
- 运行档案支持查看、曲线、导出和删除；自定义流量与参数曲线保留规范键及单位换算，重启后可读。
- 验证存储故障不会产生虚假的新修订或可执行命令；验证停服复制目录后在另一目录恢复。

## 验证记录

| 检查 | 结果 |
| --- | --- |
| `python -m pytest -q`（扩充最后 5 项专项前） | 291 passed |
| `python -m pytest -q tests/test_controls_storage.py tests/test_history.py tests/test_continuous.py`（当时 19 项控制/存储专项） | 36 passed |
| `python -m pytest -q tests/test_contracts_and_physics.py tests/test_access.py` | 42 passed，含生成合同一致性 |
| 最终 `tests/test_controls_storage.py` 专项（含重启后保留数修复） | 20 passed |
| 既有 8 组浏览器验收 | 全部通过，无页面异常 |
| 最终 `node tests/browser-workspace.mjs` | 通过：真实控制、409 冲突、507 重试、强制重启、全新浏览器恢复、自定义曲线及旧文本保留；无页面异常 |
| `npm run check`、`git diff --check` | 通过 |

浏览器测试使用临时端口与隔离数据目录。`browser-smoke.mjs` 和 `browser-platform.mjs` 也已接入自动测试服务，不再要求预先启动 8798 端口。截图位于忽略提交的 `artifacts/workspace-controls.png` 和 `artifacts/workspace-legacy.png`。

## 范围与后续

恢复的是项目和已落盘历史；原仿真不能跨服务重启续算。默认保留最近 20 次终态运行、最近 `history_window` 帧和约 2000 点的抽稀曲线，不是无限全帧归档。当前采用每帧事务落盘，尚未进行 24 小时持续运行或容量/吞吐专项验收。

备份采用停服后复制工作区与模块目录。在线备份/迁移工具、独立项目修订接口、发行包及物理模型扩展继续按 ROADMAP 推进。
