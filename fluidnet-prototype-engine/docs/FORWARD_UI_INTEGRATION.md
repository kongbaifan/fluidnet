# S7 自建暖通系统综合界面验收

2026-11-06。通过真实界面组合S1/S2设备组库、S3多选复制、已交付批量参数/面板配置、S4系统结果解释及保存报告。本记录是开发参考场景，不代表厂家标定或现场项目校核。

## 已完成流程

脚本`tests/browser-forward-integration.mjs`在隔离模块库与工作区服务内执行：

1. 从模块页“设备组与选型”创建`group_pump_branch`参考项目，实例前缀为`System`。
2. 多选设备组与两个外部压力边界，预览并复制全部内部连线，得到两个独立回路的设备组副本（`System-Equipment`与自动生成`D-23`，编号由本次工作区决定）。
3. 批量将两个组的公开`Pump_speed_ratio`改为0.9，逐台预览后应用。
4. 为当前项目的组设备配置转速滑块和实际入口流量分组；配置保存在项目模块快照，物理定义不变。
5. 真实运行完成；从运行记录打开“系统结果解释”，确认报告属于该冻结运行并包含实际实例ID。
6. 通过真实下载按钮取得HTML及CSV，两者包含本次运行ID和实例变量。
7. 导出单项目，在新项目副本导入，保存、刷新后重新运行。所有数值变量逐一比较到6位小数一致，面板分组配置保留。

pageerror为空。未通过evaluate注入应用状态，读回工作区使用真实API。仅运行本脚本与相关S3定向检查，没有执行全量浏览器链。

## 证据与边界

- `artifacts/forward-integration.json`记录两次运行ID、两个实际组ID、报告种类和错误列表。
- `artifacts/forward-integration-inspection-1080p.png`与`forward-integration-final-1080p.png`均为1920×1080、DPR1，已目视检查。
- S3的30/100/300实例编辑/保存/导入/刷新与容量记录独立见[LARGE_PROJECT_EDITING](LARGE_PROJECT_EDITING.md)。本条是功能组合验证，不将单回路的性能外推到多物理域。
- 本记录覆盖暖通水侧设备组整链；制冷持液/多高度容器和跨域储热的专门组装、物理账与失败回滚仍由相应S5/S6验收记录说明。
- 新本地DAG格式由`FluidNetDraftStore.parse`读取；本轮新增浏览器脚本的本地主键读取已同步解码。规范Project与导出项目JSON保持原格式。

## S6-3 完整闭合制冷设备组

另执行`tests/browser-refrigeration-group.mjs`，通过原生界面创建R134a泵供液参考项目，选中整个闭合组封装为`closed_refrigeration_pack`，发布v1。合同声明`composite.refrigeration.v1`（SDK0.9.0），无公开外端口；发布试算继承源项目工质，不能默默换成Water。目标空白项目在介质设置中显式改为发布记录所用的R134a名称与any相态；该UI测试使用精确工质名；随后后端增加纯工质HEOS前缀等价识别并通过定向检查，不合并不同后端或混合组分。

在空白冷库画布插入两个副本（本次自动ID为`D-24/D-25`），真实运行的库温初始相同。仅提高第一组公开库房负荷到7kW后再次运行，两组温度出现独立响应。导出单项目、导入新副本、保存刷新后，全部数值变量按6位小数比较一致，设备组总览真实采样结果非空，pageerror为空。冻结子定义和SDK能力在导出文件中保留。

证据：`artifacts/refrigeration-group-ui.json`及`artifacts/refrigeration-group-two-copies-1080p.png`，后者已经目视检查。此验证只覆盖已支持的完整内置制冷闭合组、单一项目工质；不宣称任意开放制冷端口、部分制冷组或任意混合工质组合已支持。
