"""由可执行模型生成 contracts/ 下的 JSON Schema、OpenAPI 与参考文件。

默认运行（无参数）：重写 contracts/ 下全部生成物，行为与之前一致。
`--check`：只在内存中生成，再与现盘文件做 JSON 语义比较，不写文件；
一致时打印 `contracts up to date: N files` 并退出 0，不一致时打印差异文件与简要 diff 并退出 1。
"""
import argparse
import json
import sys
from pathlib import Path

from fn_engine.api import create_app
from fn_engine.bridge import normalize_prototype_export
from fn_engine.models import (
    CommitStepRequest, CommitStepResponse, EvaluateRequest, EvaluateResponse,
    FluidConfig, ModuleDefinition, ModulePackageRef, ModuleTestRequest,
    ModuleTestResponse, NetworkRelation, PortState, Project, RunCreateResponse,
    RunEventsResponse, RunFrame, RunHistoryResponse, RunRequest, RunStatus,
    ErrorResponse, ValidationResponse,
    ModuleSaveRequest, ModuleVersionResponse, ModuleVersionsResponse,
    ModuleDesignRequest, ModuleDesignResponse,
    ProjectDocument, ProjectSaveRequest, ProjectRevisionRequest, ProjectDeleteRequest, ProjectUpgradeRequest,
)
from fn_engine.compiler import compile_project
from fn_engine.solver import solve_steady

root=Path(__file__).resolve().parents[1]
output=root/'contracts'

# 合同文件清单的唯一来源：schema 名与生成顺序都由这里给出，测试直接导入 models，避免名单漂移。
models = [
    ('module', ModuleDefinition), ('project', Project), ('run-request', RunRequest), ('run-frame', RunFrame),
    ('fluid-config', FluidConfig), ('module-package-ref', ModulePackageRef),
    ('port-state', PortState), ('network-relation', NetworkRelation),
    ('evaluate-request', EvaluateRequest), ('evaluate-response', EvaluateResponse),
    ('commit-step-request', CommitStepRequest), ('commit-step-response', CommitStepResponse),
    ('module-test-request', ModuleTestRequest), ('module-test-response', ModuleTestResponse),
    ('module-save-request', ModuleSaveRequest), ('module-version-response', ModuleVersionResponse),
    ('module-versions-response', ModuleVersionsResponse),
    ('module-design-request', ModuleDesignRequest), ('module-design-response', ModuleDesignResponse),
    ('project-document', ProjectDocument), ('project-save-request', ProjectSaveRequest),
    ('project-revision-request', ProjectRevisionRequest), ('project-delete-request', ProjectDeleteRequest),
    ('project-upgrade-request', ProjectUpgradeRequest),
    ('run-status', RunStatus), ('run-create-response', RunCreateResponse),
    ('run-history-response', RunHistoryResponse), ('run-events-response', RunEventsResponse),
    ('error-response', ErrorResponse), ('validation-response', ValidationResponse),
]

# 涉及数值求解的参考结果允许极小的浮点相对误差，避免不同机器/线程求和顺序导致门禁抖动。
rel_tolerances={'reference-result.json':1e-9}


def contract_files():
    """在内存中生成全部合同文件，返回 {文件名: JSON 可序列化数据}，不触碰磁盘。"""
    files={}
    for name,model in models:
        schema=model.model_json_schema()
        schema['$schema']='https://json-schema.org/draft/2020-12/schema'
        files[name+'.schema.json']=schema
    files['openapi.json']=create_app().openapi()
    raw=json.loads((root/'tests'/'fixtures'/'prototype.json').read_text(encoding='utf-8'))
    project=normalize_prototype_export(raw)
    files['reference-project.json']=project.model_dump(mode='json')
    files['reference-result.json']=solve_steady(compile_project(project)).model_dump(mode='json')
    return files


def write(files):
    """把生成结果按统一格式写回 contracts/。"""
    for name,data in files.items():
        (output/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def diff_contract(expected,actual,path='$',issues=None,limit=20,rel_tolerance=0.):
    """语义比较两个 JSON 值并返回差异说明列表；键集双向比较，数字容忍 int/float 与给定相对误差。"""
    issues=[] if issues is None else issues
    if len(issues)>=limit:return issues
    if isinstance(expected,dict) and isinstance(actual,dict):
        for key in sorted(expected.keys()|actual.keys(),key=str):
            if key not in actual:issues.append(f'{path}.{key}: 仅源码生成结果中存在')
            elif key not in expected:issues.append(f'{path}.{key}: 仅契约文件中存在')
            else:diff_contract(expected[key],actual[key],f'{path}.{key}',issues,limit,rel_tolerance)
    elif isinstance(expected,list) and isinstance(actual,list):
        if len(expected)!=len(actual):issues.append(f'{path}: 长度 {len(expected)} != {len(actual)}')
        else:
            for index,(left,right) in enumerate(zip(expected,actual)):
                diff_contract(left,right,f'{path}[{index}]',issues,limit,rel_tolerance)
    elif isinstance(expected,bool) or isinstance(actual,bool):
        if expected is not actual:issues.append(f'{path}: {expected!r} != {actual!r}')
    elif isinstance(expected,(int,float)) and isinstance(actual,(int,float)):
        if not _numbers_equal(expected,actual,rel_tolerance):issues.append(f'{path}: {expected!r} != {actual!r}')
    elif type(expected) is not type(actual) or expected!=actual:
        issues.append(f'{path}: {expected!r} != {actual!r}')
    return issues


def _numbers_equal(left,right,rel_tolerance=0.):
    if left==right:return True
    return abs(left-right)<=rel_tolerance*max(abs(left),abs(right))


def check(files=None):
    """比较源码生成结果与 contracts/ 现盘文件，返回退出码（0 一致，1 漂移）。"""
    files=contract_files() if files is None else files
    problems={}
    for name,expected in files.items():
        path=output/name
        if not path.is_file():
            problems[name]=['契约文件缺失']
            continue
        try:saved=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,json.JSONDecodeError) as error:
            problems[name]=[f'无法解析 JSON：{error}']
            continue
        issues=diff_contract(expected,saved,rel_tolerance=rel_tolerances.get(name,0.))
        if issues:problems[name]=issues
    if output.is_dir():
        for path in sorted(output.glob('*.json')):
            if path.name not in files:problems[path.name]=['不在生成清单中（多余的契约文件）']
    if not problems:
        print(f'contracts up to date: {len(files)} files')
        return 0
    print(f'contracts out of date: {len(problems)} 个文件与源码生成结果不一致')
    for name in sorted(problems):
        print(f'  {name}')
        for issue in problems[name][:5]:print(f'    {issue}')
        if len(problems[name])>5:print(f'    ... 另有 {len(problems[name])-5} 处差异')
    print('请运行 `python scripts/generate_contracts.py` 重新生成 contracts/。')
    return 1


def main(argv=None):
    parser=argparse.ArgumentParser(description='Generate or verify contracts/ from the executable models.')
    parser.add_argument('--check',action='store_true',help='只校验生成物与源码是否一致，不写文件（一致退出 0，不一致退出 1）')
    args=parser.parse_args(argv)
    files=contract_files()
    if args.check:return check(files)
    write(files)
    print('Generated schemas, OpenAPI, reference project and result.')
    return 0


if __name__=='__main__':
    sys.exit(main())
