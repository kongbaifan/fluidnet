"""New equipment must enter the same network, accepted-state ledger and frozen reports."""
import csv
from io import StringIO
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from fn_engine.api import create_app
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.refrigeration.modular_examples import modular_air_cooled_example, assembly_recipe
from fn_engine.sessions import create_session


def test_horizontal_air_cooled_network_closes_design_and_independent_energy_ledger():
    session = create_session(compile_project(modular_air_cooled_example()), 60., 10.)
    try:
        first = session.initialize().variables
        while not session.done:
            session.advance()
        frame = session.snapshot()
        last = frame.variables
        assert last['Room.state.temperature_k'] == pytest.approx(255.15, abs=1e-6)
        assert last['Low.state.level_height_ratio'] != pytest.approx(last['Low.state.level_ratio'])
        assert last['Low.state.level_m'] == pytest.approx(.8*last['Low.state.level_height_ratio'])
        assert last['Condenser.heat_rejection_w'] == pytest.approx(
            5.*1006.*(last['Condenser.air_outlet_temperature_k']-293.15), abs=1e-7)
        stored = lambda v: sum(v[i+'.state.internal_energy_j'] for i in ('Low','High')) + 2e6*v['Room.state.temperature_k']
        boundary = last['Room.state.external_energy_j'] + last['Cooler.state.fan_energy_j']
        boundary += last['Pump.state.electric_energy_j'] + last['Compressor.state.electric_energy_j']*.92
        boundary -= last['Condenser.state.heat_rejected_j']
        assert stored(last)-stored(first) == pytest.approx(boundary, abs=.01)
        assert last['Condenser.state.fan_energy_j'] == pytest.approx(300.*60.)
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
    finally:
        session.close()


def test_runtime_fan_change_affects_heat_and_counters_only_on_accepted_steps():
    session = create_session(compile_project(modular_air_cooled_example()), 60., 10.)
    try:
        session.initialize()
        session.advance()
        old = session.snapshot().variables
        session.set_parameter('Condenser', 'fan_ratio', .5)
        candidate = session.snapshot().variables
        assert candidate['Condenser.fan_power_w'] == pytest.approx(37.5)
        assert candidate['Condenser.heat_rejection_w'] < old['Condenser.heat_rejection_w']
        assert candidate['Condenser.state.fan_energy_j'] == old['Condenser.state.fan_energy_j']
        with pytest.raises(CompilationError):
            session.set_parameter('Condenser', 'fan_ratio', 1.1)
        assert session.snapshot().variables['Condenser.param.fan_ratio'] == .5
        session.advance()
        assert session.snapshot().variables['Condenser.state.fan_energy_j'] == pytest.approx(3375.)
        session.set_parameter('Condenser', 'fan_ratio', 0.)
        off = session.snapshot().variables
        assert off['Condenser.air_outlet_temperature_k'] is None
        assert off['Condenser.heat_rejection_w'] == 0.
        session.advance()
        assert session.snapshot().variables['High.state.pressure_pa'] > old['High.state.pressure_pa']
    finally:
        session.close()


def test_equipment_report_and_restart_keep_frozen_geometry_and_air_model(tmp_path):
    with TestClient(create_app(data_root=tmp_path)) as client:
        project = client.get('/api/v1/examples/refrigeration-modular-air-cooled').json()
        response = client.post('/api/v1/runs', json={'project':project,'mode':'dynamic','duration_s':20.,'dt_s':10.})
        assert response.status_code == 201 and response.json()['status'] == 'completed', response.text
        rid = response.json()['run_id']
        record = client.get(f'/api/v1/runs/{rid}').json()
        html = client.get(f'/api/v1/runs/{rid}/report.html').text
        assert '扩展设备末帧结果' in html and '风机电功率' in html and '液位高度' in html
        csv_response = client.get(f'/api/v1/runs/{rid}/report.csv')
        assert csv_response.status_code == 200
        rows = list(csv.reader(StringIO(csv_response.content.decode('utf-8-sig'))))
        assert any('Low.state.level_height_ratio' in cell for row in rows for cell in row)
        assert any('Condenser.air_outlet_temperature_k' in cell for row in rows for cell in row)
    with TestClient(create_app(data_root=tmp_path)) as client:
        restored = client.get(f'/api/v1/runs/{rid}').json()
        assert restored['frame']['variables'] == record['frame']['variables']
        assert client.get(f'/api/v1/runs/{rid}/report.html').text == html


def test_extension_recipe_and_project_are_reproducible():
    root = Path(__file__).resolve().parents[1]/'examples/refrigeration-modular'
    assert json.loads((root/'air-cooled.recipe.json').read_text(encoding='utf-8')) == assembly_recipe(air_cooled=True)
    assert json.loads((root/'air-cooled.project.json').read_text(encoding='utf-8')) == modular_air_cooled_example().model_dump(mode='json')
