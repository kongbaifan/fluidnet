"""Open pool with explicit evaporation/drift sinks, separate from the moist tower model."""
from dataclasses import dataclass

from .compiler import CompilationError, StorageSpec, tank_initial_state
from .models import Direction, FluidConfig, ModuleDefinition, PortSpec, VariableSpec
from .properties import property_service


def definition():
    from .catalog import _celsius, _var, number
    params=[number('area_m2','池面面积',1.,'area','m²',minimum=.001),
        number('height_m','池体高度',2.,'length','m',minimum=.01),
        number('level_m','初始水位',1.,'length','m',minimum=.001),
        number('surface_pressure_pa','池面绝对压力',101325.,'pressure','Pa','kPa',1000.,1000.),
        _celsius('temperature_k','初始水温',303.15),
        number('heat_input_w','独立外部热源（不含蒸发）',0.,'power','W','kW',1000.,runtime=True),
        number('heat_loss_ua_w_k','对环境显热 UA',0.,'conductance','W/K',minimum=0.),
        _celsius('ambient_temperature_k','环境温度',293.15),
        number('evaporation_kg_s','外给蒸发质量流量',0.,'mass_flow','kg/s',minimum=0.),
        number('drift_kg_s','外给液滴飘水质量流量',0.,'mass_flow','kg/s',minimum=0.)]
    variables=[VariableSpec(id='param.'+p.id,label=p.label,source='parameter',parameter_id=p.id,
        quantity=p.unit.quantity,unit=p.unit) for p in params]
    variables.extend([_var('state.'+key,label,quantity,unit,source='state') for key,label,quantity,unit in (
        ('mass_kg','池水质量','mass','kg'),('level_m','水位','length','m'),('volume_m3','水体积','volume','m³'),
        ('net_inflow_kg_s','库存变化率','mass_flow','kg/s'),('evaporated_kg','累计蒸发','mass','kg'),
        ('drift_kg','累计飘水','mass','kg'))])
    variables.extend([_var('state.temperature_k','池温','temperature','K','°C',offset=-273.15,source='state'),
        _var('evaporation_enthalpy_w','蒸气带走焓流','power','W'),_var('drift_enthalpy_w','飘水带走焓流','power','W')])
    return ModuleDefinition(id='tower_pool',name='冷却塔池（外给蒸发）',category='边界与节点',
        solver_model='tower_pool',state_model='open_pool_losses',
        ports=[PortSpec(id='in0',label='循环回水',direction=Direction.in_),
               PortSpec(id='in1',label='补水',direction=Direction.in_),
               PortSpec(id='out0',label='循环供水',direction=Direction.out),
               PortSpec(id='out1',label='排污',direction=Direction.out)],parameters=params,variables=variables,
        description='开式充分混合池体，补排流量由真实支路计算；外给蒸发/飘水进入质量与焓储量。'
                    '蒸气焓取池温下饱和水蒸气，不与现有湿空气冷却塔自动联算。')


@dataclass
class PoolStorage(StorageSpec):
    evaporation_kg_s: float
    drift_kg_s: float
    fluid: FluidConfig

    def loss_mass_rate(self):
        return self.evaporation_kg_s+self.drift_kg_s

    def sink_energy(self,liquid_state):
        vapor=property_service(self.fluid).state_tq(liquid_state.temperature_k,1.)
        return self.evaporation_kg_s*vapor.enthalpy_j_kg+self.drift_kg_s*liquid_state.enthalpy_j_kg


def build_spec(instance_id,params,node,service):
    from .properties import is_pure_water
    if not is_pure_water(service.config):
        raise CompilationError('POOL_WATER_REQUIRED','外给蒸发塔池首版只支持纯水液体',instance_id)
    base=tank_initial_state(instance_id,params,node,service)
    return PoolStorage(**vars(base),evaporation_kg_s=params['evaporation_kg_s'],drift_kg_s=params['drift_kg_s'],
                       fluid=service.config.model_copy(update={'phase_policy':'any'}))
