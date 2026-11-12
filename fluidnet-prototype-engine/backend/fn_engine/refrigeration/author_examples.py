"""Self-defined Python constitutive laws, with host-owned inventories and SI balances."""
from ..catalog import catalog_map
from ..model_types.module import ModuleDefinition
from ..runtime import module_content_hash, module_definition_hash


COMPRESSOR_SOURCE = '''class Compressor:
    def evaluate(self, ctx):
        x = ctx.refrigeration.point
        p = ctx.parameters
        # A custom pressure-ratio dependent volumetric-efficiency curve.
        ratio = x.outlet_pressure_pa / x.inlet_pressure_pa
        eta_v = max(0.1, p['volumetric_efficiency'] - 0.01 * max(0.0, ratio - 2.0))
        mass = p['displacement_m3_s'] * p['load_ratio'] * eta_v * x.inlet_density_kg_m3 if x.enabled else 0.0
        hout = x.inlet_enthalpy_j_kg + (x.isentropic_outlet_enthalpy_j_kg - x.inlet_enthalpy_j_kg) / p['isentropic_efficiency']
        shaft = mass * (hout - x.inlet_enthalpy_j_kg)
        ctx.refrigeration.balance(mass_flow_kg_s=mass, outlet_enthalpy_j_kg=hout,
            shaft_power_w=shaft, electric_power_w=shaft / p['motor_efficiency'])

    def initialize(self, ctx):
        ctx.state['accepted_seconds'] = 0.0

    def commit_step(self, ctx, dt_s):
        ctx.state['accepted_seconds'] += dt_s

    def finalize(self, ctx):
        pass
'''

CONDENSER_SOURCE = '''class Condenser:
    def initialize(self, ctx):
        pass

    def commit_step(self, ctx, dt_s):
        pass

    def finalize(self, ctx):
        pass

    def evaluate(self, ctx):
        x = ctx.refrigeration.point
        p = ctx.parameters
        # A custom fan-speed law, with explicit natural convection at zero fan.
        ua = p['ua_w_k'] * (p['natural_ua_ratio'] + (1.0 - p['natural_ua_ratio']) * p['fan_ratio'] ** 0.8)
        ua *= p['flooded_ua_ratio'] + (1.0 - p['flooded_ua_ratio']) * p['return_gas_ratio']
        ctx.refrigeration.balance(outlet_enthalpy_j_kg=x.inlet_enthalpy_j_kg,
            heat_rejection_w=ua * (x.inlet_temperature_k - x.sink_temperature_k),
            electric_power_w=p['fan_power_w'] * p['fan_ratio'] ** 3)
'''


def definition(kind):
    compressor = kind == 'compressor'
    if kind not in ('compressor', 'condenser'):
        raise ValueError(kind)
    base = catalog_map()['refrigerant_compressor' if compressor else 'evaporative_condenser']
    payload = base.model_dump(mode='json')
    payload.update(id='author_' + kind, name='Python 本构' + ('压缩机' if compressor else '冷凝器'),
        description='自定义参考方程；平台验证能量闭合与热力学方向，设备性能未经厂家标定。',
        schema_version=5, runtime='python', solver_model='generic', state_model=None, thermal_model=None,
        execution_role='refrigeration.' + kind + '.v1',
        sdk={'api_version':'0.11.0','capabilities':['refrigeration.constitutive.v1','state.transactions.v1','context.execution.v1'],
             'state_contract_version':1},
        source={'runtime':COMPRESSOR_SOURCE if compressor else CONDENSER_SOURCE},
        entrypoint='Compressor' if compressor else 'Condenser', source_format='python-v1')
    module = ModuleDefinition.model_validate(payload)
    module.content_hash = module_content_hash(module)
    module.definition_hash = module_definition_hash(module)
    return module


def author_station_example():
    from .examples import station_example
    project = station_example()
    modules = [definition('compressor'), definition('condenser')]
    lookup = {'refrigerant_compressor':modules[0].id, 'evaporative_condenser':modules[1].id}
    for instance in project.instances:
        instance.module_id = lookup.get(instance.module_id, instance.module_id)
    project.modules.extend(modules)
    project.name = 'Python 压缩机/冷凝器本构 · 容器库存联算'
    project.id = 'author-constitutive-station-v1'
    return project
