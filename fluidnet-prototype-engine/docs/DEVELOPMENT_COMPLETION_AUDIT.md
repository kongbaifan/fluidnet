# 开发完成情况核查与补修

日期：2026-10-27。核查基线为 `codex/development-consistency` 的 `2bf8391`，范围是最近三次提交的热耦合、无界面运行与算法补齐工作。下列修复和复验发生在该基线后的工作区。

后续用户已明确唯一目标为 **1920×1080（16:9）**，并于 2026-10-28 完成 1080p 基线、批量工况、结果存档和方案比较的[新一轮验收](FHD_BATCH_ACCEPTANCE.md)。DX 与过热度自调不在本轮范围。本页的 1366×768 等尺寸及结果是 2026-10-27 的实际测试记录，保留为历史证据，不替代后续 1080p 记录。

本次确认双盘管和电加热器各有未完成的入口或验收：双盘管的小窗口工具栏被画布遮挡；电加热器的算法虽然可直接调用，Studio 参数和通路转换却未接通。已补上这些遗漏，并同步当前状态，历史的算法测试或提交记录不再被当成完整界面验收。

## 发现与修复

| 项目 | 核查发现 | 本次修复 |
| --- | --- | --- |
| 双盘管界面与验收 | 原浏览器流程在 1366×768 下点击“盘管换热”超时，画布 SVG 拦截了点击；尚未执行后面的服务重启与保存项目复算，却已经被写为“已交付” | 工具栏换行后保留实际高度，避免被后续画布覆盖；沿用原浏览器断言完成流程，无强制点击或放宽物理容差 |
| 电加热器参数入口 | 原型的 `power` 参数未注册到转换表，调用报 `KeyError: 'heater'`；直接构造规范模型的算法测试没有覆盖这个入口 | 补上 `power → heat_input_w`，按单位定义将 kW 转为 W；同时补上局部阻力和内径映射，草稿、库值及工况共用相同转换 |
| 电加热器显式通路 | 真实界面导出的通路被标为 `heater/resistance`，编译器返回 `CHANNEL_MODEL_INVALID`；省略通路、复用默认模型的测试未发现该问题 | 保留设备的 heater 热力模型，将其水力通路转换为已注册的 resistance；回归用例包含真实原型端口／通路和自定义模块 ID |
| 当前状态文档 | ROADMAP 前段写“双盘管未实施”，末段写“已完成”；下一阶段计划也混用了开工时差距与当前状态 | 统一为经过专项复验的单／双盘管状态，标明历史判断依据，补充双盘管操作及合计变量说明 |

代码改动见 [界面样式](../frontend/index.html)、[原型转换](../backend/fn_engine/bridge.py)。新增回归在 [加热器后端测试](../tests/test_heater.py)与[加热器界面测试](../tests/browser-heater.mjs)；后者已接入 `npm run test:browser` 和前端语法检查入口。

## 验证

所有服务和算例使用临时工作区，不写入用户项目。后端测试与浏览器流程顺序执行。

| 检查 | 结果 |
| --- | --- |
| 定向后端回归 | 86 项通过（30.89 s），覆盖加热器、多进口容器、双盘管、原型转换、合同／物理与保存项目运行 |
| 加热器入口与物理 | 7 项通过，包含新增的正／负功率单位转换、显式通路、草稿／库值／工况、HTTP 归一化和保存后重启运行；已应用 5 kW 得到 5000 W，未应用 7 kW 草稿不参与计算，半功率工况得到 2500 W |
| 前端关系合同 | `npm run test:ui`：6 项通过 |
| 加热器浏览器 | 通过：真实项目导出／导入、2 kW 运行、参数预览并应用 5 kW、再次运行、保存与重载；结果分别为约 2000 W、5000 W，出口温度随功率升高，页面无脚本错误 |
| 浏览器回归 | 泵阀基础流程、单盘管通用建模、双盘管完整流程全部通过；连同加热器，共 4 个浏览器脚本通过，页面脚本错误均为 0 |
| 静态检查 | 修改的 Python 文件通过 ruff；mypy 按项目配置检查 62 个文件无错误；`npm run check` 通过 |
| 契约 | `generate_contracts.py --check`：67 个文件一致 |

本次未运行全量 pytest 或完整 `npm run test:browser`，不将以前的全量数量或覆盖率作为本次结果。新增浏览器脚本调试中修正了数字输入与滑块的选择器歧义，并在参数编辑后正常关闭设备浮窗、重载时等待工作区响应；保留真实的功率、能量残差及保存结果断言。

双盘管复验已实际执行到最后：两种拓扑运行、分别修改 UA、删除／撤销／移除／恢复关系、复制项目互不影响、1366×768 编辑，以及关闭服务后重启，再通过界面和已保存项目 API 复算，最终变量逐项一致。独立回路默认总换热量为 `28682.278758352368 W`。

## 证据与复现

- 双盘管原失败：`artifacts/dual-thermal-audit-before.log`、`artifacts/dual-thermal-failure-before-audit.png`。
- 加热器通路失败：`artifacts/heater-ui-audit-before.log`；最终通过：`artifacts/heater-ui-audit.log`、`artifacts/heater-ui-run.png`。
- 后端结果：`artifacts/completion-audit-tests.xml`。
- 浏览器回归：`artifacts/completion-audit-browser-smoke.log`、`artifacts/completion-audit-browser-thermal-coupling-modeling.log`、`artifacts/completion-audit-browser-dual-thermal-coupling.log`。
- 双盘管小窗口：`artifacts/dual-thermal-editor-1366.png`；两条盘管的运行结果：`artifacts/dual-thermal-coupling.png`。

在项目目录依次执行：

```powershell
python -m pytest tests/test_heater.py tests/test_multi_port_vessel.py tests/test_dual_thermal_coupling.py tests/test_thermal_coupling_bridge.py tests/test_contracts_and_physics.py tests/test_saved_project_runs.py -q --junitxml=artifacts/completion-audit-tests.xml
npm run test:ui
node tests/browser-heater.mjs
node tests/browser-smoke.mjs
node tests/browser-thermal-coupling-modeling.mjs
node tests/browser-dual-thermal-coupling.mjs
python -m ruff check backend/fn_engine/bridge.py tests/test_heater.py
python -m mypy --config-file mypy.ini
python scripts/generate_contracts.py --check
npm run check
```

## 明确未实施的范围

本次核查结束时未实施的批量工况与方案比较，随后已于 2026-10-28 按[新一轮计划](NEXT_DEVELOPMENT_1080P_PLAN.md)完成，见[验收](FHD_BATCH_ACCEPTANCE.md)。DX 蒸发器及按出口过热度自动调节膨胀阀仍未实现，且已移出本轮；当前满液／泵供液模型不提供所需的过热状态，见[算法域边界](ALGORITHM_DOMAIN_GAP_ACCEPTANCE.md)。液体侧储热、两条以上或跨不同容器的盘管仍不在当前耦合模型范围内。

此前取消的打包发版、变量别名、后续外部联调、24 小时稳定性专项和现场工程校核保持取消，不列为本轮剩余任务。
