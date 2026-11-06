"""Four-port enthalpy recovery: paired heat and water-vapor transfer, no dry-air leakage."""
from dataclasses import dataclass

from .air_devices import AirDeviceResult
from .moist_air import MoistAirService, AirPropertyError, vapor_enthalpy


@dataclass
class RecoveryResult:
    exhaust: AirDeviceResult
    supply: AirDeviceResult


def evaluate(exhaust,supply,exhaust_flow,supply_flow,parameters,exhaust_pressure,supply_pressure,service=None,check=True):
    service=service or MoistAirService()
    ma,mb=abs(exhaust_flow),abs(supply_flow);p=parameters
    bypass=1-p['bypass_ratio']
    if min(ma,mb)<=1e-10:
        heat=moisture=sensible=latent=0.
    else:
        ca=ma*exhaust.specific_heat_j_kg_dry_air_k;cb=mb*supply.specific_heat_j_kg_dry_air_k
        sensible=bypass*p['sensible_effectiveness']*min(ca,cb)*(exhaust.temperature_k-supply.temperature_k)
        moisture=bypass*p['moisture_effectiveness']*min(ma,mb)*(exhaust.humidity_ratio_kg_kg-supply.humidity_ratio_kg_kg)
        donor_temperature=exhaust.temperature_k if moisture>=0 else supply.temperature_k
        latent=moisture*vapor_enthalpy(donor_temperature)
        heat=sensible+latent
    wa=exhaust.humidity_ratio_kg_kg-(moisture/ma if ma>1e-10 else 0.)
    wb=supply.humidity_ratio_kg_kg+(moisture/mb if mb>1e-10 else 0.)
    ha=exhaust.enthalpy_j_kg_dry_air-(heat/ma if ma>1e-10 else 0.)
    hb=supply.enthalpy_j_kg_dry_air+(heat/mb if mb>1e-10 else 0.)
    try:
        a=service.state_phw(exhaust_pressure,ha,wa);b=service.state_phw(supply_pressure,hb,wb)
    except AirPropertyError as error:
        if error.code=='AIR_HUMIDITY_SUPERSATURATED':
            raise AirPropertyError('RECOVERY_CONDENSATION_UNSUPPORTED','全热回收出口过饱和；首版不处理凝液，需降低有效度或改变入口工况') from error
        raise
    if check:
        if min(exhaust.temperature_k,supply.temperature_k,a.temperature_k,b.temperature_k)<273.15:
            raise AirPropertyError('RECOVERY_FROST_UNSUPPORTED','全热回收首版仅适用所有端口不低于0°C，不含结霜/除霜')
        # Include the exact isenthalpic pressure-change endpoints. A zero-exchange device
        # can change temperature slightly with pressure without violating a thermal pinch.
        base_a=service.state_phw(exhaust_pressure,exhaust.enthalpy_j_kg_dry_air,exhaust.humidity_ratio_kg_kg)
        base_b=service.state_phw(supply_pressure,supply.enthalpy_j_kg_dry_air,supply.humidity_ratio_kg_kg)
        lower=min(exhaust.temperature_k,supply.temperature_k,base_a.temperature_k,base_b.temperature_k)
        upper=max(exhaust.temperature_k,supply.temperature_k,base_a.temperature_k,base_b.temperature_k)
        if any(t<lower-1e-5 or t>upper+1e-5 for t in (a.temperature_k,b.temperature_k)):
            raise AirPropertyError('RECOVERY_PINCH_RANGE','固定显热/湿量有效度组合越过入口温度夹点；此工况超出首版范围')
    outputs={'sensible_heat_w':sensible,'vapor_enthalpy_transfer_w':latent,'total_heat_w':heat,
        'moisture_transfer_kg_s':moisture,'exhaust_outlet_temperature_k':a.temperature_k,'supply_outlet_temperature_k':b.temperature_k,
        'exhaust_outlet_humidity_ratio_kg_kg':wa,'supply_outlet_humidity_ratio_kg_kg':wb,
        'energy_residual_w':ma*(a.enthalpy_j_kg_dry_air-exhaust.enthalpy_j_kg_dry_air)+mb*(b.enthalpy_j_kg_dry_air-supply.enthalpy_j_kg_dry_air),
        'moisture_residual_kg_s':ma*(wa-exhaust.humidity_ratio_kg_kg)+mb*(wb-supply.humidity_ratio_kg_kg)}
    # Signed source terms cancel between streams. No liquid drain or external moisture source
    # exists; water_removed is intentionally not used (it represents condensate enthalpy).
    return RecoveryResult(AirDeviceResult(a,-heat,water_added_kg_s=-moisture,outputs=outputs),
                          AirDeviceResult(b,heat,water_added_kg_s=moisture))


def definition():
    from .air_catalog import _derived
    from .catalog import number, _ratio, channel
    from .models import ModuleDefinition,PortSpec,Direction
    ports=[PortSpec(id=s+'_'+e,label=label+('入口' if e=='in' else '出口'),direction=Direction.in_ if e=='in' else Direction.out,circuit=s)
           for s,label in [('exhaust','排风'),('supply','新风')] for e in ('in','out')]
    return ModuleDefinition(id='enthalpy_recovery',name='双风道全热回收器（无凝结）',solver_model='enthalpy_recovery',category='风侧设备',
        description='四口双流股，干空气无泄漏，显热与水汽跨膜成对交换；固定有效度为教学参数。出口饱和、夹点越界或低于0°C拒绝，不含凝液、结霜、转轮蓄热。仅湿空气域。',ports=ports,
        channels=[channel('ch0','resistance','exhaust_in','exhaust_out'),channel('ch1','resistance_secondary','supply_in','supply_out')],
        parameters=[_ratio('sensible_effectiveness','显热有效度',.65),_ratio('moisture_effectiveness','湿量有效度',.5),
            _ratio('bypass_ratio','等效交换旁通比例',0.,True),number('diameter_m','排风等效内径',.4,'length','m','mm',.001,minimum=.001),
            number('loss_coefficient','排风阻力K',2.,'ratio','1',minimum=.001),
            number('secondary_diameter_m','新风等效内径',.4,'length','m','mm',.001,minimum=.001),
            number('secondary_loss_coefficient','新风阻力K',2.,'ratio','1',minimum=.001)],
        variables=[_derived(key,label,quantity,unit,display,scale) for key,label,quantity,unit,display,scale in [
            ('sensible_heat_w','向新风显热传递','power','W','kW',1000.),('vapor_enthalpy_transfer_w','水汽携带焓通量','power','W','kW',1000.),
            ('total_heat_w','向新风总焓传递','power','W','kW',1000.),('moisture_transfer_kg_s','向新风水汽迁移','mass_flow','kg/s','kg/s',1.),
            ('energy_residual_w','双侧能量残差','power','W','W',1.),('moisture_residual_kg_s','双侧湿量残差','mass_flow','kg/s','kg/s',1.)]]+
        [_derived(side+'_outlet_temperature_k',label+'出风温度','temperature','K','°C',offset=-273.15) for side,label in [('exhaust','排风'),('supply','新风')]]+
        [_derived(side+'_outlet_humidity_ratio_kg_kg',label+'出口含湿量','humidity_ratio','kg/kg_da','g/kg_da',.001) for side,label in [('exhaust','排风'),('supply','新风')]]+
        [_derived('state.transferred_energy_j','累计向新风焓传递','energy','J','kWh',3600000.,source='state'),
         _derived('state.transferred_water_kg','累计向新风水汽迁移','mass','kg',source='state')])
