# 倍思鹿参考算例库（v0）

> 生成日期：2026-10-22。数据来自本机只读副本 `倍思鹿数值仿真-V5.3`，**未运行倍思鹿 exe，也未修改其安装包内任何文件**。
> 生成脚本：[extract_baselu_cases.py](../scripts/extract_baselu_cases.py)；fixture 目录：[tests/fixtures/baselu](../tests/fixtures/baselu)。

## 目的与边界

本库只保存倍思鹿工程数据库（`.PJTDB`）里的**参考配置与变量快照**，供 FluidNet 做回归输入、边界/初值对照和变量契约检查。它不是数值验收基准：

- 快照没有经过本次运行的收敛确认，不能保证是收敛后结果。
- 不比较两边求解器的精度，不声称 FluidNet 与倍思鹿数值等价。
- 与 [BASELU_COMPARISON.md](BASELU_COMPARISON.md) 的口径一致：该文明确“尚无双方完整同工况的精度或性能对测”，本库仅作回归输入，不改变这一结论。

因此，任何测试都只能断言“变量集合完整、量级合理、趋势方向一致”，不得把本库的数值写成容差断言的期望值。

## `.PJTDB` 结构

两个工程文件均为 UTF-8 明文 JSON：

- `AlgProject/ASDFGHJ/ASDFGHJ_DB.PJTDB`（约 114 KB，34 个 MOD、7 个 NOD）
- `AlgProject/NH3CO2ZL/NH3CO2ZL_DB.PJTDB`（约 1.1 MB，222 个 MOD、63 个 NOD）

顶层只有三类键：

| 键 | 含意 | 观察 |
| --- | --- | --- |
| `NOD0…NODn` | 网络节点快照 | 键为 `IM0_*`/`EX0_*` 端口变量，数组通常 4 个分量 |
| `MOD0…MODn` | 模块实例快照 | 键集合与模块根 `.cpp` 的全局变量高度一致；不含模块名 |
| `PjtVarValue` | 项目级变量 | 如 `ChangdiTemp`、`HuanJingTemp`、`PumpBar*`、`COP` |

MOD 内部约定：

- 端口变量采用 `IM0_…`（入口）与 `EX0_…`（出口）编号；多端口设备递增到 `IM4`/`EX7`。
- 标量在 JSON 中仍是四分量的数组，例如 `"DN": [150, 150, 150, 0]`；有效值通常在索引 0。
- 组分 `X`、混合 `MIX`、形式 `FORM` 用 `AryDouble0…`/`AryInt0…` 包装；fixture 已按编号展开为列表的列表。
- `MODEL` 是数值数组而非模块名；模块身份只能靠键集合反推。
- `S_T`、`RUN_S` 是运行状态/使能标志，不是物理量。

`.pjt` 与 `.Modu` 均为不可读的编码内容（`.Modu` 以 base64 样式开头）。由于拿不到 `.Modu` 的端口/变量契约，本库的 `module_guess` 只能算启发式推断。

## 匹配方法与置信度

1. 对 `AlgModule/<模块>/<模块>.cpp` 解析 `void runing()` **之前**的全局声明，得到变量名集合。解析器先删除函数体，因此 `SetDllDirectoryABCDEFG()` 内的 `mid_Path`、`nbsum` 等局部变量不会进入签名。
2. 支持 `double a = 0.0;`、`double arr[8] = {0.0};`、`int x = 0;`、逗号多声明；忽略 `bool` 等非模块变量，避免把初始化辅助量算进去。
3. 对每个 MOD，用键集合与 34 个根 `.cpp` 签名计算 Jaccard 主分，并以“签名覆盖率”作次分；同分时按模块名稳定排序取首个，同时在 `notes` 记录全部并列候选。
4. 分数解释：`1.000` 为键集完全一致；`0.90–0.99` 为近似匹配（常见于源码声明了但 PJTDB 未保存的变量）；低于 `0.60` 不应采信。

工程中实际出现的模块为 23 个（ASDFGHJ 9 个、NH3CO2ZL 14 个）；34 个根 `.cpp` 全部参与候选，以免漏配。

## 10 个算例

| case_id | 工程 | 模块猜测 | 分数 | 键数 | 用途 |
| --- | --- | --- | --- | --- | --- |
| `baselu-nh3co2zl-mod0-pipe` | NH3CO2ZL | 管道通用 | 1.000 | 29 | 单相管道水力/热力快照，作管网边界与初值 |
| `baselu-nh3co2zl-mod7-valve` | NH3CO2ZL | 截止阀 | 0.9697 | 32 | 阀门开度/阻力特性，覆盖 32 键阀类契约 |
| `baselu-nh3co2zl-mod8-pump` | NH3CO2ZL | 泵曲线法 | 1.000 | 30 | 泵曲线法快照，作泵流量/扬程边界对照 |
| `baselu-nh3co2zl-mod1-compressor` | NH3CO2ZL | 压缩机 | 1.000 | 35 | 转速/功率快照，作强制流量与轴功初值 |
| `baselu-nh3co2zl-mod53-cold-store` | NH3CO2ZL | 冷库库房 | 1.000 | 136 | 库房热力状态，覆盖最大键集与房间边界 |
| `baselu-nh3co2zl-mod46-tank` | NH3CO2ZL | 罐体卧式 | 1.000 | 91 | 卧式罐液位/压力状态，作储罐初值 |
| `baselu-nh3co2zl-mod210-heat-exchanger` | NH3CO2ZL | 管壳式换热器 | 1.000 | 80 | `H_in`/`H_out`/`H_metal`/`TRANSFER` 快照 |
| `baselu-asdfghj-mod0-battery` | ASDFGHJ | 电池 | 1.000 | 45 | 电池多端口 U/i 状态，作电路边界 |
| `baselu-asdfghj-mod1-resistor` | ASDFGHJ | 电阻 | 1.000 | 25 | 最简电路契约，作 U/i 回归输入 |
| `baselu-asdfghj-mod7-inductor` | ASDFGHJ | 电感 | 1.000 | 32 | 电感动态状态，作电路初值 |

10 个算例全部 `match_score >= 0.6`；9 个为精确键集匹配，唯一非精确项是截止阀：源码声明了 `sdd`，PJTDB 未保存该键（32/33 = 0.9697）。

## Fixture 字段说明

| 字段 | 内容 | 使用方式 |
| --- | --- | --- |
| `case_id` | ASCII 稳定标识，含工程、MOD 序号与设备族 | 作为 pytest 参数 id |
| `source_db` | 相对倍思鹿包根的 `AlgProject/..._DB.PJTDB` | 定位只读来源，不写绝对路径 |
| `project` | `NH3CO2ZL` 或 `ASDFGHJ` | 按工程分组统计 |
| `object_key` | `MODn` | 与源数据库中的对象一一对应 |
| `module_guess` | 键集匹配出的模块名 | 仅猜测值，歧义见 `notes` |
| `match_score` | Jaccard 分数（保留 4 位） | `<0.6` 不采信；`1.0` 为精确键集 |
| `variables` | 变量名到原始结构的映射 | 直接读取；数组已展开为列表 |
| `notes` | 匹配、缺键、歧义、零值等逐例说明 | 人工复核时先读这里 |
| `provenance` | 固定为 `PJTDB snapshot; 未运行倍思鹿` | 证明数据边界 |
| `expected_snapshot` | 计算量/输入量分类、收敛声明 | 只能作提示，不是期望值 |
| `usage` | 边界、初值、回归三种用法与禁用项 | 接入测试时照此约束 |

`expected_snapshot.computed_keys` 只是按变量名做的启发式分类：`RLS`、`CV`、`DENSITY`、`RE`、`FLOW_VOLUME`、`FLOW_SPD`、`DHIGH`、`MID_PRE`、`PL` 以及换热器的 `H_*`/`TRANSFER` 等通常由模块回写；罐体的 `BKT_*` 除 `LH/LL/LW` 几何输入外多为状态量；电路模块的 `_U`/`_i`/`_Phase`/`_WI` 是端口状态。分类错误不会自动变成物理事实，接入前应逐项核对。

## 如何补充真正的期望值

v0 的 `expected_snapshot` 只是“快照标注”，不是实测期望值。若要把某个算例升级为 L3/L4 证据，应按以下顺序补：

1. 在倍思鹿中加载原工程，记录拓扑、模块型号、工质、边界与初值；不要修改源工程，另存副本。
2. 运行到稳定，导出 MOD 变量（界面导出或数据接口），同时记录迭代次数、残差/收敛判据、运行时间和保存时刻。
3. 把导出值写入 fixture 的 `expected_snapshot.measured_values`（新增字段），并把 `convergence_verified` 改为 `true`；保留原 `variables` 作为输入快照。
4. 在 `provenance` 中追加运行批次与导出文件哈希，避免把不同批次的数值混用。
5. 若只导出部分变量，明确缺项；不要用零值补齐，也不要把未导出误写成“已收敛”。

## 如何接入 pytest（L4 参考级，不默认进 CI）

参考算例属于外部依赖证据，建议单独标记、默认不收集：

```python
# 未来新增 tests/test_baselu_reference_cases.py 时使用
import json
from pathlib import Path
import pytest

CASES = sorted((Path(__file__).parent / "fixtures" / "baselu").glob("*.json"))

@pytest.mark.l4_reference
@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_baselu_fixture_contract(path):
    case = json.loads(path.read_text(encoding="utf-8"))
    assert case["provenance"] == "PJTDB snapshot; 未运行倍思鹿"
    assert case["match_score"] >= 0.6
    assert case["variables"]
    assert case["expected_snapshot"]["convergence_verified"] is False
```

接入注意：

- 需在 `pyproject.toml` 注册 `l4_reference` marker，并用 `pytest -m "not l4_reference"` 作为默认 CI 命令；本 v0 不改配置。
- 只做结构/契约断言，不做数值容差断言；真正的数值对照应在补充 `measured_values` 后另立任务。
- 脚本会稳定重写 10 个 JSON；如 CI 要检查漂移，可对比文件哈希，而不是要求源工程始终存在。

## 风险与已知限制

- **快照可能非收敛态**：`S_T[0]=0` 的电池/电感算例、以及电阻/电感的 `U/i` 全零，都不能当成运行结果。
- **`.Modu` 不可读**：端口顺序、单位、变量别名无法从加密模块确认；`module_guess` 只基于键名，存在同名签名歧义（如 `蒸发器` 与 `蒸发式冷凝器`、`二极管` 与 `二极管反`、`关断器` 与 `电位器`）。
- **单位需换算**：PJTDB 的压力约在 0.1–1.7、`DN` 为 150/80 等，疑似 MPa 与 mm；温度、焓、功率的单位没有可读契约，接入 FluidNet 前必须按 `DATA_CONTRACT` 显式换算并复核。
- **变量契约不全**：截止阀的 `sdd` 未落库；其他模块也可能有“声明了但未保存”的键。fixture 的 `notes` 已逐例标注缺项。
- **样本选择偏置**：v0 优先覆盖设备族而不是工况多样性，10 个算例不能代表两个工程的全部拓扑。

## 复现

```powershell
python scripts/extract_baselu_cases.py
# 可选：显式指定源包与输出目录
python scripts/extract_baselu_cases.py --source ..\..\倍思鹿数值仿真-V5.3 --out tests\fixtures\baselu
```

脚本默认从仓库根向上两级定位 `倍思鹿数值仿真-V5.3`，不写死绝对路径；只读 `.PJTDB` 与 `.cpp`，输出 UTF-8、缩进 2、按变量名排序，可重复运行且字节级稳定。验收结果：10 个 JSON 均可被 `json.load` 解析，10/10 分数 ≥0.6，7 个来自 NH3CO2ZL、3 个来自 ASDFGHJ。
