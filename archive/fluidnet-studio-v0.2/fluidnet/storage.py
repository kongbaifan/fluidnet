from __future__ import annotations

import csv
import html
import io
import json
import math
import sqlite3
import threading
import time
from pathlib import Path

import numpy as np

from .catalog import VARIABLES
from .errors import ModelError
from .models import Project, new_id
from .simulation import read_variable


def atomic_json(path: Path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


class ConflictError(ValueError):
    pass


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "studio.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        schema = self.db.execute("PRAGMA user_version").fetchone()[0]
        has_tables = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='templates'").fetchone()
        if has_tables and schema < 2:
            backups = self.root / "backups"
            backups.mkdir(exist_ok=True)
            with sqlite3.connect(backups / f"studio-before-v2-{time.time_ns()}.sqlite3") as backup:
                self.db.backup(backup)
        with self.db:
            self.db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT, revision INTEGER, body TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS versions(project_id TEXT, revision INTEGER, body TEXT, created REAL, PRIMARY KEY(project_id,revision));
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project_id TEXT, name TEXT, mode TEXT, status TEXT, started REAL, updated REAL, request TEXT, frame TEXT);
                CREATE TABLE IF NOT EXISTS templates(id TEXT PRIMARY KEY, name TEXT, kind TEXT, body TEXT, updated REAL);
            """)
            if schema < 2:
                self.db.execute("BEGIN IMMEDIATE")
                columns = {r["name"] for r in self.db.execute("PRAGMA table_info(templates)")}
                for name, declaration in (("revision", "INTEGER NOT NULL DEFAULT 1"),
                                          ("interface", "TEXT"), ("test_conditions", "TEXT NOT NULL DEFAULT '{}'"),
                                          ("archived", "INTEGER NOT NULL DEFAULT 0")):
                    if name not in columns:
                        self.db.execute(f"ALTER TABLE templates ADD COLUMN {name} {declaration}")
                self.db.execute("CREATE TABLE IF NOT EXISTS template_versions(template_id TEXT, revision INTEGER, document TEXT, created REAL, PRIMARY KEY(template_id,revision))")
                for row in self.db.execute("SELECT * FROM templates").fetchall():
                    item = self._decode_template(row)
                    self.db.execute("INSERT OR IGNORE INTO template_versions VALUES(?,?,?,?)",
                                    (item["id"], item["revision"], json.dumps(item, ensure_ascii=False), item["updated"]))
                self.db.execute("PRAGMA user_version=2")
            self.db.execute("UPDATE runs SET status='interrupted' WHERE status IN ('running','paused','queued')")

    def close(self):
        with self.lock:
            self.db.close()

    def list_projects(self):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT id,name,revision,updated FROM projects ORDER BY updated DESC")]

    def get_project(self, project_id, revision=None):
        with self.lock:
            if revision is None:
                row = self.db.execute("SELECT body FROM projects WHERE id=?", (project_id,)).fetchone()
            else:
                row = self.db.execute("SELECT body FROM versions WHERE project_id=? AND revision=?", (project_id, revision)).fetchone()
        if row is None:
            raise KeyError(project_id)
        return Project.model_validate_json(row["body"])

    def save_project(self, project: Project, check_revision=True):
        result = project.model_copy(deep=True)
        with self.lock, self.db:
            previous = self.db.execute("SELECT revision FROM projects WHERE id=?", (project.id,)).fetchone()
            revision = previous["revision"] if previous else 0
            if check_revision and previous and project.revision != revision:
                raise ConflictError("项目已被其他窗口保存，请重新载入或另存为，避免覆盖新版本")
            result.revision = revision + 1
            body = result.model_dump_json()
            now = time.time()
            self.db.execute("INSERT OR REPLACE INTO projects VALUES(?,?,?,?,?)", (result.id, result.name, result.revision, body, now))
            self.db.execute("INSERT INTO versions VALUES(?,?,?,?)", (result.id, result.revision, body, now))
        return result

    def list_versions(self, project_id):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT revision,created FROM versions WHERE project_id=? ORDER BY revision DESC", (project_id,))]

    def create_run(self, request):
        rid = new_id()
        folder = self.root / "runs" / rid
        folder.mkdir()
        atomic_json(folder / "request.json", request.model_dump())
        atomic_json(folder / "project.json", request.project.model_dump())
        with self.lock, self.db:
            now = time.time()
            self.db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)", (rid, request.project.id,
                request.project.name, request.mode, "queued", now, now, request.model_dump_json(), None))
        return rid, folder

    def update_run(self, run_id, status, frame=None):
        with self.lock, self.db:
            if frame is None:
                self.db.execute("UPDATE runs SET status=?,updated=? WHERE id=?", (status, time.time(), run_id))
            else:
                self.db.execute("UPDATE runs SET status=?,updated=?,frame=? WHERE id=?", (status, time.time(), json.dumps(frame, ensure_ascii=False, allow_nan=False), run_id))

    def list_runs(self, project_id=None):
        with self.lock:
            query = "SELECT id,project_id,name,mode,status,started,updated FROM runs"
            rows = self.db.execute(query + (" WHERE project_id=?" if project_id else "") + " ORDER BY started DESC LIMIT 200", (project_id,) if project_id else ())
            return [dict(r) for r in rows]

    def get_run(self, run_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        item = dict(row)
        item["request"] = json.loads(item["request"])
        item["frame"] = json.loads(item["frame"]) if item["frame"] else None
        return item

    def run_dir(self, run_id):
        self.get_run(run_id)
        return self.root / "runs" / run_id

    @staticmethod
    def _decode_template(row):
        item = dict(row)
        for key in ("body", "interface", "test_conditions"):
            item[key] = json.loads(item[key]) if item.get(key) else (None if key == "interface" else {})
        item["archived"] = bool(item.get("archived"))
        # Old snapshots remain stored verbatim; the response is upgraded in memory.
        from .modules import normalize_template
        try:
            item.update(normalize_template(item))
        except (ValueError, ModelError) as exc:
            item["validation_error"] = str(exc)
            item["interface"] = item.get("interface") or {"exposed_ports": {}, "exposed_parameters": {}, "port_labels": {}, "parameter_labels": {}}
        return item

    def templates(self, include_archived=False):
        with self.lock:
            return [self._decode_template(r) for r in self.db.execute(
                "SELECT * FROM templates" + ("" if include_archived else " WHERE archived=0") + " ORDER BY updated DESC")]

    def get_template(self, template_id, revision=None):
        with self.lock:
            row = self.db.execute("SELECT * FROM templates WHERE id=?", (template_id,)).fetchone()
            if row is None:
                raise KeyError(template_id)
            if revision is None:
                return self._decode_template(row)
            version = self.db.execute("SELECT document FROM template_versions WHERE template_id=? AND revision=?",
                                      (template_id, revision)).fetchone()
            if version is None:
                raise KeyError(template_id)
            item = json.loads(version["document"])
            item["archived"] = bool(row["archived"])
            return item

    def template_versions(self, template_id):
        self.get_template(template_id)
        with self.lock:
            return [dict(r) for r in self.db.execute(
                "SELECT revision,created FROM template_versions WHERE template_id=? ORDER BY revision DESC", (template_id,))]

    def save_template(self, name, kind, body, interface=None, test_conditions=None, revision=0, template_id=None):
        from .modules import normalize_template
        normalized = normalize_template({"name": name, "kind": kind, "body": body, "interface": interface,
                                         "test_conditions": test_conditions or {}, "revision": revision})
        with self.lock, self.db:
            previous = self.db.execute("SELECT revision,kind FROM templates WHERE id=?", (template_id,)).fetchone() if template_id else None
            if previous and previous["revision"] != revision:
                raise ConflictError("型号已被其他窗口修改，请重新载入最新版本")
            if previous and previous["kind"] != kind:
                raise ValueError("型号类型不能改变，请另存为新型号")
            item = {**normalized, "id": template_id or new_id(), "revision": (previous["revision"] if previous else 0) + 1,
                    "updated": time.time(), "archived": False}
            self.db.execute("INSERT OR REPLACE INTO templates(id,name,kind,body,updated,revision,interface,test_conditions,archived) VALUES(?,?,?,?,?,?,?,?,0)",
                            (item["id"], name, kind, json.dumps(item["body"], ensure_ascii=False), item["updated"], item["revision"],
                             json.dumps(item["interface"], ensure_ascii=False), json.dumps(item["test_conditions"], ensure_ascii=False)))
            self.db.execute("INSERT INTO template_versions VALUES(?,?,?,?)", (item["id"], item["revision"],
                             json.dumps(item, ensure_ascii=False), item["updated"]))
        return item

    def archive_template(self, template_id, revision):
        with self.lock, self.db:
            current = self.get_template(template_id)
            if current["revision"] != revision:
                raise ConflictError("型号版本已变化，请重新载入后归档")
            self.db.execute("UPDATE templates SET archived=1 WHERE id=?", (template_id,))
        return {**current, "archived": True}


class Recorder:
    def __init__(self, folder: Path, selected_variables):
        self.folder = folder
        self.variables = list(selected_variables)[:64]
        self.rows = []
        self.chunk = 0
        self.last_flush = time.monotonic()
        self.total_rows = 0
        atomic_json(folder / "channels.json", {"variables": self.variables, "time_unit": "s", "units": "SI"})

    def append(self, frame):
        self.rows.append([frame["time_s"]] + [read_variable(frame, path) for path in self.variables])
        self.total_rows += 1
        if len(self.rows) >= 1000 or time.monotonic() - self.last_flush >= 2:
            self.flush()

    def flush(self):
        if not self.rows:
            return
        target = self.folder / f"curve-{self.chunk:06d}.npz"
        temporary = target.with_suffix(".tmp")
        with temporary.open("wb") as f:
            np.savez_compressed(f, values=np.array(self.rows, dtype=float))
        temporary.replace(target)
        self.rows.clear()
        self.chunk += 1
        self.last_flush = time.monotonic()


def read_history(folder: Path, limit=20000):
    channels_path = folder / "channels.json"
    if not channels_path.exists():
        return {"variables": [], "rows": [], "total_rows": 0}
    channels = json.loads(channels_path.read_text(encoding="utf-8"))["variables"]
    # Two passes keep memory bounded even for long recordings.
    counts = []
    for path in sorted(folder.glob("curve-*.npz")):
        with np.load(path, allow_pickle=False) as data:
            counts.append((path, len(data["values"])))
    total = sum(count for _, count in counts)
    indices = set(np.linspace(0, max(0, total - 1), min(total, limit), dtype=int).tolist())
    rows, offset = [], 0
    for path, count in counts:
        local = [i - offset for i in indices if offset <= i < offset + count]
        if local:
            with np.load(path, allow_pickle=False) as data:
                for row in data["values"][sorted(local)]:
                    rows.append([float(v) if math.isfinite(v) else None for v in row])
        offset += count
    return {"variables": channels, "rows": rows, "total_rows": total}


def csv_chunks(folder: Path):
    variables = json.loads((folder / "channels.json").read_text(encoding="utf-8"))["variables"]
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(["time_s", *variables])
    yield "\ufeff" + stream.getvalue()
    for path in sorted(folder.glob("curve-*.npz")):
        stream = io.StringIO()
        writer = csv.writer(stream)
        with np.load(path, allow_pickle=False) as data:
            for row in data["values"]:
                writer.writerow([float(x) if math.isfinite(x) else "" for x in row])
        yield stream.getvalue()


def html_report(run):
    project = run["request"]["project"]
    frame = run.get("frame") or {}
    escape = lambda x: html.escape(str(x))
    body = []
    for element in project["elements"]:
        body.append(f"<h3>{escape(element['name'] or element['id'])}</h3><p>{escape(element['type'])} · {escape(element['id'])}</p>")
        body.append("<table><tr><th>变量</th><th>数值（SI）</th><th>单位</th></tr>")
        for name, value in frame.get("elements", {}).get(element["id"], {}).items():
            info = VARIABLES.get(name.rsplit(".", 1)[-1], (name, ""))
            body.append(f"<tr><td>{escape(name)} · {escape(info[0])}</td><td>{value:.9g}</td><td>{escape(info[1])}</td></tr>")
        body.append("</table><details><summary>输入参数</summary><pre>" + escape(json.dumps(element["parameters"], ensure_ascii=False, indent=2)) + "</pre></details>")
    diagnostics = "".join(f"<li>{escape(d.get('code'))}：{escape(d.get('message'))}</li>" for d in frame.get("diagnostics", []))
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{escape(project['name'])} · 计算报告</title>
    <style>body{{font:15px/1.7 system-ui;max-width:1000px;margin:40px auto;padding:24px;color:#1b3241}}h1,h2{{color:#126d79}}table{{border-collapse:collapse;width:100%;margin:14px 0}}th,td{{border:1px solid #dce6e9;text-align:left;padding:8px}}pre{{white-space:pre-wrap;background:#f4f7f8;padding:15px}}@media print{{details{{display:block}}h3{{break-after:avoid}}tr{{break-inside:avoid}}}}</style>
    <h1>{escape(project['name'])}</h1><p>FluidNet Studio · 运行 {escape(run['id'])} · 状态 {escape(run['status'])} · 仿真时间 {frame.get('time_s', 0):.6g} s</p>
    <h2>方法与适用范围</h2><p>单相液态水；Darcy–Weisbach / Colebrook；稀疏阻尼 Newton；比焓混合与 ε–NTU 换热；慢动态使用准稳态水力、隐式 Euler 与有限体积热输运。压力为绝压。管道不储压，不模拟水锤、气蚀或相变。</p>
    <h2>介质及后端</h2><pre>{escape(json.dumps(project['media'], ensure_ascii=False, indent=2))}</pre>
    <h2>求解指标</h2><pre>{escape(json.dumps(frame.get('metrics', {}), ensure_ascii=False, indent=2))}</pre>
    <h2>诊断</h2><ul>{diagnostics or '<li>无诊断消息</li>'}</ul><h2>元件结果</h2>{''.join(body)}</html>"""
