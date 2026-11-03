"""Capture or compare public results while moving architecture boundaries."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from fn_engine.bridge import normalize_prototype_export  # noqa: E402
from fn_engine.compiler import compile_project  # noqa: E402
from fn_engine.hvac_examples import hvac_example  # noqa: E402
from fn_engine.refrigeration.coupling_examples import thermal_coupling_example  # noqa: E402
from fn_engine.refrigeration.examples import ideal_room_example, room_example, station_example  # noqa: E402
from fn_engine.sessions import create_session  # noqa: E402


def projects():
    raw = json.loads((ROOT / 'tests/fixtures/prototype.json').read_text(encoding='utf-8'))
    raw['activeProject'] = 'water-net'
    yield 'fluid', normalize_prototype_export(raw)
    yield 'thermal', ideal_room_example()
    yield 'cold_store', room_example()
    yield 'refrigeration', station_example()
    yield 'coupled', thermal_coupling_example()
    plant = hvac_example('hvac-basic-plant')
    for node in plant.instances:
        node.page_id = 'terminals' if node.id in {'Coil', 'Coil2', 'Balance1', 'Balance2', 'Header', 'Collector'} else 'plant'
    yield 'hvac_multi_page', plant


def capture():
    result = {}
    for name, project in projects():
        for module in project.modules:
            module.package_path = None
        encoded = json.dumps(project.model_dump(mode='json'), sort_keys=True, ensure_ascii=False)
        session = create_session(compile_project(project), 10., 5.)
        try:
            frames = [session.initialize()]
            while not session.done:
                frames.append(session.advance())
            result[name] = {
                'input_sha256': hashlib.sha256(encoded.encode()).hexdigest(),
                'modules': {m.id: [m.version, m.content_hash, m.definition_hash] for m in project.modules},
                'frames': [{'time_s': f.time_s, 'sequence': f.sequence, 'parameter_revision': f.parameter_revision,
                            'valid': f.valid, 'variables': f.variables,
                            'balances': {k: v for k, v in f.metrics.items() if 'residual' in k or 'balance' in k},
                            'diagnostics': [d.code for d in f.diagnostics]} for f in frames],
            }
            print(f'{name}: {len(frames)} frames, {len(frames[-1].variables)} public variables', flush=True)
        finally:
            session.close()
    return result


def compare(expected, actual, path='root'):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and expected.keys() == actual.keys(), path + ': keys differ'
        for key in expected:
            compare(expected[key], actual[key], path + '.' + key)
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual), path + ': lengths differ'
        for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
            compare(left, right, f'{path}[{index}]')
    elif isinstance(expected, float):
        assert isinstance(actual, (float, int)) and math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-8), (
            path, expected, actual)
    else:
        assert expected == actual, (path, expected, actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', type=Path)
    args = parser.parse_args()
    result = capture()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    if args.compare:
        compare(json.loads(args.compare.read_text(encoding='utf-8')), result)
        print('All six input identities and public result sequences match the baseline.')


if __name__ == '__main__':
    main()
