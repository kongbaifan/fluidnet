"""Author laws are evaluated by Workers; inventories and acceptance stay in the host."""
import json

import pytest

from fn_engine.bench import run_module_test
from fn_engine.compiler import compile_project
from fn_engine.model_types.module import ModuleDefinition
from fn_engine.models import FluidConfig, ModuleTestRequest
from fn_engine.module_contracts import check_module_compatibility
from fn_engine.refrigeration.author_examples import definition
from fn_engine.refrigeration.modular_examples import modular_room_example
from fn_engine.refrigeration.module_adapter import evaluate_constitutive
from fn_engine.refrigeration_physics import PhysicsInput, validate_result
from fn_engine.runtime import WorkerProcess, module_content_hash, module_definition_hash
from fn_engine.properties import property_service
from fn_engine.sessions import create_session


def project():
    value = modular_room_example()
    authors = [definition('compressor'), definition('condenser')]
    lookup = {'refrigerant_compressor': authors[0].id, 'evaporative_condenser': authors[1].id}
    for instance in value.instances:
        instance.module_id = lookup.get(instance.module_id, instance.module_id)
    value.modules.extend(authors)
    return value


def test_schema5_roundtrip_and_preexecution_negotiation():
    from jsonschema import Draft202012Validator
    for kind in ('compressor', 'condenser'):
        module = definition(kind)
        restored = ModuleDefinition.model_validate_json(module.model_dump_json())
        assert module_definition_hash(restored) == module.definition_hash
        Draft202012Validator(ModuleDefinition.model_json_schema()).validate(module.model_dump(mode='json'))
        check_module_compatibility(module)
        module.sdk.api_version = '0.10.0'
        with pytest.raises(ValueError, match='0.11.0'):
            check_module_compatibility(module)


@pytest.mark.parametrize('kind', ['compressor', 'condenser'])
def test_public_bench_runs_new_roles_and_commits_only_accepted_time(kind):
    result = run_module_test(ModuleTestRequest(module=definition(kind), duration_s=.2, dt_s=.1))
    assert result.frame.valid
    assert result.constitutive_evaluation['result']
    assert len(result.history) == 3
    if kind == 'compressor':
        values = result.frame.variables
        assert values['D1.mass_flow_kg_s'] > 0
        assert values['D1.shaft_power_w'] == pytest.approx(values['D1.mass_flow_kg_s'] * (
            values['D1.discharge_enthalpy_j_kg'] - values['D1.suction_enthalpy_j_kg']))
        assert result.committed.state['accepted_seconds'] == .2
    else:
        assert result.frame.variables['D1.heat_rejection_w'] > 0


def test_station_serialization_inventory_conservation_and_worker_state():
    from fn_engine.model_types.domain import Project
    value = Project.model_validate_json(project().model_dump_json())
    session = create_session(compile_project(value), .2, .1, keep=8)
    try:
        first = session.initialize()
        final = session.advance()
        assert final.time_s == .1
        assert abs(final.metrics['energy_residual_j']) < .01
        assert all(abs(value) < 1e-6 for key, value in final.metrics.items() if key.startswith('mass_residual_kg_'))
        compressor = next(key for key, runner in session.runners.items() if runner.definition.id == 'author_compressor')
        assert final.variables[compressor + '.mass_flow_kg_s'] > 0
        assert session.runners[compressor].state['accepted_seconds'] == .1
        assert first.time_s == 0.
    finally:
        session.close()


@pytest.mark.parametrize('failure', ['energy', 'electric', 'isentropic', 'disabled', 'nan'])
def test_invalid_compressor_physics_rejected(failure):
    point = PhysicsInput(kind='compressor', inlet_pressure_pa=1e5, outlet_pressure_pa=1e6,
        inlet_temperature_k=250., inlet_enthalpy_j_kg=1000., inlet_density_kg_m3=10.,
        isentropic_outlet_enthalpy_j_kg=2000., sink_temperature_k=250., enabled=failure != 'disabled')
    values = dict(mass_flow_kg_s=.1, outlet_enthalpy_j_kg=3000., shaft_power_w=200., electric_power_w=220.)
    if failure == 'energy': values['shaft_power_w'] = 201.
    if failure == 'electric': values['electric_power_w'] = 199.
    if failure == 'isentropic': values.update(outlet_enthalpy_j_kg=1500., shaft_power_w=50.)
    if failure == 'nan': values['mass_flow_kg_s'] = float('nan')
    with pytest.raises(ValueError):
        validate_result(values, point)


def test_worker_rejects_energy_creation_and_retains_accepted_state():
    module = definition('compressor')
    module.source['runtime'] = module.source['runtime'].replace('shaft_power_w=shaft,', 'shaft_power_w=shaft + 1.0,')
    module.content_hash = module_content_hash(module)
    module.definition_hash = module_definition_hash(module)
    fluid = FluidConfig(fluid='Ammonia', phase_policy='any')
    runner = WorkerProcess(module, {}, fluid, instance_id='Custom42')
    try:
        runner.initialize()
        with pytest.raises(ValueError, match='守恒') as failure:
            evaluate_constitutive(runner, property_service(fluid), runner.parameters, 110000., 1350000., .1, 0)
        assert runner.state == {'accepted_seconds':0.}
        assert runner.state_revision == 0
        from fn_engine.module_replay import failure_snapshot, replay_module
        from fn_engine.model_types.http import ModuleReplayRequest
        snapshot = failure_snapshot(failure.value)
        assert snapshot is not None
        replay = replay_module(ModuleReplayRequest(replay=snapshot))
        assert replay.status == 'failed' and replay.matched_failure
    finally:
        runner.close()


def test_shutdown_requires_zero_power_and_flow():
    result = run_module_test(ModuleTestRequest(module=definition('compressor'), parameters={'running':0.}, duration_s=.1, dt_s=.1))
    fields = result.frame.variables
    assert fields['D1.mass_flow_kg_s'] == fields['D1.electric_power_w'] == fields['D1.shaft_power_w'] == 0.
    json.dumps(result.model_dump(mode='json'), allow_nan=False)


def test_reference_sources_and_manifests_match_executable_factories():
    from pathlib import Path
    folder = Path(__file__).resolve().parents[1] / 'examples' / 'refrigeration_extensions'
    for kind in ('compressor', 'condenser'):
        module = definition(kind)
        assert (folder / f'sdk_{kind}.py').read_text(encoding='utf-8') == module.source['runtime']
        saved = ModuleDefinition.model_validate_json((folder / f'sdk_{kind}.manifest.json').read_text(encoding='utf-8'))
        assert saved.model_dump(mode='json') == module.model_dump(mode='json')


def test_checkpoint_resumes_worker_state_and_physical_trajectory():
    from fn_engine.checkpoints import capture, restore
    continuous = create_session(compile_project(project()), .3, .1, keep=8)
    restarted = None
    try:
        continuous.initialize()
        continuous.advance()
        packet = json.loads(json.dumps(capture(continuous), allow_nan=False))
        restarted = restore(packet, duration_s=.3, keep=8)
        assert set(restarted.runners) == set(continuous.runners)
        for iid, runner in continuous.runners.items():
            assert restarted.runners[iid].state == runner.state
            assert restarted.runners[iid].state_revision == runner.state_revision
        uninterrupted = continuous.advance()
        resumed = restarted.advance()
        assert resumed.time_s == uninterrupted.time_s == .2
        for field in ('masses', 'energies', 'temperatures', 'counters'):
            assert getattr(restarted, field) == pytest.approx(getattr(continuous, field), rel=1e-11, abs=1e-6)
        for iid, runner in continuous.runners.items():
            assert restarted.runners[iid].state == runner.state
        assert abs(resumed.metrics['energy_residual_j']) < .01
    finally:
        continuous.close()
        if restarted is not None:
            restarted.close()
