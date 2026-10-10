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
    args = parser.parse_args((sys.argv[1:] if argv is None else argv) or ["serve"])
    if args.command == "serve":
        import threading
        import webbrowser
        import uvicorn
        from .api import create_app
        root = Path(__file__).resolve().parents[2]
        if args.open:
            threading.Timer(1.0, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
        uvicorn.run(create_app(root / "frontend"), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
