# 热耦合液体作者阀门

公共 SDK Python 示例，位于制冷站配套的无储量单相液体回路。有效开度为 `opening_ratio ** characteristic_exponent`，流量由全网求解。指数 1 对应线性开度，指数 2 用于比较不同开度特性。

该模块没有独立蓄水或蓄热状态，也不添加主动热量。`ctx.state` 仅演示离散记账；平台 `state.transferred_mass_kg` 另按真实接受内部步积分。参数、时间语义、作者范围和运行入口见[使用说明](../../docs/COUPLED_LIQUID_MODULES.md)。

在模块编辑器修改源码后保存新版本，再让项目显式采用。原运行及旧报告继续使用冻结版本。示例公式未经厂家或现场标定。
