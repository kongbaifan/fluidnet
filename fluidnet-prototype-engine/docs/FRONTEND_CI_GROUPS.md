# 前端浏览器分组与覆盖门禁

2026-11-07 增量：清单现为 **84 次调用、57 个可执行文件、9 组、3 个辅助文件**。新增 `canvas-performance-live`（canvas组）和 `equipment-assembly:standard-plant`（equipment-hvac组）；两组调用数分别为8和16。`interaction` suite 汇集本轮7条相关入口。以下82次调用表为2026-11-06首次分组记录，当前执行清单以脚本 `--check/--list` 输出为准。

2026-11-06。将浏览器命令集中到 `scripts/browser-groups.json`，由 `scripts/browser-groups.mjs` 生成执行计划和CI矩阵。原SDK与后端门禁保持原有命令，培训功能未加入。

## 清单与执行范围

当前登记57个可独立执行的浏览器文件，共82个带参数的调用，分为9组。相同脚本的不同参数是不同用例，例如 `refrigeration-modular` 的普通、复叠、设备变体，以及23个设备组装输入。参数不通过shell拼接执行。

| 分组 | 调用数 | 范围 |
| --- | ---: | --- |
| smoke | 5 | 固定跨域：基础求解、项目工作流、模块工作流、风水冷水机组、模块化冷库 |
| workspace | 10 | 运行控制、PID、持续运行、多工质、认证、保存、控制脚本、迁移、批量工况及参数事务 |
| authoring | 6 | 平台/模块作者流程、模块目录、自定义关系与断言边界 |
| hvac | 8 | 加热器、风系统、风批量、温控和机房单页/多页 |
| refrigeration | 12 | 冷库、热耦合、制冷作者/项目、模块设备变体及闭合/开放组 |
| workflows | 11 | 设备面板、批量、选型、设计库、系统解释、失败复现和性能资料等 |
| equipment-hvac | 15 | 水/风侧设备组装项目及recipe |
| equipment-refrigeration | 8 | 性能压缩、多冷风机、两级、融霜、流股和DX组装recipe |
| canvas | 7 | 工程结果图层、作者布局、画布交互测量、通路追踪、规模编辑、跨页及设备浮窗 |

三个辅助文件显式豁免：`browser-server.mjs`、`browser-viewport.mjs`、`browser-module-assertions.mjs`。断言边界和参数批量脚本虽然也被其他流程调用，但有独立命令入口，已单独登记。`browser-*.test.mjs` 是Node单测，不作为浏览器入口重复执行。

`--check` 检查每个浏览器文件有归属、所有用例/组/suite引用存在、没有重复调用、所有recipe路径存在，新增未登记的脚本会失败。现有 `test:browser:*` 名称作为suite别名保留，其成员仍来自同一份清单，不再维护多条独立命令链。

## 本地使用

```powershell
node scripts/browser-groups.mjs --check
node scripts/browser-groups.mjs --list --group canvas
node scripts/browser-groups.mjs --list --suite p1
node scripts/browser-groups.mjs --matrix
npm run test:browser:canvas
node scripts/browser-groups.mjs --run --case smoke
```

无 `--run` 时只检查/列出，不加载Playwright或执行浏览器文件。`npm run test:browser` 保留完整前端单测与全部浏览器入口；本次没有运行该完整入口。局部suite不自动附加其他测试，实际调用列表可用 `--list` 查看。

## CI行为

根目录 `.github/workflows/ci.yml` 新增静态/单测准备job，由清单动态生成浏览器矩阵；9组最多同时运行3组，组内顺序执行，每个原脚本继续使用既有 `browser-server.mjs` 的隔离目录/端口，不新增服务管理器。

所有PR仍运行全部登记组，固定smoke始终包含在矩阵内；本轮先解决原主链遗漏新分组的问题，没有仅按路径跳过集成检查。后续若增加影响面筛选，应让共享前端/合同/求解变更回退完整覆盖，并保留固定跨域冒烟。

每个失败调用最多重试一次；重试后成功仍显示warning，永久失败使整个组失败，但会继续记录组内其他独立用例。默认本地执行不重试。各组证据单独上传，保留7天；重试日志保留两次结果。结束时汇总job继续使用原 `frontend (Node 24 + Edge)` 名称，只有静态/单测和全部浏览器组成功才通过，防止旧required-check名称变成只检查静态代码。

## 本轮验证

清单校验、矩阵与suite dry-list、Node单测和语法检查通过。单测覆盖漏登记拒绝、缺recipe、重复调用、helper豁免、参数变体、选择去重、重试与永久失败、spawn失败/退出码，以及无shell的argv/环境传递；没有运行全量浏览器或pytest。远程GitHub Actions尚未由本轮验证，矩阵配置不等于远端全部通过。
