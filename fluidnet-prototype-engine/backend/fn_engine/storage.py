"""Local, transactional workspace and bounded run archives (one service per directory)."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import shutil
from threading import RLock
import time
import zlib

TERMINAL = {'completed', 'failed', 'cancelled', 'interrupted'}


class StorageError(RuntimeError):
    code = 'STORAGE_FAILED'


class WorkspaceConflict(ValueError):
    pass


def pack(value):
    return zlib.compress(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))


def unpack(value):
    return json.loads(zlib.decompress(value))


class WorkspaceStore:
    def __init__(self, root, recover=True):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.guard = (self.root / 'service.lock').open('a+b')
        self.db = None
        try:
            self.guard.seek(0, 2)
            if self.guard.tell() == 0:
                self.guard.write(b'0')
                self.guard.flush()
            self.guard.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.guard.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.guard.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(self.root / 'workspace.sqlite3', check_same_thread=False, timeout=5)
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
            self.db.execute('PRAGMA foreign_keys=ON')
            version = self.db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise StorageError(f'工作区版本 {version} 不受当前程序支持')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS workspace(revision INTEGER PRIMARY KEY, saved_at TEXT NOT NULL, data BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, updated REAL NOT NULL, record BLOB NOT NULL, overview BLOB);
                CREATE TABLE IF NOT EXISTS frames(run_id TEXT REFERENCES runs(id) ON DELETE CASCADE, idx INTEGER, data BLOB NOT NULL, PRIMARY KEY(run_id,idx));
                CREATE TABLE IF NOT EXISTS project_history(id TEXT, revision INTEGER, saved_at TEXT NOT NULL, data BLOB, PRIMARY KEY(id,revision));
            ''')
            if version < 2:
                with self.transaction() as db:
                    row = db.execute('SELECT saved_at,data FROM workspace ORDER BY revision DESC LIMIT 1').fetchone()
                    if row:
                        self._sync_projects(db, unpack(row[1]), row[0])
                    db.execute('PRAGMA user_version=2')
            if recover:
                self._recover()
        except Exception as error:
            self.close()
            raise StorageError(f'无法打开工作区（请确认目录可写且未被另一服务占用）：{error}') from error

    @contextmanager
    def transaction(self):
        try:
            with self.lock, self.db:
                yield self.db
        except (sqlite3.Error, OSError) as error:
            raise StorageError(f'工作区读写失败，请检查磁盘空间和目录权限：{error}') from error

    def workspace(self, revision=None):
        with self.transaction() as db:
            row = db.execute('SELECT revision,saved_at,data FROM workspace ORDER BY revision DESC LIMIT 1').fetchone() if revision is None else \
                db.execute('SELECT revision,saved_at,data FROM workspace WHERE revision=?', (revision,)).fetchone()
            if row is None:
                if revision is not None:
                    raise KeyError(revision)
                return {'revision': 0, 'saved_at': None, 'data': None}
            return {'revision': row[0], 'saved_at': row[1], 'data': unpack(row[2]),
                    'project_revisions': self.project_revisions() if revision is None else {}}

    def revisions(self):
        with self.transaction() as db:
            return [{'revision': r, 'saved_at': t} for r, t in db.execute('SELECT revision,saved_at FROM workspace ORDER BY revision DESC')]

    def usage(self):
        with self.transaction() as db:
            page_size = db.execute('PRAGMA page_size').fetchone()[0]
            pages = db.execute('PRAGMA page_count').fetchone()[0]
            free = db.execute('PRAGMA freelist_count').fetchone()[0]
            frames = db.execute('SELECT count(*) FROM frames').fetchone()[0]
            runs = db.execute('SELECT count(*) FROM runs').fetchone()[0]
            wal = self.root / 'workspace.sqlite3-wal'
            return {'database_bytes': pages * page_size, 'reusable_bytes': free * page_size,
                    'wal_bytes': wal.stat().st_size if wal.exists() else 0, 'free_disk_bytes': shutil.disk_usage(self.root).free,
                    'runs': runs, 'frames': frames, 'revision_retention': 5, 'run_retention': 20,
                    'history_window_max': 20001, 'overview_points': 2000}

    def save_workspace(self, data, expected_revision):
        saved_at = datetime.now(timezone.utc).isoformat()
        with self.transaction() as db:
            revision = self._write_workspace(db, data, expected_revision, saved_at)
            return {'revision': revision, 'saved_at': saved_at, 'project_revisions': self.project_revisions()}

    def _write_workspace(self, db, data, expected_revision, saved_at):
        current = db.execute('SELECT COALESCE(MAX(revision),0) FROM workspace').fetchone()[0]
        if current != expected_revision:
            raise WorkspaceConflict(f'服务器已有修订 {current}，当前页面基于 {expected_revision}；请先导出本地草稿，再重新载入服务器工作区')
        revision = current + 1
        db.execute('INSERT INTO workspace VALUES(?,?,?)', (revision, saved_at, pack(data)))
        self._sync_projects(db, data, saved_at)
        db.execute('DELETE FROM workspace WHERE revision<=?', (revision - 5,))
        return revision

    def _sync_projects(self, db, data, saved_at):
        from .projects import project_document
        latest = {pid: (rev, blob) for pid, rev, blob in db.execute(
            'SELECT h.id,h.revision,h.data FROM project_history h JOIN (SELECT id,max(revision) revision FROM project_history GROUP BY id) x USING(id,revision)')}
        documents = {p['id']: project_document(data, p['id']) for p in data['projects']}
        for pid in latest.keys() | documents.keys():
            rev, previous = latest.get(pid, (0, None))
            document = documents.get(pid)
            if (unpack(previous) if previous else None) == document:
                continue
            db.execute('INSERT INTO project_history VALUES(?,?,?,?)', (pid, rev + 1, saved_at, pack(document) if document else None))
            db.execute('DELETE FROM project_history WHERE id=? AND revision<=?', (pid, rev + 1 - 5))

    def project_revisions(self):
        with self.transaction() as db:
            return dict(db.execute('SELECT id,max(revision) FROM project_history GROUP BY id'))

    def project_history(self, project_id):
        with self.transaction() as db:
            return [{'revision': r, 'saved_at': t, 'deleted': data is None} for r, t, data in db.execute(
                'SELECT revision,saved_at,data FROM project_history WHERE id=? ORDER BY revision DESC', (project_id,))]

    def project(self, project_id, revision=None):
        with self.transaction() as db:
            if revision is None:
                row = db.execute('SELECT revision,saved_at,data FROM project_history WHERE id=? ORDER BY revision DESC LIMIT 1', (project_id,)).fetchone()
            else:
                row = db.execute('SELECT revision,saved_at,data FROM project_history WHERE id=? AND revision=?', (project_id, revision)).fetchone()
            if not row or row[2] is None:
                raise KeyError(project_id)
            return {'revision': row[0], 'saved_at': row[1], 'document': unpack(row[2])}

    def projects(self):
        result = []
        for pid in self.project_revisions():
            try:
                item = self.project(pid)
            except KeyError:
                continue
            p = item['document']['project']
            result.append({'id': pid, 'name': p.get('name', pid), 'revision': item['revision'], 'saved_at': item['saved_at'],
                           'instances': sum(len(pg.get('nodes', [])) for pg in p.get('pages', []))})
        return result

    def save_project(self, document, expected_revision, delete=False):
        from .projects import merge_project
        from .models import WorkspaceSaveRequest
        pid = document['project']['id']
        with self.transaction() as db:
            current = self.project_revisions().get(pid, 0)
            if current != expected_revision:
                raise WorkspaceConflict(f'项目 {pid} 已有修订 {current}，当前页面基于 {expected_revision}')
            workspace = self.workspace()
            if workspace['data'] is None:
                raise ValueError('请先保存初始工作区')
            if delete:
                data = workspace['data']
                if not any(p['id'] == pid for p in data['projects']):
                    raise ValueError('项目不存在')
                data['projects'] = [p for p in data['projects'] if p['id'] != pid]
                if not data['projects']:
                    raise ValueError('至少保留一个项目')
                if data['activeProject'] == pid:
                    data['activeProject'] = data['projects'][0]['id']
                data.get('charts', {}).setdefault('extra', [])[:] = [c for c in data.get('charts', {}).get('extra', []) if not isinstance(c, dict) or c.get('projectId') != pid]
            else:
                data = merge_project(workspace['data'], document)
            WorkspaceSaveRequest(expected_revision=workspace['revision'], data=data)
            saved_at = datetime.now(timezone.utc).isoformat()
            new_workspace = self._write_workspace(db, data, workspace['revision'], saved_at)
            return {'revision': self.project_revisions()[pid], 'saved_at': saved_at,
                    'workspace_revision': new_workspace, 'previous_workspace_revision': workspace['revision']}

    def save_run(self, record, rows=(), total_rows=0, window=2001, overview=None):
        metadata = {k: v for k, v in record.items() if k != 'history'}
        metadata['total_rows'] = total_rows
        metadata['persisted_at'] = datetime.now(timezone.utc).isoformat()
        metadata['persisted_rows'] = total_rows
        with self.transaction() as db:
            db.execute('INSERT INTO runs(id,updated,record) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,record=excluded.record',
                       (record['id'], time.time(), pack(metadata)))
            db.executemany('INSERT OR REPLACE INTO frames VALUES(?,?,?)', [(record['id'], i, pack(row)) for i, row in rows])
            db.execute('DELETE FROM frames WHERE run_id=? AND idx<?', (record['id'], max(0, total_rows - window)))
            if overview is not None:
                db.execute('UPDATE runs SET overview=? WHERE id=?', (pack(overview), record['id']))
            if record['status'] in TERMINAL:
                self._prune(db)
        record.update(persisted_at=metadata['persisted_at'], persisted_rows=total_rows)

    @staticmethod
    def _prune(db):
        ended = [rid for rid, blob in db.execute('SELECT id,record FROM runs ORDER BY updated DESC')
                 if unpack(blob)['status'] in TERMINAL]
        db.executemany('DELETE FROM runs WHERE id=?', [(rid,) for rid in ended[20:]])

    def record(self, run_id):
        with self.transaction() as db:
            row = db.execute('SELECT record FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return unpack(row[0])

    def records(self):
        with self.transaction() as db:
            records = [unpack(row[0]) for row in db.execute('SELECT record FROM runs ORDER BY updated DESC')]
        return [{'id': r['id'], 'status': r['status'], 'mode': r['mode'], 'name': r['request']['project']['name'],
                 'time_s': (r.get('frame') or {}).get('time_s', 0)} for r in records]

    def history(self, run_id, offset, limit):
        with self.transaction() as db:
            record = self.record(run_id)
            first = db.execute('SELECT MIN(idx) FROM frames WHERE run_id=?', (run_id,)).fetchone()[0]
            first = first if first is not None else record['total_rows']
            start = max(first, offset)
            rows = [unpack(row[0]) for row in db.execute('SELECT data FROM frames WHERE run_id=? AND idx>=? ORDER BY idx LIMIT ?', (run_id, start, limit))]
        return {'rows': rows, 'total_rows': record['total_rows'], 'offset': start, 'first_offset': first, 'truncated': offset < first}

    def overview(self, run_id):
        with self.transaction() as db:
            record = self.record(run_id)
            row = db.execute('SELECT overview FROM runs WHERE id=?', (run_id,)).fetchone()
            data = unpack(row[0]) if row and row[0] else {'rows': [], 'stride': 1}
            last = db.execute('SELECT data FROM frames WHERE run_id=? ORDER BY idx DESC LIMIT 1', (run_id,)).fetchone()
            if last:
                frame = unpack(last[0])
                if not data['rows'] or data['rows'][-1]['time_s'] != frame['time_s']:
                    data['rows'].append(frame)
        return {**data, 'total_rows': record['total_rows']}

    def delete_run(self, run_id):
        with self.transaction() as db:
            if not db.execute('DELETE FROM runs WHERE id=?', (run_id,)).rowcount:
                raise KeyError(run_id)

    def _recover(self):
        with self.transaction() as db:
            rows = list(db.execute('SELECT id,record FROM runs'))
            for rid, blob in rows:
                record = unpack(blob)
                if record['status'] in TERMINAL:
                    continue
                record['status'] = 'interrupted'
                frame = record.get('frame') or {}
                time_s = frame.get('time_s', 0.)
                if frame:
                    frame.update(status='interrupted', valid=False)
                events = record.setdefault('events', [])
                latest = {e['command_id']: e for e in events if e.get('command_id')}
                for key, event in latest.items():
                    if event.get('command_status') == 'accepted':
                        events.append({'type': 'command', 'time_s': time_s, 'command_id': key, 'command_status': 'rejected',
                                       'message': '服务中断，命令生效结果未确认；恢复历史后请新建运行'})
                events.append({'type': 'interrupted', 'time_s': time_s, 'message': '服务已重新启动，保留最后落盘历史；继续计算请新建运行'})
                record['events'] = events[-1000:]
                db.execute('UPDATE runs SET record=? WHERE id=?', (pack(record), rid))
            self._prune(db)

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if not self.guard.closed:
            self.guard.close()
