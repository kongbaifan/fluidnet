# 风侧 Phase 1 验收：干工况风管网络

日期：2026-10-28。范围：[风侧开发计划](AIR_SIDE_DEVELOPMENT_PLAN.md) 的 Phase 1（WP1.1–WP1.4）。基线：Phase 0 提交 `ca583eb` 加本轮工作区改动。湿空气/湿工况、风阀静压控制、风口射流与 CFD 不在本轮。

## 交付

| 工作包 | 交付 | 位置 |
| --- | --- | --- |
| WP1.1 风管元件 | 内置矩形风管 `duct`：水力直径 `Dh = 2WH/(W+H)`、Haaland 沿程阻力、可选环境散热、宽高比 >8 诊断 | `backend/fn_engine/catalog.py`、`hydraulic_derivatives.py` |
| WP1.1 管件 | `duct_fitting`：弯头 90°/45°、三通直通/支管、渐扩渐缩、进出口 K 表（教学默认值），custom 可覆盖；K→Kv 与 `pipe_fitting` 同一推导 | `modules/duct_fitting/` |
| WP1.1 风阀 | `duct_damper`：线性/等百分比/快开三种开度特性，0% 精确关断，开度运行中可调 | `modules/duct_damper/` |
| WP1.1 风口 | `air_vent`：按额定风量与额定压降折算等效 Kv，仅作风量分配/阻力教学 | `modules/air_vent/` |
| WP1.2 风机-管网 | 风机曲线与风管阻力联立求工作点；动态帧输出实际压升/轴功率/电功率与累计能量 | 复用 `modules/fan` + 现有求解器 |
| WP1.3 校验与诊断 | 宽高比警告 `DUCT_ASPECT_RATIO`；断面尺寸下限校验；Phase 0 已固定“单侧压力边界退化为零流量”的行为 | `compiler.py`、`tests/test_air_duct_phase0.py` |
| WP1.4 教学算例 | 风管+风机工作点、管件、风阀特性、风口、并联风量分配、动态帧，共 10 项专项测试 | `tests/test_air_duct_phase1.py` |
| 能力标志 | health 新增 `air_duct`；契约重新生成 | `models.py`、`api.py`、`contracts/` |

## 验证

| 检查 | 结果 |
| --- | --- |
| Phase 1 专项 | 10 项通过（9.37 s） |
| Phase 0 专项 | 4 项通过 |
| BSL 集成回归 | 9 项通过（风机/泵/模块联网无回归） |
| 契约 | `generate_contracts.py --check`：75 个文件一致 |
| 静态检查 | `ruff check backend tests scripts modules ...` 通过；`mypy --config-file mypy.ini` 通过 |

**手算对照（测试内独立实现，不调用引擎函数）：**

| 用例 | 引擎 | 手算 | 偏差 |
| --- | --- | --- | --- |
| 矩形风管 + 风机工作点（0.4×0.4 m、30 m、Re≈2.10×10⁵） | 1.5261 kg/s，50.60 Pa | 1.5261 kg/s，50.59 Pa | 0.03% |
| 管件 K=0.3（断面 0.5×0.5 m、Δp=200 Pa） | 10.024 kg/s | 10.029 kg/s | 0.05% |
| 风阀 50% 开度流量比（线性/等百分比/快开） | 0.500000 / 0.182574 / 0.870551 | 同左 | <1e-6 |
| 风口 1000 m³/h @ 50 Pa | 0.33469 kg/s | 0.33477 kg/s | 0.02% |
| 并联风管 A/B（0.4² / 0.3²、10 m、Δp=175 Pa） | 5.1246 / 2.4082 kg/s | 5.1268 / 2.4092 kg/s | 0.04% |

风管散热用例另验证出口温度向环境靠拢，`heat_w` 与 `m·cp·ΔT` 差 <0.2%（保留 cp 随温度变化的容差）。

## 复现

在项目目录执行：

```powershell
python -m pytest tests/test_air_duct_phase0.py tests/test_air_duct_phase1.py -q -s
python -m pytest tests/test_bsl_integration.py -q
python -m ruff check backend tests scripts modules examples/control_templates examples/external_clients
python -m mypy --config-file mypy.ini
python scripts/generate_contracts.py --check
```

## 物理与口径

- 风管阻力：湍流用 Haaland（与内置 `pipe` 同一摩擦律）；层流段按圆管 `64/Re` 等效（矩形层流未建专用关系，属工程近似）。
- 风管无储热、无局部阻力；弯头/三通/变径/风口单独成件，K 值为教学默认值，可覆盖。
- 风阀 `quick_open` 用 `Kv = Kv_max·x^0.2` 近似；等百分比用 `Kv_max·ALF^(x−1)`；0% 开度按 `opening=0` 精确关断。
- 风口只折算阻力与风量，不含射流、气流组织与噪声。
- 风机密度口径见 Phase 0 记录：`fan.air_density` 与引擎参考密度需显式一致或按状态折算。

## 未完成 / 下一步

- Phase 2：湿空气含湿量输运（第三个输运标量）、湿工况盘管、AHU 套件、房间湿负荷、冷却塔水耗。
- Phase 2.5：风侧结果视图（变量清单 → 报告 → Studio 面板）。
- 风侧网络目前仍需手工用内置管道/风管 + `fan` 模块搭建；专用“风系统”入口与风量平衡向导未做。
