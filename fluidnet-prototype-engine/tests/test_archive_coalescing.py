"""Archive wakeups batch new frames but never delay a command or shutdown flush."""
from collections import deque
from threading import Condition, Event
from types import SimpleNamespace

import pytest

import fn_engine.jobs as jobs


def writer_fixture(monkeypatch):
    clock = SimpleNamespace(now=0.)
    monkeypatch.setattr(jobs, 'time', SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(jobs, 'ARCHIVE_COALESCE_S', .01)
    writer = jobs._ArchiveWriter.__new__(jobs._ArchiveWriter)
    writer.manager = SimpleNamespace(wake=Condition())
    writer.closed = False
    writer.items = {}
    wakeups = deque()
    waits, writes = [], []

    class Notifications:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def wait(self, timeout=None):
            assert wakeups, 'Writer waited after the expected flush boundary'
            waits.append(timeout)
            elapsed, action = wakeups.popleft()
            clock.now += elapsed
            action()

    def save_run(record, rows, total_rows, window, overview):
        writes.append((clock.now, record['id'], list(rows), total_rows))
        writer.closed = True  # Drain every queued item, then finish this synchronous run.

    writer.condition = Notifications()
    writer.storage = SimpleNamespace(save_run=save_run)
    return writer, wakeups, waits, writes


def pending(run_id, rows, waiters=()):
    record = {'id': run_id}
    return {'job': SimpleNamespace(record=record), 'record': record, 'rows': list(rows),
            'total_rows': len(rows), 'window': 2001, 'overview': None, 'waiters': list(waiters)}


def test_new_frame_notifications_share_the_original_coalescing_deadline(monkeypatch):
    writer, wakeups, waits, writes = writer_fixture(monkeypatch)
    item = pending('run', [(0, {'sequence': 0})])
    writer.items['run'] = item

    def append():
        index = item['total_rows']
        item['rows'].append((index, {'sequence': index}))
        item['total_rows'] += 1

    wakeups.extend([(.002, append), (.002, append), (.006, lambda: None)])
    writer._run()
    assert waits == pytest.approx([.01, .008, .006])
    assert len(writes) == 1
    at, run_id, rows, total = writes[0]
    assert at == pytest.approx(.01) and run_id == 'run' and total == 3
    assert [index for index, _ in rows] == [0, 1, 2]


def test_write_through_wakes_the_writer_and_precedes_ordinary_frames(monkeypatch):
    writer, wakeups, waits, writes = writer_fixture(monkeypatch)
    writer.items['ordinary'] = pending('ordinary', [(0, {})])
    receipt, box = Event(), {}
    wakeups.append((.002, lambda: writer.items.update(command=pending('command', [(0, {})], [(receipt, box)]))))
    writer._run()
    assert waits == [.01]
    assert [(at, run_id) for at, run_id, _, _ in writes] == [(.002, 'command'), (.002, 'ordinary')]
    assert receipt.is_set() and box['persisted'] == 1


def test_shutdown_interrupts_coalescing_and_flushes_pending_rows(monkeypatch):
    writer, wakeups, waits, writes = writer_fixture(monkeypatch)
    writer.items['run'] = pending('run', [(0, {}), (1, {})])
    wakeups.append((.002, lambda: setattr(writer, 'closed', True)))
    writer._run()
    assert waits == [.01]
    assert len(writes) == 1 and writes[0][0] == .002 and writes[0][3] == 2
