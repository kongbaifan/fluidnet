# 制冷设备模块组装清单

组装recipe仅包含工质、规范参数、设备与连接，适合对照从空白画布逐个组装：

- `single-room.recipe.json`：R134a单库，8设备9连接。
- `two-room.recipe.json`：双库双压缩机，15设备18连接。
- `cascade.recipe.json`：NH₃/CO₂单库，10设备13连接，包含两个回路工质锚点。
- `air-cooled.recipe.json`：卧式圆筒容器与风冷冷凝器，8设备9连接；液位高度按几何反解，冷凝器空气侧为环境边界。

同名`.project.json`是包含模块定义的规范项目，可通过“项目 → 导入项目”载入。recipe中的参数采用规范单位，界面须按合同换算，例如K→°C、比例→%、m³/s→m³/h。开始运行前完成端口连接、初态和设计参数核对。

详见[组装说明](../../docs/REFRIGERATION_MODULES.md)及[实际验收](../../docs/REFRIGERATION_MODULAR_ACCEPTANCE.md)。这些示例为模块组合与守恒验证，不是已配置恒温控制或厂家选型结果。
