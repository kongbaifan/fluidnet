# 开放端口制冷设备组设计与使用

2026-11-06。新增 SDK0.10 `composite.refrigeration.open.v1`，保留 SDK0.9 闭合组及旧普通流体组合原语义。该能力按精确子版本展开设备，不新增设备方程、库存或单独时间积分。

## 设计合同

首批开放组用于内置压缩机/性能压缩机、制冷剂液泵、集管、节流阀、泵供液冷风机及热汇集器。容器和库房留在宿主网络，所有必接公开口必须连到真实设备。公开制冷剂/thermal端口一对一映射真实子口，保留类型、方向和必接属性；不伪造单相水力通路。物理工质必须与封装来源的单纯工质一致，允许同后端等价前缀；混合工质、跨域热耦合及作者制冷叶未开放。

按子口的工质回路和内连确定公开circuit，不将换热热口当冷媒口。实际压力等级、供液、取相和房间热量汇集仍由完整网络展开后的编译器验证。公开参数沿用runtime/writable，输出和诊断映射至组实例；两组副本独立持有叶状态，不复制房间/容器热容。

## 宿主验证

开放组不能用两个普通压力源替代制冷边界。`ModuleTestConditions.host_project`保存完整冻结宿主，`host_instance_id`指定其中待测组（缺省D1）。发布或验证时用此次候选模块替换宿主中的目标定义，覆盖目标参数后运行真实动态网络。候选新版本的全部必接口、工质、固定子版本、状态和结果必须通过；无宿主拒绝发布，不假造“独立通过”。

`POST /api/v1/modules/composites/test-context`接收project/instance_ids/module，生成以D1替换选中设备的宿主测试条件；源工程不变。新组保留选中设备页面及该页位置中心。选组内的运行参数、外部连接、回路锚点、PID测量/写目标、测点与工况显式重映射；无法安全改写的脚本/事件拒绝并提示先显式整理宿主。验证历史公开变量同时保留D1.*别名。

封装工程可以保留已显式映射的PID配置；独立发布验证宿主要求无活动控制器、脚本和项目日程，避免控制动作覆盖待测参数。可复制成专用验证项目后移除控制配置。普通验证台的入口压力、出口压力与温度不替换真实容器边界；物理工质由`host_project.fluid`及其已验证锚点决定，发布凭据将fluid规范化为宿主工质。`parameters`只覆盖目标组公开运行参数，外部设备配置及初态由宿主保存。

公开组口用于真实接线；结果使用子设备已提供的公开状态/派生变量，例如`D1.Compressor-1.mass_flow_kg_s`、`D1.state.Pump.electric_energy_j`。本批集总模型没有逐口流股p/h场，不生成假端口状态或普通水力通路结果。

## 示例与复现

[示例目录](../examples/open-refrigeration-groups/README.md)包含两个库房、两台压缩机的来源工程、三类单组宿主、三组搭建完整制冷站和选组配方。所有外部连接、容器M/U与库房热容均保留为显式工程数据。

| 组 | 包含的实际设备 | 外部连接 |
| --- | --- | --- |
| 压缩机组 | 两台压缩机、吸气/排气集管 | 低压循环桶、冷凝器 |
| 供液组 | 液泵、供液集管、节流阀 | 高压贮液器、低压桶、两台冷风机；节流和泵送是两个明确子支路 |
| 冷风机组 | 两台冷风机、回气集管 | 供液集管、低压桶、两个库房thermal口 |

`GET /api/v1/examples/refrigeration-open-group-station`返回完整成组工程；`refrigeration-open-compressors`、`refrigeration-open-liquid-supply`、`refrigeration-open-air-coolers`分别返回单组宿主。也可直接导入示例JSON。

```powershell
python scripts/generate_open_refrigeration_groups.py --check
python -m pytest tests/test_open_refrigeration_groups.py tests/test_module_composites.py tests/test_module_composite_physics.py -q
python -m pytest tests/test_forward_physics.py -k group -q
```

定向验收覆盖：三类开放组每帧全部实际设备变量与手工展开逐值对照；单回路质量残差小于1e-8kg、能量残差小于0.02W；三个组连接同一真实站；两个相同供液组副本的参数与累计能耗独立；缺口、错工质/锚点、错SDK或子版本、错误公开端口及未知参数拒绝；宿主候选替换、三类发布重启、锚点和观察变量重映射；真实取液失败后物理/累计量/时间回退，已接受公开参数命令保留，组内诊断追溯至子路径。未运行全量测试。界面验收见[开放组画布验收](OPEN_REFRIGERATION_GROUPS_UI_ACCEPTANCE.md)。

2026-11-06本次结果：开放组26项、普通/热组合9项、SDK3项、旧闭合制冷组3项，共41项通过（27.78秒）。组内初始化和推进故障均验证错误归属与已接受状态；生成器`--check`、改动Python的ruff及mypy通过。
