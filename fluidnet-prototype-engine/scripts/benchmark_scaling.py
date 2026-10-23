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
from fn_engine.compiler import compile_project
from fn_engine.runtime import WorkerProcess
from numerics_cases import series_project


def make_network(size, python_fraction=0):
    """原 100/500/1000 串联入口；样例工厂迁移后保持函数名与语义不变。"""
    return series_project(size, python_fraction)


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
        # 部分 Python 多端口模块只暴露 <实例>.<通道>.mass_flow，不一定有 2 段聚合流量；
        # 没有合适的流量字段时返回 None，不让单个展示字段影响整组基准。
        flow = next((value for key,value in frame.variables.items()
                     if len(key.split('.')) == 2 and key.endswith('.mass_flow_kg_s')), None)
        return {'compile_s':compile_s,'solve_s':solve_s,'serialize_s':serialize_s,**totals,'peak_rss_mb':memory[0]/1024**2,
                'result_bytes':len(data.encode()),'flow':flow,**frame.metrics}
    finally:stop.set();thread.join()


def build_parser():
    """原 CLI 语义保持不变；新增的 --families 只追加复杂拓扑档位。"""
    parser=argparse.ArgumentParser()
    parser.add_argument('--sizes',default='100,500,1000')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--output',default='artifacts/scaling-benchmark.json')
    parser.add_argument('--families',default='',
                        help='逗号分隔的复杂拓扑（series/parallel/mesh/components/thermal-dual-loop/python-multiport）')
    parser.add_argument('--tiers',default='small,medium,large')
    return parser


def main(argv=None):
    args=build_parser().parse_args(argv)
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
    if args.families:
        from numerics_cases import build_project, describe
        for family in [name.strip() for name in args.families.split(',') if name.strip()]:
            for tier in [name.strip() for name in args.tiers.split(',') if name.strip()]:
                model=build_project(family,tier);model.solver.hydraulic_method='sparse'
                counts=describe(compile_project(model))
                samples=[measure(model) for _ in range(args.repeats)]
                case={'family':family,'tier':tier,**counts,
                      'median':{key:statistics.median(row[key] for row in samples) for key in samples[0]},
                      'samples':samples}
                report['cases'].append(case);path.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(json.dumps({k:v for k,v in case.items() if k!='samples'}),flush=True)


if __name__=='__main__':main()
