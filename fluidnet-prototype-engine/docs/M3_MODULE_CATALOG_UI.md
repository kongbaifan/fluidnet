# M3 模块目录 UI 接入说明

> 范围：`fluidnet-prototype-engine` 中 8 个倍思鹿参考模块从 `modules/` 自动发现、经 `/api/v1/modules` 暴露，并渲染进模块库页面与画布左侧模块库。
> 交付：API 契约测试 `tests/test_module_catalog.py`；浏览器回归 `tests/browser-module-catalog.mjs`（前端并行任务添加）。

## 1. 目的

M3 把 8 个参考模块接入模块目录 UI，验证“后端自动发现 + 前端零硬编码”的接入方式：

- 后端扫描 `modules/` 下的版本化 Python 包，与内置 catalog 合并后由 `/api/v1/modules` 返回。
- 前端 bootstrap 只按 `runtime === 'python'` 消费目录，不维护模块 id 白名单。
- 模块库出现“倍思鹿参考模块”分类，卡片展示版本、参数、端口、通路、变量数量。
- 参考模块提供只读“说明”弹窗，并保留插入项目、独立验证、管网算例、编辑模块入口。
- 用 API 契约测试与浏览器回归固定上述行为，避免新增模块时回归。

## 2. 数据流

```text
fluidnet-prototype-engine/modules/<module_id>/
  manifest.json + module.py（可选 design.py）
        │
        │ packages.load_module_package(): 校验 manifest、计算 content_hash / definition_hash
        │ packages.discover_module_packages(): 扫描含 manifest.json 的子目录
        ▼
fn_engine.packages.ModuleStore.latest()
  种子目录 modules/ + 版本存储（.runtime/module-packages 或 data-dir），
  同一 id 取 version 最大的定义
        ▼
GET /api/v1/modules
  { modules: [内置模块..., Python 包...] }
  每条 = ModuleDefinition 全字段 + package 绑定
        ▼
frontend/engine-client.js init()
  Promise.all([/health, /catalog, /modules])
  moduleFromManifest() 把 manifest 投影为 UI 模块对象
        ▼
state.modules
        ├─ studio.js renderModules()   → 模块库页面（分类侧栏 + 卡片）
        └─ studio.js libraryMarkup()   → 画布左侧模块库（按分类分组）
```

关键实现位置：

- `backend/fn_engine/packages.py:16`：`load_module_package()`；缺 `manifest.json` / `module.py` 直接报错；`runtime` 固定注入为 `python`。
- `backend/fn_engine/packages.py:43`：`discover_module_packages()`；按目录名排序，单个目录失败会让本次目录请求失败，属于快速失败的契约。
- `backend/fn_engine/packages.py:86`：`ModuleStore.latest()`；种子目录与版本存储合并后，每个 id 只留最高版本。
- `backend/fn_engine/api.py:451`：`GET /api/v1/modules`；先放内置 catalog，再追加 Python 包，因此返回顺序不是稳定契约。
- `frontend/engine-client.js:129`：`moduleFromManifest()`；建立 name、category、description、ports、channels、parameters、variables 的 UI 投影。
- `frontend/engine-client.js:616`：bootstrap 同时拉取 health、catalog、modules；`packages.modules` 中 `runtime === 'python'` 的条目被写入 `state.modules`。

### 2.1 目录刷新语义

- bootstrap 只在页面加载时拉取一次 `/api/v1/modules`；新增包后刷新浏览器即可重新发现。
- 已存在的本地草稿不会被目录刷新覆盖：`engine-client.js` 只在模块无草稿、无契约草稿且源码一致时应用新 manifest。
- 目录中的每个 Python 条目会同时写入 `publishedManifest` 与 `latestVersion`，因此参考模块无需“先发布”即可插入项目。
- 版本存储中的同 id 更高版本会覆盖种子包成为 `latest()` 结果；种子目录本身不被修改。

## 3. 目录 API 契约

`GET /api/v1/modules` 返回 200，响应体为 `{ "modules": [...] }`。每个参考模块条目至少包含：

| 字段 | 契约 |
| --- | --- |
| `id` | 稳定模块标识，如 `pipe_fitting` |
| `name` / `description` | 中文名称与说明，UI 直接展示 |
| `category` | 固定为 `倍思鹿参考模块`，UI 作为分组名 |
| `version` | `1`；对应 `package.version` 为 `1.0.0` |
| `runtime` | `python` |
| `ports` | 至少 2 个；`domain` 全为 `fluid`，`direction` 为 `in` / `out`，且有入口和出口 |
| `channels` | 至少 1 条启用通路，输入/输出端口必须存在且不同 |
| `parameters` | 数量大于 0；文本、数值、曲线参数都计入 |
| `variables` | 非空；`derived` / `state` 变量会进入运行结果展示 |
| `content_hash` | `module.py` 源码的 SHA-256，64 位十六进制 |
| `definition_hash` | 规范化 manifest 契约的 SHA-256，64 位十六进制 |
| `package` | `{ module_id, version: "1.0.0", content_hash, definition_hash }`，与顶层哈希一致 |

`GET /api/v1/health` 返回 200，且 `capabilities.module_versions === true`；前端用该能力位判断是否展示 Python 模块版本相关入口。

目录不保证顺序，客户端必须按 `id` 查找；当前共 31 条：22 个内置模块 + 8 个参考模块 + 1 个自定义示例 `programmable_valve`（`category` 为 `自定义模块`，不属于本任务 8 个参考模块）。

参考模块响应的关键字段示例（省略未展示的端口细节）：

```json
{
  "id": "pipe_fitting", "name": "管道管件", "version": 1,
  "category": "倍思鹿参考模块", "runtime": "python",
  "ports": [{ "id": "in0", "domain": "fluid", "direction": "in" }, { "id": "out0", "domain": "fluid", "direction": "out" }],
  "channels": [{ "id": "main", "input_port": "in0", "output_port": "out0", "relation": "resistance", "solver_model": "valve", "enabled": true }],
  "parameters": [{ "id": "loss_coefficient", "value_type": "number", "default": 0.9 }],
  "variables": [{ "id": "velocity_m_s", "source": "derived" }],
  "content_hash": "7004d45d…", "definition_hash": "33fe52a0…",
  "package": { "module_id": "pipe_fitting", "version": "1.0.0", "content_hash": "7004d45d…", "definition_hash": "33fe52a0…" }
}
```

测试不应断言完整响应体或模块顺序，只断言契约字段与 8 个 id 的存在性；哈希具体值会随源码/契约变化。

## 4. UI 行为

### 4.1 分类与入口

- `moduleGroupNames()` 从 `state.modules[].category` 汇总分组，因此后端返回 `倍思鹿参考模块` 后，模块库侧栏自动出现同名分类并显示数量 8，无需前端常量。
- 选中该分类时页面顶部显示提示条：“来自倍思鹿参考实现，L1/L2/L3 验证状态见文档。”
- “全部模块”中同样可搜索到 8 个模块；侧栏计数与卡片列表都来自 `state.modules`，刷新目录即可更新。

### 4.2 目录卡片

参考模块卡片展示：

- 图标：按模块 id 使用 `engine-client.js:131` 的静态映射（`pipe_fitting → GitBranch`、`check_valve → ArrowRightLeft`、`fan_coil_unit → Wind`、`cooling_tower → Sun`、`fan → Wind`、`pump_variable_speed → Gauge`、`capillary_tube → Minus`、`valve_equal_percentage → SlidersHorizontal`），未命中回退 `Box`。
- 名称、模块标识（id 大写）、`参考模块` 徽标、`Python · v1` 版本徽标（来自 `publishedManifest.version`）。
- 分类 chip、`manifest.description` 摘要。
- 统计行：`N 个参数 / N 个端口 / N 条通路 / N 个变量`。
- 底部操作：`说明`（仅参考模块）、`编辑模块`、`独立验证`、`管网算例`、`插入项目`。

### 4.3 “说明”弹窗

点击卡片 `说明` 打开只读宽弹窗（`studio.js:1196`），标题为 `模块名 · v1 · 倍思鹿参考模块`，副标题为模块说明，正文包含 4 张表：

1. 参数：`id`、`label`、默认值、单位或 `value_type`。
2. 端口：`id`、`label`、`domain`、`direction`。
3. 变量：`id`、`label`、`source`、单位。
4. 通路：`id`、`relation`、`solver_model`。

弹窗底部提示仓库文档路径：`docs/MODULE_KIT.md`、`docs/MAPPING_A.md`、`docs/MAPPING_C.md`、`docs/M2_L3_CALIBRATION.md`。弹窗没有提交按钮，不写入任何状态。

### 4.4 插入与验证

- `插入项目`：跳转工作台并调用 `newInstance(id)`；Python 模块要求已有 `publishedManifest`，bootstrap 会把目录中的最新版本设为该值，因此参考模块可直接插入。
- 画布左侧模块库按同一分类分组；点击 `place-module` 进入放置模式，或拖拽 `data-drag-module` 到画布。
- `独立验证`：把模块设为验证台被测设备（`setBench`），在 `/api/v1/modules/test` 上做 Worker 试算，不改变项目实例。
- `编辑模块`：打开模块编辑器；参考模块是只读种子包，编辑后保存会在模块版本存储中生成新版本，不覆盖 `modules/`。
- `管网算例`：按模块生成一个最小示例项目，便于快速查看端口与运行结果。
- 项目绑定模块快照与 `package` 哈希，目录升级不会静默改变已有项目。

## 5. 模块清单

| id | 中文名 | 端口数 | 参数数 | 变量数 | 类别 |
| --- | --- | ---: | ---: | ---: | --- |
| `pipe_fitting` | 管道管件 | 2 | 4 | 3 | 倍思鹿参考模块 |
| `check_valve` | 止回阀 | 2 | 4 | 4 | 倍思鹿参考模块 |
| `fan_coil_unit` | 风机盘管机组 | 2 | 13 | 4 | 倍思鹿参考模块 |
| `cooling_tower` | 冷却塔 | 2 | 13 | 6 | 倍思鹿参考模块 |
| `fan` | 风机 | 2 | 7 | 5 | 倍思鹿参考模块 |
| `pump_variable_speed` | 变速水泵 | 2 | 7 | 5 | 倍思鹿参考模块 |
| `capillary_tube` | 毛细管 | 2 | 5 | 3 | 倍思鹿参考模块 |
| `valve_equal_percentage` | 等百分比调节阀 | 2 | 5 | 3 | 倍思鹿参考模块 |

8 个模块均为 2 端口、1 条主通路、`version=1`、`runtime=python`；端口均为 `in0` 入口 / `out0` 出口。

## 6. 测试入口

### 6.1 API 契约

```powershell
cd fluidnet-prototype-engine
<python> -m pytest tests/test_module_catalog.py -q
ruff check tests/test_module_catalog.py
```

`tests/test_module_catalog.py` 使用 `fastapi.testclient.TestClient` 与 `tmp_path` 独立模块存储目录，覆盖：

- 目录 200 且包含 8 个参考模块 id，重复运行稳定；
- 每个模块 category / runtime / version、端口领域与方向、通路绑定、参数/变量非空；
- `content_hash` / `definition_hash` 为 64 位哈希，并与 `package` 一致；
- `/api/v1/health` 的 `capabilities.module_versions` 为 true。

### 6.2 浏览器回归

```powershell
node tests/browser-module-catalog.mjs
```

`tests/browser-module-catalog.mjs` 启动 fixture 服务与 Edge 无头浏览器，验证：侧栏分类计数为 8、参考模块提示条、8 张卡片、统计行、静态图标、`说明` 弹窗 4 张表与文档提示、弹窗无提交按钮，并输出截图 `artifacts/module-catalog.png`。该脚本已加入 `npm run test:browser` 链路。

### 6.3 前端静态检查

```powershell
npm run check
```

依次对 `studio.js`、`engine-client.js`、`project-services.js`、`modeling-workflows.js`、`cold-storage.js` 执行 `node --check`，防止浏览器测试前出现语法错误。

## 7. 运维与新增模块

新增一个参考模块只需：

1. 在 `modules/<module_id>/` 放入 `manifest.json`、`module.py`（可选 `design.py`）；
2. 保证 `manifest.json` 的 `id` 合法且唯一，端口/参数/变量/通路引用一致；
3. 把 `category` 写成 `倍思鹿参考模块`；
4. 重启服务并刷新页面。

后端在每次 `GET /api/v1/modules` 时重新扫描种子目录，因此不重启通常也能在下一次目录请求看到新包；重启用于确保部署进程状态与缓存一致。若 manifest 声明了 `content_hash` / `definition_hash`，必须与实际源码/契约一致，否则目录请求会报错。

UI 直接展示 manifest 的以下字段，不需要改前端代码：

- `name`：卡片与弹窗标题；
- `category`：模块库分组与卡片 chip；
- `description`：卡片摘要与弹窗副标题；
- `parameters` / `variables` / `ports` / `channels`：统计行、说明弹窗表格与运行变量。

唯一需要改前端的情况是自定义图标：图标表在 `engine-client.js:131`，未登记 id 回退为 `Box`。版本存储位于 `.runtime/module-packages`（或 `data-dir/module-packages`），`modules/` 本身保持只读种子。

## 8. 已知边界

- 前端图标是静态映射，不支持 manifest 自带 icon 字段；新增模块默认显示通用 `Box` 图标。
- 模块文档（`MODULE_KIT.md`、`MAPPING_A.md`、`MAPPING_C.md`、`M2_L3_CALIBRATION.md`）不在 UI 内路由或渲染，只在说明弹窗里提示仓库路径。
- `说明` 弹窗是只读展示，不提供参数编辑；参数编辑走模块编辑器或项目实例属性。
- 目录接口不支持分页/服务端搜索，前端在 `state.modules` 上本地过滤；模块数量增长后需要重新评估。
- 参考模块是单通路、双流体端口的简化实现；多通路、双向端口由模型支持，但不在本次 8 个模块范围内。
- 目录扫描是快速失败的：任一 `modules/` 子目录 manifest 非法，整个目录请求会失败，需要先修复包。
- 浏览器测试依赖 Playwright 与 Edge，CI 环境需预装；失败截图写入 `artifacts/module-catalog-failure.png`。
