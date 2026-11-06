"""S7 short development scenarios, exact rejection codes and independent accepted-step ledgers.

python scripts/verify_forward_scenarios.py --output artifacts/forward-scenarios
Output must not exist. No full suite, long soak or external calibration is run.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.compiler import compile_project, CompilationError  # noqa: E402
from fn_engine.models import Project  # noqa: E402
from fn_engine.sessions import create_session  # noqa: E402
from fn_engine.solver import SolveFailed  # noqa: E402
from fn_engine.hydronic_buffer_example import example as air_buffer  # noqa: E402
from fn_engine.refrigeration.forward_examples import headed_example, coil_intercooler_example, manifold_example, coupled_buffer_example  # noqa: E402


def hydronic():
    p=air_buffer(stagnant=True)
    next(i for i in p.instances if i.id=='Isolation').parameters['opening_ratio']=1.
    return p


CASES={
 'hydronic-buffer':(hydronic,('WaterIn','temperature_k',282.15),[('Isolation','opening_ratio',0.)],('Buffer','heat_input_w',1e10),'BUFFER_TEMPERATURE_RANGE',True),
 'headed-cold-room':(headed_example,('Compressor','load_ratio',.5),[('Compressor','running',0.)],('Valve','opening_ratio',2.),'PARAMETER_RANGE',False),
 'coil-intercooler':(coil_intercooler_example,('HighCompressor','load_ratio',.5),[('HighCompressor','running',0.)],('HighValve','opening_ratio',2.),'PARAMETER_RANGE',False),
 'six-cooler-room':(manifold_example,('Cooler0','fan_ratio',.3),[('Cooler0','fan_ratio',0.),('Cooler0','supply_valve_ratio',0.)],('Cooler0','fan_ratio',2.),'PARAMETER_RANGE',False),
 'coupled-buffer':(coupled_buffer_example,('WV1','opening_ratio',.4),[('WV1','opening_ratio',0.)],('Buffer','heat_input_w',1e10),'REFRIGERATION_NOT_CONVERGED',True),
}


def require(condition,message):
    if not condition:raise AssertionError(message)


def close(actual,expected,tolerance,label,checks):
    error=abs(actual-expected)
    require(error<=tolerance,f'{label}: {actual} vs {expected}, tolerance {tolerance}')
    checks.append({'check':label,'actual':actual,'expected':expected,'absolute_error':error,'tolerance':tolerance})


def state(session):
    names=('masses','energies','temperatures','counters','cells','air_rooms','tanks','committed')
    def serial(v):
        if hasattr(v,'tolist'):return v.tolist()
        if hasattr(v,'__dict__'):return {k:serial(x) for k,x in vars(v).items()}
        if isinstance(v,dict):return {str(k):serial(x) for k,x in v.items()}
        if isinstance(v,(list,tuple)):return [serial(x) for x in v]
        return v
    return {name:serial(deepcopy(getattr(session,name))) for name in names if hasattr(session,name)}


def step_checks(session,before,after,checks):
    a,b=before.variables,after.variables;dt=after.time_s-before.time_s
    require(dt>0.,'accepted time must advance')
    # Buffer balance independently recomputed from physical port enthalpies, not stored_power output.
    if 'Buffer.state.stored_energy_j' in b:
        flow=b.get('Buffer.mass_flow_kg_s',b.get('Buffer.ch0.mass_flow_kg_s'))
        inlet,outlet=('out0','in0') if flow<0 else ('in0','out0')
        heat=b['Buffer.param.heat_input_w']-b['Buffer.ambient_heat_loss_w']
        net=abs(flow)*(b[f'Buffer.{inlet}.enthalpy_j_kg']-b[f'Buffer.{outlet}.enthalpy_j_kg'])+heat
        close(b['Buffer.state.stored_energy_j']-a['Buffer.state.stored_energy_j'],dt*net,.04,'buffer independent Mh ledger',checks)
    network=session.network
    if getattr(network,'execution_domain','fluid') in ('refrigeration','coupled'):
        # Each refrigerant loop is closed; sum actual stored masses without reusing residual metrics.
        for circuit in range(len(network.circuit_fluids)):
            ids=[v for v in network.vessels if network.circuit_of[v]==circuit]
            close(sum(b[v+'.state.mass_kg'] for v in ids),sum(a[v+'.state.mass_kg'] for v in ids),1e-6,'closed circuit mass '+str(circuit),checks)
        energy=sum(b[v+'.state.internal_energy_j']-a[v+'.state.internal_energy_j'] for v in network.vessels)
        boundary=0.
        for iid,kind in network.kinds.items():
            key=lambda suffix:b.get(iid+'.'+suffix,0.)
            if kind in ('refrigerant_compressor','performance_compressor','enthalpy_compressor','dx_compressor'):boundary+=key('shaft_power_w')
            if kind in ('evaporative_condenser','air_cooled_condenser'):boundary-=key('heat_rejection_w')
            if kind=='refrigerant_pump':boundary+=key('electric_power_w')
            if kind=='air_cooler':boundary+=key('fan_power_w')+key('heater_power_w')
            if kind=='cold_room':
                energy+=network.parameters[iid]['heat_capacity_j_k']*(b[iid+'.state.temperature_k']-a[iid+'.state.temperature_k'])
                boundary+=key('envelope_heat_w')+key('param.heat_input_w')
        for link in getattr(network,'couplings',[]):boundary+=b[f'coupling.{link.id}.heat_w']
        # The stream reference includes an externally heated suction line only in other fixtures.
        close(energy,dt*boundary,.05,'independent refrigerant and room energy ledger',checks)
        for key,value in b.items():
            if key.endswith('.state.electric_energy_j'):
                power_key=key.replace('.state.electric_energy_j','.electric_power_w')
                if power_key in b:close(value-a[key],dt*b[power_key],1e-5,'accepted electric integral '+key,checks)
    for key,tolerance in [('energy_residual_w',.15),('moisture_residual_kg_s',1e-7)]:
        if key in after.metrics:require(abs(after.metrics[key])<tolerance,f'{key} too large: {after.metrics[key]}')


def perform(name,mode,entry,output):
    factory,partial,off,invalid,expected,advance_failure=entry
    project=factory();project.solver.dynamic_step_s=.1
    path=output/(name+'-'+mode+'.project.json');serialized=project.model_dump_json(indent=2)+'\n';path.write_text(serialized,encoding='utf-8')
    restored=Project.model_validate_json(path.read_text(encoding='utf-8'))
    require(restored.model_dump(mode='json')==project.model_dump(mode='json'),'project reload changed contract')
    session=create_session(compile_project(restored),.3,.1);checks=[];started=time.perf_counter()
    try:
        first=session.initialize();accepted=session.advance();step_checks(session,first,accepted,checks)
        rejection=None
        if mode=='partial':session.set_parameter(*partial)
        elif mode=='off':session.write_variables({f'{iid}.param.{key}':value for iid,key,value in off})
        if mode=='invalid':
            before_state=state(session);before_frame=session.last_accepted_frame.model_dump(mode='json') if hasattr(session,'last_accepted_frame') else session.frames[-1].model_dump(mode='json')
            before_parameters=deepcopy(session.network.parameters);revision=session.revision;time_before=session.time
            try:
                session.set_parameter(*invalid)
                if advance_failure:session.advance()
                else:raise AssertionError('invalid command unexpectedly accepted')
            except (CompilationError,SolveFailed) as error:
                diagnostic=error.diagnostic;code=diagnostic.code
                require(code==expected,f'wrong failure: {code}, expected {expected}: {error}')
                require(state(session)==before_state,'failed operation changed physical state')
                require(session.time==time_before,'failed operation advanced accepted time')
                frame=session.last_accepted_frame.model_dump(mode='json') if hasattr(session,'last_accepted_frame') else session.frames[-1].model_dump(mode='json')
                require(frame==before_frame,'failed operation replaced accepted frame')
                if advance_failure:
                    require(session.revision==revision+1,'acknowledged input revision lost')
                    require(session.network.parameters[invalid[0]][invalid[1]]==invalid[2],'acknowledged command rolled back incorrectly')
                else:
                    require(session.revision==revision,'rejected command increased revision')
                    require(session.network.parameters==before_parameters,'rejected command partly applied')
                rejection={'code':code,'message':str(error),'accepted_time_s':session.time,'parameter_revision':session.revision,
                    'failure_stage':'candidate_step' if advance_failure else 'parameter_command','physical_rollback_verified':True}
            require(rejection is not None,'expected rejection not observed')
            final=accepted
        else:
            final=session.advance();step_checks(session,accepted,final,checks)
            if mode=='partial':require(final.variables[f'{partial[0]}.param.{partial[1]}']==partial[2],'requested setting not sampled')
            if mode=='off':
                for iid,key,value in off:require(final.variables[f'{iid}.param.{key}']==value,'off command not sampled')
                stopped={'hydronic-buffer':'Buffer.mass_flow_kg_s','headed-cold-room':'Compressor.mass_flow_kg_s',
                    'coil-intercooler':'HighCompressor.mass_flow_kg_s','six-cooler-room':'Cooler0.supply_mass_flow_kg_s','coupled-buffer':'Buffer.mass_flow_kg_s'}[name]
                close(final.variables[stopped],0.,1e-8,'stopped equipment flow',checks)
        record={'id':name+'-'+mode,'status':'passed','project_sha256':hashlib.sha256(serialized.encode()).hexdigest(),
            'saved_project':path.name,'reload_equal':True,'accepted_time_s':session.time,'parameter_revision':session.revision,
            'wall_time_s':time.perf_counter()-started,'checks':checks,'expected_rejection':rejection,
            'last_accepted_frame':final.model_dump(mode='json')}
        return record
    finally:session.close()


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'artifacts/forward-scenarios');args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    report={'created_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),
        'scope':'Short 0.1-second accepted steps; development assumptions, no wall-clock soak or field calibration',
        'results':[],'status':'running'}
    try:
        for name,entry in CASES.items():
            for mode in ('normal','partial','off','invalid'):
                print(name,mode,flush=True);report['results'].append(perform(name,mode,entry,args.output))
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['failure']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'scenarios':len(report['results']),'output':str(args.output)},ensure_ascii=False))
if __name__=='__main__':main()
