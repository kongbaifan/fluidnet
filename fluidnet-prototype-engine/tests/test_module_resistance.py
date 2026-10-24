"""MOD-S1 integration: unchanged old numerics, validated relations and real flow-driven networks."""
import json
import math
from pathlib import Path
import sys

import pytest

from fn_engine.bench import run_module_test
from fn_engine.compiler import compile_project
from fn_engine.hydraulic_derivatives import branch_drop_value, branch_drop_and_slope
from fn_engine.models import ChannelSpec, ModuleDefinition, ModuleTestRequest, ParameterSpec, PortSpec, VariableSpec
from fn_engine.runtime import NetworkBuilder
from fn_engine.solver import solve_steady

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from numerics_cases import assemble

FROZEN = json.loads((ROOT / 'tests/fixtures/module-system/hydraulics-v1.json').read_text(encoding='utf-8'))['cases']


def resistance_module():
    return ModuleDefinition(id='sdk_resistance', name='SDK 局部阻力示例', runtime='python',
        entrypoint='module:Module', solver_model='python_x',
        ports=[PortSpec(id='in0', label='入口', direction='in'), PortSpec(id='out0', label='出口', direction='out')],
        channels=[ChannelSpec(id='main', name='局部阻力', input_port='in0', output_port='out0',
                              relation='resistance', solver_model='python_x')],
        parameters=[ParameterSpec(id='diameter_m', label='直径 m', default=.05, minimum=.001),
                    ParameterSpec(id='loss_coefficient', label='K', default=8., minimum=0.),
                    ParameterSpec(id='heat_w', label='吸热 W', default=0.)],
        variables=[VariableSpec(id='loss_coefficient', label='K', quantity='ratio', source='derived'),
                   VariableSpec(id='density_kg_m3', label='密度', quantity='density', source='derived'),
                   VariableSpec(id='state.throughput_kg', label='累计质量', quantity='mass', source='state'),
                   VariableSpec(id='state.commit_count', label='提交次数', quantity='count', source='state')],
        source={'runtime': (ROOT / 'examples/module_sdk/resistance.py').read_text(encoding='utf-8')})


@pytest.mark.parametrize('sample', FROZEN)
def test_engine_replays_frozen_pre_extraction_values_and_slopes(sample):
    args = sample['kind'], sample['params'], sample['flow_kg_s'], sample['density_kg_m3'], sample['viscosity_pa_s']
    value = branch_drop_value(*args)
    slope_value, slope = branch_drop_and_slope(*args)
    assert value == pytest.approx(sample['pressure_drop_pa'], rel=2e-14, abs=1e-12)
    assert slope_value == pytest.approx(sample['slope_value_pa'], rel=2e-14, abs=1e-12)
    assert slope == pytest.approx(sample['slope_pa_per_kg_s'], rel=2e-14, abs=1e-12)


@pytest.mark.parametrize('flow', [-.5, 0., .5])
def test_real_resistance_network_with_known_signed_flow_boundary(flow):
    module = resistance_module()
    forced = module.model_copy(deep=True, update={'id': 'flow_boundary', 'parameters': [], 'variables': [],
        'source': {'runtime': f'''class Module:
    def initialize(self, ctx): pass
    def evaluate(self, ctx):
        ctx.net.compressor(channel="main", forced_mass_flow_kg_s={flow!r})
    def commit_step(self, ctx, dt_s): pass
    def finalize(self, ctx): pass
'''}})
    project = assemble('resistance-flow-boundary', [
        ('B1', 'source', {'pressure_pa': 250000.}), ('R1', module.id, {}),
        ('F1', forced.id, {}), ('B2', 'source', {'pressure_pa': 120000.})],
        [('B1:out0', 'R1:in0'), ('R1:out0', 'F1:in0'), ('F1:out0', 'B2:out0')], [module, forced])
    project.solver.thermal = False
    frame = solve_steady(compile_project(project))
    assert frame.valid
    actual_flow = frame.variables['R1.main.mass_flow_kg_s']
    drop = frame.variables['R1.main.pressure_drop_pa']
    density = frame.variables['R1.density_kg_m3']
    velocity = 4 * flow / (density * math.pi * .05 ** 2)
    expected = 8.0 * density * velocity * abs(velocity) / 2
    assert actual_flow == pytest.approx(flow, abs=1e-8)
    assert drop == pytest.approx(expected, abs=1e-6, rel=1e-8)
    assert frame.metrics['mass_residual_kg_s'] <= project.solver.mass_tolerance_kg_s
    assert frame.metrics['pressure_residual_pa'] <= project.solver.pressure_tolerance_pa


def test_real_bench_transfers_heat_and_commits_mass_for_new_resistance_relation():
    result = run_module_test(ModuleTestRequest(module=resistance_module(), parameters={'heat_w': 250.},
        inlet_pressure_pa=250000., outlet_pressure_pa=120000., duration_s=1., dt_s=.5))
    density = result.evaluation.variables['density_kg_m3']
    expected = math.pi * .05 ** 2 / 4 * math.sqrt(2 * density * 130000 / 8.)
    assert result.frame.variables['D1.main.mass_flow_kg_s'] == pytest.approx(expected, rel=1e-6)
    assert result.frame.variables['D1.main.heat_w'] == pytest.approx(250., abs=1e-6)
    assert result.committed.state['commit_count'] == 2
    integrated = sum(abs(frame.variables['D1.main.mass_flow_kg_s']) * (frame.time_s - previous.time_s)
                     for previous, frame in zip(result.history, result.history[1:]))
    assert result.committed.state['throughput_kg'] == pytest.approx(integrated, abs=1e-8)


@pytest.mark.parametrize('overrides', [
    {'diameter_m': 0.}, {'diameter_m': True}, {'loss_coefficient': -1.},
    {'loss_coefficient': float('nan')}, {'density_kg_m3': -1.}, {'density_kg_m3': False},
    {'heat_w': float('inf')}, {'channel': 'invalid.channel'},
])
def test_builder_rejects_invalid_relation_without_registering_it(overrides):
    builder = NetworkBuilder()
    with pytest.raises(ValueError):
        builder.resistance(**{'channel': 'main', 'diameter_m': .05, 'loss_coefficient': 8., **overrides})
    assert not builder.relations


def test_zero_loss_is_not_clamped_and_unspecified_density_uses_the_host_reference():
    builder = NetworkBuilder()
    builder.resistance(channel='main', diameter_m=.05, loss_coefficient=0.)
    relation = builder.relations[0]
    assert relation.kind == 'resistance'
    assert branch_drop_value('resistance', relation.parameters, 1.0, 1000., .001) == 0.
    assert relation.parameters['density_kg_m3'] == 0.
    with pytest.raises(TypeError):
        builder.resistance(channel='unsupported', diameter_m=.05, loss_coefficient=8., height_m=1.)
