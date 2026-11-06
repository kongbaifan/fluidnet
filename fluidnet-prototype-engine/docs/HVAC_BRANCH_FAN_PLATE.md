# H01／H02／H04：风侧分支箱、性能风机和板式换热器

2026-11-05。三个模块以新 ID、v1 发布，旧 `fan`、水三通、双侧换热器和已有组合的源码、整数版本及固定快照不修改。合同生成入口 `backend/fn_engine/hvac_expansion.py`，生成及一致性检查脚本 `scripts/generate_hvac_expansion.py --check`。

## 设备设计卡与边界

| 模块 | 运行类型／域 | 端口及压力参考 | 状态与范围 |
| --- | --- | --- | --- |
| `air_branch_box` | 固定子版本组合，展开为3个 `air_branch_leg` 与1个中心节点 | `common`、`branch1`、`branch2`，同一空气回路；压力参考来自外部边界 | 无物理储量；普通 Air/gas 及 `moist_air`。每腿阻力决定分配，中心按质量／焓／水分混合；无流量比相关经验 K |
| `fan_performance` | Python Worker，SDK0.6，使用 `net.pump`、`net.resistance`、`thermal.v1`、湿空气透传 | `in0`→`out0`，外部压力边界；运行反流不支持，停机允许被动双向流 | 仅 Air／HEOS::Air；无转子惯性、储热或风机失速区模型。累计轴功、电量仅在接受步推进 |
| `plate_exchanger` | Python Worker，两个独立单相 `fluid` 回路，SDK0.6热输运 | `hot_in/out`、`cold_in/out`；两侧各有独立压力参考与工质 | 无持液储热；不声明湿空气透传，因此编译拒绝湿空气／风水项目。没有板片几何关联、冷凝/沸腾或厂家性能表 |

所有默认曲线和 K、UA 都是可复算的教学输入；用户可按明确资料建立设备型号，不代表现场或厂家精度。

### H01 真多端口风侧分支箱

三个外端口分别经过独立阻力腿接入一个理想混合节点，属于真实三端口网络，不是两端口三通图标。每条腿采用

\[
\Delta p=K\frac{\rho v|v|}{2},\qquad A=\frac{\pi d^2}{4}.
\]

K 的参考速度是该腿等效内径的实际速度；试算上游由压差方向选择。公开参数为 `Common/Branch1/Branch2_diameter_m`（默认0.4m，显示mm）与对应 `*_loss_coefficient`（默认0.2／0.5／2）；K可运行中调整，直径为静态。中心节点的 `Node_elevation_m` 保留既有零标高限制。零 K 表示理想无压降腿，连接互相冲突的固定压力时仍由网络拒绝。

分流、汇流及反向均由求解的压力和连线决定；湿空气在中心按干空气质量、含湿量和焓守恒，设备不提供冷凝、除湿或加湿。累计穿过质量只是接受步统计，不是储量。扩展到更多出口应创建另一个固定端口组合或使用多个分支箱，不能给现有冻结合同增加端口。

### H02 停转通流与效率曲线风机

| 参数 | 默认值与单位 | 修改权限 |
| --- | --- | --- |
| `running` | 1，0/1 | runtime |
| `speed_ratio` | 1，0–2 | runtime；0等同停机 |
| `pressure_curve` | `[0,300],[2000,250],[4000,120],[5000,0]`；m³/h、Pa | 静态 |
| `efficiency_curve` | `[0,.4],[2000,.65],[4000,.55],[5000,.35]`；Q/n m³/h、效率 | 静态 |
| `motor_efficiency` | 0.9，范围0.01–1 | 静态 |
| `diameter_m` | 0.4m，显示400mm | 静态，停机被动通路 |
| `stopped_loss_coefficient` | 2 | 静态，正值 |

运行时用相似律 `Δp(Q,n)=n² Δp_rated(Q/n)` 注册泵关系，压力曲线首点须Q=0，流量严格递增、压力严格递减，末点压力须0。效率曲线在同一个折算流量Q/n轴上分段线性插值，所有效率必须在(0,1]，并覆盖整个额定曲线；不隐式夹值、回退默认或外推。失效诊断文字含 `FAN_CURVE_RANGE`／`FAN_EFFICIENCY_RANGE`。

同一已收敛流量上计算：

\[
P_{fluid}=\Delta p Q,\quad P_{shaft}=P_{fluid}/\eta(Q/n),\quad
P_{electric}=P_{shaft}/\eta_{motor}.
\]

引擎已经把流体功加入气流，模块只额外加入 `Pshaft−Pfluid` 的风机耗散，因而气流总得热为轴功；电机损失排向环境，不重复加入。此热边界与旧风机的默认边界不同，故使用新模块ID。普通空气和湿空气分别验收，湿空气以混合物质量/实际密度求Q，能量以干空气焓输运核算。

停机时注册同一两端口的被动K阻力，零压升驱动、零轴功及电耗，但允许外部压差引起正向或反向通流。运行反流拒绝（`FAN_REVERSE_RUNNING`）；运行高于曲线范围由已有泵曲线门槛拒绝。没有用 `net.pressure_drop` 绕过湿空气能力边界。

输出包括实际压升、流体功率、轴功率、电功率、效率及实际运行状态；`state.electric_energy_j` 和 `state.shaft_energy_j` 仅累计接受步。

### H04 双侧阻力与污垢板换

四个独立端口使用热／冷两个流体回路。参数：`hot/cold_diameter_m` 默认0.04m（显示40mm）；`hot/cold_loss_coefficient` 默认5/12；`clean_ua_w_k` 默认2000W/K（显示2kW/K）；`hot/cold_fouling_resistance_k_w` 默认0K/W。污垢参数是**总热阻K/W**，不是需要另乘换热面积的单位面积热阻。

\[
UA_{eff}=\left(\frac1{UA_{clean}}+R_{f,hot}+R_{f,cold}\right)^{-1}.
\]

清洁UA为0时直接得到零换热。热、冷流量由各自的直径、K及边界压力解出，各自取真实上游密度／比热；换热采用公共SDK的单相ε–NTU关系：`Q=ε Cmin(Th,in−Tc,in)`。设计正向为逆流；只反转一侧时按并流，双侧反转恢复逆流。两侧热量严格等量反向；任一侧零流时不换热。冷热倒置保留Q的符号。

参考方法与独立验证使用标准能量守恒与ε–NTU：LBNL Buildings 库的 `HeatExchangers.BaseClasses.epsilon_ntuZ` 同样按流型及容量比定义有效度。现有SDK实现不是厂家板片模型；新增污垢只描述总UA下降，不自行增加压降。若污堵同时改变水力，应显式修改对应K或另建型号。

输出：有效UA、冷侧得热、热／冷侧压差、接受步累计冷侧得热。普通水与30%乙二醇示例使用 `INCOMP::MEG[0.3]`，不强制共用水的物性。

## 可复算项目与浏览器入口

`examples/hvac-expansion/` 内每个名字均有 `.project.json`（含固定模块源码/合同/哈希）及 `.recipe.json`（设备参数、边界、实际连线）两份：

- `air-branch-dry`、`air-branch-moist`：不等K支路的三口分配。
- `fan-running-dry`、`fan-running-moist`：运行压升250Pa、额定折算风量2000m³/h。
- `plate-water-glycol`：热侧60°C水、冷侧20°C 30%乙二醇，两侧压差20kPa。

这些新包可从模块库逐个插入；边界和参数应按recipe填写。湿空气例须用Air/gas、`thermal=true`、`property_coupling=node`、湿空气合同版本1。风机独立验证台边界必须入口低压、出口高压，不能用阻力设备的入口高压试算。板换独立验证需分别指定两侧边界。

## 定向验收

`tests/test_hvac_expansion.py` 核对：普通／湿空气分流与汇流守恒、独立三腿阻力参考、零流、风机Q/n与效率、完整轴功热账、停机双向阻力、动态启停电量、非法修改不推进状态、板换不同工质与双侧压降、污垢、反转、零流、湿空气拒绝、冻结包无本地路径复算。完整从空白画布组装、保存导入和报告由主集成验收单独记录，不以本文件设备测试替代。

```powershell
python scripts/generate_hvac_expansion.py --check
python -m pytest -q tests/test_hvac_expansion.py
```
