# 冷库设备模型扩展 · 第一批

日期：2026-11-05。按设备模型扩展主线交付三种新目录模块，不增加控制模板。分支沿用 `codex/device-panel-and-chiller-controls`，此前未提交工作保持原位。

## 新设备

| 设备 | 模块ID | 新物理能力 |
| --- | --- | --- |
| 卧式圆筒贮液器 | `horizontal_receiver` | 内径与直筒长度决定容积，由M/U/V决定饱和状态，圆截面液位反解 |
| 卧式圆筒低压循环桶 | `horizontal_drum` | 同上，气/液出口独立供吸气、液泵或满液蒸发侧 |
| 风冷冷凝器 | `air_cooled_condenser` | 恒温制冷剂侧与有限空气热容量换热，出口空气温度、风机立方功率、独立自然散热及反向换热 |

卧式容器的 `level_ratio` 仍表示液体体积分数；高度比另用 `state.level_height_ratio`。直径0.8m、容积0.6m³、体积分数40%的设计点对应高度比42.11319%、高度0.3369055m。旧容器仍按原volume/height合同工作，输出键不自动变化。

风冷冷凝器为单个制冷剂压力等级上的排热设备，空气侧是显式环境边界。强制风侧采用 `G=C(1-exp(-UA/C))`，自然导热系数独立并联、默认0；风机热排到环境，不重复加入制冷剂账本。停风时空气出口温度为空；环境更热时保留负排热，不截成零。

模型细节与依据：[卧式容器](HORIZONTAL_VESSELS.md)、[风冷冷凝器](AIR_COOLED_CONDENSER.md)。本批忽略容器封头、倾斜和液面晃动，未加入厂家性能图、制冷管路压降、DX过热度或融霜。恒定UA与空气比热属于首版明确假设。

## 使用与组装

从“新建项目 → 空白冷库画布”进入，在“制冷站设备”中插入上述模块；它们沿用气/液相和冷凝进出口连接规则。参考 `examples/refrigeration-modular/air-cooled.recipe.json` 逐台设参，或从项目页导入同名 `air-cooled.project.json`。API示例为 `/api/v1/examples/refrigeration-modular-air-cooled`。

新示例替换单库回路的两个容器和冷凝器，仍为8设备9连接。风冷UA按有限风量反算，不能直接使用蒸发式冷凝器的Q/温差UA。初始净库负荷5kW，冷凝排热约7.8862kW，5kg/s空气从20°C升到约21.56784°C；额定风机电功率300W。

新变量已进入设备面板、组装概览、曲线可选项以及冻结CSV/HTML报告。HTML明确显示液位高度和体积分数及风冷工作点，不宣称组合项目自动配置了压力或库温控制。

## 实际验证

仅执行定向验证，未运行全量或触发远端CI：

| 检查 | 结果 |
| --- | --- |
| `tests/test_horizontal_vessels.py` | 37 passed，独立几何积分/反解、物性、合同、NH₃/CO₂库存和能量 |
| `tests/test_air_cooled_condenser.py` | 28 passed，独立空气微元积分、有限风量、零UA、停风、反向换热、功率和单位 |
| `tests/test_refrigeration_equipment_expansion.py` | 4 passed，真实整站能量账、运行调风/停风、非法参数拒绝、报告及服务重启、生成物一致 |
| 原设备目录新增ID断言 | 单项复验1 passed；旧设备组其余项在定向检查已通过 |
| 前端概览与参数转换 | 6 passed |
| `browser-refrigeration-modular.mjs --equipment` | 完整真实组装流程通过，无页面错误 |
| 质量检查 | 改动文件ruff、mypy96文件、90份合同生成一致、JavaScript语法和差异检查通过 |

浏览器基准1920×1080/DPR=1，逐台插入设备而非导入完整案例，画布生成的D-23等ID与recipe不同。实际操作包括尺寸/风冷参数输入、拖动布置、9条端口连接、运行60秒、将库房附加热从2220W改为6000W、保存导出、导入新项目后刷新复算。初始库温255.15K，改变负荷后60秒为255.26183448071248K，导入复算到7位小数一致。

该流程还发现拖动结束后100ms抑制计时会吞掉下一次真实端口点击，已改为新pointerdown清除抑制，仅屏蔽拖动本身产生的尾随click；每条连接都有实际计数断言。

截图 `artifacts/refrigeration-modular-air-cooled-assembled-1080p.png` 已实际查看；设备名称、液位高度、风冷排热/出风温度/功率均可见。新代码仍保留本地，未提交、未合并。
