import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project, CompilationError
from fn_engine.refrigeration.multi_cooler_example import multi_cooler_example
from fn_engine.refrigeration.modular_examples import modular_room_example
from fn_engine.refrigeration.report import station_series_keys
from fn_engine.sessions import create_session
from fn_engine.solver import solve_dynamic


def test_two_coils_match_one_coil_without_duplicating_room_storage():
    original=solve_dynamic(compile_project(modular_room_example()),60.,30.)[-1]
    project=multi_cooler_example(); network=compile_project(project)
    frames=solve_dynamic(network,60.,30.); final=frames[-1]; v=final.variables
    assert network.room_cooler_groups=={'Room':['Cooler','CoolerB']}
    assert v['Room.state.temperature_k']==pytest.approx(original.variables['Room.state.temperature_k'],abs=1e-7)
    assert v['Room.cooling_power_w']==pytest.approx(v['Cooler.room_cooling_w']+v['CoolerB.room_cooling_w'])
    assert v['Room.stored_energy_j']==pytest.approx(original.variables['Room.stored_energy_j'])
    assert abs(final.metrics['energy_residual_j'])<.05
    keys=dict(station_series_keys(network))
    assert 'CoolerB.refrigerant_heat_w' in keys and 'CoolerB.state.fan_energy_j' in keys


def test_independent_fan_control_changes_only_one_actuator_and_preserves_heat_accounting():
    session=create_session(compile_project(multi_cooler_example()),120.,30.)
    try:
        session.initialize(); session.advance(); before=session.snapshot()
        session.set_parameter('CoolerB','running',0.)
        frame=session.advance(); v=frame.variables
        assert v['CoolerB.fan_power_w']==0. and v['Cooler.fan_power_w']==200.
        assert v['Room.cooling_power_w']==pytest.approx(v['Cooler.room_cooling_w']+v['CoolerB.room_cooling_w'])
        assert v['Room.state.temperature_k']>before.variables['Room.state.temperature_k']
        assert abs(frame.metrics['energy_residual_j'])<.05
    finally: session.close()


def test_legacy_one_coil_contract_still_rejects_duplicate_thermal_connection():
    old=catalog_map()['cold_room']
    assert [p.id for p in old.ports]==['heat']
    project=multi_cooler_example()
    thermal=[c for c in project.connections if c.target.instance_id=='Room']
    thermal[1].target.port_id='heat0'
    with pytest.raises(CompilationError): compile_project(project)


def test_id_rename_and_multiple_rooms_have_no_hidden_room_binding():
    project=multi_cooler_example(); ids={i.id:'X-'+i.id for i in project.instances}
    for i in project.instances:i.id=ids[i.id]
    for c in project.connections:
        c.source.instance_id=ids[c.source.instance_id];c.target.instance_id=ids[c.target.instance_id]
    project.instances.reverse();project.connections.reverse()
    frame=solve_dynamic(compile_project(project),60.,30.)[-1]
    assert frame.valid and frame.variables['X-Room.state.temperature_k']==pytest.approx(255.15,abs=1e-6)
