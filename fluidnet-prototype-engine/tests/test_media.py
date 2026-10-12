"""Phase A: wider fluid support - backend prefixes, INCOMP solutions, extra properties, fluid-specific limits."""
import math

import pytest
from CoolProp.CoolProp import HAPropsSI, PropsSI

from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import ChannelSpec, FluidConfig, ModuleDefinition, PortSpec
from fn_engine.properties import PropertyError, humid_air, property_service
from fn_engine.solver import solve_dynamic, solve_steady
from test_thermal import line, project

MEG30 = 'INCOMP::MEG[0.3]'


def fluid_line(fluid, kind='valve', params=None, inlet=250000., outlet=120000., t=293.15, **solver):
    p = line(kind, params, inlet=inlet, outlet=outlet, t_in=t, t_out=t, **solver)
    p.fluid = FluidConfig(fluid=fluid)
    return p


def test_meg30_pt_ph_roundtrip_and_properties():
    meg = property_service(FluidConfig(fluid=MEG30))
    state = meg.state_pt(2e5, 263.15)
    # Measured with CoolProp 8.0 (plan): rho 1047.5 kg/m³, cp 3627 J/(kg·K) at −10 °C.
    assert state.phase == 'liquid' and state.quality is None
    assert state.density_kg_m3 == pytest.approx(1047.49, abs=0.05)
    assert state.specific_heat_j_kg_k == pytest.approx(3627.07, abs=0.05)
    assert state.speed_of_sound_m_s is None and state.entropy_j_kg_k is not None
    assert meg.state_ph(2e5, state.enthalpy_j_kg).temperature_k == pytest.approx(263.15, abs=1e-9)
    # The 30 % solution freezes at about −14.6 °C, well above the correlation's Tmin.
    assert meg.limits()['t_min_k'] == pytest.approx(258.574, abs=1e-3)
    with pytest.raises(PropertyError) as error:
        meg.state_pq(2e5, .5)
    assert error.value.code == 'PROPERTY_FAILURE'


def test_meg30_loop_at_minus_10_solves():
    frame = solve_steady(compile_project(fluid_line(MEG30, params={'opening_ratio': .5, 'kv_m3_h': 10.}, t=263.15)))
    v = frame.variables
    rho = property_service(FluidConfig(fluid=MEG30)).state_pt((250000 + 120000) / 2, 263.15).density_kg_m3
    expected = 5 * math.sqrt(1.3 / (rho / 1000)) * rho / 3600
    assert v['D1.mass_flow_kg_s'] == pytest.approx(expected, rel=1e-7)
    assert v['D1.out0.temperature_k'] == pytest.approx(263.15, abs=0.2)
    assert v['D1.out0.density_kg_m3'] == pytest.approx(rho, rel=1e-3)
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line(MEG30, t=253.15))  # below the solution's freezing point
    assert error.value.diagnostic.code == 'PARAMETER_RANGE' and error.value.diagnostic.instance_id == 'B1'


def test_liquid_ammonia_at_minus_30_compiles_and_solves_while_water_is_rejected():
    frame = solve_steady(compile_project(fluid_line('Ammonia', inlet=500000., outlet=400000., t=243.15)))
    v = frame.variables
    assert v['D1.mass_flow_kg_s'] > 0
    assert v['D1.in0.density_kg_m3'] == pytest.approx(677.7, abs=0.5)
    assert v['D1.out0.temperature_k'] == pytest.approx(243.15, abs=0.1)
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line('Water', inlet=500000., outlet=400000., t=243.15))
    assert error.value.diagnostic.code == 'PARAMETER_RANGE'
    assert 'Water' in error.value.diagnostic.message and '°C' in error.value.diagnostic.message


def test_water_boundary_must_be_liquid():
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line('Water', t=423.15))  # 150 °C at 2.5 bar is steam
    # Same code the thermal layer uses for a stream leaving the liquid phase.
    assert error.value.diagnostic.code == 'PHASE_UNSUPPORTED'
    assert error.value.diagnostic.field == 'temperature_k'
    # 95 °C is outside the old 1–90 °C bound but liquid at these pressures.
    assert solve_steady(compile_project(fluid_line('Water', t=368.15))).variables['D1.mass_flow_kg_s'] > 0


# Review 2026-10-11: thermal=False keeps accepting what 0.3.0 accepted (no phase check there).
def test_thermal_off_skips_the_water_phase_check():
    compile_project(fluid_line('Water', inlet=4000., outlet=3000., t=303.15, thermal=False))
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line('Water', inlet=4000., outlet=3000., t=303.15))
    assert error.value.diagnostic.code == 'PHASE_UNSUPPORTED'


# Review: reference mode keeps the 20 °C water density; hot water gets a visible warning.
def test_reference_mode_warns_when_density_moves_away():
    hot = solve_steady(compile_project(fluid_line('Water', t=368.15)))
    warning = next(d for d in hot.diagnostics if d.code == 'REFERENCE_DENSITY_DEVIATION')
    assert warning.severity == 'warning' and 'node' in warning.message
    cool = solve_steady(compile_project(fluid_line('Water', t=303.15)))
    assert not any(d.code == 'REFERENCE_DENSITY_DEVIATION' for d in cool.diagnostics)
    node = solve_steady(compile_project(fluid_line('Water', t=368.15, property_coupling='node')))
    assert not any(d.code == 'REFERENCE_DENSITY_DEVIATION' for d in node.diagnostics)


# Review: ambient above the line's boiling point must not count latent heat as transferable.
def test_pipe_heat_from_ambient_above_boiling_is_sensible_only():
    params = {'length_m': 30., 'heat_loss_ua_w_k': 50., 'ambient_temperature_k': 423.15}
    v = solve_steady(compile_project(fluid_line('Water', 'pipe', params, inlet=130000., outlet=120000.))).variables
    w, cp = v['D1.mass_flow_kg_s'], v['D1.in0.specific_heat_j_kg_k']
    expected = 423.15 + (293.15 - 423.15) * math.exp(-50. / (w * cp))
    assert v['D1.outlet_temperature_k'] == pytest.approx(expected, abs=0.02)
    assert v['D1.heat_w'] == pytest.approx(w * cp * (expected - 293.15), rel=2e-3)


# Review: every spelling of pure water gives identical hydraulics.
def test_all_water_spellings_give_identical_hydraulics():
    flows = {f: solve_steady(compile_project(fluid_line(f))).variables['D1.mass_flow_kg_s']
             for f in ('Water', 'water', 'HEOS::Water', 'IF97::Water', ' heos :: Water ')}
    assert len(set(flows.values())) == 1, flows


def test_ambient_temperature_follows_fluid_limits():
    p = fluid_line('Water', 'pipe', {'heat_loss_ua_w_k': 10., 'ambient_temperature_k': 263.15})
    with pytest.raises(CompilationError) as error:
        compile_project(p)
    assert error.value.diagnostic.code == 'PARAMETER_RANGE' and error.value.diagnostic.field == 'ambient_temperature_k'


@pytest.mark.parametrize('fluid,pressure,temperature', [('Water', 1e6, 300.), ('HEOS::R134a', 3e5, 300.), (MEG30, 2e5, 280.)])
def test_state_ps_isentropic_roundtrip(fluid, pressure, temperature):
    service = property_service(FluidConfig(fluid=fluid))
    state = service.state_pt(pressure, temperature)
    back = service.state_ps(pressure, state.entropy_j_kg_k)
    assert back.temperature_k == pytest.approx(temperature, abs=1e-7)
    assert back.enthalpy_j_kg == pytest.approx(state.enthalpy_j_kg, rel=1e-9)


def test_saturation_queries():
    r134a = property_service(FluidConfig(fluid='HEOS::R134a'))
    assert r134a.saturation_t(3e5) - 273.15 == pytest.approx(0.672, abs=1e-3)
    water = property_service(FluidConfig())
    assert water.saturation_p(373.15) == pytest.approx(PropsSI('P', 'T', 373.15, 'Q', 0, 'Water'), rel=1e-9)
    inside = water.state_pq(3e5, .5)
    assert inside.phase == 'twophase' and inside.quality == pytest.approx(.5)
    assert inside.speed_of_sound_m_s is None and inside.viscosity_pa_s is None and inside.cv_j_kg_k is None
    assert inside.entropy_j_kg_k == pytest.approx(PropsSI('Smass', 'P', 3e5, 'Q', .5, 'Water'), rel=1e-9)
    saturated_liquid = water.state_pq(3e5, 0.)
    assert saturated_liquid.viscosity_pa_s == pytest.approx(PropsSI('V', 'P', 3e5, 'Q', 0, 'Water'), rel=1e-9)
    tq = water.state_tq(373.15, 1.)
    assert tq.pressure_pa == pytest.approx(water.saturation_p(373.15), rel=1e-9)


def test_single_phase_extras_match_coolprop():
    state = property_service(FluidConfig()).state_pt(3e5, 293.15)
    for field, key in [('entropy_j_kg_k', 'Smass'), ('internal_energy_j_kg', 'Umass'), ('cv_j_kg_k', 'Cvmass'),
                       ('speed_of_sound_m_s', 'A')]:
        assert getattr(state, field) == pytest.approx(PropsSI(key, 'P', 3e5, 'T', 293.15, 'Water'), rel=1e-9), field


ISENTROPIC = '''class Module:
    def evaluate(self, ctx):
        ctx.net.valve(channel="main", kv=10.0, opening=1.0)
    def commit_step(self, ctx, dt_s):
        inlet, outlet = ctx.port("in0"), ctx.port("out0")
        s_in = ctx.fluid.state_pt(inlet.pressure_pa, inlet.temperature_k).entropy_j_kg_k
        ctx.var("s_in", s_in)
        ctx.var("h_isentropic", ctx.fluid.state_ps(outlet.pressure_pa, s_in).enthalpy_j_kg)
        ctx.var("t_sat_out", ctx.fluid.saturation_t(outlet.pressure_pa))
'''


def test_python_module_uses_state_ps_in_commit_step():
    module = ModuleDefinition(id='isentropic', name='isentropic', runtime='python', entrypoint='module:Module',
        solver_model='python_x', source={'runtime': ISENTROPIC},
        ports=[PortSpec(id='in0', label='in0', direction='in'), PortSpec(id='out0', label='out0', direction='out')],
        channels=[ChannelSpec(id='main', name='main', input_port='in0', output_port='out0', relation='resistance',
                              solver_model='python_x')])
    p = project([('B1', 'source', {'pressure_pa': 250000., 'temperature_k': 293.15}), ('M1', 'isentropic', {}),
                 ('B2', 'source', {'pressure_pa': 120000., 'temperature_k': 293.15})],
                [('B1:out0', 'M1:in0'), ('M1:out0', 'B2:out0')], extra_modules=[module])
    v = solve_dynamic(compile_project(p), .2, .1)[-1].variables
    s_in = PropsSI('Smass', 'P', v['M1.in0.pressure_pa'], 'T', v['M1.in0.temperature_k'], 'Water')
    assert v['M1.s_in'] == pytest.approx(s_in, rel=1e-9)
    assert v['M1.h_isentropic'] == pytest.approx(PropsSI('Hmass', 'P', v['M1.out0.pressure_pa'], 'Smass', s_in, 'Water'), rel=1e-9)
    assert v['M1.t_sat_out'] == pytest.approx(PropsSI('T', 'P', v['M1.out0.pressure_pa'], 'Q', 0, 'Water'), rel=1e-9)


@pytest.mark.parametrize('fluid,code', [('NotAFluid', 'FLUID_UNKNOWN'), ('INCOMP::NotASolution', 'FLUID_UNKNOWN'),
                                        ('REFPROP::Water', 'PROPERTY_BACKEND_UNSUPPORTED'),
                                        ('Methane&Ethane', 'COMPOSITION_UNSUPPORTED'),
                                        ('HEOS::Water[0.5]', 'COMPOSITION_UNSUPPORTED'),
                                        ('INCOMP::MEG[1.5]', 'PROPERTY_RANGE'),
                                        # Inside (0, 1) but outside the correlation (0–0.6): range, not failure.
                                        ('INCOMP::MEG[0.9]', 'PROPERTY_RANGE')])
def test_bad_fluid_strings_fail_at_compile_time(fluid, code):
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line(fluid))
    assert error.value.diagnostic.code == code
    assert error.value.diagnostic.field == 'fluid'


def test_whitespace_inside_fraction_syntax_is_ignored():
    assert property_service(FluidConfig(fluid=' INCOMP :: MEG [0.3] ')).key == ('INCOMP', 'MEG', (0.3,))


def test_unknown_fluid_query_keeps_property_failure():
    with pytest.raises(PropertyError) as error:
        property_service(FluidConfig(fluid='NotAFluid')).state_pt(3e5, 293.15)
    assert error.value.code == 'PROPERTY_FAILURE'


def test_prefixed_and_bare_names_share_one_fluid():
    bare, prefixed = property_service(FluidConfig(fluid='Water')), property_service(FluidConfig(fluid='HEOS::Water'))
    assert bare.key == prefixed.key == ('HEOS', 'Water', ())
    assert bare.state_pt(3e5, 293.15).density_kg_m3 == prefixed.state_pt(3e5, 293.15).density_kg_m3


def test_humid_air_matches_hapropssi():
    result = humid_air(298.15, 101325., .6)
    for key, code in [('humidity_ratio_kg_kg', 'W'), ('dew_point_k', 'D'), ('wet_bulb_k', 'B'), ('enthalpy_j_kg_dry_air', 'H')]:
        assert result[key] == pytest.approx(HAPropsSI(code, 'T', 298.15, 'P', 101325., 'R', .6), rel=1e-12), key
    assert property_service(FluidConfig(fluid='Air')).humid_air(298.15, 101325., .6) == result
    with pytest.raises(PropertyError) as error:
        humid_air(298.15, 101325., 1.5)
    assert error.value.code == 'PROPERTY_RANGE'
