# 工作区备份与恢复

## 页面操作

1. 先点击“保存原型”，或将未保存草稿导出为 JSON。
2. 顶部“备份与恢复” → “下载完整备份”，得到 `fluidnet-backup.zip`。服务可以继续运行；数据库和模块版本在同一个备份窗口内固定。
3. “恢复备份到新目录”选择 ZIP。全部校验通过后，页面显示新目录和启动命令。关闭当前服务，再执行该命令打开恢复的工作区。
4. 同一弹窗可查看容量与最近 5 个工作区修订。恢复旧修订前保存浏览器草稿备份，恢复成功生成新修订；其他页面已保存更新时返回冲突，运行档案保留。

备份涵盖已保存的原型项目、修订、运行请求与历史、示例及已发布 Python 模块版本。浏览器中尚未保存的编辑内容、访问令牌文件不在 ZIP 内。“导出载入前草稿”可取回本浏览器上次载入前保留的 JSON。

恢复的是记录。备份时尚未结束的运行，在新目录启动后标为 `interrupted`，可以查看已落盘历史；需要创建新运行才能继续计算。

## 命令行

在已安装项目依赖的环境，从项目目录执行。命令行备份要求原服务已停止；在线备份使用页面/API。

```powershell
python -m fn_engine workspace backup --data-dir ".runtime/workspace" --output "artifacts/workspace-backup.zip"
python -m fn_engine workspace restore "artifacts/workspace-backup.zip" --destination "artifacts/restored-workspace"
python -m fn_engine serve --data-dir "artifacts/restored-workspace" --open
```

备份文件和恢复目录都必须使用尚不存在的目标。模块存储单独配置时，备份与启动可传 `--module-dir "模块目录"`。优先级为显式 `--module-dir` → 工作区已有 `module-packages/` → `FLUIDNET_MODULE_STORE` → 项目默认 `.runtime/module-packages/`。恢复的同 ID/版本模块优先于软件附带的示例版本，保留备份时的双哈希。

ZIP 使用格式版本 1；当前 SQLite `user_version=3`。恢复接受数据库版本 1、2、3，旧版本在首次打开时自动迁移到版本 3，保留项目、运行及修订；版本 3 增加的批次快照、结果和曲线也随数据库备份。清单逐文件记录大小和 SHA-256，恢复同时验证数据库完整性、外键、修订号以及 Python 模块的源码/定义哈希。校验过程不执行模块源码。

页面/API 上传限制为 256 MiB；更大的 ZIP 使用 CLI。所有恢复限制解压后不超过 2 GiB、条目数不超过 10000。数据库与模块文件全部校验成功后才发布恢复目录。

## 容量与保留

页面分别显示数据库、可复用页、WAL 和剩余磁盘空间。删除或淘汰记录后，SQLite 可复用页可能增加，文件不一定立即缩小。默认保留 5 个工作区修订、20 次终态运行；每次运行保留最近历史窗口（最多 20001 帧）和约 2000 点全程抽稀曲线。完整 ZIP 仅包含这些已保留内容。

持续运行的启动、状态核对和验收边界见 [验收记录](BACKUP_ACCEPTANCE.md)。
