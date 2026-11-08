"""Separable teaching maps for a saturated-suction compressor; no manufacturer calibration."""
import math

from .cycle import DeviceRangeError, compress

CURVES = ('isentropic_pressure_curve', 'volumetric_pressure_curve', 'load_factor_curve', 'speed_factor_curve')
OUTPUT_KEYS = ('mass_flow_kg_s', 'shaft_power_w', 'electric_power_w', 'discharge_temperature_k',
               'pressure_ratio', 'actual_isentropic_efficiency', 'actual_volumetric_efficiency', 'actual_speed_ratio')


def validate_maps(parameters):
    for name in CURVES:
        points = parameters.get(name)
        if (not isinstance(points, list) or len(points) < 2 or any(not isinstance(row, (list, tuple)) or len(row) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in row)
                for row in points)):
            raise DeviceRangeError('COMPRESSOR_MAP_INVALID', f'{name} 必须至少包含两个有限数值点', field=name)
        if any(x <= 0 or y <= 0 or y > 1. for x,y in points) or any(a[0] >= b[0] for a,b in zip(points,points[1:])):
            raise DeviceRangeError('COMPRESSOR_MAP_INVALID', f'{name} 横坐标须为正且递增，纵坐标须在 (0,1] 内', field=name)
        if name in ('load_factor_curve', 'speed_factor_curve') and points[-1][0] > 1.:
            raise DeviceRangeError('COMPRESSOR_MAP_INVALID', f'{name} 比例轴不能超过 1', field=name)


def interpolate(points, value, field):
    if not points[0][0] <= value <= points[-1][0]:
        raise DeviceRangeError('COMPRESSOR_MAP_RANGE', f'{field} 输入 {value:g} 超出 [{points[0][0]:g}, {points[-1][0]:g}]，禁止外推', field=field)
    for a,b in zip(points, points[1:]):
        if value <= b[0]:
            return a[1]+(b[1]-a[1])*(value-a[0])/(b[0]-a[0])
    return points[-1][1]


def check_operating_point(p, result):
    if not result['running']:
        return
    ratio = result['pressure_ratio']
    if ratio <= 1. or ratio > p['max_pressure_ratio']:
        raise DeviceRangeError('COMPRESSOR_ENVELOPE', f'运行压比 {ratio:g} 不满足 (1,{p["max_pressure_ratio"]:g}]', field='max_pressure_ratio')
    for name, value in zip(CURVES, (ratio, ratio, p['load_ratio'], p['speed_ratio'])):
        interpolate(p[name], value, name)
    if result['discharge_temperature_k'] > p['max_discharge_temperature_k']:
        raise DeviceRangeError('COMPRESSOR_ENVELOPE', f'排气温度超出 {p["max_discharge_temperature_k"]:g} K', field='max_discharge_temperature_k')


def compressor_point(service, p, suction_pa, discharge_pa, check=True, inlet_state=None):
    validate_maps(p)
    if not all(math.isfinite(v) and v > 0. for v in (suction_pa, discharge_pa)):
        raise DeviceRangeError('COMPRESSOR_PRESSURE', '压缩机两侧绝压必须为有限正数')
    suction = service.state_pq(suction_pa, 1.) if inlet_state is None else inlet_state
    ratio = discharge_pa/suction_pa
    load, speed = p['load_ratio'], p['speed_ratio']
    active = p['running'] >= .5 and load > 0. and speed > 0.
    result = dict.fromkeys(OUTPUT_KEYS, 0.)
    result.update(discharge_temperature_k=None, pressure_ratio=ratio, suction_enthalpy_j_kg=suction.enthalpy_j_kg,
                  discharge_enthalpy_j_kg=suction.enthalpy_j_kg, running=float(active), diagnostics=[])
    if not active:
        return result
    if ratio <= 1.:
        raise DeviceRangeError('COMPRESSOR_PRESSURE_RATIO', '运行压缩机排气压力必须高于吸气压力')
    def mapped(name, value):
        # During a Newton probe, use a bounded continuation. The accepted point is checked strictly below.
        value = value if check else min(p[name][-1][0], max(p[name][0][0], value))
        return interpolate(p[name], value, name)
    factor = mapped('load_factor_curve', load)*mapped('speed_factor_curve', speed)
    eta_i = mapped('isentropic_pressure_curve', ratio)*factor
    eta_v = mapped('volumetric_pressure_curve', ratio)*factor
    mass = p['displacement_m3_s']*load*speed*eta_v*suction.density_kg_m3
    _, h_out = compress(service, suction, discharge_pa, eta_i)
    temperature = service.state_ph(discharge_pa, h_out).temperature_k
    shaft = mass*(h_out-suction.enthalpy_j_kg)
    result.update(mass_flow_kg_s=mass, shaft_power_w=shaft, electric_power_w=shaft/p['motor_efficiency'],
                  discharge_temperature_k=temperature, discharge_enthalpy_j_kg=h_out,
                  actual_isentropic_efficiency=eta_i, actual_volumetric_efficiency=eta_v, actual_speed_ratio=speed)
    if check:
        check_operating_point(p, result)
    return result


def definition():
    from ..catalog import _celsius, _ratio, _stream, _switch, _var, number
    from .._module_schema_v1 import Direction, ParameterSpec
    from ..model_types.module import ModuleDefinition
    return ModuleDefinition(id='performance_compressor', name='性能曲线压缩机', category='制冷站设备',
        solver_model='performance_compressor', description='饱和吸气、压比效率曲线×载量/转速修正；默认曲线为人为教学假设，非厂家标定。'
            '分段线性插值，不允许外推；电机损失排向机房；不模拟真实过热吸气、油冷或惯性。',
        ports=[_stream('suction','吸气',Direction.in_), _stream('discharge','排气',Direction.out)],
        parameters=[_switch(), _ratio('load_ratio','载量',.75,runtime=True), _ratio('speed_ratio','转速比',1.,runtime=True),
            number('displacement_m3_s','额定理论排量',.01,'volume_flow','m³/s','m³/h',1/3600,minimum=1e-8),
            _ratio('motor_efficiency','电机效率',.92,minimum=.01),
            number('max_pressure_ratio','运行压比上限',14.,'ratio','1',minimum=1.),
            _celsius('max_discharge_temperature_k','排气温度上限',523.15),
            ParameterSpec(id='isentropic_pressure_curve',label='压比—等熵效率（教学）',value_type='curve',default=[[1.01,.76],[4.,.74],[8.,.70],[14.,.62]]),
            ParameterSpec(id='volumetric_pressure_curve',label='压比—容积效率（教学）',value_type='curve',default=[[1.01,.9],[4.,.85],[8.,.78],[14.,.65]]),
            ParameterSpec(id='load_factor_curve',label='载量—效率修正系数（教学）',value_type='curve',default=[[.2,.8],[.5,.94],[1.,1.]]),
            ParameterSpec(id='speed_factor_curve',label='转速比—效率修正系数（教学）',value_type='curve',default=[[.3,.85],[.7,.97],[1.,1.]])],
        variables=[_var('mass_flow_kg_s','制冷剂质量流量','mass_flow','kg/s'),
            _var('shaft_power_w','压缩轴功','power','W','kW',1000.),_var('electric_power_w','电功率','power','W','kW',1000.),
            _var('discharge_temperature_k','排气温度','temperature','K','°C',offset=-273.15),_var('pressure_ratio','压比','ratio','1'),
            *[_var(key,label,'ratio','1','%',.01) for key,label in [('actual_isentropic_efficiency','实际等熵效率'),
                ('actual_volumetric_efficiency','实际容积效率'),('actual_speed_ratio','实际转速比')]],
            _var('state.electric_energy_j','累计压缩机电量','energy','J','kWh',3600000.,source='state')])
