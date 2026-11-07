"""Read executable frozen definitions into an inventory; no solves or Worker execution."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from fn_engine.catalog import builtin_catalog  # noqa: E402
from fn_engine.packages import load_module_package  # noqa: E402


def inventory():
    definitions=builtin_catalog()
    for path in sorted((ROOT/'modules').rglob('manifest.json')):
        definitions.append(load_module_package(path.parent))
    definitions=list({(m.id,m.version,m.runtime):m for m in definitions}.values())
    return [{'id':m.id,'version':m.version,'name':m.name,'runtime':m.runtime,'solver_model':m.solver_model,
        'port_domains':sorted({p.domain.value for p in m.ports}),
        'ports':[{'id':p.id,'required':p.required,'circuit':p.circuit} for p in m.ports],
        'scope':m.applicability.model_dump(mode='json') if m.applicability else None,
        'design':bool(m.source.get('design')),'composite':m.composite is not None,
        'description':m.description,
        'evidence_note':'目录和合同事实；未单独声明工况/执行域不等于任意域已验证'}
        for m in sorted(definitions,key=lambda m:(m.id,m.version))]


if __name__=='__main__':
    target=ROOT/'docs/capability-inventory.json'
    target.write_text(json.dumps(inventory(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Capability contracts: {len(inventory())}')
