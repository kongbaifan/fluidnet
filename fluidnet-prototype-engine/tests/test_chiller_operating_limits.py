"""E09: final-point flow protection and conservative cycle-averaged low-load operation."""
from copy import deepcopy
import csv
from io import StringIO

from fastapi.testclient import TestClient
import numpy as np
import pytest
from scipy.optimize import least_squares

from fn_engine.air_variables import collect_air_variables
from fn_engine.air_examples import air_example
from fn_engine.api import create_app
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.refrigeration.cycle import DeviceRangeError, cycle_rates, rated_displacement
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady
from fn_engine.water_chiller import check_chiller_flow_limits, evaluate_chiller, refrigerant_service
from test_chiller_air_loop import water_only_project
from test_water_chiller import PARAMS, WATER, run


def test_minimum_load_on_point_matches_independent_balance():
    e, c, result = run(t_in=281.15, minimum_load_ratio=.3)
    outputs = result['outputs']
    assert outputs['low_load_cycling']
    service = refrigerant_service(PARAMS)
    displacement = rated_displacement(service, PARAMS)
    ge = e.specific_heat_j_kg_k * -np.expm1(-PARAMS['evaporator_ua_w_k']/e.specific_heat_j_kg_k)
    cc = 1.6*c.specific_heat_j_kg_k
    gc = cc*-np.expm1(-PARAMS['condenser_ua_w_k']/cc)

    def residual(x):
        rates = cycle_rates(service, PARAMS, displacement, x[0], x[1], .3)
        return [(ge*(e.temperature_k-x[0])-rates['cooling_w'])/1000.,
                (gc*(x[1]-c.temperature_k)-rates['rejection_w'])/1000.]

    solution = least_squares(residual, [278., 307.], xtol=1e-13, ftol=1e-13, gtol=1e-13)
    assert np.linalg.norm(solution.fun) < 1e-8
    assert outputs['evaporating_temperature_k'] == pytest.approx(solution.x[0], abs=1e-7)
    assert outputs['condensing_temperature_k'] == pytest.approx(solution.x[1], abs=1e-7)
    on = cycle_rates(service, PARAMS, displacement, *solution.x, .3)
    duty = outputs['cycling_ratio']
    assert 0. < duty < 1.
    assert outputs['compressor_load_ratio'] == .3
    assert outputs['load_ratio'] == pytest.approx(.3*duty)
    assert outputs['cooling_power_w'] == pytest.approx(duty*on['cooling_w'], rel=1e-9)
    assert outputs['condenser_heat_w'] == pytest.approx(duty*on['rejection_w'], rel=1e-9)
    assert outputs['condenser_heat_w'] == pytest.approx(outputs['cooling_power_w']+outputs['shaft_power_w'], rel=1e-12)
    assert outputs['electric_power_w'] == pytest.approx(outputs['shaft_power_w']/PARAMS['motor_efficiency'])
    assert e.enthalpy_j_kg-result['evaporator_outlet_h'] == pytest.approx(outputs['cooling_power_w'])
    assert 1.6*(result['condenser_outlet_h']-c.enthalpy_j_kg) == pytest.approx(outputs['condenser_heat_w'])
    assert WATER.state_ph(240000., result['evaporator_outlet_h']).temperature_k == pytest.approx(280.15, abs=1e-9)
    assert result['on_evaporator_outlet_h'] < result['evaporator_outlet_h']
    assert abs(outputs['evaporator_equation_residual_w']) < 1e-6
    assert abs(outputs['condenser_equation_residual_w']) < 1e-6


def test_cycle_averaged_transition_is_continuous():
    baseline = run(t_in=281.15)[2]['outputs']
    threshold = baseline['load_ratio']
    below = run(t_in=281.15, minimum_load_ratio=threshold*(1.-1e-6))[2]['outputs']
    above = run(t_in=281.15, minimum_load_ratio=threshold*(1.+1e-6))[2]['outputs']
    assert not below['low_load_cycling'] and below['cycling_ratio'] == 1.
    assert above['low_load_cycling'] and above['cycling_ratio'] == pytest.approx(1., abs=2e-6)
    for key in ('cooling_power_w', 'condenser_heat_w', 'electric_power_w'):
        assert above[key] == pytest.approx(baseline[key], rel=2e-6)


def test_average_outlet_cannot_hide_on_point_outside_operating_envelope():
    assert run(t_in=281.15, min_evaporating_temperature_k=278.)[2]['active']
    with pytest.raises(DeviceRangeError) as exc:
        run(t_in=281.15, minimum_load_ratio=.5, min_evaporating_temperature_k=278.)
    assert exc.value.code == 'REFRIGERATION_ENVELOPE'


def test_frozen_legacy_parameters_preserve_default_results():
    e, c, result = run()
    old = {key:value for key,value in PARAMS.items()
           if key not in ('minimum_load_ratio', 'evaporator_min_flow_kg_s', 'condenser_min_flow_kg_s')}
    assert evaluate_chiller(e, 1., c, 1.6, old, WATER, 240000., check=True) == result


@pytest.mark.parametrize('side,flow', [('evaporator', 1.), ('condenser', 1.6)])
def test_final_flow_limit_boundary_and_disabled_machine(side, flow):
    field = f'{side}_min_flow_kg_s'
    assert run(**{field:flow})[2]['active']
    with pytest.raises(DeviceRangeError) as exc:
        run(**{field:flow+1e-6})
    assert exc.value.code == f'CHILLER_{side.upper()}_LOW_FLOW'
    assert exc.value.field == field
    assert run(check=False, **{field:flow+1e-6})[2]['active']
    assert not run(running=0., **{field:flow+1e-6})[2]['active']


def test_disabled_flow_limits_preserve_the_existing_reverse_flow_tolerance():
    check_chiller_flow_limits(PARAMS, -1e-10, -1e-10)
    assert not run(m_e=-1e-10, m_c=-1e-10)[2]['active']
    with pytest.raises(DeviceRangeError) as exc:
        run(m_e=-1e-8)
    assert exc.value.code == 'CHILLER_REVERSE_FLOW'


def test_minimum_flow_waits_for_water_density_convergence():
    project = water_only_project()
    # Initial reference-density flow is 1.240752; the converged water flow is 1.241668 kg/s.
    limit = 1.2412101773242676
    project.instances[0].parameters['evaporator_min_flow_kg_s'] = limit
    frame = solve_steady(compile_project(project))
    assert frame.valid and frame.variables['Chiller.ch0.mass_flow_kg_s'] > limit
    assert frame.variables['Chiller.ch0.mass_flow_kg_s'] == pytest.approx(1.2416682034677313, rel=1e-8)


@pytest.mark.parametrize('side,channel,limit', [('evaporator', 'ch0', 1.1694), ('condenser', 'ch1', 3.558)])
def test_minimum_flow_waits_for_air_water_density_convergence(side, channel, limit):
    project = air_example('chiller-air-loop')
    # Both thresholds sit above the first property iterate and below the converged flow.
    next(i for i in project.instances if i.id == 'Chiller').parameters[f'{side}_min_flow_kg_s'] = limit
    frame = solve_steady(compile_project(project))
    assert frame.valid and frame.variables[f'Chiller.{channel}.mass_flow_kg_s'] > limit


@pytest.mark.parametrize('coupling', ['reference', 'node', 'moist_air'])
@pytest.mark.parametrize('side', ['evaporator', 'condenser'])
def test_final_network_flow_still_rejects_a_real_shortfall(coupling, side):
    project = air_example('chiller-air-loop') if coupling == 'moist_air' else water_only_project()
    if coupling != 'moist_air':
        project.solver.property_coupling = coupling
    field = f'{side}_min_flow_kg_s'
    next(i for i in project.instances if i.id == 'Chiller').parameters[field] = 4.
    with pytest.raises(CompilationError) as exc:
        solve_steady(compile_project(project))
    assert exc.value.diagnostic.code == f'CHILLER_{side.upper()}_LOW_FLOW'
    assert exc.value.diagnostic.instance_id == 'Chiller' and exc.value.diagnostic.field == field


@pytest.mark.parametrize('field,value', [('minimum_load_ratio', -0.1), ('minimum_load_ratio', 1.1),
    ('evaporator_min_flow_kg_s', -1.), ('condenser_min_flow_kg_s', -1.)])
def test_operating_parameters_reject_out_of_range(field, value):
    project = water_only_project()
    project.instances[0].parameters[field] = value
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code == 'PARAMETER_RANGE'


def test_stopped_machine_retains_real_water_resistance():
    project = water_only_project()
    project.instances[0].parameters.update(running=0., evaporator_min_flow_kg_s=99., condenser_min_flow_kg_s=99.)
    frame = solve_steady(compile_project(project))
    v = frame.variables
    for channel in ('ch0', 'ch1'):
        assert v[f'Chiller.{channel}.mass_flow_kg_s'] > 0
        assert v[f'Chiller.{channel}.pressure_drop_pa'] == pytest.approx(1000., abs=1e-6)
    for side in (0, 1):
        assert v[f'Chiller.in{side}.enthalpy_j_kg'] == pytest.approx(v[f'Chiller.out{side}.enthalpy_j_kg'])
    assert v['Chiller.cooling_power_w'] == v['Chiller.electric_power_w'] == v['Chiller.cycling_ratio'] == 0.


@pytest.mark.parametrize('side,source', [('evaporator', 'A'), ('condenser', 'C')])
def test_low_flow_failure_does_not_advance_accepted_energy_or_time(side, source):
    project = water_only_project()
    project.instances[0].parameters.update(minimum_load_ratio=.5, **{f'{side}_min_flow_kg_s':1.2})
    next(i for i in project.instances if i.id == 'A').parameters['temperature_k'] = 281.15
    session = SimulationSession(compile_project(project), 4., 2.)
    try:
        session.initialize()
        session.advance()
        accepted = session.snapshot()
        accepted_frame = deepcopy(session.last_accepted_frame)
        ledger = deepcopy(session.air_accumulators)
        assert accepted.variables['Chiller.low_load_cycling']
        assert ledger['Chiller']['electric_energy_j'] == pytest.approx(2.*accepted.variables['Chiller.electric_power_w'])
        session.set_parameter(source, 'pressure_pa', 200900.)
        with pytest.raises(CompilationError) as exc:
            session.advance()
        assert exc.value.diagnostic.code == f'CHILLER_{side.upper()}_LOW_FLOW'
        assert session.time == 2. and session.air_accumulators == ledger
        assert session.last_accepted_frame == accepted_frame
    finally:
        session.close()


def test_average_model_fields_have_frozen_report_units():
    fields = {v.key:v for v in collect_air_variables(water_only_project())}
    assert fields['Chiller.low_load_cycling'].value_type == 'boolean'
    assert fields['Chiller.cycling_ratio'].unit.display_unit == '%'
    assert fields['Chiller.param.evaporator_min_flow_kg_s'].unit.canonical_unit == 'kg/s'


def test_cycle_average_closes_all_three_circuits():
    project = air_example('chiller-air-loop')
    next(i for i in project.instances if i.id == 'Chiller').parameters['minimum_load_ratio'] = .7
    frame = solve_steady(compile_project(project))
    v = frame.variables
    assert frame.valid and frame.metrics['reference_heat_w'] == 0.
    assert v['Chiller.low_load_cycling'] and 0. < v['Chiller.cycling_ratio'] < 1.
    assert v['Chiller.out0.temperature_k'] == pytest.approx(280.15, abs=1e-5)
    assert v['Chiller.cooling_power_w'] == pytest.approx(v['Coil.water_heat_w']+v['ChilledPump.shaft_power_w'], abs=.03)
    assert v['Tower.heat_rejected_w'] == pytest.approx(v['Chiller.condenser_heat_w']+v['CoolingPump.shaft_power_w'], abs=.03)
    assert v['Chiller.condenser_heat_w'] == pytest.approx(v['Chiller.cooling_power_w']+v['Chiller.shaft_power_w'], abs=1e-7)


def test_average_model_api_reports_and_restart_preserve_the_snapshot(tmp_path):
    project = water_only_project()
    project.instances[0].parameters['minimum_load_ratio'] = .5
    next(i for i in project.instances if i.id == 'A').parameters['temperature_k'] = 281.15
    with TestClient(create_app(data_root=tmp_path)) as client:
        response = client.post('/api/v1/runs', json={'project':project.model_dump(mode='json'),
            'mode':'dynamic', 'duration_s':2., 'dt_s':2.})
        assert response.status_code == 201 and response.json()['status'] == 'completed', response.text
        rid = response.json()['run_id']
        record = client.get(f'/api/v1/runs/{rid}').json()
        duty = record['frame']['variables']['Chiller.cycling_ratio']
        assert 0. < duty < 1.
        html = client.get(f'/api/v1/runs/{rid}/report.html').text
        assert '周期平均运行' in html and '不表示已模拟真实启停次数或时间' in html
        rows = list(csv.DictReader(StringIO(client.get(f'/api/v1/runs/{rid}/report.csv').content.decode('utf-8-sig'))))
        row = next(row for row in rows if row['变量键'] == 'Chiller.cycling_ratio' and float(row['时间(s)']) == 2.)
        assert row['显示单位'] == '%' and float(row['显示数值']) == pytest.approx(100.*duty)
    with TestClient(create_app(data_root=tmp_path)) as client:
        restored = client.get(f'/api/v1/runs/{rid}').json()
        assert restored['air_metadata'] == record['air_metadata']
        assert restored['frame']['variables']['Chiller.cycling_ratio'] == duty
