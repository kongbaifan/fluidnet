"""捆绑 REFPROP 的运行时发现与 /api/v1/health 上报。

不加载 DLL、不要求真实安装：用 tmp_path 造假目录（空 REFPRP64.DLL 即可，判定只看存在性）。
本机装了 REFPROP 时，最后的真实联动用例会真实运行；CI 无安装则 skip。
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine import properties
from fn_engine.api import create_app
from fn_engine.properties import REFPROP_LIBRARY, refprop_candidates, refprop_info, refprop_root

LAYOUTS = ('vendor/refprop9.1', 'refprop9.1', 'refprop', 'NISTRefprop9.1')


def fake_install(root: Path, *, library: bool = True, fluids: bool = True, uppercase: bool = False) -> Path:
    """造一个看起来像 REFPROP 的目录；判定只看文件存在，所以空 DLL 就够。"""
    root.mkdir(parents=True, exist_ok=True)
    if library:
        (root / REFPROP_LIBRARY).write_bytes(b'')
    if fluids:
        (root / ('FLUIDS' if uppercase else 'fluids')).mkdir(exist_ok=True)
    return root


def write_manifest(root: Path, version='9.1') -> None:
    (root / properties.BUNDLE_MANIFEST).write_text(json.dumps({
        'format': 'fluidnet-refprop-bundle', 'version': version, 'library': REFPROP_LIBRARY,
        'source': r'C:\Program Files (x86)\REFPROP'}, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """隔离真实安装：环境变量清空，默认目录与捆绑候选都指向空目录，用例自行覆盖。"""
    monkeypatch.delenv(properties.REFPROP_ENV, raising=False)
    monkeypatch.setattr(properties, 'REFPROP_DEFAULT', tmp_path / 'no-system')
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [tmp_path / 'no-bundle'])
    return tmp_path


def test_env_override_beats_bundled_directory(isolated, monkeypatch):
    env_root = fake_install(isolated / 'env-install')
    bundle_base = isolated / 'bundle-base'
    assert fake_install(bundle_base / 'vendor' / 'refprop9.1').is_dir()
    monkeypatch.setenv(properties.REFPROP_ENV, str(env_root))
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [bundle_base])
    assert refprop_root() == env_root
    assert refprop_info() == {'installed': True, 'source': 'env', 'path': str(env_root), 'version': None}


def test_invalid_env_override_does_not_fall_back(isolated, monkeypatch):
    """显式覆盖指向坏目录时当未安装，不能静默用上捆绑/系统目录里的另一套文件。"""
    assert fake_install(isolated / 'bundle-base' / 'vendor' / 'refprop9.1').is_dir()
    monkeypatch.setenv(properties.REFPROP_ENV, str(isolated / 'empty-env'))
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [isolated / 'bundle-base'])
    assert refprop_root() is None
    assert refprop_info()['installed'] is False


@pytest.mark.parametrize('layout', LAYOUTS)
def test_bundled_layouts_are_discovered(isolated, monkeypatch, layout):
    base = isolated / 'base'
    install = fake_install(base / layout)
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [base])
    assert refprop_root() == install
    assert refprop_info()['source'] == 'bundled'
    assert Path(refprop_info()['path']) == install


def test_directory_without_fluid_files_is_skipped(isolated, monkeypatch):
    base = isolated / 'base'
    incomplete = fake_install(base / 'vendor' / 'refprop9.1', fluids=False)
    complete = fake_install(base / 'refprop')
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [base])
    assert not (incomplete / 'fluids').exists()
    assert refprop_root() == complete


def test_uppercase_fluids_directory_counts_as_installation(isolated, monkeypatch):
    base = isolated / 'base'
    install = fake_install(base / 'vendor' / 'refprop9.1', uppercase=True)
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [base])
    assert refprop_root() == install


def test_no_refprop_anywhere_reports_not_installed(isolated):
    assert refprop_root() is None
    assert refprop_info() == {'installed': False, 'source': None, 'path': None, 'version': None}


def test_candidates_follow_the_contract_order_and_dedupe(isolated, monkeypatch):
    # 项目根、仓库根、当前工作目录可能重合，重复 base 只保留第一次出现
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [isolated / 'a', isolated / 'b', isolated / 'a'])
    expected = [isolated / 'a' / layout for layout in LAYOUTS]
    expected += [isolated / 'b' / layout for layout in LAYOUTS]
    expected += [isolated / 'no-system']
    assert refprop_candidates() == expected
    assert len({str(path) for path in expected}) == len(expected)

    env_root = isolated / 'env-install'
    monkeypatch.setenv(properties.REFPROP_ENV, str(env_root))
    candidates = refprop_candidates()
    assert candidates[0] == env_root
    assert candidates[1:] == expected


def test_manifest_version_is_reported(isolated, monkeypatch):
    base = isolated / 'base'
    install = fake_install(base / 'vendor' / 'refprop9.1')
    write_manifest(install, '9.1')
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [base])
    info = refprop_info()
    assert info['installed'] is True
    assert info['source'] == 'bundled'
    assert info['version'] == '9.1'
    assert Path(info['path']) == install


@pytest.mark.parametrize('manifest', [None, '', '{not json', '[]', '{"format":"fluidnet-refprop-bundle"}'])
def test_missing_or_broken_manifest_keeps_installed_without_version(isolated, monkeypatch, manifest):
    base = isolated / 'base'
    install = fake_install(base / 'vendor' / 'refprop9.1')
    if manifest is not None:
        (install / properties.BUNDLE_MANIFEST).write_text(manifest, encoding='utf-8')
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [base])
    info = refprop_info()
    assert info['installed'] is True and info['source'] == 'bundled'
    assert info['version'] is None


def test_system_default_install_is_labelled_system(isolated, monkeypatch):
    system = fake_install(isolated / 'system-install')
    monkeypatch.setattr(properties, 'REFPROP_DEFAULT', system)
    assert refprop_root() == system
    assert refprop_info() == {'installed': True, 'source': 'system', 'path': str(system), 'version': None}


def test_health_reports_full_refprop_capability(isolated, monkeypatch):
    base = isolated / 'base'
    install = fake_install(base / 'vendor' / 'refprop9.1')
    write_manifest(install, '9.1')
    monkeypatch.setattr(properties, '_bundle_bases', lambda: [base])
    with TestClient(create_app(module_storage_root=isolated / 'modules')) as client:
        response = client.get('/api/v1/health')
    assert response.status_code == 200
    capability = response.json()['capabilities']['refprop']
    assert set(capability) == {'installed', 'source', 'path', 'version'}
    assert capability['installed'] is True
    assert capability['source'] == 'bundled'
    assert capability['version'] == '9.1'
    assert Path(capability['path']) == install


def test_health_reports_refprop_missing(isolated):
    with TestClient(create_app(module_storage_root=isolated / 'modules')) as client:
        capability = client.get('/api/v1/health').json()['capabilities']['refprop']
    assert capability == {'installed': False, 'source': None, 'path': None, 'version': None}


def test_real_installation_is_consistent():
    """真实联动：本机有安装时 refprop_info() 与 refprop_root() 自洽。"""
    root = refprop_root()
    if root is None:
        pytest.skip('本机没有 REFPROP 安装')
    info = refprop_info()
    assert info['installed'] is True
    assert info['source'] in ('env', 'bundled', 'system')
    assert Path(info['path']).resolve() == Path(root).resolve()
    assert properties._is_refprop_installation(root)
