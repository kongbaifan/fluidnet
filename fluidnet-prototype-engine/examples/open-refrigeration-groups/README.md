# 开放制冷设备组示例

`source.project.json`是可直接运行的两个库房、两台压缩机的手工设备网络。

- `compressors.project.json`：压缩机及吸/排气集管封为D1，接外部循环桶和冷凝器。
- `liquid-supply.project.json`：液泵、供液集管、节流阀封为D1，保留真实泵供液和高压节流两个子支路。
- `air-coolers.project.json`：两台冷风机及回气集管封为D1，各热口接外部库房。
- `grouped-station.project.json`：使用以上三个组搭建的完整制冷站。

对应的`*.recipe.json`提供来源文件、选组设备ID、模块名与公开端口；不把开放组作为闭合工程运行。模块定义已嵌入宿主的modules，可用于发布请求；测试条件须携带该完整host_project及host_instance_id。设计点属于教学假设，不是设备性能标定。

生成与只读检查：`python scripts/generate_open_refrigeration_groups.py`及同命令加`--check`。封装合同、宿主测试API与验证范围见[说明](../../docs/OPEN_REFRIGERATION_GROUPS.md)。
