"""PID observations retain the frozen measurement/actuator units in air reports."""
import csv
from io import StringIO

from fastapi.testclient import TestClient
import pytest

from fn_engine.air_examples import air_example
from fn_engine.air_variables import collect_air_variables
from fn_engine.api import create_app
from fn_engine.batches import observation_choices
from fn_engine.models import PIDController


def controlled_coil():
    project = air_example('air-coil-wet')
    project.controllers = [PIDController(
        id='Supply-Control', measurement='Coil.out0.temperature_k',
        instance_id='Coil', parameter_id='bypass_factor', setpoint=292.15,
        kp=.01, ki=.0001, sample_s=1., minimum=.01, maximum=.9)]
    return project


def test_pid_metadata_uses_actual_frozen_units_and_ids():
    project = controlled_coil()
    definition = next(m for m in project.modules if m.id == 'cooling_coil')
    target = next(p for p in definition.parameters if p.id == 'bypass_factor')
    target.unit = target.unit.model_copy(update={'display_unit': '%', 'display_scale': .01})
    catalog = {v.key: v for v in collect_air_variables(project)}
    temperature = catalog['controller.Supply-Control.setpoint']
    assert temperature.unit.from_canonical(292.15) == pytest.approx(19.)
    assert temperature.unit == catalog['Coil.out0.temperature_k'].unit
    assert temperature.available_in == ['dynamic'] and temperature.writable
    assert catalog['controller.Supply-Control.measurement'].nullable
    output = catalog['controller.Supply-Control.output']
    assert output.unit.from_canonical(.35) == pytest.approx(35.)
    assert not output.writable
    assert catalog['controller.Supply-Control.integral'].unit == output.unit
    manual = catalog['controller.Supply-Control.manual_output']
    assert manual.unit == output.unit and manual.unit.from_canonical(.35) == pytest.approx(35.)
    assert manual.writable and manual.nullable and manual.value_type == 'number'
    assert manual.available_in == ['dynamic']
    assert catalog['controller.Supply-Control.mode'].value_type == 'text'
    choices = {v.key: v for v in observation_choices(project)}
    assert choices['controller.Supply-Control.setpoint'].unit == temperature.unit
    assert choices['controller.Supply-Control.output'].unit == output.unit
    assert choices['controller.Supply-Control.manual_output'].unit == output.unit
    assert 'controller.Supply-Control.mode' not in choices


def test_pid_report_and_restart_use_frozen_controller_catalog(tmp_path, monkeypatch):
    project = controlled_coil()
    with TestClient(create_app(data_root=tmp_path)) as client:
        created = client.post('/api/v1/runs', json={
            'project': project.model_dump(mode='json'), 'mode': 'dynamic', 'duration_s': 1., 'dt_s': 1.})
        assert created.status_code == 201, created.text
        assert created.json()['status'] == 'completed', created.text
        run_id = created.json()['run_id']
        record = client.get('/api/v1/runs/' + run_id).json()
        metadata = record['air_metadata']
        observed = record['frame']['variables']['controller.Supply-Control.output']
        # A later edit must not change either the saved catalog or report values.
        project.controllers[0].id = 'Renamed'
        project.controllers[0].setpoint = 298.15
        from fn_engine import air_variables
        monkeypatch.setattr(air_variables, 'collect_air_variables',
                            lambda *_: pytest.fail('reports must read their frozen catalog'))
        response = client.get(f'/api/v1/runs/{run_id}/report.csv')
        assert response.status_code == 200, response.text
        rows = list(csv.DictReader(StringIO(response.content.decode('utf-8-sig'))))
        by_key = {r['变量键']: r for r in rows if float(r['时间(s)']) == 1.}
        target = by_key['controller.Supply-Control.setpoint']
        assert target['显示单位'] == '°C'
        assert float(target['显示数值']) == pytest.approx(19.)
        assert float(by_key['controller.Supply-Control.output']['规范数值']) == pytest.approx(observed)
        html = client.get(f'/api/v1/runs/{run_id}/report.html').text
        assert 'PID Supply-Control · 设定值' in html and 'Renamed' not in html
    with TestClient(create_app(data_root=tmp_path)) as client:
        assert client.get('/api/v1/runs/' + run_id).json()['air_metadata'] == metadata
        assert 'controller.Supply-Control.setpoint' in client.get(f'/api/v1/runs/{run_id}/report.html').text
