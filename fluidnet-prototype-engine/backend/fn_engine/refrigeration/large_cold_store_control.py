"""An editable six-room example using existing sampled controllers and devices."""
from ..model_types.domain import PIDController, Scenario, ScheduleEvent, SolverOptions
from ..properties import property_service
from .large_cold_store_example import ROOMS, build_large_cold_store


def controlled_large_cold_store():
    project, _ = build_large_cold_store(fan_ratio=.65, condenser_fan=.8)
    project.id = 'large-cold-store-controlled'
    project.name = '六库房冷库 · 简单自动温控'
    project.description = ('六库独立设定温度，冷风机自动调节；压缩机、补液和冷凝器维持各自工作点。'
                           '使用现有简化设备模型，冷风机和冷凝器留有调节余量。')
    project.solver = SolverOptions(dynamic_step_s=30.)
    service = property_service(project.fluid)

    def pid(cid, measurement, instance, parameter, target, kp, ki, minimum=0.):
        return PIDController(id=cid, measurement=measurement, instance_id=instance, parameter_id=parameter,
                             setpoint=target, kp=kp, ki=ki, sample_s=30., minimum=minimum, maximum=1.)

    project.controllers = [
        pid(f'{room[0]}_temperature_{i}', f'{room[0]}.state.temperature_k', f'{room[0]}_AC{i}',
            'fan_ratio', room[2] + 273.15, -.8, -.8 / 900.) for room in ROOMS for i in (1, 2)]
    for zone, vessel, temperature in [('LT', 'LP', 241.15), ('HT', 'IP', 265.15)]:
        pressure = service.state_tq(temperature, 1.).pressure_pa
        for i in (1, 2):
            project.controllers.append(pid(f'{zone}_capacity_{i}', f'{vessel}.state.pressure_pa', f'{zone}_K{i}',
                                           'load_ratio', pressure, -1. / pressure, -1. / pressure / 300., .1))
    high = service.state_tq(308.15, 1.).pressure_pa
    project.controllers.extend([
        pid('condensing', 'HP.state.pressure_pa', 'COND', 'fan_ratio', high, -2. / high, -2. / high / 300.),
        pid('middle_level', 'IP.state.level_ratio', 'HP_VALVE', 'opening_ratio', .4, 2., 2. / 600.),
        pid('low_level', 'LP.state.level_ratio', 'LT_VALVE', 'opening_ratio', .4, 2., 2. / 600.)])
    room = next(n for n in project.instances if n.id == 'F01')
    load = room.parameters['heat_input_w']
    event = lambda eid, time, key, value: ScheduleEvent(id=eid, type='set_variable', time_s=time, key=key, value=value)
    project.scenarios = [
        Scenario(id='baseline', name='自动温控 · 正常运行'),
        Scenario(id='load-step', name='库房 1 增载后恢复', events=[
            event('extra-load', 600., 'F01.param.heat_input_w', load + 100000.),
            event('restore-load', 5400., 'F01.param.heat_input_w', load)]),
        Scenario(id='cooler-off', name='库房 1 一台冷风机停机', overrides={'F01_AC1': {'running': 0., 'supply_valve_ratio': 0.}}),
        Scenario(id='lower-load', name='库房 1 减载，自动减小制冷', events=[
            event('less-load', 600., 'F01.param.heat_input_w', load - 100000.)])]
    return project
