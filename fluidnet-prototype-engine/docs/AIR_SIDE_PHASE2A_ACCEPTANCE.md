# 风侧 Phase 2a 验收：湿空气与湿工况

日期：2026-10-28。范围：[风侧开发计划](AIR_SIDE_DEVELOPMENT_PLAN.md) 的 Phase 2a（湿空气含湿量输运、湿工况表冷器、加湿器）。Phase 2b（房间湿负荷、冷却塔水耗、结果视图）未实施。

## 交付

| 项 | 位置 |
| --- | --- |
| 湿空气物性与状态换算（Magnus 饱和压力、含湿量/相对湿度/露点、h↔T、混合物密度/比热） | `backend/fn_engine/moist_air.py` |
| `SolverOptions.moist_air` 开关与编译期校验（Air 气相、边界含湿量不超饱和） | `models.py`、`compiler.py` |
| 含湿量输运（节点混合/边界/逐端口输出）与水分账 | `thermal.py`、`solver.py` |
| 湿工况表冷器 `cooling_coil`（旁通系数法，显热/潜热/凝水/SHR） | `catalog.py`、`thermal.py` |
| 加湿器 `humidifier`（等焓/等温） | `catalog.py`、`thermal.py` |
| 能力标志 `moist_air` | `models.py`、`api.py`、`contracts/` |
| 专项测试 | `tests/test_moist_air_phase2.py` |

## 验证

| 检查 | 结果 |
| --- | --- |
| Phase 2a 专项 | 8 项通过：物性 vs CoolProp `HAPropsSI`（焓/含湿量 2%、露点 ±1 K）、风管含湿量守恒、湿工况表冷器（T/w 与公式 1e-6、凝水 = mΔw、潜热与 mΔw·h_fg 差 <10%）、干工况无凝水、等焓加湿（h 守恒、T 下降）、等温加湿（T 不变、h 增加）、两股空气按质量混合、模式与饱和校验 |
| 定向回归 | 87 项通过（含 `test_thermal.py`、风侧 Phase 0/1、热耦合） |
| 静态检查 | ruff 通过；mypy 67 个源文件零错误 |
| 契约 | `generate_contracts.py --check`：75 个文件一致 |

## 复现

```powershell
python -m pytest tests/test_moist_air_phase2.py tests/test_air_duct_phase0.py tests/test_air_duct_phase1.py tests/test_thermal.py tests/test_thermal_coupling.py -q
python -m ruff check backend tests scripts modules examples/control_templates examples/external_clients
python -m mypy --config-file mypy.ini
python scripts/generate_contracts.py --check
```

## 物理与近似

- 湿空气焓按**每 kg 干空气**计：`h = cp_da·(T−T0) + w·(r0 + cp_v·(T−T0))`；水力流量仍为湿空气质量流量，因此能量账容差放宽到 1% 相对（干网络仍为 1e-6）。
- 饱和水蒸气压力用 Magnus 近似；与 CoolProp `HAPropsSI` 的湿空气焓/含湿量差约 2%，露点差 <1 K，仅用于教学，不作为物性基准。
- 湿工况表冷器为旁通系数法：出口干球与含湿量由盘管表面温度（机器露点）和 BF 确定，不建模翅片凝水滞留、析湿系数分区、除湿再热。
- 含湿量输运为稳态/准稳态标量场（与焓同层），没有房间或风管的湿量储能状态。
- 湿空气模式下允许多数内置风侧元件与 Python 模块（模块按干空气近似），不支持水箱/换热器/冷库/制冷站等非空气域设备。

## 未完成 / 下一步

- Phase 2b：房间含湿量动态状态、新风/渗透/人员/货物散湿、冷却塔水耗与逼近度。
- Phase 2.5：风侧结果视图（变量清单 → 报告 → Studio 面板）。
- 湿工况下的再热、除湿能耗与风机湿空气密度修正未建模。
