# 制冷站与二次液体回路热耦合

2026-10-27：集总 NH₃ 制冷站与闭式水／乙二醇回路通过一根或两根浸没盘管交换热量；双盘管须关联同一个饱和制冷剂容器。压力和质量网络相互独立，二次侧温度由环境热负荷、泵轴功和制冷剂温度共同确定。该案例是开发参考，参数未经厂家或现场标定。

## 使用

在项目页可创建现成热耦合案例，也可在自己的画布中搭建制冷站和单相液体回路。建模页工具栏的“建立热耦合”提供关系标识、液体管段、通路、饱和制冷剂容器和 UA 的选择与编辑；已有关系时按钮显示“盘管换热”。液体管段须为无储量内置圆管，只有一条启用通路，原环境散热 UA 和热容分段数均为零。没有合法端点时，弹窗会说明需要补充的设备或参数条件。

关系标识以字母开头，可包含字母、数字、下划线和连字符，最多 81 个字符。端点选择遵循项目保存的端口／通路定义；禁用通路不会因为原始模块模板可用而被列为合法盘管。最多两条关系，且两条须关联同一个饱和制冷剂容器。

项目页的“双盘管示例”提供“同回路双支路”和“水与乙二醇独立回路”两种拓扑。单条关系编辑器可“新增关系”；已有两条时，“盘管换热”先显示关系列表，可分别编辑或移除。第二条关系只能选择尚未绑定的液体通路，容器须与第一条相同。双盘管结果区可滚动查看汇总及两根盘管的指标。

页面按实际关系显示换热量、二次侧流量、盘管进出液温度、制冷剂饱和温度和累计传热量，提供对应曲线，不要求使用示例设备编号。关系或参数改变后旧结果标记过期，当前耦合曲线等待重新计算；已记录的历史曲线保留原绑定，后来添加的普通观察变量也可随运行快照保存。

修改、重绑定或移除关系，以及删除被引用的设备前须停止运行；暂停中的项目同样受此限制。删除被引用设备会列出要解除的关系，确认后一起删除，可用撤销／重做恢复设备、连线、关系和当前曲线。复制单个设备不会自动复制耦合。单独移除关系会保留两侧设备。

保存、重新载入与按保存项目启动均保留耦合关系、完整工质配置、求解选项和已应用参数。尚未建立关系的混合域草稿可以保存；检查和运行会返回 `COUPLED_RELATION_MISSING`，提示先建立热耦合。

`GET /api/v1/examples/thermal-coupling` 返回单盘管规范 `Project`；双盘管使用查询参数 `topology=parallel` 或 `topology=independent`。提交到 `POST /api/v1/runs` 可计算；保存到工作区后也可通过 [无界面接口](API.md#无界面服务与已保存项目运行) 启动。单盘管 Python 调用示例（在项目目录执行）：

```python
from fn_engine.compiler import compile_project
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
from fn_engine.solver import solve_dynamic, solve_steady

project = thermal_coupling_example()  # INCOMP::MEG[0.3]；也可传入 'Water'
steady = solve_steady(compile_project(project))
print(steady.variables['coupling.HX1.heat_w'])
frames = solve_dynamic(compile_project(project), duration_s=10, dt_s=1)
```

## 合同与物理关系

```json
{
  "thermal_couplings": [{
    "id": "HX1",
    "fluid_instance_id": "HX_W",
    "fluid_channel_id": "ch0",
    "refrigerant_vessel_id": "LP1",
    "ua_w_k": 1800
  }]
}
```

最多两条耦合，每条绑定一个内置圆管的唯一通路，且两条须关联同一个饱和制冷剂容器；同一液体通路不能重复绑定。盘管的原环境散热 UA 和热容分段数必须为零；耦合合同指定换热 UA。二次侧支持无储量的内置单相液体网络，不含水箱、管壁／流体热容分段、困液和 Python 设备模块。支持项目 Python 控制、PID、运行参数写入及 `set_variable` 日程。耦合项目中的设备 ID 不可为 `coupling`，该名称保留给换热结果，避免覆盖设备通路变量。

相变侧取容器当前饱和温度；液体侧用当前物性与上游温度计算：

```text
C = |m| × cp
ε = 1 − exp(−UA / C)
Q = ε × C × (T_in − T_sat)
```

`Q > 0` 表示液体向制冷剂放热。关闭通路时质量流量和换热量为零，反向流时按实际上游取温度，反向温差允许负换热量。管段高差造成的势能变化与跨壁热量分别核算。每次容器隐式试算都重新计算液体网络，将同一热量以相反符号写入两侧能量方程；未接受的时间段不提交状态或累计量。

## 稳态与动态

基础案例指定氨侧蒸发／冷凝温度 5／35 °C、环境 30 °C。创建案例时按液体负荷和制冷剂比焓差反算压缩机排量、节流阀 Kv、冷凝器 UA，形成一致设计点：30% 乙二醇约 **16.0488 kW**，水约 **15.9718 kW**。这些参数在运行前已固定，稳态求解器不自动调整设备参数。

稳态保持各制冷剂回路初始总质量，并要求全部容器质量／能量变化率为零。接受阈值为最大质量变化率 `1e-8 kg/s`、最大能量变化率 `0.01 W`、回路总质量相对误差 `1e-8`。固定排量、阀开度与外部负荷不一定存在共同平衡；改变 UA 或负荷后可用动态计算观察响应，无物理解的稳态会明确失败。稳态首版不执行控制器、启用的脚本或事件，也不支持库房储热节点。

动态采用现有制冷站的隐式 Euler 积分和可选时间误差控制，发布时刻与控制／事件时刻保持原有约定。默认基础设计点可用于检查平衡保持；“环境热负载升高”和“二次侧阀门开度减小”用于动态扰动研究。

## 输出与验证

| 变量／指标 | 含义 |
| --- | --- |
| `coupling.HX1.heat_w` | 液体向制冷剂的传热功率，W |
| `coupling.HX1.fluid_heat_w` / `refrigerant_heat_w` | 两侧带符号热量，和为零 |
| `coupling.HX1.mass_flow_kg_s` | 按盘管标称方向带符号的流量 |
| `coupling.HX1.fluid_inlet_temperature_k` / `fluid_outlet_temperature_k` | 按实际流向的液体进出口温度，K |
| `coupling.HX1.refrigerant_temperature_k` | 氨侧容器饱和温度，K |
| `coupling.HX1.effectiveness` | 换热有效度 ε |
| `coupling.HX1.equation_residual_w` | 实际换热量与 ε–NTU 关系的差值 |
| `coupling.HX1.state.heat_energy_j` | 仅累计已接受时间步的传热量，J |
| `metrics.coupling_heat_w` / `metrics.coupling_heat_energy_j` | 各盘管传热功率之和（W）及已接受时间步累计总传热量（J） |
| `metrics.energy_residual_j` | 制冷站存储能量变化与边界能量的累计差值，包含盘管传入热量 |
| `metrics.fluid_energy_residual_w` | 二次侧热力平衡残差 |
| `metrics.steady_*` | 稳态质量率、能量率、总质量误差和求解次数 |

上表的 `HX1` 换成实际关系标识即可读取另一根盘管；两个独立回路的泵分别为 `WP1` 与 `WP2`。原有设备、端口和参数键保留；耦合变量可直接用于 REST 读取与 WebSocket 订阅。`metrics.electric_power_w` 沿用制冷站设备电功率口径，二次侧泵轴功通过对应泵的 `shaft_power_w` 单独读取。

单盘管物理专项见 `tests/test_thermal_coupling.py`，覆盖独立物性／能量账、稳态与动态、流向和温差反转、零流量、控制写入和编译边界；双盘管见 `tests/test_dual_thermal_coupling.py`。前端与保存往返验证由对应浏览器脚本执行；首版结果见[首版验收](COMPLETION_ACCEPTANCE.md)，双盘管的小窗口编辑、重启与保存项目复算见[完成情况核查](DEVELOPMENT_COMPLETION_AUDIT.md)。
