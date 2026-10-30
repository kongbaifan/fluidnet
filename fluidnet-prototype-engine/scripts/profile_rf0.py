"""Isolated A/B timings using the frozen RF-0 budget; --formal measures the released SDK path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='1'

from profile_module_system import rss  # noqa: E402
from rf0_probe import ProbeSession, compile_probe, throttle_module  # noqa: E402
from fn_engine.compiler import compile_project  # noqa: E402
from fn_engine.refrigeration.examples import station_case  # noqa: E402
from fn_engine.refrigeration.station import StationSession  # noqa: E402


def measure(mode,config,formal=False):
    project=station_case()
    if formal and mode=='python':
        from fn_engine.module_templates import create_template
        module=create_template('refrigeration_throttle','profile_author_throttle','Profile author throttle')
        project.modules.append(module)
        next(i for i in project.instances if i.id=='EV1').module_id=module.id
    began=time.perf_counter()
    network=compile_probe(project,{'EV1':throttle_module()}) if mode=='python' and not formal else compile_project(project)
    compile_s=time.perf_counter()-began
    cls=ProbeSession if mode=='python' and not formal else StationSession
    session=cls(network,config['duration_s'],config['dt_s'])
    if formal:
        # Count real transport actions without changing request/response handling.
        def trace(runner):
            invoke=runner._request_impl
            runner.actions={};runner.rpc_seconds=0.
            def counted(payload):
                action=payload['action'];runner.actions[action]=runner.actions.get(action,0)+1
                began=time.perf_counter()
                try:return invoke(payload)
                finally:runner.rpc_seconds+=time.perf_counter()-began
            runner._request_impl=counted
        for runner in session.runners.values():trace(runner)
    peak=[rss(os.getpid())];stop=threading.Event()
    def memory():
        while not stop.wait(.025):
            workers=[*session.runners.values(),*session.scripts.values()]
            peak[0]=max(peak[0],rss(os.getpid())+sum(rss(worker.process.pid) for worker in workers if worker.process))
    watcher=threading.Thread(target=memory,daemon=True);watcher.start()
    try:
        began=time.perf_counter();session.initialize();initialization_s=time.perf_counter()-began
        samples=[]
        for index in range(config['candidate_warmups']+config['candidate_samples']):
            began=time.perf_counter();point=session._evaluate(session.masses,session.energies,session.temperatures)
            elapsed=time.perf_counter()-began
            if index>=config['candidate_warmups']:samples.append(elapsed)
        initial_flow=point['devices']['EV1']['mass_flow_kg_s']
        began=time.perf_counter()
        while not session.done:session.advance()
        dynamic_s=time.perf_counter()-began
        frame=session.frames[-1]
        result={'mode':mode,'compile_s':compile_s,'initialization_s':initialization_s,
            'candidate_samples_s':samples,'candidate_median_s':statistics.median(samples),'dynamic_s':dynamic_s,
            'newton_iterations':session.nonlinear_iterations,'initial_flow_kg_s':initial_flow,
            'final_variables':frame.variables,'final_metrics':frame.metrics,
            'final_masses':session.masses,'final_energies':session.energies,'final_temperatures':session.temperatures,
            'source_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                ['backend/fn_engine/refrigeration/station.py','scripts/profile_rf0.py',
                 *(['backend/fn_engine/refrigeration/module_adapter.py','backend/fn_engine/runtime.py',
                    'backend/fn_engine/worker.py','modules/isenthalpic_throttle/module.py'] if formal else
                   ['scripts/rf0_probe.py','examples/refrigeration_extensions/rf0_throttle.py'])]}}
        workers=[*session.runners.values(),*session.scripts.values()]
        processes=[worker.process for worker in workers if worker.process]
        # Use the counted RPC path for module finalization too.
        for worker in session.runners.values():worker.finalize()
        session.close()
        result['rpc']={worker.execution.instance_id:{'requests':worker.request_count,
            'actions':getattr(worker,'actions',None),'seconds':getattr(worker,'rpc_seconds',None)} for worker in workers}
        result['all_workers_reclaimed']=all(process.poll() is not None for process in processes)
        result['peak_sampled_rss_bytes']=peak[0]
        return result
    finally:
        session.close();stop.set();watcher.join(timeout=2)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sample',choices=['builtin','python'])
    parser.add_argument('--formal',action='store_true',help='Measure schema 4 / SDK 0.7.0 in the normal StationSession')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output is None:args.output=ROOT/'artifacts/platform-extension'/('rf2' if args.formal else 'rf0')
    budget_path=ROOT/'docs/platform-extension/rf0-performance-budget.json'
    config=json.loads(budget_path.read_text(encoding='utf-8'))
    if args.sample:
        print(json.dumps(measure(args.sample,config,args.formal),allow_nan=False));return
    args.output.mkdir(parents=True,exist_ok=True)
    samples=[]
    for index in range(config['repeats']):
        # Alternate order to reduce warm-machine/order bias; each sample is a new Python process.
        for mode in (['builtin','python'] if index%2==0 else ['python','builtin']):
            received=subprocess.run([sys.executable,__file__,'--sample',mode,*(['--formal'] if args.formal else [])],cwd=ROOT,capture_output=True,text=True,
                encoding='utf-8',env={**os.environ,'PYTHONUTF8':'1'},timeout=180,check=True)
            sample=json.loads(received.stdout);sample['repeat']=index;samples.append(sample)
            (args.output/f'{index}-{mode}.json').write_text(json.dumps(sample,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({key:sample[key] for key in ['repeat','mode','initialization_s','candidate_median_s','dynamic_s','newton_iterations']}),flush=True)
    summaries={mode:{key:statistics.median(sample[key] for sample in samples if sample['mode']==mode)
                    for key in ['initialization_s','candidate_median_s','dynamic_s','peak_sampled_rss_bytes','newton_iterations']}
               for mode in ['builtin','python']}
    base,custom=summaries['builtin'],summaries['python'];limits=config['limits']
    checks={
        'initialization':custom['initialization_s']-base['initialization_s']<=limits['initialization_extra_s'],
        'candidate':custom['candidate_median_s']-base['candidate_median_s']<=limits['candidate_median_extra_s'],
        'dynamic':custom['dynamic_s']-base['dynamic_s']<=max(limits['dynamic_extra_s_floor'],base['dynamic_s']*limits['dynamic_extra_fraction']),
        'memory':custom['peak_sampled_rss_bytes']-base['peak_sampled_rss_bytes']<=limits['peak_sampled_rss_extra_bytes'],
        'workers':all(sample['all_workers_reclaimed'] for sample in samples),
        'iterations':all(sample['newton_iterations']==samples[0]['newton_iterations'] for sample in samples),
        'same_sources':all(sample['source_hashes']==samples[0]['source_hashes'] for sample in samples),
    }
    # Full-station numerical comparison uses the built-in sample independently of the author source.
    reference=next(sample for sample in samples if sample['mode']=='builtin')
    differences={field:max(abs(sample[field][key]-reference[field][key]) for sample in samples for key in reference[field])
                 for field in ['final_masses','final_energies','final_temperatures']}
    checks['physics']=differences['final_masses']<1e-9 and differences['final_energies']<1e-5 and differences['final_temperatures']<1e-9
    summary={'protocol':'schema4-sdk0.7' if args.formal else 'rf0-experiment',
        'configuration':config,'budget_sha256':hashlib.sha256(budget_path.read_bytes()).hexdigest(),
        'environment':{'python':sys.version,'platform':platform.platform(),'processor':platform.processor(),
                       'logical_cpus':os.cpu_count()},'medians':summaries,'checks':checks,'max_differences':differences,
        'steady':{'supported':False,'code':'REFRIGERATION_DYNAMIC_REQUIRED','replacement_measurement':'fixed-candidate evaluation, not a steady solve'},
        'samples':samples}
    (args.output/'performance.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({'medians':summaries,'checks':checks,'max_differences':differences},ensure_ascii=False),flush=True)
    if not all(checks.values()):raise SystemExit('性能或数值门槛未通过')


if __name__=='__main__':main()
