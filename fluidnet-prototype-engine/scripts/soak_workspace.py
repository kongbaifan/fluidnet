"""Durable wall-clock soak runner. It writes progress atomically until completion."""
import os
for variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[variable]='1'
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import platform

import psutil
from fastapi.testclient import TestClient
from fn_engine.api import create_app
from fn_engine.models import ControlScript
from acceptance_cases import parallel


def child_processes(process):
    """Split live children into fn_engine Workers and everything else.

    A hidden background launch (PowerShell `Start-Process -WindowStyle Hidden`, scheduled task)
    gives python a `conhost.exe` child that lives until python exits. Counting it as a Worker made
    the 2026-10-15 24 h run report 「停止后仍残留 Worker」 while no Worker was left.
    """
    workers, others = [], []
    for child in process.children(recursive=True):
        try:
            if not child.is_running():
                continue
            (workers if 'fn_engine.worker' in ' '.join(child.cmdline()) else others).append(child)
        except (psutil.Error, OSError):
            continue
    return workers, others


def run(hours, directory, case='hydraulic'):
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/'progress.json').exists():
        raise ValueError('测试目录已有记录，请选择新目录以保留原始证据')
    process=psutil.Process()
    started=time.monotonic()
    report={'status':'running','pid':os.getpid(),'process_created_at':process.create_time(),
            'platform':platform.platform(),'started_at':datetime.now(timezone.utc).isoformat(),
            'target_hours':hours,'samples':[],'errors':[],'commands':0}
    def save():
        report['elapsed_s']=time.monotonic()-started
        temporary=directory/'progress.pending'
        temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,directory/'progress.json')
    save()
    run_id=None
    try:
        with TestClient(create_app(data_root=directory/'workspace',module_storage_root=directory/'modules')) as client:
            if case=='cold-store':
                # Cold-store case A: thermostat script, cycle Newton and room/goods state; 30× real time.
                from fn_engine.refrigeration.examples import room_example
                model=room_example()
                request={'project':model.model_dump(mode='json'),'mode':'dynamic','duration_s':None,'dt_s':30.,
                         'execution_mode':'realtime','speed_ratio':30.,'history_window':100,'history':'trend',
                         'trend_variables':['ROOM1.state.temperature_k']}
            else:
                request=None
                model=parallel(python_valve=True)
            if request is None:
              model.control_scripts=[ControlScript(id='soak',enabled=True,sample_s=1.,inputs=['V1.mass_flow_kg_s'],
                outputs=['P1.param.speed_ratio'],source='''def initialize(ctx): ctx.state["samples"] = 0
def step(ctx, dt_s):
    ctx.read("V1.mass_flow_kg_s")
    ctx.write("P1.param.speed_ratio", 0.6 + 0.1 * (int(ctx.time_s / 60) % 2))
    ctx.state["samples"] += 1
def finalize(ctx): pass
''')]
              request={'project':model.model_dump(mode='json'),
                'mode':'dynamic','duration_s':None,'dt_s':1.,'execution_mode':'realtime','history_window':100,
                'history':'trend','trend_variables':['V1.mass_flow_kg_s']}
            report['case']=case
            response=client.post('/api/v1/runs?background=true',json=request)
            response.raise_for_status();run_id=response.json()['run_id'];report['run_id']=run_id
            deadline=time.monotonic()+30
            while True:
                record=client.get('/api/v1/runs/'+run_id).json()
                if record['status']=='failed':raise RuntimeError(str(record['frame']))
                if record['frame']:break
                if time.monotonic()>deadline:raise RuntimeError('运行初始化超时')
                time.sleep(.1)
            started=time.monotonic();report['started_at']=datetime.now(timezone.utc).isoformat()
            next_command=60.;next_backup=300.
            while time.monotonic()-started<hours*3600:
                record=client.get('/api/v1/runs/'+run_id).json()
                if record['status']=='failed':raise RuntimeError(str(record['frame']))
                elapsed=time.monotonic()-started
                if elapsed>=next_command and record['frame']:
                    for action in ('pause','step','resume'):
                        receipt=client.post(f'/api/v1/runs/{run_id}/command',json={'action':action})
                        receipt.raise_for_status()
                        key=receipt.json()['command_id']
                        deadline=time.monotonic()+30
                        while True:
                            events=client.get(f'/api/v1/runs/{run_id}/events').json()['events']
                            latest=next((e for e in reversed(events) if e['command_id']==key),None)
                            if latest and latest['command_status']=='applied':break
                            if latest and latest['command_status']=='rejected':raise RuntimeError(str(latest))
                            if time.monotonic()>deadline:raise RuntimeError('命令生效超时')
                            time.sleep(.05)
                        if action=='step':
                            while client.get('/api/v1/runs/'+run_id).json()['status']!='paused':
                                if time.monotonic()>deadline:raise RuntimeError('单步超时')
                                time.sleep(.05)
                        report['commands']+=1
                    next_command=elapsed+60
                if elapsed>=next_backup:
                    backup=client.post('/api/v1/workspace/backup',json={});backup.raise_for_status()
                    (directory/'latest-backup.zip').write_bytes(backup.content)
                    next_backup=elapsed+300
                workers,others=child_processes(process)
                memory=process.memory_info().rss+sum(c.memory_info().rss for c in workers+others if c.is_running())
                history=client.get(f'/api/v1/runs/{run_id}/history').json()
                if len(history['rows'])>100:raise RuntimeError('历史窗口越界')
                if record['frame'] and record['frame']['metrics'].get('mass_residual_kg_s',0)>1e-6:
                    raise RuntimeError('质量守恒残差超限')
                if record['frame'] and abs(record['frame']['metrics'].get('energy_residual_j',0))>100.:
                    raise RuntimeError('能量账本残差超限')
                report['samples'].append({'elapsed_s':elapsed,'rss_bytes':memory,'workers':len(workers),
                    'other_children':sorted(c.name() for c in others),
                    'total_rows':record['total_rows'],'history_rows':len(history['rows']),
                    'storage':client.get('/api/v1/workspace/storage').json()})
                save();time.sleep(min(30,max(.1,hours*3600-(time.monotonic()-started))))
            client.post(f'/api/v1/runs/{run_id}/command',json={'action':'stop'}).raise_for_status()
            deadline=time.monotonic()+30
            while client.get('/api/v1/runs/'+run_id).json()['status']!='cancelled':
                if time.monotonic()>deadline:raise RuntimeError('停止超时')
                time.sleep(.05)
        with TestClient(create_app(data_root=directory/'workspace',module_storage_root=directory/'modules')) as client:
            restored=client.get('/api/v1/runs/'+run_id).json()
            if restored['status'] not in {'cancelled','interrupted'}:raise RuntimeError('停止归档恢复失败')
            report['restored_status']=restored['status']
        samples=[row['rss_bytes'] for row in report['samples'] if row['elapsed_s']>=1800]
        if samples:
            baseline=sum(samples[:10])/len(samples[:10]);report['warm_rss_bytes']=baseline
            report['peak_warm_rss_bytes']=max(samples)
            if max(samples)>baseline+max(64*1024**2,baseline*.25):raise RuntimeError('预热后内存增长超出验收阈值')
        # Workers exit asynchronously after terminate(); give them the same grace as the tests.
        deadline=time.monotonic()+30
        workers,others=child_processes(process)
        while workers and time.monotonic()<deadline:
            time.sleep(.05);workers,others=child_processes(process)
        report['workers_after_stop']=len(workers)
        report['other_children_after_stop']=sorted(c.name() for c in others)
        if workers:raise RuntimeError('停止后仍残留 Worker：'+'; '.join(' '.join(c.cmdline()) for c in workers))
        report['status']='completed'
    except BaseException as error:
        report['status']='failed';report['errors'].append(str(error));raise
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat();save()


def status(directory):
    path=directory/'progress.json'
    report=json.loads(path.read_text(encoding='utf-8'))
    alive=False
    try:
        process=psutil.Process(report['pid'])
        alive=(process.create_time()==report['process_created_at']) if 'process_created_at' in report else (
            any(Path(arg).name=='soak_workspace.py' for arg in process.cmdline()))
    except psutil.NoSuchProcess:
        pass
    return {'status':'interrupted' if report['status']=='running' and not alive else report['status'],
            'process_alive':alive,'last_update_age_s':time.time()-path.stat().st_mtime,
            **{key:report.get(key) for key in ('started_at','target_hours','elapsed_s','commands','errors')},
            'samples':len(report['samples']),'latest':report['samples'][-1] if report['samples'] else None}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--hours',type=float,default=24)
    parser.add_argument('--status',action='store_true',help='核对进程及最新记录，不启动测试')
    parser.add_argument('--case',choices=['hydraulic','cold-store'],default='hydraulic',help='hydraulic：并联水力 + Python 阀；cold-store：冷库 A 案例')
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.hours<=0:parser.error('--hours 必须为正数')
    if args.status:
        print(json.dumps(status(args.output.resolve()),ensure_ascii=False,indent=2))
    else:
        run(args.hours,args.output.resolve(),args.case)
