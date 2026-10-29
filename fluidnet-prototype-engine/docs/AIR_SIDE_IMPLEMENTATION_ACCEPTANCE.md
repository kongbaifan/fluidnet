# 风侧 W0–W9 实施与验收

日期：2026-10-29。基线 `348f104`，分支 `codex/development-consistency`。本轮获授权实施完整计划、执行验证并分批中文提交。以下记录基于真实源码与执行结果。

## 实现范围

| 工作包 | 实现 |
| --- | --- |
| W0 | 核对已修复的支路数组，删除旧湿空气热力分支与 1% 能量容差，补跨协议状态传递和独立边界账 |
| W1 | CoolProp 湿空气服务、ptw/phw 往返、零含湿量露点空值、明确干空气/混合物字段、SDK 0.6.0 |
| W2 | 干空气连续性、入口总质量压损和导数因子、h/w 联合迭代、真实吸收边界、反流/停滞/无参考诊断 |
| W3 | 表冷器干湿切换、h/w 旁通关系、凝水焓、等焓/等温加湿及饱和限幅、接受子步累计 |
| W4 | 混合箱、过滤器、再热、风机实际风量工作点、四个新版官方模块、完整 AHU 示例 |
| W5 | 房间固定有效干空气存量、隐式热湿存储、负荷/渗透、真实稳态、拒绝子步回滚 |
| W6 | 湿空气接触效能塔、蒸发/飘水/排污/补水、浓缩倍数、独立能量与水账、累计量 |
| W7 | 运行前目录、运行冻结目录、物性/状态图接口、SQLite 元数据、CSV/HTML、历史与失败结果 |
| W8 | 1920×1080 风系统页、设备参数、RH→w 草稿、过期保护、状态图、四运行对比、批量扫描 |
| W9 | 旧项目显式迁移及备份、原模块版本保留、六个规范与原型文件、合同及文档同步 |

## 已执行的验收映射

| 设计用例 | 可复现证据 |
| --- | --- |
| A01–A05 | `tests/test_moist_air_properties.py`：27 点物性网格、边界、单位与缓存保护，共 38 项 |
| N01–N08 | `test_moist_air_transport.py`、`test_moist_air_phase2.py`：独立全网账、m>n 并联、不同 w 混合、反流、无供气闭环、零流量和耦合 |
| C/H/U | `test_air_devices.py`、湿空气输运测试、`browser-air-side.mjs` 的完整 AHU 运行 |
| R01–R05 | `test_air_room.py`：无通风真实网络、恒定散湿、一阶指数对照、dt 减半、拒绝子步、参数事务、失败历史 |
| T01–T04 | `test_cooling_tower_moist.py` 与既有 `test_bsl_modules_p1.py`：独立流股账、飘水限制、旁通/不可行点、原塔兼容 |
| P01–P03 | `test_air_module_protocol.py`：真实单/批量 Worker 四阶段、独立验证台、强制总质量流量；既有模块/控制事务回归 |
| I01–I03 | `test_air_api_reports.py`：REST/WS/CSV 同 sequence/revision、重启元数据、禁止报告重新编译、裁剪历史累计量 |
| I04 | `browser-air-batches.mjs`：三档 BF 批次、凝水/温度趋势、保存重载；既有批次上限、取消及部分失败测试 |
| F01–F04 | `browser-air-side.mjs`：六个示例、参数应用、过期提示、运行对比、延迟旧响应切换、保存/重载、规范往返 |

## 数值和界面证据

- 典型塔例：约 2.7696 kg/s 循环水，37°C→27.5866°C，排热约 108.973 kW；蒸发 0.041478 kg/s、飘水 0.000554 kg/s、排污 0.020185 kg/s、补水 0.062217 kg/s，浓缩倍数 3；独立能量残差约 4.1×10⁻⁷ W。
- 物性与设备误差门槛和独立计算写在测试中；没有通过扩大守恒容差掩盖物理口径差异。
- 本地截图：`artifacts/air-distribution-1080p.png`、`air-psychrometrics-1080p.png`、`air-comparison-1080p.png`、`air-tower-1080p.png`、`air-batches-1080p.png`；各有实际 viewport/DPR 的 JSON 旁证。
- 首轮全量：1522 passed、11 failed，覆盖率 90.96%。失败包括旧版风机/目录断言和新增协议适配问题；修复后相关 88 项定向回归全部通过。最终全量结果在完成后填入下节，不把首轮失败计为通过。

原始日志摘要与 SHA-256 见 [validation.json](air-side-detailed-plan/results/validation.json)。

## 最终门禁

- `python -m pytest --cov=fn_engine --cov-report=term -q --tb=short`：**1543 passed**，覆盖率 **91.04%**（门槛 85%），耗时 1373.75 s；日志 `artifacts/air-final-pytest.txt`。
- 随后新增关闭热力时的塔编译门禁，`test_cooling_tower_moist.py` **5 passed**；不改变任何有效输入的数值计算。
- ruff 全范围通过；mypy 79 个源文件零错误；前端语法检查通过。
- 六组规范/原型文件的编译参数、连接和工质逐项一致；不只做 JSON 解析检查。
- `npm run test:browser`：**23 个浏览器脚本与 6 项界面合同测试通过**，日志 `artifacts/air-final-browser-2.txt`。
- `python scripts/generate_contracts.py --check`：**85 个合同文件一致**。
- 后续修正房间初始接受态、零风量塔温度别名后，热湿/房间/塔/协议/API/原热力 **116 项专项通过**，日志 `artifacts/air-final-numerics-recheck.txt`。
- 最终水耗卡片去重与单设备布局由两个风侧浏览器脚本再次验证，见 `artifacts/air-final-ui-recheck.txt`。

## 与设计稿的实现落点差异

- 复用既有 `CompiledNetwork.port_nodes/branches`，新增 `air_rooms/air_room_step`，未重复建立平行的拓扑对象。
- 元数据直接保存到既有运行 JSON，不增加不必要的数据库列或数据库迁移。
- 新增 `POST /air/migrations/preview`，使物理口径迁移与现有模块版本升级各有明确入口；共五条风侧新端点。
- 报告与目录共用 `air_variables.py`；动态候选累计量集中在 `air_ledger.py`。
- 原型参数支持既有别名和合同 ID，但同一参数同时用两种名称会拒绝，避免歧义。

## 适用边界

这是低速单相风网与教学热湿设备模型。湿盘管的冷源为规定 ADP，未与真实水/制冷剂盘管联立；房间为完全混合固定有效存量；塔为规定空气流股的接触效能模型。VAV/静压控制、课程产品封装、完整可压缩流、结霜/CFD、DX 后续专项以及已取消的打包发版、24 小时稳定性与现场校核均未恢复。
