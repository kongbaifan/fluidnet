# 无界面运行与热耦合收尾验收

日期：2026-10-27。基于 master `e5a90ce` 的工作区改动，范围为本轮确认的无界面运行接口与制冷站／二次液体回路热耦合。

## 已交付

- `serve --headless` 与 health 模式报告；`POST /api/v1/projects/{project_id}/runs` 固定保存修订和工况，保留模块／控制脚本快照与归档关联。
- Python / JavaScript 客户端及真实 HTTP/WebSocket 联调：认证、上传项目、启动、订阅、变量写入、暂停／继续、停止、Worker 回收、服务重启读档。WebSocket 已纳入固定版本运行依赖。
- 饱和制冷剂容器与无储量液体回路的盘管热耦合，包含物理一致的水／30% 乙二醇设计点、严格稳态平衡与动态扰动。
- 项目页“制冷站热耦合”入口、工况／UA 编辑、指标与曲线；保存／重启／复算及按保存项目运行逐变量一致。完整工质配置与求解选项保留。
- JSON Schema、OpenAPI、API／数据合同／操作说明同步，共 67 个生成契约文件。

收尾中修复了泵曲线进入标量帧导致运行失败、原示例设备参数无法形成稳态、盘管势能被计入跨壁热、无效回路锚点被丢弃、`coupling` 变量前缀冲突，以及失败步回滚后嵌套液体网络参数快照不一致。

## 验证

本机环境：Windows、Python 3.11、Node 24+、Edge；依赖采用项目锁定版本。全部服务与算例使用临时测试工作区。

| 检查 | 结果 |
| --- | --- |
| 全量后端回归 | 初验 1374 通过、7 失败，覆盖率 90.95%；全部失败已由下方最终补测复验通过 |
| 最终文件定向复验 | 本轮 6 个测试文件共 62 项全部通过（24.71 s），包含初验失败项及后续新增项 |
| 热耦合物理、合同与回滚专项 | `tests/test_thermal_coupling.py` 36 项通过 |
| 工质／求解选项保存往返 | `tests/test_thermal_coupling_bridge.py` 3 项通过 |
| 联算后台 REST / WebSocket | `tests/test_thermal_coupling_api.py` 1 项通过 |
| 无界面／按保存项目运行／客户端 | 22 项通过，停止后无残留 Worker |
| 浏览器 | `package.json` 中 17 个脚本全部通过，包含新增热耦合及原冷库 A/B |
| 契约 | `generate_contracts.py --check`：67 个文件一致 |
| 静态检查 | ruff 通过；mypy 后端 62 个文件、SDK 11 个文件零错误；前端 `npm run check` 通过 |

全量初验在专项测试仍完善时启动，载入了早期测试版本：2 项本机 HTTP 设置受系统代理影响，4 项高差测试尚未声明 `height_m` 参数，1 项把仍可能形成停机平衡的工况误当作无解。最终已限定本机测试连接直连、为高差用例显式声明参数、改用运行压缩机且关闭节流阀的确定无解条件。最后在全部文件稳定后重跑上述 62 项，覆盖全部 7 个失败及新增边界测试；未把初验记为单次全绿。当前收集数为 1389，无未解释的失败。

最终补测记录为 `artifacts/completion-focused-tests.xml`；全量初验的覆盖率记录为 `artifacts/completion-coverage.json`。

物理校核采用端口质量流量与比焓差、独立 CoolProp 比热的 ε–NTU、制冷剂总质量及已接受步累计能量账。默认设计点热量：乙二醇 `16048.7787 W`、水 `15971.8193 W`；稳态最大能量变化率均小于 `6e-8 W`，没有放宽原接受阈值。

浏览器证据：`artifacts/thermal-coupling-run.png` 显示独立的两侧网络、工况、盘管曲线与指标；`artifacts/completion-browser-results.json` 记录其余 14 个通用脚本的退出码。热耦合脚本同时断言修改后结果失效、重新计算、保存、服务重启与界面／保存项目 API 结果完全一致。

复验命令（在项目目录执行）：

```powershell
python -m pytest -q --cov=fn_engine --cov-report=term
python scripts/generate_contracts.py --check
python -m ruff check backend tests scripts examples/external_clients
python -m mypy --config-file mypy.ini
python -m mypy --config-file mypy-sdk.ini
npm run check
npm run test:browser
```

## 后续范围

2026-10-27 按用户决定，M3 打包与发版，以及“变量别名 → 源码环境真实服务联调 → 24 小时稳定性验证 → 工程算例校核”整条后续任务链均已取消。这些工作不再列为剩余待办、其他工作的前置条件或当前验收门槛；取消不等于已经完成。已有源码功能、客户端和本页记录的已完成测试继续保留。随后重新规划的单盘管通用建模首批已完成，见[独立验收](THERMAL_COUPLING_MODELING_ACCEPTANCE.md)；当前状态以 [路线图](ROADMAP.md) 为准。

热耦合首版仅支持一根浸没盘管和无储量的内置液体侧；扰动工况用于动态研究，固定参数不保证存在稳态平衡。具体适用边界和变量单位见 [热耦合说明](THERMAL_COUPLING.md)，对接步骤见 [客户端说明](../examples/external_clients/README.md)。
