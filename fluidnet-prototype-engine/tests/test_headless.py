from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine import cli
from fn_engine.api import create_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('frontend, mode, static_status', [
    (None, 'headless', 404), ('', 'headless', 404), (ROOT / 'frontend', 'studio', 200)])
def test_health_mode_matches_static_ui_mount(frontend, mode, static_status, tmp_path):
    with TestClient(create_app(frontend, data_root=tmp_path)) as client:
        assert client.get('/api/v1/health').json()['mode'] == mode
        assert client.get('/').status_code == static_status
        assert client.get('/studio.js').status_code == static_status
        assert client.get('/api/v1/catalog').status_code == 200
        assert client.get('/openapi.json').status_code == 200


@pytest.mark.parametrize('headless', [False, True])
def test_cli_headless_preserves_auth_workspace_and_other_serve_options(tmp_path, monkeypatch, headless):
    import uvicorn
    monkeypatch.setenv('FLUIDNET_TOKEN_FILE', str(tmp_path / 'tokens.json'))
    seen = {}

    def run(app, **options):
        seen.update(options)
        with TestClient(app) as client:
            seen['health'] = client.get('/api/v1/health').json()
            seen['static_status'] = client.get('/').status_code
            assert client.get('/api/v1/projects').status_code == 200

    monkeypatch.setattr(uvicorn, 'run', run)
    args = ['serve', '--data-dir', str(tmp_path / 'data'), '--host', '127.0.0.1', '--port', '18888', '--auth', 'off']
    cli.main([*args, *(['--headless'] if headless else [])])
    assert seen['health']['mode'] == ('headless' if headless else 'studio')
    assert seen['health']['auth']['required'] is False
    assert seen['health']['capabilities']['persistent_workspace'] is True
    assert seen['static_status'] == (404 if headless else 200)
    assert seen['host'] == '127.0.0.1' and seen['port'] == 18888
    assert (tmp_path / 'data/workspace.sqlite3').is_file()


def test_cli_rejects_open_and_headless_together(capsys):
    with pytest.raises(SystemExit) as error:
        cli.main(['serve', '--headless', '--open'])
    assert error.value.code == 2
    assert '--open' in capsys.readouterr().err


def test_cli_open_keeps_the_existing_browser_launch(tmp_path, monkeypatch):
    import threading
    import uvicorn
    import webbrowser
    monkeypatch.setenv('FLUIDNET_TOKEN_FILE', str(tmp_path / 'tokens.json'))
    opened = []

    class ImmediateTimer:
        def __init__(self, delay, callback):
            assert delay == 1.0
            self.callback = callback

        def start(self):
            self.callback()

    monkeypatch.setattr(threading, 'Timer', ImmediateTimer)
    monkeypatch.setattr(webbrowser, 'open', lambda url: opened.append(url))

    def run(app, **options):
        with TestClient(app) as client:
            assert client.get('/api/v1/health').json()['mode'] == 'studio'

    monkeypatch.setattr(uvicorn, 'run', run)
    cli.main(['serve', '--open', '--port', '18889', '--data-dir', str(tmp_path / 'data')])
    assert opened == ['http://127.0.0.1:18889']
