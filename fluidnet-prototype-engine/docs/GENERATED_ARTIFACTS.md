# 生成物与审查

2026-11-07。可直接导入的项目、冻结模块来源和历史 SDK 契约仍随仓库保存。源码或生成规则是修改入口；生成 JSON 的行数不能代替实际行为差异的说明。

## 清单与只读校验

`scripts/generated-artifacts.json` 登记当前 13 个带 `--check` 的生成器、命令及输出范围。`generated_artifacts.py` 检查脚本存在、只读入口、输出文件匹配、重复登记以及新增生成器遗漏。

输出范围用于定位**候选**生成器；例如几个生成器都发布 `modules/*/manifest.json`，这不是每个模块都由它们全部管理的声明。手写模块来源、recipe、参考输入继续展开审查。`generate_capability_inventory.py` 没有 `--check`，不在这份可重现产物清单内。

```powershell
python scripts/generated_artifacts.py --check
python scripts/generated_artifacts.py --verify --group contracts --group hydronic-buffer
python scripts/generated_artifacts.py --verify
```

`--check` 仅验证清单，不执行求解。`--verify` 依次运行所选生成器的既有 `--check`，不覆盖产物；无 `--group` 时覆盖全部 13 个生成器。这不执行 pytest 或浏览器链。CI 通过统一入口验证，避免只覆盖早期四个生成脚本。参数通过 argv 传递，不拼接 shell 命令。

## 审查变化

```powershell
python scripts/generated_artifacts.py
python scripts/generated_artifacts.py --base HEAD~1 --json
python scripts/generated_artifacts.py --base master --limit 10
```

默认将工作区（含暂存、未暂存、未跟踪及删除）与 `HEAD` 比较；`--base` 必须解析成真实提交。摘要记录文件增删、字节数、SHA-256 和 JSON 路径的语义变化。键序及相等数值的 int/float 表示差异不计为语义变化；布尔值、删除字段和数组顺序变化会计入。每个文件只展示有限路径，但保留总数；不输出冻结的完整 Python 源码或字段值。无效 JSON 返回非零退出码。

数组目前按索引比较，插入靠前的元素会让后续索引产生变化；摘要只是审查导航，不能代替原始 diff。未知生成规则、未登记手写样例不会被推断为可再生成文件。

根 `.gitattributes` 只对 contracts 和已确认的便携项目生成 JSON 设置 `linguist-generated`。GitHub 可默认折叠这些文件，但文件内容、Git diff、下载和导入能力都保留；recipe 和模块 Python 源码不折叠。CI 上传 `generated-artifact-review`，相对 PR base 或 push 前提交生成摘要。

冻结的 SDK v1–v4 合同及旧版本模块不可因“重新生成”被默默改写。先看摘要，查生成来源和兼容影响，再决定是否更新。新增设备接口产生的 OpenAPI 增量，与类型纯搬移必须保持零差异的要求分别登记。

## 本轮验证

8 项针对性测试通过，覆盖清单漂移/路径越界/重复/缺输出拒绝、语义类型差异、路径转义、输出限额、嵌套目录 Git 的已暂存/未暂存/新建/删除变化、无效 JSON、无副作用及非法 ref。实际执行命令和本轮其他工作包结果统一见 [架构后续验收](ARCHITECTURE_FOLLOWUP_ACCEPTANCE.md)。
