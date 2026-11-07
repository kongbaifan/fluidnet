# 模型类型分层

2026-11-07。`models.py` 已改为历史导入的兼容入口，原有 127 个类迁移至 `model_types/`。引擎内部和合同生成器按实际依赖导入对应层；`model_types/__init__.py` 不聚合加载各层。

| 层 | 内容 | 允许依赖的同包层 |
| --- | --- | --- |
| `base.py` | 工质、端口和通路状态、诊断、模块包引用 | 无 |
| `module.py` | 模块定义、manifest、版本及迁移记录 | base |
| `protocol.py` | Worker 请求／响应、执行上下文、接受步候选及回放快照 | base、module |
| `domain.py` | Project、设备实例、连接、控制、求解配置及项目文档 | base、module |
| `run.py` | 运行请求、选项、帧、事件及命令 | base、domain |
| `module_testing.py` | 模块验证台、工况和断言合同 | base、module、protocol、domain、run |
| `http.py` | REST 输入／输出、工作区与目录响应 | 上述各层 |

这些是依赖层，不是新的进程或服务。`protocol` 与 `domain` 并列，Worker 加载路径不再通过 HTTP／Project 聚合文件；HTTP 层可以引用领域对象。`base` 和模块类型继续引用现有冻结的 `_module_schema_v1`～`v4`，冻结 SDK 合同不迁移、不重写。

新增代码直接导入所需层，例如 `from fn_engine.model_types.domain import Project`。外部已有的 `from fn_engine.models import Project` 仍得到同一个类对象，兼容入口显式重导出旧名称。历史 pickle 中的 `fn_engine.models.ClassName` 也可解析；新对象的 Python `__module__` 路径会反映实际实现位置。这不改变 JSON 线格式，且不把 Python pickle 作为新的持久化接口。

`tests/fixtures/model-layering.json` 记录拆分前 `models.py` 的源 SHA-256 以及 127 类的 JSON Schema SHA-256。它是兼容基线，不随新增 HTTP DTO 自动重建。本次核对该源 hash 与 `c7410f6` 的文件一致，原 127 类的 AST 实现体均未改变。字段、默认值、验证器、遗漏空字段和序列化行为保持原样，旧 Project JSON、模块内容／定义双哈希和 SDK 使用方式无需迁移。

`tests/test_model_layering.py` 验证所有旧类的 schema 与导入身份、默认值和序列化遗漏、冻结身份与额外字段拒绝、历史 pickle 名称，以及新进程导入隔离。依赖检查阻止后端重新导入兼容聚合器，阻止类型层反向依赖。新进程分别加载 `protocol`、`runtime`、`worker` 时，不应出现 `models`、HTTP DTO、Project 或 API 模块。

验收证据：分层完成时运行的模型／冻结 SDK／Worker 启动／运行合同专项共 82 项通过，后端 ruff 和 mypy 通过；`python scripts/generate_contracts.py --check` 报告 111 份生成合同一致。随后 Runner 协议的针对性验证见 [Runner 接口](RUNNER_PROTOCOL.md)。后续设备展示元数据对 OpenAPI 的新增属于独立功能差异，不应通过更新上述 127 类基线来吸收。

本轮范围和总验收入口见 [架构后续验收](ARCHITECTURE_FOLLOWUP_ACCEPTANCE.md)。
