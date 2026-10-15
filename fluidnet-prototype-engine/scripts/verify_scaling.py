"""100/500/1000-instance sparse series, branched, and Python-module benchmarks."""
import json
from pathlib import Path
import platform

from benchmark_scaling import make_network, measure
from acceptance_cases import assemble


def branched(size):
    nodes=[('B1','source',{'pressure_pa':250000}),('J0','junction',{}),('J1','junction',{}),('B2','source',{'pressure_pa':120000})]
    edges=[('B1:out0','J0:in0'),('J1:in0','B2:out0')]
    count=size-4
    for branch,number in enumerate([count//2,count-count//2]):
        port='out'+str(branch);previous='J0:'+port
        for i in range(number):
            name=f'L{branch}_{i}';nodes.append((name,'pipe',{'length_m':1}))
            edges.append((previous,name+':in0'));previous=name+':out0'
        edges.append((previous,'J1:'+port))
    return assemble('scale-branches',nodes,edges)


if __name__=='__main__':
    report={'platform':platform.platform(),'cpu':platform.processor(),'native_threads':1,'repeats':1,'cases':[]}
    path=Path('artifacts/scaling-acceptance.json');path.parent.mkdir(exist_ok=True)
    for size in [100,500,1000]:
        for family in ['series','branches','python-25-percent']:
            model=branched(size) if family=='branches' else make_network(size,.25 if family.startswith('python') else 0)
            model.solver.hydraulic_method='sparse'
            result=measure(model)
            assert result['mass_residual_kg_s']<1e-6 and result['pressure_residual_pa']<1
            entry={'family':family,'instances':size,'status':'passed',**result}
            report['cases'].append(entry);path.write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(entry),flush=True)
