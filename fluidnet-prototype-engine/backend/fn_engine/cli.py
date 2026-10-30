from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="FluidNet Prototype Engine")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8798)
    interface = serve.add_mutually_exclusive_group()
    interface.add_argument("--open", action="store_true", help='启动后打开开发界面')
    interface.add_argument('--headless', action='store_true', help='仅启动 API 与后台计算，不挂载开发界面')
    serve.add_argument('--data-dir', help='工作区目录（默认 FLUIDNET_DATA_DIR 或项目 .runtime/workspace）')
    serve.add_argument('--module-dir', help='模块版本目录；恢复的工作区默认使用其 module-packages 子目录')
    serve.add_argument("--auth", choices=("auto", "required", "off"), default="auto",
                       help="auto：只在监听本机以外地址时要求令牌；反向代理后面请用 required")
    serve.add_argument("--cors-origin", action="append", default=[], help="允许跨域调用的来源，可重复")
    token = sub.add_parser("token", help="管理访问令牌（文件位置：FLUIDNET_TOKEN_FILE 或 .runtime/tokens.json）")
    actions = token.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("name")
    create.add_argument("--scope", choices=("read", "control"), default="read")
    actions.add_parser("list")
    revoke = actions.add_parser("revoke")
    revoke.add_argument("id")
    workspace = sub.add_parser('workspace', help='工作区备份与恢复')
    operations = workspace.add_subparsers(dest='operation', required=True)
    backup = operations.add_parser('backup', help='停服备份；服务运行时请使用页面备份按钮')
    backup.add_argument('--data-dir', required=True)
    backup.add_argument('--module-dir')
    backup.add_argument('--output', required=True)
    restore = operations.add_parser('restore', help='校验并恢复到一个新目录')
    restore.add_argument('backup')
    restore.add_argument('--destination', required=True)
    args = parser.parse_args((sys.argv[1:] if argv is None else argv) or ["serve"])
    from .auth import TokenStore, resolve_auth
    if args.command == 'workspace':
        from .backup import backup_workspace, restore_workspace
        from .storage import WorkspaceStore
        from .packages import ModuleStore
        root = Path(__file__).resolve().parents[2]
        try:
            if args.operation == 'restore':
                result = restore_workspace(args.backup, args.destination)
                print(f'已恢复修订 {result["revision"]} 到 {Path(args.destination).resolve()}')
            else:
                data_root = Path(args.data_dir)
                if not (data_root / 'workspace.sqlite3').is_file():
                    raise ValueError('指定目录没有工作区数据库')
                storage = WorkspaceStore(data_root, recover=False)
                try:
                    module_root = args.module_dir or (data_root / 'module-packages' if (data_root / 'module-packages').exists()
                        else os.environ.get('FLUIDNET_MODULE_STORE') or root / '.runtime' / 'module-packages')
                    result = backup_workspace(storage, ModuleStore(root / 'modules', Path(module_root)), args.output)
                    print(f'已备份修订 {result["revision"]} 到 {Path(args.output).resolve()}')
                finally:
                    storage.close()
        except (ValueError, OSError, RuntimeError) as error:
            parser.exit(1, f'{error}\n')
        return
    if args.command == "token":
        store = TokenStore()
        if args.action == "create":
            record, secret = store.create(args.name, args.scope)
            print(f"已创建令牌 {record['id']}（{record['name']}，{record['scope']}）。只显示这一次，请妥善保存：")
            print(secret)
        elif args.action == "list":
            for record in store.list():
                print(f"{record['id']}  {record['scope']:7s}  {record['created_at']}  {record['name']}")
        elif not store.revoke(args.id):
            parser.exit(1, f"没有 id 为 {args.id} 的令牌\n")
        return
    if args.command == "serve":
        import threading
        import webbrowser
        import uvicorn
        from .api import create_app
        root = Path(__file__).resolve().parents[2]
        try:
            auth = resolve_auth(args.auth, args.host, TokenStore())
        except ValueError as error:
            parser.exit(2, f"{error}\n")
        if args.open:
            threading.Timer(1.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
        data_root = args.data_dir or os.environ.get('FLUIDNET_DATA_DIR') or (
            Path(os.environ['FLUIDNET_MODULE_STORE']) / '.workspace' if os.environ.get('FLUIDNET_MODULE_STORE') else root / '.runtime' / 'workspace')
        frontend = None if args.headless else root / 'frontend'
        uvicorn.run(create_app(frontend, module_storage_root=args.module_dir, auth=auth, cors_origins=args.cors_origin, data_root=data_root), host=args.host, port=args.port,
                    log_level="info")


if __name__ == "__main__":
    main()
