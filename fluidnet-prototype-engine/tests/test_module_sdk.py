"""Lightweight SDK contract tests: no fn_engine or scientific dependencies imported."""
import json
from pathlib import Path
import subprocess
import sys
import textwrap

import fn_sdk

ROOT = Path(__file__).resolve().parents[1]


def test_public_exports_and_pep561_marker():
    assert {'ModuleContext', 'NetworkBuilder', 'PortState', 'ChannelResult', 'FluidState',
            'PropertyService', 'EvaluateResult', 'CommitResult', 'DeviceModule'} <= set(fn_sdk.__all__)
    assert all(hasattr(fn_sdk, name) for name in fn_sdk.__all__)
    assert (Path(fn_sdk.__file__).parent / 'py.typed').is_file()


def test_sdk_and_typed_example_import_with_only_the_standard_library():
    source = textwrap.dedent('''
        import importlib.abc
        import json
        import pathlib
        import subprocess
        import sys
        sys.path.insert(0, sys.argv[1])
        forbidden = {'fn_engine', 'numpy', 'scipy', 'CoolProp', 'pydantic'}
        class RejectScientificImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in forbidden:
                    raise AssertionError('unexpected dependency: ' + fullname)
        def no_process(*args, **kwargs):
            raise AssertionError('SDK import started a subprocess')
        subprocess.Popen = no_process
        sys.meta_path.insert(0, RejectScientificImports())
        import fn_sdk
        for path in sys.argv[2:]:
            example = {'__name__': 'sdk_example'}
            exec(compile(pathlib.Path(path).read_text(encoding='utf-8'), path, 'exec'), example)
            example['typed_module']()
        assert fn_sdk.pipe_pressure_drop_pa(mass_flow_kg_s=0., density_kg_m3=1000.,
            viscosity_pa_s=.001, length_m=10., diameter_m=.05) == 0.
        assert fn_sdk.kv_from_loss_coefficient(diameter_m=.05, loss_coefficient=8.) > 0
        assert not any(name.split('.')[0] in forbidden for name in sys.modules)
        print(json.dumps({'sdk_version': fn_sdk.SDK_API_VERSION, 'examples': len(sys.argv[2:])}))
    ''')
    result = subprocess.run([sys.executable, '-I', '-S', '-c', source, str(ROOT / 'backend'),
                             str(ROOT / 'examples/module_sdk/valve.py'), str(ROOT / 'examples/module_sdk/resistance.py'),
                             str(ROOT / 'examples/module_sdk/timed_valve.py'),str(ROOT/'examples/module_sdk/fan_coil.py'),
                             str(ROOT/'examples/module_sdk/cooling_tower.py'),str(ROOT/'examples/module_sdk/capillary.py')],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)['examples'] == 6


def test_type_checker_rejects_bad_relation_state_and_input_writes(tmp_path):
    source = tmp_path / 'invalid_author.py'
    source.write_text(textwrap.dedent('''
        from fn_sdk import ModuleContext
        def evaluate(ctx: ModuleContext) -> None:
            ctx.net.valve(channel='main', kv='sixteen', opening=0.8)
            ctx.state['object'] = object()
            ctx.port('in0').pressure_pa = 120000.0
            ctx.time_s = 3.0
            ctx.execution.phase = 'commit_step'
    '''), encoding='utf-8')
    result = subprocess.run([sys.executable, '-m', 'mypy', '--config-file', 'mypy-sdk.ini', str(source)],
                            cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert result.returncode == 1, result.stdout + result.stderr
    assert '[arg-type]' in result.stdout
    assert '[assignment]' in result.stdout
    assert 'read-only' in result.stdout
