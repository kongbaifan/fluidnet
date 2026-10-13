"""Several fluids in one project: one fluid per circuit, circuits meet only across exchangers."""
import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import ChannelSpec, CircuitFluid, Endpoint, FluidConfig, ModuleDefinition, PortSpec
from fn_engine.properties import property_service
from fn_engine.solver import RHO_WATER, solve_dynamic, solve_steady
from test_thermal import analytic_q, project

MEG30 = 'INCOMP::MEG[0.3]'
P_HOT, P_COLD, P_OUT = 208486.8, 208099.8, 201325.


def circuit(id, instance, port, fluid):
    return CircuitFluid(id=id, anchor=Endpoint(instance_id=instance, port_id=port), fluid=FluidConfig(fluid=fluid))


def hx(cold=MEG30, t_cold=263.15, coupling='reference', cold_sink=('SC', 'source', None)):
    sink_id, sink_kind, sink_params = cold_sink
    p = project([('BH', 'source', {'pressure_pa': P_HOT, 'temperature_k': 333.15}),
                 ('BC', 'source', {'pressure_pa': P_COLD, 'temperature_k': t_cold}),
                 ('HX', 'exchanger', {'ua_w_k': 2000.}),
                 ('SH', 'source', {'pressure_pa': P_OUT, 'temperature_k': 303.15}),
                 (sink_id, sink_kind, sink_params or {'pressure_pa': P_OUT, 'temperature_k': t_cold})],
                [('BH:out0', 'HX:in0'), ('HX:out0', 'SH:out0'), ('BC:out0', 'HX:in1'), (f'HX:out1', f'{sink_id}:' + ('in0' if sink_kind == 'tank' else 'out0'))],
                property_coupling=coupling)
    if cold:
        p.circuit_fluids = [circuit('brine', 'BC', 'out0', cold)]
    return p


def test_exchanger_sides_use_their_own_fluid():
    network = compile_project(hx())
    assert network.mixed and [f.fluid for f in network.circuit_fluids] == [MEG30, 'Water']
    assert network.circuit_sources == ['brine', 'project']
    frame = solve_steady(network)
    v = frame.variables
    assert any(d.code == 'MULTIPLE_FLUIDS' for d in frame.diagnostics)
    meg = property_service(FluidConfig(fluid=MEG30)).state_pt(v['HX.in1.pressure_pa'], 263.15)
    assert v['HX.in1.density_kg_m3'] == pytest.approx(meg.density_kg_m3, rel=1e-12)
    assert v['HX.in1.specific_heat_j_kg_k'] == pytest.approx(meg.specific_heat_j_kg_k, rel=1e-12)
    expected = analytic_q(v['HX.in0.specific_heat_j_kg_k'], v['HX.in1.specific_heat_j_kg_k'], v['HX.ch0.mass_flow_kg_s'],
                          v['HX.ch1.mass_flow_kg_s'], 2000., v['HX.in0.temperature_k'], v['HX.in1.temperature_k'])
    assert v['HX.ch1.heat_w'] == pytest.approx(expected, rel=1e-9)
    assert v['HX.ch0.heat_w'] == pytest.approx(-expected, rel=1e-9)
    assert abs(frame.metrics['energy_residual_w']) < 1e-6 * expected


def test_limits_are_checked_with_the_fluid_of_each_circuit():
    compile_project(hx())  # −10 °C glycol is fine
    with pytest.raises(CompilationError) as error:
        compile_project(hx(cold=None))  # −10 °C water is not
    assert error.value.diagnostic.code == 'PARAMETER_RANGE' and error.value.diagnostic.instance_id == 'BC'


@pytest.mark.parametrize('coupling', ['reference', 'node'])
def test_hydraulics_use_the_reference_density_of_each_circuit(coupling):
    mixed = solve_steady(compile_project(hx(t_cold=293.15, coupling=coupling))).variables
    water = solve_steady(compile_project(hx(cold=None, t_cold=293.15, coupling=coupling))).variables
    if coupling == 'reference':
        # The water circuit is untouched by the brine next door.
        assert mixed['HX.ch0.mass_flow_kg_s'] == pytest.approx(water['HX.ch0.mass_flow_kg_s'], rel=1e-12)
        # Exchanger channels: Δp = K·w²/(2ρA²), so at equal Δp w ∝ √ρ.
        rho = property_service(FluidConfig(fluid=MEG30)).state_pt((P_COLD + P_OUT) / 2, 293.15).density_kg_m3
        ratio = mixed['HX.ch1.mass_flow_kg_s'] / water['HX.ch1.mass_flow_kg_s']
        assert ratio == pytest.approx(math.sqrt(rho / RHO_WATER), rel=1e-9)
    else:
        assert mixed['HX.ch1.mass_flow_kg_s'] != pytest.approx(water['HX.ch1.mass_flow_kg_s'], rel=1e-3)


def test_assigning_the_project_fluid_changes_nothing():
    plain = solve_steady(compile_project(hx(cold=None, t_cold=293.15)))
    same = hx(cold='HEOS::Water', t_cold=293.15)
    network = compile_project(same)
    assert not network.mixed
    assert solve_steady(network).variables == plain.variables


def test_tank_in_a_brine_circuit_stores_brine():
    p = hx(t_cold=263.15, cold_sink=('T1', 'tank', {'area_m2': .5, 'height_m': 3., 'level_m': 1., 'temperature_k': 263.15}))
    p.instances = [i for i in p.instances if i.id != 'SC']
    frames = solve_dynamic(compile_project(p), 1., .5)
    first = frames[0].variables
    meg = property_service(FluidConfig(fluid=MEG30))
    rho = meg.state_pt(101325. + first['T1.state.mass_kg'] * 9.80665 / .5, 263.15).density_kg_m3
    assert first['T1.state.mass_kg'] == pytest.approx(rho * .5 * 1., rel=1e-9)
    assert frames[-1].variables['T1.state.mass_kg'] > first['T1.state.mass_kg']


def test_a_single_circuit_with_another_fluid_does_not_fall_back_to_the_project_fluid():
    p = project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 263.15}), ('L1', 'pipe', {}),
                 ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 263.15})],
                [('B1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])
    p.circuit_fluids = [circuit('only', 'B1', 'out0', MEG30)]
    network = compile_project(p)  # −10 °C is fine for the glycol, not for the project water
    assert network.mixed and network.fluid_at(0).fluid == MEG30
    v = solve_steady(network).variables
    meg = property_service(FluidConfig(fluid=MEG30)).state_pt(v['L1.in0.pressure_pa'], 263.15)
    assert v['L1.in0.density_kg_m3'] == pytest.approx(meg.density_kg_m3, rel=1e-12)


def test_conflicting_fluids_in_one_circuit_are_rejected():
    p = hx()
    p.circuit_fluids.append(circuit('again', 'SC', 'out0', MEG30))
    compile_project(p)  # the same fluid twice in one circuit is fine
    p.circuit_fluids.append(circuit('other', 'HX', 'out1', 'HEOS::Ethanol'))
    with pytest.raises(CompilationError) as error:
        compile_project(p)
    assert error.value.diagnostic.code == 'FLUID_CONFLICT'


def test_a_closed_valve_does_not_split_a_circuit():
    p = project([('B1', 'source', {'pressure_pa': 250000.}), ('V1', 'valve', {'opening_ratio': 0.}), ('L1', 'pipe', {}),
                 ('B2', 'source', {'pressure_pa': 120000.})],
                [('B1:out0', 'V1:in0'), ('V1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])
    p.circuit_fluids = [circuit('a', 'B1', 'out0', 'Water'), circuit('b', 'B2', 'out0', MEG30)]
    with pytest.raises(CompilationError) as error:
        compile_project(p)
    assert error.value.diagnostic.code == 'FLUID_CONFLICT'


@pytest.mark.parametrize('entry, code', [(circuit('x', 'HX', 'nope', MEG30), 'CIRCUIT_ANCHOR_UNKNOWN'),
                                         (circuit('x', 'NOPE', 'out0', MEG30), 'CIRCUIT_ANCHOR_UNKNOWN'),
                                         (circuit('x', 'BC', 'out0', 'NotAFluid'), 'FLUID_UNKNOWN')])
def test_bad_circuit_entries_fail_at_compile_time(entry, code):
    p = hx()
    p.circuit_fluids = [entry]
    with pytest.raises(CompilationError) as error:
        compile_project(p)
    assert error.value.diagnostic.code == code


TWO_SIDED = '''class Module:
    def evaluate(self, ctx):
        ctx.net.valve(channel="a", kv=10.0, opening=1.0)
        ctx.net.valve(channel="b", kv=10.0, opening=1.0)
    def commit_step(self, ctx, dt_s):
        for port in ("in0", "in1"):
            state = ctx.port(port)
            ctx.var("rho_" + port, ctx.fluid_at(port).state_pt(state.pressure_pa, state.temperature_k).density_kg_m3)
        ctx.var("rho_default", ctx.fluid.state_pt(ctx.port("in0").pressure_pa, ctx.port("in0").temperature_k).density_kg_m3)
'''


@pytest.mark.parametrize('batch', [False, True])
def test_python_module_across_two_circuits_sees_both_fluids(batch):
    ports = [PortSpec(id=i, label=i, direction='in' if i.startswith('in') else 'out') for i in ('in0', 'out0', 'in1', 'out1')]
    module = ModuleDefinition(id='twosided', name='twosided', runtime='python', entrypoint='module:Module',
        solver_model='python_x', source={'runtime': TWO_SIDED}, ports=ports,
        channels=[ChannelSpec(id='a', name='a', input_port='in0', output_port='out0', relation='resistance', solver_model='python_x'),
                  ChannelSpec(id='b', name='b', input_port='in1', output_port='out1', relation='resistance', solver_model='python_x')])
    p = project([('BH', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                 ('BC', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}), ('M1', 'twosided', {}),
                 ('SH', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15}),
                 ('SC', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
                [('BH:out0', 'M1:in0'), ('M1:out0', 'SH:out0'), ('BC:out0', 'M1:in1'), ('M1:out1', 'SC:out0')],
                extra_modules=[module], batch_modules=batch)
    p.circuit_fluids = [circuit('brine', 'BC', 'out0', MEG30)]
    v = solve_dynamic(compile_project(p), .2, .1)[-1].variables
    water, meg = property_service(FluidConfig()), property_service(FluidConfig(fluid=MEG30))
    assert v['M1.rho_in0'] == pytest.approx(water.state_pt(v['M1.in0.pressure_pa'], v['M1.in0.temperature_k']).density_kg_m3, rel=1e-12)
    assert v['M1.rho_in1'] == pytest.approx(meg.state_pt(v['M1.in1.pressure_pa'], v['M1.in1.temperature_k']).density_kg_m3, rel=1e-12)
    assert v['M1.rho_default'] == v['M1.rho_in0']


def test_validation_reports_the_circuits():
    with TestClient(create_app()) as client:
        body = client.post('/api/v1/projects/validate', json=hx().model_dump(mode='json')).json()
    assert body['valid']
    circuits = {c['source']: c for c in body['circuits']}
    assert circuits['brine']['fluid']['fluid'] == MEG30 and set(circuits['brine']['ports']) == {'BC:out0', 'HX:in1', 'HX:out1', 'SC:out0'}
    assert circuits['project']['fluid']['fluid'] == 'Water' and 'HX:in0' in circuits['project']['ports']


def test_prototype_circuit_fluids_are_normalized():
    raw = json.loads((Path(__file__).parent / 'fixtures' / 'prototype.json').read_text(encoding='utf-8'))
    active = next(p for p in raw['projects'] if p['id'] == raw['activeProject'])
    node = active['pages'][0]['nodes'][0]
    active['circuitFluids'] = [{'id': 'c1', 'anchor': {'instance_id': node['id'], 'port_id': 'out0'}, 'medium': 'meg30'},
                               {'id': 'c2', 'anchor': {'instance_id': node['id'], 'port_id': 'out0'},
                                'fluid': 'REFPROP::R32[0.5]&R125[0.5]', 'fluidReference': 'mole'}]
    entries = normalize_prototype_export(raw).circuit_fluids
    assert [(e.id, e.fluid.fluid, e.fluid.reference) for e in entries] == [('c1', MEG30, 'mass'),
                                                                           ('c2', 'REFPROP::R32[0.5]&R125[0.5]', 'mole')]
