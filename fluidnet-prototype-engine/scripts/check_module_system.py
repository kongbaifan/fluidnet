"""Record complete module-system gates without overwriting historical evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--frontend',action='store_true')
    args=parser.parse_args();target=Path(args.output).resolve()
    if not target.is_relative_to((ROOT/'artifacts/module-system').resolve()) or target.exists():
        raise ValueError('验收必须写入新的 artifacts/module-system 目录')
    target.mkdir(parents=True)
    env=os.environ.copy();env['PYTHONUTF8']='1';env['PYTHONPATH']=str(ROOT/'backend')
    for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):env[key]='1'
    commands=[('pytest',[sys.executable,'-m','pytest','-q','--basetemp',str(target/'temp'),'--cov=fn_engine','--cov=fn_sdk',
        '--cov-report=term-missing','--cov-report=xml:'+str(target/'coverage.xml')],False),
        ('ruff',[sys.executable,'-m','ruff','check','backend','tests','scripts','modules','examples'],False),
        ('sdk-mypy',[sys.executable,'-m','mypy','--config-file','mypy-sdk.ini'],False),
        ('backend-mypy',[sys.executable,'-m','mypy'],False),
        ('contracts',[sys.executable,'scripts/generate_contracts.py','--check'],False)]
    if args.frontend:
        commands += [('frontend-check',['cmd','/c','npm','run','check'],False),('browser',['cmd','/c','npm','run','test:browser'],False)]
    results=[]
    for name,command,advisory in commands:
        print(json.dumps({'gate':name,'status':'running'}),flush=True);start=time.perf_counter()
        with (target/f'{name}.txt').open('w',encoding='utf-8') as output:
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
        results.append({'name':name,'command':command,'exit_code':result.returncode,'advisory':advisory,'elapsed_s':time.perf_counter()-start})
        (target/'report.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps(results[-1]),flush=True)
    raise SystemExit(int(any(row['exit_code'] and not row['advisory'] for row in results)))


if __name__=='__main__':main()
