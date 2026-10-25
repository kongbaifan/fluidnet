"""Engineering acceptance helpers: independent equations, frame comparison and one end-to-end case."""
import math
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

from engineering_checks import compare_frames, effectiveness  # noqa: E402


def test_effectiveness_matches_textbook_limits():
    # Balanced counterflow: NTU/(1+NTU); parallel flow with Cr=1: (1-exp(-2NTU))/2.
    assert effectiveness(1000., 500., 500.) == pytest.approx(2 / 3)
    assert effectiveness(1000., 500., 500., counterflow=False) == pytest.approx(-math.expm1(-4.) / 2)
    # Cr -> 0 reduces to 1-exp(-NTU) for both arrangements.
    assert effectiveness(1000., 500., 5e9) == pytest.approx(-math.expm1(-2.), rel=1e-6)
    assert effectiveness(0., 500., 500.) == 0.


def frame(time_s, **variables):
    return {'time_s': time_s, 'sequence': 0, 'parameter_revision': 0, 'valid': True, 'status': 'solved',
            'variables': variables}


def test_compare_frames_uses_key_tolerances():
    reference = [frame(0., **{'B.pressure_pa': 1e5, 'B.mass_flow_kg_s': 1., 'B.mode': 'on'})]
    assert compare_frames(reference, [frame(0., **{'B.pressure_pa': 1e5 + .5, 'B.mass_flow_kg_s': 1. + 1e-9,
                                                   'B.mode': 'on'})])['passed']
    report = compare_frames(reference, [frame(0., **{'B.pressure_pa': 1e5 + 1e3, 'B.mass_flow_kg_s': 1.,
                                                     'B.mode': 'off'})])
    assert not report['passed']
    assert {f['key'] for f in report['failures']} == {'B.pressure_pa', 'B.mode'}
    assert not compare_frames(reference, reference + reference)['passed']


def test_pid_tank_case_passes_ledgers_and_releases_workers():
    from engineering_acceptance import run_case
    row = run_case('pid-tank', 'both')
    assert row['checks']['passed'], row['checks']['failures']
    assert row['checks']['counts']['tank_mass_ledger'] == row['accepted_substeps'] > 0
    assert row['workers_started'] == 1 and row['workers_alive_after_close'] == 0
