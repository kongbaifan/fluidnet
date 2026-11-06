# 性能资料导入教学样例

以下均为项目编写的教学曲线，不是厂家资料、标定结果或设备选型依据。制造商、型号留空；来源填写“项目教学样例，非厂家资料”。所有样例参考转速为 1450 rpm。

| 文件 | kind | 横轴单位 | 纵轴单位 | 参考工质 | 参考密度 kg/m³ |
| --- | --- | --- | --- | --- | --- |
| pump-head.csv | pump_head | m3/h | m | Water | 998.2 |
| pump-efficiency.json | efficiency | m3/h | % | Water | 998.2 |
| fan-pressure.csv | fan_pressure | m3/h | kPa | Air | 1.2 |
| fan-efficiency.json | efficiency | m3/h | % | Air | 1.2 |

导入时分别使用独立 ID，如 `teaching-pump-head` 与 `teaching-pump-efficiency`。首次保存期望末版为 0；后续同 ID 修订追加版本。CSV 使用默认 `flow,value` 列名，范围可留空使用全曲线范围。进入 `design_pump` 或 `design_fan` 设备草稿后分别预览应用匹配的效率与性能资料，再重新选型；曲线参考 rpm 对应 `speed_ratio=1`，不是自动推定设备实际转速。

完整合同和兼容限制见 `docs/PERFORMANCE_DATA_LIBRARY.md`。
