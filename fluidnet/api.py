from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .catalog import catalog_json, get_parameters
from .compiler import validate_project
from .errors import ModelError
from .examples import example_projects, example_templates
from .jobs import JobManager, TERMINAL
from .media import media_catalog
from .models import Element, ModuleInterface, Position, Project, RunCommand, RunRequest, TemplateRequest, StrictModel
from .modules import apply_template, configure_group, extract_group, insert_template, make_bench, normalize_template
from .storage import ConflictError, Store, csv_chunks, html_report, read_history


class ModuleRequest(StrictModel):
    project: Project
    element_ids: list[str] = Field(default_factory=list)
    group_id: str | None = None
    element_id: str | None = None
    name: str = Field(default="组合模块", min_length=1, max_length=120)
    interface: ModuleInterface | None = None
    template_id: str | None = None
    revision: int | None = Field(default=None, ge=1)
    template: dict | None = None
    position: Position = Field(default_factory=lambda: Position(x=200, y=200))
    page: int = Field(default=0, ge=0, le=15)
    scenario_id: str | None = None


def create_app(workspace=None, static_root=None, seed=True):
    root = Path(workspace or os.environ.get("FLUIDNET_WORKSPACE", "workspace")).resolve()
    static = Path(static_root or Path(__file__).resolve().parents[1] / "web" / "dist")
    @asynccontextmanager
    async def lifespan(app):
        store = Store(root)
        if seed:
            existing = {p["id"] for p in store.list_projects()}
            for project in example_projects():
                if project.id not in existing:
                    store.save_project(project)
            existing_templates = {t["id"] for t in store.templates(include_archived=True)}
            for template in example_templates():
                if template["id"] not in existing_templates:
                    store.save_template(**{k: v for k, v in template.items() if k != "id"}, template_id=template["id"])
        app.state.store = store
        app.state.jobs = JobManager(store)
        yield
        app.state.jobs.close()
        store.close()

    app = FastAPI(title="FluidNet Studio", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type"])

    @app.exception_handler(ModelError)
    async def model_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": exc.diagnostic.to_dict()})

    @app.exception_handler(ConflictError)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid_module(request, exc):
        return JSONResponse(status_code=422, content={"detail": {"code": "MODULE_INVALID", "message": str(exc)}})

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(status_code=404, content={"detail": "项目或运行记录不存在"})

    @app.get("/api/v1/health")
    def health():
        versions = {}
        for name in ("numpy", "scipy", "CoolProp", "fastapi"):
            versions[name] = importlib.metadata.version(name)
        return {"status": "ok", "version": __version__, "versions": versions,
                "workspace": str(root), "flow_models": ["quasi_incompressible_liquid"]}

    @app.get("/api/v1/catalog")
    def catalog():
        return {**catalog_json(), "media": media_catalog()}

    @app.get("/api/v1/examples")
    def examples():
        return [p.model_dump() for p in example_projects()]

    @app.get("/api/v1/projects")
    def projects():
        return app.state.store.list_projects()

    @app.get("/api/v1/projects/{project_id}")
    def project(project_id: str, revision: int | None = None):
        return app.state.store.get_project(project_id, revision).model_dump()

    @app.post("/api/v1/projects")
    def save_project(project: Project):
        return app.state.store.save_project(project).model_dump()

    @app.post("/api/v1/projects/upgrade")
    def upgrade_project(project: Project):
        return project.model_dump()

    @app.put("/api/v1/projects/{project_id}")
    def update_project(project_id: str, project: Project):
        if project.id != project_id:
            raise HTTPException(400, "路径与项目 ID 不一致")
        return app.state.store.save_project(project).model_dump()

    @app.get("/api/v1/projects/{project_id}/versions")
    def versions(project_id: str):
        return app.state.store.list_versions(project_id)

    @app.post("/api/v1/validate")
    def validate(project: Project):
        return validate_project(project)

    @app.post("/api/v1/projects/{project_id}/validate")
    def validate_saved(project_id: str):
        return validate_project(app.state.store.get_project(project_id))

    @app.post("/api/v1/runs", status_code=202)
    def run(request: RunRequest):
        if request.project is None:
            if request.project_id is None:
                raise HTTPException(400, "请提供项目或项目 ID")
            request.project = app.state.store.get_project(request.project_id)
        try:
            request.project = request.project.with_scenario(request.scenario_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        check = validate_project(request.project)
        if not check["valid"]:
            raise HTTPException(422, check["diagnostics"][0])
        return {"run_id": app.state.jobs.submit(request)}

    @app.post("/api/v1/projects/{project_id}/compare", status_code=202)
    def compare(project_id: str, scenario_ids: list[str]):
        project = app.state.store.get_project(project_id)
        if not scenario_ids or len(scenario_ids) > 20:
            raise HTTPException(422, "每批需要 1 到 20 个工况")
        prepared = []
        for sid in scenario_ids:
            try:
                selected = project.with_scenario(sid)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            scenario = next(s for s in project.scenarios if s.id == sid)
            selected.name += " / " + scenario.name
            check = validate_project(selected)
            if not check["valid"]:
                raise HTTPException(422, check["diagnostics"][0])
            prepared.append(RunRequest(project=selected, mode="steady"))
        return {"run_ids": [app.state.jobs.submit(r) for r in prepared]}

    @app.get("/api/v1/runs")
    def runs(project_id: str | None = None):
        return app.state.store.list_runs(project_id)

    @app.get("/api/v1/runs/{run_id}")
    def run_status(run_id: str):
        stored = app.state.store.get_run(run_id)
        live = app.state.jobs.state(run_id)
        return {**stored, **live}

    @app.post("/api/v1/runs/{run_id}/commands", status_code=202)
    def command(run_id: str, command: RunCommand):
        return app.state.jobs.command(run_id, command)

    @app.get("/api/v1/runs/{run_id}/history")
    def history(run_id: str, limit: int = Query(default=20000, ge=2, le=100000)):
        return read_history(app.state.store.run_dir(run_id), limit)

    @app.get("/api/v1/runs/{run_id}/results")
    def results(run_id: str, format: str = "json"):
        stored = app.state.store.get_run(run_id)
        live = app.state.jobs.state(run_id)
        stored["frame"] = live["frame"]
        stored["status"] = live["status"]
        if format == "html":
            return HTMLResponse(html_report(stored), headers={"Content-Disposition": f'attachment; filename="fluidnet-{run_id}.html"'})
        if format == "csv":
            folder = app.state.store.run_dir(run_id)
            if not (folder / "channels.json").exists():
                raise HTTPException(409, "尚无记录数据")
            return StreamingResponse(csv_chunks(folder), media_type="text/csv; charset=utf-8",
                                     headers={"Content-Disposition": f'attachment; filename="fluidnet-{run_id}.csv"'})
        if format != "json":
            raise HTTPException(400, "支持 json、csv、html")
        return {"run": {k: stored[k] for k in ("id", "name", "mode", "status", "started")},
                "project": stored["request"]["project"], "result": stored["frame"]}

    @app.get("/api/v1/runs/{run_id}/events")
    def events(run_id: str):
        path = app.state.store.run_dir(run_id) / "events.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    @app.websocket("/api/v1/runs/{run_id}/stream")
    async def stream(websocket: WebSocket, run_id: str):
        origin = websocket.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1"}:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        last = -1
        try:
            while True:
                current = app.state.jobs.state(run_id)
                if current["sequence"] != last:
                    await websocket.send_json(current)
                    last = current["sequence"]
                if current["status"] in TERMINAL:
                    await websocket.close()
                    break
                await asyncio.sleep(0.1)
        except (WebSocketDisconnect, RuntimeError):
            pass
        except KeyError:
            await websocket.close(code=1008)

    @app.get("/api/v1/templates")
    def templates(include_archived: bool = False):
        return app.state.store.templates(include_archived)

    @app.post("/api/v1/templates")
    def save_template(template: TemplateRequest):
        return app.state.store.save_template(**normalize_template(template))

    @app.get("/api/v1/templates/{template_id}")
    def get_template(template_id: str, revision: int | None = None):
        return app.state.store.get_template(template_id, revision)

    @app.put("/api/v1/templates/{template_id}")
    def update_template(template_id: str, template: TemplateRequest):
        app.state.store.get_template(template_id)
        return app.state.store.save_template(**normalize_template(template), template_id=template_id)

    @app.get("/api/v1/templates/{template_id}/versions")
    def template_versions(template_id: str):
        return app.state.store.template_versions(template_id)

    @app.delete("/api/v1/templates/{template_id}")
    def archive_template(template_id: str, revision: int = Query(ge=1)):
        return app.state.store.archive_template(template_id, revision)

    @app.post("/api/v1/modules/group")
    def group_module(request: ModuleRequest):
        project, gid = configure_group(request.project, request.element_ids, request.name, request.interface, request.group_id)
        return {"project": project.model_dump(), "group_id": gid}

    @app.post("/api/v1/modules/extract")
    def extract_module(request: ModuleRequest):
        return extract_group(request.project.with_scenario(request.scenario_id), request.group_id)

    def requested_template(request):
        if request.template_id:
            template = app.state.store.get_template(request.template_id, request.revision)
            if template["archived"]:
                raise ValueError("型号已归档；可保留原实例，或将定义另存为新型号")
            return template
        if request.template is not None:
            return normalize_template(request.template)
        raise ValueError("请选择型号或提供完整的模板定义")

    @app.post("/api/v1/modules/insert")
    def insert_module(request: ModuleRequest):
        project, gid, ids = insert_template(request.project, requested_template(request), request.position, request.page)
        return {"project": project.model_dump(), "group_id": gid, "element_ids": ids}

    @app.post("/api/v1/modules/apply")
    def preview_module(request: ModuleRequest):
        project, changes = apply_template(request.project, requested_template(request), request.group_id, request.element_id)
        return {"project": project.model_dump(), "changes": changes}

    @app.post("/api/v1/modules/normalize")
    def normalize_module(template: TemplateRequest):
        return normalize_template(template)

    @app.post("/api/v1/modules/bench")
    def bench_module(template: TemplateRequest):
        return make_bench(template).model_dump()

    if static.exists():
        app.mount("/", StaticFiles(directory=str(static), html=True), name="web")
    else:
        @app.get("/", response_class=HTMLResponse)
        def not_built():
            return "<meta charset='utf-8'><h1>FluidNet 计算服务已启动</h1><p>请先运行 npm run build 构建网页。</p><a href='/docs'>API 文档</a>"
    return app
