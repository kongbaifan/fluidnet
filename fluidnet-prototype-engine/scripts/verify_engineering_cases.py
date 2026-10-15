"""Run source-related engineering checks and export inspectable input/output files."""
import json
from pathlib import Path
import platform
import time

from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady, solve_dynamic
from acceptance_cases import parallel, tanks


def main():
    directory=Path('artifacts/engineering-acceptance');directory.mkdir(parents=True,exist_ok=True)
    report={'platform':platform.platform(),'parameter_basis':'Declared engineering assumptions; public Baselu screenshots lack full parameters.',
        'sources':['https://www.baselu.cn/article?id=moqzplol4gps','https://www.baselu.cn/article?id=moqzvavjph6k'],
        'cases':[]}
    previous=None
    for name,model in [('parallel-open',parallel(.8)),('parallel-throttled',parallel(.1)),('parallel-closed',parallel(0)),
                       ('parallel-tanks-charge',tanks(True)),('parallel-tanks-drain',tanks(False))]:
        begin=time.perf_counter()
        frames=solve_dynamic(compile_project(model),30.,.5) if 'tanks' in name else [solve_steady(compile_project(model))]
        for frame in frames:
            assert frame.valid and frame.metrics['mass_residual_kg_s']<1e-6
        first,last=frames[0].variables,frames[-1].variables
        checks={}
        if 'tanks' not in name:
            checks['branch_mass_error']=abs(last['P1.mass_flow_kg_s']-last['L1.mass_flow_kg_s']-last['L2.mass_flow_kg_s'])
            assert checks['branch_mass_error']<1e-6
            flow=last['L2.mass_flow_kg_s']
            if previous is not None:assert flow<previous
            previous=flow;checks['controlled_branch_flow']=flow
            if name.endswith('closed'):assert abs(flow)<1e-10
        else:
            change=sum(last[f'T{i}.state.mass_kg']-first[f'T{i}.state.mass_kg'] for i in range(1,4))
            accumulated=sum(.5*sum(f.variables[f'T{i}.state.net_inflow_kg_s'] for i in range(1,4)) for f in frames[1:])
            checks['mass_ledger_error_kg']=abs(change-accumulated)
            assert abs(change-accumulated)<1e-5
            assert change>0 if name.endswith('charge') else change<0
            assert max(last[f'T{i}.state.level_m'] for i in range(1,4))-min(last[f'T{i}.state.level_m'] for i in range(1,4))<1e-8
        entry={'name':name,'status':'passed','frames':len(frames),'elapsed_s':time.perf_counter()-begin,'checks':checks,
               'metrics':frames[-1].metrics}
        (directory/(name+'-project.json')).write_text(model.model_dump_json(indent=2),encoding='utf-8')
        (directory/(name+'-frames.json')).write_text(json.dumps([f.model_dump(mode='json') for f in frames]),encoding='utf-8')
        report['cases'].append(entry);print(json.dumps(entry),flush=True)
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
