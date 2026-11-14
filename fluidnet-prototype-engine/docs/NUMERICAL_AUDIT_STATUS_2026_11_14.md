# Issue #13 数值修复与验收状态

日期：2026-11-14。关联 [issue #13](https://github.com/kongbaifan/fluidnet/issues/13)。审阅与本地验证工作基线为 `7cacadf346533cbc2bb27a51bb9fbc9bc8b4568d`；独立合并分支从 `master@42691341cbe5dbbd925c4c552dae373feddf88bc` 建立，核心数值修复提交为 `919971aff328f89fc82512a966445317ed9f1066`。控制回归与验收记录按独立提交维护。

## 已完成修复

| 条目 | 实现与证据 |
| --- | --- |
| 奇异 Newton 线性系统 | 制冷站、冷库先重建 Jacobian 并重试；失败转换为领域诊断，进入既有缩步/第二初值机制。固定步、自适应、已接受帧后的持续失败均有正式回归。 |
| 焓零点与能量门 | 全局、水箱、气垫罐的验收尺度改用实际焓差、热流和储能变化；不同回路可独立平移参考零点。故障注入验证相同缺陷在不同参考下均被拒绝。 |
| 耦合黏度与流量门 | 液体 node 耦合及湿空气独立检查黏度和流量；新相对容差默认 1e-6，流量结合既有绝对质量容差。最终缺陷进入帧指标和失败信息。 |
| 最终状态一致性 | 非线性热力最终固定点门直接使用配置温差容差；湿空气设备评估与房间账本使用接受状态，并同步复核守恒。 |
| 曲线泵范围 | 活动曲线泵使用有界体积流量坐标；质量守恒和缓存保留 kg/s。小图 Jacobian 对实际方程差分，包含密度与体积流量换算；标量求解也使用声明范围。 |
| 默认与 schema 兼容 | 保留历史固定步哈希，新增 PID 手动输出观察字段单独断言。新耦合容差为可选扩展，默认项目 JSON 保持原格式；原模型层次和 foundation 基线保留。 |

上述故障注入验证真实引擎的接受与恢复合同，不代表自然工况或现场设备已触发相同缺陷。

## 控制与曲线泵补充

126 设备组合回归将故障窗口缩短到 60–240 秒，分别验证工作泵和低级压缩机。停止命令、首次观察、备用启动采样分别为 60、90、120 秒；恢复及备用退出采样为 240、270 秒。换序和多个接受边界的快照续算一致。

泵恢复时曾找到声明曲线之外的根：34.107 m³/h，高于上限 31.494 m³/h。有界体积流量求解在原曲线数据下得到有效工作点；连续和恢复路径流量约为 5.36039 kg/s。收口审阅另补小图坐标导数与单泵标量路径回归。

控制语义、原始运行日的预期采样及输出帧时刻见 [六库持续仿真说明](SIX_ROOM_CONTINUOUS_SIMULATION.md)。短程组合回归不替代原始运行日事件附近的完整物理验证。

## 最后一次定向检查

| 检查 | 结果 |
| --- | --- |
| 核心接受门、历史哈希、模型与接口合同 | 159 passed |
| 曲线坐标、小图 Jacobian、图式网络与冷媒流股 | 20 passed |
| 组合控制、快照与融霜相关回归 | 20 passed |
| CI 规划 Node 单测 | 8 passed |
| Ruff、Mypy 后端与严格会话/执行器边界 | 通过 |
| 已登记生成器只读一致性 | 15 个通过 |
| 差异空白检查 | 通过 |

最终三组 Python 检查合计 199 项，无失败或跳过；不与早先 250/340/475/83 项阶段记录相加。新增独立 Jacobian 回归在修正前曾发现约 0.812 的归一化导数误差，修正后在单相平滑区通过原 1e-4 比较门。

本地日志、JUnit XML 与审阅证据位于工作区 `output/issue-13-closeout-2026-11-14/`。检查使用 CPython 3.11、NumPy 2.3.2、SciPy 1.17.1、CoolProp 8.0.0、pytest 8.4.1；在 `fluidnet-prototype-engine` 根目录复现：

```powershell
py -3.11 -m pytest tests/test_refrigeration_linear_failures.py tests/test_thermal_energy_datum.py tests/test_coupling_acceptance.py tests/test_refrigeration_curve_bounds.py tests/test_timestep_station.py::test_old_fixed_step_path_is_bit_identical_to_v050 -q
py -3.11 -m pytest tests/test_six_room_continuous.py tests/test_session_checkpoints.py tests/test_station_defrost.py -q
py -3.11 scripts/generated_artifacts.py --verify
node scripts/ci-quick.mjs --check
```

## 保留的未完成项

- 86,520 秒完整六库运行日未通过。第一次尝试保留的接受时刻为 14,430 秒，首次融霜附近报 `NETWORK_NOT_CONVERGED`；被拒绝候选的质量残差为 1.59176e-7 kg/s，压力残差约 0.00154916 Pa。已接受轨迹的残差峰值与被拒绝候选残差分别记录。
- 该次运行未到达 35,970/36,000/36,030 秒、43,170/43,200/43,230 秒及跨日快照检查点。不能把缩短窗口回归写成这些原始时刻已验收。
- 51/126 设备的完整时间步网格收敛与累计能耗对照未完成；19/20/21 边对比仅有代表性静态等价网络证据，未覆盖全部图网络与切换工况。

完整运行尝试的项目、轨迹、控制采样、检查点与失败摘要保留在工作区 `output/issue-13-control-2026-11-14/full-day-attempt-1/`；仓库摘要为 [continuous-validation-summary.json](../examples/large-cold-store/continuous-validation-summary.json)。2,400 秒待冻货物和 480 秒高级机泵备用切换辅助工况通过，分别保留在 `auxiliary-attempt-1/`。

本次收口未继续排查或重启长跑，也未运行全仓 pytest。Issue #13 的完整退出条件尚未全部满足，不能据此关闭。
