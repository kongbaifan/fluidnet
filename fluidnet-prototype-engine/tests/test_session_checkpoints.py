"""Continued physical/control histories match an uninterrupted calculation."""
from copy import deepcopy
import time

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.checkpoints import capture, restore, validate
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.examples import pid_example
from fn_engine.refrigeration.examples import ideal_room_example, room_example
from fn_engine.refrigeration.forward_examples import coupled_buffer_example
from fn_engine.refrigeration.modular_examples import modular_room_example
from fn_engine.sessions import create_session


@pytest.mark.parametrize('factory', [ideal_room_example, room_example, modular_room_example,
                                    coupled_buffer_example, lambda: pid_example('level')])
def test_all_physical_domains_continue_with_the_same_inventory_and_control_clock(factory):
    original = create_session(compile_project(factory()), 2., .2, keep=8)
    resumed = None
    try:
        original.initialize()
        original.advance()
        packet = capture(original)
        resumed = restore(packet)
        assert resumed.time == original.time
        for _ in range(2):
            a, b = original.advance(), resumed.advance()
            assert a.time_s == b.time_s
            assert a.parameter_revision == b.parameter_revision
            for key, value in a.variables.items():
                if ('.state.' in key or key.startswith('controller.')) and isinstance(value, (int, float)):
                    assert b.variables[key] == pytest.approx(value, rel=1e-8, abs=1e-7), key
            assert abs(b.metrics.get('energy_residual_j', 0.)) < .05
    finally:
        original.close()
        if resumed is not None:
            resumed.close()


def wait_status(client, run_id, status):
    deadline = time.monotonic() + 10.
    while time.monotonic() < deadline:
        record = client.get(f'/api/v1/runs/{run_id}').json()
        if record.get('status') == status:
            return record
        if record.get('status') == 'failed':
            pytest.fail(str(record.get('frame')))
        time.sleep(.01)
    pytest.fail(f'run did not reach {status}')


def test_archive_restart_resume_restores_inventory_instead_of_reinitializing(tmp_path):
    source_project = modular_room_example()
    next(i for i in source_project.instances if i.id == 'Low').draft_parameters = {'temperature_k': 333.15}
    payload = {'project': source_project.model_dump(mode='json'), 'mode': 'dynamic',
               'duration_s': 2., 'dt_s': .2, 'start_paused': True}
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/runs?background=true', json=payload)
        assert response.status_code == 202
        source = response.json()['run_id']
        wait_status(client, source, 'paused')
        for count in range(2):
            client.post(f'/api/v1/runs/{source}/command', json={'action': 'step', 'command_id': f'prime-{count}'})
            deadline = time.monotonic() + 10.
            while time.monotonic() < deadline:
                before = wait_status(client, source, 'paused')
                if before['frame']['time_s'] >= (count + 1) * .2 - 1e-9:
                    break
                time.sleep(.01)
        assert before['checkpoint_available'] and before['checkpoint_time_s'] == pytest.approx(.4)
        assert 'checkpoint' not in before
    with TestClient(create_app(data_root=tmp_path)) as client:
        old = client.get(f'/api/v1/runs/{source}').json()
        assert old['status'] == 'interrupted'
        frozen = client.get(f'/api/v1/runs/{source}/checkpoint-project')
        assert frozen.status_code == 200, frozen.text
        assert {i['id'] for i in frozen.json()['instances']} == {i.id for i in modular_room_example().instances}
        low = next(i for i in frozen.json()['instances'] if i['id'] == 'Low')
        assert low['parameters']['temperature_k'] == 248.15
        assert low['draft_parameters'] == low['parameters']
        response = client.post(f'/api/v1/runs/{source}/resume', json={})
        assert response.status_code == 202, response.text
        child = response.json()['run_id']
        resumed = wait_status(client, child, 'paused')
        assert resumed['frame']['time_s'] == pytest.approx(.4)
        for key in ('Low.state.mass_kg', 'High.state.internal_energy_j', 'Room.state.temperature_k'):
            assert resumed['frame']['variables'][key] == before['frame']['variables'][key]
        client.post(f'/api/v1/runs/{child}/command', json={'action': 'step'})
        deadline = time.monotonic() + 10.
        while time.monotonic() < deadline:
            resumed = wait_status(client, child, 'paused')
            if resumed['frame']['time_s'] > .4:
                break
            time.sleep(.01)
        assert resumed['frame']['time_s'] == pytest.approx(.6)
        assert abs(resumed['frame']['metrics']['energy_residual_j']) < .05


def test_checksum_rejects_modified_state_and_a_completed_clock_requires_extension():
    original = create_session(compile_project(ideal_room_example()), .2, .2, keep=8)
    resumed = None
    try:
        original.initialize()
        original.advance()
        packet = capture(original)
        changed = deepcopy(packet)
        changed['parameters'][next(iter(changed['parameters']))]['temperature_k'] = 1.
        with pytest.raises(CompilationError, match='完整性'):
            validate(changed)
        with pytest.raises(CompilationError) as error:
            restore(packet)
        assert error.value.diagnostic.code == 'CHECKPOINT_DURATION'
        resumed = restore(packet, duration_s=.6)
        assert resumed.advance().time_s == pytest.approx(.4)
    finally:
        original.close()
        if resumed is not None:
            resumed.close()


def test_numerical_dependency_version_is_part_of_checkpoint_identity(monkeypatch):
    import fn_engine.checkpoints as checkpoints
    checkpoints.kernel_fingerprint.cache_clear()
    try:
        original = checkpoints.kernel_fingerprint()
        installed_version = checkpoints.version
        monkeypatch.setattr(checkpoints, 'version', lambda name:
            installed_version(name) + ('-changed' if name == 'CoolProp' else ''))
        checkpoints.kernel_fingerprint.cache_clear()
        assert checkpoints.kernel_fingerprint() != original
    finally:
        checkpoints.kernel_fingerprint.cache_clear()


def test_resumed_project_copy_uses_accepted_controller_settings():
    from fn_engine.checkpoints import accepted_project
    session = create_session(compile_project(pid_example('level')), 2., .2)
    try:
        session.initialize()
        session.advance()
        cid = next(iter(session.controllers))
        target = session.controllers[cid].config.setpoint + .1
        session.update_controller(cid, 'setpoint', target)
        project = accepted_project(capture(session))
        assert next(c for c in project.controllers if c.id == cid).setpoint == target
    finally:
        session.close()
