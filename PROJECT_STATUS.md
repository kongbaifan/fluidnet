# 项目状态 · 2026-10-08

按已确认方案完成 FluidNet Studio **v0.2.0**：结合 Baselu 教程中的模块接口、型号复用和单步验证流程，保持独立项目格式与求解器，完成实现、回归验证、文档和 Windows 便携包。

## 可交付文件

- `dist/FluidNetStudio-Windows-x64-0.2.0.zip`：73,598,513 字节，约 70.19 MiB。
- `dist/FluidNetStudio-Windows-x64-0.2.0.zip.sha256`：完整性校验文件。
- `dist/portable/0.2.0/FluidNetStudio/FluidNetStudio.exe`：可直接运行的解压目录。
- `README.md`、`docs/USER_GUIDE.md`、`docs/DEVELOPMENT.md`：启动、组合/型号操作、迁移与开发说明。

ZIP 的 SHA-256：

```text
68bec9766c6001ae48d2a1f60bcc3cbb42a7db872043e6a668e5e2da089b3192
```

完整解压后双击 `FluidNetStudio.exe`，默认访问 `http://127.0.0.1:8765`。若旧服务仍占用端口，可用 `.\FluidNetStudio.exe serve --port 8768 --open` 启动新版的独立工作区。程序包包含运行依赖、网页、六套项目示例和三套组合型号，没有包含正式或测试工作区数据。

## v0.2 实现

| 能力 | 已完成内容 |
| --- | --- |
| 单层组合设备 | 主画布显示单个设备，双击进入内部画布；移动、复制、删除、撤销和重载保留成员关系；可展开或解散 |
| 接口配置 | 稳定端口/参数 ID、可编辑显示名称、一对一映射、已接外部管路的端口保护；内部连线映射到真实管网 |
| 型号版本 | 创建、编辑、历史版本、JSON 导入/导出和归档；已插入实例独立；预览后手动应用，保留有效工况/曲线/控制引用 |
| 原子版本应用 | 稳定成员 ID、外连接口重新绑定；失效引用拒绝整次应用；名称变化也进入接口差异预览 |
| 独立验证台 | 型号测试边界、稳态与慢动态、暂停/继续/单步/停止、残差、曲线和结果；独立项目快照及运行记录 |
| 内置型号 | 泵阀组合、双侧换热机组、水箱调节单元；验证模板不混入主项目，换热器两侧水配置保持独立 |
| 迁移 | 项目 schema 2；有效 v0.1 项目和草稿读取时升级；SQLite 升级前自动备份；旧型号保留 ID 成为 v1；无效旧型号提供修复提示 |
| 便携构建 | 按版本隔离输出，遇到用户 workspace 改用带时间戳的目录；生成版本化 ZIP 和 SHA-256 |

## 验收结果

- `npm run check`：Python 语法和 TypeScript 检查通过。
- `npm test`：42 项后端测试通过；重新构建网页后，10 项浏览器测试通过。
- 后端覆盖封装/展开前后结果一致、介质和控制引用复制、版本应用原子性、曲线有效性、外接口重绑定、三套独立验证模型、旧库备份及版本冲突。
- 浏览器覆盖原有五项工作台流程，以及组合移动/复制/删除/恢复、内部插入元件和重新连线后发布、显式版本应用和回退、独立动态单步、型号 JSON 交换及无效旧模板展示。
- 页面异常检查通过；组合工作台、组合内部画布及独立验证窗口截图已查看。
- `npm run build -- --portable` 成功，`npm run smoke:portable` 的 12 项检查全部通过。
- 打包验收从中文及空格路径解压后执行，子进程移除 Python 搜索路径，PATH 仅保留 Windows 系统目录；检查命令行、网页、冻结计算进程、三种导出、WebSocket、动态单步/停止/曲线、模板版本应用与归档、重启后的数据恢复。
- ZIP 共 230 个文件，包含 6 套 schema 2 项目与 3 套组合模板。4 份文档/锁定依赖文件及 3 个网页文件与当前构建源文件一致，校验和匹配。

验收证据：`.cache/qa/portable-smoke.json`、`.cache/qa/portable-contents.json`、`.cache/qa/build-portable.log`、`.cache/qa/modules-workbench.png`、`.cache/qa/module-internal.png`、`.cache/qa/module-bench.png`、`test-results/.last-run.json`。

## 用户数据与升级

旧版 `dist/portable/FluidNetStudio/` 及其中的用户 `workspace` 保留，本轮未启停用户的旧应用。旧版 ZIP 的 SHA-256 仍为 `9100c49752a153531bbf35ae6044ef9488b0b9a5af32bc15e1fc5d0ef6f2f7fe`。本轮源码修改前的备份在 `.cache/v02-backup/source-20261008-163630.zip`。

迁移正式数据时，先保存浏览器草稿并停止旧服务，保留完整工作区副本，再将 `workspace` 复制到新版旁或通过 `--workspace` 指定目录。新版会自动备份旧数据库后升级；两个版本不要同时使用同一工作区。回退时使用升级前副本。测试使用 `.cache/e2e-workspace` 和 `.cache/portable-smoke`，没有迁移用户工作区。

## 当前边界

支持单相纯液态水、稳态水热耦合和设备慢动态；自定义设备通过参数、性能曲线与单层内部管网组成。没有嵌套组合或用户算法代码执行。气体、蒸汽、制冷剂、混合物、水锤和相变求解仍属后续范围。1000 个元件、64 条曲线为结构上限，尚未做相应规模的性能验收；可继续开展外部基准对照和较大水网性能测试。

工作区没有 Git 仓库或 CodeGraph 索引。
