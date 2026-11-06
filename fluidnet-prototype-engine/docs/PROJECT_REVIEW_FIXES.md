# 整体审查问题修复

日期：2026-11-04。分支 `codex/device-panel-and-chiller-controls`。本轮在上一轮本地未提交的设备面板与机组扩展基础上修复已复现问题；仅执行定向检查，没有运行全量回归或触发远端 CI。

## 修复结果

| 问题 | 修复后行为 | 验证 |
| --- | --- | --- |
| 运行中应用设备库值仅改本地 | 普通草稿和库值共用确认事务，整批发送后端；确认后更新本地，拒绝保留参数与草稿。禁止同设备重复提交，迟到回执不作用于替换项目或运行，等待期间新草稿保留 | 真实浏览器库值80%→40%并核对后端命令回执；脚本控制拒绝；5项异步行为回归 |
| 最小流量保护在物性中间迭代误触发 | 普通水侧与风水联算统一在网络收敛后、观察和状态接受前检查两侧流量。阈值0关闭新增保护，原反流与物态保护保留 | 旧实现3条误报回归失败；修复后机组专项51 passed；另1条关闭保护/反流容差边界通过 |
| 查看设备定义打开全局库的新版本 | 只读弹窗展示项目绑定版本的合同、源码和选中变量；另有明确的“编辑模块库草稿”入口，保留返回设备 | 真实发布新版本后检查旧设备定义仍为旧版、旧源码；库编辑可看到新版；变量定位和返回通过 |
| 接口示例固定V1 | 从所选运行的冻结合同与实际发布帧生成变量目录；使用规范单位，排除控制器/脚本接管参数；读取、写入格式和订阅使用所选键 | 无V1的两支路暖通项目成功读取/生成示例，令牌认证通过；3项目录与请求单测 |

接口页面写入与订阅继续只提供示例，GET读取真实后端；写入要求运行未结束，页面已明确说明。刷新目录可在新帧产生后重取；异步结果绑定项目对象、运行对象及运行编号，旧响应不能覆盖新项目。

## 文档一致性

- 能力清单SDK版本同步到实际0.8.0。
- 帮助与设置页明确真实后端计算、Python控制脚本执行行为。
- 浏览器测试数量以package.json脚本清单为准。
- 机组旧说明补充可选周期平均运行，同时保留水侧储热、真实逐次启停尚未实现的范围。

## 定向检查记录

- `node --test tests/device-application.test.mjs`：5 passed。
- `node --test tests/api-examples.test.mjs tests/device-panel.test.mjs`：7 passed。
- `node tests/browser-device-transactions.mjs`：通过，包含库值后端确认、脚本归属拒绝、绑定版本和库草稿分离。
- `node tests/browser-api-examples.mjs`、`node tests/browser-auth.mjs`：通过。
- 受参数事务影响的 `browser-run-control.mjs`、`browser-authoring.mjs`：通过。
- `python -m pytest -q tests/test_water_chiller.py tests/test_chiller_operating_limits.py tests/test_chiller_air_loop.py --tb=short`：51 passed，55.65秒。
- 关闭保护容差补充：`test_disabled_flow_limits_preserve_the_existing_reverse_flow_tolerance`，1 passed，5.65秒；未重复执行前述51项。
- 改动前端语法检查、后端改动文件ruff、mypy（93文件）与差异检查通过。

新的测试入口已加入现有脚本清单；本轮未执行其中的全量命令。截图位于忽略提交的artifacts目录，测试使用隔离工作区。所有原有设计稿与用户数据保持原位。
