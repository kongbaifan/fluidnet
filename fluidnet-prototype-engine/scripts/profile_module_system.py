"""Fixed cold-5/hot-7 A/B profiles of small/medium/large mixed fluid networks."""
import argparse
import ctypes
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


def rss(pid):
    if os.name!='nt':
        try:
            return int(Path(f'/proc/{pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
        except (OSError,IndexError): return 0
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('faults',wintypes.DWORD)]+[(name,ctypes.c_size_t) for name in
            ['peak','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile']]
    kernel=ctypes.windll.kernel32
    kernel.OpenProcess.restype=wintypes.HANDLE
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return 0
    try:
        counters=Counters();counters.cb=ctypes.sizeof(counters)
        ctypes.windll.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE,ctypes.POINTER(Counters),wintypes.DWORD]
        return counters.working if ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb) else 0
    finally: kernel.CloseHandle(wintypes.HANDLE(handle))


def project(size,shards,optimized):
    from numerics_cases import series_project
    from fn_engine.models import ModuleDefinition
    p=series_project(size+2,python_fraction=.5)
    module=next(m for m in p.modules if m.runtime=='python')
    payload=module.model_dump(mode='json')
    payload.update(schema_version=3,sdk={'api_version':'0.5.0','capabilities':['net.valve','evaluate.pure.v1']},
        pure_evaluate=True,content_hash=None,definition_hash=None)
    # The benchmark module declares a pure fixed relation, with no observer identity or side effects.
    payload['source']={'runtime':'''class Module:
    def initialize(self,ctx): pass
    def evaluate(self,ctx): ctx.net.valve(channel='main',kv=ctx.parameter('kv_m3_h'),opening=ctx.parameter('opening_ratio'))
    def commit_step(self,ctx,dt): pass
    def finalize(self,ctx): pass
'''}
    payload['variables']=[]
    p.modules=[ModuleDefinition.model_validate(payload) if m.runtime=='python' else m for m in p.modules]
    p.solver.thermal=False;p.solver.hydraulic_method='sparse';p.solver.hydraulic_diagnostics=True
    p.solver.module_parallelism=shards;p.solver.module_cache=optimized;p.solver.module_mixed_jacobian=optimized
    return p


def measure(size,shards,optimized,hot):
    from fn_engine.compiler import compile_project
    from fn_engine.solver import _python_runners,_close_runners,solve_network
    from fn_engine.runtime import WorkerProcess,module_content_hash,module_definition_hash
    started=time.perf_counter();p=project(size,shards,optimized)
    at=time.perf_counter();network=compile_project(p);compile_s=time.perf_counter()-at
    trace={'requests':0,'request_s':0.,'serialize_s':0.,'instance_evaluations':0,'cache_hits':0}
    original=WorkerProcess._request
    def request(worker,payload):
        before=time.perf_counter();json.dumps(payload,ensure_ascii=False);trace['serialize_s']+=time.perf_counter()-before
        before=time.perf_counter();response=original(worker,payload);trace['request_s']+=time.perf_counter()-before
        trace['requests']+=1
        items=response.values() if payload['action']=='batch' else [response]
        for item in items:
            if isinstance(item,dict) and 'relations' in item:
                trace['instance_evaluations']+=1;trace['cache_hits']+=int(item.get('cache_hit',False))
        return response
    WorkerProcess._request=request
    runners={};stop=threading.Event();peak=[rss(os.getpid())]
    def memory():
        while not stop.wait(.025):
            workers=getattr(runners,'workers',list(runners.values()))
            peak[0]=max(peak[0],rss(os.getpid())+sum(rss(w.process.pid) for w in workers if w.process))
    thread=threading.Thread(target=memory,daemon=True);thread.start()
    try:
        at=time.perf_counter();runners=_python_runners(network);initialization_s=time.perf_counter()-at
        at=time.perf_counter();warm=solve_network(network,runners);first_s=time.perf_counter()-at
        first_available_s=time.perf_counter()-started
        samples=[]
        if hot:
            solve_network(network,runners,warm=warm) # warm-up excluded
            for _ in range(7):
                before=dict(trace);at=time.perf_counter();warm=solve_network(network,runners,warm=warm)
                samples.append({'wall_s':time.perf_counter()-at,'pressure_residual_pa':warm.hydraulic.pressure_residual,
                    'mass_residual_kg_s':warm.hydraulic.mass_residual,'flow_kg_s':float(warm.hydraulic.flows[0]),
                    'counters':warm.hydraulic.counters,'rpc':{key:trace[key]-before[key] for key in trace}})
        module=next(m for m in p.modules if m.runtime=='python')
        return {'size':size,'shards':shards,'optimized':optimized,'compile_s':compile_s,'initialization_s':initialization_s,
            'first_s':first_s,'first_available_s':first_available_s,'peak_tree_rss_bytes':peak[0],
            'trace':trace,'hot_samples':samples,'content_hash':module_content_hash(module),'definition_hash':module_definition_hash(module),
            'project':p.model_dump(mode='json'),'passed':warm.hydraulic.pressure_residual<=1 and warm.hydraulic.mass_residual<=1e-8}
    finally:
        stop.set();thread.join(timeout=1);_close_runners(runners);WorkerProcess._request=original


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='artifacts/module-system/98dadd5/MOD-P5')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--size',type=int,default=4)
    parser.add_argument('--shards',type=int,default=1);parser.add_argument('--optimized',action='store_true')
    args=parser.parse_args()
    if args.worker:
        print(json.dumps(measure(args.size,args.shards,args.optimized,False)));return
    target=Path(args.output).resolve()
    if not target.is_relative_to((ROOT/'artifacts/module-system').resolve()) or target.exists():
        raise ValueError('性能证据必须写入新的 artifacts/module-system 目录')
    target.mkdir(parents=True)
    rows=[]
    for size in [4,16,40]:
        for shards in [1,2]:
            for optimized in [False,True]:
                cold=[]
                for sample in range(5):
                    command=[sys.executable,__file__,'--worker','--size',str(size),'--shards',str(shards)]+(['--optimized'] if optimized else [])
                    start=time.perf_counter();result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
                    if result.returncode:raise RuntimeError(result.stderr)
                    record=json.loads(result.stdout);record['process_wall_s']=time.perf_counter()-start;cold.append(record)
                hot=measure(size,shards,optimized,True)
                row={'size':size,'shards':shards,'optimized':optimized,'cold_samples':cold,'hot':hot,
                    'cold_median_s':statistics.median(r['process_wall_s'] for r in cold),
                    'hot_median_s':statistics.median(r['wall_s'] for r in hot['hot_samples']),
                    'failures':sum(not r['passed'] for r in cold)+sum(r['pressure_residual_pa']>1 or r['mass_residual_kg_s']>1e-8 for r in hot['hot_samples'])}
                (target/f'{size}-{shards}-{int(optimized)}.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
                rows.append(row);print(json.dumps({key:row[key] for key in ['size','shards','optimized','cold_median_s','hot_median_s','failures']}),flush=True)
    comparisons=[]
    for base,optimized in zip(rows[::2],rows[1::2],strict=True):
        gain=1-optimized['hot_median_s']/base['hot_median_s']
        comparisons.append({'size':base['size'],'shards':base['shards'],'hot_improvement':gain,'target_met':gain>=.2,
            'equivalent_flow':abs(base['hot']['hot_samples'][-1]['flow_kg_s']-optimized['hot']['hot_samples'][-1]['flow_kg_s'])<=1e-8+1e-6*abs(base['hot']['hot_samples'][-1]['flow_kg_s'])})
    summary={'environment':{'python':sys.version,'platform':platform.platform(),'processor':platform.processor(),'threads':1},
        'protocol':{'cold':5,'hot':7,'warmup':1,'timing_overlap':'RPC includes serialization/worker execution; not additive to solve wall time'},
        'comparisons':comparisons,'defaults_enabled':False,'reason':'Optional optimizations remain off pending workload benefit and review.'}
    (target/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
