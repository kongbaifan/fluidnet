# FluidNet × 倍思鹿：模块开发套件 v1 交付说明

> 交付日期：2026-10-22
> 基线：`kongbaifan/fluidnet` master（本地提交 `52f0ac7`）
> 内容：模块开发套件 + 34 模块移植矩阵 + **三批共 7 个模块包 + 2 个控制脚本模板** + 参考算例库 + CI/CD
> 本目录即「基线 + 本轮新增」，可直接运行；仓库根 `bsl-modules.patch` 是等价的累计补丁。

## 1. 交付清单

| 文件/目录 | 行数/大小 | 作用 |
| --- | --- | --- |
| `fluidnet-prototype-engine/docs/MODULE_KIT.md` | 398 行 | 模块开发套件 v1：决策树、合同字段、单位、生命周期、API、测试分级、验收 checklist、版本发布、模板、21 条常见错误 |
| `docs/MODULES_P0.md` | 357 行 | P0 批次设计（管件、止回阀、风机盘管），12 个用例 |
| `docs/MODULES_P1.md` | 348 行 | P1 批次设计（冷却塔、风机、变速泵），9 个用例 |
| `docs/MODULES_P2.md` | 335 行 | P2 批次设计（毛细管单相近似 + 两个控制脚本模板） |
| `docs/BSL_MODULE_MAP.md` | 约 180 行 | 34 模块 → FluidNet 落点矩阵（A/B/C/D、P0–P3、人日、验收算例） |
| `docs/BASELU_REFERENCE_CASES.md` | 139 行 | 参考算例库 v0 说明（10 个快照用例） |
| `docs/MAPPING_A.md` | 391 行 | M2-A：A 类 5 模块 → 内置模型的映射与 20 条验收算例 |
| `docs/MAPPING_C.md` | 449 行 | M2-C：C 类 8 模块 → 制冷/冷库执行域的映射与 31 条验收算例 |
| `docs/NH3CO2ZL_CASE.md` | 341 行 | M2-C：NH3CO2ZL 工程画像、可迁移/不可迁移、最小可运行替代方案与验收容差 |
| `scripts/extract_nh3co2zl_parameters.py` | 400 行 | 从 NH3CO2ZL `.PJTDB` 提取 222 个对象的参数/分类，输出稳定 JSON |
| `tests/fixtures/nh3co2zl/parameters.json` | 1.6 MB | 上述脚本产物（可复现；不含拓扑） |
| `tests/test_bsl_integration.py` | 约 18.5 KB | M2-B：7 个模块在真实 `compile_project`+`solve_steady/solve_dynamic` 下的 9 项 L3 集成测试 |
| `modules/pipe_fitting/` | 3 文件 | 管件局部阻力，K→等效 Kv |
| `modules/check_valve/` | 3 文件 | 止回阀，反向 `opening=0` 零流量约束 |
| `modules/fan_coil_unit/` | 3 文件 | 风机盘管，水侧网络 + 空气侧 ε-NTU |
| `modules/cooling_tower/` | 3 文件 | 冷却塔，ε-NTU（湿球近似）+ 逼近度 |
| `modules/fan/` | 3 文件 | 风机，压力曲线→扬程曲线 + 效率/电功率 |
| `modules/pump_variable_speed/` | 3 文件 | 变速泵，相似律 + 效率/电能账本 |
| `modules/capillary_tube/` | 3 文件 | 毛细管（单相液体近似），细长管阻力 + 流速 |
| `modules/valve_equal_percentage/` | 3 文件 | 等百分比调节阀（ALF/LF 特性，CVF→Kv），对应倍思鹿 V-4 |
| `docs/M2_L3_CALIBRATION.md` | 279 行 | M2-L3 标定清单：11 条 L3 的现状、倍思鹿侧数据采集清单、验收公式与回填流程 |
| `tests/test_bsl_calibration.py` | 约 19.7 KB | P-4/V-4/M-4 的 6 项标定/验收测试（本地已通过） |
| `docs/M3_MODULE_CATALOG_UI.md` | 212 行 | M3：模块目录 UI 数据流、卡片/说明弹窗行为、8 模块清单、测试入口与运维说明 |
| `tests/test_module_catalog.py` | 97 行 | `/api/v1/modules` 契约测试：8 个参考模块的 category/runtime/端口/参数/变量/双哈希（10 项） |
| `tests/browser-module-catalog.mjs` | 约 4.1 KB | 浏览器回归：分类计数、8 张卡片、图标、说明弹窗、pageerror（已加入 `test:browser` 链） |
| `frontend/{engine-client,studio}.js` + `index.html` | 少量 | 参考模块图标、卡片“参考模块”徽章/参数数/说明按钮、只读说明弹窗、分类提示条 |
| `examples/control_templates/comparator.py` | — | 比较器控制模板（双阈值 + 回差） |
| `examples/control_templates/fan_coil_thermostat.py` | — | 风机盘管温控模板（三速 + 比例阀位 + 死区） |
| `tests/test_bsl_modules.py` | 304 行 | P0 批次 7 项回归 |
| `tests/test_bsl_modules_p1.py` | 约 310 行 | P1 批次 7 项回归 |
| `tests/test_bsl_modules_p2.py` | 约 8.5 KB | P2 模块 5 项回归 |
| `tests/test_control_templates.py` | 约 4.7 KB | 控制模板 2 项回归 |
| `.github/workflows/bsl-modules.yml` | — | 新增快速门禁：模块/控制模板测试 + artifact 打包 |
| `.github/workflows/ci.yml` | 改 1 行 | ruff 范围加入 `modules examples/control_templates` |
| `tests/fixtures/baselu/*.json` | 10 个 | 参考算例快照（输入/变量，非验收基准） |
| `scripts/extract_baselu_cases.py` | 534 行 | 从 `.PJTDB` 提取参考算例，稳定可重跑 |

## 2. 如何应用

方式 A：直接使用本目录（已含基线 + 新增）。

方式 B：把补丁打到你的工作分支：

```powershell
git checkout -b bsl-modules
git apply --check ..\bsl-modules.patch   # 先干跑
git apply ..\bsl-modules.patch
```

补丁包含新增文件与 1 行 `ci.yml` 扩展，不改业务代码。

## 3. 验证结果（本机实测）

```text
python -m pytest tests/test_bsl_modules.py tests/test_bsl_modules_p1.py \
                 tests/test_bsl_modules_p2.py tests/test_control_templates.py -q
21 passed

python -m pytest tests/test_bsl_integration.py -q
9 passed

python -m pytest tests/test_bsl_calibration.py -q
6 passed

python -m pytest tests/test_module_catalog.py -q
10 passed

# 本机合计 46 项（21 单元 + 9 集成 + 6 标定 + 10 目录契约）

python -m ruff check backend tests scripts modules examples/control_templates
All checks passed!

npm run check
# 前端 5 个 JS 语法检查通过

PYTHONPATH=backend node tests/browser-module-catalog.mjs
# 分类计数 8、8 张卡片、说明弹窗、pageerror=[]，exit 0

python scripts/extract_baselu_cases.py --out <目录>          # 10 个 fixture，连跑两次 SHA 一致
python scripts/extract_nh3co2zl_parameters.py --out <目录>  # 222 对象，连跑两次 SHA 一致
```

关键数值（节选）：
- `pipe_fitting`：`d=0.05, K=0.9 → Kv=105.3729 m³/h`；
- `fan_coil_unit`：`0.1 kg/s、12/27 °C、UA=2000 → Q=3574.54 W、ε=0.98700`；
- `cooling_tower`：`3 kg/s、37/27 °C、UA=20000 → Q≈34.3 kW、approach≈7.26 K`；
- `fan`：`1 kg/s、Δp=300 Pa → P_shaft=416.67 W、P_elec=462.96 W`；
- `pump_variable_speed`：`2 kg/s、Δp=150 kPa → P_shaft=429.34 W、P_elec=477.05 W`；
- `capillary_tube`：`D=1.5 mm、L=1.5 m、0.02 kg/s → v≈11.34 m/s`；
- 控制模板：比较器 `0.7→1 / 0.5→1（回差）/ 0.3→0`；温控 `303.15→3 档/100%`、`299.5→0 档/0%`。
- **M2-B 集成测试**：`tests/test_bsl_integration.py` 9 项全部通过（本机 30 s，真实求解器）：管件解析解、止回阀正/反向、风机盘管 ε-NTU、冷却塔热耦合、风机气相单相、风机/泵动态功率、毛细管层流。关键值如冷却塔 `Q≈−69.1 kW / approach≈19.19 K`、风机 `P_elec≈273 W`（动态）、泵 `P_elec≈249.5 W`（动态）。

## 3.1 M2-A / M2-B 进展

- **M2-A 映射（已完成）**：`docs/MAPPING_A.md` 把管道通用、截止阀、泵曲线法、管壳式换热器、容积型源头映射到内置 `pipe/valve/pump/exchanger/source`，共 20 条验收算例（17 条 L1/L2 可执行，3 条标注为 L3/待标定）。结论：管道/阀门/泵可直接映射；换热器需“exchanger + tank”组合且壳侧两相/液位暂不可验收；多端口定焓源头需 `source + junction`。
- **M2-B 集成测试（已完成）**：`tests/test_bsl_integration.py` 9 项，覆盖全部 7 个模块，无 xfail；全部走真实编译与求解，并校验收敛残差/质量守恒/模块变量。该文件由全量 `ci.yml` backend job 执行（不在快速 `bsl-modules` job 里，避免引入 scipy/CoolProp 依赖）。
- **M2-C（已完成）**：
  - `docs/MAPPING_C.md`：压缩机、蒸发器、蒸发式冷凝器、罐体卧式/立式、中间冷却器、冷库库房、热力膨胀阀 → 制冷/冷库执行域，31 条验收算例（L1×9/L2×14/L3×8），逐项列出映射差异与暂不可验收项（两相只在设备内部、分层取液、过热度自调等）。
  - `docs/NH3CO2ZL_CASE.md` + `scripts/extract_nh3co2zl_parameters.py` + `tests/fixtures/nh3co2zl/parameters.json`：从 `.PJTDB` 提取 63 NOD / 222 MOD 对象（精确键集匹配 168 个），给出参数/设备类别统计与 `station_case` 最小替代方案；明确 **`.pjt/.Modu` 加密、PJTDB 无拓扑字段**，因此只能人工搭种子拓扑，不能直接导入原工程。
  - 已知数据异常：MOD161 的 `IM0_TEMP=973.99 °C` 越界，脚本已在 caveats 标注，使用时需剔除。
- **M2-L3 标定（本轮新增）**：
  - `docs/M2_L3_CALIBRATION.md`：11 条 L3（A 类 3 + C 类 8）的三态清单——已执行 / 待倍思鹿数据 / 阻塞，附采集变量、验收公式与回填流程。
  - 已执行：**P-4** 管道动态热容（`thermal_cells=4` + 壁面热容，动态逼近稳态）、**V-4** 等百分比阀（新增 `modules/valve_equal_percentage`，复刻 `CVF=(ALF^(o−1)+LF)/(1+LF)−1/ALF`，50% 开度流量比≈0.09 对照线性 0.5）、**M-4** 泵曲线单位（MPa/bar 两种假设的工作点对比，单位待倍思鹿一次运行判定）。
  - 待数据：C-4、E-4、EC-4、V-4(罐体液位)、V-7、IC-4、R-4、TX-4，必须跑倍思鹿导出指定变量后回填，不得用快照假装通过。
  - 测试：`tests/test_bsl_calibration.py` 6 项，本地通过。
- **M3 模块目录 UI（本轮新增）**：
  - 8 个参考模块由 `/api/v1/modules` 自动发现并渲染进模块库：分类「倍思鹿参考模块」、卡片显示版本/参数/端口/通路/变量数、「参考模块」徽章与「说明」按钮；说明弹窗展示参数/端口/变量/通路四表与文档路径提示（只读）。
  - 前端补齐了参考模块图标映射与分类提示条；未改引擎/后端接口。
  - 测试：`tests/test_module_catalog.py` 10 项（API 契约）+ `tests/browser-module-catalog.mjs`（分类计数 8、8 卡片、说明弹窗、pageerror 为空，已加入 `test:browser` 链）。
  - 本机验证：浏览器测试实测通过（npm ci + Edge headless），截图 `artifacts/module-catalog.png`。

## 4. CI / CD（本次新增）

- **`.github/workflows/bsl-modules.yml`**（快速门禁，约 1 分钟）：
  - 仅装 `pydantic/pytest/ruff`，跑 `tests/test_bsl_modules*.py` + `tests/test_control_templates.py` 与对应 ruff；
  - 不依赖 scipy/CoolProp，跟主 `ci.yml` 的全量 backend job 互补；
  - `package` job 在门禁通过后上传 artifact `bsl-module-kit`（modules + templates + docs + tests + fixtures）。
- **`.github/workflows/ci.yml`**：ruff 范围扩展为 `backend tests scripts modules examples/control_templates`，主 backend job 的全量 pytest 会自动收集新增测试。
- **触发策略**：feature 分支只由 `pull_request` 事件运行，`push` 仅 `master`，避免同一提交产生重复运行；两个 workflow 都配置 `concurrency`（同分支取消旧运行），防止 `cancelled` 检查影响 PR 合并状态。
- **前端门禁**：`test:browser` 链新增 `tests/browser-module-catalog.mjs`，`ci.yml` frontend job 会随现有 13 个浏览器脚本一起执行；`npm run check` 覆盖 5 个前端 JS 文件。

未在本机运行倍思鹿 exe；L3 的可执行部分（P-4/V-4/M-4）已在本地跑通，待数据项由全量 `ci` backend job 登记、回填后再转为断言。

## 5. 模块/模板能力摘要

| 对象 | 形态 | 关键能力 | 测试 |
| --- | --- | --- | --- |
| `pipe_fitting` | 模块 | 管件 K→Kv 等效、流速、累计质量 | 2 |
| `check_valve` | 模块 | 反向 `opening=0`、关断计数、通过量 | 2 |
| `fan_coil_unit` | 模块 | 水侧阻力 + 空气侧 ε-NTU、压差反解流量 | 3 |
| `cooling_tower` | 模块 | 逆流 ε-NTU（湿球）+ 逼近度/出风温度 | 3 |
| `fan` | 模块 | 压力曲线→扬程、气体压升、轴功/电功率 | 2 |
| `pump_variable_speed` | 模块 | 变速相似律、效率/电能账本 | 2 |
| `capillary_tube` | 模块 | 单相细长管阻力、流速、累计质量；两相明确不支持 | 5 |
| `valve_equal_percentage` | 模块 | 等百分比特性（ALF/LF，CVF→Kv），50% 开度≈9% Kv；对应 V-4 | 6（含 P-4/M-4 标定） |
| 模块目录 UI | 前端 | 参考模块分类、卡片徽章/参数数、说明弹窗、图标映射 | 10 API + 1 浏览器 |
| `comparator` / `fan_coil_thermostat` | 控制模板 | 回差比较；三速分级 + 比例阀位 + 死区 | 2 |

## 6. 设计决策与平台依赖

1. **不做引擎改动**：模块只用公开 SDK；管件用 K→Kv 等效替代缺失的 `NetworkBuilder.resistance()`（建议见 `MODULES_P0.md §1.5`）。
2. **`heat_w` 不重名**：单通路实例由求解器生成 `<I>.heat_w`；模块输出 `heat_flow_w`，平台别名保留、数值相同。
3. **evaluate 拿不到流量**：冷却塔/风机盘管/毛细管用试算压差按 `solver.pipe_drop` 同律反解；`commit_step` 用收敛流量重算。该函数与求解器是**平台依赖点**。
4. **泵/风机曲线合同**：`head_curve` 必须首点流量 0、末点扬程 0、流量递增、扬程递减；风机在模块内归一化压力曲线。
5. **控制不做网络模块**：求解器只接受 fluid 端口；比较器/温控用项目控制脚本（独立 Worker、采样写参数），与 PID 分工明确。
6. **参考算例是输入快照**，不是收敛验收基准（`convergence_verified: false`），与 `BASELU_COMPARISON.md` 口径一致。

## 7. 已知限制 / 未完成

- 本地未跑 L3 联网测试；CI 的全量 job 会覆盖，但需要在合并后看 CI 结果。
- 冷却塔为干空气显热模型（无蒸发潜热/水耗/填料 KaV/L）；毛细管为单相近似（无两相壅塞/闪发）。
- 风机无失速区/噪声/效率曲线；变速泵未实现 `FUD_TRNPRP`（变物性交给 `property_coupling='node'`）。
- 风机盘管为干工况；控制模板中的 `input.*`/`output.*` 需替换为真实工程变量路径后才能部署。
- 参考算例要成为数值 oracle 需跑倍思鹿导出收敛结果后回填。

## 8. 复现命令

```powershell
cd fluidnet-prototype-engine
python -m pytest tests/test_bsl_modules.py tests/test_bsl_modules_p1.py tests/test_bsl_modules_p2.py tests/test_control_templates.py -q
python -m pytest tests/test_bsl_integration.py -q
python -m pytest tests/test_bsl_calibration.py -q
python -m pytest tests/test_module_catalog.py -q
python -m ruff check backend tests scripts modules examples/control_templates
npm run check
# 浏览器测试（需 playwright + Edge）：
$env:PYTHONPATH='backend'; node tests/browser-module-catalog.mjs
python scripts/extract_baselu_cases.py --out tests/fixtures/baselu
python scripts/extract_nh3co2zl_parameters.py --out tests/fixtures/nh3co2zl
```
