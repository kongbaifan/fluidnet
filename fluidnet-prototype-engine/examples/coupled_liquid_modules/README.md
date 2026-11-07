# 作者水阀与制冷站热耦合

从“项目 → 导入单项目”选择 [`author_loop.json`](author_loop.json)。该文件含完整 Ammonia 制冷站、闭式 Water 回路、内置浸没盘管和公共 SDK 作者阀门，模块源码及哈希已内嵌。

建议先动态运行 2 s，输出间隔 1 s；随后比较 80%/40% 指令开度和平方特性。模块 `coupled_liquid_valve` 的实例编号为 `LiquidValve-Custom`，支持运行时开度调节、版本升级/回退、归档报告和批量工况。

操作及模型范围见[使用说明](../../docs/COUPLED_LIQUID_MODULES.md)。重新生成使用 `python scripts/generate_coupled_liquid_example.py`；一致性检查加 `--check`。
