"""External batch commands must not leave partial inputs after a Worker RPC fault."""
from copy import deepcopy
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.compiler import compile_project
from fn_engine.models import PIDController
from fn_engine.packages import load_module_package
from fn_engine.runtime import RuntimeErrorBase
from fn_engine.simulation import SimulationSession
from test_module_execution_network import network_for

ROOT = Path(__file__).resolve().parents[1]


def network(batch=False, parallelism=1):
    definition = load_module_package(ROOT / 'modules/programmable_valve')
    for parameter in definition.parameters:
        parameter.runtime = True
    definition.content_hash = definition.definition_hash = None
    return network_for(definition, 2, batch=batch, parallelism=parallelism)


@pytest.mark.parametrize('batch,parallelism', [(False, 1), (True, 1), (True, 2)])
@pytest.mark.parametrize('command', ['write', 'composite-set'])
def test_second_worker_lost_ack_restores_all_inputs_and_preserves_state(monkeypatch, batch, parallelism, command):
    session = SimulationSession(network(batch, parallelism), .2, .1)
    try:
        session.initialize()
        before = deepcopy(session.network.parameters)
        states = {key: deepcopy(runner.state) for key, runner in session.runners.items()}
        revisions = {key: runner.state_revision for key, runner in session.runners.items()}
        original = session.runners['D2'].update_parameters
        calls = []

        def lost_ack(parameters):
            original(parameters)
            calls.append(deepcopy(parameters))
            if len(calls) == 1:
                raise RuntimeErrorBase('injected lost parameter acknowledgement')

        monkeypatch.setattr(session.runners['D2'], 'update_parameters', lost_ack)
        with pytest.raises(RuntimeErrorBase, match='lost parameter acknowledgement'):
            if command == 'write':
                session.write_variables({'D1.param.opening_ratio': .3, 'D2.param.opening_ratio': .3})
            else:
                session.network.composite_maps = {'parameters': {
                    'Group.param.opening_ratio': [('D1', 'opening_ratio'), ('D2', 'opening_ratio')]}}
                session.set_parameter('Group', 'opening_ratio', .3)
        assert session.network.parameters == before
        assert session.revision == 0 and session.time == 0
        assert len(calls) == 2 and calls[1] == before['D2']
        assert {key: runner.state for key, runner in session.runners.items()} == states
        assert {key: runner.state_revision for key, runner in session.runners.items()} == revisions
        # Continuing exercises actual Worker inputs, not only the parent copies.
        frame = session.advance()
        for key in ('D1', 'D2'):
            assert frame.variables[f'{key}.opening_ratio'] == before[key]['opening_ratio']
        assert session.revision == 0
    finally:
        session.close()


def test_physical_side_effect_failure_restores_valves_and_controller_config(monkeypatch):
    from test_thermal import project
    p = project([('B1', 'source', {'pressure_pa': 250000}), ('V1', 'valve', {}), ('V2', 'valve', {}),
                 ('B2', 'source', {'pressure_pa': 120000})],
                [('B1:out0', 'V1:in0'), ('V1:out0', 'V2:in0'), ('V2:out0', 'B2:out0')])
    p.controllers = [PIDController(id='pid1', instance_id='V1', parameter_id='opening_ratio',
        measurement='V1.mass_flow_kg_s', setpoint=1., kp=.01, minimum=0., maximum=1.)]
    session = SimulationSession(compile_project(p), .2, .1)
    try:
        session.initialize()
        before = deepcopy(session.network.parameters)
        controllers = deepcopy(session.controllers)
        closed = [b.closed for b in session.network.branches]
        original = session.apply_parameter_changes

        def reject_after_apply(key, parameters):
            original(key, parameters)
            if key == 'V2':
                raise ValueError('injected physical effect failure')

        monkeypatch.setattr(session, 'apply_parameter_changes', reject_after_apply)
        with pytest.raises(ValueError, match='physical effect failure'):
            session.write_variables({'V2.param.opening_ratio': 0., 'controller.pid1.setpoint': 2.})
        assert session.network.parameters == before
        assert [b.closed for b in session.network.branches] == closed
        assert session.controllers == controllers
        assert session.revision == 0
    finally:
        session.close()


def test_unrecoverable_parameter_rpc_rejects_command_and_stops_background_run(monkeypatch, tmp_path):
    from fn_engine.runtime import WorkerProcess
    original = WorkerProcess.update_parameters
    calls = []

    def unavailable(self, parameters):
        if self.execution.instance_id == 'D2':
            calls.append(parameters)
            raise RuntimeErrorBase('injected unavailable parameter Worker')
        return original(self, parameters)

    monkeypatch.setattr(WorkerProcess, 'update_parameters', unavailable)
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/runs?background=true', json={
            'project': network().project.model_dump(mode='json'), 'mode': 'dynamic',
            'duration_s': 1., 'dt_s': .1, 'start_paused': True})
        assert response.status_code == 202, response.text
        rid = response.json()['run_id']
        deadline = time.monotonic() + 20
        while client.get('/api/v1/runs/' + rid).json()['status'] != 'paused':
            assert time.monotonic() < deadline
            time.sleep(.025)
        first = client.post(f'/api/v1/runs/{rid}/variables', json={'wait_s': 5, 'values': {
            'D1.param.opening_ratio': .6}})
        assert first.json()['command_status'] == 'applied'
        client.post(f'/api/v1/runs/{rid}/command', json={'action': 'step'})
        deadline = time.monotonic() + 20
        while True:
            advanced = client.get('/api/v1/runs/' + rid).json()
            if advanced['status'] == 'paused' and advanced['frame']['time_s'] == .1:
                break
            assert time.monotonic() < deadline
            time.sleep(.025)
        before = client.get('/api/v1/runs/' + rid).json()['frame']
        receipt = client.post(f'/api/v1/runs/{rid}/variables', json={'wait_s': 5, 'values': {
            'D1.param.opening_ratio': .3, 'D2.param.opening_ratio': .4}})
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()['command_status'] == 'rejected'
        deadline = time.monotonic() + 20
        while True:
            record = client.get('/api/v1/runs/' + rid).json()
            if record['status'] == 'failed':
                break
            assert time.monotonic() < deadline
            time.sleep(.025)
        assert len(calls) == 2
        assert record['frame']['time_s'] == before['time_s']
        assert record['frame']['parameter_revision'] == before['parameter_revision'] == 1
        history = client.get(f'/api/v1/runs/{rid}/history').json()['rows']
        assert history and history[-1]['parameter_revision'] == 1
        for key in ('D1', 'D2'):
            assert record['frame']['variables'][f'{key}.param.opening_ratio'] == before['variables'][f'{key}.param.opening_ratio']
            assert history[-1]['variables'][f'{key}.param.opening_ratio'] == before['variables'][f'{key}.param.opening_ratio']
        assert any(d['code'] == 'MODULE_WORKER_IO_ERROR' for d in record['frame']['diagnostics'])
        assert client.post(f'/api/v1/runs/{rid}/command', json={'action': 'resume'}).status_code == 409
