"""Product A1 seed; canonical parameters mirror the versioned case assumptions."""
from ..catalog import thermal_catalog
from ..models import Connection, Endpoint, ModuleInstance, PIDController, Project, SolverOptions


def ideal_room_example():
    return Project(id='cold-room-ideal-v1', name='−18°C 单库房 · A1 理想冷源',
        description='库房热容和围护漏热的开发基准；理想冷源，不含货物状态、制冷循环与能耗。',
        modules=thermal_catalog(),
        instances=[
            ModuleInstance(id='ROOM1', module_id='cold_room', name='冻结物储藏库 · 热节点'),
            ModuleInstance(id='COLD1', module_id='ideal_cold_source', name='理想冷源', parameters={'capacity_ratio': 1.})],
        connections=[Connection(id='heat1', source=Endpoint(instance_id='COLD1', port_id='heat'),
                                target=Endpoint(instance_id='ROOM1', port_id='heat'))],
        controllers=[PIDController(id='room_temperature', measurement='ROOM1.state.temperature_k',
            instance_id='COLD1', parameter_id='capacity_ratio', setpoint=255.15, kp=-.4, ki=-.002,
            sample_s=5., minimum=0., maximum=1.)],
        selected_variables=[],
        solver=SolverOptions(dynamic_step_s=10.))
