"""Portable, verified snapshots. Restore creates a separate workspace directory."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import zipfile

from . import __version__
from .packages import load_module_package
from .storage import StorageError

MAX_BACKUP_BYTES = 2 * 1024**3


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            value.update(chunk)
    return value.hexdigest()


def backup_workspace(storage, modules, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise ValueError('备份目标已存在，请使用新文件名')
    with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=output.parent) as temporary:
        root = Path(temporary)
        # Module publishing takes only the module lock. Holding it before the DB
        # lock gives the backup one stable library and one committed DB snapshot.
        with modules.lock, storage.lock:
            snapshot = sqlite3.connect(root / 'workspace.sqlite3')
            try:
                storage.db.backup(snapshot)
            finally:
                snapshot.close()
            for module in modules.definitions():
                source = Path(module.package_path)
                target = root / 'module-packages' / f'module-{module.id}' / f'v{module.version}'
                if target.exists():
                    previous = load_module_package(target)
                    if (previous.content_hash, previous.definition_hash) != (module.content_hash, module.definition_hash):
                        raise StorageError('同一模块版本存在不同内容，无法生成一致备份')
                    continue
                target.mkdir(parents=True)
                for name in ('manifest.json', 'module.py', 'release.json'):
                    if (source / name).exists():
                        shutil.copyfile(source / name, target / name)
            revision = storage.workspace()['revision']
        files = {p.relative_to(root).as_posix(): {'sha256': digest(p), 'size': p.stat().st_size}
                 for p in sorted(root.rglob('*')) if p.is_file()}
        manifest = {'format': 'fluidnet-backup', 'version': 1, 'engine_version': __version__,
                    'created_at': datetime.now(timezone.utc).isoformat(), 'revision': revision, 'files': files}
        (root / 'backup.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        pending = root / 'snapshot.zip'
        with zipfile.ZipFile(pending, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name in [*files, 'backup.json']:
                archive.write(root / name, name)
        # Create-only publishing also prevents concurrent callers overwriting a backup.
        with output.open('xb') as target, pending.open('rb') as source:
            try:
                shutil.copyfileobj(source, target)
                target.flush()
                os.fsync(target.fileno())
            except BaseException:
                target.close()
                output.unlink(missing_ok=True)
                raise
    return manifest


def restore_workspace(source, destination):
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('恢复目录已存在；请选择一个新目录，当前工作区不会被覆盖')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=destination.parent) as temporary:
        root = Path(temporary) / 'workspace'
        root.mkdir()
        try:
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if len(names) != len(set(names)) or len(names) > 10000:
                    raise ValueError('备份包含重复或过多文件')
                if sum(entry.file_size for entry in entries) > MAX_BACKUP_BYTES:
                    raise ValueError('备份解压体积超过 2 GiB')
                if 'backup.json' not in names or archive.getinfo('backup.json').file_size > 1024**2:
                    raise ValueError('缺少有效的备份清单')
                manifest = json.loads(archive.read('backup.json'))
                if not isinstance(manifest, dict) or manifest.get('format') != 'fluidnet-backup' or manifest.get('version') != 1:
                    raise ValueError('不支持的备份格式或版本')
                if type(manifest.get('revision')) is not int or manifest['revision'] < 0:
                    raise ValueError('备份缺少有效的工作区修订号')
                files = manifest.get('files', {})
                if not isinstance(files, dict) or set(names) != set(files) | {'backup.json'}:
                    raise ValueError('备份文件与清单不一致')
                if 'workspace.sqlite3' not in files:
                    raise ValueError('备份缺少工作区数据库')
                for name, spec in files.items():
                    path = PurePosixPath(name)
                    allowed = name == 'workspace.sqlite3' or (
                        len(path.parts) == 4 and path.parts[0] == 'module-packages'
                        and path.parts[1].startswith('module-') and path.parts[2].startswith('v')
                        and path.parts[3] in {'manifest.json', 'module.py', 'release.json'})
                    if not allowed or path.is_absolute() or any(p in {'..', '.'} or ':' in p or '\\' in p for p in path.parts):
                        raise ValueError('备份包含不允许的文件路径')
                    target = root.joinpath(*path.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as incoming, target.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
                    if target.stat().st_size != spec['size'] or digest(target) != spec['sha256']:
                        raise ValueError(f'备份文件校验失败：{name}')
            connection = sqlite3.connect(root / 'workspace.sqlite3')
            try:
                if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('数据库完整性检查未通过')
                database_version = connection.execute('PRAGMA user_version').fetchone()[0]
                if database_version not in (1, 2):
                    raise ValueError('不支持的数据库版本')
                for table, columns in (('workspace', 'revision,saved_at,data'),
                                       ('runs', 'id,updated,record,overview'), ('frames', 'run_id,idx,data')):
                    connection.execute(f'SELECT {columns} FROM {table} LIMIT 1')
                if database_version == 2:
                    connection.execute('SELECT id,revision,saved_at,data FROM project_history LIMIT 1')
                if connection.execute('PRAGMA foreign_key_check').fetchone():
                    raise ValueError('数据库包含失效的运行历史引用')
                revision = connection.execute('SELECT coalesce(max(revision),0) FROM workspace').fetchone()[0]
                if revision != manifest['revision']:
                    raise ValueError('备份清单修订号与数据库不一致')
            finally:
                connection.close()
            for path in (root / 'module-packages').glob('module-*/v*'):
                load_module_package(path)  # Source and definition hashes; never execute source.
            (root / 'backup.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            os.rename(root, destination)
        except (zipfile.BadZipFile, KeyError, TypeError, sqlite3.Error, OSError) as error:
            raise ValueError(f'备份无法恢复：{error}') from error
    return manifest
