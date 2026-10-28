"""Batch records and results live independently of bounded project/run histories."""
from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
from datetime import datetime, timezone
import math
import uuid

from .storage import WorkspaceStore, pack, unpack

BATCH_SCHEMA = '''
CREATE TABLE IF NOT EXISTS batches(
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, request_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL, name TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL, status TEXT NOT NULL, snapshot BLOB NOT NULL,
    metadata BLOB NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0, error TEXT,
    UNIQUE(project_id,request_key));
CREATE TABLE IF NOT EXISTS batch_items(
    batch_id TEXT NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    id TEXT NOT NULL, ordinal INTEGER NOT NULL, name TEXT NOT NULL,
    scenario_id TEXT NOT NULL, status TEXT NOT NULL, run_id TEXT UNIQUE,
    started_at TEXT, finished_at TEXT, attempts BLOB NOT NULL,
    result BLOB, curves BLOB, PRIMARY KEY(batch_id,id));
CREATE INDEX IF NOT EXISTS batches_project_created ON batches(project_id,created_at);
'''


class BatchConflict(ValueError):
    pass


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def numeric_value(frame, key):
    value = (frame.get('metrics') or {}).get(key[8:]) if key.startswith('metrics.') else \
        (frame.get('variables') or {}).get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def finish_batch(db, batch_id):
    row = db.execute('SELECT status FROM batches WHERE id=?', (batch_id,)).fetchone()
    if not row or row[0] != 'running':
        return
    states = [r[0] for r in db.execute('SELECT status FROM batch_items WHERE batch_id=?', (batch_id,))]
    if any(state in {'pending', 'running'} for state in states):
        return
    status = 'interrupted' if 'interrupted' in states else 'cancelled' if 'cancelled' in states else \
        'completed_with_errors' if 'failed' in states else 'completed'
    db.execute('UPDATE batches SET status=?,updated_at=? WHERE id=?', (status, timestamp(), batch_id))


def capture_batch_result(db, record, overview=None, total_rows=0):
    """Called in the terminal run-write transaction, BEFORE ordinary run pruning."""
    found = db.execute('''SELECT i.batch_id,i.id,b.metadata,i.attempts
        FROM batch_items i JOIN batches b ON b.id=i.batch_id
        WHERE i.run_id=? AND i.status='running' ''', (record['id'],)).fetchone()
    if found is None or record['status'] not in {'completed', 'failed', 'cancelled', 'interrupted'}:
        return
    batch_id, item_id, metadata_blob, attempts_blob = found
    metadata = unpack(metadata_blob)
    keys = [v['key'] for v in metadata['variables']]
    frame = record.get('frame') or {}
    storage_failed = any(d.get('code') == 'STORAGE_FAILED' for d in frame.get('diagnostics', []))
    outcome = 'interrupted' if storage_failed else record['status']
    if overview is None:
        saved = db.execute('SELECT overview FROM runs WHERE id=?', (record['id'],)).fetchone()
        overview = unpack(saved[0]) if saved and saved[0] else {'rows': [], 'stride': 1}
    rows = list(overview.get('rows') or [])
    last = db.execute('SELECT data FROM frames WHERE run_id=? ORDER BY idx DESC LIMIT 1',
                      (record['id'],)).fetchone()
    if last:
        rows.append(unpack(last[0]))
    if frame.get('valid'):
        rows.append(frame)
    by_time = {float(row['time_s']): row for row in rows}
    ordered = [by_time[key] for key in sorted(by_time)]
    step = max(1, math.ceil(max(0, len(ordered) - 1) / 1999))
    sampled = ordered[::step]
    if ordered and (not sampled or sampled[-1] is not ordered[-1]):
        sampled.append(ordered[-1])
    curves = {'points': {key: [[row['time_s'], numeric_value(row, key)] for row in sampled] for key in keys},
              'stride': max(1, overview.get('stride', 1)) * step, 'total_rows': total_rows}
    result = {'time_s': frame.get('time_s'), 'values': {key: numeric_value(frame, key) for key in keys},
              'diagnostics': frame.get('diagnostics') or []}
    now = timestamp()
    attempts = unpack(attempts_blob)
    if attempts:
        attempts[-1].update(status=outcome, finished_at=now)
    db.execute('''UPDATE batch_items SET status=?,finished_at=?,attempts=?,result=?,curves=?
                  WHERE batch_id=? AND id=?''',
               (outcome, now, pack(attempts), pack(result), pack(curves), batch_id, item_id))
    db.execute('UPDATE batches SET updated_at=? WHERE id=?', (now, batch_id))
    finish_batch(db, batch_id)


def recover_batches(db):
    """No restart automatically replays simulations or resumes an old process."""
    rows = list(db.execute("SELECT batch_id,id,run_id,attempts FROM batch_items WHERE status='running'"))
    for batch_id, item_id, run_id, attempts_blob in rows:
        saved = db.execute('SELECT record,overview FROM runs WHERE id=?', (run_id,)).fetchone()
        if saved:
            record = unpack(saved[0])
            if record['status'] in {'completed', 'failed', 'cancelled', 'interrupted'}:
                capture_batch_result(db, record, unpack(saved[1]) if saved[1] else None, record.get('total_rows', 0))
                continue
        now = timestamp()
        attempts = unpack(attempts_blob)
        if attempts:
            attempts[-1].update(status='interrupted', finished_at=now)
        db.execute("UPDATE batch_items SET status='interrupted',finished_at=?,attempts=? WHERE batch_id=? AND id=?",
                   (now, pack(attempts), batch_id, item_id))
    db.execute("UPDATE batches SET status='interrupted',updated_at=? WHERE status='running'", (timestamp(),))


class BatchStore:
    def __init__(self, storage: WorkspaceStore):
        self.storage = storage

    def existing(self, project_id, request_key, fingerprint, db=None):
        with (self.storage.transaction() if db is None else nullcontext(db)) as db:
            row = db.execute('SELECT id,fingerprint FROM batches WHERE project_id=? AND request_key=?',
                             (project_id, request_key)).fetchone()
            if row and row[1] != fingerprint:
                raise BatchConflict('同一提交标识不能用于不同的批次内容')
            return row[0] if row else None

    def create(self, project_id, request_key, fingerprint, name, project, preview):
        with self.storage.transaction() as db:
            existing = self.existing(project_id, request_key, fingerprint, db)
            if existing:
                return existing
            identifier, now = uuid.uuid4().hex, timestamp()
            db.execute('''INSERT INTO batches
                (id,project_id,request_key,fingerprint,name,created_at,updated_at,status,snapshot,metadata)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                       (identifier, project_id, request_key, fingerprint, name, now, now, 'ready',
                        pack(project), pack(preview)))
            db.executemany('''INSERT INTO batch_items
                (batch_id,id,ordinal,name,scenario_id,status,attempts) VALUES(?,?,?,?,?,'pending',?)''',
                [(identifier, item['id'], index, item['name'], item['scenario']['id'], pack([]))
                 for index, item in enumerate(preview['items'])])
            return identifier

    def metadata(self, batch_id, db=None):
        with (self.storage.transaction() if db is None else nullcontext(db)) as db:
            row = db.execute('SELECT metadata FROM batches WHERE id=?', (batch_id,)).fetchone()
            if not row:
                raise KeyError(batch_id)
            return unpack(row[0])

    def snapshot(self, batch_id):
        with self.storage.transaction() as db:
            row = db.execute('SELECT snapshot FROM batches WHERE id=?', (batch_id,)).fetchone()
            if not row:
                raise KeyError(batch_id)
            return unpack(row[0])

    def summary(self, batch_id, db=None):
        with (self.storage.transaction() if db is None else nullcontext(db)) as db:
            row = db.execute('''SELECT name,project_id,created_at,updated_at,status,metadata,error
                                FROM batches WHERE id=?''', (batch_id,)).fetchone()
            if row is None:
                raise KeyError(batch_id)
            name, project_id, created, updated, status, metadata_blob, error = row
            source = unpack(metadata_blob)['source']
            counts = Counter(r[0] for r in db.execute('SELECT status FROM batch_items WHERE batch_id=?', (batch_id,)))
            return {'id': batch_id, 'name': name, 'project_id': project_id, 'project_name': source['project_name'],
                    'project_revision': source['revision'], 'snapshot_hash': source['snapshot_hash'],
                    'status': status, 'created_at': created, 'updated_at': updated, 'total': sum(counts.values()),
                    **{state: counts[state] for state in ('completed', 'failed', 'cancelled', 'interrupted')},
                    'error': error}

    def list(self, project_id=None, offset=0, limit=50):
        with self.storage.transaction() as db:
            clause, args = (' WHERE project_id=?', [project_id]) if project_id is not None else ('', [])
            total = db.execute('SELECT COUNT(*) FROM batches' + clause, args).fetchone()[0]
            rows = db.execute('SELECT id FROM batches' + clause + ' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',
                              [*args, limit, offset]).fetchall()
            return {'batches': [self.summary(row[0], db) for row in rows], 'offset': offset, 'total': total}

    def detail(self, batch_id):
        with self.storage.transaction() as db:
            summary, metadata = self.summary(batch_id, db), self.metadata(batch_id, db)
            previews = {item['id']: item for item in metadata['items']}
            items = []
            for row in db.execute('''SELECT id,name,scenario_id,status,run_id,started_at,finished_at,attempts,result
                                    FROM batch_items WHERE batch_id=? ORDER BY ordinal''', (batch_id,)):
                item_id, name, scenario, status, run_id, started, finished, attempts, result = row
                info = unpack(result) if result else {}
                items.append({'id': item_id, 'name': name, 'scenario_id': scenario, 'status': status,
                    'run_id': run_id, 'started_at': started, 'finished_at': finished, 'attempts': unpack(attempts),
                    'parameter_value': previews[item_id].get('parameter_value'),
                    'parameter_unit': previews[item_id].get('parameter_unit'),
                    'time_s': info.get('time_s'), 'values': info.get('values', {}),
                    'diagnostics': info.get('diagnostics', [])})
            return {**summary, 'source': metadata['source'], 'options': metadata['options'],
                    'variables': metadata['variables'], 'items': items}

    def curve(self, batch_id, item_id, key):
        with self.storage.transaction() as db:
            metadata = self.metadata(batch_id, db)
            variable = next((v for v in metadata['variables'] if v['key'] == key), None)
            if variable is None:
                raise ValueError('该变量不在本批次冻结的观察列表中')
            row = db.execute('SELECT status,curves FROM batch_items WHERE batch_id=? AND id=?',
                             (batch_id, item_id)).fetchone()
            if row is None:
                raise KeyError(item_id)
            result = unpack(row[1]) if row[1] else {'points': {}, 'stride': 1, 'total_rows': 0}
            return {'batch_id': batch_id, 'item_id': item_id, 'status': row[0], 'variable': variable,
                    'points': result['points'].get(key, []), 'stride': result['stride'],
                    'total_rows': result['total_rows']}

    def start(self, batch_id):
        with self.storage.transaction() as db:
            current = self.summary(batch_id, db)
            if current['status'] == 'running':
                return False
            active = db.execute("SELECT id FROM batches WHERE status='running' AND id<>?", (batch_id,)).fetchone()
            if active:
                raise BatchConflict('已有活动批次，请等待结束或取消其剩余工况')
            count = db.execute("SELECT COUNT(*) FROM batch_items WHERE batch_id=? AND status IN ('pending','interrupted')",
                               (batch_id,)).fetchone()[0]
            if not count:
                raise BatchConflict('本批次没有待运行或中断的工况')
            db.execute("UPDATE batch_items SET status='pending' WHERE batch_id=? AND status='interrupted'", (batch_id,))
            db.execute("UPDATE batches SET status='running',cancel_requested=0,error=NULL,updated_at=? WHERE id=?",
                       (timestamp(), batch_id))
            return True

    def begin_next(self, batch_id):
        with self.storage.transaction() as db:
            if self.summary(batch_id, db)['status'] != 'running':
                return None
            row = db.execute("""SELECT id,scenario_id,attempts FROM batch_items
                WHERE batch_id=? AND status='pending' ORDER BY ordinal LIMIT 1""", (batch_id,)).fetchone()
            if not row:
                finish_batch(db, batch_id)
                return None
            item_id, scenario_id, attempts_blob = row
            run_id, now = uuid.uuid4().hex, timestamp()
            attempts = unpack(attempts_blob)
            attempts.append({'run_id': run_id, 'status': 'running', 'started_at': now, 'finished_at': None})
            db.execute("""UPDATE batch_items SET status='running',run_id=?,started_at=?,finished_at=NULL,
                          attempts=?,result=NULL,curves=NULL WHERE batch_id=? AND id=?""",
                       (run_id, now, pack(attempts), batch_id, item_id))
            db.execute('UPDATE batches SET updated_at=? WHERE id=?', (now, batch_id))
            return item_id, scenario_id, run_id

    def item_state(self, batch_id, item_id):
        with self.storage.transaction() as db:
            row = db.execute('SELECT status FROM batch_items WHERE batch_id=? AND id=?', (batch_id, item_id)).fetchone()
            if row is None:
                raise KeyError(item_id)
            return row[0]

    def cancel_remaining(self, batch_id):
        with self.storage.transaction() as db:
            self.summary(batch_id, db)
            now = timestamp()
            db.execute("UPDATE batch_items SET status='cancelled',finished_at=? WHERE batch_id=? AND status IN ('pending','interrupted')",
                       (now, batch_id))
            db.execute('UPDATE batches SET cancel_requested=1,updated_at=? WHERE id=?', (now, batch_id))
            active = db.execute("SELECT COUNT(*) FROM batch_items WHERE batch_id=? AND status='running'", (batch_id,)).fetchone()[0]
            if not active:
                current = self.summary(batch_id, db)
                if current['cancelled']:
                    db.execute("UPDATE batches SET status='cancelled' WHERE id=?", (batch_id,))

    def capture(self, record, overview, total_rows):
        with self.storage.transaction() as db:
            capture_batch_result(db, record, overview, total_rows)

    def interrupt(self, batch_id, error=None):
        with self.storage.transaction() as db:
            current = self.summary(batch_id, db)
            if current['status'] != 'running' and not (error and current['status'] == 'interrupted'):
                return
            now = timestamp()
            for item_id, attempts_blob in db.execute(
                    "SELECT id,attempts FROM batch_items WHERE batch_id=? AND status='running'", (batch_id,)).fetchall():
                attempts = unpack(attempts_blob)
                if attempts:
                    attempts[-1].update(status='interrupted', finished_at=now)
                result = {'time_s': None, 'values': {}, 'diagnostics': [
                    {'code': 'BATCH_INTERRUPTED', 'severity': 'error', 'message': error or '服务结束，工况可从冻结输入重新运行'}]}
                db.execute("""UPDATE batch_items SET status='interrupted',finished_at=?,attempts=?,
                    result=COALESCE(result,?) WHERE batch_id=? AND id=?""",
                    (now, pack(attempts), pack(result), batch_id, item_id))
            db.execute('UPDATE batches SET status=?,error=?,updated_at=? WHERE id=?',
                       ('failed' if error else 'interrupted', error, now, batch_id))

    def delete(self, batch_id):
        with self.storage.transaction() as db:
            if self.summary(batch_id, db)['status'] == 'running':
                raise BatchConflict('请先结束活动批次，再删除其结果')
            if not db.execute('DELETE FROM batches WHERE id=?', (batch_id,)).rowcount:
                raise KeyError(batch_id)
            return {'id': batch_id, 'deleted': True}
