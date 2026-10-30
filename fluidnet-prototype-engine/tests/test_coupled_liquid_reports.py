"""Coupled reports retain liquid-author definitions and accepted results across restarts."""
from copy import deepcopy
import csv
import io

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app, shape_history
from fn_engine.compiler import compile_project
from fn_engine.models import RunFrame, RunRequest
from fn_engine.module_templates import create_template
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example
from fn_engine.refrigeration.report import station_series_keys
from fn_engine.runtime import WorkerProcess
from test_continuous import wait


AUTHOR = 'Secondary-Valve-27'


def author_project(module=None):
    project = thermal_coupling_example('Water')
    module = module or create_template('managed_state', 'report_liquid_author', '报告作者水阀')
    project.modules.append(module)
    valve = next(instance for instance in project.instances if instance.id == 'WV1')
    valve.id, valve.module_id = AUTHOR, module.id
    for edge in project.connections:
        for endpoint in (edge.source, edge.target):
            if endpoint.instance_id == 'WV1':
                endpoint.instance_id = AUTHOR
    for scenario in project.scenarios:
        if 'WV1' in scenario.overrides:
            scenario.overrides[AUTHOR] = scenario.overrides.pop('WV1')
    return project


def publish(client, module, previous):
    response = client.post('/api/v1/modules/versions', json={
        'module': module.model_dump(mode='json'), 'expected_latest_version': previous})
    assert response.status_code == 201, response.text
    return type(module).model_validate(response.json()['module'])


def test_coupled_liquid_reports_use_frozen_version_and_no_worker_after_restart(tmp_path, monkeypatch):
    config = {'data_root': tmp_path / 'data', 'module_storage_root': tmp_path / 'modules'}
    with TestClient(create_app(**config)) as client:
        original = publish(client, create_template('managed_state', 'report_liquid_author', '报告作者水阀'), 0)
        project = author_project(original)
        submitted = client.post('/api/v1/runs?background=true', json={
            'project': project.model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': .2, 'dt_s': .1})
        assert submitted.status_code == 202, submitted.text
        run_id = submitted.json()['run_id']
        record = wait(client, run_id, lambda item: item['status'] in {'completed', 'failed'})
        assert record['status'] == 'completed', record
        frame = deepcopy(record['frame'])
        assert frame['variables'][AUTHOR + '.state.commit_count'] == 2
        assert frame['variables'][AUTHOR + '.state.transferred_mass_kg'] > 0
        changed = original.model_copy(deep=True)
        changed.source['runtime'] = changed.source['runtime'].replace('count + 1', 'count + 2')
        latest = publish(client, changed, 1)
        assert latest.definition_hash != original.definition_hash
        monkeypatch.setattr(WorkerProcess, '__init__', lambda *args, **kwargs: pytest.fail('report executed author code'))
        path = '/api/v1/runs/' + run_id
        response = client.get(path + '/report.html')
        assert response.status_code == 200, response.text
        report = response.text
        assert '制冷站与液体热耦合运行报告' in report
        assert original.definition_hash in report and latest.definition_hash not in report
        assert AUTHOR in report and 'WV1' not in report
        assert AUTHOR + '.density_kg_m3' in report
        assert AUTHOR + '.mass_flow_kg_s' in report
        assert AUTHOR + '.pressure_drop_pa' in report
        assert AUTHOR + '.state.transferred_mass_kg' in report
        assert '累计通过质量（平台积分）' in report
        assert 'HX_W.ch0' in report
        response = client.get(path + '/report.csv')
        assert response.status_code == 200, response.text
        report_csv = response.text
        rows = list(csv.DictReader(io.StringIO(report_csv.lstrip('\ufeff'))))
        assert len(rows) == 3
        assert float(rows[-1][AUTHOR + '.state.commit_count [1]']) == 2
        assert float(rows[-1][AUTHOR + '.state.transferred_mass_kg [kg]']) == pytest.approx(
            frame['variables'][AUTHOR + '.state.transferred_mass_kg'])
        assert float(rows[-1][AUTHOR + '.density_kg_m3 [kg/m³]']) > 0
        for key, unit in [('mass_flow_kg_s', 'kg/s'), ('pressure_drop_pa', 'Pa')]:
            assert float(rows[-1][f'{AUTHOR}.{key} [{unit}]']) == pytest.approx(frame['variables'][f'{AUTHOR}.{key}'])
        assert float(rows[-1]['coupling.HX1.state.heat_energy_j [J]']) > 0
    with TestClient(create_app(**config)) as client:
        assert client.get(path).json()['frame'] == frame
        assert client.get(path + '/report.html').text == report
        assert client.get(path + '/report.csv').text == report_csv


def test_sync_trend_history_retains_coupled_author_derived_fields_and_platform_ledger():
    project = author_project()
    network = compile_project(project)
    keys = dict(station_series_keys(network))
    assert not network.refrigeration_modules
    assert keys[AUTHOR + '.mass_flow_kg_s'] == 'kg/s'
    assert keys[AUTHOR + '.pressure_drop_pa'] == 'Pa'
    assert keys[AUTHOR + '.state.transferred_mass_kg'] == 'kg'
    wanted = {AUTHOR + '.density_kg_m3': 998., AUTHOR + '.opening_ratio': .8,
              AUTHOR + '.state.transferred_mass_kg': 1.2, 'coupling.HX1.heat_w': 2000.}
    frames = [RunFrame(status='converged', valid=True, time_s=float(index),
                       variables={**wanted, 'unobserved.output': 123.}) for index in range(61)]
    shape_history(frames, RunRequest(project=project, mode='dynamic', duration_s=60., dt_s=1., history='trend'),
                  project, network)
    assert not frames[1].full
    assert 'unobserved.output' not in frames[1].variables
    assert frames[1].variables == wanted


def test_liquid_host_report_units_override_conflicting_author_declarations():
    project = author_project()
    module = project.modules[-1]
    temperature = next(variable for definition in project.modules for variable in definition.variables
                       if variable.unit and variable.unit.canonical_unit == 'K')
    for key in ['mass_flow_kg_s', 'pressure_drop_pa', 'state.transferred_mass_kg']:
        module.variables.append(temperature.model_copy(deep=True, update={'id': key, 'label': '错误温度标记', 'source': 'derived'}))
    keys = dict(station_series_keys(compile_project(project)))
    assert keys[AUTHOR + '.mass_flow_kg_s'] == 'kg/s'
    assert keys[AUTHOR + '.pressure_drop_pa'] == 'Pa'
    assert keys[AUTHOR + '.state.transferred_mass_kg'] == 'kg'
