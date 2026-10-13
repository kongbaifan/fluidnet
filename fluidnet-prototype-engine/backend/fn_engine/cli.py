from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="FluidNet Prototype Engine")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8798)
    serve.add_argument("--open", action="store_true")
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
    args = parser.parse_args((sys.argv[1:] if argv is None else argv) or ["serve"])
    from .auth import TokenStore, resolve_auth
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
        uvicorn.run(create_app(root / "frontend", auth=auth, cors_origins=args.cors_origin), host=args.host, port=args.port,
                    log_level="info")


if __name__ == "__main__":
    main()
