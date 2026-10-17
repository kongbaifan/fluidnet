"""把 REFPROP 9.1 运行时最小集复制到项目 vendor/refprop9.1/ 并生成可校验清单。

默认只复制 REFPRP64.DLL、fluids/、mixtures/（来源存在时再加上 defaults.prf、FLUIDSET.LST），
不复制 REFPROP.EXE、32 位 DLL、ocx、示例与文档。NIST REFPROP 是按用户许可软件：DLL 与工质
文件不提交 git，只在持有合法 NIST 许可时使用或随包分发。

用法：
  python scripts/bundle_refprop.py                     # 源取 FLUIDNET_REFPROP_PATH 或 Windows 默认安装
  python scripts/bundle_refprop.py --force             # 目标已存在时覆盖重建
  python scripts/bundle_refprop.py --check             # 校验清单、逐文件 SHA-256、最小集并真实加载
  python scripts/bundle_refprop.py --check --json      # 机器可读摘要
退出码：0 成功或校验通过；1 来源不完整、目标内容冲突或校验失败。
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(os.environ.get('FLUIDNET_REFPROP_PATH') or r'C:\Program Files (x86)\REFPROP')
DEFAULT_TARGET = ROOT / 'vendor' / 'refprop9.1'
LIBRARY = 'REFPRP64.DLL'
MANIFEST_NAME = 'refprop-manifest.json'
BUNDLE_FORMAT = 'fluidnet-refprop-bundle'
BUNDLE_VERSION = '9.1'
LICENSE_NOTE = 'NIST REFPROP 按用户许可；仅在持有合法 NIST 许可时使用或随包分发'
# 运行时最小集：64 位 DLL + 纯质工质目录 + 混合物目录；顺序同时也是清单里的目录顺序。
REQUIRED_DIRS = ('fluids', 'mixtures')
# REFPROP 安装目录里的可选文件：体积可忽略，复制过去可提高兼容性。
OPTIONAL_FILES = ('defaults.prf', 'FLUIDSET.LST')

# 真实加载探测必须放在子进程：REFPROP 9.1 的 DLL 读到其他版本的工质文件会让 Fortran 直接终止进程。
_PROBE = r"""
import sys
import CoolProp.CoolProp as CP
root = sys.argv[1]
CP.set_config_string(CP.ALTERNATIVE_REFPROP_PATH, root)
CP.set_config_string(CP.ALTERNATIVE_REFPROP_LIBRARY_PATH, root + 'REFPRP64.DLL')
version = CP.get_global_param_string('REFPROP_version')
state = CP.AbstractState('REFPROP', 'WATER')
state.update(CP.PT_INPUTS, 101325., 293.15)
print('VERSION=' + version)
print('DENSITY=%.12g' % state.rhomass())
"""


class BundleError(Exception):
    """捆绑生成或校验失败；main() 统一转换为退出码 1。"""


def sha256_file(path):
    """返回文件的 SHA-256 十六进制摘要（分块读取，避免大文件占内存）。"""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def find_entry(directory, name, want_dir):
    """在 directory 下按大小写不敏感查找文件或目录。

    REFPROP 安装里大小写不统一（files/FLUIDS、refprop9.1/NISTRefprop9.1），Linux 上的测试
    来源则是小写；这里同时兼容两种情况，找到后返回实际路径，没有则返回 None。
    """
    directory = Path(directory)
    direct = directory / name
    if (direct.is_dir() if want_dir else direct.is_file()):
        return direct
    try:
        children = list(directory.iterdir())
    except OSError:
        return None
    for child in children:
        if child.name.lower() != name.lower():
            continue
        if (child.is_dir() if want_dir else child.is_file()):
            return child
    return None


def collect_files(source):
    """收集运行时最小集，返回 {清单相对路径(posix): 来源文件}。

    来源必须含 REFPRP64.DLL 以及 fluids/、mixtures/ 两个目录；目录内的子目录结构原样保留。
    来源缺任一必需项时抛 BundleError 并指明缺什么。
    """
    source = Path(source)
    if not source.is_dir():
        raise BundleError(f'来源 REFPROP 目录不存在：{source}')
    missing = []
    library = find_entry(source, LIBRARY, False)
    if library is None:
        missing.append(LIBRARY + '（64 位 DLL）')
    directories = {}
    for name in REQUIRED_DIRS:
        found = find_entry(source, name, True)
        if found is None:
            missing.append(name + '/')
        else:
            directories[name] = found
    if missing:
        raise BundleError(f'来源不是可用的 REFPROP {BUNDLE_VERSION} 目录（{source}），缺少：' + '、'.join(missing))
    files = {LIBRARY: library}
    for name, found in directories.items():
        entries = sorted(path for path in found.rglob('*') if path.is_file())
        if not entries:
            raise BundleError(f'来源的 {name}/ 目录为空，不是完整的 REFPROP 安装：{found}')
        for path in entries:
            files[(Path(name) / path.relative_to(found)).as_posix()] = path
    for name in OPTIONAL_FILES:
        found = find_entry(source, name, False)
        if found is not None:
            files[name] = found
    return files


def build_manifest(source, files):
    """按清单契约构造 refprop-manifest.json 的内容（含每个文件的 sha256 与字节数）。"""
    entries = {relative: {'sha256': sha256_file(path), 'size': path.stat().st_size}
               for relative, path in sorted(files.items())}
    return {'format': BUNDLE_FORMAT, 'version': BUNDLE_VERSION, 'library': LIBRARY,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'source': str(Path(source).resolve()), 'license': LICENSE_NOTE, 'files': entries}


def relative_parts(relative):
    """把清单里的 posix 相对路径拆成安全分段；绝对路径、反斜杠或 .. 一律视为非法。"""
    if not isinstance(relative, str) or not relative or '\\' in relative or ':' in relative:
        return None
    if relative.startswith('/'):
        return None
    parts = relative.split('/')
    if any(part in ('', '.', '..') for part in parts):
        return None
    return parts


def load_manifest(target):
    """读取目标的清单；文件缺失或 JSON 损坏时返回 None。"""
    path = Path(target) / MANIFEST_NAME
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def manifest_problems(target, manifest):
    """校验清单元数据与逐文件 sha256/size，返回问题列表；空列表表示通过。"""
    target = Path(target)
    if manifest is None:
        return [f'缺少或无法解析清单文件：{MANIFEST_NAME}']
    problems = []
    if manifest.get('format') != BUNDLE_FORMAT:
        problems.append(f'清单 format 应为 {BUNDLE_FORMAT!r}，实际 {manifest.get("format")!r}')
    if manifest.get('version') != BUNDLE_VERSION:
        problems.append(f'清单 version 应为 {BUNDLE_VERSION!r}，实际 {manifest.get("version")!r}')
    if manifest.get('library') != LIBRARY:
        problems.append(f'清单 library 应为 {LIBRARY!r}，实际 {manifest.get("library")!r}')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        return problems + ['清单 files 为空或不是对象']
    if LIBRARY not in files:
        problems.append(f'清单 files 未包含运行时库 {LIBRARY}')
    expected = set()
    for relative in sorted(files):
        spec = files[relative]
        parts = relative_parts(relative)
        if parts is None:
            problems.append(f'清单里有非法相对路径：{relative!r}')
            continue
        path = target / Path(*parts)
        expected.add(Path(*parts))
        if not isinstance(spec, dict):
            problems.append(f'清单条目格式错误：{relative}')
            continue
        size, digest = spec.get('size'), spec.get('sha256')
        if not isinstance(size, int) or size < 0 or not isinstance(digest, str) or len(digest) != 64:
            problems.append(f'清单条目缺少有效的 size/sha256：{relative}')
            continue
        if not path.is_file():
            problems.append(f'缺少文件：{relative}')
            continue
        actual = path.stat().st_size
        if actual != size:
            problems.append(f'大小不一致：{relative}（清单 {size}，实际 {actual}）')
        elif sha256_file(path) != digest:
            problems.append(f'sha256 不一致：{relative}')
    actual_files = {path.relative_to(target) for path in target.rglob('*') if path.is_file()}
    for relative in sorted(actual_files - expected - {Path(MANIFEST_NAME)}):
        problems.append(f'清单未列出的多余文件：{relative.as_posix()}')
    return problems


def structure_problems(target):
    """校验运行时最小集在目标目录里实际存在：REFPRP64.DLL + fluids/ + mixtures/。"""
    problems = []
    if find_entry(target, LIBRARY, False) is None:
        problems.append(f'捆绑目录缺少 {LIBRARY}')
    for name in REQUIRED_DIRS:
        if find_entry(target, name, True) is None:
            problems.append(f'捆绑目录缺少 {name}/ 目录')
    return problems


def probe_bundle(target, timeout=120):
    """用子进程真实加载捆绑目录里的 REFPROP：读版本并对 REFPROP::WATER 做一次 PT flash。

    成功返回 REFPROP_version 字符串；失败时把子进程 stderr 尾部原样打印到 stderr 并抛 BundleError。
    """
    target = Path(target)
    if find_entry(target, LIBRARY, False) is None:
        raise BundleError(f'捆绑目录缺少 {LIBRARY}，无法做加载探测：{target}')
    root = str(target) + os.sep
    try:
        done = subprocess.run([sys.executable, '-c', _PROBE, root], capture_output=True, text=True,
                              timeout=timeout, env=os.environ.copy())
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BundleError(f'REFPROP 加载探测无法完成：{error}') from error
    if done.returncode != 0:
        tail = '\n'.join((done.stderr or done.stdout).strip().splitlines()[-20:])
        if tail:
            print(tail, file=sys.stderr)
        raise BundleError(f'REFPROP 加载探测失败（子进程退出码 {done.returncode}）：{target}')
    version, density = None, None
    for line in done.stdout.splitlines():
        if line.startswith('VERSION='):
            version = line[len('VERSION='):].strip()
        elif line.startswith('DENSITY='):
            try:
                density = float(line[len('DENSITY='):])
            except ValueError:
                raise BundleError(f'REFPROP 加载探测返回的密度无法解析：{line}')
    if not version:
        raise BundleError('REFPROP 加载探测没有返回 REFPROP_version')
    if not version.startswith(BUNDLE_VERSION):
        raise BundleError(f'探测到的 REFPROP 版本是 {version}，不是要求的 {BUNDLE_VERSION}')
    if density is None or not density > 0:
        raise BundleError(f'REFPROP::WATER PT flash 没有返回有效密度：{density!r}')
    return version


def bundle_info(target, manifest):
    """从清单汇总版本、文件数、总字节、清单 SHA-256 和哈希样例行；清单不可用时给出空字段。"""
    target = Path(target)
    info = {'version': None, 'files': 0, 'bytes': 0,
            'manifest': str(target / MANIFEST_NAME), 'manifest_sha256': None, 'entries': {}}
    manifest_path = target / MANIFEST_NAME
    if manifest_path.is_file():
        info['manifest_sha256'] = sha256_file(manifest_path)
    files = manifest.get('files') if isinstance(manifest, dict) else None
    if not isinstance(files, dict) or not files:
        return info
    info['version'] = manifest.get('version')
    info['files'] = len(files)
    info['bytes'] = sum(spec['size'] for spec in files.values()
                        if isinstance(spec, dict) and isinstance(spec.get('size'), int))
    info['entries'] = {relative: files[relative]['sha256'] for relative in sorted(files)[:3]
                       if isinstance(files[relative], dict) and isinstance(files[relative].get('sha256'), str)}
    return info


def build_bundle(source, target, force=False, skip_verify=False):
    """复制最小运行时集、写清单并按需加载探测；返回摘要 dict。"""
    source, target = Path(source).resolve(), Path(target).resolve()
    files = collect_files(source)
    manifest = build_manifest(source, files)
    reused = False
    if target.exists() and not target.is_dir():
        if not force:
            raise BundleError(f'目标路径已存在且不是目录：{target}（用 --force 覆盖）')
        target.unlink()
    if target.is_dir() and any(target.iterdir()) and not force:
        existing = load_manifest(target)
        problems = manifest_problems(target, existing)
        if problems:
            raise BundleError(f'目标目录已存在且不是有效捆绑（{problems[0]}）：{target}；用 --force 覆盖')
        if manifest['files'] != existing['files']:
            changed = [relative for relative in sorted(set(manifest['files']) | set(existing['files']))
                       if manifest['files'].get(relative) != existing['files'].get(relative)]
            raise BundleError(f'目标目录已存在且内容不同（{len(changed)} 个文件差异，如 {changed[:3]}）：{target}；用 --force 覆盖')
        manifest, reused = existing, True
    if not reused:
        if target.is_dir() and any(target.iterdir()):
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        for relative, path in sorted(files.items()):
            destination = target / Path(*relative.split('/'))
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        (target / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    result = {'ok': True, 'action': 'bundle', 'target': str(target), 'source': str(source), 'reused': reused,
              **bundle_info(target, manifest)}
    if not skip_verify:
        result['detected_version'] = probe_bundle(target)
    return result


def check_bundle(target, skip_verify=False):
    """校验已有捆绑目录：清单、逐文件 sha256/size、最小集与真实加载；返回摘要 dict。"""
    target = Path(target).resolve()
    if not target.is_dir():
        return {'ok': False, 'action': 'check', 'target': str(target), 'problems': [f'目标目录不存在：{target}']}
    manifest = load_manifest(target)
    problems = manifest_problems(target, manifest) + structure_problems(target)
    result = {'ok': False, 'action': 'check', 'target': str(target), **bundle_info(target, manifest)}
    if not problems and not skip_verify:
        try:
            result['detected_version'] = probe_bundle(target)
        except BundleError as error:
            problems.append(str(error))
    result['problems'] = problems
    result['ok'] = not problems
    return result


def report(result, as_json=False):
    """打印人读摘要或机器可读 JSON；失败时把每个问题逐行写到 stderr。"""
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
        return
    if not result.get('ok'):
        for problem in result.get('problems') or ([result['error']] if result.get('error') else ['未知错误']):
            print('错误：' + problem, file=sys.stderr)
        return
    if result.get('action') == 'bundle':
        tail = '已存在且内容一致（跳过复制）' if result.get('reused') else '完成'
        print(f"REFPROP {result['version']} 捆绑{tail}：{result['target']}")
        print(f"  来源：{result['source']}")
    else:
        print(f"捆绑目录校验通过：{result['target']}")
    print(f"  版本：{result['version']}；文件：{result['files']:,} 个；总字节：{result['bytes']:,}")
    print(f"  清单：{result['manifest']} sha256={result['manifest_sha256']}")
    entries = result.get('entries') or {}
    if entries:
        listed = '；'.join(f'{name}={digest}' for name, digest in entries.items())
        print(f'  清单 sha256 前 {len(entries)} 项：{listed}（共 {result["files"]} 项）')
    if result.get('detected_version'):
        print(f"  探测：REFPROP {result['detected_version']} 加载通过，REFPROP::WATER PT flash 正常")


def main(argv=None):
    parser = argparse.ArgumentParser(description='把 REFPROP 9.1 运行时最小集复制到捆绑目录并生成/校验清单。')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE,
                        help=f'来源 REFPROP 目录（默认 FLUIDNET_REFPROP_PATH 或 {DEFAULT_SOURCE}）')
    parser.add_argument('--target', type=Path, default=DEFAULT_TARGET,
                        help=f'捆绑目标目录（默认 {DEFAULT_TARGET.relative_to(ROOT).as_posix()}）')
    parser.add_argument('--force', action='store_true', help='目标已存在时覆盖重建（会先删除目标目录）')
    parser.add_argument('--check', action='store_true', help='不复制，只校验目标目录的清单、逐文件 sha256/size、最小集与真实加载')
    parser.add_argument('--skip-verify', action='store_true', help='跳过 CoolProp 真实加载探测（供无 REFPROP 的机器做结构测试）')
    parser.add_argument('--json', action='store_true', help='输出机器可读 JSON 摘要')
    args = parser.parse_args(argv)
    try:
        result = check_bundle(args.target, args.skip_verify) if args.check else \
            build_bundle(args.source, args.target, args.force, args.skip_verify)
    except BundleError as error:
        result = {'ok': False, 'error': str(error)}
    report(result, args.json)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    sys.exit(main())
