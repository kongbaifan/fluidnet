# 止回阀参考模块

`evaluate()` 比较入口与出口绝对压力：

- 任一压力缺失（还未拿到端口状态）时按正向处理。
- `p_out − p_in > cracking_pressure_pa` 时判定反向：`opening_ratio = 0`、`direction = -1`，水力求解器把零开度支路当作零流量约束。
- 其他情况按正向开启：`opening_ratio` 取参数值、`direction = +1`。

`commit_step()` 在提交方向为反向时累加 `state.closed_steps`，并用收敛流量累计 `state.throughput_kg`；`state.last_direction` 保存最近一次提交的流向，供下一步判断使用。
