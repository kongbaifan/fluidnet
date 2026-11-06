"""Horizontal cylinder geometry, saturated inventories and composable station behaviour."""
import math

from CoolProp.CoolProp import PropsSI
import pytest
from scipy.integrate import quad

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project, validated_parameters
from fn_engine.models import FluidConfig, ModuleInstance
from fn_engine.properties import property_service
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.modular_examples import modular_cascade_example
from fn_engine.refrigeration.vessel_geometry import (
    horizontal_height_ratio, horizontal_volume, horizontal_volume_fraction,
)
from fn_engine.solver import solve_dynamic


def defaults(module_id):
    return {p.id:p.default for p in catalog_map()[module_id].parameters}


@pytest.mark.parametrize('ratio', [0., 1e-12, .001, .01, .1, .25, .5, .75, .9, .999, 1.-1e-12, 1.])
def test_circle_segment_matches_independent_integral_and_roundtrips(ratio):
    # Unit diameter circle: integrate its horizontal chord from the bottom to h.
    expected = quad(lambda h: 2.*math.sqrt(max(0., .25-(h-.5)**2)), 0., ratio,
                    epsabs=1e-12, epsrel=1e-12)[0]/(math.pi/4.)
    fraction = horizontal_volume_fraction(ratio)
    assert fraction == pytest.approx(expected, abs=1e-10)
    if fraction == 1. and ratio < 1.:
        # Near full, the remaining cap volume can be below one double-precision ulp.
        assert 1.-ratio < 2e-11
    else:
        assert horizontal_height_ratio(fraction) == pytest.approx(ratio, abs=2e-13)
    assert horizontal_volume_fraction(1.-ratio) == pytest.approx(1.-fraction, abs=1e-14)


def test_geometry_is_monotone_at_endpoints_and_differs_from_vertical_level():
    values = [i/1000. for i in range(1001)]
    fractions = [horizontal_volume_fraction(v) for v in values]
    heights = [horizontal_height_ratio(v) for v in values]
    assert all(a < b for a,b in zip(fractions, fractions[1:]))
    assert all(a < b for a,b in zip(heights, heights[1:]))
    assert horizontal_height_ratio(0.) == 0. and horizontal_height_ratio(1.) == 1.
    assert horizontal_height_ratio(.5) == .5
    assert horizontal_volume_fraction(.25) == pytest.approx(1./3.-math.sqrt(3.)/(4.*math.pi), abs=1e-14)
    assert horizontal_height_ratio(.25) > .25
    assert horizontal_volume(1.2, 3.) == pytest.approx(math.pi*1.2**2*3./4.)
    for fraction in (1e-18, 1e-12, 1e-6):
        assert horizontal_volume_fraction(horizontal_height_ratio(fraction)) == pytest.approx(fraction, rel=1e-10)


@pytest.mark.parametrize('value', [-.01, 1.01, float('nan'), float('inf')])
def test_geometry_rejects_invalid_fractions(value):
    with pytest.raises(ValueError): horizontal_volume_fraction(value)
    with pytest.raises(ValueError): horizontal_height_ratio(value)


@pytest.mark.parametrize('diameter,length', [(0.,1.), (1.,0.), (-1.,2.), (float('nan'),2.), (1.,float('inf'))])
def test_geometry_rejects_invalid_dimensions(diameter, length):
    with pytest.raises(ValueError): horizontal_volume(diameter, length)


@pytest.mark.parametrize('fluid,t', [('Ammonia', 243.15), ('CarbonDioxide', 248.15)])
@pytest.mark.parametrize('fraction', [.1, .25, .5, .75, .9])
def test_horizontal_inventory_and_height_follow_independent_properties(fluid, t, fraction):
    params = defaults('horizontal_drum') | {'temperature_k':t, 'level_ratio':fraction}
    service = property_service(FluidConfig(fluid=fluid, phase_policy='any'))
    volume = math.pi*params['diameter_m']**2*params['length_m']/4.
    liquid = fraction*volume*PropsSI('D', 'T', t, 'Q', 0, fluid)
    vapor = (1.-fraction)*volume*PropsSI('D', 'T', t, 'Q', 1, fluid)
    mass, energy = devices.vessel_initial(service, params)
    assert mass == pytest.approx(liquid+vapor, rel=1e-8)
    assert energy == pytest.approx(liquid*PropsSI('U','T',t,'Q',0,fluid)+vapor*PropsSI('U','T',t,'Q',1,fluid), rel=1e-8)
    state = devices.vessel_state(service, params, mass, energy)
    assert state.level_ratio == pytest.approx(fraction, abs=1e-9)
    assert state.level_height_ratio == pytest.approx(horizontal_height_ratio(fraction), abs=1e-9)
    assert state.level_m == pytest.approx(params['diameter_m']*state.level_height_ratio)
    assert state.volume_m3 == volume
    assert state.pressure_pa == pytest.approx(PropsSI('P','T',t,'Q',0,fluid), rel=1e-7)
    values = state.variables('Receiver-A')
    assert values['Receiver-A.state.level_height_ratio'] == state.level_height_ratio
    assert values['Receiver-A.volume_m3'] == volume


@pytest.mark.parametrize('module_id', ['horizontal_receiver', 'horizontal_drum'])
def test_new_geometry_contract_has_no_conflicting_independent_volume(module_id):
    definition = catalog_map()[module_id]
    instance = ModuleInstance(id='User-Vessel', module_id=module_id, name='任意容器')
    params = validated_parameters(instance, definition)
    assert {'diameter_m', 'length_m'} <= params.keys()
    assert not {'volume_m3', 'height_m'} & params.keys()
    for key, value in (('volume_m3',1.), ('height_m',1.), ('diameter_m',0.), ('length_m',-.1)):
        with pytest.raises(CompilationError) as exc:
            validated_parameters(instance.model_copy(update={'parameters':{key:value}}), definition)
        assert exc.value.diagnostic.code == ('UNKNOWN_PARAMETER' if key in ('volume_m3','height_m') else 'PARAMETER_RANGE')


def test_legacy_definition_and_geometry_remain_unchanged():
    definition = catalog_map()['hp_receiver']
    params = defaults('hp_receiver')
    instance = ModuleInstance(id='Old', module_id=definition.id, name='原容器')
    assert validated_parameters(instance, definition) == params
    assert not {'diameter_m','length_m'} & params.keys()
    # Unregistered aliases retain the prior solver-model fallback.
    alias = definition.model_copy(update={'id':'custom-vessel'})
    assert validated_parameters(instance, alias) == params
    service = property_service(FluidConfig(fluid='Ammonia',phase_policy='any'))
    state = devices.vessel_state(service, params, *devices.vessel_initial(service, params))
    assert state.level_m == pytest.approx(state.level_ratio*params['height_m'])
    assert state.level_height_ratio is None and state.volume_m3 is None
    assert 'Old.state.level_height_ratio' not in state.variables('Old')


def horizontal_cascade():
    project = modular_cascade_example()
    catalog = catalog_map()
    for instance in project.instances:
        if instance.id in ('Low', 'High'):
            instance.module_id = 'horizontal_drum' if instance.id == 'Low' else 'horizontal_receiver'
            volume = instance.parameters.pop('volume_m3')
            instance.parameters.pop('height_m')
            instance.parameters.update(diameter_m=.6, length_m=4.*volume/(math.pi*.6**2))
    project.modules = [catalog[key] for key in {i.module_id for i in project.instances}]
    return project


def test_same_volume_geometry_changes_height_not_mass_energy_or_pressure():
    vertical = modular_cascade_example()
    horizontal = horizontal_cascade()
    a = solve_dynamic(compile_project(vertical), 30., 30.)[-1].variables
    b = solve_dynamic(compile_project(horizontal), 30., 30.)[-1].variables
    for iid in ('Low', 'High'):
        for field in ('pressure_pa', 'mass_kg', 'internal_energy_j', 'level_ratio'):
            assert b[f'{iid}.state.{field}'] == pytest.approx(a[f'{iid}.state.{field}'], rel=1e-8)
    assert b['Low.state.level_m'] != pytest.approx(a['Low.state.level_m'])


def test_horizontal_modules_compose_and_preserve_station_inventory_and_energy():
    project = horizontal_cascade()
    next(i for i in project.instances if i.id == 'Room').parameters['heat_input_w'] += 1000.
    frames = solve_dynamic(compile_project(project), 120., 30.)
    assert all(frame.valid for frame in frames)
    a, b = frames[0].variables, frames[-1].variables
    assert b['Low.state.mass_kg']+b['High.state.mass_kg'] == pytest.approx(a['Low.state.mass_kg']+a['High.state.mass_kg'], abs=1e-8)
    assert b['Secondary.state.mass_kg'] == pytest.approx(a['Secondary.state.mass_kg'], abs=1e-8)
    assert abs(frames[-1].metrics['energy_residual_j']) < .05
    for iid in ('Low', 'High'):
        assert b[f'{iid}.state.level_m'] == pytest.approx(.6*b[f'{iid}.state.level_height_ratio'])
        assert horizontal_volume_fraction(b[f'{iid}.state.level_height_ratio']) == pytest.approx(b[f'{iid}.state.level_ratio'])
    assert b['Low.state.level_height_ratio'] != pytest.approx(b['Low.state.level_ratio'], abs=.01)
