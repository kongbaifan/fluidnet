"""REFPROP backend. Needs a licensed REFPROP (FLUIDNET_REFPROP_PATH or the default install); skipped otherwise."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from CoolProp.CoolProp import PropsSI

from fn_engine import properties
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import FluidConfig
from fn_engine.properties import PropertyError, property_service, refprop_root
from fn_engine.solver import solve_steady
from test_media import fluid_line

ROOT = refprop_root()
needs_refprop = pytest.mark.skipif(ROOT is None, reason='REFPROP 未安装')


def service(fluid, reference='mass'):
    return property_service(FluidConfig(fluid=fluid, reference=reference))


def test_missing_installation_is_reported_at_compile_time(monkeypatch, tmp_path):
    monkeypatch.setenv('FLUIDNET_REFPROP_PATH', str(tmp_path))
    monkeypatch.setattr(properties, '_configured', [])
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line('REFPROP::WATER'))
    assert error.value.diagnostic.code == 'PROPERTY_BACKEND_UNSUPPORTED'
    assert 'FLUIDNET_REFPROP_PATH' in str(error.value)


@needs_refprop
@pytest.mark.parametrize('refprop, heos, p, t', [('WATER', 'Water', 5e5, 293.15), ('R134A', 'R134a', 2e6, 283.15),
                                                ('CO2', 'CarbonDioxide', 5e5, 293.15)])
def test_pure_fluids_agree_with_coolprop_heos(refprop, heos, p, t):
    state = service('REFPROP::' + refprop).state_pt(p, t)
    assert state.density_kg_m3 == pytest.approx(PropsSI('D', 'P', p, 'T', t, heos), rel=1e-9)
    assert state.enthalpy_j_kg == pytest.approx(PropsSI('H', 'P', p, 'T', t, heos), rel=1e-6)
    assert state.viscosity_pa_s == pytest.approx(PropsSI('V', 'P', p, 'T', t, heos), rel=1e-3)


@needs_refprop
def test_zeotropic_mixture_glides_and_reports_its_phase():
    r407c = service('REFPROP::R407C.MIX')
    bubble, dew = r407c.state_pq(1e6, 0.).temperature_k, r407c.state_pq(1e6, 1.).temperature_k
    assert dew - bubble == pytest.approx(5.63, abs=.05)
    assert r407c.saturation_t(1e6) == bubble
    assert r407c.state_pt(2e6, 273.15).phase == 'liquid'
    assert r407c.state_pt(5e5, 293.15).phase == 'gas'
    middle = property_service(FluidConfig(fluid='REFPROP::R407C.MIX', phase_policy='any')).state_ph(5e5, 3e5)
    assert middle.phase == 'twophase' and 0 < middle.quality < 1
    assert middle.viscosity_pa_s is None and middle.specific_heat_j_kg_k is None
    with pytest.raises(PropertyError) as error:
        property_service(FluidConfig(fluid='REFPROP::R407C.MIX', phase_policy='liquid')).state_pt(5e5, 293.15)
    assert error.value.code == 'PHASE_UNSUPPORTED'


@needs_refprop
def test_component_mixtures_follow_the_configured_basis():
    by_mass = service('REFPROP::R32[0.5]&R125[0.5]')
    r410a = service('REFPROP::R410A.MIX')
    assert by_mass.state_pt(2e6, 273.15).density_kg_m3 == pytest.approx(r410a.state_pt(2e6, 273.15).density_kg_m3, rel=1e-4)
    assert by_mass.state_pt(2e6, 273.15).composition == {'R32': .5, 'R125': .5}
    # Equal moles carry more of the heavier R125 (120 g/mol vs 52 g/mol): a denser liquid.
    by_mole = service('REFPROP::R32[0.5]&R125[0.5]', reference='mole')
    assert by_mole.state_pt(2e6, 273.15).density_kg_m3 == pytest.approx(1232.77, rel=1e-4)
    assert by_mole.state_pt(2e6, 273.15).composition == {'R32': .5, 'R125': .5}


@needs_refprop
def test_mixture_without_transport_equations_is_rejected_for_hydraulics():
    ammonia_water = service('REFPROP::AMMONIA[0.3]&WATER[0.7]')
    state = ammonia_water.state_pt(5e5, 293.15)
    assert state.viscosity_pa_s is None and state.density_kg_m3 > 800
    network = compile_project(fluid_line('REFPROP::AMMONIA[0.3]&WATER[0.7]'))
    with pytest.raises(ValueError, match='黏度'):
        solve_steady(network)


@needs_refprop
@pytest.mark.parametrize('fluid, code', [('REFPROP::NOTAFLUID', 'FLUID_UNKNOWN'),
                                        ('REFPROP::R32[0.4]&R125[0.4]', 'PROPERTY_RANGE'),
                                        ('REFPROP::R32&R125', 'PROPERTY_RANGE'),
                                        ('REFPROP::WATER[0.5]', 'COMPOSITION_UNSUPPORTED')])
def test_bad_refprop_strings_fail_at_compile_time(fluid, code):
    with pytest.raises(CompilationError) as error:
        compile_project(fluid_line(fluid))
    assert error.value.diagnostic.code == code


@needs_refprop
def test_network_with_refprop_r134a_matches_heos():
    liquid = dict(inlet=30e5, outlet=28e5, t=283.15)
    refprop = solve_steady(compile_project(fluid_line('REFPROP::R134A', **liquid)))
    heos = solve_steady(compile_project(fluid_line('HEOS::R134a', **liquid)))
    for key, value in heos.variables.items():
        if isinstance(value, float):
            assert refprop.variables[key] == pytest.approx(value, rel=1e-6, abs=1e-6), key


def test_prototype_fluid_string_overrides_the_preset_medium():
    import json
    from fn_engine.bridge import normalize_prototype_export
    raw = json.loads((Path(__file__).parent / 'fixtures' / 'prototype.json').read_text(encoding='utf-8'))
    active = next(p for p in raw['projects'] if p['id'] == raw['activeProject'])
    active.update(fluid=' REFPROP::R32[0.5]&R125[0.5] ', fluidReference='mole')
    fluid = normalize_prototype_export(raw).fluid
    assert (fluid.fluid, fluid.reference) == ('REFPROP::R32[0.5]&R125[0.5]', 'mole')
    active.update(fluid='', fluidReference='mass', medium='r134a')
    assert normalize_prototype_export(raw).fluid.fluid == 'R134a'


@needs_refprop
def test_concurrent_queries_of_different_fluids_are_serialized():
    water, r134a = service('REFPROP::WATER'), service('REFPROP::R134A')
    temperatures = [283.15 + i * .013 for i in range(300)]

    def run(fluid):
        target = water if fluid == 'Water' else r134a
        return [target.state_pt(3e6, t).density_kg_m3 for t in temperatures]
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(run, ['Water', 'R134a'] * 2))
    for fluid, densities in zip(['Water', 'R134a'] * 2, results):
        assert densities == pytest.approx([PropsSI('D', 'P', 3e6, 'T', t, fluid) for t in temperatures], rel=1e-9)


@needs_refprop
def test_fluid_files_of_another_version_fail_without_killing_the_server(tmp_path):
    """A REFPROP 9.1 DLL aborts in Fortran on REFPROP 10 fluid files; only the probe process dies."""
    newer = Path(__file__).resolve().parents[2] / 'AddIns'
    if not (newer / 'FLUIDS' / 'WATER.FLD').is_file() or '10.0' not in (newer / 'FLUIDS' / 'WATER.FLD').read_text(errors='ignore'):
        pytest.skip('没有另一版本的工质文件')
    shutil.copy(ROOT / properties.REFPROP_LIBRARY, tmp_path)
    shutil.copytree(newer / 'FLUIDS', tmp_path / 'fluids')
    shutil.copytree(newer / 'MIXTURES', tmp_path / 'mixtures')
    code = ("from fn_engine.compiler import compile_project, CompilationError\n"
            "from test_media import fluid_line\n"
            "try:\n    compile_project(fluid_line('REFPROP::WATER'))\n"
            "except CompilationError as e:\n    print('CODE', e.diagnostic.code)\n")
    env = os.environ | {'FLUIDNET_REFPROP_PATH': str(tmp_path),
                        'PYTHONPATH': os.pathsep.join([str(Path(__file__).parent)] + sys.path)}
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, timeout=120)
    assert done.returncode == 0, done.stderr[-500:]
    assert 'CODE PROPERTY_FAILURE' in done.stdout
