from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urljoin

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import FileResponse

from fn_engine.api import create_app
from fn_engine.frontend_assets import FrontendAssets


@pytest.fixture
def frontend(tmp_path: Path):
    root = tmp_path / "frontend"
    root.mkdir()
    (root / "index.html").write_text(
        '<!doctype html><link rel="stylesheet" href="style.css">'
        '<link rel="stylesheet" href="https://example.test/external.css">'
        '<main>studio</main><script type="module" src="bootstrap.js"></script>', encoding="utf-8")
    (root / "bootstrap.js").write_text("import './nested/feature.js';", encoding="utf-8")
    (root / "style.css").write_text("body { color: black; }", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "feature.js").write_text("import '../shared.js'; export const ready = true;", encoding="utf-8")
    (root / "shared.js").write_text("export const value = 1;", encoding="utf-8")
    assets = FrontendAssets(root)
    app = FastAPI()
    app.mount("/", assets)
    with TestClient(app) as client:
        yield root, assets, client


def entry_url(html: str) -> str:
    return re.search(r'src="([^\"]+/bootstrap.js)"', html)[1]


def test_entry_and_relative_module_graph_share_the_same_revision(frontend):
    _, assets, client = frontend
    for path in ("/", "/index.html"):
        response = client.get(path)
        assert response.status_code == 200
        url = entry_url(response.text)
        assert url == f"/_ui/{assets.revision()}/bootstrap.js"
        assert f'href="/_ui/{assets.revision()}/style.css"' in response.text
        assert 'href="https://example.test/external.css"' in response.text
        assert client.get(url).text == "import './nested/feature.js';"
        nested = urljoin(url, "nested/feature.js")
        assert "export const ready = true" in client.get(nested).text
        assert client.get(urljoin(nested, "../shared.js")).text == "export const value = 1;"


@pytest.mark.parametrize("asset", ["shared.js", "style.css", "index.html"])
def test_any_frontend_source_change_advances_revision_and_rejects_the_old_prefix(frontend, asset):
    root, assets, client = frontend
    before = assets.revision()
    path = root / asset
    info = path.stat()
    # Same-length edits with a nanosecond timestamp change still invalidate the graph.
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("1", "2") if asset.endswith(".js") else content + " ", encoding="utf-8")
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000))
    after = assets.revision()
    assert after != before
    assert entry_url(client.get("/").text) == f"/_ui/{after}/bootstrap.js"
    assert client.get(f"/_ui/{before}/bootstrap.js").status_code == 404


def test_renamed_or_new_asset_changes_revision(frontend):
    root, assets, _ = frontend
    before = assets.revision()
    (root / "new.js").write_text("", encoding="utf-8")
    added = assets.revision()
    assert added != before
    (root / "new.js").rename(root / "renamed.js")
    assert assets.revision() != added


def test_no_store_and_conditional_requests_never_reuse_old_entry(frontend):
    root, assets, client = frontend
    legacy = client.get("/bootstrap.js")
    assert legacy.status_code == 200
    old_entry_etag = FileResponse(root / "index.html", stat_result=(root / "index.html").stat()).headers["etag"]
    assert client.get("/", headers={"If-None-Match": old_entry_etag}).status_code == 200
    for path in ("/", "/index.html", "/bootstrap.js", "/style.css", f"/_ui/{assets.revision()}/bootstrap.js"):
        response = client.get(path, headers={"If-None-Match": legacy.headers["etag"], "If-Modified-Since": "Wed, 01 Jan 2099 00:00:00 GMT"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
    assert client.get("/").headers.get("etag") is None
    head = client.head("/")
    assert head.status_code == 200
    assert head.headers["cache-control"] == "no-store"
    assert head.content == b""


def test_missing_assets_and_paths_stay_404_instead_of_becoming_the_entry(frontend):
    root, assets, client = frontend
    (root.parent / "private.js").write_text("PRIVATE_SECRET", encoding="utf-8")
    for path in ("/missing", "/missing.js", "/_ui/not-a-revision/bootstrap.js",
                 f"/_ui/{assets.revision()}/missing.js", "/%2e%2e/private.js",
                 f"/_ui/{assets.revision()}/%2e%2e/%2e%2e/%2e%2e/private.js",
                 f"/_ui/{assets.revision()}/%2e%2e%5c%2e%2e%5c%2e%2e%5cprivate.js"):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "PRIVATE_SECRET" not in response.text
        assert "<main>studio</main>" not in response.text


def test_api_mount_uses_versioned_entry_and_headless_does_not_mount_it(frontend, tmp_path):
    root, _, _ = frontend
    with TestClient(create_app(frontend_root=root, data_root=tmp_path / "studio-data")) as client:
        assert client.get("/").status_code == 200
        assert "/_ui/" in client.get("/").text
        assert client.get("/api/v1/health").json()["mode"] == "studio"
    with TestClient(create_app(data_root=tmp_path / "headless-data")) as client:
        assert client.get("/").status_code == 404
        assert client.get("/bootstrap.js").status_code == 404
        assert client.get("/api/v1/health").json()["mode"] == "headless"
