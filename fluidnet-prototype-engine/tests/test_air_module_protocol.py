"""P01：真实单 Worker 与批量 Worker 的四阶段湿空气合同。"""
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError,compile_project
from fn_engine.models import ModuleDefinition,ModuleInstance
from fn_engine.module_contracts import air_request_payload
from fn_engine.simulation import SimulationSession
from test_moist_air_phase2 import PA,air_project,boundary,link

SOURCE='''
class Module:
    def initialize(self,ctx):
        ctx.state['steps']=0
    def check(self,ctx,flows=False):
        for port in ctx.ports.values():
            assert port.humidity_ratio_kg_kg is not None
            assert port.enthalpy_j_kg_dry_air is not None
            assert abs(port.enthalpy_j_kg*(1+port.humidity_ratio_kg_kg)-port.enthalpy_j_kg_dry_air)<1e-6
        if flows:
            channel=ctx.channel('ch0')
            assert channel.dry_air_mass_flow_kg_s is not None
            assert abs(channel.mass_flow_kg_s-channel.dry_air_mass_flow_kg_s*1.008)<1e-8
    def evaluate(self,ctx):
        self.check(ctx)
        ctx.net.resistance(channel='ch0',diameter_m=.4,loss_coefficient=4.)
    def thermal(self,ctx):
        self.check(ctx,True)
        ctx.heat('ch0',0.)
    def observe(self,ctx):
        self.check(ctx,True)
    def commit_step(self,ctx,dt_s):
        self.check(ctx,True)
        ctx.state['steps']+=1
'''


def protocol_project():
    c=catalog_map();base=c['heater'].model_dump(exclude={'parameters','variables','source'})
    module=ModuleDefinition.model_validate(base|{'id':'probe','schema_version':3,'runtime':'python','solver_model':'generic',
        'entrypoint':'module:Module','source':{'runtime':SOURCE},'sdk':{'api_version':'0.6.0','state_contract_version':1,
        'capabilities':['lifecycle.v1','state.json.v1','net.resistance','air.properties.v1','air.pass_through.v1','thermal.v1','observe.v1']}})
    return air_project([boundary('A',PA+100),ModuleInstance(id='Probe',module_id='probe',name='协议探针'),boundary('Z')],
                       [link('a',('A','out0'),('Probe','in0')),link('z',('Probe','out0'),('Z','out0'))],[c['source'],module])


@pytest.mark.parametrize('batch',[True,False])
def test_complete_state_in_four_callback_phases(batch):
    project=protocol_project();project.solver.batch_modules=batch
    session=SimulationSession(compile_project(project),1.,1.)
    try:
        session.initialize();frame=session.advance()
        assert frame.variables['Probe.state.steps']==1
    finally:
        session.close()


def test_old_module_is_rejected_before_wet_execution_and_filtered_for_old_rpc():
    project=protocol_project();module=project.modules[-1]
    module.sdk.capabilities.remove('air.pass_through.v1')
    with pytest.raises(CompilationError) as exc:
        compile_project(project)
    assert exc.value.diagnostic.code=='MODULE_AIR_CAPABILITY_REQUIRED'
    payload={'request':{'trial_ports':{'p':{'pressure_pa':101325.,'humidity_ratio_kg_kg':.008}},
                        'readonly_state':{'humidity_ratio_kg_kg':123}}}
    output=air_request_payload(module,payload)
    assert output['request']['trial_ports']['p']=={'pressure_pa':101325.}
    assert output['request']['readonly_state']==payload['request']['readonly_state']


def test_standalone_bench_uses_same_wet_protocol():
    from fn_engine.bench import run_module_test
    from fn_engine.models import ModuleTestRequest
    project=protocol_project()
    result=run_module_test(ModuleTestRequest(module=project.modules[-1],fluid=project.fluid,
        inlet_pressure_pa=PA+100,outlet_pressure_pa=PA,temperature_k=293.15,
        moist_air=True,moist_air_options={'contract_version':1},property_coupling='node',duration_s=.1,dt_s=.1))
    assert result.frame.variables['D1.state.steps']==1


def test_forced_module_flow_is_public_mixture_mass():
    from fn_engine.solver import solve_steady
    project=protocol_project();module=project.modules[-1]
    module.sdk.capabilities.append('net.compressor')
    module.source['runtime']=SOURCE.replace("ctx.net.resistance(channel='ch0',diameter_m=.4,loss_coefficient=4.)",
                                          "ctx.net.compressor(channel='ch0',forced_mass_flow_kg_s=1.008)")
    values=solve_steady(compile_project(project)).variables
    assert values['Probe.mass_flow_kg_s']==pytest.approx(1.008,rel=1e-8)
    assert values['Probe.dry_air_mass_flow_kg_s']==pytest.approx(1.,rel=1e-8)
