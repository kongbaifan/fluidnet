"""Exercise the shipped Windows executable with no host Python in its environment."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".runtime" / "python"))
sys.path.insert(0, str(ROOT))


def main():
    from fluidnet import __version__
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--archive", type=Path)
    source.add_argument("--executable", type=Path)
    args = parser.parse_args()
    cache = ROOT / ".cache" / "portable-smoke"
    cache.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="验证 ", dir=cache)).resolve()
    report_path = ROOT / ".cache" / "qa" / "portable-smoke.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "workspace": str(work), "checks": []}
    process = None
    log = None
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    child_env = {k: v for k, v in os.environ.items()
                 if k.upper() not in {"PYTHONPATH", "PYTHONHOME"}}
    if os.name == "nt":
        system = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        child_env["PATH"] = os.pathsep.join((str(system / "System32"), str(system)))
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"

    def passed(name):
        report["checks"].append(name)
        print(f"PASS: {name}", flush=True)

    def stop_server():
        nonlocal process, log
        if process is not None and process.poll() is None:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=flags, timeout=15)
            else:
                process.terminate()
            process.wait(timeout=15)
        if log is not None:
            log.close()
        process, log = None, None

    try:
        if args.executable:
            executable = args.executable.resolve()
        else:
            archive = (args.archive or ROOT / "dist" / f"FluidNetStudio-Windows-x64-{__version__}.zip").resolve()
            if not archive.is_file():
                raise RuntimeError("Build the archive first: npm run build -- --portable")
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            checksum = Path(str(archive) + ".sha256")
            if not checksum.is_file() or checksum.read_text(encoding="ascii").split()[0] != digest:
                raise RuntimeError("The archive SHA-256 checksum is missing or does not match")
            report.update(archive=str(archive), sha256=digest)
            with zipfile.ZipFile(archive) as bundle:
                for entry in bundle.infolist():
                    if not (work / entry.filename).resolve().is_relative_to(work):
                        raise RuntimeError("Archive entry escapes the test directory")
                bundle.extractall(work)
            executable = work / "FluidNetStudio" / "FluidNetStudio.exe"
            passed("archive checksum and extraction into a path with Chinese text and spaces")
        if not executable.is_file():
            raise RuntimeError(f"Executable not found: {executable}")
        report["executable"] = str(executable)
        manifest = json.loads((executable.parent / "build-info.json").read_text(encoding="utf-8"))
        report["build"] = manifest

        def cli(*arguments):
            result = subprocess.run([str(executable), *map(str, arguments)], cwd=work,
                                    env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    creationflags=flags, timeout=60)
            if result.returncode:
                raise RuntimeError(f"CLI {arguments[0]} failed ({result.returncode}): {result.stdout}")

        examples = work / "命令行 examples"
        cli("examples", "--output", examples)
        projects = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in examples.glob("*.json")}
        assert len(projects) == 6, projects.keys()
        passed("CLI generates all six example projects")
        validation = work / "validation.json"
        cli("validate", examples / "example_single.json", "--output", validation)
        assert json.loads(validation.read_text(encoding="utf-8"))["valid"]
        result_file = work / "steady.json"
        cli("solve", examples / "example_single.json", "--output", result_file)
        result = json.loads(result_file.read_text(encoding="utf-8"))
        assert result["valid"] and result["elements"]["pipe"]["mass_flow_kg_s"] > 0
        passed("CLI validation and steady solve")
        simulation = work / "动态 results"
        cli("simulate", examples / "example_tanks.json", "--duration", "0.2", "--dt", "0.1",
            "--output", simulation)
        result = json.loads((simulation / "result.json").read_text(encoding="utf-8"))
        assert result["valid"] and abs(result["time_s"] - 0.2) < 1e-9
        passed("CLI dynamic solve and result files")

        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        def request(path, body=None, method=None):
            data = None if body is None else json.dumps(body).encode("utf-8")
            req = urllib.request.Request(base + path, data=data,
                                         headers={"Content-Type": "application/json"}, method=method)
            try:
                with urllib.request.urlopen(req, timeout=5) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                raise RuntimeError(f"{path}: HTTP {error.code}: {error.read().decode('utf-8')}") from error

        def api(path, body=None, method=None):
            return json.loads(request("/api/v1" + path, body, method))

        def start_server():
            nonlocal process, log
            log = (work / "server.log").open("ab")
            process = subprocess.Popen([str(executable), "serve", "--port", str(port),
                                        "--workspace", str(work / "数据 workspace")],
                                       cwd=work, env=child_env, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=flags)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Server exited: {(work / 'server.log').read_text(encoding='utf-8', errors='replace')[-6000:]}")
                try:
                    return api("/health")
                except (OSError, urllib.error.URLError):
                    time.sleep(0.1)
            raise RuntimeError("Server did not become ready within 30 seconds")

        def wait_run(run_id, status, time_s=None):
            deadline = time.monotonic() + 30
            state = None
            while time.monotonic() < deadline:
                state = api(f"/runs/{run_id}")
                if state["status"] == status and (time_s is None or
                        abs(state["frame"]["time_s"] - time_s) < 1e-9):
                    return state
                if state["status"] in {"failed", "interrupted", "event"}:
                    raise RuntimeError(f"Run failed: {json.dumps(state, ensure_ascii=False)}")
                time.sleep(0.1)
            raise RuntimeError(f"Run did not reach {status} at {time_s}: {state}")

        health = start_server()
        assert health["status"] == "ok" and health["version"] == manifest["version"]
        assert Path(health["workspace"]) == work / "数据 workspace"
        report["health"] = health
        page = request("/").decode("utf-8")
        assert "FluidNet" in page
        assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', page)
        assert assets, page
        for asset in assets:
            assert request(asset), asset
        passed("local service health and bundled web assets")

        project = projects["example_parallel"]
        project["id"] = "portable_saved_project"
        project["name"] = "免安装持久化验证"
        saved = api("/projects", project)
        assert saved["revision"] == 1
        run_id = api("/runs", {"project_id": saved["id"]})["run_id"]
        state = wait_run(run_id, "completed")
        assert state["frame"]["valid"] and state["frame"]["elements"]["trunk"]["mass_flow_kg_s"] > 0
        passed("steady calculation in a frozen worker process")
        assert "time_s" in request(f"/api/v1/runs/{run_id}/results?format=csv").decode("utf-8-sig")
        assert "计算报告" in request(f"/api/v1/runs/{run_id}/results?format=html").decode("utf-8")
        assert api(f"/runs/{run_id}/results?format=json")["result"]["valid"]
        passed("CSV, HTML and JSON exports")

        dynamic_id = api("/runs", {"project": projects["example_tanks"], "mode": "dynamic",
                                    "start_paused": True, "duration_s": 2, "dt_s": 0.1})["run_id"]
        wait_run(dynamic_id, "paused", 0)
        from websockets.sync.client import connect
        with connect(f"ws://127.0.0.1:{port}/api/v1/runs/{dynamic_id}/stream", open_timeout=5) as stream:
            message = json.loads(stream.recv(timeout=10))
            assert message["id"] == dynamic_id and message["status"] == "paused"
        passed("WebSocket status stream")
        api(f"/runs/{dynamic_id}/commands", {"action": "step"})
        wait_run(dynamic_id, "paused", 0.1)
        api(f"/runs/{dynamic_id}/commands", {"action": "stop"})
        wait_run(dynamic_id, "stopped", 0.1)
        assert api(f"/runs/{dynamic_id}/history")["total_rows"] == 2
        passed("dynamic initialization, single step, stop and recorded history")

        templates = api("/templates")
        assert len(templates) == 3
        assert len(list((executable.parent / "templates").glob("*.json"))) == 3
        for template in templates:
            payload = {k: v for k, v in template.items() if k not in {"id", "updated", "archived"}}
            bench = api("/modules/bench", payload)
            assert api("/validate", bench)["valid"]
        passed("three packaged group templates and independent test boundaries")
        grouped = api("/modules/group", {"project": projects["example_single"], "element_ids": ["pipe"], "name": "免安装组合"})
        definition = api("/modules/extract", {"project": grouped["project"], "group_id": grouped["group_id"]})
        template = api("/templates", definition)
        definition["revision"] = template["revision"]
        definition["body"]["elements"][0]["parameters"]["length_m"] = 70
        updated = api(f"/templates/{template['id']}", definition, "PUT")
        assert updated["revision"] == 2
        preview = api("/modules/apply", {"project": grouped["project"], "group_id": grouped["group_id"], "template_id": template["id"], "revision": 2})
        assert next(e for e in grouped["project"]["elements"] if e["id"] == "pipe")["parameters"]["length_m"] == 100
        module_run = api("/runs", {"project": preview["project"]})["run_id"]
        assert wait_run(module_run, "completed")["frame"]["valid"]
        api(f"/templates/{template['id']}?revision=2", method="DELETE")
        assert len(api("/templates")) == 3
        assert len(api(f"/templates/{template['id']}/versions")) == 2
        passed("group insertion, version preview, explicit apply, frozen solve and template archival")

        stop_server()
        start_server()
        restored = api(f"/projects/{saved['id']}")
        assert restored["revision"] == 1 and restored["name"] == saved["name"]
        assert api(f"/runs/{run_id}")["status"] == "completed"
        assert api(f"/runs/{dynamic_id}/history")["total_rows"] == 2
        passed("projects and results persist after restarting the executable")
        report["status"] = "passed"
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        try:
            stop_server()
        except Exception as error:
            report.update(status="failed", error=f"Server cleanup failed: {error}")
            raise
        finally:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Smoke report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
