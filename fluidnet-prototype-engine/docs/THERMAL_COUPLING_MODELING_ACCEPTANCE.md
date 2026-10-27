# 单盘管通用建模验收

日期：2026-10-27。基于 master `e5a90ce` 和上一轮无界面／热耦合工作区继续实现 [TC-1–TC-4](NEXT_DEVELOPMENT_PLAN.md)。状态：**首批实现与本地验收完成**。

## 交付

- 任意项目的建模页可建立一条热耦合，选择合法液体管段、通路、饱和制冷剂容器并设置 UA；已有关系可编辑、重绑定和移除。
- 端点筛选使用项目固定的端口／通路覆盖；关系标识与后端 Identifier 合同一致，支持合法连字符。没有合法端点时说明具体条件。
- 关系和指标不依赖 caseId、HX1、HX_W 或 LP1；建立关系后打开对应盘管曲线。改变关系后当前结果过期，历史记录保留原绑定，运行后加入的普通观察变量也能记录。
- 运行或暂停期间禁止改变关系、删除其端点或经撤销恢复拓扑。删除端点会说明解除关系的影响；撤销／重做恢复设备、连线、关系和当前曲线。复制单设备不复制关系。
- 混合域无耦合的草稿可以保存；检查和运行以 `COUPLED_RELATION_MISSING` 明确说明需要先建立关系。目标或通路错误携带关系、设备和字段定位。

物理范围和数量上限不变：最多一条关系，内置、无储量单相液体侧与现有集总制冷站联算。双盘管、水侧储热和批量工况未在本轮实现。

## 验证

全部测试使用临时工作区；环境为 Windows、Python 3.11、Node 和 Edge。未使用现场标定数据。

| 检查 | 结果 |
| --- | --- |
| 热耦合物理及保存往返专项 | 51 项通过 |
| 前端端点与合同专项 | `npm run test:ui`，3 项通过；覆盖项目禁用通路、自定义通路和非法关系标识 |
| 原单盘管浏览器流程 | 通过：原 HX1 示例、UA 和工况修改、保存、重启、按保存项目复算 |
| 新建模浏览器专项 | 通过：自定义编号／无 caseId、重绑定、历史曲线、复制、删除取消／确认、撤销／重做、移除、真实运行／暂停限制、重启复算，以及 1366×768 下端点选择和提交按钮的可见性 |
| 全量后端回归及覆盖率 | 首次全量 1400 项通过、1 项失败，覆盖率 91.07%；旧诊断断言更新后，13 项拓扑测试全部复验通过 |
| 完整浏览器回归 | 修复后 `npm run test:browser` 返回 0；3 项前端专项及 18 个浏览器脚本全部通过 |
| 静态与契约 | ruff 通过；mypy 后端 62 个文件及 SDK 11 个文件零错误；前端语法检查通过；67 个生成契约一致 |

新浏览器专项先通过实际导出／导入建立自定义项目，再经界面创建 `CustomCoil-2`，将所有设备改为用户编号，并在两根串联管段之间重绑定。输入来源保留已有设计点；与旧运行请求和重启前后的逐变量结果核对。它验证的是自定义项目操作与计算一致性，不是完整通用设备选型。

前两次浏览器试跑分别因把图标 SVG 计入曲线数量、使用仅在设备浮窗存在的复制按钮选择器失败；已分别改为识别实际曲线 SVG 和使用现有 Ctrl+C/Ctrl+V 操作，未放宽产品行为断言。

完整浏览器首轮在批量参数客户端检查中发现，旧客户端状态没有 `charts.extra` 时，首次帧的观察绑定快照会读取失败。已按客户端其余读取路径使用空列表默认值，并重新运行完整浏览器回归；首轮日志保留为 `artifacts/thermal-modeling-browser-first.log`。

全量后端的唯一失败为旧 `REFRIGERATION_MODEL_UNSUPPORTED` 用例：它向制冷站加入一根水管，原先应报不支持；新混合域入口按设计先报 `COUPLED_RELATION_MISSING`。已为水管保留专门的缺关系用例，并用不属于制冷站设备的理想冷源继续覆盖原不支持模型诊断。13 项拓扑复验包含这两条路径，未删除旧拒绝能力或修改物理容差。首次全量记录保留，不登记为单次全绿。

证据入口：`artifacts/thermal-coupling-modeling.png`、`artifacts/thermal-coupling-editor-1366.png`，以及回归的 `artifacts/thermal-modeling-tests.xml`、`artifacts/thermal-modeling-topology-recheck.xml`、`artifacts/thermal-modeling-coverage.json` 和 `artifacts/thermal-modeling-browser.log`。以实际生成记录为准。

## 复现

在项目目录执行：

```powershell
python -m pytest -q --cov=fn_engine
python -m ruff check backend tests scripts modules examples/control_templates examples/external_clients
python -m mypy --config-file mypy.ini
python -m mypy --config-file mypy-sdk.ini
python scripts/generate_contracts.py --check
npm run check
npm run test:browser
```

`test:browser` 先执行 3 项前端合同测试，再依次运行浏览器脚本。单独定位新功能可用 `node tests/browser-thermal-coupling-modeling.mjs`。后端与浏览器全量回归顺序运行，避免同时运行的 Worker 干扰进程清理检查。
