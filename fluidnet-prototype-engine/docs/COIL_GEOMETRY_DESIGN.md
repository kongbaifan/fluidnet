# 干盘管几何设计层（S5-4）

2026-11-06。适用于内置water_coil及公开Coil参数的AHU/FAHU/FCU。在设备参数页点击“盘管几何设计”，输入几何及有来源系数，预览后仅填入草稿，确认应用才改变设备。

设计卡：没有新增物理储量或第二套运行算法，输出映射现有air_side_ua_w_k、水侧UA、两侧等效直径和K。规范API为POST /api/v1/equipment-library/coil-geometry，严格CoilGeometryRequest/Response。输入单位全部明确SI；并联管数/翅片数整数，外径必须大于内径、管孔/净通风面积不超过迎风面积、翅片总厚度小于管长。

解析几何：N根同尺寸管的内面积=NπdiL；裸外面积=Nπdo(L−nfin·tfin)；双面翅片面积=2nfin(WH−Nπdo²/4)；有效外面积=裸外面积+ηfin·翅片面积。指定h_air乘有效面积得到空气侧UA；水膜热阻1/(h_water·Ainside)与圆壁导热ln(do/di)/(2πkLN)串联形成水侧UA。热阻均有限正，最终有效UA按两侧串联计算。

水侧等效直径√N·di保存总流通面积，K=f_Darcy·L/di+K_minor保持单管实际速度基准；风侧等效直径√(4A_free/π)，K为有来源输入。本版不自动计算Re/翅片传热/摩阻经验关联，不冒称全工况数据库；系数是显式设计点资料。忽略集管不均流、接触热阻、管壁热容和复杂翅片形状；设计只覆盖干盘管，湿面/结霜另验。运行仍按原水盘管双回路真实物性与适用域处理。

几何输入和结果来源随项目实例geometryDesign保留在工作区封装里，不写物理模块哈希。已有design.py和草稿/应用接口保持兼容。独立面积/等效速度基准测试、非法几何测试和真实三回路盘管求解通过；browser-design-library原生FCU设计/应用/重载通过。生成截图与证据见DESIGN_AND_GROUP_LIBRARY.md。
