# 自主建模首批验收：PF-0 / PF-1

日期：2026-10-30。起始代码基线 `802b4c5`，分支 `claude/chiller-air-loop`。本次完成 [扩展计划](PLATFORM_EXTENSION_PLAN.md) 的前两个工作包；后续 RF-0 至 RF-4 与 PF-2 尚未完成。

## 已交付

- **PF-0**：[按执行范围核对的能力清单](PLATFORM_CAPABILITIES.md)，覆盖单相、湿空气/风水、库房热节点、冷库、集总制冷站和热耦合；每项有源码和验证入口，并区分物理限制与作者接口缺口。模块向导及开发指南说明现有模板适用范围。
- **PF-1**：从空白画布创建自定义阻力项目，作者配置预期值并发布，实际接线、单位换算、PID 绑定、曲线与 CSV、单模块和组合版本升级/回退、组合导出导入重载及历史复算。测试不向应用写入伪造状态，也不使用内置示例项目冒充自建流程。

## 修复的问题

1. **自定义设备没有默认概览曲线**：原适配器固定读取 `P1/V1/V2`，页面仍显示这些编号。现在从实际设备/通路选择最多三条流量，趋势请求、概览值、图例和出口压力/温度使用相同绑定；历史档案从冻结项目定义重新绑定。缺失值保持缺失。
2. **设备温度串用了项目概览值**：设备结果面板现在读取自身流体出口温度；空白项目也不再预置引用 `V1` 的控制脚本。
3. **组合能计算但不能导回项目**：画布生成的 `D-24` 子实例产生 `D-24_in0` 公开端口。后端接受这个标识，前端却用旧的 Python 名称规则验证展示名称，报“端口定义不合法”。现在契约生成的名称按展示字段校验，保留规范端口/变量 ID、版本及双哈希，不通过改名破坏引用。
4. **曲线页 CSV 缺少实际观察变量**：导出列现包含实际变量标识和显示单位，并包含用户添加的曲线；历史导出读取所选运行的绑定。此处为曲线页下载格式调整，后端报告接口不变。

## 真实作者流程与结果

新增 [browser-platform-authoring.mjs](../tests/browser-platform-authoring.mjs)，使用隔离的临时服务、模块仓库和工作区：

1. 创建 `pf1_resistor`，阻力系数默认 12，直径引擎值 0.04 m、显示值 40 mm；配置压降 130000 Pa 的预期，三个测试工况通过，然后发布 v1。
2. 新建空白项目，通过模块卡片插入两个压力边界和阻力设备，使用画布生成的 `D-23/D-24/D-25` 编号；手工接线并设置 250/120 kPa 边界。
3. 配置 PID 的真实设备参数与测量引用，添加入口流量曲线。根据独立关系 `m = A × sqrt(2ρΔp/K)` 得到参考流量 **5.844280689925339 kg/s**，真实 Worker/网络结果 **5.84428068992534 kg/s**。CSV 的列标识使用 `D-24`。
4. 编辑算法使有效阻力系数乘 4，发布 v2；项目显式升级后流量减半，控制引用保留；回退 v1 后恢复原值。
5. 从画布封装 `pf1_assembly`，发布组合 v1；虽然模块库已有子模块 v2，组合仍固定子模块 v1。插入第二个空白项目并计算，与手工项目结果一致。
6. 组合显式采用子模块 v2，更新内嵌定义和双哈希并发布组合 v2；组合项目升级后流量减半，回退组合 v1 后恢复。导出单项目、作为副本导入、保存重载再计算，结果仍为 **5.84428068992534 kg/s**。
7. 在组合副本项目打开原始阻力项目的历史运行，曲线仍显示原来的 `D-24`，没有改绑到当前组合的 `D-30`；原运行保留子模块 v1。

界面截图使用 1920×1080、DPR=1。结果摘要、命令、日志哈希和源码哈希见 [验证索引](platform-extension/results/pf01-validation.json)。截图及视口元数据位于 `artifacts/platform-extension/pf1/`。

## 验证范围

| 检查 | 结果 |
| --- | --- |
| 模板、版本、迁移、组合、组合物理、作用范围后端回归 | **43 项通过**；本轮开始时执行，此后没有修改后端或 SDK |
| 前端合同与概览回归 | **10 项通过**，包括自定义 ID、多通路冻结定义、缺失值、已保存通路覆盖，以及原热耦合界面合同 |
| 首批作者流程 | 新浏览器脚本通过，含独立公式、单模块/组合版本切换、CSV、组合导入复算及跨项目历史显示 |
| 既有浏览器回归 | `browser-smoke`、`browser-workflows`、`browser-archive-migration`、`browser-module-workflow` 通过；含四类模板、作者预期值与失败修正 |
| 前端语法 | `npm run check` 通过 |

共五个浏览器脚本通过，页面脚本错误均为 0。修复前的固定编号和组合导入失败用于定位问题，不计作通过结果。没有重跑全量后端、完整浏览器链或覆盖率；历史 1581 项全量结果不作为本次新增流程的证据。

## 操作与复现

普通使用入口是“模块 → 新建模块 → 配置工况与预期值 → 保存新版本”，再从“项目 → 新建项目 → 空白画布”插入和连接设备。组合入口在建模工具栏“封装设备组”；项目工具栏“模块版本”可预览升级和回退。完整说明见 [模块开发指南](modules/DEVELOPMENT_GUIDE.md)。

在 `fluidnet-prototype-engine` 目录执行：

```powershell
$env:PYTHONPATH='backend'
$env:PYTHONUTF8='1'
python -m pytest -q tests/test_module_templates.py tests/test_module_versions.py tests/test_module_migrations.py tests/test_module_composites.py tests/test_module_composite_physics.py tests/test_module_scope.py
npm run test:ui
npm run test:browser:platform-authoring
node tests/browser-smoke.mjs
node tests/browser-workflows.mjs
node tests/browser-archive-migration.mjs
node tests/browser-module-workflow.mjs
npm run check
```

## 后续交接

下一包为 **RF-0：制冷设备合同与可行性验证**。需用真实 Worker 证明同一候选状态上的等焓节流、质量/能量流股汇总、接受/失败路径及调用成本，再确定 SDK 扩展合同和性能预算。本批没有开放制冷站 Python 设备，也没有放开热耦合液体侧 Python、风水储热或机组启停。
