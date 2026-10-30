# 已保存项目的外部客户端

[saved_project.py](saved_project.py) 和 [saved_project.mjs](saved_project.mjs) 通过 HTTP/WebSocket 驱动已保存项目，不需要打开 Studio。两者依次启动持续动态运行、订阅三帧、按配置写入变量、暂停/继续并停止，等待命令 `applied` 回执后再继续。异常退出时也会尝试发送停止命令。

从 `fluidnet-prototype-engine` 目录执行。先在 Studio 中保存一个能动态运行的项目，再停止原服务，并用相同工作区启动无界面服务。安装项目依赖（已包含 WebSocket 传输）后创建控制令牌，令牌只显示一次：

```powershell
python -m pip install -r requirements.txt
python -m fn_engine token create external-client --scope control
python -m fn_engine serve --headless --auth required --data-dir .runtime/workspace
```

在第二个终端设置连接信息，令牌填上一步显示的值。若服务使用了自定义 `FLUIDNET_TOKEN_FILE`，创建令牌时也需使用相同文件。

```powershell
$env:FLUIDNET_URL = 'http://127.0.0.1:8798'
$env:FLUIDNET_TOKEN = '<控制令牌>'
$headers = @{ Authorization = 'Bearer ' + $env:FLUIDNET_TOKEN }
Invoke-RestMethod ($env:FLUIDNET_URL + '/api/v1/projects') -Headers $headers
$env:FLUIDNET_PROJECT_ID = '<上一步返回的项目 ID>'
```

任选一个客户端：

```powershell
# Python 3.11+；使用项目自带的 websockets 依赖。
python examples/external_clients/saved_project.py

# Node 24+；客户端无 npm 依赖。
node examples/external_clients/saved_project.mjs
```

客户端输出运行 ID、实际项目修订、订阅帧和最终 `cancelled` 状态。停止命令的终态名为 `cancelled`，表示用户主动结束运行。客户端不会创建或打印令牌。

| 环境变量 | 含义 |
| --- | --- |
| `FLUIDNET_PROJECT_ID` | 必填，已保存项目 ID |
| `FLUIDNET_URL` | 服务地址，默认 `http://127.0.0.1:8798` |
| `FLUIDNET_TOKEN` | 认证启用时必填，需 control 权限 |
| `FLUIDNET_REVISION` | 可选，项目修订号；省略则固定当前最新保存修订 |
| `FLUIDNET_SCENARIO` | 可选，项目内已有工况 ID |
| `FLUIDNET_VARIABLES` | 可选，逗号分隔的完整帧变量键；省略则订阅全部变量，输出展示前 8 个 |
| `FLUIDNET_WRITE_VALUES` | 可选，JSON 对象；未设置时跳过写变量步骤 |

例如，内置“泵阀并联管网”的 V2 阀门支持运行时修改开度，可以在运行客户端前设置：

```powershell
$env:FLUIDNET_VARIABLES = 'V2.param.opening_ratio,V2.mass_flow_kg_s'
$env:FLUIDNET_WRITE_VALUES = '{"V2.param.opening_ratio":0.6}'
```

写入值使用规范单位（这里 `0.6` 表示 60%），且必须选择项目实际存在并允许运行时修改的参数。不可写、越界或被 PID 绑定的参数会返回拒绝回执，客户端报错并停止运行。别名映射尚未实现。

重启服务后，用输出的运行 ID 查询归档：

```powershell
$runId = '<客户端输出的运行 ID>'
Invoke-RestMethod ($env:FLUIDNET_URL + '/api/v1/runs/' + $runId) -Headers $headers
```

源码环境的联调回归：`python -m pytest tests/test_external_clients.py -q`。该测试使用独立临时工作区和控制令牌，实测两个客户端的订阅、写入、暂停/继续、停止、Worker 回收和服务重启后归档。缺少 Node 24 时 JavaScript 客户端测试跳过。

2026-10-27 已按用户决定取消 M3 打包与发版，以及变量别名、源码环境真实服务联调、24 小时稳定性验证、工程算例校核这条后续任务链；不再将它们列为剩余待办、前置条件或验收门槛。本文保留已有客户端及已完成联调的使用说明，新的开发方向尚未确定。

接口、错误响应与快照语义详见 [API 文档](../../docs/API.md#无界面服务与已保存项目运行)。

## 风系统

现有 Python/JavaScript 客户端可直接驱动已保存的风侧动态项目。设置 `FLUIDNET_PROJECT_ID` 为项目 ID，`FLUIDNET_VARIABLES` 使用实际键，例如 `Coil.condensate_kg_s,Room.state.relative_humidity`；`FLUIDNET_WRITE_VALUES` 可写 `Room.param.moisture_load_kg_s` 等运行参数。含湿量使用 kg/kg_da、温度使用 K，不能发送页面的显示值。

变量目录先调用 `/runs/{run_id}/air-variables`，报告使用原 `/runs/{run_id}/report.csv` / `report.html`。同一 sequence 和 parameter_revision 的 REST/WS/报告数值一致。完整示例和质量基准见 [风侧使用说明](../../docs/AIR_SIDE_USER_GUIDE.md)。
