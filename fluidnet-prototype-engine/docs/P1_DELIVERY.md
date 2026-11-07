# P1 交付记录

日期：2026-11-06。完成本轮约定的两条 P1 主线，按既有模块合同、冻结版本、草稿与显式应用机制开发。没有运行全量测试。

## 开放端口制冷设备组

压缩机与集管、供液泵/阀/集管、冷风机可以分别封装，连接公开制冷剂与热端口后组成完整制冷站。房间和容器仍由宿主系统持有，组内展开后使用已有真实设备方程。SDK 0.10 增加 `composite.refrigeration.open.v1`；schema 1–4 与既有发布版本保持兼容。

从已连接系统封装时保存完整宿主工况。独立验证、版本发布与宿主验收项目均代入当前候选/发布组，验证实际压力等级和热连接。三个组的单独宿主和完整搭站工程位于 `examples/open-refrigeration-groups/`。

后端 41 项定向检查通过，覆盖与手工展开逐帧对照、副本隔离、错端口/工质/子版本拒绝、发布重启、初始化与推进失败诊断以及接受状态回退。浏览器完成三类组发布、9 条公开连接、两个冷风机副本独立改参及导出导入重载后六位小数对照；旧闭合组浏览器回归通过。

使用范围与模型约定见 [开放组设计](OPEN_REFRIGERATION_GROUPS.md)，界面操作和证据见 [开放组浏览器验收](OPEN_REFRIGERATION_GROUPS_UI_ACCEPTANCE.md)。首批针对文档列明的内置设备；不是任意制冷作者模块或跨域热耦合的通用封装器。

## 设备性能资料库

模块页“性能资料库”和设备面板“性能资料”提供 CSV/JSON 导入、单位与有效范围校验、来源/工质/密度/rpm 记录、不可变版本、同参考条件对照和原文件导出。资料保存在现有工作区 SQLite，随数据库备份恢复。

支持泵扬程、风机压升和效率资料；自动建议仅面向已审核算法，不对同名自定义参数推断单位。来源先进入草稿，正式应用成功后才成为当前来源；同点但不同来源也须显式应用。手动改点不冒用原资料。设备选型、保存型号、型号新版本、插入和批量套用均保留对应来源与冻结模块关联。

后端 21 项定向检查通过；浏览器通过实际文件上传、三版资料、曲线对照、原文件字节对照、设计选型、完整型号保存与重载、同点来源切换等流程。教学数据位于 `examples/performance-data/`，明确标注非厂家性能；导入通过不代表数据已获厂家或现场标定。操作、API 与限制见 [性能资料库说明](PERFORMANCE_DATA_LIBRARY.md)。

## 集成检查与复现入口

新增功能相关的前端单元测试、设备应用事务测试及批量型号测试共 36 项通过；8 项合同/OpenAPI 定向门禁通过，包含全部 HTTP 路由响应与导出原始字节媒体声明。修改的 Python 文件通过 Ruff/mypy，前端通过 `npm run check`。生成器检查确保例子与声明一致。

```powershell
npm run test:ui:p1
npm run test:browser:p1
python -m pytest -q tests/test_open_refrigeration_groups.py tests/test_performance_data.py
python scripts/generate_contracts.py --check
python scripts/generate_open_refrigeration_groups.py --check
```

这份记录描述本次定向验证范围，不表示执行过全仓测试。P0/P2 的其他工作未混入本轮。
