"""Read-only generation checks and bounded semantic review of retained portable artifacts."""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'scripts/generated-artifacts.json'


def load_manifest(root: Path = ROOT) -> list[dict[str, Any]]:
    document = json.loads((root / 'scripts/generated-artifacts.json').read_text(encoding='utf-8'))
    if document.get('version') != 1:
        raise ValueError('Unsupported generated artifact manifest version')
    entries = document['generators']
    seen: set[str] = set()
    scripts: set[str] = set()
    for entry in entries:
        if entry['id'] in seen or entry['script'] in scripts:
            raise ValueError('Duplicate generator: ' + entry['id'])
        seen.add(entry['id'])
        scripts.add(entry['script'])
        for path in [entry['script'], *entry['outputs']]:
            if PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or '\\' in path or ':' in path:
                raise ValueError('Expected project-relative path: ' + path)
        source = root / entry['script']
        if not source.is_file() or '--check' not in source.read_text(encoding='utf-8'):
            raise ValueError('Missing read-only generator: ' + entry['script'])
        if not entry['outputs'] or any(not list(root.glob(pattern)) for pattern in entry['outputs']):
            raise ValueError('Output pattern has no files: ' + entry['id'])
    discovered = {path.relative_to(root).as_posix() for path in (root / 'scripts').glob('generate_*.py')
                  if '--check' in path.read_text(encoding='utf-8')}
    if discovered != scripts:
        raise ValueError('Generator registration drift: ' + repr(sorted(discovered ^ scripts)))
    return entries


def semantic_changes(before: Any, after: Any, limit: int = 20) -> dict[str, Any]:
    """Count all JSON changes; report only bounded JSON-pointer paths, never embedded source."""
    count = 0
    samples: list[dict[str, str]] = []

    def note(path: str, kind: str) -> None:
        nonlocal count
        count += 1
        if len(samples) < limit:
            samples.append({'path': path or '/', 'kind': kind})

    def visit(left: Any, right: Any, path: str = '') -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(left.keys() | right.keys()):
                child = path + '/' + key.replace('~', '~0').replace('/', '~1')
                if key not in left:
                    note(child, 'added')
                elif key not in right:
                    note(child, 'removed')
                else:
                    visit(left[key], right[key], child)
        elif isinstance(left, list) and isinstance(right, list):
            for index in range(max(len(left), len(right))):
                child = path + '/' + str(index)
                if index >= len(left):
                    note(child, 'added')
                elif index >= len(right):
                    note(child, 'removed')
                else:
                    visit(left[index], right[index], child)
        elif isinstance(left, bool) or isinstance(right, bool):
            if type(left) is not type(right) or left != right:
                note(path, 'changed')
        elif left != right:
            note(path, 'changed')

    visit(before, after)
    return {'change_count': count, 'changes': samples, 'truncated': count > len(samples)}


def git(root: Path, *args: str, optional: bool = False) -> bytes | None:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, check=False)
    if result.returncode:
        if optional:
            return None
        raise ValueError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def review(root: Path, entries: list[dict[str, Any]], base: str = 'HEAD', limit: int = 20) -> dict[str, Any]:
    # Resolve the revision before using it as a diff argument; no shell or user-built commands.
    revision = (git(root, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}') or b'').decode().strip()
    repo = Path((git(root, 'rev-parse', '--show-toplevel') or b'').decode().strip())
    prefix = root.resolve().relative_to(repo.resolve()).as_posix()
    prefix = '' if prefix == '.' else prefix + '/'
    tracked = git(repo, 'diff', '--name-only', '--no-renames', '-z', revision, '--', prefix or '.') or b''
    untracked = git(repo, 'ls-files', '--others', '--exclude-standard', '-z', '--', prefix or '.') or b''
    files = []
    for raw in sorted(set(tracked.split(b'\0') + untracked.split(b'\0')) - {b''}):
        path = raw.decode('utf-8')
        relative = path[len(prefix):]
        owners = [entry['id'] for entry in entries if any(fnmatchcase(relative, pattern) for pattern in entry['outputs'])]
        if not owners:
            continue
        old = git(repo, 'show', revision + ':' + path, optional=True)
        target = root / relative
        current = target.read_bytes() if target.is_file() else None
        item: dict[str, Any] = {
            'path': relative, 'candidate_generators': owners,
            'status': 'added' if old is None else 'deleted' if current is None else 'modified',
            'before_bytes': len(old) if old is not None else 0,
            'after_bytes': len(current) if current is not None else 0,
            'before_sha256': hashlib.sha256(old).hexdigest() if old is not None else None,
            'after_sha256': hashlib.sha256(current).hexdigest() if current is not None else None,
        }
        if relative.endswith('.json'):
            try:
                left = json.loads(old) if old is not None else None
                right = json.loads(current) if current is not None else None
                item.update(semantic_changes(left, right, limit))
            except (ValueError, UnicodeError) as error:
                item['error'] = 'Invalid JSON: ' + str(error)
        files.append(item)
    return {'base': revision, 'file_count': len(files), 'files': files}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate generator registration only')
    parser.add_argument('--verify', action='store_true', help='Run registered generators with --check only')
    parser.add_argument('--group', action='append', default=[], help='Select generator ID for --verify; repeatable')
    parser.add_argument('--base', default='HEAD', help='Compare working tree against this commit (default HEAD)')
    parser.add_argument('--json', action='store_true', help='Emit review as JSON')
    parser.add_argument('--limit', type=int, default=20, help='Maximum changed JSON paths per file')
    args = parser.parse_args(argv)
    try:
        entries = load_manifest()
        if args.limit < 1:
            raise ValueError('--limit must be positive')
        unknown = set(args.group) - {entry['id'] for entry in entries}
        if unknown or (args.group and not args.verify):
            raise ValueError('--group requires --verify and known IDs: ' + repr(sorted(unknown)))
        if args.verify:
            failed = []
            for entry in entries:
                if args.group and entry['id'] not in args.group:
                    continue
                print('Verify: ' + entry['id'], flush=True)
                result = subprocess.run([sys.executable, entry['script'], '--check'], cwd=ROOT, check=False)
                if result.returncode:
                    failed.append(entry['id'])
            if failed:
                print('Generation checks failed: ' + ', '.join(failed), file=sys.stderr)
                return 1
        if args.check or args.verify:
            print(f'Generated artifact registry valid: {len(entries)} generators')
            return 0
        result = review(ROOT, entries, args.base, args.limit)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Generated review against {result['base'][:12]}: {result['file_count']} files")
            for item in result['files']:
                print(f"{item['status']}: {item['path']} ({item['before_bytes']} -> {item['after_bytes']} bytes)")
                if 'error' in item:
                    print('  ' + item['error'])
                for change in item.get('changes', []):
                    print('  ' + change['kind'] + ' ' + change['path'])
                if item.get('truncated'):
                    print(f"  ... {item['change_count']} changed paths total")
        return int(any('error' in item for item in result['files']))
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
