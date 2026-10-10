# FluidNet Prototype Engine

基于现有 FluidNet Studio 交互原型建立的独立项目。前端继承画布、模块库、型号、设备属性、草稿/应用和曲线工作流；后端重新定义模块合同、网络编译、水力算法和 HTTP 接口。

本目录独立于原来的 `fluidnet/` 与 `web/`。原型来源为 `../output/visualizations/fluidnet-studio-prototype.html`。前端原型脚本已拆为 `frontend/studio.js`，新增 `frontend/engine-client.js` 负责真实计算接口。

## 启动

Python 3.11 或更高版本，在本目录执行：

```powershell
.\start.ps1
```

脚本首次创建本目录下的 `.venv` 并安装依赖，随后打开浏览器。默认地址 `http://127.0.0.1:8798`，交互接口文档在 `/docs`。也可以手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m fn_engine serve --port 8798 --open
```

使用现有环境时可执行 `python -m pip install -r requirements.txt`，再执行 `python -m fn_engine serve --port 8798 --open`。本版本以源码/可编辑安装运行，不提供可独立分发的前端 wheel 包。

## 已接通的工作流

1. 打开“泵阀并联管网”，点击“检查连接”。请求后端完成端口、参数、内部通路和压力参考校验。
2. 点击“运行”或“单步”。原型项目经归一化转换成新合同，后端返回真实水力结果。
3. 修改 V1 的开度，点击“预览并应用”，再单步。草稿值不进入计算，已应用值进入下一次求解。
4. 画布、设备变量表和曲线读取同一运行帧。热力算法尚未返回的温度保持空值。
5. 保存项目后可刷新继续查看已有结果；后端运行记录在服务重启后清空，浏览器中保存的结果不依赖内存记录。

初始算例的主管/A 路/B 路质量流量约为 **6.240269 / 3.582427 / 2.657843 kg/s**。A 路开度从 80% 改为 40% 后，A 路约为 **2.346158 kg/s**。这是内置参数下的回归算例，示例泵曲线不是厂家标定数据。

## 能力范围

| 能力 | 当前行为 |
| --- | --- |
| 压力边界、连接节点 | 支持；各连通子网络必须有压力参考 |
| 泵 | 流量—扬程曲线、转速相似律、轴功率估算；曲线外/反向/停泵工况报错 |
| 阀门 | Kv × 开度，正反流；0% 开度精确约束零流量 |
| 管道 | Darcy–Weisbach、层流关系、Haaland 湍流近似及过渡区插值 |
| 双侧换热器 | 两侧独立水力支路；明确提示未计算换热 |
| 动态选项 | 准稳态时间序列，固定参数复用一个稳态解；没有惯性或状态积分 |
| 暂停/继续/停止 | 控制已完成计算结果的前端回放；不是后端任务控制 |
| 单步 | 新建不可变计算快照，取下一个采样时刻，允许应用参数后重新求解 |
| 水箱、加热器、PID、止回阀、物性扩展 | 保留原型编辑入口；进入当前求解器时明确拒绝 |
| Python、控制脚本、自定义变量、串口演示 | 保留定义/编辑功能，不执行物理算法或真实外部控制 |
| 单机测试面板 | 尚未接入真实求解，提示到主系统配置边界后运行 |
| 组合设备 | 已展开为普通实例/连接的项目可计算；专用组合定义的递归展开待实现 |

水力内核采用定密度、定黏度液态水近似，不计算温度相关物性、汽蚀、相变、重力标高或水锤。非零节点标高会被参数校验拒绝。换热器原型没有水力内径输入时使用目录默认 40 mm；建议通过规范合同指定参数。

前端默认总览曲线仍绑定示例变量 `P1`、`V1`、`V2`。自定义实例与换热器第二侧可在“全部变量”中加入观察；未绑定的总览变量显示为空。

## 结构

```text
frontend/             原型前端、计算适配器、基线说明
backend/fn_engine/    数据模型、模块目录、归一化、编译器、求解器、API、CLI
contracts/            自动生成的 JSON Schema/OpenAPI 和完整参考算例
scripts/              合同生成工具
tests/                物理/合同/API 回归测试和浏览器端到端验证
docs/                架构、字段、算法和接口说明
```

- [架构与扩展边界](docs/ARCHITECTURE.md)
- [数据合同与变量定义](docs/DATA_CONTRACT.md)
- [算法、假设与后续状态方程](docs/ALGORITHM.md)
- [API 请求与返回](docs/API.md)
- [原型适配说明](frontend/BACKEND_INTEGRATION.md)

## 验证

```powershell
python -m pytest -q
python scripts/generate_contracts.py
```

浏览器验证使用 Node 和 Playwright，服务需先启动：

```powershell
npm install
npm run test:browser
```

Windows 测试使用本机 Edge 的无头模式。验证真实页面加载、连接检查、求解、修改开度、应用、曲线值、保存和刷新。截图写入忽略提交的 `artifacts/workbench.png`。仅在明确更新原型基线时执行 `npm run test:browser -- --refresh-fixture`。

当前测试包含单位双向转换、Kv 解析解、管道层流压降、粗糙度影响、节点流量守恒、关阀、反向流、未收敛、断开子网络、冲突压力边界、不支持模型、双侧换热器、API 错误响应、工况覆盖和采样上限。
