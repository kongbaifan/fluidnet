"""Frozen pre-refactor values and public dispatcher errors, not generated expectations."""
import json
from pathlib import Path

import pytest

from fn_engine.hydraulic_derivatives import HYDRAULIC_RELATIONS, branch_drop_and_slope, branch_drop_value

BASELINE = json.loads((Path(__file__).parent / 'fixtures/hydraulic-dispatch.json').read_text())


@pytest.mark.parametrize('row', BASELINE['rows'])
def test_registered_value_and_derivative_preserve_frozen_results(row):
    args = row['model'], BASELINE['parameters'], row['flow'], row['density'], row['viscosity']
    assert branch_drop_value(*args) == row['value']
    assert list(branch_drop_and_slope(*args)) == row['slope_pair']


def test_registry_is_read_only_and_rejects_unknown_models():
    with pytest.raises(TypeError):
        HYDRAULIC_RELATIONS['other'] = HYDRAULIC_RELATIONS['pipe']
    for function in (branch_drop_value, branch_drop_and_slope):
        with pytest.raises(ValueError, match='未注册的支路模型：other'):
            function('other', {}, 1., 1000., .001)
        with pytest.raises(ValueError, match='停泵阻力模型尚未定义'):
            function('pump_curve', {'speed_ratio': 0}, 1., 1000., .001)
