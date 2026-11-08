# 底层扩展实施与验收

日期：2026-11-08。本轮接续中断的“都补完向我汇报”任务；在同一工作树继续实现。用户没有厂家或现场数据，已授权使用公开资料和自定义参考工况。

**本轮交付了一组可执行扩展，F3、F4 和工程标定仍有明确未完成范围，不能把下表解释为所有底层缺口已消失。**

## 工作包结果

| 工作包 | 本轮可执行结果 | 仍保留的边界 |
| --- | --- | --- |
| F1 流股与取口 | 高度取口静压/相焓传入下游；同一容器支持多条独立串联流股；共用原 M/U 库存 | 共享有限阻力使用新图式网络；原串联系统仍拒绝共享管段。液阀、气体压缩机不自动跨相变换 |
| F2 制冷管网 | 压力、质量、焓联立；曲线泵工作点；供液/湿回气支路阻力；独立持液单元 M/U 参加隐式步 | HEM 均相平衡，无滑移/流型/临界流；参考几何曲线，未做现场管径选型认证；大图计算成本待优化 |
| F3 作者与跨域 | schema 5、SDK 0.11.0 压缩机/冷凝器本构；Worker、接受事务、验证台、失败回放、续算；制冷作者连接原生液体侧 storage_v1 | **部分完成**：任意作者物理储量/DAE/多端口状态方程、图式网内作者压缩机/冷凝器、液体/制冷双侧 Python、直接湿空气跨域未开放 |
| F4 动态精度 | 原生流体/风水、冷库 A、storage_v1 步加倍误差接受；制冷站恢复 kg/J/K 后比较误差；失败段完整回滚；固定步融霜结束事件定位 | **部分完成**：流体/风水 Python 作者自适应事务重放、通用取口跨液面事件与自动相态切换未做；自适应融霜提前结束在外部分段端点判断 |
| F5 断点续算 | JSON 完整会话、摘要与数值源码校验、SQLite 保存、重启后新 run 延续原时钟；PID/脚本采样、Worker 状态、统计/热启动及物理库存恢复 | 改变数值实现拒绝旧快照；历史曲线不能当物理状态；后台动态运行才产生完整快照 |
| F6 外部校核 | NIST 氨 Antoine 关联式、独立层流解析极限、潜热/湿量/守恒参考；保留来源、温区、误差及脚本 | **参考校核完成，厂家/实测标定未完成**。无同工况日志或厂商包络，不能用守恒残差替代 COP/功率工程精度 |
| F7 冷库过程 | 热湿/门交换、货物潜热、霜水/表面能量、热气凝液/排水、油库存/回油/油冷却、工作机泵备用切换 | 集中参数参考模型；不解析货物空间冻结、油溶解/润滑膜、热气临界流。安全泄放、氨检测/通风保护不包含 |

## 可直接使用的入口

五份项目位于 [examples/foundation](../examples/foundation/README.md)，可导入网页项目；对应 API 示例同页列出。既有六库工程保留原设备解释，不会因新模块登记改变物理模型。

```powershell
python scripts/generate_foundation.py --check
python scripts/validate_foundation_reference.py
python -m pytest tests/test_foundation_stream_branches.py tests/test_foundation_network.py tests/test_cold_processes.py tests/test_author_constitutive.py tests/test_timestep_domains.py tests/test_session_checkpoints.py tests/test_foundation_standby.py -q
```

新增 `GET /api/v1/runs/{id}/checkpoint-project` 返回快照对应项目和已接受参数；`POST /api/v1/runs/{id}/resume` 创建续算子运行。`duration_s` 是原时钟的绝对终止时刻，须晚于快照。源码变化或摘要不一致明确拒绝。

快照还修复了接续中发现的问题：脚本 next_s/samples 未保存、自适应统计对象恢复后未重新绑定、风侧附加结果未声明为数据字段、schema 5 成功模块事务未清理而阻止捕获快照。恢复不重新初始化库存后修改时间标签。

## 独立参考证据

来源表为 examples/foundation/reference-sources.json；scripts/validate_foundation_reference.py 输出 artifacts/foundation/reference-validation.json。

- 氨在 239.6–333.15 K 的八点，与 NIST Chemistry WebBook 的 Stull (1947) Antoine 参数比较，最大相对差 **1.8251%**。3% 回归阈值为项目选择，不是 NIST 不确定度。
- 层流管段与独立 Hagen–Poiseuille 极限比较，压降 **8.17578053505 Pa**，相对差约 **2.44×10⁻¹³**。
- 不同长度两支路初始化约 **0.186889 与 0.140858 kg/s**，总量 **0.327747 kg/s**；等长重新求解为等流量，通过独立泵曲线插值检查。
- 持液质量随时间变化，全回路质量/能量账闭合，恢复后下一步与连续轨迹一致。
- 过程验收包含潜热、真实热气、两套独立油路、任意 ID、回滚、报告和续算。固定步融霜结束样例定位到 **0.0061840128 s**，而非把整步末态强行截到目标温度。

这些分别是关联式差异、解析极限和数值守恒，未合并成所谓设备精度。

## 兼容与校验

新增八类设备，目录由 60 类扩展到 68 类。原 60 类定义哈希与相对顺序保持测试；schema 1–4 独立冻结。组合合同 30 个 schema 扩展逐项登记旧/新哈希，保留原模型分层基线。

新生成器已登记，合同/OpenAPI 由源码生成，日常 CI 制冷/会话专项加入新管网、过程、作者、时间步和续算。完整静态/回归结果见下文；专项与首轮全量结果分开保留。

最终前端 **300 项单元测试通过**。新增真实浏览器续算验收通过：1 s 末帧恢复、单步到 1.1 s、继续至 2 s，原项目后续修改保留，零页面错误。六库浏览器四工况三小时仿真、保存失败恢复、反复替换、导出重载和报告通过。51 台组装中浮层拦截双击已修复为避让所选设备，并通过该流程及原路径追踪交互复测。

详见 [作者本构](AUTHOR_CONSTITUTIVE.md)、[动态误差覆盖](TIMESTEP_DOMAIN_COMPLETION.md)、[冷库过程](COLD_STORE_PROCESSES.md)。

本轮专项联合运行 **54 passed**；其后新增卧式/封头取口两项回归，图式网络单独整组 **7 passed**。Ruff、普通 mypy（166 文件）、严格 SDK（12 文件）、session（2 文件）、runner（3 文件）通过。全部 15 个生成器的只读验证通过，包含 118 份合同/OpenAPI/参考文件。


## 最终回归记录

- 全量后端首轮：**2491 passed / 10 failed / 5 warnings**，耗时 42 分 32 秒。该长进程启动后仍在进行本轮修复，保留了已加载的旧实现；不能把这份日志改写为单次全绿。
- 将首轮十个失败 nodeid 固定保存，修复后在同一新进程统一复测：**10 passed in 21.85s**。失败涉及固定步接受帧/趋势体积、生成器登记、模型兼容新增断言、风侧续算状态、设备目录清单/参数观测、无冷机合成管网误入冷机检查、API 示例包含本机 package_path。未放宽物理容差或趋势体积上限。
- 首轮之后补充的定向验收：续算 **9 passed**，制冷设备与注册 **36 passed**，冷机范围与设备注册 **33 passed**；图式网络最新整组 **7 passed**。这些与其他测试有重叠，不合并成虚构的独立总数。
- 最终前端 **300 passed**；CI 选择/登记 **23 passed**。浏览器六库、组装、路径追踪、续算真实流程已通过，续算证据在 artifacts/foundation/checkpoint-resume.json。
- Ruff、普通及三套严格 mypy、git diff --check 通过；十五个生成器只读验证通过；末次 foundation/contract 校验继续通过。

原始日志：artifacts/foundation-full-pytest.log、foundation-failed-targets.json、foundation-failures-final.log、foundation-acceptance.log、foundation-ui-final.log、foundation-generated-final.log。最新快照还对 Python 与 numpy/scipy/CoolProp/pydantic 版本建立身份校验，并把运行中修改的 PID 设置带入独立续算项目。

这轮完成了上述范围的实现与验收，**尚未把 F3/F4 的任意作者储量、统一双侧作者事务、通用跨液面相态事件和实际厂家/现场标定实现完毕**。没有把这些限制隐藏为已完成。
