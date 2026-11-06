"""Isothermal ideal-gas cushion coupled to liquid mass, EOS and internal energy.

Gas mass is fixed: p*Vg = precharge_pressure*total_volume. Liquid volume is M/rho(p,h).
The gas bath heat equals its reversible isothermal work and is reported explicitly.
"""
from dataclasses import dataclass, replace
import math

from scipy.optimize import brentq

from .compiler import CompilationError, StorageSpec
from .models import ModuleDefinition, VariableSpec
from .properties import property_service


def definition():
    from .catalog import _celsius, _var, number, ports
    parameters=[number('volume_m3','罐体总容积',.1,'volume','m³',minimum=.001),
                number('precharge_pressure_pa','空罐等温预充绝对压力',150000.,'pressure','Pa','kPa',1000.,1000.),
                number('initial_liquid_fraction','初始液体体积分数',.4,'ratio','1','%',.01,.001,.95),
                _celsius('temperature_k','初始液温',293.15),
                number('heat_input_w','液体外部加热',0.,'power','W','kW',1000.,runtime=True),
                number('heat_loss_ua_w_k','液体对环境 UA',0.,'conductance','W/K',minimum=0.),
                _celsius('ambient_temperature_k','液体环境温度',293.15)]
    variables=[VariableSpec(id='param.'+p.id,label=p.label,source='parameter',parameter_id=p.id,
                             quantity=p.unit.quantity,unit=p.unit) for p in parameters]
    for key,label,quantity,unit in [('mass_kg','液体存量','mass','kg'),('volume_m3','液体体积','volume','m³'),
        ('gas_volume_m3','气垫体积','volume','m³'),('pressure_pa','气液绝对压力','pressure','Pa'),
        ('internal_energy_j','液体内能','energy','J'),('gas_work_j','气体累计对液体做功/等温热浴吸热','energy','J'),
        ('net_inflow_kg_s','液体净流入','mass_flow','kg/s')]:
        variables.append(_var('state.'+key,label,quantity,unit,source='state'))
    variables.append(_var('state.temperature_k','液温','temperature','K','°C',offset=-273.15,source='state'))
    return ModuleDefinition(id='gas_expansion_tank',name='气垫膨胀罐（等温气体）',category='边界与节点',
        solver_model='expansion_tank',state_model='isothermal_gas_cushion',ports=ports('in0','out0'),
        parameters=parameters,variables=variables,
        description='两水口共用压力节点；气体pV常数、液体M/rho(p,h)联立压力，液体内能计气垫压缩功。'
                    '气体等温热浴显式记账；仅普通液体动态，不含气体溶解、膜片弹性或高度静压。')


@dataclass
class ExpansionStorage(StorageSpec):
    service: object
    total_volume_m3: float
    gas_constant_j: float
    initial_gas_volume_m3: float

    def __deepcopy__(self,memo):
        # The property service owns thread-local caches; only scalar model parameters are copied.
        value=replace(self)
        memo[id(self)]=value
        return value

    def pressure(self,mass_kg,enthalpy=None):
        h=self.initial_enthalpy_j_kg if enthalpy is None else enthalpy
        def volume_error(pressure):
            fluid=self.service.state_ph(pressure,h)
            return mass_kg/fluid.density_kg_m3+self.gas_constant_j/pressure-self.total_volume_m3
        low=self.gas_constant_j/self.total_volume_m3*.1
        high=max(self.initial_pressure_pa*2.,low*20.)
        while volume_error(high)>0 and high<1e8:
            high*=2.
        if volume_error(low)<0 or volume_error(high)>0:
            raise CompilationError('EXPANSION_VOLUME_RANGE','气垫罐质量/焓状态无法满足容积与压力关系',self.instance_id)
        return brentq(volume_error,low,high,xtol=1e-6)

    def pressure_slope(self,mass_kg,enthalpy=None):
        delta=max(abs(mass_kg)*1e-5,1e-5)
        return (self.pressure(mass_kg+delta,enthalpy)-self.pressure(mass_kg-delta,enthalpy))/(2*delta)

    def state(self,mass_kg,enthalpy):
        pressure=self.pressure(mass_kg,enthalpy)
        fluid=self.service.state_ph(pressure,enthalpy)
        liquid_volume=mass_kg/fluid.density_kg_m3
        if fluid.phase not in ('liquid','supercritical_liquid'):
            raise CompilationError('EXPANSION_LIQUID_REQUIRED','膨胀罐液体必须保持单相液态',self.instance_id)
        if not .001*self.total_volume_m3 <= liquid_volume <= .99*self.total_volume_m3:
            raise CompilationError('EXPANSION_VOLUME_RANGE','膨胀罐液体体积须保持在罐容0.1%–99%范围',self.instance_id)
        return pressure,fluid,liquid_volume,self.gas_constant_j/pressure

    def energy_terms(self,old,mass,pressure,h,dt):
        """Extra term F(h) in the mixing row: F + inflow*h - inflow_enthalpy = 0."""
        old_p,old_fluid,_,old_gas=self.state(old.mass_kg,old.enthalpy_j_kg)
        fluid=self.service.state_ph(pressure,h)
        gas=self.gas_constant_j/pressure
        work=self.gas_constant_j*math.log(gas/old_gas)
        stored=(mass*fluid.internal_energy_j_kg-old.mass_kg*old_fluid.internal_energy_j_kg)/dt
        net=(mass-old.mass_kg)/dt
        loss=self.heat_loss_ua_w_k*(fluid.temperature_k-self.ambient_temperature_k)
        extra=stored-work/dt-net*h-self.heat_input_w+loss
        delta=max(fluid.specific_heat_j_kg_k*.001,1.)
        a=self.service.state_ph(pressure,h+delta)
        b=self.service.state_ph(pressure,h-delta)
        slope=mass*(a.internal_energy_j_kg-b.internal_energy_j_kg)/(2*delta*dt)-net
        slope+=self.heat_loss_ua_w_k*(a.temperature_k-b.temperature_k)/(2*delta)
        return slope,slope*h-extra,stored,work/dt


def build_spec(instance_id,params,node,service):
    p=params['precharge_pressure_pa']/(1.-params['initial_liquid_fraction'])
    state=service.state_pt(p,params['temperature_k'])
    volume=params['volume_m3']
    mass=volume*params['initial_liquid_fraction']*state.density_kg_m3
    spec=ExpansionStorage(instance_id,node,volume,1.,0.,params['heat_input_w'],params['heat_loss_ua_w_k'],
        params['ambient_temperature_k'],mass,p,params['temperature_k'],state.enthalpy_j_kg,
        property_service(service.config.model_copy(update={'phase_policy':'any'})),volume,
        params['precharge_pressure_pa']*volume,volume*(1.-params['initial_liquid_fraction']))
    spec.state(mass,state.enthalpy_j_kg)
    return spec
