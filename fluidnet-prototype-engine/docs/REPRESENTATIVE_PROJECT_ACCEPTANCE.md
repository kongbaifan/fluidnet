# 本轮代表工程验收

2026-11-07。输入采用仓库现有机房与模块化冷库，所有组装、参数编辑、连接、观察变量、保存与文件操作经真实界面完成。`page.evaluate` 仅读取 DOM／已保存状态和测量屏幕位置，不直接写应用状态。测试使用独立临时服务与数据目录。

## 标准机房：空白组装

```powershell
node tests/browser-equipment-assembly.mjs examples/hvac-basic/hvac-basic-plant.project.json --standard-plant
```

30 台设备、34 条连接由模块库逐台插入并经鼠标拖动排列。四个测点经控制页建立。脚本逐项检查所有 recipe 明确给定的参数已应用，并与第一次引擎规范请求对照，不以“草稿已填入”代替参数生效。

此流程采用动态 1 s／0.1 s，用来覆盖真实连续曲线；热湿迭代上限从设置对话框设为参考工程的 400。其余未开放的求解选项保留新项目默认，故这是一套同拓扑、给定物理参数一致的 UI 组装验证，不宣称它与原稳态案例所有求解选项逐字段相同。原稳态合同另由下节独立验证。

| 测量 | Balance1 80% | Balance1 40% | 导入重算 |
| --- | ---: | ---: | ---: |
| 支路 1 体积流量（m³/h） | 3.4169287004 | 1.6788149477 | 1.6788149477 |
| 支路 2 体积流量（m³/h） | 4.4268730722 | 5.4090966294 | 5.4090966294 |

测点规范单位为 m³/s，表格按测点合同的显示比例转换。调阀后，保存导出、导入新项目、页面重载与复算全部通过；1600 个数值变量的最大绝对差为 0。三次运行的完整模块定义及内容／定义哈希完全一致。曲线页面存在来自真实采样的路径，HTML／CSV 从归档界面下载并包含本次设备和运行身份。

最终运行：基线 `e506fd1d94f64b26af9d5d0ad3b24083`、调阀 `8595b27d1e534792932d9b4bc630d3b1`、导入重算 `6d97aaecc4c44a109b574bc48102a86c`。页面异常为空。证据：`artifacts/interaction-delivery/hvac-assembly.log`、`hvac-assembly-evidence.json`。早期未应用泵曲线的运行已作废，不属于上述结论。

## 原标准机房：稳态物理与展示回归

```powershell
node tests/browser-hvac-plant.mjs
```

原案例保持稳态和原测点／求解设置。风水三回路、端口质量／比焓独立守恒、仪表、曲线采样点、报告、调平衡阀及保存重载通过。支路 1 从 3.4171917926 降到 1.6789463113 m³/h，支路 2 从 4.4272141654 升到 5.4095205782 m³/h；重载相同。调阀后水量残差为 0，冷冻水热残差约 -0.00532 W，冷却水热残差约 0.00344 W，均遵循原断言阈值。

最终运行：基线 `f6efe5a1c10e42cf9b3ab257adffd01f`、调阀 `71c9df0b0b6c417c95a55391aa359c25`、重载 `d8685306a22c4136bbac99c5e5e96492`。页面异常为空。日志为 `artifacts/interaction-delivery/hvac-plant.log`；原脚本图像／JSON／报告保存在 `artifacts/hvac-plant-*`。

## 本轮集成修复

- 湿空气设置缺少已存在合同的迭代上限入口。新增输入对应 `MoistAirOptions.max_iterations`，默认 60、整数 1–500；保留其他湿空气选项，不改数值算法。3 项公开界面工厂测试验证已有值、默认值、边界与非法输入拒绝。
- 只改曲线时 `input` 不解析，`change` 虽写入草稿却未刷新应用按钮。将待应用徽标及按钮刷新统一到草稿写入路径，保持先预览确认后应用；设备事务浏览器核对泵曲线进入实际运行请求，Node 验证预览快照的深复制。
- 测点动作原先被独立监听器和总分派重复处理，正常操作会附带“未识别”提示。四个测点动作改为精确动作路由，功能只执行一次。
- 运行控制浏览器的旧读取方式无法解析配额降级后的 DAG 草稿。测试改用正式 `FluidNetDraftStore.parse`，保留完整状态和历史断言，不放宽产品行为。

## 模块化冷库

```powershell
node tests/browser-refrigeration-modular.mjs
```

单库房从空白冷库画布插入 8 台设备、建立 9 条连接；任意生成实例 ID 均由真实端口连接关联。初始库温 255.15 K；把库房负荷调至 6000 W 后，60 s 末库温为 255.2618344807 K，变化来自真实求解。导出、导入新项目与重载复算后，完整冻结模块定义（含版本／双哈希）相等，108 个数值变量按六位小数对照全部通过。

库温观察量经曲线页选择，SVG 路径含多个实际采样点；HTML／CSV 通过运行归档界面下载，校验设备标识和 HTML 的运行 ID。页面异常为空。日志：`artifacts/interaction-delivery/refrigeration.log`，截图：`artifacts/refrigeration-modular-single-room-*`。本轮没有重跑 `--cascade`／`--equipment` 变体，脚本仍保留其原有参数和断言。

## 相关界面集成

| 命令 | 最终结果 | 日志 |
| --- | --- | --- |
| `node tests/browser-module-catalog.mjs` | 60 项内置目录图标与 8 个参考模块／文档弹窗通过；Snowflake/GitMerge 图标已补齐，Home 使用既有 house 别名；页面异常为空 | `artifacts/interaction-delivery/module-catalog.log` |
| `node tests/browser-device-transactions.mjs` | 曲线单独编辑可确认并进入规范运行请求；库值写入有接受回执，控制器拥有的批次被拒绝；冻结项目 v2 与库新 v3 隔离；页面异常为空 | `artifacts/interaction-delivery/device-transactions.log` |
| `node tests/browser-run-control.mjs` | 后端 stop→cancelled，t=0.7 s、15 帧保留且不再增长；61 趋势帧中30个partial、末帧完整；水箱动态通过；参数批3次写入、2次接受修订、1次整批拒绝；页面异常为空 | `artifacts/interaction-delivery/run-control.log` |

运行控制内嵌的参数批辅助页面已显式加载新 `run-commands.js` 依赖；这是测试宿主与实际应用加载入口保持一致所需的接线，原服务端写入／拒绝断言保持。

上述 6 条浏览器流程顺序执行，每条均已退出成功并关闭其隔离浏览器与服务。语法和差异格式检查通过。它们是本轮相关集成范围，不代表全量浏览器、全量 pytest 或多设备厂家校准。
