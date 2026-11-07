import csv
from io import StringIO
from unittest.mock import patch
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.regulating_valves import example
from fn_engine.buffer_example import buffer_example
from fn_engine.equipment_report import csv_report


def test_fluid_equipment_report_reads_frozen_units_without_recompile_after_restart(tmp_path):
    for project in (example(), buffer_example()):
        with TestClient(create_app(data_root=tmp_path)) as client:
            response=client.post('/api/v1/runs',json={'project':project.model_dump(mode='json'),'mode':'dynamic','duration_s':.2,'dt_s':.1})
            assert response.status_code==201 and response.json()['status']=='completed',response.text
            rid=response.json()['run_id']
            with patch('fn_engine.api.compile_project',side_effect=AssertionError('report must not compile')):
                report=client.get(f'/api/v1/runs/{rid}/report.html')
                csv=client.get(f'/api/v1/runs/{rid}/report.csv')
                assert report.status_code==csv.status_code==200
                assert '冻结定义' in report.text and project.instances[1].id in report.text
                assert 'kPa' in csv.content.decode('utf-8-sig')
        with TestClient(create_app(data_root=tmp_path)) as client:
            with patch('fn_engine.api.compile_project',side_effect=AssertionError('report must not compile')):
                assert client.get(f'/api/v1/runs/{rid}/report.html').text==report.text


def test_equipment_csv_escapes_text_formula_cells_but_preserves_numeric_signs():
    project = example().model_dump(mode='json')
    instance = project['instances'][0]
    variable = project['modules'][0]['variables'][0]
    key = f"{instance['id']}.{variable['id']}"
    for prefix in ('=', '+', '-', '@'):
        instance['name'] = prefix+'instance'
        variable['unit'].update(canonical_unit=prefix+'canonical', display_unit=prefix+'display',
                                display_scale=2., display_offset=-3.)
        record = {'id': prefix+'run', 'status': 'completed', 'request': {'project': project}}
        rows = [{'time_s': 0., 'variables': {key: -2.5, prefix+'unknown': prefix+'1+1'}}]
        exported = list(csv.reader(StringIO(csv_report(record, rows).lstrip('\ufeff'))))[1:]
        number_row = next(row for row in exported if row[2] == key)
        string_row = next(row for row in exported if row[2] == "'"+prefix+'unknown')
        assert number_row[0] == "'"+prefix+'run'
        assert number_row[3] == "'"+instance['name']+' · '+variable['label']
        assert number_row[4:8] == ["'"+prefix+'canonical', '-2.5', "'"+prefix+'display', '-4.25']
        assert string_row[2:4] == ["'"+prefix+'unknown'] * 2
        assert string_row[5] == string_row[7] == "'"+prefix+'1+1'
