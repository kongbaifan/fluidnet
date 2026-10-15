"""Bundle source and validated examples; this is not the offline Windows installer."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def main(acceptance, output):
    report=json.loads((acceptance/'report.json').read_text(encoding='utf-8'))
    if report['status']!='passed':raise ValueError('样例验收未通过，不能生成候选包')
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--',ROOT.name],cwd=ROOT.parent).decode('utf-8').split('\0')
    paths={name:ROOT.parent/name for name in names if name}
    paths.update({'trial-acceptance/'+p.relative_to(acceptance).as_posix():p for p in acceptance.rglob('*') if p.is_file()})
    manifest={'format':'fluidnet-source-candidate','created_at':datetime.now(timezone.utc).isoformat(),
        'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'scope':'源码、测试与样例验收结果；未捆绑 Python/Node 或依赖，不是离线便携发行包。',
        'files':{name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for name,p in sorted(paths.items())}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,path in sorted(paths.items()):archive.write(path,name)
        archive.writestr('candidate.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        archive.writestr('README.txt','FluidNet 源码候选包\n\n需要 Python 3.11+。进入 fluidnet-prototype-engine，安装 requirements.txt 后运行 python -m fn_engine serve。\n建模流程、验收结果与剩余问题见 docs/MODELING_TRIAL_VALIDATION.md；样例输入、请求与输出见 trial-acceptance/。\n本包未包含离线运行时，尚未通过干净机器发行验收。\n')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n',encoding='utf-8')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise ValueError('候选包 ZIP 完整性检查失败')
        for name,spec in manifest['files'].items():
            data=archive.read(name)
            if len(data)!=spec['size'] or hashlib.sha256(data).hexdigest()!=spec['sha256']:raise ValueError('候选包文件校验失败：'+name)
    print(json.dumps({'file':str(output),'files':len(paths),'bytes':output.stat().st_size,'sha256':digest},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--acceptance',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();main(args.acceptance.resolve(),args.output.resolve())
