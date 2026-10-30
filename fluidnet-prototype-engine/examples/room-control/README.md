# 房间自动温控示例

三个 `.project.json` 文件可从“管理项目 → 导入单项目”载入。它们包含完整三回路、模块源码快照、PID 及必要的 Python 阶跃脚本，不依赖原机器上的模块目录。

- `room-temperature-control.project.json`：初始 30°C 降到 26°C。
- `room-control-load-step.project.json`：600 s 时室内显热负荷由 5 kW 增至 8 kW。
- `room-control-setpoint-step.project.json`：600 s 时目标由 26°C 改为 25°C。

导入后在“湿空气设置”选择动态计算，时长 2400 s、输出步长 30 s。通过“创建风侧示例”创建时，会自动设置这两个运行参数。

所有参数均为可复现工程假设，控制与模型边界见[中文使用说明](../../docs/ROOM_TEMPERATURE_CONTROL.md)。再生成：

```powershell
python scripts/generate_room_control_examples.py
python scripts/generate_room_control_examples.py --check
```
