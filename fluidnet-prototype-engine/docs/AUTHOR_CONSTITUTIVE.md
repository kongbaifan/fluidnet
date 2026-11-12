# 制冷作者本构合同与验收

2026-11-08。新增 schema 5 / SDK 0.11.0，为 Python 作者模块开放压缩机和冷凝器本构。schema 1–4 的定义、规范哈希与原有节流角色保持原含义。

## 已交付能力

- `refrigeration.compressor.v1`：`suction` / `discharge` 两个制冷剂端口。平台提供饱和吸气状态、出口压力及等熵出口焓；作者返回流量、出口焓、轴功和输入电功。
- `refrigeration.condenser.v1`：`in0` / `out0` 同一压力等级端口。作者计算饱和容器对指定热沉的排热和风机输入电功；平台把排热从容器内能中扣除。
- 两种角色均使用隔离 Worker 执行。作者通过 `ctx.refrigeration.point` 读取冻结 SI 输入，通过 `ctx.refrigeration.balance(...)` 提交一次本构结果。牛顿试算不会提交作者 JSON 状态；`commit_step` 只随平台接受段提交，失败段保留旧状态。
- 父进程重新校验有限值、角色、参数一致性、`Pshaft = m × (hout − hin)`、电功不小于轴功、压缩机等熵下限、停机零流量零功率，以及冷凝器被动换热方向。作者不能覆盖平台库存、压力或功率观察字段。
- 平台的容器质量、内能和库房温度仍共同进入隐式求解及守恒账。作者 JSON 状态用于控制记忆和接受步累计，不替代物理库存。
- schema 5 制冷作者可通过显式热耦合连接内置液体侧，包括 `storage_v1` 储热联算；接受事务统一提交作者状态。液体侧 Python 作者与制冷侧 Python 作者同时存在的项目明确拒绝，防止两套模块适配器互相覆盖。
- 独立验证台、API 模板、模块保存与重新加载、运行失败回放和完整会话续算支持新角色。界面可选择“制冷压缩机本构”“制冷冷凝器本构”模板，使用相应的边界默认值。

## 运行入口

新建模板的标识为 `refrigeration_compressor` 与 `refrigeration_condenser`，经现有模块模板接口创建。代码示例与冻结 manifest 位于 `examples/refrigeration_extensions/sdk_compressor.*`、`sdk_condenser.*`。

`fn_engine.refrigeration.author_examples.author_station_example()` 返回完整容器站项目，可序列化保存和运行；参考项目由基础算例生成脚本统一维护。

单设备测试可直接运行：

```python
from fn_engine.bench import run_module_test
from fn_engine.models import ModuleTestRequest
from fn_engine.refrigeration.author_examples import definition

result = run_module_test(ModuleTestRequest(
    module=definition('compressor'), duration_s=.2, dt_s=.1))
print(result.constitutive_evaluation)
```

参考压缩机使用自定义压比修正容积效率；参考冷凝器使用自定义风机转速–UA 和风机功率关系。这些是可检验的自定义关系，没有宣称对应实际厂家的设备标定。

## 保留的适用边界

新本构角色仍采用饱和容器边界。图式管网内部的作者压缩机和冷凝器明确拒绝编译，避免绕过作者方程而调用内置模型。直接与湿空气域连接也不支持；跨域须采用显式热耦合和内置液体侧。schema 4 的节流角色保留纯制冷站范围。

尚未开放任意作者质量/内能坐标、自定义 DAE 残差、任意多端口两相设备和作者物理储热。这些不能以 `state.json.v1` 或本次纯本构角色替代。当前可用物理储量由平台的容器、管内库存和过程设备登记、积分和校验。

## 验收证据

`tests/test_author_constitutive.py` 检查真实 Worker 验证台、项目 JSON 往返、站级质量和能量守恒、非法产能/过高效率/停机输出拒绝、接受状态保留、源码与 manifest 一致，以及重启续算与连续运行轨迹一致性。

模型分层兼容检查保留 `tests/fixtures/model-layering.json` 原基线；新增 `model-layering-foundation.json` 对 30 个受合同扩展影响的公开及嵌套模型逐一登记旧、新 schema 哈希，并独立锁定 schema 1–4。未登记模型继续按原哈希检查。
