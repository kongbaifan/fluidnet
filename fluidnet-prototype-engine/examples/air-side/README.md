# 风系统与冷却塔示例

2026-10-29。全部为可修改、可复算的教学参数，不是现场标定或厂家选型数据。

| 示例 | 规范计算项目 | Studio 导入文件 | 独立判断依据 |
| --- | --- | --- | --- |
| 湿盘管除湿 | [air-coil-wet.project.json](air-coil-wet.project.json) | [原型](air-coil-wet.prototype.json) | 旁通系数在 h/w 空间混合；凝水=m_da×入口出口含湿量差；冷源负荷+凝水焓流=空气焓降 |
| 新回风混合 | [air-mixing.project.json](air-mixing.project.json) | [原型](air-mixing.prototype.json) | 按干空气质量流量分别加权焓和含湿量；新风比例由支路阻力决定 |
| 空气处理机组 | [ahu-wet.project.json](ahu-wet.project.json) | [原型](ahu-wet.prototype.json) | 混合→过滤→表冷除湿→再热→等温加湿→风机→送风；风机工作点满足实际体积流量曲线 |
| 房间送回风系统 | [ahu-room.project.json](ahu-room.project.json) | [原型](ahu-room.prototype.json) | 完全混合房间的水量和能量隐式存储；实际新风与平衡渗透不重复；有送回风和排风支路 |
| 并联风侧设备 | [air-parallel-wet.project.json](air-parallel-wet.project.json) | [原型](air-parallel-wet.prototype.json) | 盘管与过滤器并联分风后混合，出口流股独立于压力边界的输入湿度 |
| 湿空气冷却塔 | [cooling-tower-moist.project.json](cooling-tower-moist.project.json) | [原型](cooling-tower-moist.prototype.json) | 补水=蒸发+飘水+排污；水侧焓降、补排水和空气焓增共同闭合 |

Studio：左侧 **风系统 → 创建风侧示例**。也可在“项目 → 导入原型”载入 `.prototype.json`。文件已清除临时运行 ID 和本机模块路径；Python 模块源码、版本和哈希包含在项目快照中。

规范项目可以直接 POST 到 `/api/v1/solve`；动态运行使用 `/api/v1/runs`，把完整规范项目放入 `project`。房间建议从 `duration_s=120, dt_s=2` 开始。界面参数使用显示单位，规范 JSON 使用 SI，不能把两种文件互换。

```powershell
# 在项目根运行；已启动服务，默认端口 8798。
$airProject = Get-Content -LiteralPath 'examples/air-side/air-coil-wet.project.json' -Raw | ConvertFrom-Json
$airRequest = @{ project=$airProject; mode='steady' } | ConvertTo-Json -Depth 100
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8798/api/v1/runs' -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($airRequest))
```

启用认证时沿用现有 Bearer 令牌。无界面启停、WebSocket 和变量写入可复用 [外部客户端](../external_clients/README.md)，把观察键换成 `Coil.condensate_kg_s`、`Room.state.relative_humidity` 等实际设备键。

输入依据：风机为既有参考模块默认曲线；风管尺寸和长度为教学假设；盘管采用规定表面温度/BF；房间采用固定有效干空气存量；塔采用规定空气流量和接触效能。适用边界与单位见[风侧使用说明](../../docs/AIR_SIDE_USER_GUIDE.md)。
