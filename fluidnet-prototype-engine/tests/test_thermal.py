import json
import math
from pathlib import Path

import numpy as np
import pytest

from fn_engine.bridge import normalize_prototype_export
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import (ChannelSpec, Connection, Endpoint, FluidConfig, ModuleDefinition, ModuleInstance,
                              ParameterSpec, PortSpec, Project)
from fn_engine.properties import property_service
from fn_engine.solver import (MU_WATER, RHO_WATER, THERMAL_ONLY_SUFFIXES, solve_dynamic, solve_steady)
from fn_engine.thermal import ThermalError, solve_thermal

WATER = property_service(FluidConfig())
FIXTURE = Path(__file__).parent / 'fixtures' / 'prototype.json'


def link(cid, source, target):
    (si, sp), (ti, tp) = source.split(':'), target.split(':')
    return Connection(id=cid, source=Endpoint(instance_id=si, port_id=sp), target=Endpoint(instance_id=ti, port_id=tp))


def project(instances, connections, extra_modules=(), **solver):
    catalog = catalog_map()
    kinds = sorted({kind for _, kind, _ in instances if kind in catalog})
    p = Project(id='thermal', name='thermal', modules=[catalog[k] for k in kinds] + list(extra_modules),
                instances=[ModuleInstance(id=i, module_id=kind, name=i, parameters=params) for i, kind, params in instances],
                connections=[link(f'e{n}', a, b) for n, (a, b) in enumerate(connections)])
    for key, value in solver.items():
        setattr(p.solver, key, value)
    return p


def line(kind, params=None, inlet=250000., outlet=120000., t_in=293.15, t_out=293.15, **solver):
    return project([('B1', 'source', {'pressure_pa': inlet, 'temperature_k': t_in}), ('D1', kind, params or {}),
                    ('B2', 'source', {'pressure_pa': outlet, 'temperature_k': t_out})],
                   [('B1:out0', 'D1:in0'), ('D1:out0', 'B2:out0')], **solver)


def prototype(active):
    raw = json.loads(FIXTURE.read_text(encoding='utf-8'))
    raw['activeProject'] = active
    return normalize_prototype_export(raw)


def h(pressure, temperature):
    return WATER.state_pt(pressure, temperature).enthalpy_j_kg


# 1. Mixing at a node is the mass-weighted mean of the arriving enthalpies.
def test_node_mixing_is_mass_weighted():
    p = project([('H', 'source', {'pressure_pa': 300000., 'temperature_k': 333.15}),
                 ('C', 'source', {'pressure_pa': 300000., 'temperature_k': 293.15}),
                 ('VH', 'valve', {'kv_m3_h': 6.}), ('VC', 'valve', {'kv_m3_h': 14.}),
                 ('N', 'junction', {}), ('VO', 'valve', {'kv_m3_h': 20.}),
                 ('S', 'source', {'pressure_pa': 150000., 'temperature_k': 293.15})],
                [('H:out0', 'VH:in0'), ('C:out0', 'VC:in0'), ('VH:out0', 'N:in0'), ('VC:out0', 'N:out1'),
                 ('N:out0', 'VO:in0'), ('VO:out0', 'S:out0')])
    v = solve_steady(compile_project(p)).variables
    wh, wc = v['VH.mass_flow_kg_s'], v['VC.mass_flow_kg_s']
    expected = (wh * v['VH.out0.enthalpy_j_kg'] + wc * v['VC.out0.enthalpy_j_kg']) / (wh + wc)
    assert wh != pytest.approx(wc)
    assert v['N.in0.enthalpy_j_kg'] == pytest.approx(expected, rel=1e-12)
    assert v['VO.in0.enthalpy_j_kg'] == pytest.approx(expected, rel=1e-12)
    assert 293.15 < v['VO.inlet_temperature_k'] < 333.15


# 2. Throttling and an adiabatic pipe keep enthalpy.
@pytest.mark.parametrize('kind,params', [('valve', {}), ('pipe', {'heat_loss_ua_w_k': 0.})])
def test_valve_and_adiabatic_pipe_are_isenthalpic(kind, params):
    v = solve_steady(compile_project(line(kind, params, t_in=330.))).variables
    assert v['D1.out0.enthalpy_j_kg'] == pytest.approx(v['D1.in0.enthalpy_j_kg'], rel=1e-12)
    assert v['D1.heat_w'] == pytest.approx(0., abs=1e-6)
    assert v['D1.out0.temperature_k'] == pytest.approx(330., abs=0.05)


# 3. Pipe heat loss matches T_out = T_env + (T_in − T_env)·exp(−UA/(w·cp)).
def test_pipe_heat_loss_matches_analytic_decay():
    # A small pressure drop keeps the throttling (Joule–Thomson) temperature shift far below the tolerance;
    # the closed form only describes the exchange with ambient.
    params = {'length_m': 20., 'diameter_m': .04, 'heat_loss_ua_w_k': 300., 'ambient_temperature_k': 293.15}
    v = solve_steady(compile_project(line('pipe', params, inlet=202000., outlet=200000., t_in=303.15))).variables
    w, cp = v['D1.mass_flow_kg_s'], v['D1.in0.specific_heat_j_kg_k']
    expected = 293.15 + (v['D1.inlet_temperature_k'] - 293.15) * math.exp(-300. / (w * cp))
    assert v['D1.outlet_temperature_k'] == pytest.approx(expected, abs=1e-3)
    assert 293.15 < v['D1.outlet_temperature_k'] < 303.15
    assert v['D1.heat_w'] == pytest.approx(w * (v['D1.out0.enthalpy_j_kg'] - v['D1.in0.enthalpy_j_kg']), rel=1e-9)
    assert v['D1.heat_w'] < 0


# 4. Shaft work ends up in the fluid: Δh·w = shaft power.
def test_pump_shaft_power_heats_the_fluid():
    v = solve_steady(compile_project(prototype('water-net'))).variables
    assert v['P1.shaft_power_w'] > 0
    assert v['P1.heat_w'] == pytest.approx(v['P1.shaft_power_w'], rel=1e-9)
    assert v['P1.outlet_temperature_k'] > v['P1.inlet_temperature_k']


def hx_network(t_hot=333.15, t_cold=293.15, ua=2000., p_hot=208486.8, p_cold=208099.8, p_out=201325.):
    return compile_project(project(
        [('BH', 'source', {'pressure_pa': p_hot, 'temperature_k': t_hot}),
         ('BC', 'source', {'pressure_pa': p_cold, 'temperature_k': t_cold}),
         ('HX', 'exchanger', {'ua_w_k': ua}),
         ('SH', 'source', {'pressure_pa': p_out, 'temperature_k': 303.15}),
         ('SC', 'source', {'pressure_pa': p_out, 'temperature_k': 303.15})],
        [('BH:out0', 'HX:in0'), ('HX:out0', 'SH:out0'), ('BC:out0', 'HX:in1'), ('HX:out1', 'SC:out0')]))


def hx_direct(network, w_hot, w_cold):
    pressures = np.zeros(len(network.node_keys))
    for node, value in network.fixed_pressures.items():
        pressures[node] = value
    flows = np.array([w_hot if b.channel_id == 'ch0' else w_cold for b in network.branches])
    return solve_thermal(network, WATER, pressures, flows), [b.channel_id for b in network.branches]


def analytic_q(cp_h, cp_c, w_h, w_c, ua, t_h, t_c):
    ch, cc = w_h * cp_h, w_c * cp_c
    cmin, cmax = min(ch, cc), max(ch, cc)
    ratio, ntu = cmin / cmax, ua / cmin
    if abs(1 - ratio) < 1e-8:
        eff = ntu / (1 + ntu)
    else:
        e = math.exp(-ntu * (1 - ratio))
        eff = (1 - e) / (1 - ratio * e)
    return eff * cmin * (t_h - t_c)


# 5. ε–NTU, Cr < 1 and Cr = 1; both sides equal and opposite; one side without flow.
@pytest.mark.parametrize('balanced', [False, True])
def test_exchanger_matches_epsilon_ntu(balanced):
    network = hx_network()
    hot_node, cold_node = network.port_nodes['HX:in0'], network.port_nodes['HX:in1']
    cp_h = WATER.state_ph(network.fixed_pressures[hot_node], h(network.fixed_pressures[hot_node], 333.15)).specific_heat_j_kg_k
    cp_c = WATER.state_ph(network.fixed_pressures[cold_node], h(network.fixed_pressures[cold_node], 293.15)).specific_heat_j_kg_k
    w_h, w_c = (0.8, 0.8 * cp_h / cp_c) if balanced else (0.8, 0.5)
    result, channels = hx_direct(network, w_h, w_c)
    a, b = channels.index('ch0'), channels.index('ch1')
    states = result.node_states
    expected = analytic_q(states[hot_node].specific_heat_j_kg_k, states[cold_node].specific_heat_j_kg_k, w_h, w_c, 2000.,
                          states[hot_node].temperature_k, states[cold_node].temperature_k)
    assert -result.heat_w[a] == pytest.approx(expected, rel=1e-9)
    assert result.heat_w[b] == pytest.approx(expected, rel=1e-9)
    assert result.heat_w[a] + result.heat_w[b] == pytest.approx(0., abs=1e-6 * expected)
    assert result.outlet_states[a].temperature_k < 333.15 and result.outlet_states[b].temperature_k > 293.15


def test_exchanger_without_flow_on_one_side_exchanges_nothing():
    network = hx_network()
    result, channels = hx_direct(network, 0.8, 0.)
    a, b = channels.index('ch0'), channels.index('ch1')
    assert result.heat_w[a] == 0 and result.heat_w[b] == 0
    assert any(d.code == 'THERMAL_EXCHANGER_NO_FLOW' for d in result.diagnostics)
    assert result.outlet_states[a].enthalpy_j_kg == pytest.approx(
        result.node_states[network.port_nodes['HX:in0']].enthalpy_j_kg, rel=1e-12)


# 6. Reversed flow: the upwind side and the outlet port follow the actual direction.
def test_reverse_flow_uses_actual_upwind_side():
    params = {'heat_loss_ua_w_k': 200., 'ambient_temperature_k': 293.15}
    v = solve_steady(compile_project(line('pipe', params, inlet=120000., outlet=250000., t_in=293.15, t_out=323.15))).variables
    assert v['D1.mass_flow_kg_s'] < 0
    assert v['D1.inlet_temperature_k'] == pytest.approx(323.15, abs=0.05)
    assert 293.15 < v['D1.outlet_temperature_k'] < v['D1.inlet_temperature_k']
    # in0 is where the reversed stream leaves the pipe.
    assert v['D1.in0.temperature_k'] == pytest.approx(v['D1.outlet_temperature_k'])
    assert v['B1.out0.temperature_k'] == pytest.approx(v['D1.outlet_temperature_k'])


# 7. A closed valve isolates stagnant nodes: they keep their boundary temperature.
def test_closed_valve_nodes_keep_boundary_temperature():
    frame = solve_steady(compile_project(line('valve', {'opening_ratio': 0}, t_in=330., t_out=293.15)))
    v = frame.variables
    assert any(d.code == 'THERMAL_STAGNANT_NODE' for d in frame.diagnostics)
    assert v['D1.in0.temperature_k'] == pytest.approx(330.)
    assert v['D1.out0.temperature_k'] == pytest.approx(293.15)
    assert v['D1.heat_w'] == 0


def closed_loop(**solver):
    return project([('E', 'source', {'pressure_pa': 200000., 'temperature_k': 293.15}), ('N', 'junction', {}),
                    ('P', 'pump', {}), ('L', 'pipe', {'length_m': 40., 'diameter_m': .03})],
                   [('E:out0', 'N:in0'), ('N:out0', 'P:in0'), ('P:out0', 'L:in0'), ('L:out0', 'N:out1')], **solver)


# 8. A loop without make-up water takes its temperature reference from the boundary and reports the heat.
def test_closed_loop_without_supply_uses_boundary_reference():
    frame = solve_steady(compile_project(closed_loop()))
    v = frame.variables
    assert v['P.mass_flow_kg_s'] > 0
    assert any(d.code == 'THERMAL_REFERENCE_FROM_BOUNDARY' for d in frame.diagnostics)
    assert v['N.in0.temperature_k'] == pytest.approx(293.15)
    assert v['P.outlet_temperature_k'] > 293.15
    # The pump keeps adding heat; only the fallback reference can take it out of a closed loop.
    assert frame.metrics['reference_heat_w'] == pytest.approx(-v['P.shaft_power_w'], rel=1e-9)


# 9. Whole-network energy balance on the heat-loop example.
def test_heat_loop_energy_balance_closes():
    frame = solve_steady(compile_project(prototype('heat-loop')))
    v = frame.variables
    duty = v['HX1.ch1.heat_w']
    assert duty > 1000
    assert v['HX1.ch0.heat_w'] == pytest.approx(-duty, rel=1e-9)
    assert abs(frame.metrics['energy_residual_w']) < 1e-6 * duty
    assert frame.metrics['thermal_iterations'] >= 1
    assert not any(d.code == 'THERMAL_NOT_SOLVED' for d in frame.diagnostics)


# 10. Reference mode leaves the hydraulics unchanged; thermal=False reproduces the old output.
def test_reference_mode_keeps_hydraulic_baseline():
    v = solve_steady(compile_project(prototype('water-net'))).variables
    # Values recorded before the thermal layer existed (tmp/baseline.json, 2026-10-11).
    assert v['V1.mass_flow_kg_s'] == pytest.approx(3.5826766415095452, rel=1e-12)
    off = prototype('water-net')
    off.solver.thermal = False
    v_off = solve_steady(compile_project(off)).variables
    for key, value in v_off.items():
        if isinstance(value, float) and not key.endswith(('temperature_k', 'heat_w')):
            assert v[key] == pytest.approx(value, rel=1e-12, abs=1e-12), key


def test_thermal_off_reports_no_thermal_values():
    p = prototype('heat-loop')
    p.solver.thermal = False
    frame = solve_steady(compile_project(p))
    v = frame.variables
    assert any(d.code == 'THERMAL_NOT_SOLVED' for d in frame.diagnostics)
    # Thermal-only keys are omitted entirely, so the frame keeps its pre-0.3 size.
    assert 'HX1.ch0.outlet_temperature_k' not in v and 'HX1.ch0.heat_w' not in v
    assert 'HX1.in0.enthalpy_j_kg' not in v and 'HX1.in0.density_kg_m3' not in v
    assert v['B1.out0.temperature_k'] == pytest.approx(338.15)
    assert 'thermal_iterations' not in frame.metrics


# 11. node coupling: hot-side properties feed back into the hydraulics.
def test_node_coupling_uses_hot_side_properties():
    reference = solve_steady(compile_project(prototype('heat-loop'))).variables
    p = prototype('heat-loop')
    p.solver.property_coupling = 'node'
    frame = solve_steady(compile_project(p))
    v = frame.variables
    assert v['HX1.in0.density_kg_m3'] < RHO_WATER - 10
    assert v['HX1.in0.viscosity_pa_s'] < 0.6 * MU_WATER
    assert frame.metrics['coupling_iterations'] > 1
    assert v['HX1.ch0.mass_flow_kg_s'] != pytest.approx(reference['HX1.ch0.mass_flow_kg_s'], rel=1e-6)
    p.solver.max_coupling_iterations = 1
    with pytest.raises(ThermalError) as error:
        solve_steady(compile_project(p))
    assert error.value.diagnostic.code == 'COUPLING_NOT_CONVERGED'


HEATER_SOURCE = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("commits", 0)

    def evaluate(self, ctx):
        port = ctx.port("in0")
        ctx.net.valve(channel="main", kv=ctx.parameter("kv_m3_h"), opening=ctx.parameter("opening_ratio"),
                      density_kg_m3=port.density_kg_m3, heat_w=ctx.parameter("heat_w"))
        ctx.var("seen_density", port.density_kg_m3)

    def commit_step(self, ctx, dt_s):
        ctx.state["commits"] += 1
        ctx.var("seen_temperature", ctx.port("out0").temperature_k)
        ctx.var("seen_enthalpy", ctx.port("out0").enthalpy_j_kg)
'''


def heater_module():
    return ModuleDefinition(id='heater', name='Python heater', runtime='python', entrypoint='module:Module',
        solver_model='python_valve', source={'runtime': HEATER_SOURCE},
        ports=[PortSpec(id='in0', label='in0', direction='in'), PortSpec(id='out0', label='out0', direction='out')],
        channels=[ChannelSpec(id='main', name='main', input_port='in0', output_port='out0', relation='resistance',
                              solver_model='python_valve')],
        parameters=[ParameterSpec(id='heat_w', label='heat', default=0.0),
                    ParameterSpec(id='opening_ratio', label='opening', default=1.0, minimum=0, maximum=1),
                    ParameterSpec(id='kv_m3_h', label='Kv', default=4.0, minimum=.001)])


def heater_line(params, t_in=293.15, **solver):
    return project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': t_in}), ('H1', 'heater', params),
                    ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
                   [('B1:out0', 'H1:in0'), ('H1:out0', 'B2:out0')], extra_modules=[heater_module()], **solver)


# 12. Python modules: heat_w is applied, commit_step sees real thermal state, failures are explicit.
def test_python_module_heat_and_committed_thermal_state():
    frames = solve_dynamic(compile_project(heater_line({'heat_w': 20000.})), .2, .1)
    v = frames[-1].variables
    assert v['H1.heat_w'] == pytest.approx(20000., rel=1e-9)
    assert v['H1.outlet_temperature_k'] > v['H1.inlet_temperature_k'] + 1
    assert v['H1.seen_temperature'] == pytest.approx(v['H1.out0.temperature_k'])
    assert v['H1.seen_enthalpy'] == pytest.approx(v['H1.out0.enthalpy_j_kg'])
    # reference mode keeps the reference density in evaluate()
    assert v['H1.seen_density'] == pytest.approx(RHO_WATER)
    assert v['H1.state.commits'] == 2


def test_python_module_heat_without_flow_is_rejected():
    with pytest.raises(ThermalError) as error:
        solve_steady(compile_project(heater_line({'heat_w': 5000., 'opening_ratio': 0.})))
    assert error.value.diagnostic.code == 'NO_FLOW_HEAT'
    assert error.value.diagnostic.instance_id == 'H1'


def test_boiling_the_stream_is_reported_as_unsupported_phase():
    with pytest.raises(ThermalError) as error:
        solve_steady(compile_project(heater_line({'heat_w': 4.0e6})))
    assert error.value.diagnostic.code == 'PHASE_UNSUPPORTED'
    assert error.value.diagnostic.instance_id == 'H1'


def test_node_mode_evaluate_receives_node_density():
    v = solve_steady(compile_project(heater_line({}, t_in=353.15, property_coupling='node'))).variables
    assert v['H1.seen_density'] == pytest.approx(WATER.state_pt(250000., 353.15).density_kg_m3, rel=1e-3)
    assert v['H1.seen_density'] < RHO_WATER - 20


# 13. Dynamic frames warm-start from the previous frame and keep the same thermal state.
def test_dynamic_frames_warm_start():
    frames = solve_dynamic(compile_project(prototype('heat-loop')), .3, .1)
    assert frames[1].metrics['iterations'] < frames[0].metrics['iterations']
    assert frames[-1].variables['HX1.ch1.outlet_temperature_k'] == pytest.approx(
        frames[0].variables['HX1.ch1.outlet_temperature_k'], abs=1e-9)
    assert '热力' in next(d.message for d in frames[0].diagnostics if d.code == 'DYNAMIC_QUASI_STEADY')


# 14. Two boundaries on one node must agree on temperature.
def test_boundary_temperature_conflict_is_rejected():
    def build(**solver):
        return project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}),
                        ('B3', 'source', {'pressure_pa': 250000., 'temperature_k': 313.15}), ('N', 'junction', {}),
                        ('D1', 'valve', {}), ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
                       [('B1:out0', 'N:in0'), ('B3:out0', 'N:out1'), ('N:out0', 'D1:in0'), ('D1:out0', 'B2:out0')], **solver)
    with pytest.raises(CompilationError) as error:
        compile_project(build())
    assert error.value.diagnostic.code == 'BOUNDARY_TEMPERATURE_CONFLICT'
    compile_project(build(thermal=False))


# 15. Declared variables match the frame with the thermal layer on and off (see also test_contracts_and_physics).
@pytest.mark.parametrize('thermal', [True, False])
def test_catalog_variables_match_frame(thermal):
    p = prototype('water-net')
    p.solver.thermal = thermal
    frame = solve_steady(compile_project(p))
    modules = {m.id: m for m in p.modules}
    # Pipe state variables exist only when the pipe has thermal_cells > 0 (test_states covers them).
    declared = {f'{i.id}.{v.id}' for i in p.instances for v in modules[i.module_id].variables
                if not (modules[i.module_id].solver_model == 'pipe' and v.source == 'state')}
    if not thermal:
        declared = {k for k in declared if not k.endswith(THERMAL_ONLY_SUFFIXES)}
    assert set(frame.variables) == declared


# 16. Cross-check against the archived v0.2 kernel (IF97). Values come from running
# archive/fluidnet-studio-v0.2 `examples.exchanger()` with solve_steady on 2026-10-11: exchanger inlet
# pressures/temperatures/flows below, hot outlet 318.5596507335328 K, cold outlet 308.1187791645757 K,
# duty 50459.92078905712 W. The engine uses CoolProp HEOS, so a small property difference is allowed.
def test_exchanger_agrees_with_archived_v02_kernel():
    network = hx_network(t_hot=333.15860130066153, t_cold=293.159720551676,
                         p_hot=208486.82286963172, p_cold=208099.80416768367, p_out=201325.0)
    result, channels = hx_direct(network, 0.8267757885789107, 0.806893418218578)
    a, b = channels.index('ch0'), channels.index('ch1')
    assert result.outlet_states[a].temperature_k == pytest.approx(318.5596507335328, abs=0.05)
    assert result.outlet_states[b].temperature_k == pytest.approx(308.1187791645757, abs=0.05)
    assert result.heat_w[b] == pytest.approx(50459.92078905712, rel=5e-3)


# Review findings (2026-10-11), each pinned by a regression test.

def python_line(mid, source, params=(), values=None, inlet=250000., outlet=120000., **solver):
    module = ModuleDefinition(id=mid, name=mid, runtime='python', entrypoint='module:Module', solver_model='python_x',
        source={'runtime': source},
        ports=[PortSpec(id='in0', label='in0', direction='in'), PortSpec(id='out0', label='out0', direction='out')],
        channels=[ChannelSpec(id='main', name='main', input_port='in0', output_port='out0', relation='resistance',
                              solver_model='python_x')],
        parameters=list(params))
    return project([('B1', 'source', {'pressure_pa': inlet, 'temperature_k': 293.15}), ('M1', mid, values or {}),
                    ('B2', 'source', {'pressure_pa': outlet, 'temperature_k': 293.15})],
                   [('B1:out0', 'M1:in0'), ('M1:out0', 'B2:out0')], extra_modules=[module], **solver)


OPENS_AFTER_FIRST_COMMIT = '''class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("n", 0)
    def evaluate(self, ctx):
        ctx.net.valve(channel="main", kv=10.0, opening=0.0 if ctx.state.get("n", 0) < 1 else 1.0)
    def commit_step(self, ctx, dt_s):
        ctx.state["n"] += 1
'''


# A warm start from a zero-flow frame must not stall on the zero slope of q·|q|.
@pytest.mark.parametrize('thermal', [True, False])
def test_valve_opening_between_frames_converges(thermal):
    frames = solve_dynamic(compile_project(python_line('opens', OPENS_AFTER_FIRST_COMMIT, thermal=thermal)), .3, .1)
    flows = [f.variables['M1.mass_flow_kg_s'] for f in frames]
    assert abs(flows[0]) < 1e-9 and abs(flows[1]) < 1e-9
    steady = solve_steady(compile_project(python_line('open', '''class Module:
    def evaluate(self, ctx):
        ctx.net.valve(channel="main", kv=10.0, opening=1.0)
''', thermal=thermal))).variables['M1.mass_flow_kg_s']
    assert flows[2] == pytest.approx(steady, rel=1e-9) and flows[3] == pytest.approx(steady, rel=1e-9)


# A Python pump delivers its hydraulic power to the fluid, like the built-in pump does.
def test_python_pump_shaft_work_heats_the_fluid():
    source = '''class Module:
    def evaluate(self, ctx):
        ctx.net.pump(channel="main", head_curve=[[0.,20.],[10.,18.],[20.,12.],[30.,0.]], speed_ratio=1.0)
'''
    v = solve_steady(compile_project(python_line('pypump', source, inlet=200000., outlet=250000.))).variables
    w, rise = v['M1.mass_flow_kg_s'], v['M1.outlet_pressure_pa'] - v['M1.inlet_pressure_pa']
    assert w > 0 and rise > 0
    assert v['M1.heat_w'] == pytest.approx(rise * w / RHO_WATER, rel=1e-9)
    assert v['M1.outlet_temperature_k'] > v['M1.inlet_temperature_k']


# Allowed phases are per hydraulic component: an unrelated vapour line must not let a liquid stream boil.
def test_phase_check_is_per_hydraulic_component():
    p = heater_line({'heat_w': 4.0e6})
    if not any(m.id == 'valve' for m in p.modules):
        p.modules.append(catalog_map()['valve'])
    p.instances += [ModuleInstance(id='G1', module_id='source', name='G1', parameters={'pressure_pa': 30000., 'temperature_k': 330.}),
                    ModuleInstance(id='GV', module_id='valve', name='GV', parameters={}),
                    ModuleInstance(id='G2', module_id='source', name='G2', parameters={'pressure_pa': 20000., 'temperature_k': 330.})]
    p.connections += [link('g1', 'G1:out0', 'GV:in0'), link('g2', 'GV:out0', 'G2:out0')]
    network = compile_project(p)
    # Since v0.3.1 the compiler rejects a steam boundary for water outright (its hydraulics use the
    # liquid reference density), so the vapour line is injected after compiling to exercise the
    # thermal layer's per-component phase check on its own.
    for instance_id in ('G1', 'G2'):
        network.parameters[instance_id]['temperature_k'] = 363.
        network.fixed_temperatures[network.port_nodes[f'{instance_id}:out0']] = 363.
    with pytest.raises(ThermalError) as error:
        solve_steady(network)
    assert error.value.diagnostic.code == 'PHASE_UNSUPPORTED'
    assert error.value.diagnostic.instance_id == 'H1'


# With one side reversed the exchanger runs in parallel flow and uses the parallel-flow ε.
def test_exchanger_with_one_side_reversed_uses_parallel_flow():
    network = hx_network()
    hot_node, cold_node = network.port_nodes['HX:in0'], network.port_nodes['HX:out1']
    pressures = np.zeros(len(network.node_keys))
    for node, value in network.fixed_pressures.items():
        pressures[node] = value
    # Cold side enters at out1 (its sink boundary) and leaves at in1: flow on ch1 is negative.
    flows = np.array([0.8 if b.channel_id == 'ch0' else -0.5 for b in network.branches])
    result = solve_thermal(network, WATER, pressures, flows)
    a = [b.channel_id for b in network.branches].index('ch0')
    states = result.node_states
    cp_h, cp_c = states[hot_node].specific_heat_j_kg_k, states[cold_node].specific_heat_j_kg_k
    ch, cc = 0.8 * cp_h, 0.5 * cp_c
    cmin, cmax = min(ch, cc), max(ch, cc)
    ratio, ntu = cmin / cmax, 2000. / cmin
    parallel = (1 - math.exp(-ntu * (1 + ratio))) / (1 + ratio)
    expected = parallel * cmin * (states[hot_node].temperature_k - states[cold_node].temperature_k)
    assert -result.heat_w[a] == pytest.approx(expected, rel=1e-9)
    assert -result.heat_w[a] < analytic_q(cp_h, cp_c, 0.8, 0.5, 2000., states[hot_node].temperature_k,
                                          states[cold_node].temperature_k)
