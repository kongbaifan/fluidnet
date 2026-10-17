"""Bundle source and validated examples; this is not the offline Windows installer.

默认只打包 git 跟踪/未忽略的源码与 trial-acceptance/；传 `--refprop DIR` 时再显式加入一份已校验的
REFPROP 9.1 捆绑目录（vendor/ 被 .gitignore 忽略，不能靠 git ls-files 收集）。
NIST REFPROP 是按用户许可软件，带 REFPROP 的候选包只能在接收方持有合法许可时交付。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
# 候选包内 REFPROP 捆绑目录的固定落点：运行时按“项目根/vendor/refprop9.1”发现捆绑。
REFPROP_BUNDLE_NAME='refprop9.1'
REFPROP_MANIFEST='refprop-manifest.json'


def refprop_summary(directory):
    """读取捆绑清单元数据并汇总，返回写入 candidate.json 的 refprop 字段。"""
    directory=Path(directory)
    manifest_path=directory/REFPROP_MANIFEST
    if not manifest_path.is_file():raise ValueError(f'REFPROP 捆绑目录缺少 {REFPROP_MANIFEST}：{directory}')
    raw=manifest_path.read_bytes()
    try:manifest=json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError,json.JSONDecodeError) as error:raise ValueError(f'REFPROP 捆绑清单无法解析：{error}') from error
    files=manifest.get('files')
    version=manifest.get('version')
    if manifest.get('format')!='fluidnet-refprop-bundle' or not isinstance(files,dict) or not files or not isinstance(version,str) or not version:
        raise ValueError(f'REFPROP 捆绑清单格式不符：{manifest_path}')
    zip_prefix=f'{ROOT.name}/vendor/{REFPROP_BUNDLE_NAME}/'
    return {'version':version,'files':len(files),
        'bytes':sum(spec['size'] for spec in files.values() if isinstance(spec,dict) and isinstance(spec.get('size'),int)),
        'manifest':zip_prefix+REFPROP_MANIFEST,'manifest_sha256':hashlib.sha256(raw).hexdigest()}


def main(acceptance, output, refprop=None):
    report=json.loads((acceptance/'report.json').read_text(encoding='utf-8'))
    if report['status']!='passed':raise ValueError('样例验收未通过，不能生成候选包')
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--',ROOT.name],cwd=ROOT.parent).decode('utf-8').split('\0')
    paths={name:ROOT.parent/name for name in names if name}
    paths.update({'trial-acceptance/'+p.relative_to(acceptance).as_posix():p for p in acceptance.rglob('*') if p.is_file()})
    refprop_info=None
    if refprop is not None:
        refprop=Path(refprop).resolve()
        if not refprop.is_dir():raise ValueError(f'REFPROP 捆绑目录不存在：{refprop}')
        refprop_info=refprop_summary(refprop)
        # vendor/ 被忽略，git ls-files 收不到；这里显式按固定落点加入候选包。
        prefix=f'{ROOT.name}/vendor/{REFPROP_BUNDLE_NAME}/'
        for path in sorted(refprop.rglob('*')):
            if path.is_file():paths[prefix+path.relative_to(refprop).as_posix()]=path
    manifest={'format':'fluidnet-source-candidate','created_at':datetime.now(timezone.utc).isoformat(),
        'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'scope':'源码、测试与样例验收结果；未捆绑 Python/Node 或依赖，不是离线便携发行包。'}
    if refprop_info is not None:manifest['refprop']=refprop_info
    manifest['files']={name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size} for name,p in sorted(paths.items())}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,path in sorted(paths.items()):archive.write(path,name)
        archive.writestr('candidate.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        readme='FluidNet 源码候选包\n\n需要 Python 3.11+。进入 fluidnet-prototype-engine，安装 requirements.txt 后运行 python -m fn_engine serve。\n建模流程、验收结果与剩余问题见 docs/MODELING_TRIAL_VALIDATION.md；样例输入、请求与输出见 trial-acceptance/。\n本包未包含离线运行时，尚未通过干净机器发行验收。\n'
        if refprop_info is not None:
            readme+=f"\n本包内含 REFPROP {refprop_info['version']} 运行时文件，仅在持有 NIST 许可时使用。\n"
        archive.writestr('README.txt',readme)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n',encoding='utf-8')
    with zipfile.ZipFile(output) as archive:
        if archive.testzip():raise ValueError('候选包 ZIP 完整性检查失败')
        for name,spec in manifest['files'].items():
            data=archive.read(name)
            if len(data)!=spec['size'] or hashlib.sha256(data).hexdigest()!=spec['sha256']:raise ValueError('候选包文件校验失败：'+name)
    summary={'file':str(output),'files':len(paths),'bytes':output.stat().st_size,'sha256':digest}
    if refprop_info is not None:summary['refprop']=refprop_info
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--acceptance',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--refprop',type=Path,default=None,help='把该 REFPROP 捆绑目录整体加入候选包（如 vendor/refprop9.1，需已通过 --check）')
    args=parser.parse_args();main(args.acceptance.resolve(),args.output.resolve(),args.refprop.resolve() if args.refprop else None)
