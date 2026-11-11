"""Serve one revision of the browser module graph without reusing legacy caches."""
from __future__ import annotations

import hashlib
import posixpath
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, HTMLResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope


_REVISION = re.compile(r"[0-9a-f]{64}\Z")
_RESOURCE_TAG = re.compile(r"<(?:script|link)\b[^>]*>", re.IGNORECASE)
_RESOURCE_URL = re.compile(r'''(\b(?:src|href)\s*=\s*)(["'])([^"']+)\2''', re.IGNORECASE)


class FrontendAssets(StaticFiles):
    def __init__(self, directory: str | Path):
        super().__init__(directory=str(directory), html=True)
        self.frontend_root = Path(directory)

    def revision(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.frontend_root.rglob("*")):
            if path.suffix.lower() not in {".html", ".js", ".css"} or not path.is_file():
                continue
            try:
                info = path.stat()
            except FileNotFoundError:
                # A source edit may remove a file between listing and stat.
                continue
            name = path.relative_to(self.frontend_root).as_posix()
            digest.update(f"{name}\0{info.st_mtime_ns}\0{info.st_size}\0".encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def version_html(source: str, revision: str) -> str:
        def replace_url(match: re.Match[str]) -> str:
            url = urlsplit(match[3])
            if url.scheme or url.netloc or Path(url.path).suffix.lower() not in {".js", ".css"}:
                return match[0]
            path = posixpath.normpath("/" + url.path.lstrip("/"))
            versioned = urlunsplit(("", "", f"/_ui/{revision}{path}", url.query, url.fragment))
            return f"{match[1]}{match[2]}{versioned}{match[2]}"

        return _RESOURCE_TAG.sub(lambda match: _RESOURCE_URL.sub(replace_url, match[0]), source)

    async def get_response(self, path: str, scope: Scope) -> Response:
        revision = await run_in_threadpool(self.revision)
        normalized = path.replace("\\", "/")
        parts = normalized.split("/", 2)
        if parts[0] == "_ui":
            if len(parts) != 3 or not _REVISION.fullmatch(parts[1]) or parts[1] != revision:
                raise HTTPException(status_code=404)
            path = parts[2]
            normalized = path

        # A legacy browser may send an old entry ETag even after deployment.
        # Returning the current bytes also repairs cached root-level assets.
        fresh_scope = dict(scope)
        fresh_scope["headers"] = [(key, value) for key, value in scope.get("headers", [])
                                  if key.lower() not in {b"if-none-match", b"if-modified-since"}]
        response = await super().get_response(path, fresh_scope)
        if normalized in {".", "", "index.html"} and isinstance(response, FileResponse) and response.status_code == 200:
            source = await run_in_threadpool(Path(response.path).read_text, encoding="utf-8")
            response = HTMLResponse(self.version_html(source, revision))
            if scope["method"] == "HEAD":
                response.body = b""
        response.headers["Cache-Control"] = "no-store"
        return response
