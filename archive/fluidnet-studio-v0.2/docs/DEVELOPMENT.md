# 开发说明 · v0.2

## 代码入口

| 路径 | 职责 |
| --- | --- |
| `fluidnet/models.py`、`catalog.py` | 项目结构、元件定义、参数和结果变量 |
| `fluidnet/compiler.py` | 端口连接编译、网络校验、介质回路归属 |
| `fluidnet/media.py` | 物性接口与 IF97 液态水适配器 |
| `fluidnet/hydraulics.py` | 支路特性、摩阻、稀疏水力迭代 |
| `fluidnet/thermal.py`、`solver.py` | 热平衡、水热耦合与结果快照 |
| `fluidnet/simulation.py` | 容积、热输运和控制器的时间推进 |
| `fluidnet/jobs.py` | 独立计算进程、任务队列、暂停/单步/停止 |
| `fluidnet/storage.py` | SQLite 项目版本、运行记录、分块曲线与报告 |
| `fluidnet/modules.py` | 组合接口校验、模板提取/插入、原子版本预览与独立验证模型 |
| `fluidnet/api.py`、`cli.py` | 本地 HTTP/WebSocket API 与命令行 |
| `web/src/App.tsx` | 建模、编辑历史、项目保存与运行工作台 |
| `web/src/Inspector.tsx`、`EquipmentNode.tsx`、`Charts.tsx` | 属性、画布元件和曲线 |
| `web/src/modules.ts`、`ModulePanels.tsx` | 组合投影与复制、接口编辑、型号库和独立验证台 |
| `scripts/build_portable.py`、`smoke_portable.py` | 打包与独立程序验收 |

水力与热力联立使用外层耦合迭代；单个任务的网络求解并非按照画布分块并行。当前任务管理器用 `spawn` 启动最多 2 个计算进程，UI 服务与计算进程分离。

介质扩展需要同时实现物性能力、对应流动模型及元件适用性，不能仅将新名称映射到水的物性提供器。

## 组合与版本的数据约定

项目 `schema_version` 为 2。物理网络始终平铺在 `elements` / `connections` 中；`groups` 保存单层成员关系、画布位置、折叠状态、端口与参数映射。界面用 `group:<id>` 作为外壳的可视节点 ID，连线在进入项目数据前转换成真实元件端口。求解器直接处理完整网络，不需要额外的“组合求解器”。

`member_keys` 将模板内的稳定 ID 映射到实例元件 ID，`template_id` / `template_revision` 仅记录来源。插入、复制时重新分配实例 ID，同时重映射内部控制引用、记录变量和介质配置。换热器 a/b 回路保持分离；未显式配置的介质先解析为原项目默认介质，防止跨项目插入时改变物性归属。

接口格式为 `exposed_ports: {alias: "element:port"}` 和 `exposed_parameters: {alias: "element.parameter"}`，显示名称分别放在 `port_labels` / `parameter_labels`。别名首字符为字母或下划线，其余可用字母、数字、下划线或连字符，最长 64 个字符；每个目标只允许一个别名。已接到主网的端口必须保持暴露。

`apply_template` 在副本上生成候选项目与差异列表。保留能够匹配的成员 ID、外部连线 ID、工况和记录变量，外连端口通过稳定接口别名重新绑定。新增、删除和类型变更导致引用失效时拒绝整个应用。HTTP 预览不保存项目，前端需显式接受，且会检查预览期间项目是否已被编辑；之后仍需正常保存项目。

型号的 `kind` 为 `equipment` 或 `group`；内容为参数化元件或无嵌套组合的项目定义。`test_conditions` 按端口别名保存压力/温度边界。`make_bench` 每次生成独立项目 ID，附加测试边界并保留两侧介质，交给同一计算任务管理器。验证结果使用该副本的历史数据，不修改工作台项目。

## v0.1 数据迁移

`Project` 的前置校验器在内存中升级显式 `schema_version: 1`，复制输入后保留元件位置，并为旧分组补齐界面元数据与稳定参数别名。原项目版本和运行快照仍按原文存放，读取或恢复时升级；再次保存生成 schema 2 的新版本。

SQLite 使用 `PRAGMA user_version=2`。对已有旧库，先通过 SQLite backup API 在 `workspace/backups/` 创建一致性备份，再新增模板版本、接口、测试条件、归档字段及 `template_versions` 表。旧型号保留 ID 并成为 v1；版本记录不可覆盖。无效旧型号返回 `validation_error` 供界面展示和导出修复，其余型号继续可用。内置模板按固定 ID 首次补齐，不覆盖用户已修改或已归档的条目。

## 命令行

源码执行前缀是 `python scripts/launch.py`；免安装版将此前缀替换为 `.\FluidNetStudio.exe`。

```powershell
python scripts/launch.py examples --output .cache/examples
python scripts/launch.py validate .cache/examples/example_single.json
python scripts/launch.py solve .cache/examples/example_single.json --output .cache/result.json
python scripts/launch.py simulate .cache/examples/example_tanks.json --duration 10 --dt 0.1 --output .cache/tank-run
python scripts/launch.py serve --port 8765 --workspace workspace --open
```

CLI 验证或求解失败时返回非零退出码。动态结果目录包含模型、最后一帧、曲线通道定义和压缩数据块。

## 本地 API

运行服务后可访问 `/docs` 查看完整 OpenAPI 文档。

| 方法与路径 | 用途 |
| --- | --- |
| `GET /api/v1/health` | 版本、依赖、工作区和启用模型 |
| `GET /api/v1/catalog`、`GET /api/v1/examples` | 元件定义和内置示例 |
| `POST /api/v1/projects` | 保存项目；`revision` 用于乐观并发检查 |
| `GET /api/v1/projects/{id}` | 读取项目，支持 `?revision=N` |
| `POST /api/v1/projects/upgrade` | 在内存中校验/升级项目或历史快照，不写入数据库 |
| `POST /api/v1/validate` | 校验传入的项目 |
| `POST /api/v1/runs` | 提交 `project` 或 `project_id`、运行模式与参数 |
| `GET /api/v1/runs/{id}` | 查询状态和最后一帧 |
| `POST /api/v1/runs/{id}/commands` | `pause`、`resume`、`step`、`stop`、`reset`、`set` |
| `WS /api/v1/runs/{id}/stream` | 实时状态帧 |
| `GET /api/v1/runs/{id}/results?format=csv` | 导出，可选 `json`、`csv`、`html` |
| `GET /api/v1/templates` | 型号库，可选 `?include_archived=true` |
| `POST /api/v1/templates` | 创建型号 v1 |
| `GET /api/v1/templates/{id}` | 读取当前或 `?revision=N` 指定版本 |
| `PUT /api/v1/templates/{id}` | 携带当前 `revision` 追加新版本 |
| `GET /api/v1/templates/{id}/versions` | 型号版本列表 |
| `DELETE /api/v1/templates/{id}?revision=N` | 乐观版本校验后归档 |
| `POST /api/v1/modules/group` | 创建组合或配置已有组合的接口 |
| `POST /api/v1/modules/extract` | 提取指定组合，可用 `scenario_id` 保存工况参数 |
| `POST /api/v1/modules/insert` | 将指定型号版本或内联定义插入项目副本 |
| `POST /api/v1/modules/apply` | 返回候选项目与版本差异，不自动保存 |
| `POST /api/v1/modules/normalize` | 校验可移植型号定义 |
| `POST /api/v1/modules/bench` | 生成带测试边界的独立项目 |

组合操作请求通过 `project`、`group_id` / `element_id` / `element_ids` 指定实例，通过 `template_id` + `revision` 或 `template` 指定定义，插入可传 `position` 和 `page`。不合法定义或引用返回 422；保存和归档的版本冲突返回 409。现有项目、运行与导出 API 保持兼容。

## 验证与构建

先安装 README 中的依赖，再运行 `npm run check` 和 `npm test`。浏览器测试会重新构建网页，避免运行旧的 `web/dist`。后端覆盖解析参考值、质量/能量守恒、反向连接、介质隔离和动态推进；v0.2 还覆盖封装前后计算一致、接口冲突、原子版本应用、控制引用重映射、三套验证模型与旧库迁移。浏览器测试覆盖新建项目、保存竞争、组合内部编辑、独立版本应用、验证单步和 JSON 导入/导出。

Windows x64 上执行 `npm run build -- --portable`，输出：

- `dist/portable/0.2.0/FluidNetStudio/FluidNetStudio.exe` 及其依赖目录。
- `dist/FluidNetStudio-Windows-x64-0.2.0.zip` 和对应 `.sha256` 文件。
- 包内 `examples/` 的六套项目与 `templates/` 的三套组合型号，以及 README、使用/开发说明和构建信息。

打包脚本会在 `build/packaging-python` 创建隔离的 Python 环境，使用 `.runtime/python` 中已安装的依赖。构建缓存保存在项目内，宿主机其他项目的可选库不会参与打包。输出目录按版本隔离；若同版本目录中已有 `workspace`，自动改用带时间戳的目录。旧便携目录中的用户数据保持原样，正式 ZIP 不含工作区或验收数据。

随后执行 `npm run smoke:portable`。自检会启动已构建的可执行文件，移除其子进程环境中的 Python 搜索路径，限制 PATH 为 Windows 系统目录，在带空格和中文的临时路径中检查命令行、网页资源、计算进程、WebSocket、动态单步、结果导出、组合型号和版本应用。报告写入 `.cache/qa/portable-smoke.json`。自检只启停自己创建的服务和工作区。

## Baselu 教程的结合方式

用户提供的 [Baselu 案例入口](https://www.baselu.cn/cases.html) 作为工作流参考。v0.2 对应关系如下：

| 参考内容 | 本项目的实现 |
| --- | --- |
| [教程 1：模块与对外数据](https://www.baselu.cn/article?id=moqzjiw0iw9j) | 参数化设备、组合内部画布和明确的端口/参数接口 |
| [教程 3：流网压力与流量联动](https://www.baselu.cn/article?id=moqzplol4gps) | 保留真实支路和节点，由完整管网统一计算压力与流量 |
| [教程 9：设备型号库](https://www.baselu.cn/article?id=moqzy16vv1nj) | 可编辑型号、JSON 交换、不可覆盖的版本和独立项目实例 |
| [教程 7：曲线与逐帧调试](https://www.baselu.cn/article?id=moqzuqg1p5qi) | 独立验证台、初始化/单步控制、残差与历史曲线 |

FluidNet 使用自己的项目格式、元件目录与求解器，支持配置已有设备行为。用户算法编译、Baselu 文件互操作、电网、气体/两相介质与该网站的性能指标均不属于 v0.2 的实现或验收范围。

## 继续开发时

当前代码已修正画布选中状态循环、空画布缩放、撤销/重做后的保存版本，以及保存期间保留新编辑和单独删除连线的问题；相应流程由浏览器测试覆盖。工作区没有 Git 仓库或 CodeGraph 索引，是否初始化版本控制或建立索引由项目维护者决定。

后续可优先补充复杂工况与外部基准对照、较大网络性能测试和独立介质求解模型。新增功能应先明确物理适用范围，再补充能验证结果的参考算例。
