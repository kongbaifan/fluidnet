"""Reproducible public correlation and analytical limit checks, not plant calibration."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fn_engine.model_types.base import FluidConfig  # noqa: E402
from fn_engine.properties import property_service  # noqa: E402
from fn_engine.refrigeration.network import homogeneous_drop  # noqa: E402


def evaluate_reference():
    sources = json.loads((ROOT / 'examples/foundation/reference-sources.json').read_text(encoding='utf-8'))
    reference = sources['ammonia_saturation']
    ammonia = property_service(FluidConfig(fluid='Ammonia', phase_policy='any'))
    rows = []
    for temperature in reference['evaluation_temperature_k']:
        assert reference['valid_temperature_k'][0] <= temperature <= reference['valid_temperature_k'][1]
        expected = 1e5 * 10 ** (reference['A'] - reference['B'] / (temperature + reference['C']))
        actual = ammonia.saturation_p(temperature)
        rows.append({'temperature_k': temperature, 'reference_pressure_pa': expected,
                     'engine_pressure_pa': actual, 'relative_difference': actual / expected - 1.})
    water = property_service(FluidConfig(fluid='Water', phase_policy='any'))
    state = water.state_pt(200000., 293.15)
    diameter, length, mass = .01, 2., .001
    # Independent Hagen-Poiseuille laminar limit, with no call to the engine's
    # friction-factor, pipe-drop or pump interpolator for the expected result.
    expected = 128. * state.viscosity_pa_s * length * mass / (math.pi * state.density_kg_m3 * diameter ** 4)
    actual = homogeneous_drop(water, {'diameter_m': diameter, 'length_m': length}, mass,
                              state.pressure_pa, state.pressure_pa, state.enthalpy_j_kg)
    maximum = max(abs(row['relative_difference']) for row in rows)
    laminar = {'reference_pressure_drop_pa': expected, 'engine_pressure_drop_pa': actual,
               'relative_difference': actual / expected - 1.}
    return {'reference_version': 1, 'calibration_status': sources['calibration_status'],
            'sources': sources, 'ammonia_saturation': rows,
            'maximum_pressure_relative_difference': maximum, 'laminar_pipe': laminar,
            'passed': maximum < reference['maximum_relative_disagreement']
                      and abs(laminar['relative_difference']) < 1e-10}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/foundation/reference-validation.json')
    args = parser.parse_args()
    result = evaluate_reference()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ('passed', 'maximum_pressure_relative_difference', 'laminar_pipe')}))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
