# PF-2：自主建模与制冷设备扩展阶段验收

日期：2026-10-30。基线 `802b4c5`。**状态：PF-0/PF-1/RF-0 至 RF-4/PF-2 共八个工作包已完成；本阶段交付与验收收口。**

## 交付范围

本阶段完成两条作者流程：

1. 单相网络：创建自定义阻力设备，编辑合同与源码、配置预期值、发布、插入自建项目、封装组合、升级与回退、保存和导出重载。详见 [PF-0/PF-1](PLATFORM_AUTHORING_ACCEPTANCE.md)。
2. 制冷站：通过公共 SDK 编写无独立物理储量的等焓节流设备，接入独立 Worker 与整段接受事务；在完整站中替换节流阀，改变开度算法、发布和显式升级，复用历史、报告与批量快照。详见 [RF-1 合同](REFRIGERATION_MODULE_CONTRACT.md)、[RF-2/RF-3](REFRIGERATION_MODULE_EXECUTION.md)及[RF-4](REFRIGERATION_PROJECT_ACCEPTANCE.md)。

当前支持 schema 4 / SDK 0.7.0 的 `refrigeration.isenthalpic_throttle.v1` 角色，仅用于纯集总制冷站。schema 1/2/3 的解析、导出和定义哈希语义保留。其他制冷作者角色、制冷模块的热耦合、独立物理储量以及集总站稳态求解器均未开放。

模板、[作者源码](../modules/isenthalpic_throttle/module.py)、[中文说明](../modules/isenthalpic_throttle/README.md)、[完整站与小型站文件](../examples/refrigeration_extensions/README.md)可直接复用。可从 Studio 新建作者模板，或从“项目 → 导入单项目”加载规范 Project 文件。

## 验收依据

| 工作包 | 交付与证据 |
| --- | --- |
| PF-0/PF-1 | [能力清单](PLATFORM_CAPABILITIES.md)、[作者流程验收](PLATFORM_AUTHORING_ACCEPTANCE.md)；自定义编号、真实 Worker、预期值、组合及版本复用 |
| RF-0 | [接口可行性、事务试验与冻结预算](REFRIGERATION_EXTENSION_DESIGN.md) |
| RF-1 | [正式角色、SDK、合同与 Worker](REFRIGERATION_MODULE_CONTRACT.md)；旧合同保持原规范化 |
| RF-2/RF-3 | [运行与验证台](REFRIGERATION_MODULE_EXECUTION.md)；固定/自适应步、控制边界、失败缩步、准备失败、同步失败、停止、独立公式检查 |
| RF-4 | [项目、版本、报告与批量闭环](REFRIGERATION_PROJECT_ACCEPTANCE.md)；完整站和第二项目、1→2→1、规范/原型交换、服务重启及旧快照 |

正式协议的性能记录沿用本阶段 [RF-2/RF-3 实测](platform-extension/results/rf2-rf3/performance.json)。五次独立进程样本的初始化、候选求值、60 s 动态计算、峰值工作集、迭代次数及 Worker 回收均通过预先冻结的 RF-0 预算。本次 RF-4 只修改项目交换、报告和界面引用，没有改变求解或 Worker 算法，因此不重复相同的性能采样。

该预算只适用于规定的短案例，不代表任意设备数量或长期运行性能；独立物理参考是工程假设及公式校验，不代表厂家或现场标定。

## 最终检查

最终源码的检查结果：

| 检查 | 结果 |
| --- | --- |
| 全量后端与覆盖率 | **1723 passed**，29 分 29 秒；覆盖率 **91.05%**，保持原有 85% 门槛 |
| 完整浏览器链 | **27 个脚本全部通过**，1920×1080、DPR=1；覆盖原作者流程、制冷作者、项目与版本、冷库、风侧、冷热水联算和批量 |
| 前端专项 | **15 项通过**，包含局部工况单位、规范项目交换、冻结包和报告入口的回归 |
| 公共 SDK 独立测试 | **128 passed**，覆盖率 **98.69%**；不与后端全量数量相加 |
| 类型检查 | 后端 mypy 87 个源文件、SDK 严格检查 12 个源文件及作者模块严格检查通过 |
| 静态与生成物 | ruff、前端语法、90 个生成合同一致性及两份制冷站示例再生成检查通过 |

浏览器首轮有一项旧制冷站用例仍要求固定“NH₃/CO₂”报告标题；本阶段报告已改为通用标题。更新断言并继续检查具体案例名称和运行编号后，整套重启/复算流程复验通过。记录页新增的历史 HTML/CSV 下载入口也通过 RF-4 最终浏览器复验。已通过且未受后续修改影响的脚本沿用本轮结果，不重复执行。

后端有 5 条警告：4 条来自 WebSocket 依赖弃用提示，1 条来自故意构造非法端口的 Pydantic 序列化用例；没有失败或跳过项。完整日志、覆盖率 XML、源码与证据哈希见 [PF-2 验证索引](platform-extension/results/pf2-validation.json)。

复现入口（项目根目录）：

```powershell
$env:PYTHONUTF8='1'
python -m pytest -q --cov=fn_engine --cov-report=term-missing
npm run test:browser
npm run check
python -m ruff check backend tests scripts modules examples/control_templates examples/refrigeration_extensions
python -m mypy
python -m mypy --config-file mypy-sdk.ini
python -m mypy --config-file mypy-sdk.ini modules/isenthalpic_throttle/module.py
python scripts/generate_contracts.py --check
python scripts/generate_refrigeration_author_example.py --check
```

Windows 打包发版、变量别名、外部真实服务联调、24 小时稳定性和现场工程校核继续保持取消。水侧储热、机组启停、第二类制冷作者设备和 DX 过热度控制仍是后置候选，本次不登记为已实现。
