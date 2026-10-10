# 可编程阀门示例模块包

这个目录展示第一版模块包格式：`manifest.json` 保存契约，`module.py` 实现 `initialize/evaluate/commit_step/finalize`。

`evaluate()` 只调用 `ctx.net.valve()` 注册当前试算关系；`commit_step()` 才更新累计通过质量和提交次数。
