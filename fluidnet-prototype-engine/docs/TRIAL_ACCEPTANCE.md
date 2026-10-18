# 试用版验收记录

日期：2026-10-18。代码基线：v0.4.10（本次 A/B 工作流提交；脚本与文档同批入库）。
环境：Windows + PowerShell；系统 Python 3.11.0（无 `.venv`）；CoolProp 8.0.0；Node 24 + Playwright 1.64.0（msedge，headless）；前端零构建。

本文件汇总三部分验收证据：M1 遗留的**浏览器旧存档迁移**、M4 的**常用操作与规模记录摘要**，以及**真实算例准备清单**。所有数字来自仓库内脚本的实测输出；现场数据尚待用户提供，本文件**未伪造**任何现场算例结果。范围与能力状态以 [README 能力表](../README.md) 为准。

## 1. 验收入口与隔离方式

```powershell
python -m pytest -q
npm run check
node --check tests/browser-archive-migration.mjs
node tests/browser-archive-migration.mjs
```

- 本轮新增 `tests/browser-archive-migration.mjs` 与本文档；`package.json` 的 `test:browser` 已接入迁移脚本，浏览器验收共 11 个脚本（原有 10 个 + 迁移脚本）。
- 浏览器脚本统一使用临时端口、`mkdtemp` 临时数据目录，并隔离 `FLUIDNET_MODULE_STORE` / `FLUIDNET_DATA_DIR`；不触碰 8799 端口上的既有服务。
- 本记录对应的迁移脚本两次重复运行输出一致（见第 4 节），`node --check` 通过；`node tests/browser-archive-migration.mjs` 退出码 0，输出含项目数量、模块双哈希、关键参数与工作区修订号。

## 2. 常用操作验收清单

| 常用操作 | 浏览器脚本证据（关键断言） | 结果 |
| --- | --- | --- |
| 新建项目 | `tests/browser-archive-migration.mjs`：项目页“新建项目”用空白画布创建项目，项目选择器与迁移前导出都包含该项目 | 通过 |
| 导入（单项目） | `tests/browser-workflows.mjs`：`wf-export` 下载单项目文档 → `wf-import` 创建副本 → 保存项目 → 刷新后仍在；`tests/browser-archive-migration.mjs`：把旧存档导出中的单项目导入服务器工作区 | 通过 |
| 调参 | `tests/browser-smoke.mjs`：V1 开度改为 40 并应用，单步运行后被控支路流量下降、旁路流量上升 | 通过 |
| 单步 | `tests/browser-smoke.mjs`、`tests/browser-pid.mjs`、`tests/browser-multifluid.mjs`、`tests/browser-auth.mjs`：step 后运行状态为 paused 且仿真时间推进，历史帧保留 | 通过 |
| 暂停/继续 | `tests/browser-smoke.mjs`：运行 → 暂停（暂停按钮禁用、运行按钮可用）→ 继续 → 停止，按钮状态与后端命令一致 | 通过 |
| 工况对照 | `tests/browser-workflows.mjs`：新建“节流 25%”工况并保存运行，再以基础模型运行；曲线页对照两次已完成运行显示 2 条曲线，结果显示“节流 25%”，运行请求记录工况与项目修订 | 通过 |
| 版本升级 | `tests/browser-workflows.mjs`：发布 v2 → 预览兼容升级 → 应用后项目快照为 v2、新增参数生效 → 从项目修订回退到 v1；`tests/browser-authoring.mjs`：发布 v2 后重启页面，载入 v1 复现旧流量 | 通过 |
| 保存恢复 | `tests/browser-workspace.mjs`：工作区修订 1→2→3、陈旧页面 409、保存失败 507 后重试、强杀服务后全新浏览器上下文恢复项目/控制/运行档案、工作区修订恢复；`tests/browser-archive-migration.mjs`：迁移保存修订 2 后全新上下文恢复 | 通过 |
| 运行/停止 | `tests/browser-run-control.mjs`：后台长运行 stop → cancelled 且保留已算历史、页面停止回放；`tests/browser-continuous.mjs`：持续运行请求 `duration_s=null`，曲线页可切换全程抽稀，stop → cancelled | 通过 |
| 模块独立验证 | `tests/browser-platform.mjs`：可编程阀门独立验证台试算、提交计数与状态回传 | 通过 |
| 鉴权/多工质（附加） | `tests/browser-auth.mjs`（令牌保护与运行变量接口）、`tests/browser-multifluid.mjs`（双回路两种工质、密度按回路取值） | 通过 |

上述脚本均断言 `pageerror` 为空。未列入本表的入口（如串口、加热器、止回阀）在 README 能力表中明确为“仅编辑/预览或拒绝求解”，不属于本轮试用验收通过项。

## 3. 规模记录摘要（引用 [BACKUP_ACCEPTANCE.md](BACKUP_ACCEPTANCE.md)）

数据来源：`artifacts/scaling-acceptance.json`，脚本 `scripts/verify_scaling.py`，共 9 组通过。记录环境：Windows 10.0.29683、AMD64 Family 25 Model 80、原生数值线程 1；每组测量 1 次；sparse 水力算法。时间是求解耗时（不含编译和序列化），峰值 RSS 含采样时的子进程。

| 实例数 | 串联求解 / 峰值 MiB | 分支求解 / 峰值 MiB | 25% Python 模块求解 / 峰值 MiB |
| --- | --- | --- | --- |
| 100 | 0.540 s / 134.6 | 0.368 s / 136.0 | 3.091 s / 268.9 |
| 500 | 2.575 s / 143.9 | 0.894 s / 146.6 | 4.974 s / 280.4 |
| 1000 | 2.736 s / 160.8 | 1.955 s / 162.2 | 7.205 s / 294.9 |

残差：最大压力残差约 2.75e-6 Pa，各组质量残差小于 1e-6 kg/s。

**前端上限**：每张画布最多 64 台设备（`frontend/studio.js` 的 `newInstance` 拒绝新增第 65 台，`validateImport` 拒绝单页节点数超过 64 的导入；工作区最多保存 20 个项目、每个项目最多 8 张画布）。因此 1000 实例只是后端求解规模观测，**不能当作画布/前端规模验收**；前端使用应按每页 64 实例拆分画布。以上为单次后端观测，不是吞吐保证。

已有 5 组工程假设算例（并联支路阀门开度 0.8/0.1/0、三水箱充液/排液）见 [BACKUP_ACCEPTANCE.md](BACKUP_ACCEPTANCE.md) 的“已有工程算例证据”，参数为工程假设而非现场数据，不等同现场验收。

## 4. 旧存档迁移验收记录

### 背景

旧版本只把原型草稿写在浏览器 `localStorage`（键 `fluidnet-prototype-engine-v1`），没有服务器工作区。新版本默认使用 SQLite 工作区。ROADMAP 的 M1 遗留项要求：**先保留原始导出 → 载入服务器工作区 → 单项目导入**，并核对导入后的项目数量、模块哈希与关键参数。

### 脚本与步骤

脚本 `tests/browser-archive-migration.mjs` 可独立运行，使用临时端口、临时数据目录与临时模块库。流程（与脚本内编号一致）：

1. 保存服务器工作区基线：内置 3 个项目，修订 1。
2. 常用操作“新建项目”：空白画布新建一个项目（证明新建入口可用，并进入后续存档）。
3. 用“可编程阀门 · 管网算例”生成带固定 Python 模块快照的项目；迁移前草稿共 5 个项目（3 个内置 + 1 个新建空白 + 1 个 Python 模块算例）。
4. 把导出改造成“旧版存档”：删除 `workspaceRevision` / `projectRevisions` / `projectSavedKeys` / `savedAt`，`dirty=true` 模拟未保存草稿；写入关键参数 `V1.opening_ratio=0.65`、`V1.kv_m3_h=20`。
5. 写入 `localStorage` 后重新打开页面：dirty 本地草稿被保留，未被服务器工作区静默覆盖，此时还没有 `-before-workspace` 备份。
6. **迁移前先保留原始导出**：设置 → 保存与交换 → “导出原型 JSON”，下载迁移前完整存档。
7. 点顶部“载入服务器”并确认：旧草稿先备份到 `fluidnet-prototype-engine-v1-before-workspace`，随后载入服务器基线（3 个项目）。
8. 从原始导出取出 Python 项目构造单项目文档，用“导入单项目”（copy 模式）迁入，得到 4 个项目。
9. 保存工作区：服务器修订 1 → 2，4 个项目。
10. 迁移后、再次载入前：原始导出、`-before-workspace` 备份与落盘旧存档三者哈希不变。
11. 全新浏览器上下文（无任何本地草稿）从服务器恢复：证明迁移结果已持久化，而不只是浏览器内存。
12. 全新上下文载入没有改写原页面的载入前备份；原始导出仍逐字节一致。

### 实测结果（2026-10-18，两次运行输出一致）

- 项目数量：旧存档 5 → 服务器基线 3 → 导入后 4 → 新上下文恢复 4。copy 导入给项目名追加“导入”后缀，重新生成的项目 ID 在迁移后工作区唯一且不属于服务器原有项目。
- 模块双哈希：`programmable_valve` 的 `content_hash = d87e5126332eaafaf72c38ab908e2532f529ce1daf5433202ce06d87e72e5dc8`，`definition_hash = 41909fe01b1ba0a31ec1089e00f9d1fa93e984429eaf441c35244e7299facd59`。导入项目快照与实例 `package` 的双哈希一致；保存后服务器工作区一致；全新上下文恢复后一致。
- 关键参数：`V1.opening_ratio=0.65`、`V1.kv_m3_h=20` 在导入后、服务器保存后、恢复后三处一致。
- 原始存档未被破坏：原始导出 SHA-256 `c3e6848595d521ca08242aadc415f9621c742b1f1a53f604ca680d6288aa1f70` 全程不变；`-before-workspace` 备份 SHA-256 `93e443b2c31d4ade12998608323892f68cfced8a7d0636330fca66e74d2a7d87` 与写入的旧存档 SHA-256 完全相同（备份文本与旧存档逐字节一致），迁移后复核不变。
- 页面异常（`pageerror`）：0。

证据文件（`artifacts/` 已在 `.gitignore` 中）：

```text
artifacts/archive-migration/old-browser-draft.json               # 写入 localStorage 的旧存档
artifacts/archive-migration/original-export-before-migration.json # 迁移前保留的原始导出
artifacts/archive-migration/single-project-from-old-export.json   # 从原始导出取出的单项目文档
artifacts/archive-migration/migration-result.json                 # 数量/哈希/参数/修订号/哈希值
artifacts/archive-migration/archive-migration.png                 # 最终页面截图
```

### 边界与遗留风险

- 本验收模拟“旧版本地存档 + 已保存服务器工作区”的迁移路径；**未覆盖**从更老 schema 或其他字段结构自动升级——启动只接受 `schema=1` 且 `projects/modules/models` 数组非空的原型记录，不满足时退回内置示例；字段级校验发生在“导入原型/载入服务器”时，不做字段级自动迁移。
- `-before-workspace` 是“最近一次载入服务器前”的**滚动备份**：之后再次正常打开页面（本地草稿干净）会以当前草稿覆盖该键。需要长期保留时应依赖迁移前下载的原始导出文件（本脚本已验证该文件不变）。
- copy 模式导入会按 `state.serial` 重新生成项目 ID；脚本只断言新 ID 在迁移后工作区内唯一且不属于服务器原有项目，不依赖新旧 ID 是否相同。若旧项目仍在同一工作区，应使用 replace 模式或先改名。
- 本脚本只断言迁移链路的数据一致性，不覆盖 ZIP 完整备份/恢复（由 `tests/browser-workspace.mjs` 与 `tests/test_backup.py` 覆盖）。

## 5. 真实算例准备清单（待用户提供，未伪造）

本轮**没有**获得现场数据，因此不构造“现场算例通过”的结论。已有 5 组工程假设算例与 9 组规模记录均不等同于现场验收。要完成 M4 的真实算例验收，需要用户提供以下数据（逐项）：

1. **拓扑**：设备清单与连接关系（原始模型文件、导出文件或截图）；回路数量、每个回路的工质与压力参考点；是否有并联/串联支路、旁通或隔离段。
2. **设备参数**：管道（长度、内径、粗糙度、热容、散热 UA）；阀门（Kv、开度范围、是否调节）；泵（流量—扬程曲线、转速、效率、轴功率）；换热器（UA、两侧流道与流向）；水箱（容积、初始液位、加热功率、环境温度）；Python 模块的算法、参数与输出变量。
3. **边界条件**：进出口压力/温度/流量、环境温度、初始液位等初始状态；稳态或动态、仿真时长、时间步、采样周期、是否持续运行。
4. **工质**：水、乙二醇比例（如 `INCOMP::MEG[0.3]`）或 REFPROP 字符串（如 `REFPROP::R134A`、`REFPROP::R407C.MIX`）；混合物需给出质量或摩尔分数；是否需要两相（当前只支持单相，进入两相报 `PHASE_UNSUPPORTED`）。
5. **期望结果与基准**：现场实测或厂商选型的流量、压降、温度、换热量、能耗等；允许误差；用于对照的原始表格（CSV/Excel/截图）与单位约定。
6. **控制与运行策略**（如适用）：PID 目标与限幅、项目控制脚本、暂停/单步/继续/持续运行要求。
7. **交付形式与授权**：原始数据文件、单位约定、是否允许写入验收记录与候选发行包。

范围确认：当前试用版为单机、单相流体网络，不含两相流、水锤、完整可压缩流动；压缩机、两相节流、冷风机、库房等未支持模型不计为通过（见 [MODELING_TRIAL_VALIDATION.md](MODELING_TRIAL_VALIDATION.md)）。收到数据后应按 `tests/browser-*.mjs` 的隔离方式在临时工作区复现，保存输入、运行请求、结果帧与误差，再补写验收记录；不修改用户已有工作区。

## 6. 结论与未完成项

- 已完成：M1 浏览器旧存档迁移的单独验收（第 4 节）；常用操作的浏览器证据清单（第 2 节）；规模记录摘要（第 3 节）。
- 仍未完成：真实算例（**待用户提供，未伪造**）；24 小时持续运行复验（现有记录为 `failed`，见 [BACKUP_ACCEPTANCE.md](BACKUP_ACCEPTANCE.md)）；干净 Windows 离线发行包与升级/回退验证；前端每页 64 实例限制下的规模使用说明需在试用中确认。
- 本记录不把 M4 标记为整体完成。
