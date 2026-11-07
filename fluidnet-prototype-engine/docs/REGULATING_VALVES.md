# 压差旁通阀与PICV首版

2026-11-05。两个新ID v1：`differential_bypass_valve`、`pressure_independent_valve`，普通单相液体，无储量，正向通流；旧阀门不变。源包由 `scripts/generate_regulating_valves.py` 生成，`--check`只核对。

旁通阀内部开度为clip((Δp−开启压差)/比例带,0,1)，再按真实Kv关系求流量。它是比例调节式设备，超过比例带后全开，不声称严格恒压。反压关闭，最大压差在最终结果观察阶段检查，超界拒绝。

PICV采用理想准静态机械调节，规定最小工作压差、最大允许压差、额定体积流量和设定比例。达到最小工作压差后通过限制有效Kv维持设定流量；低压差时有限Kv导致流量随sqrt(Δp)减小，关断与反流为零。密度按入口p/T物性计算，示例采用node物性联算。无动作时间、回差、汽蚀与厂家标定。

可行范围参考制造商对最小工作压差/恒流调节区的定义，不复制其专有结构或精度：Belimo Mechanical Pressure Independent说明、Danfoss AVDO比例旁通原理。实现参数为教学输入，不是品牌型号。风水湿空气路径未验收，模块不声明air.pass_through.v1。

规范量为绝压Pa、kg/s、m³/h、0–1比例；显示kPa/%按合同转换。evaluate无状态修改，observe只读取已收敛流量，累计质量只在commit_step接受后变化。

验证：`python -m pytest -q tests/test_regulating_valves.py` 27 passed，包含压差/开度扫掠、独立Kv式、低压差失调、反压、运行改目标、超压拒绝不推进累计、真实Worker验证台。初轮因并行目录曲线参数单位修复暂失败，最终已通过。两阀的空白组装/导出重载浏览器结果由整体实施记录登记。

示例：`examples/regulating-valves/*.project.json`，可导入或按其中三设备、两连接从空白组装。模块先做普通fluid液体，不能宣称任意湿空气/风水执行域可用。
