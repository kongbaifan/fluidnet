"""MOD-B0: capture the executable baseline without opening user storage.

Run from any directory: python scripts/module_baseline.py --output <artifact-directory>.
The bundle contains HEAD, a binary tracked-file patch, and untracked-file overlays.
Replay in a separate checkout, never in the user's module/workspace directory.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import inspect
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'backend') not in sys.path:
    sys.path.insert(0, str(ROOT / 'backend'))

THREAD_KEYS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')
DEPENDENCIES = ('pydantic', 'numpy', 'scipy', 'CoolProp', 'fastapi', 'uvicorn',
                'pytest', 'pytest-cov', 'ruff', 'mypy', 'psutil')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def git(*args):
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True,
                          capture_output=True, timeout=30).stdout


def now():
    # Windows' stdlib installation need not include an IANA timezone database.
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def output_directory(path):
    path = Path(path).resolve()
    repo = Path(git('rev-parse', '--show-toplevel').decode().strip())
    # In-repository results belong only in the ignored artifact area.
    if path.is_relative_to(repo) and not path.is_relative_to(ROOT / 'artifacts/module-system'):
        raise ValueError('仓库内输出必须位于 artifacts/module-system/，不能写入用户模块或工作区目录')
    path.mkdir(parents=True, exist_ok=True)
    return path


def module_inventory():
    from fn_engine.packages import discover_module_packages
    from fn_engine.runtime import module_content_hash, module_definition_hash

    return [{'id': module.id, 'version': module.version, 'schema_version': module.schema_version,
             'package': Path(module.package_path).relative_to(ROOT).as_posix(),
             'content_hash': module_content_hash(module), 'definition_hash': module_definition_hash(module)}
            for module in discover_module_packages(ROOT / 'modules')]


def environment():
    from fn_engine.models import SolverOptions
    from fn_engine.runtime import ModuleContext, NetworkBuilder

    versions = {}
    for name in DEPENDENCIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    openapi_path = ROOT / 'contracts/openapi.json'
    openapi = json.loads(openapi_path.read_text(encoding='utf-8'))
    methods = {'get', 'post', 'put', 'patch', 'delete', 'options', 'head'}
    endpoints = sorted(f'{method.upper()} {path}' for path, route in openapi['paths'].items()
                       for method in route if method in methods)
    api = {cls.__name__: {name: str(inspect.signature(value)) for name, value in vars(cls).items()
                         if not name.startswith('_') and callable(value)}
           for cls in (ModuleContext, NetworkBuilder)}
    return {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
            'machine': platform.machine(), 'processor': platform.processor(), 'cpu_count': os.cpu_count(),
            'dependencies': versions, 'native_thread_environment': {k: os.environ.get(k) for k in THREAD_KEYS},
            'solver_defaults': SolverOptions().model_dump(mode='json'), 'legacy_runtime_api': api,
            'http_api': {'source': 'contracts/openapi.json', 'sha256': digest(openapi_path.read_bytes()),
                         'endpoints': endpoints, 'validation': 'run generate_contracts.py --check separately'}}


def capture(path):
    path = output_directory(path)
    if (path / 'baseline.json').exists():
        raise FileExistsError('基线目录已有 baseline.json；请使用新目录保留原始基线')
    repo = Path(git('rev-parse', '--show-toplevel').decode().strip())
    def repo_git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], check=True,
                              capture_output=True, timeout=30).stdout
    tracked = repo_git('ls-files', '-z').decode('utf-8').split('\0')
    untracked = repo_git('ls-files', '--others', '--exclude-standard', '-z').decode('utf-8').split('\0')
    supplement = subprocess.run(['git', '-C', str(repo), 'diff', '--binary', 'HEAD'],
                                check=True, capture_output=True, timeout=30).stdout
    (path / 'workspace.patch').write_bytes(supplement)
    overlays, sources = [], []
    project_prefix = ROOT.relative_to(repo).as_posix() + '/'
    for name in sorted(set(tracked + untracked) - {''}):
        source = repo / name
        is_source = (name.startswith((project_prefix, '.github/')) and
                     source.suffix in {'.py', '.js', '.mjs', '.json', '.toml', '.ini', '.txt', '.yml', '.yaml'})
        if not is_source and name not in untracked:
            continue
        if source.is_symlink():
            raise ValueError(f'基线不复制符号链接：{name}')
        if not source.is_file():
            continue
        data = source.read_bytes()
        relative = Path(name).as_posix()
        record = {'path': relative, 'sha256': digest(data), 'bytes': len(data)}
        if name in untracked:
            target = path / 'overlay' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            overlays.append(record)
        if is_source:
            sources.append({**record, 'lf_sha256': digest(data.replace(b'\r\n', b'\n'))})
    report = {'format_version': 1, 'work_package': 'MOD-B0', 'generated_at': now(),
              'commit': git('rev-parse', 'HEAD').decode().strip(),
              'working_tree_status': git('status', '--porcelain=v1').decode('utf-8').splitlines(),
              'tracked_patch_sha256': digest(supplement), 'untracked_overlays': overlays,
              'source_files': sources, 'source_manifest_sha256': digest(json_bytes(sources)),
              'environment': environment(), 'modules': module_inventory(),
              'storage_policy': 'no user storage opened; run samples in TemporaryDirectory',
              'replay': ['create a separate checkout at commit', 'git apply --binary workspace.patch (if nonempty)',
                         'copy overlay/ contents into that checkout preserving repository-relative paths',
                         'verify overlay/source SHA-256 and install the recorded dependencies',
                         'run benchmark_modules.py with an isolated artifact output directory']}
    (path / 'baseline.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                                       encoding='utf-8')
    return report


def verify_sources(report, checkout):
    """Verify restored code, allowing only checkout CRLF conversion on tracked text."""
    checkout = Path(checkout).resolve()
    endings = []
    for entry in report['source_files'] + report['untracked_overlays']:
        path = (checkout / entry['path']).resolve()
        if not path.is_relative_to(checkout):
            raise ValueError(f'非法快照路径：{entry["path"]}')
        data = path.read_bytes()
        if digest(data) == entry['sha256']:
            continue
        if entry.get('lf_sha256') == digest(data.replace(b'\r\n', b'\n')):
            endings.append(entry['path'])
            continue
        raise ValueError(f'源码哈希不一致：{entry["path"]}')
    return {'source_files_verified': len(report['source_files']),
            'overlays_verified': len(report['untracked_overlays']),
            'line_ending_only_differences': endings}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'artifacts/module-system' /
                                               git('rev-parse', '--short', 'HEAD').decode().strip() / 'MOD-B0'))
    parser.add_argument('--verify', type=Path, help='verify baseline.json against this separate checkout')
    args = parser.parse_args(argv)
    if args.verify:
        report = json.loads(args.verify.read_text(encoding='utf-8'))
        repo = Path(git('rev-parse', '--show-toplevel').decode().strip())
        print(json.dumps(verify_sources(report, repo), ensure_ascii=False))
        return
    report = capture(args.output)
    print(json.dumps({'commit': report['commit'], 'modules': len(report['modules']),
                      'source_manifest_sha256': report['source_manifest_sha256'], 'output': args.output}))


if __name__ == '__main__':
    main()
