# M2-L3 标定清单：11 项 L3 的采集口径、验收公式与回填落点

> 日期：2026-10-22。范围：`MAPPING_A.md` 的 3 项（P-4、V-4、M-4）与 `MAPPING_C.md` 的 8 项（C-4、E-4、EC-4、V-4 罐体液位、V-7、IC-4、R-4、TX-4），共 11 条 L3。
> 只读证据：倍思鹿 `AlgModule/<模块>/code/<模块>_Run.cpp` 与中文根 `.cpp`；FluidNet `backend/fn_engine/**`（`catalog.py`、`solver.py`、`thermal.py`、`simulation.py`、`refrigeration/*`）与现有测试；`docs/BASELU_REFERENCE_CASES.md` 的 10 个快照 fixture。
> 本文只登记口径与落点，不填任何倍思鹿实测数值，不宣称任何一条"已通过"；未运行倍思鹿任何 `.exe`，未运行全量 pytest（`MAPPING_A.md:6`、`MAPPING_C.md:6` 的边界继续有效）。
> `modules/valve_equal_percentage/` 与 `tests/test_bsl_calibration.py` 已由并行交付落地；本文只规定它们必须满足的公式与断言口径，不重复其实现，也不替它宣称测试结果。

## 1 目的与状态定义

### 1.1 L3 的含义

M2-A/M2-C 已把验收分成三级：**L1** 纯解析、单次编译+求解可断言；**L2** 依赖物性或热力迭代、容差放宽；**L3** 需倍思鹿标定或 CI 全量 job，只登记、不填数值（`MAPPING_A.md:31`、`MAPPING_C.md:31`）。本文处理的就是那 11 条 L3。

L3 与 L1/L2 的差别不在"精度高低"，而在**证据来源**：L1/L2 的期望值可以本地用解析式或 `PropsSI` 复算；L3 的期望值只有三种可能来源——倍思鹿实测、FluidNet 全量动态运行的稳定量、或"目前根本没有可比量"。所以本文的核心不是再写一遍物理，而是把每条 L3 拆成**可采集的变量清单 + 可回填的公式 + 可执行的落点**。

本文不重排优先级、不改写人日，也不改变两份映射文的结论：M2-A 的 17 条可执行 + 3 条 L3（`MAPPING_A.md:370`）与 M2-C 的 23 条可执行 + 8 条 L3（`MAPPING_C.md:431`）保持不变。

### 1.2 三态定义

| 状态 | 判定标准 | CI 中的允许形态 | 解除条件 |
| --- | --- | --- | --- |
| ✅ 已执行 | FluidNet 侧算例能跑，断言能写；数值基准可缺，缺时只断言公式、量纲、自洽性或单调性 | 正常 `assert`，不 skip | 回填 `measured_values` 后追加数值断言 |
| 🟡 待数据 | 断言必须依赖倍思鹿实测值，没有数据就只能断言"结构存在" | `pytest.mark.skip(reason='缺少倍思鹿 measured_values: <字段>')` | 本文 §4 的采集单回填到 fixture |
| ⛔ 阻塞 | 语义不可映射或无接口：采集再多数据也写不出断言，需先改合同或新增对象 | `skip(reason='BLOCKED: <合同缺口>')`，并在 §3 对应小节写明缺口 | 合同决策完成后重新定级，不是"再等等" |

三条纪律：

1. **✅ 不等于与倍思鹿对上**。P-4、V-4 的 ✅ 只说"这条证据现在能进 CI 跑出结果"，数值基准仍待回填；快照不是 oracle（`BASELU_REFERENCE_CASES.md:8-14`）。
2. **三态只描述证据进度，不描述模型质量**。一条 L3 长期停在 🟡 是数据问题，不是模型错误；⛔ 才是"模型能力缺口"。
3. **状态变更必须同时改两处**：本表 §2 的"现状"列、`tests/test_bsl_calibration.py` 里对应测试的 skip 原因；只改一处视为未完成。

### 1.3 与 MAPPING_A / MAPPING_C 的关系

- 本文是两份映射文 L3 行的**展开**，不是替代：P-4（`MAPPING_A.md:177`）、V-4（`:222`）、M-4（`:267`）、C-4（`MAPPING_C.md:132`）、E-4（`:172`）、EC-4（`:212`）、V-4 罐体（`:254`）、V-7（`:291`）、IC-4（`:333`）、R-4（`:375`）、TX-4（`:415`）的输入/期望/容差以原文为准，本文只补"怎么采、怎么算、采完放哪"。
- 原文的"待回填"字样由维护者在回填时改写；本文不改那两份文件，因此不承诺它们与本文状态永远同步。
- 单位与变量命名沿用 `DATA_CONTRACT.md:60-72`（Pa、K、J/kg、kg/s、m³/h）与 `MAPPING_A.md:72-80`（倍思鹿 `VOLUME` 是密度，不是体积）。

### 1.4 证据边界

1. 倍思鹿的关系式大多在 DLL 内不可见（`FudPhyLink.h` / `MODULEAPILINK.h` 只有声明，`MAPPING_A.md:44`），因此本文只使用**可见的调用参数、分支条件、端口/参数索引**，不推断内部关联式。
2. `.PJTDB` 是某时刻快照，不保证收敛（`BASELU_REFERENCE_CASES.md:123-128`），只能当输入/初值/契约对照，不能当期望值。
3. 时间离散不同：倍思鹿 `S_T` 是毫秒级模块步长（`MAPPING_A.md:168`），FluidNet 动态是秒级隐式 Euler（`simulation.py:39-41`）；任何"逐帧对比"都必须先对齐采样间隔。
4. 两相只在设备内部：FluidNet 管网不支持两相支路（`ALGORITHM.md:422`、`devices.py:1-6`），所以 C 类标定的对象是**设备函数与集总容器**，不是管网节点。

## 2 总表（A 类 3 条 + C 类 8 条）

| ID | 模块/主题 | 现状 | 需要倍思鹿侧采集的数据（变量/对象/工况） | 验收公式 | 回填后落点 |
| --- | --- | --- | --- | --- | --- |
| P-4 | 管道动态热容 | ✅ 已执行，τ 待记录 | `MOD0` 管道：`S_T`、`IM0_TEMP`、`EX0_TEMP`，与交付测试同工况（L=30 m、d=0.06 m、UA=3000 W/K、环境 293.15 K） | 稳态 `h_out=h_env+(h_in−h_env)(w/(w+g))^N`、`g=UA/(N·cp)`；动态断言单调/储能/τ（§3.1） | `test_p4_pipe_thermal_cells_dynamic_transient`（`test_bsl_calibration.py`）；fixture `...-mod0-pipe` 的 `measured_values.pipe_p4` |
| V-4 | 截止阀等百分比 | ✅ 已执行（CVF 公式），Kv 基准待标定 | `MOD7`：`VSPACT` 扫描 0.1…1.0、固定 Δp≈0.1 MPa，读 `EX0_FLOW`/`IM0_PRE`/`EX0_PRE`/`DENSITY`/`CV` | `CVF=(ALF^(VSPACT−1)+LF)/(1+LF)−1/ALF`（ALF=100、LF=0）；`kv_eff=kv_rated·CVF`；`kv_rated=Kv_full/0.99`（§3.2） | `test_equal_percentage_characteristic_points`、`test_equal_percentage_flow_ratio_versus_linear_valve`；fixture `...-mod7-valve` 的 `measured_values.valve_v4` |
| M-4 | 泵曲线单位 | 🟡 已分析、待数据 | `MOD8`：`EN=1`、`CURVE_A=0.1`、`CURVE_B=10`，≥3 个流量点（建议 5 点）读 `EX0_PRE`/`IM0_PRE`/`EX0_FLOW` | `Δp(Q)=CURVE_A(1−Q²/CURVE_B²)`；MPa→`H₀=10.214 m`，bar→`1.021 m`（§3.3） | `test_pump_curve_mpa_and_bar_unit_assumptions`；fixture `...-mod8-pump` 的 `measured_values.pump_m4` |
| C-4 | 压缩机排量/效率 | 🟡 待数据 | `MOD1`：`EN=1`、`Opening` 0.5/0.75/1.0、固定吸排气，读 `FORCE_VOLUME`/`FORCE_FLOW`/`POWER`/`EX0_ENTHALPY` | `FORCE_FLOW=FORCE_VOLUME·ROTATE_SPEED·ρ·1e−3·Opening·EN`；令 η=1 反算排量（§3.4） | `test_c4_*`；fixture `...-mod1-compressor` 的 `measured_values.compressor_c4` |
| E-4 | 蒸发器 UA | 🟡 待数据 | 蒸发器 `EN=1` + 所在库房：`OUTTEMP`/`EX0_FLOW`/`IM0_ENTHALPY`/`EX0_ENTHALPY`/`BKT_TEMP` | `UA_eff=m(h_out−h_in)/(T_room−T_evap)`，`T_evap=OUTTEMP−0.5 K`（§3.5） | `test_e4_*`；`fixtures/baselu/measured/e4-evaporator.json` |
| EC-4 | 冷凝器 UA/饱和液 | 🟡 待数据（需两点） | 蒸发式冷凝器：两个负荷、同一环境，读 `OUTTEMP`/`EX0_PRE`/`EX0_FLOW`/`IM0_ENTHALPY`/`EX0_ENTHALPY` | `Q=m(h_in−h_out)`；`UA=(Q₁−Q₂)/(T_c1−T_c2)`，`T_wb=T_c1−Q₁/UA`（§3.6） | `test_ec4_*`；`measured/ec4-condenser.json` |
| V-4 | 罐体液位口径（卧式） | 🟡 待数据 | `MOD46`：2 h 运行，`BKT_LEVEL`/`BKT_M`/`BKT_Q`/`BKT_PRE`/`BKT_DL`/`BKT_DV` 曲线 | `BKT_LEVEL=h/D`；`level_ratio=f(h/D)` 圆筒弓形面积式（§3.7） | `test_v4_tank_*`；fixture `...-mod46-tank` 的 `measured_values.tank_level_v4` |
| V-7 | 立式液位 | 🟡 待数据 | `罐体立式`：2 h 运行，`BKT_LEVEL`/`BKT_M`/`BKT_Q`/`BKT_SR`/`BKT_SH` | `BKT_LEVEL=LEVEL/(2R)`；`level_ratio=BKT_LEVEL·2R/H`（§3.8） | `test_v7_*`；`measured/v7-vertical-drum.json` |
| IC-4 | 中间冷却器闪发 | 🟡 待数据 | 中间冷却器：`BKT_M`/`BKT_Q`/`BKT_PRE`、`EX*_FLOW`、盘管 `IM3/EX4` 流量与焓、高压级吸气 | `x_flash=m_vapor/m_total`；`Q_coil=m_pass(h_IM3−h_EX4)`（§3.9） | `test_ic4_*`；`measured/ic4-intercooler.json` |
| R-4 | 冷库房间 | ⛔ 阻塞（无压力/干度/多端口接口） | 只能采 `BKT_TEMP`/`NUMBER`/`BKT_V`；`BKT_PRE`/`BKT_Q` 在 FluidNet 无对应物 | 仅温度层可比，但 C/UA 需由同一段数据拟合（§3.10） | `test_r4_*` 保持 `skip('BLOCKED: ...')` |
| TX-4 | 膨胀阀 CV 尺度 | 🟡 待数据 | 热力膨胀阀：`TC` 扫描 3/5/8 K、固定 `m`，读 `M_PRE`/`EX0_PRE`/`IM0_PRE`/`CP`/`AV`/`DENSITY` | `Kv_eff=3600·m/√(1000ρΔp/1e5)`，`Δp=IM0_PRE−EX0_PRE`（§3.11） | `test_tx4_*`；`measured/tx4-expansion-valve.json` |

> 编号说明：`V-4` 在 `MAPPING_A.md:222`（截止阀）与 `MAPPING_C.md:254`（罐体液位）中各出现一次，本文沿用原编号，用"V-4"/"V-4 罐体"区分；11 行对应 10 个不同编号。

### 2.1 状态分布与判读

| 状态 | 条数 | 条目 |
| --- | --- | --- |
| ✅ 已执行 | 2 | P-4、V-4 |
| 🟡 待数据 | 8 | M-4、C-4、E-4、EC-4、V-4 罐体、V-7、IC-4、TX-4 |
| ⛔ 阻塞 | 1 | R-4 |

判读时注意三点：

1. ✅ 的 2 条都在 A 类，因为它们只需要"公式 + 本侧算例"就能写断言；C 类没有任何一条现在能进 assert 的数值断言（EC-4 的饱和液子断言除外，但它不解除整条）。
2. 🟡 的 8 条全部卡在"倍思鹿侧一次人工导出"，不是卡在 FluidNet 代码；因此它们的解除时间取决于采集批次，不取决于开发排期。
3. ⛔ 的 1 条（R-4）卡在合同层，采集再多数据也不会变绿；把它和 🟡 混在一起统计会高估 L3 的可完成度。

## 3 逐条小节

### 3.1 P-4 管道动态热容（A 类，✅）

- **现状**：`pipe` 有 `thermal_cells`（0–50，默认 0）与 `wall_heat_capacity_j_k`（`catalog.py:48-50`）；`N>0` 时把管容均分为 N 个单元、壁容也按 N 等分（`thermal.py:257-260`），单元焓按链式线性关系逐单元传递（`thermal.py:378-411`），每帧回写 `state.mean_temperature_k` 与 `state.stored_power_w`（`solver.py:723-740`）。**动态**没有闭合解，但**稳态**有 N 段串联解析式：`h_out=h_env+(h_in−h_env)(w/(w+g))^N`、`g=UA/(N·cp)`——交付测试正是用它做严格对照。
- **交付测试的构造**（`tests/test_bsl_calibration.py` 的 `thermal_capacity_project`）：`L=30 m`、`d=0.06 m`、`ε=45 µm`、`UA=3000 W/K`、`ambient=293.15 K`、`thermal_cells=4`、`C_wall=5e5 J/K`、入口 353.15 K、末端 353.15 K；`t=0` 阀门全关（管内静止、单元初温=入口温度），`ControlScript` 在第一步把 `V1.param.opening_ratio` 写到 1.0，制造**流量阶跃**后管段向"带散热的稳态剖面"冷却。600 s / 1 s 共 601 帧。
- **为什么不是温度阶跃**：边界温度不是运行时可写参数，而阀门开度是（`catalog.py:39` 的 `runtime=True`）。所以交付测试用阀门造流量阶跃；若坚持 `MAPPING_A.md:177` 的 333→353 K 温度阶跃，只能两次编译（先 333 K 跑到平衡、再 353 K 重驱动）或直接调 `solve_thermal(..., storage_step=(dt, {}, cells))`（`thermal.py:146-148`、`:233`）。两条路径激发同一阶系统，但 **τ 不能跨工况比**。
- **变量**：FluidNet 侧 `L1.out0.temperature_k`、`L1.state.mean_temperature_k`、`L1.state.stored_power_w`、`L1.ch0.heat_w`；倍思鹿侧 `MOD0` 的 `IM0_TEMP`/`EX0_TEMP`/`EX0_FLOW`/`S_T`。
- **断言口径**（交付测试现有 5 类）：(a) 601 帧；(b) `outlet[0]=353.15 K`、单调不增；(c) 末帧逐步变化 `<1e-3 K`、10 s 变化 `<1e-2 K`；(d) 稳态出口焓对 N 段解析式 `rel=1e-6`、温度 `abs=0.01 K`；(e) `|stored_power_w|` 从 >1e5 W 衰减到 `<10 W`。τ63 目前只断在 `20 s < τ < 300 s` 的量级带内。
- **容差**：稳态焓 1e-6、温度 0.01 K、储能终值 10 W；**τ 的 20–300 s 只是回填前的量级带**，回填后必须收窄到对 fixture τ 的 ±10%（否则就是 §5 明令禁止的"宽松断言"）。
- **回填目标**：`baselu-nh3co2zl-mod0-pipe.json` 的 `expected_snapshot.measured_values.pipe_p4 = {time_constant_s, steady_outlet_temperature_k, sample_interval_s, run_seconds}` 并把 `convergence_verified` 置 `true`（`BASELU_REFERENCE_CASES.md:91`）；测试 `test_p4_pipe_thermal_cells_dynamic_transient` 增加"读 fixture 断言 τ/稳态"的分支，原量级带降级为兜底。

### 3.2 V-4 截止阀等百分比（A 类，✅ 公式侧）

- **现状**：等百分比特性由并行交付的 `modules/valve_equal_percentage/` 承载（`manifest.json` + `module.py` + `README.md`）：参数 `kv_m3_h=16`、`opening_ratio=0.5`、`rangeability_alf=100`、`leakage_fraction=0`、`density_kg_m3=998.2`；变量 `cvf`、`effective_kv_m3_h`、`state.throughput_kg`；通路 `main` 的 `relation=resistance`、`solver_model=valve`。
- **公式与实现**：`CVF=(ALF^(opening−1)+LF)/(1+LF)−1/ALF`，夹到非负（`module.py:27-29`，对应 `截止阀_Run.cpp:87-88`；`LF=0`（`:69`）时退化为 `100^(VSPACT−1)−0.01`）；然后 `kv_eff=kv_rated·CVF`、`opening=1.0`（`module.py:42-48`），开度 0 或 CVF→0 时改交 `opening=0` 走精确关断（`:34-41`）。代入得 `CVF(1)=0.99`、`CVF(0.5)=0.09`、`CVF(0.1)=0.005849`，与 `MAPPING_A.md:208` 一致。
- **与内置阀的差别**：内置 `valve` 是 `Kv_eff=Kv·opening`，对开度线性（`solver.py:104-106`）；模块把 CVF 折进 Kv、把 `opening` 固定为 1.0，所以两者在 50% 开度的流量比是 `0.09/0.99≈0.0909` 对 `0.5`，差 5.5 倍（交付测试 `test_equal_percentage_flow_ratio_versus_linear_valve` 断言 `linear_ratio/equal_percentage_ratio>5`）。若绕开模块直接用内置阀复刻，等价开度是 `CVF/0.99`，不是 `CVF`；`MAPPING_A.md:222` 取 `opening=0.09`（Q=1.4412 m³/h、m=0.399655 kg/s）就是 CVF 本身，与 0.090909 差 1.0%（尺度差，不影响形状）。
- **仍缺的基准**：`CVF` 是无量纲当量流通面积，`Kv` 是有量纲流量系数，二者的换算在 `VALVECV_SHUT` 内部（`FudPhyLink.h:81`），包内不可见（`MAPPING_A.md:209`）。注意模块在满开时的有效值是 `0.99·kv_m3_h`，所以要让"满开有效 Kv = 物理 Kv_full"，必须填 `kv_m3_h=Kv_full/0.99`；`Kv_full` 只能由倍思鹿实测反算。
- **采集工况**：`MOD7`，`DN=150`、`LF=0`、`AUTO=0`（关掉 ±0.005/步 的开度斜坡，`:46-61`），固定上游 0.5 MPa、下游 0.4 MPa（Δp≈0.1 MPa，介质必须是单相水或过冷氨液；用饱和态会让 `Q` 跨相，`FUD_PH` 的出口状态不可比），`VSPACT` 取 0.1/0.3/0.5/0.7/0.9/1.0 六点，每点跑到流量稳定（建议 ≥60 s 或 `S_T` 的 6000 步）后取一帧。
- **变量**：`VSPACT`、`IM0_PRE`、`EX0_PRE`、`EX0_FLOW`、`IM0_VOLUME`（密度）、`CV`（`VALVECV_SHUT` 回写，仅作旁证）。
- **公式**：`Q=m/ρ×3600`；`Kv_eff=Q/√(Δp·1000/(1e5·ρ))`；`Kv_full=Kv_eff(1.0)`；逐点检查 `Kv_eff(VSPACT)/Kv_full` 与 `CVF(VSPACT)/0.99` 的比值是否恒定。
- **容差**：曲线形状（六点归一化比值）相对误差 ≤3%；`Kv_full` 与样本/铭牌值 ±10%；若 `CV` 与 `Kv_eff` 的比值在同一次运行内恒定为常数，说明 `CV` 就是同一尺度的另一个名字，可把该常数写进模块 `manifest.json` 的 `kv_scale`，否则只保留 `Kv_full`。
- **回填目标**：`baselu-nh3co2zl-mod7-valve.json` 的 `measured_values.valve_v4 = {dn, points:[{vspact, dp_pa, rho_in, q_m3_h, kv_eff}], kv_full_m3_h, kv_param_m3_h}`；现有 `test_equal_percentage_characteristic_points` 与 `test_equal_percentage_flow_ratio_versus_linear_valve` 在回填后追加"`kv_m3_h` 取标定值"的算例（当前只断言 0.99/0.09/0.005849 三个公式点与流量比）。

### 3.3 M-4 泵曲线单位（A 类，🟡）

- **现状**：倍思鹿曲线是二次式 `Δp=A+BQ+CQ²`，`EN>0.5` 时 `A=CURVE_A`、`B=0`、`C=−CURVE_A/CURVE_B²`（`泵曲线法_Run.cpp:25-37`），即 `Δp=CURVE_A(1−Q²/CURVE_B²)`；`DPRE=EX0_PRE−IM0_PRE`（`:88`）。入口夹紧 `CURVE_A≥1e-6`、`CURVE_B≥0.1`（`:17-24`）。快照 `MOD8` 是 `CURVE_A=0.1、CURVE_B=10、R=0.06、EN=0`（`MAPPING_A.md:267`）——**`EN=0` 时 `A=B=C=0`（`:32-37`），泵退化为零压升支路，用这个快照永远标不出扬程**，标定运行必须先把 `EN` 置 1。
- **两种单位假设**：若 `CURVE_A` 是 MPa，则 `H₀=0.1e6/(998.275·9.80665)=10.214 m`；若是 bar，则 `H₀=1.021 m`，两者正好差 10 倍（`MAPPING_A.md:267`）。FluidNet 的 `head_curve` 用 m（`catalog.py:35-36`），所以单位错会让关死点扬程差一个数量级。
- **一次运行判定**：同一台泵、同一转速，读 `EX0_PRE−IM0_PRE` 与 `EX0_FLOW`。在 `Q≈0`（关死点，可把下游阀关到 1% 开度）读到的 `DPRE` 若 ≈1e5 Pa 则 MPa 成立，≈1e4 Pa 则 bar 成立；若落在 1e3 Pa 量级，说明 `CURVE_A` 很可能是"扬程米数"而不是压力，按 `H=CURVE_A` 处理并单独登记（`MAPPING_A.md:253` 只列了 MPa/bar 两种，第三种是运行中才可能暴露的分支）。
- **变量**：`EX0_FLOW`、`IM0_PRE`、`EX0_PRE`、`IM0_VOLUME`（密度）、`EN`、`CURVE_A`、`CURVE_B`、`R`；`DPRE` 是模块回写的输出（`泵曲线法_Run.cpp:88`），只作旁证，不要当输入。
- **曲线采样误差（必须知道的偏差）**：三点点列 `[[0,H₀],[5,0.75H₀],[10,0]]` 在 Q=7.5 处线性插值给 0.375H₀，二次式给 0.4375H₀，**最大偏低 14.3%**。回填时应采 5–6 点（0/2/4/6/8/10），否则 M-4 的容差会被采样误差吃掉。
- **采集工况**：`MOD8` 副本，`EN=1`、`CURVE_A=0.1`、`CURVE_B=10`、`R` 不改；下游阻力从大到小扫 5 点（含关死点），每点稳定后取帧；同时记录 `ROTATE_SPEED`（泵模块没有转速输入，`MAPPING_A.md:248`，只能按 1.0 处理）。
- **公式/容差**：`H(Q)=DPRE/(ρg)`（ρ 取 `IM0_VOLUME`）；单位判定成立后，FluidNet 用同一 `H(Q)` 点列复算 `Δp=−ρgH`（`solver.py:109-112`），逐点 ±2% 或 ±20 Pa（取大者）；关死点单独 ±50 Pa。判据只有一条：**单位假设必须让 5 个点同时落在容差内**，只对上一个点不算判定。
- **回填目标**：`baselu-nh3co2zl-mod8-pump.json` 的 `measured_values.pump_m4 = {curve_a_raw, curve_b_raw, unit_hypothesis, points:[{q_m3_h, dp_pa, rho}], h0_m}`；现有 `test_pump_curve_mpa_and_bar_unit_assumptions` 已固定"10.214 vs 1.021"与两条假设各自的工作点（bar 假设下 50 kPa 已超过关死扬程，改用 5 kPa），回填后在该测试里追加"用实测 `DPRE` 选边、再用 5 点复算"的分支。

### 3.4 C-4 压缩机排量/效率（C 类，🟡）

- **现状**：倍思鹿流量是强制式 `FORCE_FLOW=FORCE_VOLUME·ROTATE_SPEED·IM0_VOLUME·0.001·Opening·EN`（`压缩机_Run.cpp:69`），负值置 0（`:71-74`）；功率 `POWER=m(EX0_ENTHALPY−IM0_ENTHALPY)`（`:28`、`:41`），排气焓由 `FUD_PS(EX0_PRE, entropy)` 得等熵值（`:26`）。**代码里没有容积效率、没有等熵效率、没有电机效率**，这一点与 FluidNet 的 `η_vol=0.8/η_is=0.72/η_motor=0.92` 默认（`catalog.py:389-391`）是语义差，不是数值差。
- **退化风险**：`FORCE_VOLUME` 与 `η_vol` 在 `m=V_d·load·η_vol·ρ`（`cycle.py:26-28`）里只以乘积出现。倍思鹿侧等于 `η_vol=1`，所以标定必须**先令 FluidNet 的 `volumetric_efficiency=1`**，否则排量与效率不可分辨；标出的排量是"含倍思鹿未建模泄漏的等效排量"，与铭牌排量之比记为隐含 `η_v`，**只记录不断言**（铭牌不在包内）。
- **采集工况**：`MOD1`，`EN=1`、`Opening` 取 0.5/0.75/1.0、`ROTATE_SPEED` 记录不改；吸排气边界沿用同一工程副本（快照线索：`EX0_PRE≈1.0714 MPa`、`EX0_FLOW≈0.077505 kg/s`，仅作工况参考，不作期望）；每点稳定 ≥60 s。
- **变量**：`FORCE_VOLUME`、`ROTATE_SPEED`、`Opening`、`IM0_VOLUME`（吸气密度）、`FORCE_FLOW`、`POWER`、`IM0_ENTHALPY`、`EX0_ENTHALPY`、`EX0_PRE`。
- **公式**：`V_d_eq=FORCE_FLOW/(ROTATE_SPEED·ρ_suc·1e−3·Opening·EN)`；三点应给同一 `V_d_eq`（离散度 ≤2%，否则说明 `×0.001` 或 `ROTATE_SPEED` 的口径不是线性）；`η_v,implied=V_d_eq·3600/V_d_nameplate`。等熵效率：FluidNet 令 `η_is=1`、`η_motor=1` 时 `P_shaft=m(h₂s−h₁)`，应与 `POWER` 同值。
- **容差**：`m` ±1%（排量标定后）；`POWER` ±2%；三点排量离散 ≤2%。任何一项超差都先查单位（L vs m³/h vs 每转排量），不要先调效率。
- **回填目标**：`baselu-nh3co2zl-mod1-compressor.json` 的 `measured_values.compressor_c4 = {force_volume_raw, rotate_speed, points:[{opening, rho_suction, force_flow_kg_s, power_w, h_in, h_out}], displacement_m3_s_derived, implied_eta_v}`；测试 `test_c4_displacement_and_isentropic_work`。

### 3.5 E-4 蒸发器 UA（C 类，🟡）

- **现状**：倍思鹿蒸发器**没有 UA、没有空气侧**：`EN≥0.5` 时把出口钉在"出口压力对应饱和温度 +0.5 K"（`蒸发器_Run.cpp:46-53`），换热量完全由网络与上游决定；`EN<0.5` 是等焓旁通（`:17-39`）。FluidNet 的 `air_cooler` 反过来：给定 `ua_w_k` 与库温，`Q=UA_eff(T_room−T_evap)` 并受供液量与干度上限约束（`devices.py:165-182`）。所以 E-4 不是"对比 UA"，而是**由一次倍思鹿运行反算等效 UA**，再把它当 FluidNet 的输入。
- **采集工况**：蒸发器 `EN=1`、`TC` 不改、供液与回气接原工程；同帧记录所在库房 `BKT_TEMP`（`冷库库房_Run.cpp:116-119`，经 `MAPPING_C.md:342`）；稳定 ≥120 s 取一帧（换热量对库温敏感，取稳定段中位数比取末帧稳）。
- **变量**：`OUTTEMP`、`EX0_PRE`、`EX0_FLOW`、`IM0_FLOW`、`IM0_ENTHALPY`、`EX0_ENTHALPY`、房间 `BKT_TEMP`。
- **公式**：`T_evap=OUTTEMP−0.5`（倍思鹿把过热写死在出口，`:47`）；`Q=m(h_out−h_in)`；`UA_eff=Q/(T_room−T_evap)`（`MAPPING_C.md:172` 的口径）。注意 `h_out−h_in` 含 0.5 K 过热的显热，所以 `UA_eff` 是"含过热段"的空气侧等效值，回填时不能同时再把 `superheat_k` 设成 5 K。
- **容差**：`UA_eff` 本身无对照，只要求反算可复现（同一帧重算差 <1e-9）；真正断言在回填后：FluidNet 用该 `ua_w_k` 复算 `Q` ±10%、`T_evap` ±0.5 K。若 `T_room−T_evap` 小于 A 链声明的 `superheat_k`，`superheat_warning` 会给 `CYCLE_SUPERHEAT_APPROACH` 警告（`cycle.py:137-143`，只警告不报错，B 链 `air_cooler` 没有这一项），这类工况要在采集时避开或单独登记。
- **落点**：新增 `tests/fixtures/baselu/measured/e4-evaporator.json`（无 v0 fixture，见 §4 第 4 步的 provenance 规则）；测试 `test_e4_evaporator_ua_from_bsl`，A 链回填到 `condensing_unit.superheat_k=0.5` + `unit_cooler.ua_w_k`（`catalog.py:271`、`:243`）。

### 3.6 EC-4 冷凝器 UA/饱和液（C 类，🟡）

- **现状**：`EN≥0.5` 时 `OUTTEMP=Tsat(EX0_PRE)−0.5`、`FUD_TP` 定出口焓（`蒸发式冷凝器_Run.cpp:45-52`）；没有 UA、没有湿球、没有风机（`MAPPING_C.md:182`、`:194`、`:200`）。FluidNet 的 `evaporative_condenser` 是 `Q=UA_eff(T_cond−T_wb)`（`devices.py:114-122`）。倍思鹿侧 `Q` 可测、`T_cond` 可测、`T_wb` 不可测——**单点不可辨识**（一个方程两个未知数）。
- **两点辨识**：同一环境、同一湿球，取两个不同负荷（改 `Opening` 或下游压力，使 `T_cond` 相差 ≥2 K）：`Q_i=m_i(h_in,i−h_out,i)`、`T_c,i=OUTTEMP_i+0.5`（因为 `OUTTEMP` 比饱和温度低 0.5 K），解 `UA=(Q₁−Q₂)/(T_c1−T_c2)`、`T_wb=T_c1−Q₁/UA`。两点法的误差放大是 `δUA/UA≈(δQ₁+δQ₂)/|Q₁−Q₂|`，所以**先保证 `|T_c1−T_c2|≥2 K` 再谈容差**，否则数据齐了也标不准。
- **采集工况**：两帧，同一工程副本与环境变量（`PjtVarValue` 的 `ChangdiTemp`/`HuanJingTemp`，`BASELU_REFERENCE_CASES.md:29`），负荷分别取额定与约 70%；稳定 ≥120 s 取中位段。
- **变量**：每点 `OUTTEMP`、`EX0_PRE`、`EX0_FLOW`、`IM0_ENTHALPY`、`EX0_ENTHALPY`，以及所在容器的 `BKT_PRE`（旁证压力）。
- **先做的可执行子项**：出口饱和液校验现在就能写——`|OUTTEMP−(Tsat(EX0_PRE)−0.5)|≤0.05 K` 且 `EX0_Q` 在饱和液侧（`EX0_Q≈0`）。这一条不需要倍思鹿数据，属于 🟡 条目里的 ✅ 子断言，但**不解除整条**（UA 仍缺）。
- **容差**：饱和液校验 ±0.05 K；`UA` ±15%、`T_wb` ±1.5 K（两点法本身的放大，不要再收紧）。
- **落点**：`measured/ec4-condenser.json` 的 `points:[{load, out_temp_k, p_pa, m_kg_s, h_in, h_out}], ua_w_k, twb_k`；测试 `test_ec4_condenser_outlet_is_saturated_liquid`（现在可写）与 `test_ec4_condenser_ua_two_point`（回填后）。

### 3.7 V-4 罐体液位口径（卧式）（C 类，🟡）

- **现状**：倍思鹿卧式罐的液位是 `BKT_LEVEL=LEVEL/(2R)`（`罐体卧式_Run.cpp:108`，即"充液高度/直径"）；FluidNet 的 `state.level_ratio` 是"液相体积占比"（`devices.py:62-76`）。卧式圆筒两者非线性：`h/D=0.25 ↔ 0.195501`、`h/D=0.05 ↔ 0.018693`（`MAPPING_C.md:242`，圆筒弓形面积式），直接把 `BKT_LEVEL` 当 `level_ratio` 会在 5% 高度处把液相质量高估 2.675 倍。
- **采集工况**：`MOD46`（fixture 已存在，键数 91），保持原 10 端口拓扑与 `BKT_CORE` 不变，动态 2 h、采样 ≤10 s；让液位从 0.15 缓慢升到 0.85（充液/排液工况由维护者定，不改源工程，另存副本）。
- **变量**：`BKT_LEVEL`、`BKT_M`、`BKT_Q`、`BKT_PRE`、`BKT_DL`、`BKT_DV`、`BKT_SR`、`BKT_SL`，以及几何 `BKT_V`。
- **公式**：令 `x=BKT_LEVEL`，圆筒段体积分数 `f(x)=(acos(1−2x)−(1−2x)√(1−(1−2x)²))/π`；两端半球封头的体积 `V_h=4πR³/3`，总容积按 `罐体卧式_Run.cpp:35` 的 `BKT_V` 计算，再用 `level_ratio=(V_cyl·f(x)+V_head(x))/(BKT_V)` 修正（`V_head(x)` 按球冠高 `x·2R` 计算）。验收只比 `level_ratio` 与 `M`，不比 `h`。
- **容差**：`level_ratio` 绝对 ±0.02（整条曲线 12 个点）；`M` 相对 ±3%；`BKT_PRE` 作为旁证 ±2%（`(M,U)` 反求压力用，`devices.py:62-76`）。
- **落点**：`baselu-nh3co2zl-mod46-tank.json` 的 `measured_values.tank_level_v4 = {sr_m, sl_m, curve:[{bkt_level, bkt_m, bkt_q, bkt_pre}]}`；测试 `test_v4_tank_level_is_volume_fraction`。

### 3.8 V-7 罐体立式液位（C 类，🟡）

- **现状**：立式罐同样写 `BKT_LEVEL=LEVEL/(2R)`（`罐体立式.cpp:356`），但立式等截面的体积分数应是 `LEVEL/H`，所以该口径系统性偏大 `H/(2R)`：`V=4 m³、H=2 m` 时 `R=0.969944`，满罐给 `BKT_LEVEL=1.031`（103.1%），FluidNet 给 `1.0`，偏差 3.1%（`MAPPING_C.md:280`、`:290`）。
- **采集工况**：`罐体立式` 9 端口拓扑不变，`BKT_SH=2 m`、`BKT_SR≈0.97 m`，动态 2 h、采样 ≤10 s，液位扫过 0.2–0.95。
- **变量**：`BKT_LEVEL`、`BKT_M`、`BKT_Q`、`BKT_PRE`、`BKT_DL`、`BKT_SR`、`BKT_SH`。
- **公式**：`level_ratio=BKT_LEVEL·2R/H`（等价于 `BKT_LEVEL·BKT_SR/BKT_SH`）；反过来 FluidNet→倍思鹿是 `BKT_LEVEL=level_ratio·H/(2R)`。把满罐的 `BKT_LEVEL=1.031` 代回该式，正好得 1.000——这就是换算正确性的判据（原样照抄会得到 103% 的液位）。
- **容差**：`level_ratio` 绝对 ±0.02；并单独断言"换算不是恒等"：满罐 `BKT_LEVEL≥1.02`，防止实现回退成直接复制。
- **落点**：`measured/v7-vertical-drum.json` 的 `measured_values.vertical_level_v7 = {sr_m, sh_m, curve:[{bkt_level, bkt_m, bkt_q}]}`；测试 `test_v7_vertical_level_uses_two_radius_scale`。

### 3.9 IC-4 中间冷却器闪发（C 类，🟡）

- **现状**：倍思鹿中间冷却器是"容器 + 盘管 + 液位分档"：盘管换热量 `Tra_H=(IM3_ENTHALPY−EX4_ENTHALPY)·EX4_FLOW`（`中间冷却器_Run.cpp:28-29`），并入容器能量（`:93`）；容器液位 `BKT_LEVEL=LEVEL/BKT_SH`（`:136`，与卧式/立式都不同）；液位在 `H/4、H/2、3H/4` 处切换出口取气/取液，并给 `IM0/IM1/IM2` 加 `ρgH/4, /2, 3H/4` 静压（`中间冷却器.cpp:488-490`）。FluidNet 用 `lp_drum` + `cascade_exchanger` 组合（`catalog.py:377-382`、`:424-435`），盘管一侧接另一回路（`station.py:180-182`），液位不再改变出口相态。
- **可比的量**：闪发气比例 `x_flash=m_vapor/m_total`（IP 桶气相去高压级吸气的流量 / 总回气）与盘管换热量 `Q_coil`。不可比的是液位分档与静压分层（`MAPPING_C.md:321-322`），所以 IC-4 只标这两个量，不标"第几路出口"。
- **采集工况**：两级 NH3、中间 −5 °C（`BSL_MODULE_MAP.md:40`），容器液位落在 `H/4–H/2` 中段（避开分档切换点，否则同一液位会对应两种出口相态），稳定 ≥300 s 取 3 帧。
- **变量**：`BKT_M`、`BKT_Q`、`BKT_PRE`、`BKT_TEMP`、`EX0–EX4` 的 `FLOW`、盘管 `IM3_FLOW/EX4_FLOW`、`IM3_ENTHALPY/EX4_ENTHALPY`、高压级吸气 `EX0_FLOW`。
- **公式**：`x_flash=m_HP_suction/m_LP_return`；`Q_coil=m_pass(h_IM3−h_EX4)`（注意符号：`Tra_H` 在焓升时为负，`:28` 的注释）；FluidNet 侧用 `cascade_exchanger` 的 `heat_w` 与 `evaporated_kg_s` 对照（`catalog.py:432-435`）。
- **容差**：`x_flash` ±10%（相对）；`Q_coil` ±5%；3 帧之间的漂移 ≤3%（漂移大说明还没稳定，数据作废而不是放宽容差）。
- **落点**：`measured/ic4-intercooler.json` 的 `measured_values.intercooler_ic4 = {p_ip_pa, t_ip_k, flash_gas_kg_s, total_return_kg_s, coil_m_kg_s, coil_h_in, coil_h_out}`；测试 `test_ic4_intermediate_flash_and_coil_duty`。

### 3.10 R-4 冷库房间（C 类，⛔）

- **阻塞点（三条，缺一不可解除）**：
  1. **物理对象不同**：倍思鹿房间是"定容两相流体罐 + 单一内热源"——`BKT_V=BKT_LL·BKT_LH·BKT_LW`（`冷库库房_Run.cpp:38`），能量只加 `NUMBER`（`:87`），`T/p` 由 `FUD_DH(BKT_D,BKT_H,...)` 反求（`:118`，口径见 `MAPPING_C.md:342`）；FluidNet 房间是"空气 + 货物两热节点 + 围护/地面/开门/照明/融霜"（`catalog.py:193-237`、`cold_store.py:352-397`）。两者只共用"库温"一个标量。
  2. **接口不存在**：倍思鹿房间有 15 个流体端口 + 1 个信号口（`EX7`），FluidNet 只有一个 `heat` 入端口（`catalog.py:196`）；`BKT_PRE`/`BKT_Q`/液位在冷库域**没有任何对应变量**。
  3. **断言会退化**：若用倍思鹿的 `BKT_TEMP` 曲线去拟合 FluidNet 的 `heat_capacity_j_k` 与 `wall_ua_w_k`，再断言"复现这条曲线"，等于用数据拟合自己的参数——这不是标定，是把两套物理强行换元（`MAPPING_C.md:377` 已把房间模型定性为"换元"而非移植）。
- **合同层缺口**：`ALGORITHM.md:422` 明确"气液两相闭式罐"不在计划内，所以不能靠新增一个两相房间对象绕过去；可行的只有两条路——(a) 新增"两相定容房间"合同对象并给出压力/干度接口；(b) 明确接受"换元"，把 R-4 降级为 🟡 的**黑箱温度比对**（只比 2 h 末库温，且 FluidNet 的 C/UA 由设计工况给定、不由本数据拟合）。两者都是合同决策，不是采集能解决的。
- **若走 (b) 的最小协议（仅登记，不计入本条解除）**：采 `BKT_V`、`NUMBER`、初温、2 h 后 `BKT_TEMP`（`BKT_PRE` 不采，无对应物）；断言 `|T_FN(2h)−T_BSL(2h)|≤1 K`，且 FluidNet 侧 `heat_capacity_j_k` 与 `wall_ua_w_k` 必须来自设计值而非本曲线。
- **CI 形态**：`test_r4_room_temperature_blackbox` 保持 `skip(reason='BLOCKED: 房间为定容两相罐，无 pressure/quality/multi-port 接口；见 M2_L3_CALIBRATION.md §3.10')`，不得改成 `xfail`（xfail 会给"将来可能通过"的错觉）。

### 3.11 TX-4 膨胀阀 CV 尺度（C 类，🟡）

- **现状**：倍思鹿是静态经验式：`CP=0.02005√ρ_in+6.34·EX0_CV`（`热力膨胀阀_Run.cpp:58`）、`AV=(1.9+0.28·TC)·1e−6`（`:60`）、`M_PRE=IM0_CV·IM0_FLOW²/CP²/AV²`（`:62`）、`EX0_PRE=IM0_PRE−M_PRE`（`:66`）；`TC` 只读不调，没有"过热度→开度"闭环（`MAPPING_C.md:385`）。FluidNet 是 `m=Kv·opening·√(1000ρΔp/1e5)/3600`（`devices.py:125-134`），开度与 Kv 线性。
- **不要拟合 `CV`**：`MAPPING_C.md:403` 已算过——`ρ=580、CV=0.5、TC=5、m=0.05` 时该式给 `M_PRE=8.6023e6`，反解 1.2 MPa 需 `CV≈0.0697`，说明 `CV` 不是 Kv、公式内嵌未公开尺度。TX-4 只能从**测得的 Δp** 走，不碰 `CV`。
- **采集工况**：固定入口饱和液（同一 `IM0_PRE`、同一 `m`），`TC` 取 3/5/8 K 三点（`TC` 是蒸发器出口过热度，需与蒸发器一并稳定），每点稳定 ≥120 s。
- **变量**：`TC`、`IM0_FLOW`、`IM0_PRE`、`EX0_PRE`、`IM0_VOLUME`（ρ_in）、`CP`、`AV`、`EX0_CV`。
- **公式**：`Δp=IM0_PRE−EX0_PRE`；`Kv_eff=3600·m/√(1000·ρ_in·Δp/1e5)`；FluidNet 内置阀同式（`solver.py:104-106`），所以 `Kv_eff` 可直接当 `kv_m3_h×opening` 的等效值。三点 `Kv_eff` 若随 `TC` 单调上升且近似线性（`AV` 随 `TC` 线性，`:60`），把 `Kv_eff(TC)=Kv₀(1+k·(TC−5))` 的两参数写进 `manifest.json`；若三点落在 ±15% 内，则常数 `Kv` 就够，不必加参数。
- **容差**：`Kv_eff` 拟合残差 ±15%（三点）；`Δp` 复算 ±10%；`m` 复算 ±10%。超差时先查 `ρ_in` 用的是入口液密度还是平均密度（倍思鹿用 `DENSITY=(IM0_VOLUME+EX0_VOLUME)/2`，`:55`，与 `CP` 里的 `IM0_VOLUME` 不是同一个量）。
- **落点**：`measured/tx4-expansion-valve.json` 的 `measured_values.tx4 = {points:[{tc_k, m_kg_s, p_in_pa, p_out_pa, rho_in, cp, av}], kv0_m3_h, kv_tc_slope_per_k}`；测试 `test_tx4_expansion_valve_kv_scale`。

## 4 数据采集模板

### 4.1 倍思鹿侧导出清单

| 项目 | 对象 | 变量（端口/容器/状态） | 单位 | 时间步/采样 | 保存方式 |
| --- | --- | --- | --- | --- | --- |
| P-4 管道热容 | `MOD0` | `IM0_TEMP`、`EX0_TEMP`、`EX0_FLOW`、`S_T` | ℃、℃、kg/s、ms | 与 `S_T` 同步，再降采样到 1 s | 一列一变量 CSV + 阶跃时刻单独标注 |
| V-4 阀门曲线 | `MOD7` | `VSPACT`、`IM0_PRE`、`EX0_PRE`、`EX0_FLOW`、`IM0_VOLUME`、`CV` | 1、MPa、MPa、kg/s、kg/m³、1 | 每点稳定后单帧 | 一点一行 CSV（工况表） |
| M-4 泵曲线 | `MOD8` | `EN`、`CURVE_A/B`、`EX0_FLOW`、`IM0_PRE`、`EX0_PRE`、`IM0_VOLUME` | 1、原始、kg/s、MPa、MPa、kg/m³ | 每点稳定后单帧 | 一点一行 CSV + 原 `.PJTDB` 副本 |
| C-4 压缩机 | `MOD1` | `FORCE_VOLUME`、`ROTATE_SPEED`、`Opening`、`FORCE_FLOW`、`POWER`、`IM0/EX0_ENTHALPY`、`EX0_PRE` | 原始、rpm?、1、kg/s、W、kJ/kg、MPa | 稳定 ≥60 s 取中位帧 | 一点一行 CSV；`ROTATE_SPEED` 单位必须注 |
| E-4 蒸发器 | 蒸发器 + 库房 | `OUTTEMP`、`EX0_PRE`、`EX0_FLOW`、`IM0_ENTHALPY`、`EX0_ENTHALPY`、库房 `BKT_TEMP` | ℃、MPa、kg/s、kJ/kg、kJ/kg、℃ | 1 s，取稳定段中位数 | 双对象同时间戳 CSV |
| EC-4 冷凝器 | 蒸发式冷凝器 | `OUTTEMP`、`EX0_PRE`、`EX0_FLOW`、`IM0/EX0_ENTHALPY`、容器 `BKT_PRE` | ℃、MPa、kg/s、kJ/kg、MPa | 1 s × 2 个负荷 | 两段 CSV，段首记环境变量 |
| V-4 卧式液位 | `MOD46` | `BKT_LEVEL`、`BKT_M`、`BKT_Q`、`BKT_PRE`、`BKT_DL`、`BKT_DV` | 1、kg、1、MPa、kg/m³ | ≤10 s × 2 h | 整段 CSV（含几何列） |
| V-7 立式液位 | `罐体立式` | `BKT_LEVEL`、`BKT_M`、`BKT_Q`、`BKT_PRE`、`BKT_SR`、`BKT_SH` | 1、kg、1、MPa、m、m | ≤10 s × 2 h | 整段 CSV |
| IC-4 中间冷却 | 中间冷却器 + 高压级 | `BKT_M/Q/PRE/TEMP`、`EX0–EX4_FLOW`、`IM3/EX4_FLOW/ENTHALPY`、高压级 `EX0_FLOW` | kg、1、MPa、℃、kg/s、kJ/kg | 1 s × ≥300 s | 双对象同时间戳 CSV |
| R-4 房间 | `MOD53` | `BKT_TEMP`、`NUMBER`、`BKT_V`（`BKT_PRE/Q` 不采） | ℃、W、m³ | 60 s × 2 h | 单列 CSV + 设计值表 |
| TX-4 膨胀阀 | 热力膨胀阀 + 蒸发器 | `TC`、`IM0_FLOW`、`IM0_PRE`、`EX0_PRE`、`IM0_VOLUME`、`CP`、`AV` | K、kg/s、MPa、MPa、kg/m³、1、m² | 每 `TC` 稳定 ≥120 s 单帧 | 一点一行 CSV |

单位提醒：倍思鹿端口是 MPa / kJ·kg⁻¹ / ℃ / kg·m⁻³，`VOLUME` 是**密度**（`MAPPING_A.md:40`、`:75-79`）；FluidNet 一律 Pa / J·kg⁻¹ / K / kg·m⁻³（`DATA_CONTRACT.md:60-70`）。导出的第一件事是单位换算并写回列名，不是先看数值。

### 4.2 导出后的回填流程

1. **另存副本，不碰源工程**：在倍思鹿里另存 `<工程>_L3` 副本，记录拓扑、模块型号、工质、边界与初值；源 `.PJTDB` 保持只读（`BASELU_REFERENCE_CASES.md:89`）。
2. **一份运行一份日志**：CSV 旁边必须同时存迭代次数、残差/收敛判据、运行时长与保存时刻；没有收敛记录的数据不进 fixture（`BASELU_REFERENCE_CASES.md:90`）。
3. **写进 `measured_values`**：只写 `expected_snapshot.measured_values`（新增字段），`variables` 保留原输入快照不动，`convergence_verified` 改 `true`，`provenance` 追加运行批次与导出文件 sha256（`BASELU_REFERENCE_CASES.md:91-92`）。
4. **没有 v0 fixture 的项**（E-4/EC-4/V-7/IC-4/TX-4）放到 `tests/fixtures/baselu/measured/<id>.json`，`provenance` 用独立字符串（例如 `"Beisilu run <batch>; exported by hand; exe not executed by FluidNet"`）。**不要复用** `"PJTDB snapshot; 未运行倍思鹿"`——那是现有快照契约的固定值（`BASELU_REFERENCE_CASES.md:111`），混用会让"快照 vs 实测"失去区分度。
5. **测试从 skip→assert**：删掉对应 `reason` 的字段名，把本节的容差写成 `pytest.approx`；一次只解除一条，避免一条坏数据掩盖另外十条。
6. **回写映射文**：由维护者在 `MAPPING_A.md:177/222/267` 与 `MAPPING_C.md:132/172/212/254/291/333/375/415` 的"待回填"处改成实测值或指向 fixture；本文不改那两份文件。

### 4.3 采集结果与现有 fixture 的对应

| 项目 | 目标文件 | 现状 | 备注 |
| --- | --- | --- | --- |
| P-4 | `tests/fixtures/baselu/baselu-nh3co2zl-mod0-pipe.json` | 已有快照，缺 `measured_values` | 追加 `pipe_p4` |
| V-4 | `tests/fixtures/baselu/baselu-nh3co2zl-mod7-valve.json` | 已有快照（32 键，`sdd` 缺），缺 `measured_values` | 追加 `valve_v4` |
| M-4 | `tests/fixtures/baselu/baselu-nh3co2zl-mod8-pump.json` | 已有快照，缺 `measured_values` | 追加 `pump_m4`；`EN` 必须由 0 改 1 另存副本 |
| C-4 | `tests/fixtures/baselu/baselu-nh3co2zl-mod1-compressor.json` | 已有快照，缺 `measured_values` | 追加 `compressor_c4` |
| E-4 | `tests/fixtures/baselu/measured/e4-evaporator.json` | 无 v0 fixture | 新建，独立 `provenance` |
| EC-4 | `tests/fixtures/baselu/measured/ec4-condenser.json` | 无 v0 fixture | 新建，两点同文件 |
| V-4 罐体 | `tests/fixtures/baselu/baselu-nh3co2zl-mod46-tank.json` | 已有快照，缺 `measured_values` | 追加 `tank_level_v4` |
| V-7 | `tests/fixtures/baselu/measured/v7-vertical-drum.json` | 无 v0 fixture | 新建 |
| IC-4 | `tests/fixtures/baselu/measured/ic4-intercooler.json` | 无 v0 fixture | 新建 |
| R-4 | `tests/fixtures/baselu/baselu-nh3co2zl-mod53-cold-store.json` | 已有快照，**不新增** | ⛔ 期间只保留原快照 |
| TX-4 | `tests/fixtures/baselu/measured/tx4-expansion-valve.json` | 无 v0 fixture | 新建，三点同文件 |

`measured/` 子目录是新增的：现有 10 个 fixture 的契约测试只认同一个 `provenance`（`BASELU_REFERENCE_CASES.md:111`），所以实测文件必须另起一个目录与另一套 `provenance`，不要塞进原 10 个文件的同一字段里假装"还是快照"。

## 5 与 CI 的关系

1. **执行位置**：已执行项进 `tests/test_bsl_calibration.py`，由 `.github/workflows/ci.yml:49-50` 的全量 backend job（`python -m pytest -q --cov=fn_engine ...`，工作目录 `fluidnet-prototype-engine`，`ci.yml:26-28`、Python 3.11，`:33`）执行；ruff 的检查范围含 `tests`（`ci.yml:41`），所以新文件必须过 lint。
2. **`bsl-modules` job 不跑本文件**：`.github/workflows/bsl-modules.yml:56` 只显式跑 `test_bsl_modules*.py` 与 `test_control_templates.py`，paths 过滤（`:11-25`）也不含 `tests/test_bsl_calibration.py`。并行交付虽然把本文件与本测试放进了该 workflow 的 **artifact 打包清单**（`:80`、`:85`），但那只是随包发布，不执行。若要快速反馈，需把该文件加进 paths 与 pytest 命令——属 CI 配置改动，本文不改，留给维护者决定；在此之前它只由 `ci.yml` 的全量 backend job 覆盖。
3. **禁止假通过**：缺数据用 `pytest.mark.skip(reason='缺少倍思鹿 measured_values: <字段>')`；⛔ 用 `skip(reason='BLOCKED: ...')`；确知实现未完成且断言方向已定才用 `xfail(strict=True)`，**不允许 `strict=False`**。禁止 `assert True`、`if not data: return`、把容差放到 50% 来"变绿"。
4. **✅ 项的断言必须"有牙"**：P-4 现有五类（帧数 601、单调不增、末段变化率、稳态对 N 段解析式 1e-6、储能衰减到 <10 W）；V-4 现有三类（CVF 三点、50% 流量比 0.0909、质量守恒 + 关系种类 `valve`）。这几条不依赖倍思鹿数据，是覆盖率与回归的实际来源。**唯一需要后续收紧的是 P-4 的 `20<τ<300 s`**——回填前它是量级兜底，回填后必须换成对 fixture τ 的 ±10% 断言。
5. **覆盖率**：floor 85%（`pyproject.toml:44`）。skip 的测试不计覆盖，所以 🟡/⛔ 条目不会帮忙；新增的 ✅ 断言要真正执行到分支，而不是被 `skipif` 掉。
6. **命名与追溯**：测试名统一 `test_<id小写>_<主题>`，与本文 §2 的 ID 一一对应（如 `test_p4_pipe_thermal_cells_dynamic_transient`、`test_equal_percentage_characteristic_points`）；每条 skip 的 reason 里必须带本文 §3 的小节号，便于按 ID 反查。文件内的分组注释（`# --- 4. P-4 动态热容 ---` 等）比函数名稳定，改名时以分组为准。
7. **数值断言只在回填后出现**：回填前允许断言"量纲/形状/单调/稳态"，不允许断言"与倍思鹿一致"；回填后允许断言的也只有本文 §3 给出的容差，不允许临时收紧或放宽。
8. **三种写法的样板**（`tests/test_bsl_calibration.py` 内可照抄，替换字段名与断言体）：

```python
# 缺数据：跳过，reason 里必须带 §3 小节号与缺失字段名
@pytest.mark.skip(reason='缺少倍思鹿 measured_values.compressor_c4（见 M2_L3_CALIBRATION.md §3.4）')
def test_c4_displacement_and_isentropic_work(): ...

# 阻塞：跳过，reason 里写明合同缺口；不要改成 xfail
@pytest.mark.skip(reason='BLOCKED: 房间为定容两相罐，无 pressure/quality/multi-port 接口（§3.10）')
def test_r4_room_temperature_blackbox(): ...

# 已可执行：不 skip、不放宽，断言只依赖本侧公式与自洽性
def test_equal_percentage_characteristic_points():
    assert evaluate(half_open).variables['cvf'] == pytest.approx(0.09, abs=1e-12)
    ...
```

## 6 风险与假设

1. **快照不是 oracle**：`.PJTDB` 是某一时刻的状态，不保证收敛（`BASELU_REFERENCE_CASES.md:8-14`、`:123-128`）。`MOD1/MOD7/MOD8/MOD46` 的索引 0 值只能作工况线索，不能作期望；本文引用它们时都标了"参考"。
2. **不运行倍思鹿 exe**：所有倍思鹿数据由人手工导出，FluidNet 侧不调用、不自动化 `.exe`（`MAPPING_A.md:6`、`MAPPING_C.md:6`）。因此"采集"是一个人工批次，本文的 `run_batch`/`sha256` 就是为批次追溯留的。
3. **单位与量纲先核对**：MPa↔Pa、℃↔K、kJ/kg↔J/kg、`VOLUME`=密度、`DN` 是 mm。M-4 的单位判定、TX-4 的 `ρ_in` 选择、C-4 的 `×0.001` 都是"单位错就整条结论错"的位置，先核单位再谈容差（`DATA_CONTRACT.md:60-72`、`MAPPING_A.md:72-80`）。
4. **两相只在设备内部**：FluidNet 不做两相支路（`ALGORITHM.md:422`），所有 C 类标定都落在设备函数/集总容器上；把倍思鹿端口的两相状态搬进支路会直接报 `PHASE_UNSUPPORTED`（`MAPPING_A.md:167`）。
5. **时间离散不可对齐**：倍思鹿 `S_T` 毫秒、FluidNet 秒级隐式 Euler（`MAPPING_A.md:168`、`simulation.py:39-41`）。P-4/V-4tank/V-7 这类动态项，先降采样到同一采样间隔再比，否则比的是插值误差。
6. **两点法的条件数**：EC-4 的 `UA/T_wb` 辨识在 `|T_c1−T_c2|<2 K` 时会放大到不可用；这不是"数据不够多"，是"数据不够散"。同理 P-4 的 τ 在 600 s 内若未走过 63.2%，拟合值没有意义。
7. **效率语义不可互比**：倍思鹿压缩机/泵没有效率参数（`压缩机_Run.cpp:69`、`泵曲线法_Run.cpp:92`），FluidNet 的 `η_vol/η_is/η_motor` 是目录默认（`catalog.py:389-391`）。C-4/M-4 的标定必须显式把 η 置 1 再比，否则差的是定义不是模型。
8. **假设清单**：工质为单相液（P-4/V-4/M-4/TX-4 的液侧）、NH3 为 C 类默认工质、`ρ` 用 `reference` 模式常数（`solver.py:20-22`）、倍思鹿 `S_T` 按 ms 理解、`FORCE_VOLUME` 的单位待 C-4 定、`CURVE_A` 的单位待 M-4 定。任何一条被推翻，对应小节的容差要重新推导，而不是沿用。

## 7 下一步顺序

1. **第一步：C-4 与 M-4 两次最小运行**（各 1 台设备、1 张工况表）。C-4 判定 `FORCE_VOLUME` 的口径并给出 `displacement_m3_s_derived`；M-4 用关死点 `DPRE` 判定 MPa/bar 并给出 5 点 `H(Q)`。这两条是"单位/排量"级问题，错一位后面全错，必须先做；做完把 `test_c4_*`、`test_m4_*` 从 skip 改 assert。
2. **第二步：V-4 与 TX-4 的特性曲线**（各 6 点 / 3 点，一次装夹可连续采）。V-4 出 `Kv_full` 与六点归一化曲线，回填后 `valve_equal_percentage` 才能从"公式对"升级为"尺度对"；TX-4 出 `Kv_eff(TC)`，决定是否需要两参数。顺序上先 V-4（单相液、稳定快）后 TX-4（要等蒸发器过热度稳定）。
3. **第三步：E-4 与 EC-4 的换热 UA**（E-4 一点 + EC-4 两点，需要库房/环境同帧数据）。EC-4 必须凑够 `|T_c1−T_c2|≥2 K` 再采，否则重跑；E-4 的 `UA_eff` 要写清"含 0.5 K 过热"，回填时同步把 A 链 `superheat_k` 设 0.5。
4. **并行批次：V-4 罐体、V-7、IC-4 的 2 h 动态**（不占关键路径，可与第 2–3 步并行；每台设备单独一份 CSV）。这三条依赖液位稳定与采样密度，之所以不放在前面，是因为它们最容易因为"没稳定"而整批作废，作废一次的时间成本远高于前三条。
5. **第五步：R-4 走合同决策**，不是采集任务。要么新增"两相定容房间"对象，要么正式接受"换元"并降级为黑箱温度比对；在此之前 `test_r4_*` 保持 ⛔ 的 skip，不要用拟合参数把它"做绿"。
6. **收尾**：11 条全部有归属后，由维护者统一回写 `MAPPING_A.md`/`MAPPING_C.md` 的"待回填"，并把本文 §2 的现状列更新为最终态；本文不预先改写那两份文件。
