"""Room feedback is a declared physical state, including independently named instances."""
import pytest

from fn_engine.air_examples import air_example
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import PIDController


def test_room_feedback_states_are_declared_with_canonical_and_display_units():
    variables = {v.id:v for v in catalog_map()['air_room'].variables}
    temperature = variables['state.temperature_k']
    assert temperature.source == 'state' and temperature.sampleable
    assert temperature.unit.from_canonical(299.15) == pytest.approx(26.)
    assert variables['state.humidity_ratio_kg_kg'].unit.from_canonical(.01) == pytest.approx(10.)
    assert variables['state.relative_humidity'].unit.from_canonical(.5) == pytest.approx(50.)


def test_arbitrary_room_id_can_drive_a_runtime_water_valve_and_unknown_state_still_fails():
    project = air_example('chiller-air-loop')
    room = next(i for i in project.instances if i.id == 'Room')
    room.id = 'Office-West'
    for connection in project.connections:
        for endpoint in (connection.source, connection.target):
            if endpoint.instance_id == 'Room':
                endpoint.instance_id = room.id
    project.controllers = [PIDController(id='comfort', measurement='Office-West.state.temperature_k',
        instance_id='WaterValve', parameter_id='opening_ratio', setpoint=299.15, kp=-.1, ki=-.00003,
        minimum=.02, maximum=1.)]
    network = compile_project(project)
    assert network.project.controllers[0].measurement == 'Office-West.state.temperature_k'
    project.controllers[0].measurement = 'Office-West.state.not_a_temperature'
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'PID_MEASUREMENT_UNKNOWN'
