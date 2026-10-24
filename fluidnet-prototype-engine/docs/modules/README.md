# 模块系统实施与证据

对应 [模块系统优化计划](../MODULE_SYSTEM_OPTIMIZATION_PLAN.md)。M0、S0–S3 已形成实现及本地证据；正式作者模块版本、状态事务和新热回调按后续工作包推进。

| 工作包 | 本地交付 | 状态 / 证据 |
| --- | --- | --- |
| MOD-B0 | 环境、模块/API 清单、commit + binary patch + untracked overlay 基线包 | 待评审；[M0 结果](results/M0.md) |
| MOD-B1 | 七类可重放场景、真实 RPC 请求/响应、已接受帧和质量账本 | 待评审；[M0 结果](results/M0.md) |
| MOD-B2 | v1 固定合同/项目样例和版本决策 | 待评审；[兼容决策](V1_COMPATIBILITY.md)、[M0 结果](results/M0.md) |
| MOD-S0 | 标准库公共类型接口、严格类型示例、轻依赖 CI 和 PEP 561 打包 | 待评审；[SDK API](SDK_API.md)、[S0 结果](results/S0.md) |
| MOD-S1 | resistance 构建器、共享阻力/流量单位工具、原公式与导数回放 | 待评审；[SDK API](SDK_API.md)、[S1 结果](results/S1.md) |
| MOD-S2 | 冻结 v1/v2 解析与哈希、SDK/能力/状态合同声明、执行前兼容检查 | 待评审；[协商合同](CONTRACT_VERSIONING.md)、[S2 结果](results/S2.md) |
| MOD-S3 | SDK 0.3.0 时间/阶段、会话/请求/子步身份、数据来源及接受时间标记 | 待评审；[阶段合同](EXECUTION_CONTEXT.md)、[S3 结果](results/S3.md) |

在工程目录运行：

```powershell
python scripts/benchmark_modules.py
python scripts/benchmark_modules.py --no-batch --cases multi-instance --output artifacts/module-system/98dadd5/MOD-B1-unbatched
python scripts/benchmark_modules.py --workers 2 --cases multi-instance --output artifacts/module-system/98dadd5/MOD-B1-sharded
python scripts/module_baseline.py
python -m pytest -q tests/test_module_system_baseline.py tests/test_module_v1_compatibility.py tests/test_module_versions.py
```

默认产物目录为 `artifacts/module-system/<当前短 commit>/MOD-B0/` 和 `MOD-B1/`，不提交完整原始请求与计时。B0 已存在的基线不能覆盖，再次采集应使用新的 `--output` 目录。B1 每个场景输出 `project.json` 和 `result.json`，总索引为 `report.json`。

回放使用保存的项目快照，保留其中源码与模块版本；不会自动替换为当前目录中的模块：

```powershell
python scripts/benchmark_modules.py --replay artifacts/module-system/98dadd5/MOD-B1/single-valve/project.json --output artifacts/module-system/98dadd5/replay
```

脚本临时设置独立数据/模块目录，结束后清理；不打开已保存的用户工作区。仓库内输出只允许放在 `artifacts/module-system/`。完整源码回放应另建 checkout，按 `baseline.json` 中的 commit、patch、overlay 与哈希恢复，再运行场景；不能向当前用户工作区应用这些补丁。

恢复后可在隔离 checkout 运行 `python scripts/module_baseline.py --verify <baseline.json绝对路径>`。tracked 文本同时保存原始字节和 LF 规范化哈希，允许 Git 的 CRLF 转换；untracked overlay 必须逐字节一致。修改实际源码仍会拒绝通过。本轮有效 B0 产物为 `MOD-B0-r2/`；首轮 `MOD-B0/` 在隔离重放时暴露换行差异，保留为失败证据。

这是 M0 正确性基线，每场景执行一次，不能作为冷启动 5 次/热运行 7 次的性能验收。RPC 时间与求解时间重叠，不相加；`_request` 次数不包含关闭时直接写管道的 finalize。原始响应包括物性输入、关系、状态和诊断；帧中的求解计数继续沿用已有口径。
