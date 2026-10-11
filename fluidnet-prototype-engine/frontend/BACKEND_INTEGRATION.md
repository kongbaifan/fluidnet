# 原型与后端接入

前端来源为当前 Studio 原型，保留 HTML/CSS 布局与交互。原单文件内的 JavaScript 已移入 studio.js，新增 engine-client.js；index.html 依次加载二者。

已完成的映射：

1. 启动读取 /health、/catalog 和 /modules；内置目录与版本化 Python 模块包合并到模块库，清单参数和版本/哈希同步到原型控件。
2. 检查连接提交原型活动项目到 /prototype/normalize，再调用 /projects/validate。
3. 稳态调用 /runs；动态和单步调用 `/runs?background=true` 并轮询 `/runs/{id}`，再读取 `/runs/{id}/history`。
4. 暂停/停止先调用后端 `POST /runs/{run_id}/command`(仅后台运行),再停止本地回放;独立验证台没有后台 `run_id`,只停本地回放;已暂停的项目运行继续时额外调用 `resume` 同步后端。无进行中的后台任务时只停止本地回放。改动已应用参数后重新提交运行。
5. 每帧保留 canonical 规范变量字典，并映射到原型变量表的显示单位及 sampleKey。
6. 主系统演示 sampleStep/sampleHistory 已移除。初始演示记录为空，不从公式构造伪造流量或温度。
7. 本地存储使用 fluidnet-prototype-engine-v1，与原型原有 storage key 分开。

后台 `run_id` 记录在 `owner.run.runId`,暂停/停止据此取消真实任务;控制端点返回 404/501 时降级为仅本地回放,并在事件中说明。后台轮询有 3000 次或 300 秒双重上限,先到者生效,超时把该次前端运行标为失败并给出原因。

绘图保留原型的主管、A 路、B 路快捷观察，对应 P1/V1/V2 的真实单通路变量；其他设备从“全部变量”加入观察。温度未计算时为 null，曲线留空。前端端口流量按照标称方向显示，后端端口流量统一按流入设备为正。

独立验证台已对接 `/modules/test`：Python 模块的每条启用通路各接一组真实压力边界并一次求解，返回 Worker 的 evaluate 关系、模块变量、commit_step 状态、源码哈希和历史帧。设备面板与验证台按 `value_type` 渲染数值、布尔、文本和曲线参数，曲线使用 JSON 点对数组。项目中的 Python 模块同样在独立 Worker 中执行；每个实例在一次动态运行内复用同一个 Worker，成功时间步提交一次，异常或超时统一回收。

Python 包代码页的检查调用后端 `/modules/validate`，包含完整语法、Pydantic 和 Worker 入口校验；内置原型代码仍保留轻量预览。控制脚本、PID、串口以及未实现的热力/状态模型不进入当前物理求解。

新建模块使用 Python 包模板；变量属性页可编辑数值参数与输出，契约与版本页可修改完整 JSON、保存备注、查看历史并载入版本。`POST /modules/versions` 会重新试算当前提交内容，成功后更新可插入版本。保存期间继续输入会保留为后续草稿。

模块的 `publishedManifest` 表示可插入的保存版本，正在编辑的 source/contractDraft 不进入项目求解。项目 `moduleSnapshots` 固定完整定义，实例携带 `package` 引用。设备参数、端口和变量面板读取项目快照，避免库中新版参数覆盖旧项目。原型保存/导出包含快照；归一化优先使用快照并由编译器检查双哈希。浏览器草稿保存与磁盘模块版本保存是两个明确动作。

后续可把剩余 UI 描述完全迁移为目录驱动，再引入热力、状态和异步控制；不需要重写画布与设备编辑器。
