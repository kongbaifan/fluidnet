# FluidNet Prototype Engine

基于现有 FluidNet Studio 交互原型建立的独立项目。前端继承画布、模块库、型号、设备属性、草稿/应用和曲线工作流；后端重新定义模块合同、网络编译、水力算法和 HTTP 接口，并提供基于 Pydantic 的契约层、CoolProp 单相物性服务、版本化 Python 模块包和独立 Worker 生命周期。

本目录独立于原来的 `fluidnet/` 与 `web/`。原型来源为 `../output/visualizations/fluidnet-studio-prototype.html`。前端原型现拆分为 `frontend/index.html`(HTML/CSS 外壳与挂载点)与 `frontend/studio.js`(原内联 JavaScript),新增 `frontend/engine-client.js` 负责真实计算接口;`index.html` 末尾依次加载二者,服务把 `frontend/` 目录以 `StaticFiles(html=True)` 挂载到 `/`,默认入口页即 `frontend/index.html`。

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
2. 点击“运行”或“单步”。原型项目经归一化转换成新合同，后端返回真实水力与热力结果。
3. 修改 V1 的开度，点击“预览并应用”，再单步。草稿值不进入计算，已应用值进入下一次求解。
4. 画布、设备变量表和曲线读取同一运行帧。端口的温度、比焓、密度和干度来自热力层；设备“全部变量”另有黏度、比热和通路吸热量。
5. 保存项目后可刷新继续查看已有结果；后端运行记录在服务重启后清空，浏览器中保存的结果不依赖内存记录。

初始算例的 A 路质量流量约为 **3.582677 kg/s**。A 路开度从 80% 改为 40% 后，A 路约为 **2.346313 kg/s**。这是内置参数下的回归算例，示例泵曲线不是厂家标定数据。默认 `property_coupling='reference'` 下热力层不改变水力结果，这两个值与接入热力层之前完全一致。

“双侧换热机组”示例（UA = 2000 W/K）中，热侧 65.002 → 62.741 °C，冷侧 25.002 → 27.307 °C，换热量约 75.4 kW。

## 可编程模块验收入口

1. 打开「模块」，找到服务器清单加载的「可编程阀门 · Python · v1」。
2. 点击「独立验证」并运行：验证台显示实际流量、evaluate 变量/密度、网络关系、commit_step 状态和源码哈希。
3. 点击模块卡片的「管网算例」：创建「压力源 → 管道 → 可编程阀门 → 出口」，点击运行完成 1 秒、10 个成功时间步。
4. 在设备「全部变量」中查看累计通过质量和提交次数，并加入曲线。也可从模块库拖入新的实例，编辑参数后预览并应用。
5. Python 源码编辑形成浏览器草稿；独立验证执行草稿。项目执行插入时绑定的已保存版本，后续编辑和发布不会改变已有项目。

## 模块开发与版本保存

1. 在「模块库 → 新建模块」选择 Python 模板，填写唯一标识和名称。
2. 在「代码」编辑 `module.py` 的四阶段方法。在「变量属性」新增/编辑数值参数和输出，在「绘制模块 / 通路设置」编辑端口及内部连接。
3. 「契约与版本」可以编辑完整 JSON，包括其他参数类型和单位换算。点击「校验并应用契约」完成 Pydantic、Python 语法、Worker 入口检查，并更新参数面板。
4. 「独立验证」配置边界并试算；回到编辑器填写版本备注，点击「保存新版本」。后端重新校验、用参数默认值试算并验证声明的输出后，才写入不可变版本。
5. 版本按模块 ID 从 v1 递增；内置示例 v1 的下一版本为 v2。「刷新版本」查看备注、哈希和验证状态，「载入为草稿」可以基于历史版本继续开发。
6. 拖入项目或创建管网算例时保存完整版本快照和引用。同一项目中同一模块 ID 使用同一版本；发布后新项目可以使用新版，已有项目继续使用原版。暂未提供项目内的版本升级/迁移操作。

模块版本默认保存在本项目 `.runtime/module-packages/module-<id>/v<N>/`，包含 `manifest.json`、`module.py`、`release.json`（备注、时间、试算条件与结果）。可用环境变量 `FLUIDNET_MODULE_STORE` 指定持久目录。服务重启不会丢失这些文件；该目录属于本地用户数据，Git 忽略它，备份时需另外复制。`modules/` 中的示例包不被修改。浏览器「保存原型」只保存项目和编辑草稿，与后端版本保存分开。

保存前试算会为每条启用通路各接一组独立压力边界，多通路模块（如两侧独立的换热结构）在同一个网络中一次求解；通路共用端口、端口未绑定通路或非流体端口会被拒绝，并在诊断中说明。数值、布尔、文本和曲线参数都可以在设备面板和验证台按类型编辑；数值参数显示单位换算，曲线参数使用 JSON 点对数组。设备面板的草稿仍通过“预览并应用”生效。

## 能力范围

| 能力 | 当前行为 |
| --- | --- |
| 压力边界、连接节点 | 支持；各连通子网络必须有压力参考 |
| 泵 | 流量—扬程曲线、转速相似律、轴功率估算；曲线外/反向/停泵工况报错 |
| 阀门 | Kv × 开度，正反流；0% 开度精确约束零流量 |
| 管道 | Darcy–Weisbach、层流关系、Haaland 湍流近似及过渡区插值；可选向环境散热（`heat_loss_ua_w_k`，默认 0 为绝热） |
| 热力层 | 端口压力 + 焓；按流向迎风传焓、节点按质量加权混合；内置泵与 Python 泵/压缩机关系的轴功计入流体；Python 模块可声明 `heat_w`；闭合回路无补水时取边界温度为参考并报告等效热量；全网能量残差校核 |
| 双侧换热器 | 两侧独立水力支路；ε–NTU 计算换热量与两侧出口温度（标称逆流，单侧反向时按顺流） |
| 物性耦合 | 默认 `reference`：水力用参考常数物性，结果与接入热力层前一致；可选 `node`：节点平均密度/黏度回到水力外迭代 |
| 动态选项 | 每帧求解水力与热力并热启动，收敛后调用 Python commit_step；没有水锤/热惯性/内置水箱积分 |
| 暂停/继续/停止 | 控制已完成计算结果的前端回放;后台运行同时调用 `POST /runs/{run_id}/command` 协作式控制;取消在当前时间帧结束后生效,不是抢占式 |
| 单步 | 新建不可变计算快照；含 Python 模块时每次重新初始化，连续状态演化使用一次完整动态运行 |
| 水箱、加热器、PID、止回阀、物性扩展 | 保留原型编辑入口；进入当前求解器时明确拒绝 |
| 控制脚本、原型自定义变量、串口演示 | 保留编辑与预览；不执行控制或真实外部连接 |
| 独立验证台 | 每条启用通路各接独立边界，多通路一起求解；真实边界、Worker 生命周期和状态返回 |
| 组合设备 | 已展开为普通实例/连接的项目可计算；专用组合定义的递归展开待实现 |
| Pydantic 契约 | API、项目、模块包和 Worker 消息使用严格模型；自动生成 JSON Schema/OpenAPI |
| Python 模块包 | 模块清单驱动 UI；项目与验证台均在独立 Worker 中执行 `initialize/evaluate/commit_step/finalize` |
| 模块版本保存 | 后端校验、独立试算、原子写入、并发冲突检测；项目绑定源码与契约双哈希 |
| CoolProp 物性 | AbstractState 单次 flash 的 `state_pt/state_ph`；压力—焓查询在两相区返回干度；网络流动只支持与边界一致的单相，进入两相报 `PHASE_UNSUPPORTED`；混合物仍未实现 |
| 后台运行 | `POST /api/v1/runs?background=true` 返回 `run_id`,可查询状态、历史和事件;`POST /runs/{run_id}/command` 支持 pause/resume/stop(step/set 未实现),health 的 `capabilities.run_control` 为 true |

默认 `reference` 模式下水力采用定密度、定黏度液态水近似，温度相关物性只在热力层和 `node` 耦合模式中使用；内置模型不计算汽蚀、相变或水锤；Python SDK 可显式传入物性及通路高差。非零节点标高会被参数校验拒绝。换热器原型没有水力内径输入时使用目录默认 40 mm；建议通过规范合同指定参数。

后台运行的暂停与取消现已接入:`POST /api/v1/runs/{run_id}/command` 接受 `RunCommand`,只有 pause/resume/stop 生效。取消是帧粒度的协作式停止——求解器在下一个时间帧之前退出,已算出的帧保留,Worker 子进程由正常关闭路径回收;"单步"仍指新建一次运行,不是对已有运行的 step 命令。

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

Windows 测试使用本机 Edge 的无头模式。验证真实页面加载、连接检查、求解、修改开度、应用、曲线值、保存和刷新。`browser-authoring.mjs` 另外启动临时端口和隔离存储，覆盖新建模块、参数/输出编辑、校验失败、版本保存、旧项目隔离与服务重启复现，不向用户模块目录写入测试版本。截图写入忽略提交的 `artifacts/`，包括 `module-authoring.png`。仅在明确更新原型基线时执行 `node tests/browser-smoke.mjs --refresh-fixture`。

当前测试包含单位双向转换、Kv 解析解、管道层流压降、粗糙度影响、节点流量守恒、关阀、反向流、未收敛、断开子网络、冲突压力边界、不支持模型、双侧换热器、API 错误响应、工况覆盖和采样上限。热力测试（`test_thermal.py`）覆盖节点混合、等焓、管道散热解析解、泵温升、ε–NTU（含 C_r=1）、单侧无流量、反向流、停滞节点、闭合回路参考热量、全网能量平衡、reference 模式水力基准、thermal 关闭、node 耦合、Python 模块 heat_w 与相态拒绝、动态热启动、边界温度冲突，以及与归档 v0.2 内核的换热器对照；物性测试（`test_properties.py`）覆盖 PT/PH 往返、两相干度、相态策略与多线程查询。平台契约测试另外覆盖 CoolProp 水/空气状态、版本化可编程阀门 Worker、`evaluate` 关系进入网络求解器、模块默认值、后台运行事件、独立进程 ID、嵌套状态隔离、超时终止、失败清理、末步 dt、真实累计质量、通路缺失诊断及前端保存/刷新/拖放。
