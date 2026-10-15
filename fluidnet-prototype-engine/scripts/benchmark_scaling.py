"""Reproducible single-native-thread scaling runs; no vendor speed claims."""
import os
for name in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name]='1'

import argparse
import json
import platform
from pathlib import Path
import statistics
import threading
import time
from unittest.mock import patch

import psutil
from fn_engine import solver
from fn_engine.catalog import catalog_map
from fn_engine.compiler import compile_project
from fn_engine.models import Project, ModuleInstance, Endpoint, Connection
from fn_engine.packages import load_module_package
from fn_engine.runtime import WorkerProcess


def make_network(size, python_fraction=0):
    catalog=catalog_map()
    count=size-2
    definitions=[catalog['source'],catalog['pipe']]
    module=load_module_package(Path(__file__).resolve().parents[1]/'modules/programmable_valve')
    if python_fraction:definitions.append(module)
    nodes=[ModuleInstance(id='B1',module_id='source',name='in',parameters={'pressure_pa':250000})]
    for i in range(count):
        custom=i<int(count*python_fraction)
        nodes.append(ModuleInstance(id=f'N{i}',module_id=module.id if custom else 'pipe',name=str(i),
                                    parameters={'opening_ratio':.8,'kv_m3_h':16} if custom else {'length_m':1.}))
    nodes.append(ModuleInstance(id='B2',module_id='source',name='out',parameters={'pressure_pa':120000}))
    links=[]
    for i,(a,b) in enumerate(zip(nodes,nodes[1:])):
        links.append(Connection(id=f'e{i}',source=Endpoint(instance_id=a.id,port_id='out0'),
                                target=Endpoint(instance_id=b.id,port_id='out0' if b.id=='B2' else 'in0')))
    return Project(id='scale',name=f'{size} instances',modules=definitions,instances=nodes,connections=links)


def measure(model):
    totals={'hydraulic_s':0.,'thermal_s':0.,'worker_rpc_s':0.}
    timing_lock=threading.Lock()
    def timed(key,fn):
        def call(*args,**kwargs):
            begin=time.perf_counter()
            try:return fn(*args,**kwargs)
            finally:
                with timing_lock:totals[key]+=time.perf_counter()-begin
        return call
    process=psutil.Process()
    memory=[0];stop=threading.Event()
    def sample():
        while not stop.is_set():
            try:
                total=process.memory_info().rss
                for child in process.children(recursive=True):
                    try:total+=child.memory_info().rss
                    except psutil.Error:pass
                memory[0]=max(memory[0],total)
            except psutil.Error:pass
            stop.wait(.01)
    thread=threading.Thread(target=sample,daemon=True);thread.start()
    start=time.perf_counter();network=compile_project(model);compile_s=time.perf_counter()-start
    try:
        with patch.object(solver,'_solve_hydraulics',timed('hydraulic_s',solver._solve_hydraulics)), \
             patch.object(solver,'solve_thermal',timed('thermal_s',solver.solve_thermal)), \
             patch.object(WorkerProcess,'_request',timed('worker_rpc_s',WorkerProcess._request)):
            start=time.perf_counter();frame=solver.solve_steady(network);solve_s=time.perf_counter()-start
        start=time.perf_counter();data=frame.model_dump_json();serialize_s=time.perf_counter()-start
        flow = next(value for key,value in frame.variables.items() if len(key.split('.')) == 2 and key.endswith('.mass_flow_kg_s'))
        return {'compile_s':compile_s,'solve_s':solve_s,'serialize_s':serialize_s,**totals,'peak_rss_mb':memory[0]/1024**2,
                'result_bytes':len(data.encode()),'flow':flow,**frame.metrics}
    finally:stop.set();thread.join()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sizes',default='100,500,1000')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',default='artifacts/scaling-benchmark.json')
    args=parser.parse_args()
    report={'hardware':platform.platform(),'cpu':platform.processor(),'native_threads':1,'repeats':args.repeats,'cases':[],
            'notes':'RPC totals are summed across Workers and overlap hydraulic time. Peak RSS includes child processes. First compile includes cold property initialization.'}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    cases=[(int(size),0.,method,True,1) for size in args.sizes.split(',') for method in ('dense','sparse')]
    cases += [(30,fraction,'sparse',batch,threads) for fraction in (.25,1.) for batch,threads in ((False,1),(True,1),(True,2))]
    for size,fraction,method,batch,threads in cases:
        model=make_network(size,fraction);model.solver.hydraulic_method=method
        model.solver.batch_modules=batch;model.solver.module_parallelism=threads
        samples=[measure(model) for _ in range(args.repeats)]
        case={'instances':size,'python_fraction':fraction,'method':method,'batch':batch,'workers':threads,
              'median':{key:statistics.median(row[key] for row in samples) for key in samples[0]},'samples':samples}
        report['cases'].append(case);path.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in case.items() if k!='samples'}),flush=True)


if __name__=='__main__':main()
