# 制冷作者模块示例

设备算法见 [公共 SDK 节流阀](../../modules/isenthalpic_throttle/README.md)。它支持线性和等百分比开度特性，平台负责流股守恒及累计通过质量。

可直接在 Studio 的“项目 → 导入单项目”选择：

- [author_station.json](author_station.json)：NH₃/CO₂ 完整制冷站，保留五个 PID 和上层控制脚本，以作者模块替换节流阀。
- [author_station_small.json](author_station_small.json)：使用同一模块的较小单回路制冷站。

两份文件都是规范 Project JSON。导入会生成画布、显示单位、固定模块快照、控制及工况，默认运行 60 s；在“设置 → 求解”调整时长和输出步长。实例使用 `Expansion-Custom` 和 `Condenser-Custom`，用于展示项目编号可以不同于内置案例。

原始模块固定为 v1。可在模块库选择“新建模块 → 制冷等焓节流阀”编写自己的版本；规范 JSON 中的 `modules`、相应实例的 `module_id` 和 `package` 共同固定作者模块，之后用单项目导出保留画布与观察配置。修改已有模块并保存新版本后，项目通过“模块版本”显式预览和采用；仅发布不会改动已有项目和运行。

示例包含两个工况：“初始半开度”只覆盖初始开度，“等百分比特性”只覆盖开度特性。完整站的液位 PID 会在运行中继续控制开度，因此扫描初始开度不代表保持固定开度；比较设备能力时可在“批量”扫描额定 Kv，或按工程目的调整控制器。

在“记录”页载入服务端档案后，可下载 HTML 报告与报告 CSV；历史曲线同样使用运行时冻结的模块与结果。批量页面保存完整输入快照，项目后来升级或回退不会改变旧批次。

再生成或检查样例（项目根目录）：

```powershell
python scripts/generate_refrigeration_author_example.py
python scripts/generate_refrigeration_author_example.py --check
```

`rf0_throttle.py` 是 RF-0 历史实验运输，不能作为正式项目模块；`sdk_throttle.py` 和对应 manifest 是 RF-1 协议样例。当前作者入口使用 `modules/isenthalpic_throttle`，运行边界与操作详见 [RF-2/RF-3](../../docs/REFRIGERATION_MODULE_EXECUTION.md)及[RF-4](../../docs/REFRIGERATION_PROJECT_ACCEPTANCE.md)。
