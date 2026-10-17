"""REFPROP 捆绑脚本：用假来源覆盖复制、清单、幂等、冲突与校验；本机有真实安装时再跑一次加载探测。"""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'bundle_refprop.py'
LIBRARY = 'REFPRP64.DLL'
MANIFEST = 'refprop-manifest.json'
SYSTEM_REFPROP = Path(os.environ.get('FLUIDNET_REFPROP_PATH') or r'C:\Program Files (x86)\REFPROP')


def usable_refprop(path):
    """目录是否含 DLL、fluids/ 与 mixtures/，可用于真实加载探测。"""
    path = Path(path)
    return (path / LIBRARY).is_file() and (path / 'fluids').is_dir() and (path / 'mixtures').is_dir()


REAL_REFPROP = next((path for path in (SYSTEM_REFPROP, Path(r'C:\Program Files (x86)\REFPROP'))
                     if usable_refprop(path)), None)
needs_refprop = pytest.mark.skipif(REAL_REFPROP is None, reason='REFPROP 未安装')


def run(*args, timeout=300):
    """在项目根执行捆绑脚本，按 UTF-8 解码两个输出流。"""
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8', timeout=timeout)


def make_source(root, mixtures=True, extra=True):
    """构造假的 REFPROP 来源：REFPRP64.DLL 假文件 + fluids/（含子目录）+ mixtures/ + 非运行时文件。"""
    root = Path(root)
    (root / 'fluids' / 'sub').mkdir(parents=True)
    (root / LIBRARY).write_bytes(b'not-a-real-dll')
    (root / 'fluids' / 'WATER.FLD').write_text('water', encoding='utf-8')
    (root / 'fluids' / 'sub' / 'R134A.FLD').write_bytes(b'r134a')
    if mixtures:
        (root / 'mixtures').mkdir()
        (root / 'mixtures' / 'R407C.MIX').write_text('mixture', encoding='utf-8')
    if extra:
        (root / 'defaults.prf').write_text('defaults', encoding='utf-8')
        (root / 'FLUIDSET.LST').write_text('fluidset', encoding='utf-8')
        # 以下都不是运行时组件，不应被复制进捆绑目录。
        (root / 'REFPROP.EXE').write_bytes(b'exe')
        (root / 'refprop.dll').write_bytes(b'32-bit')
        (root / 'REFPRP64.LIB').write_bytes(b'lib')
        (root / 'refprop.chm').write_bytes(b'chm')
        (root / 'Examples').mkdir()
        (root / 'Examples' / 'demo.txt').write_text('demo', encoding='utf-8')
    return root


@pytest.fixture
def source(tmp_path):
    return make_source(tmp_path / 'REFPROP')


@pytest.fixture
def target(tmp_path):
    return tmp_path / 'vendor' / 'refprop9.1'


def bundle(source_path, target_path, *args):
    """以 --skip-verify 生成假来源捆绑，避免假 DLL 触发真实加载探测。"""
    return run('--source', source_path, '--target', target_path, '--skip-verify', *args)


def test_bundle_copies_the_minimal_runtime_set(source, target):
    done = bundle(source, target, '--json')
    assert done.returncode == 0, done.stderr
    summary = json.loads(done.stdout)
    assert summary['ok'] is True and summary['version'] == '9.1'
    # 只复制最小集与两个可选文件：DLL、2 个纯质、1 个混合物、defaults.prf、FLUIDSET.LST。
    assert summary['files'] == 6
    assert (target / LIBRARY).is_file()
    assert (target / 'fluids' / 'WATER.FLD').read_text(encoding='utf-8') == 'water'
    assert (target / 'fluids' / 'sub' / 'R134A.FLD').read_bytes() == b'r134a'
    assert (target / 'mixtures' / 'R407C.MIX').is_file()
    assert (target / 'defaults.prf').is_file() and (target / 'FLUIDSET.LST').is_file()
    for name in ('REFPROP.EXE', 'refprop.dll', 'REFPRP64.LIB', 'refprop.chm', 'Examples'):
        assert not (target / name).exists(), name
    manifest = json.loads((target / MANIFEST).read_text(encoding='utf-8'))
    assert manifest['format'] == 'fluidnet-refprop-bundle'
    assert manifest['version'] == '9.1' and manifest['library'] == LIBRARY
    assert manifest['source'] == str(source.resolve())
    assert manifest['license']
    assert datetime.fromisoformat(manifest['created_at']).tzinfo is not None
    assert set(manifest['files']) == {'REFPRP64.DLL', 'fluids/WATER.FLD', 'fluids/sub/R134A.FLD',
                                      'mixtures/R407C.MIX', 'defaults.prf', 'FLUIDSET.LST'}
    for name, spec in manifest['files'].items():
        data = (target / Path(name)).read_bytes()
        assert spec['size'] == len(data)
        assert spec['sha256'] == hashlib.sha256(data).hexdigest()
    assert summary['bytes'] == sum(spec['size'] for spec in manifest['files'].values())
    assert summary['manifest_sha256'] == hashlib.sha256((target / MANIFEST).read_bytes()).hexdigest()
    assert len(summary['entries']) == 3


def test_repeat_run_is_idempotent(source, target):
    first = bundle(source, target)
    assert first.returncode == 0, first.stderr
    assert '文件：6 个' in first.stdout
    manifest_before = (target / MANIFEST).read_bytes()
    second = bundle(source, target)
    assert second.returncode == 0, second.stderr
    assert '跳过复制' in second.stdout
    assert '文件：6 个' in second.stdout
    assert (target / MANIFEST).read_bytes() == manifest_before


def test_different_content_without_force_exits_one(source, target):
    assert bundle(source, target).returncode == 0
    (target / 'fluids' / 'WATER.FLD').write_text('tampered', encoding='utf-8')
    done = bundle(source, target)
    assert done.returncode == 1
    assert '--force' in done.stderr
    forced = bundle(source, target, '--force')
    assert forced.returncode == 0, forced.stderr
    assert (target / 'fluids' / 'WATER.FLD').read_text(encoding='utf-8') == 'water'


def test_check_accepts_a_good_bundle(source, target):
    assert bundle(source, target).returncode == 0
    done = run('--check', '--target', target, '--skip-verify', '--json')
    assert done.returncode == 0, done.stderr
    summary = json.loads(done.stdout)
    assert summary['ok'] is True and summary['files'] == 6 and summary['version'] == '9.1'
    assert summary['bytes'] > 0
    assert summary['manifest_sha256'] == hashlib.sha256((target / MANIFEST).read_bytes()).hexdigest()


def test_check_detects_tampering(source, target):
    assert bundle(source, target).returncode == 0
    path = target / 'mixtures' / 'R407C.MIX'
    path.write_bytes(b'X' + path.read_bytes()[1:])  # 大小不变，仅内容变化 -> sha256 不一致
    done = run('--check', '--target', target, '--skip-verify')
    assert done.returncode == 1
    assert 'sha256 不一致' in done.stderr


def test_check_requires_the_manifest(source, target):
    assert bundle(source, target).returncode == 0
    (target / MANIFEST).unlink()
    done = run('--check', '--target', target, '--skip-verify')
    assert done.returncode == 1
    assert MANIFEST in done.stderr


def test_source_without_mixtures_is_rejected(tmp_path, target):
    incomplete = make_source(tmp_path / 'incomplete', mixtures=False)
    done = bundle(incomplete, target)
    assert done.returncode == 1
    assert 'mixtures' in done.stderr
    assert not target.exists()


@needs_refprop
def test_real_refprop_bundle_passes_the_load_probe(tmp_path):
    """真实最小集复制到 tmp 后，构建与 --check 都做实际加载探测（约 5 MB，几秒）。"""
    target = tmp_path / 'refprop9.1'
    done = run('--source', REAL_REFPROP, '--target', target, '--json')
    assert done.returncode == 0, done.stderr
    summary = json.loads(done.stdout)
    assert summary['ok'] is True and summary['detected_version'].startswith('9.1')
    manifest = json.loads((target / MANIFEST).read_text(encoding='utf-8'))
    assert summary['files'] == len(manifest['files']) and summary['bytes'] > 4_000_000
    checked = run('--check', '--target', target, '--json')
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)['detected_version'].startswith('9.1')
