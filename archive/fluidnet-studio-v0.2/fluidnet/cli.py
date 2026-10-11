import argparse
import json
import multiprocessing
import os
import sys
import threading
import webbrowser
from pathlib import Path

from .compiler import validate_project
from .errors import ModelError
from .examples import example_projects
from .models import Project
from .simulation import SimulationSession
from .solver import solve_steady
from .storage import Recorder, atomic_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="FluidNet Studio · 流体网络计算")
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="启动本地网页与 API")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--workspace", default="workspace")
    serve.add_argument("--open", action="store_true")
    for name in ("validate", "solve", "simulate"):
        command = sub.add_parser(name)
        command.add_argument("project")
        command.add_argument("--output")
        if name == "simulate":
            command.add_argument("--duration", type=float, default=60)
            command.add_argument("--dt", type=float, default=0.1)
    example = sub.add_parser("examples")
    example.add_argument("--output", default="examples")
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["serve", "--open"])
    if args.command == "serve":
        import uvicorn
        from .api import create_app
        static_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "web" / "dist"
        if args.open:
            threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}")).start()
        uvicorn.run(create_app(args.workspace, static_root), host="127.0.0.1", port=args.port,
                    log_level="info", ws="websockets")
        return
    if args.command == "examples":
        root = Path(args.output)
        root.mkdir(parents=True, exist_ok=True)
        for p in example_projects():
            atomic_json(root / f"{p.id}.json", p.model_dump())
        print(f"已生成 6 个示例：{root.resolve()}")
        return
    project = Project.model_validate_json(Path(args.project).read_text(encoding="utf-8"))
    try:
        if args.command == "validate":
            result = validate_project(project)
        elif args.command == "solve":
            result = solve_steady(project)
        else:
            if args.duration <= 0:
                parser.error("duration 必须大于零")
            session = SimulationSession(project, args.dt)
            folder = Path(args.output or "simulation-output")
            folder.mkdir(parents=True, exist_ok=True)
            recorder = Recorder(folder, project.selected_variables)
            recorder.append(session.frame)
            while session.time_s < args.duration - 1e-10:
                recorder.append(session.advance(min(args.dt, args.duration - session.time_s)))
                if session.status == "event":
                    break
            recorder.flush()
            atomic_json(folder / "result.json", session.frame)
            atomic_json(folder / "project.json", project.model_dump())
            print(f"结果已保存：{folder.resolve()}")
            return
        content = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
        if args.output:
            Path(args.output).write_text(content, encoding="utf-8")
        else:
            print(content)
        if not result.get("valid", True):
            raise SystemExit(2)
    except ModelError as exc:
        print(json.dumps(exc.diagnostic.to_dict(), ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
