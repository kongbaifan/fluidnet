# 管道管件参考模块

按管件类型取局部阻力系数 K，再折算成等效阀门 `Kv` 参与水力求解：

```text
A  = π·d²/4
Kv = 50912·A/√K
```

`evaluate()` 只注册 `main` 通路的阀门等效关系并输出有效 K 与流速；`commit_step()` 用收敛流量累计 `state.throughput_kg`。

- 管件表：`elbow_90=0.9`、`elbow_45=0.4`、`reducer=0.5`、`tee_through=0.2`、`tee_branch=1.0`、`entrance=0.5`、`exit=1.0`。
- `fitting_type="custom"` 时使用参数 `loss_coefficient`；其余类型未匹配时也回退到该参数。
- K 下限为 `0.05`，避免等效 Kv 过大。
- 密度优先取 `in0` 端口值，缺失时回退参数 `density_kg_m3`。
