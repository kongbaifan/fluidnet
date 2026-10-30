# RF-4：制冷作者项目、版本和结果闭环

日期：2026-10-30。状态：**RF-4 已完成；PF-2 全阶段回归也已通过。**

本阶段接续 [RF-2/RF-3](REFRIGERATION_MODULE_EXECUTION.md)，使用完整 NH₃/CO₂ 站及自定义实例 ID 验证作者节流设备的项目保存、规范/原型交换、版本升级与回退、历史报告和批量比较。物理范围仍为纯集总制冷站的无独立储量等焓节流角色。

## 使用入口

“项目 → 导入单项目”现在接受单项目文件、完整原型和规范 Project JSON。规范文件先经过后端项目校验，再转换画布、参数显示单位、工质配置、PID、控制脚本、事件、工况、草稿、三组库值与模块快照。当前画布仍最多八页、每页 64 台设备，跨画布连接和超过三组设备库值明确拒绝。

“管理项目 → 导出此项目”保留 Studio 项目、模块快照和曲线；新增“导出计算项目”导出规范 Project。规范格式本身不含运行时长和输出间隔，重新导入默认采用 60 s 动态运行，需按场景调整。

交付 [完整站](../examples/refrigeration_extensions/author_station.json)和[小型站](../examples/refrigeration_extensions/author_station_small.json)，两者均使用同一公共 SDK 模块。源码和操作见[示例目录](../examples/refrigeration_extensions/README.md)。

## 修复与行为

- 版本升级保留工况的局部参数覆盖，不把未填写的文本参数或其他默认值塞入工况；未升级设备的显示单位保持原值。草稿、库值、控制引用和已绑定版本随升级一起保存。
- 导入的内置设备快照不会被错误绑定为含空哈希的 Python 包；Python 作者设备继续固定版本、源码哈希与定义哈希。
- 通用概览按声明的制冷角色识别流量及出口状态，使用真实实例编号生成曲线，不依赖 EV1。
- 制冷站报告的压力和执行器曲线按项目中的容器、控制器与设备生成；作者结果、CSV 列及版本表来自冻结合同，包含声明的累计通过质量。报告不执行作者源码。
- 旧批次记录自己的模块版本、控制脚本和完整项目输入快照；后来发布、升级、回退或重启都不改变其结果和比较曲线。CSV 保留原有列顺序，用“输入快照”标识对应批次，模块双哈希可在批次元数据中查阅。

完成运行后，从“记录 → 刷新档案 → 查看运行记录”可下载该次运行的 HTML 报告和报告 CSV。入口按所选归档的执行域判断，导入的自定义制冷站也可使用；按钮不会绑定当前正在编辑的项目或模块版本。

单项目导入为副本时，来源设备编号和控制引用保留，项目 ID 与其曲线归属更新。完整原型从其活动项目读取一份项目，已有其他项目保留。

## 验收场景

后端接口检查覆盖：发布 v1 → 保存站内项目 → 建立 v1 批次 → 发布及显式采用 v2 → v2 运行 → 启动早先 v1 批次 → 回退项目修订 → 复算 → 服务重启 → 读取旧帧和报告。报告读取时禁止创建 Worker，证实它没有重新运行当前源码。

浏览器流程使用自定义作者模块、`Expansion-Custom` 节流设备和 `Condenser-Custom` 冷凝器；检查 1→2→1 版本切换、局部工况、控制不变、曲线绑定、两种文件导出/导入、批量 Kv 扫描及服务重启。界面与报告采用 1920×1080、DPR=1 验收。

最终检查、截图及源码哈希见 [RF-4 验证索引](platform-extension/results/rf4-validation.json)。PF-2 全量回归与交付状态见 [阶段验收](PLATFORM_EXTENSION_ACCEPTANCE.md)。

复现命令：

```powershell
$env:PYTHONUTF8='1'
python -m pytest -q tests/test_refrigeration_projects.py --tb=short
npm run test:ui
npm run test:browser:refrigeration-projects
python scripts/generate_refrigeration_author_example.py --check
```
