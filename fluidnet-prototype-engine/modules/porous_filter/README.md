# 自定义多孔滤芯

只依赖公共 `fn_sdk`。用当前试算流量计算线性加二次压降，平台负责联网求解。

源码见 [module.py](module.py)，参数与端口见 [manifest.json](manifest.json)。`clogging_ratio` 可在运行时调整；累计通过质量只在接受后提交。参数为教学演示，不是厂家标定。

创建、编辑、发布与组网步骤见 [自定义压降说明](../../docs/CUSTOM_PRESSURE_DROP.md)。
