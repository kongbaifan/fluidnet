# 热耦合液体侧 Python 设备

本功能允许无独立储量的 Python 阀门或局部阻力，参与集总制冷站与单相液体网络的热耦合。普通模块编写、验证、保存版本、项目升级/回退和结果归档流程继续适用。

本轮实现与统一检查已完成，结果及可追溯日志见[综合验收](COUPLED_MODULES_ROOM_CONTROL_ACCEPTANCE.md)。

## 从完整示例开始

1. 启动源码服务，从“项目 → 导入单项目”导入 [`author_loop.json`](../examples/coupled_liquid_modules/author_loop.json)。这是包含模块源码及双哈希的规范 Project 文件，可在另一工作区导入，无须本机绝对路径。
2. 在设置页选择动态计算，建议先用时长 2 s、输出间隔 1 s。运行后查看盘管热量、液体流量和制冷容器温度。
3. 设备 `LiquidValve-Custom` 是自定义水阀。基础工况为 80% 开度；切换“线性特性 · 40% 开度”或“平方特性 · 80% 开度”比较流量与换热量。
4. 在模块库找到“热耦合液体作者阀门”，打开源码、修改算法并通过验证，保存新版本。项目通过“模块版本”显式采用新版本；也可回退到旧版本。
5. 在“记录”打开运行档案，可下载 HTML 报告及报告 CSV；作者版本、派生量、累计量和热耦合量来自该运行冻结的项目，不会被后来编辑的源码替换。

示例 API：`GET /api/v1/examples/thermal-coupling-author`。重新生成规范文件：

```powershell
python scripts/generate_coupled_liquid_example.py
python scripts/generate_coupled_liquid_example.py --check
```

示例使用液态 Water；构建函数 `coupled_liquid_module_example(coolant='INCOMP::MEG[0.3]')` 可生成乙二醇载冷液版本。制冷剂回路为 Ammonia，液体与制冷剂只交换热量，不通过流体端口连接。

## 作者能改什么

完整公共 SDK 源码位于 [`module.py`](../modules/coupled_liquid_valve/module.py)。本例采用 `有效开度 = 指令开度 ** 特性指数`：指数 1 为线性，指数 2 表示同样指令下更小的流通能力。此关系是可编辑的开发示例，不是厂家阀门标定曲线。

`evaluate` 使用本次候选状态的液体密度注册 `ctx.net.valve(...)`。可以替换为自己的开度曲线，或者用 `ctx.net.resistance(...)` 返回直径和局部阻力系数。质量流量由全网方程解出，不应在算法里指定一个与网络无关的流量。

| 参数 | 含义 |
| --- | --- |
| `opening_ratio` | 0–1 指令开度，支持运行时修改、PID 或 Python 控制脚本写入 |
| `kv_m3_h` | 全开流量系数，规范单位 m³/h |
| `characteristic_exponent` | 开度指数；保存为项目参数，也可按工况覆盖 |

模块验证台可以使用普通单相液体边界。完整热耦合项目仍须验证流量、盘管传热、制冷剂质量守恒和能量守恒；独立模块测试通过不能代替系统联算验证。

## 当前支持范围

- schema 2 或 3 的 Python 流体模块；须声明 `state.transactions.v1`，以及 `net.valve` 或 `net.resistance`。
- 两个液体端口、一条启用的阻力通路，无 `state_model` 和 `thermal_model`。支持 JSON 离散记账状态、观察回调和已有运行时参数控制。
- 实际每次求值只能返回无附加 `heat_w` 的 valve/resistance 关系；越界能力和实际不受支持的关系均拒绝，即使源码没有声明它们。
- 作者只能输出声明过的派生量，不能覆盖平台的端口、通路、参数和 `state.*` 字段。状态由接受回调写入 `ctx.state`。
- 热耦合关系的液体目标仍须为内置单通路圆管；作者设备放在配套液体回路中。最多两条热耦合，仍关联同一个饱和容器。
- 泵、主动热源、作者双侧换热器、液体水箱/管段热容、制冷作者设备参与混合域，继续由各自物理范围约束。

这些限制按合同和返回关系检查，与模块名称和实例编号无关。

## 时间与累计量

外层制冷站对每个候选容器状态重新求解液体网络。作者模块看到实际候选时刻；一次时间段内所有试算都使用上一段已接受的模块状态。只有制冷剂状态、液体解、控制和全部作者候选都成功，才能一起接受。任一作者准备失败会回滚整段；接受后的 Worker 同步失败则保留已接受帧并结束运行。

| 变量 | 计算口径 |
| --- | --- |
| `LiquidValve-Custom.state.transferred_mass_kg` | 平台按每个真实接受内部步的绝对质量流量积分；自适应计算使用被接受的两个半步，拒绝的试算不计入 |
| `LiquidValve-Custom.state.throughput_kg` | 示例作者 `commit_step` 的离散记账：整段末流量乘整段时长；流量变化且存在内部细分时，可能与平台积分不同 |
| `LiquidValve-Custom.state.commit_count` | 成功接受的控制/调度段数；不等于牛顿迭代次数、内部半步数或输出帧数 |
| `coupling.HX1.state.heat_energy_j` | 平台按接受内部步积分的盘管传热量 |

工程累计质量应读取平台 `transferred_mass_kg`。作者不能创建同名状态覆盖它。读取历史或重复查看当前结果不执行接受回调。

无控制/事件、无库房储热的项目也可使用原有热耦合稳态平衡入口。稳态运行会启动真实 Worker 求值，但不调用接受回调，不增加累计量；求解结束后关闭 Worker。

## 验证入口

```powershell
python -m pytest -q tests/test_coupled_liquid_modules.py tests/test_coupled_liquid_examples.py tests/test_coupled_liquid_reports.py
npm run test:browser:coupled-author
```

后端用例包含与内置阀门对照、真实候选时刻、动态参数写入、零流量、失败缩步、自适应拒绝、多模块准备失败、接受后同步失败、稳态平衡与进程关闭。报告测试覆盖冻结版本、作者派生变量、平台积分、重启读取及不执行作者源码。浏览器验收使用 1920×1080、DPR=1；完整项目版本和导入导出流程见对应脚本输出。
