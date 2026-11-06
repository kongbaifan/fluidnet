# R01/R02/R04：性能压缩机、同库多冷风机与电融霜

日期：2026-11-05。三项均为新的设备合同，旧 `refrigerant_compressor`、`cold_room`、`air_cooler` 保持原合同与行为。

## R01 性能曲线压缩机

设计卡：`performance_compressor`，内置 `refrigeration` 域，制冷剂 `suction/discharge` 两端口，连接两饱和压力等级。仍从吸气容器读取饱和气，不宣称真实过热吸气。无新增物理状态，累计电量由原接受事务积分。

输入为额定理论排量 m³/s、载量/转速比0–1、电机效率、最大压比、最大排气温度及四条分段线性曲线。两条曲线分别为压比—等熵效率、压比—容积效率，另外两条为载量—效率修正和转速—效率修正。实际效率等于对应压比效率乘两个修正系数；质量流量为排量×载量×转速×容积效率×饱和吸气密度，排气焓由等熵焓升除以实际等熵效率计算，电功率为轴功除以电机效率。

默认曲线全部为**明确的人为教学假设，不是厂家标定**。每条曲线至少两点，横坐标正且严格递增，纵坐标在(0,1]内；载量/转速轴不超过1。禁止在最终工作点外推，域外返回 `COMPRESSOR_MAP_RANGE`；非法曲线为 `COMPRESSOR_MAP_INVALID`；超最大压比/排温为 `COMPRESSOR_ENVELOPE`。停机、0载量或0转速输出0功率/流量。运行时只开放启停、载量和转速，不运行中重写曲线。

Newton内部扰动使用曲线端点有界延续以允许迭代恢复；整体物理子步求解后、接受前严格核对原曲线域和排温包络，超界结果不能接受。独立设备调用默认立即严格检查。有限状态还必须经过原物性和帧检查。

输出新增 `actual_isentropic_efficiency`、`actual_volumetric_efficiency`、`actual_speed_ratio`，保留质量流量、轴/电功、排气温度和累计电量。曲线为非标量参数，不伪造可采样 `param` 标量变量；完整曲线保存在冻结项目参数合同。

`performance-compressor.recipe.json/project.json` 使用单库8设备9连接，额定排量与冷凝UA按教学曲线重新平衡5kW库负荷。Python入口 `performance_example.performance_example()`。

## R02 一个库房接多台冷风机

设计卡：新增 `cold_room_multi`，`solver_model=cold_room`，四个输入热口 `heat0…heat3`，第一个必连，其余可选。参数仍为一个库房的初温、热容、围护与附加负荷，不复制房间储热。每个冷风机热口只归属一个库房；旧 `cold_room.heat` 仍保持一对一。

库房净冷量为全部关联冷风机 `room_cooling_w` 之和。每台冷风机的制冷剂得热和风机电热分别按原公式计入，只在对应位置记一次。共享供液仍按供液阀开度分配，不声称逐支路压降求解。报告及趋势目录列出所有冷风机，不只保留代表设备。

内部保留旧 `room_coolers` 代表映射以兼容旧消费者；实际计算使用 `room_cooler_groups`。新增界面/报告必须使用分组或实际设备目录，不能用代表映射推断冷风机数量。

`multi-cooler.recipe.json/project.json` 为同库两台冷风机11设备14连接，总UA和风机功率与原单台相同，只有一个库房热容。Python入口 `multi_cooler_example.multi_cooler_example()`。

## R04 泵供液冷风机电融霜

设计卡：`defrost_air_cooler`，沿用 `air_cooler` 的泵供液制冷和三端口。新增运行请求 `defrost_request`、固定加热功率、加热/滴水时长、入库热份额。状态为制冷0→加热1→滴水2→制冷0，0→1请求边沿触发；忙期间上升沿不排队，持续1不会重复融霜，必须回0后重新请求。

加热/滴水阶段供液支路关闭，风机停止，制冷换热为0；加热功率按显式份额分别进入库房与制冷剂储量，和电量账一致。全部供液支路关闭且泵仍输出时返回 `DEFROST_PUMP_NO_OUTLET`，要求停泵或保留有效支路，不凭空添加旁通。示例保留另一台在制冷。

阶段起点和结束点切分积分段，阶段/请求记忆/次数包含在会话事务检查点，失败段不推进状态及电量。输出为 `state.defrost_mode/count`、`heater_power_w`、`defrost_room_heat_w`、`state.heater_energy_j`；总电量和总功率包含电融霜，原冷风机保持无新增输出。

明确不模拟霜量、融化潜热、温感终止、热气融霜或自动设备联锁。加热与滴水时间是用户配置的过程假设。显示帧在阶段边界结束时记录刚完成段状态，下一积分段开始切换阶段，与控制采样时序一致。

`electric-defrost.recipe.json/project.json` 保留11设备14连接，60s请求CoolerB加热120s，滴水60s。recipe包含events，空白组装后需按其日程或手动将请求从0置1。Python入口 `defrost_example.defrost_example()`。

## 项目标准与验证

L1检查新目录、端口、曲线合法性、规范单位、旧模型兼容；L2以独立CoolProp焓熵计算和手算分段插值校核压缩机，以纯状态转换校核融霜；L3用实际组网、同库求和、独立供液、能量账和失败回滚验证。示例参数与目录固定在JSON，界面从空白搭建及保存重载由主集成另行记录。仅运行定向测试，不运行全量。

2026-11-05：`python -m pytest -q tests/test_station_defrost.py tests/test_multiple_coolers.py tests/test_performance_compressor.py tests/test_two_stage_modular.py --tb=short` 得到 **22 passed，6.10 秒**，包含R03子任务的五项真实两级存量/能量验证。相关文件ruff通过，mypy105/106个源码文件阶段检查无错误。原目录固定集合及曲线参数非标量规则由集成同步，不将本次定向结果解释为全量通过。
