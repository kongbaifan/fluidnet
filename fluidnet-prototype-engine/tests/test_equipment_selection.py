from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.models import ModuleTestRequest
from fn_engine.packages import load_module_package
from fn_engine.bench import run_module_test


ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize('fluid', ['Water', 'INCOMP::MEG[0.3]'])
def test_design_valve_reference_flow_is_reproduced_by_worker_network(tmp_path, fluid):
    module = load_module_package(ROOT/'modules/design_valve')
    inputs = {p.id:p.default for p in module.parameters}
    inputs.update(opening_ratio=.6,design_flow_m3_s=12/3600,design_pressure_drop_pa=130000.)
    with TestClient(create_app(data_root=tmp_path)) as client:
        response=client.post('/api/v1/modules/design',json={'module':module.model_dump(mode='json'),
            'parameters':inputs,'fluid':{'fluid':fluid,'phase_policy':'liquid'}})
        assert response.status_code==200,response.text
    params=response.json()['parameters']
    result=run_module_test(ModuleTestRequest(module=module,parameters=params,
        fluid={'fluid':fluid,'phase_policy':'liquid'},property_coupling='node',
        inlet_pressure_pa=250000.,outlet_pressure_pa=120000.,temperature_k=293.15))
    values=result.frame.variables
    assert values['D1.main.mass_flow_kg_s']/values['D1.in0.density_kg_m3']==pytest.approx(12/3600,rel=1e-6)
    assert inputs['kv_m3_h']==16.


@pytest.mark.parametrize('change',[
    {'design_pressure_drop_pa':0.}, {'design_flow_m3_s':0.}, {'opening_ratio':0.},
    {'design_inlet_pressure_pa':100000.,'design_pressure_drop_pa':100000.},
])
def test_design_valve_rejects_invalid_design_points(tmp_path,change):
    module=load_module_package(ROOT/'modules/design_valve')
    with TestClient(create_app(data_root=tmp_path)) as client:
        response=client.post('/api/v1/modules/design',json={'module':module.model_dump(mode='json'),'parameters':change})
        assert response.status_code==422,response.text
