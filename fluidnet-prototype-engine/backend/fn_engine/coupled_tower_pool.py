"""A fully mixed wet-contact pool with real water inventory and ambient humid-air streams.

All heat and water exchange is evaluated without the old tower's algebraic makeup.
An outer fixed point freezes each candidate exchange on an isolated network view.
"""
from dataclasses import dataclass, field, replace

from .compiler import CompilationError, StorageSpec, tank_initial_state
from .model_types.base import FluidConfig
from .moist_air import AirPropertyError, MoistAirService, _ha, liquid_enthalpy
from .properties import PropertyError, property_service


def definition():
    from .tower_pool import definition as pool_definition
    from .catalog import _celsius, _var, number
    from ._module_schema_v1 import VariableSpec
    model=pool_definition()
    model.id,model.name='coupled_tower_pool','湿接触冷却塔池（真实储量）'
    model.solver_model,model.state_model='coupled_tower_pool','wet_contact_pool'
    model.description=('完全混合池体与规定环境湿空气接触，蒸发和飘水进入真实质量/焓库存；'
        '补水与排污经独立水口实际计算，无隐含补水。膜温取池温，非填料与池体双温模型。')
    model.parameters=[p for p in model.parameters if p.id not in ('evaporation_kg_s','drift_kg_s')]
    model.parameters.extend([
        _celsius('air_temperature_k','接触空气干球温度',298.15,runtime=True),
        number('air_pressure_pa','空气绝对压力',101325.,'pressure','Pa','kPa',1000.,60000.,120000.),
        number('air_humidity_ratio_kg_kg','进风含湿量',.01,'humidity_ratio','kg/kg_da','g/kg_da',.001,0.,.05,True),
        number('rated_air_volume_flow_m3_s','风机额定实际风量',.3,'volume_flow','m³/s','m³/h',1/3600,.000001,1000.),
        number('fan_ratio','风机转速比',1.,'ratio','1','%',.01,0.,1.,True),
        number('fan_power_w','额定风机电功率（排向外界）',100.,'power','W','kW',1000.,0.),
        number('contact_effectiveness','湿接触效能',.5,'ratio','1','%',.01,0.,1.,True),
        number('drift_fraction','实际循环回水飘水比例',.0002,'ratio','1','%',.01,0.,.01)])
    model.variables=[v for v in model.variables if v.source!='parameter' and v.id not in ('evaporation_enthalpy_w','drift_enthalpy_w')]
    model.variables.extend(VariableSpec(id='param.'+p.id,label=p.label,source='parameter',parameter_id=p.id,
        quantity=p.unit.quantity,unit=p.unit) for p in model.parameters)
    for key,label,quantity,unit in [('evaporation_kg_s','实际湿空气增湿量','mass_flow','kg/s'),
        ('drift_kg_s','实际飘水','mass_flow','kg/s'),('makeup_kg_s','水口实际补水','mass_flow','kg/s'),
        ('blowdown_kg_s','水口实际排污','mass_flow','kg/s'),('dry_air_mass_flow_kg_s','干空气流量','dry_air_mass_flow','kg_da/s'),
        ('air_heat_w','空气焓增加（湿空气基准）','power','W'),('heat_rejected_w','水池对外总焓流','power','W'),
        ('fan_electric_power_w','风机电功率（不进入水）','power','W'),
        ('air_outlet_humidity_ratio_kg_kg','出风含湿量','humidity_ratio','kg/kg_da'),
        ('air_inlet_enthalpy_j_kg_da','进风比焓','specific_enthalpy','J/kg_da'),
        ('air_outlet_enthalpy_j_kg_da','出风比焓','specific_enthalpy','J/kg_da'),
        ('water_enthalpy_reference_j_kg','水/湿空气焓基准差','specific_enthalpy','J/kg'),
        ('drift_enthalpy_w','飘水带走焓','power','W'),('water_residual_kg_s','湿空气水账残差','mass_flow','kg/s')]:
        model.variables.append(_var(key,label,quantity,unit))
    model.variables.extend([_var('air_outlet_temperature_k','出风温度','temperature','K','°C',offset=-273.15),
        _var('state.makeup_kg','累计实际补水','mass','kg',source='state'),
        _var('state.blowdown_kg','累计实际排污','mass','kg',source='state'),
        _var('state.heat_rejected_j','累计对外焓','energy','J',source='state'),
        _var('state.fan_energy_j','累计风机电量','energy','J',source='state')])
    return model


def exchange(parameters,liquid_state,water_service,circulation_kg_s):
    try:
        return _exchange(parameters,liquid_state,water_service,circulation_kg_s)
    except (AirPropertyError,PropertyError) as error:
        raise CompilationError(error.code,f'湿接触塔池物性不可用：{error}') from error


def validate_parameters(parameters):
    try:
        MoistAirService().state_ptw(parameters['air_pressure_pa'],parameters['air_temperature_k'],
                                    parameters['air_humidity_ratio_kg_kg'])
    except AirPropertyError as error:
        raise CompilationError(error.code,str(error)) from error


def _exchange(parameters,liquid_state,water_service,circulation_kg_s):
    """Actual humid-air stream at a wet film equal to the fully mixed pool temperature."""
    p=parameters
    air_service=MoistAirService()
    air=air_service.state_ptw(p['air_pressure_pa'],p['air_temperature_k'],p['air_humidity_ratio_kg_kg'])
    t=liquid_state.temperature_k
    if not 273.16<=t<=333.15:
        raise CompilationError('TOWER_POOL_WATER_RANGE','湿接触池体水温只支持0.01–60°C')
    flow=p['rated_air_volume_flow_m3_s']*p['fan_ratio']
    dry=flow*air.density_kg_m3/(1.+air.humidity_ratio_kg_kg)
    effective=p['contact_effectiveness'] if circulation_kg_s>1e-10 and flow>0. else 0.
    hs=_ha('H','P',p['air_pressure_pa'],'T',t,'R',1.)
    ws=_ha('W','P',p['air_pressure_pa'],'T',t,'R',1.)
    ha=air.enthalpy_j_kg_dry_air+effective*(hs-air.enthalpy_j_kg_dry_air)
    wa=air.humidity_ratio_kg_kg+effective*(ws-air.humidity_ratio_kg_kg)
    evaporation=dry*(wa-air.humidity_ratio_kg_kg)
    if evaporation < -1e-12:
        raise CompilationError('TOWER_POOL_CONDENSATION_UNSUPPORTED','环境空气会向池体凝水，超出蒸发塔范围')
    evaporation=max(0.,evaporation)
    # Drift requires both circulating water and moving air in this contact model.
    drift=p['drift_fraction']*circulation_kg_s if flow>0. and effective>0. else 0.
    offset=water_service.state_pt(101325.,273.16).enthalpy_j_kg-liquid_enthalpy(273.16)
    heat=dry*(ha-air.enthalpy_j_kg_dry_air)
    liquid_loss=drift*liquid_state.enthalpy_j_kg
    outlet=air_service.state_phw(p['air_pressure_pa'],ha,wa)
    return {'evaporation_kg_s':evaporation,'drift_kg_s':drift,'dry_air_mass_flow_kg_s':dry,
        'air_heat_w':heat,'heat_rejected_w':heat+evaporation*offset+liquid_loss,
        'fan_electric_power_w':p['fan_power_w']*p['fan_ratio']**3,
        'air_outlet_temperature_k':outlet.temperature_k,'air_outlet_humidity_ratio_kg_kg':wa,
        'air_inlet_enthalpy_j_kg_da':air.enthalpy_j_kg_dry_air,'air_outlet_enthalpy_j_kg_da':ha,
        'water_enthalpy_reference_j_kg':offset,'drift_enthalpy_w':liquid_loss,
        'water_residual_kg_s':evaporation-dry*(wa-air.humidity_ratio_kg_kg)}


@dataclass
class CoupledPoolStorage(StorageSpec):
    fluid: FluidConfig
    parameters: dict
    exchange_values: dict = field(default_factory=dict)
    exchange_frozen: bool = False

    def loss_mass_rate(self):
        return self.exchange_values.get('evaporation_kg_s',0.)+self.exchange_values.get('drift_kg_s',0.)

    def sink_energy(self,liquid_state):
        return self.exchange_values.get('heat_rejected_w',0.)


def build_spec(instance_id,parameters,node,service):
    from .properties import is_pure_water
    if not is_pure_water(service.config):
        raise CompilationError('POOL_WATER_REQUIRED','湿接触池体首版只支持纯水',instance_id)
    base=tank_initial_state(instance_id,parameters,node,service)
    state=service.state_pt(base.initial_pressure_pa,base.initial_temperature_k)
    exchange(parameters,state,service,1.)
    return CoupledPoolStorage(**vars(base),fluid=service.config,parameters=dict(parameters))


def solve_coupled_pool(network,runners,time_s,warm,service,storage_step):
    """Coordinate humidity-derived losses with hydraulic mass storage and liquid enthalpy.

    Only disposable view objects receive the iteration guesses. The accepted session
    stores mass/enthalpy and accumulated rates after normal frame validation.
    """
    from .solver import _solve_network, port_mass_flows
    specs={node:spec for node,spec in network.storage.items() if isinstance(spec,CoupledPoolStorage)}
    guessed={}
    for node,spec in specs.items():
        parameters=network.parameters[spec.instance_id]
        water=property_service(spec.fluid)
        state=warm.thermal.node_states[node] if warm is not None and warm.thermal is not None else water.state_pt(
            spec.initial_pressure_pa,spec.initial_temperature_k)
        guessed[node]=exchange(parameters,state,water,1.)
    for iteration in range(1,network.project.solver.max_coupling_iterations+1):
        storage=dict(network.storage)
        for node,spec in specs.items():
            parameters=network.parameters[spec.instance_id]
            storage[node]=replace(spec,exchange_values=guessed[node],exchange_frozen=True,parameters=dict(parameters),
                heat_input_w=parameters['heat_input_w'])
        view=replace(network,storage=storage)
        result=_solve_network(view,runners,time_s,warm,service,storage_step)
        ports=port_mass_flows(view,result.hydraulic.flows)
        new={}
        converged=True
        for node,spec in specs.items():
            iid=spec.instance_id
            flow=ports[f'{iid}:in0']
            if flow < -network.project.solver.mass_tolerance_kg_s:
                raise CompilationError('TOWER_POOL_RETURN_REVERSE','湿接触塔池循环回水口不支持反流',iid)
            values=exchange(network.parameters[iid],result.thermal.node_states[node],property_service(spec.fluid),max(flow,0.))
            values['makeup_kg_s']=max(ports[f'{iid}:in1'],0.)
            values['blowdown_kg_s']=max(-ports[f'{iid}:out1'],0.)
            if ports[f'{iid}:in1'] < -1e-9 or ports[f'{iid}:out1']>1e-9:
                raise CompilationError('TOWER_POOL_SERVICE_REVERSE','补水/排污口流向与声明不符',iid)
            new[node]=values
            converged &= (abs(values['heat_rejected_w']-guessed[node]['heat_rejected_w'])<1e-5
                and abs(values['evaporation_kg_s']+values['drift_kg_s']-storage[node].loss_mass_rate())<1e-11)
        if converged:
            for node,spec in specs.items():
                # Output the exact sink used by this accepted candidate, with actual service-port flows.
                values=guessed[node]|{'makeup_kg_s':new[node]['makeup_kg_s'],'blowdown_kg_s':new[node]['blowdown_kg_s']}
                result.thermal.coil_outputs[spec.instance_id]=values
            result.coupling_iterations+=iteration
            return result
        guessed=new
        warm=result
    raise CompilationError('COUPLING_NOT_CONVERGED','湿接触空气/真实塔池质量与热量迭代未收敛')
