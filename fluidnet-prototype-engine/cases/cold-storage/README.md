# 冷库案例

本目录是“−18°C 单库房 → NH₃ 制冷 + CO₂ 液泵载冷系统”的计划和实施入口。2026-10-19 完成 A0（固定输入数据与独立循环参考），2026-10-20 完成 A1（库房热节点 + 理想冷源贯通引擎与页面），2026-10-21 完成 A2–A6（真实单级循环、库房/货物/冷风机耦合、控制与日程、报告与对照、案例验收，见 [VALIDATION-A](single-room-minus18/results/VALIDATION-A.md)）。

- [完整开发计划](PLAN.md)：范围、模型、阶段、工期与验收。
- [任务与实测进度](TASKS.md)：已完成内容、下一步与证据。
- [单库房案例说明](single-room-minus18/README.md)：参数、七组日程与验证命令。
- [NH₃/CO₂ 扩展范围](nh3-co2/README.md)：B 版入口；含[倍思鹿案例拆解](nh3-co2/BASELU_CASE.md)与 [B 版执行计划](nh3-co2/EXECUTION_PLAN.md)。

```text
cold-storage/
  PLAN.md                         完整计划
  TASKS.md                        任务和进度
  single-room-minus18/
    README.md                     参数与工况说明
    parameters.json               单位为 SI 的版本化假设参数
    scenarios.json                七组仿真工况与事件日程
    sources.json                  参数来源和模型边界
    references/                   独立计算结果与验证报告
  tools/
    verify_reference.py           输入校验及独立循环参考
  nh3-co2/
    README.md                     NH₃/CO₂ 后续扩展入口
    BASELU_CASE.md                倍思鹿公开案例拆解与 B 范围
    EXECUTION_PLAN.md             B 版执行计划
```

在本项目根目录运行：

```powershell
python cases/cold-storage/tools/verify_reference.py --check
python -m pytest tests/test_refrigeration_a1.py tests/test_refrigeration_cold_store.py -q
python scripts/verify_cold_storage.py --output artifacts/cold-storage-a6-<日期>
```

第一条命令需要安装项目既有依赖中的 CoolProp，直接按热力方程核对输入与 A0 独立工作点。第二条运行 A1 与 A 版产品验收，第三条在全新工作区跑完七组工况并输出案例包。浏览器链路（创建案例 → 选工况运行 → 单步改参数 → 改日程 → 导出报告/CSV/对照 → 保存 → 重启复算）用 `node tests/browser-cold-storage.mjs` 运行，需要 Playwright 与 Edge，与既有浏览器验收脚本相同。

输入参数和工况是工程示范假设，数据文件采用本案例的 `schema_version=1`，尚不是引擎 `Project` 导入格式。工作台上的案例由引擎 `/api/v1/examples/cold-storage-room` 生成（A1 理想冷源种子仍为 `/api/v1/examples/cold-storage`），参数与工况和本目录文件逐项一致（由测试核对）。
