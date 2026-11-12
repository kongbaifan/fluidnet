# 底层扩展参考工程

这些工程可通过项目 JSON 导入，或由 `GET /api/v1/examples/{name}` 获取。设备几何、UA、泵曲线和控制阈值为自定义参考输入；没有厂家或现场标定数据。

| 文件 | API 示例名 | 用途 |
| --- | --- | --- |
| `parallel-network.project.json` | `refrigeration-network` | 两库不同管长、曲线泵、供液和湿回气阻力共同决定分流 |
| `inventory-network.project.json` | `refrigeration-network-inventory` | 管内持液单元的质量与内能参加隐式积分 |
| `cold-store-processes.project.json` | `refrigeration-cold-store-processes` | 库房热湿、货物冻结、霜层、热气融霜和油路 |
| `standby.project.json` | `refrigeration-standby` | 两台压缩机、两台泵，运行反馈与实际流量触发备用切换 |
| `author-constitutive.project.json` | `refrigeration-author-constitutive` | schema 5 的 Python 压缩机/冷凝器本构和平台库存联算 |

在项目目录运行 `python scripts/generate_foundation.py --check` 校验保存示例；用 `python scripts/validate_foundation_reference.py` 生成公开关联式和层流解析极限校核报告。来源与温区记录在 `reference-sources.json`。默认管网/过程示例建议先运行 0.1–1 秒，输出间隔 0.1 秒；带持液与多个过程状态的隐式联算成本明显高于原集总案例。

备用示例的 `duty-failure` 工况在 0.4 秒把工作泵转速、工作压缩机载量置零，控制器根据真实流量切换备用。0.2 秒确认期和安全阈值专为短时验收设置；不能直接作为真实机组启停保护设定。第二次设备故障或高压/低液位触发锁停，恢复需要新建会话或显式修改控制逻辑。

网页使用路径：运行记录 → 查看档案 → 从快照续算 → 输入更晚的终止时刻。系统创建独立项目副本并暂停恢复，可使用原有单步/继续按钮，保留旧项目的后续修改。

完整会话续算由后台动态运行提供：先创建 `POST /api/v1/runs?background=true`，运行记录暴露 `checkpoint_available` 和 `checkpoint_time_s`。重启后原运行标记 `interrupted`，调用 `POST /api/v1/runs/{id}/resume`，正文 `{"start_paused":true,"duration_s":10}`，得到新 run id 并延续物理时钟。`duration_s` 是原时钟上的终止时刻；数值实现改变时拒绝旧快照。快照包含库存、PID/脚本采样时钟、模块已接受状态和积分器热启动数据，不能用旧历史曲线替代。

详见 [总验收记录](../../docs/FOUNDATION_COMPLETION.md)、[冷库过程模型](../../docs/COLD_STORE_PROCESSES.md)。
