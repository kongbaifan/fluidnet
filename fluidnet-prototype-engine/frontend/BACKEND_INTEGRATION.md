# 原型与后端接入

前端来源为当前 Studio 原型，保留 HTML/CSS 布局与交互。原单文件内的 JavaScript 已移入 studio.js，新增 engine-client.js；index.html 依次加载二者。

已完成的映射：

1. 启动读取 /health 和 /catalog，目录中的单位和范围同步到原型现有参数控件。
2. 检查连接提交原型活动项目到 /prototype/normalize，再调用 /projects/validate。
3. 运行和单步调用 /runs，读取 /runs/{id}/history。
4. 暂停/继续/停止操作已计算历史帧的回放；改动已应用参数后重新提交运行。
5. 每帧保留 canonical 规范变量字典，并映射到原型变量表的显示单位及 sampleKey。
6. 主系统演示 sampleStep/sampleHistory 已移除。初始演示记录为空，不从公式构造伪造流量或温度。
7. 本地存储使用 fluidnet-prototype-engine-v1，与原型原有 storage key 分开。

绘图保留原型的主管、A 路、B 路快捷观察，对应 P1/V1/V2 的真实单通路变量；其他设备从“全部变量”加入观察。温度未计算时为 null，曲线留空。前端端口流量按照标称方向显示，后端端口流量统一按流入设备为正。

独立测试、代码执行、PID、串口、物性等原型页保留其编辑/预览含义；不能把相关演示操作理解为已接入物理内核。原型导入能完整保存界面状态，归一化接口只生成求解投影。

后续可把剩余 UI 描述完全迁移为目录驱动，再引入热力、状态和异步控制；不需要重写画布与设备编辑器。
