"""Independent sensible-heat references and final-state feedback rejection."""
import math
from pathlib import Path

import pytest

from fn_engine.bench import run_module_test
from fn_engine.models import ModuleTestRequest
from fn_engine.packages import load_module_package
from fn_engine.simulation import SimulationSession
from test_module_execution_network import network_for, probe_definition

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('mode', ['reference', 'node'])
@pytest.mark.parametrize('gain', [.1, 1.])
def test_only_python_heat_module_converges_using_final_outlet_and_accepted_ledger(mode, gain):
    module = probe_definition()
    module.sdk.api_version = '0.4.0'
    module.sdk.capabilities = ['thermal.v1', 'observe.v1']
    module.source = {'runtime': f'''class Module:
    def initialize(self,ctx): ctx.state['energy'] = 0.
    def evaluate(self,ctx): ctx.net.valve(channel='main',kv=10,opening=.8)
    def thermal(self,ctx):
        ctx.heat('main', {gain} * (140000 - .5*(ctx.port('in0').enthalpy_j_kg+ctx.port('out0').enthalpy_j_kg)))
    def observe(self,ctx): ctx.var('observed_heat',ctx.channel('main').heat_w)
    def commit_step(self,ctx,dt): ctx.state['energy'] += ctx.channel('main').heat_w * dt
    def finalize(self,ctx): pass
'''}
    network = network_for(module, node=True)
    network.project.solver.property_coupling = mode
    session = SimulationSession(network, .2, .1)
    try:
        frame0 = session.initialize()
        assert frame0.variables['D1.observed_heat'] != 0
        assert session.runners['D1'].state['energy'] == 0
        first, second = session.advance(), session.advance()
        for frame in [frame0, first, second]:
            q, inlet = abs(frame.variables['D1.main.mass_flow_kg_s']), frame.variables['D1.in0.enthalpy_j_kg']
            expected = gain * (140000 - inlet) / (1 + gain / (2*q))
            assert frame.variables['D1.main.heat_w'] == pytest.approx(expected, rel=2e-6, abs=1e-6)
            assert frame.metrics['thermal_iterations'] > 1
            assert abs(frame.metrics['energy_residual_w']) < 1e-5
        assert session.runners['D1'].state['energy'] == pytest.approx(
            .1*(first.variables['D1.main.heat_w']+second.variables['D1.main.heat_w']))
    finally:
        session.close()


@pytest.mark.parametrize('identifier,temperature', [('fan_coil_unit', 285.15), ('cooling_tower', 315.15)])
def test_new_dry_air_versions_match_independent_ntu_and_accepted_energy(identifier, temperature):
    module = load_module_package(ROOT / f'modules/{identifier}_sdk')
    result = run_module_test(ModuleTestRequest(module=module, temperature_k=temperature, duration_s=.2, dt_s=.1))
    frame = result.frame
    params = {p.id:p.default for p in module.parameters}
    # Independent NTU expression uses the actual inlet cp supplied to the callback.
    from fn_engine.properties import property_service
    from fn_engine.models import FluidConfig
    water = property_service(FluidConfig()).state_ph(frame.variables['D1.in0.pressure_pa'], frame.variables['D1.in0.enthalpy_j_kg'])
    cw = abs(frame.variables['D1.main.mass_flow_kg_s']) * water.specific_heat_j_kg_k
    ca = params['air_flow_m3_s']*params['air_density_kg_m3']*params['air_cp_j_kg_k']
    ratio, ntu = min(cw,ca)/max(cw,ca), params['ua_w_k']/min(cw,ca)
    exp = math.exp(-ntu*(1-ratio))
    epsilon = (1-exp)/(1-ratio*exp)
    target = params['air_inlet_temperature_k'] if identifier == 'fan_coil_unit' else params['air_wet_bulb_temperature_k']
    expected = epsilon*min(cw,ca)*(target-water.temperature_k)
    assert frame.variables['D1.heat_flow_w'] == pytest.approx(expected, rel=1e-6, abs=1e-6)
    assert result.committed.state['thermal_energy_j'] == pytest.approx(sum(
        row.variables['D1.main.heat_w']*(row.time_s-before.time_s) for before,row in zip(result.history,result.history[1:])))


def test_thermal_callback_cannot_mutate_managed_state():
    module = load_module_package(ROOT / 'modules/fan_coil_unit_sdk')
    module.source['runtime'] = module.source['runtime'].replace("ctx.heat('main', power)", "ctx.state['thermal_energy_j'] += 1\n        ctx.heat('main', power)")
    module.content_hash = module.definition_hash = None
    with pytest.raises(ValueError, match='修改了只读状态'):
        run_module_test(ModuleTestRequest(module=module))


def test_zero_flow_heat_callback_returns_zero_without_accumulating_energy():
    module=load_module_package(ROOT/'modules/fan_coil_unit_sdk')
    result=run_module_test(ModuleTestRequest(module=module,inlet_pressure_pa=200000,outlet_pressure_pa=200000))
    assert abs(result.frame.variables['D1.main.mass_flow_kg_s'])<=1e-8
    assert result.frame.variables['D1.heat_flow_w']==pytest.approx(0,abs=1e-6)
    assert result.committed.state['thermal_energy_j']==pytest.approx(0,abs=1e-6)
