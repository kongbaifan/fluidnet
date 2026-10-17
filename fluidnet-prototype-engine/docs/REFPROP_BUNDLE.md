# 内置 REFPROP 9.1 捆绑说明

本项目可以携带一份 REFPROP 9.1 运行时（`REFPRP64.DLL` + `fluids/` + `mixtures/`）放在
`vendor/` 下，服务按固定顺序自动发现它。用户因此不必单独安装 REFPROP，只要把捆绑副本放在约定位置，
项目设置 → 介质配置的“物性字符串”就能直接使用 `REFPROP::` 前缀（如 `REFPROP::R134A`、
`REFPROP::R407C.MIX`、`REFPROP::R32[0.5]&R125[0.5]`）。

没有捆绑副本、环境变量和默认安装时，CoolProp 自带的 `HEOS::`、`IF97::`、`INCOMP::` 后端仍然可用；
`REFPROP::` 请求会返回明确的物性错误，而不是让服务退出。

## 许可与合规

- **NIST REFPROP 是按用户许可的商业软件**，版权和许可归 NIST 所有。只有**持有合法 NIST 许可**时才能
  使用本机安装的 DLL 与工质文件，也才能在自己的发布包中随附这份副本。
- **本仓库不提交 REFPROP 的 DLL 和工质文件**：`vendor/` 目录已被项目 `.gitignore` 忽略（仓库根目录的
  `NISTRefprop9.1/` 同样忽略）。克隆仓库的执行环境需要自行从合法安装复制，或用下面的脚本生成捆绑。
- **随包分发前必须确认接收方许可**：把捆绑副本打进源码候选包、安装包、镜像或交付目录时，接收方必须
  各自持有合法的 NIST REFPROP 许可证。不要把捆绑文件上传到公开仓库、公开下载站或共享网盘。
- 仓库只保存脚本、说明和清单格式；清单里记录 `license` 字段用于提示许可归属，它不是许可证明。

## 目录布局

默认捆绑目录是项目根下的 `vendor/refprop9.1/`（项目根即 `fluidnet-prototype-engine/`）：

```text
vendor/refprop9.1/
├─ REFPRP64.DLL            # 64 位 REFPROP 动态库（运行时必需）
├─ fluids/                 # 纯质工质文件（运行时必需）
├─ mixtures/               # 混合物文件，支持 .MIX 与自定义配比（运行时必需）
├─ refprop-manifest.json   # 捆绑清单：版本、来源、逐文件 SHA-256（必需）
├─ defaults.prf            # 可选：REFPROP 默认设置文件
└─ FLUIDSET.LST            # 可选：工质集合列表
```

最小运行时文件集是 `REFPRP64.DLL` + `fluids/` + `mixtures/`，本机实测 REFPROP 9.1 加上可选的
`defaults.prf`、`FLUIDSET.LST` 共 209 个文件、5,102,937 字节（约 4.9 MiB / 5.1 MB），CoolProp 7.x
可以加载。`defaults.prf`、`FLUIDSET.LST` 等 REFPROP 安装目录里的其他文件不是运行时必需，可按需一并复制。

### 捆绑清单 `refprop-manifest.json`

清单放在捆绑目录根，由生成脚本自动写出，**不要手工编辑**：

```json
{
  "format": "fluidnet-refprop-bundle",
  "version": "9.1",
  "library": "REFPRP64.DLL",
  "created_at": "2026-10-17T00:00:00+00:00",
  "source": "C:\\Program Files (x86)\\REFPROP",
  "license": "NIST REFPROP 按用户许可；仅在持有合法许可时使用或随包分发",
  "files": {
    "REFPRP64.DLL": {"sha256": "<hex>", "size": 2531328},
    "fluids/WATER.FLD": {"sha256": "<hex>", "size": 12345}
  }
}
```

| 字段 | 含义 |
| --- | --- |
| `format` | 固定为 `fluidnet-refprop-bundle` |
| `version` | 捆绑的 REFPROP 版本，如 `9.1`；健康检查的 `version` 取自这里 |
| `library` | 运行时加载的动态库文件名，固定 `REFPRP64.DLL` |
| `created_at` | 生成时间，ISO 8601 |
| `source` | 复制来源目录（仅供排查，不参与运行时发现） |
| `license` | 许可提示文本，不构成许可授权 |
| `files` | 相对路径 → `sha256` 与字节数，用于完整性校验 |

`source`/`version` 只描述这份副本；运行时是否可用仍以“目录里有 `REFPRP64.DLL`，且有 `fluids` 或
`FLUIDS` 目录”为准。清单缺失或损坏时 `installed` 仍可为 true，只是 `version` 为 `null`。

## 运行时搜索顺序

服务每次判断 REFPROP 可用位置时严格按以下顺序，命中即停止：

1. **环境变量 `FLUIDNET_REFPROP_PATH`**（显式覆盖，优先级最高）。设置后它就是唯一候选：目录不满足
   “含 `REFPRP64.DLL` 且含 `fluids`/`FLUIDS` 目录”时**按未安装处理，不会回退**到捆绑或系统目录，
   避免用户以为在用自己的安装、实际却静默加载了另一套 DLL 与工质文件。未设置该变量时才进入下一步。
2. **捆绑候选**。依次以这四个目录为基准：
   - 项目根（`fluidnet-prototype-engine/` 所在目录）
   - 项目根的父目录（仓库根）
   - 当前工作目录
   - `sys.executable` 所在目录

   每个基准依次尝试 `<base>/vendor/refprop9.1`、`<base>/refprop9.1`、`<base>/refprop`、
   `<base>/NISTRefprop9.1`，重复路径去重并保持顺序；第一个同时含 `REFPRP64.DLL` 和
   `fluids`/`FLUIDS` 目录的目录胜出。
3. **Windows 默认安装目录** `C:\Program Files (x86)\REFPROP`（64 位系统上的典型位置）。

判定条件与后端 `refprop_root()` 一致：有 `REFPRP64.DLL`，且有 `fluids` 或 `FLUIDS` 目录。
注意目录一经进程加载就不能切换；改了环境变量或放置位置后要重启服务。

## 生成与校验

用仓库脚本从本机合法安装的 REFPROP 9.1 复制最小运行时文件集，计算清单并做加载自检。
脚本默认源目录取 `FLUIDNET_REFPROP_PATH` 或 Windows 默认安装目录，默认目标是 `vendor/refprop9.1/`：

```powershell
# 生成默认捆绑目录 vendor/refprop9.1/（只复制 DLL、fluids/、mixtures/ 及可选的 defaults.prf、FLUIDSET.LST）
python scripts/bundle_refprop.py

# 指定来源与目标目录（目标仍按同一清单格式）
python scripts/bundle_refprop.py --source D:\REFPROP91 --target D:\fluidnet-refprop\9.1

# 只校验已有捆绑：清单、逐文件 SHA-256/大小、最小文件集、CoolProp 真实加载
python scripts/bundle_refprop.py --check

# 机器可读摘要（给脚本/CI 用）
python scripts/bundle_refprop.py --check --json

# 目标目录已存在时覆盖重建（会先删除目标目录）
python scripts/bundle_refprop.py --force

# 跳过 CoolProp 真实加载探测（只做结构与哈希校验；供无 REFPROP 的机器做结构测试）
python scripts/bundle_refprop.py --skip-verify
```

脚本退出码 0 表示成功或校验通过，1 表示来源不完整、目标内容冲突或校验失败。`--check` 要求清单
`version` 为 `9.1`，并会用子进程真实加载 `REFPRP64.DLL`、读 `REFPROP_version` 并对
`REFPROP::WATER` 做一次 PT flash；探测到的版本不是 9.1、缺文件或哈希不符都会失败。生成后目录应包含
`REFPRP64.DLL`、`fluids/`、`mixtures/`、`refprop-manifest.json`；`--check` 失败时不要继续分发。

脚本默认在项目根执行。若源 REFPROP 既不在 `FLUIDNET_REFPROP_PATH` 也不在默认目录，可直接用
`--source` 指定，或先 `$env:FLUIDNET_REFPROP_PATH = 'D:\REFPROP91'` 再运行。

## 与源码候选包集成

`scripts/build_trial_candidate.py` 负责生成带样例验收结果的源码候选包。要连内置 REFPROP 一起打包时，
指定已校验的捆绑目录：

```powershell
python scripts/build_trial_candidate.py --acceptance <验收目录> --output <候选包.zip> --refprop vendor/refprop9.1
```

只有通过 `--check` 的捆绑才应放进候选包；脚本要求目录里有合法的 `refprop-manifest.json`，会把整个目录
放到候选包的 `vendor/refprop9.1/`（运行时按此路径发现），并在 `candidate.json` 记录版本、文件数、总字节
和清单哈希。**分发前确认接收方持有合法 NIST 许可**（见“许可与合规”）。

## 版本一致性

`REFPRP64.DLL` 与 `fluids/`、`mixtures/` 必须是同一版本（本仓库按 9.1 验证）。REFPROP 9.1 的 DLL
读取其他版本的工质文件时，Fortran 层会直接 `abort` 整个进程（常见 `forrtl: severe (…)` 崩溃或
静默退出），表现为模型运行进程崩溃而 API 进程仍在。因此：

- 只从同一套 REFPROP 9.1 安装复制 DLL 与工质文件，不要混用 10.x/9.0 的 `fluids/`。
- 用 `python scripts/bundle_refprop.py --check` 复核清单与加载。
- 服务首次使用 REFPROP 工质时会先在子进程里探测一次，用子进程隔离版本不匹配导致的崩溃；
  但这只是兜底，不能代替同版本要求。

## 故障排查

| 现象 | 常见原因与处理 |
| --- | --- |
| 运行/试算进程出现 `forrtl: severe (…)` 崩溃、直接退出或生成 forrtl 日志 | DLL 与工质文件版本不一致，或混入了其他版本的 `fluids/`。用同版本 9.1 重新生成捆绑并 `--check` |
| 报“未找到 REFPROP”或 `PROPERTY_BACKEND_UNSUPPORTED` | 目录不含 `REFPRP64.DLL` 或 `fluids`/`FLUIDS`；对照“运行时搜索顺序”检查实际落点，或设置 `FLUIDNET_REFPROP_PATH`。若该变量已设置但目录无效，会直接按未安装处理（不回退），先修正或清空它 |
| 提示找不到工质（如 `REFPROP::R134A` 失败） | 缺 `fluids/`/`mixtures/` 文件或工质名称不对；确认目录完整、名称与 REFPROP 安装一致（混合物还需 `mixtures/`） |
| 32/64 位不匹配、加载 DLL 失败 | 必须使用 64 位 `REFPRP64.DLL` 与 64 位 Python/CoolProp；32 位的 `refprop.dll`、`REFPROP.EXE` 不是运行时组件 |
| 权限错误、DLL 被阻止 | 捆绑目录需对运行服务的账号可读；从网络/压缩包解出的文件可能带“来自 Internet”标记，可 `Unblock-File` 后重试；避免放在受保护目录 |
| 路径含空格或中文时失败 | 服务用绝对路径配置 REFPROP，空格/中文通常可用；若遇异常，把捆绑移到纯 ASCII 路径（如 `D:\refprop91`）并设 `FLUIDNET_REFPROP_PATH` |
| 改了 REFPROP 位置或环境变量后不生效 | 进程内 REFPROP 目录只加载一次且不能切换；重启服务后重新查询健康检查 |
| 健康检查 `version` 为 null 但 `installed` 为 true | 捆绑目录缺 `refprop-manifest.json` 或清单损坏；重新生成清单，功能本身不受影响 |

## 确认当前生效来源

`GET /api/v1/health` 的 `capabilities.refprop` 返回：

```json
{"installed": true, "source": "bundled", "path": "E:\\liuwangjisuan\\fluidnet-prototype-engine\\vendor\\refprop9.1", "version": "9.1"}
```

- `source`：`env`（环境变量）、`bundled`（捆绑候选）、`system`（Windows 默认安装），未检测到为 `null`。
  设置了 `FLUIDNET_REFPROP_PATH` 但目录无效时返回 `installed: false`，不会回退到捆绑/系统目录。
- `path`：实际生效目录（绝对路径）；未检测到为 `null`。
- `version`：优先读该目录 `refprop-manifest.json` 的 `version`；无清单或损坏为 `null`。

本机查看：

```powershell
(Invoke-RestMethod http://127.0.0.1:8798/api/v1/health).capabilities.refprop
```

前端「设置 → 介质配置」在同一位置显示检测结果与来源；`installed` 为 true 时才提示可使用 `REFPROP::` 前缀。

相关文档：[README 的 REFPROP 能力说明](../README.md)、[HTTP API](API.md)。
