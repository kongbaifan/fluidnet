"""J0/J1：内置水力关系解析导数与自适应中心差分的对照。"""
import math

import pytest

from fn_engine.hydraulic_derivatives import (branch_drop_and_slope, branch_drop_value, haaland_friction,
                                             _haaland_slope, pipe_drop, pipe_drop_and_slope,
                                             pump_head, pump_head_and_slope)

RHO, MU = 998.2752462838249, 1.0015503944484675e-3


def numeric_slope(function, q, relative=1e-4, absolute=0.0):
    h = max(abs(q) * relative, absolute) or 1e-6
    if q == 0:
        return (function(h) - function(-h)) / (2 * h)
    return (function(q + h) - function(q - h)) / (2 * h)


def assert_close(analytic, numeric, rel=1e-5, abs_=1e-9):
    scale = max(abs(numeric), 1e-300)
    assert abs(analytic - numeric) <= abs_ + rel * scale, f'解析 {analytic!r} vs 差分 {numeric!r}'


# --- J0：阀门 / 阻力 -------------------------------------------------------

@pytest.mark.parametrize('q', [1e-4, 0.05, 1.0, 5.0, -0.05, -2.0])
def test_valve_slope_matches_central_difference(q):
    params = {'kv_m3_h': 12.0, 'opening_ratio': 0.6, 'height_m': 1.5}
    value, slope = branch_drop_and_slope('valve', params, q, RHO, MU)
    assert value == pytest.approx(branch_drop_value('valve', params, q, RHO, MU), rel=0, abs=0)
    assert_close(slope, numeric_slope(lambda x: branch_drop_value('valve', params, x, RHO, MU), q))


def test_valve_slope_at_zero_is_math_limit():
    params = {'kv_m3_h': 12.0, 'opening_ratio': 0.6}
    _, slope = branch_drop_and_slope('valve', params, 0.0, RHO, MU)
    assert slope == 0.0
    assert branch_drop_value('valve', params, 0.0, RHO, MU) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize('q', [0.01, 0.5, 3.0, -0.5])
def test_resistance_slope(q):
    params = {'diameter_m': 0.05, 'loss_coefficient': 8.0}
    _, slope = branch_drop_and_slope('resistance', params, q, RHO, MU)
    assert_close(slope, numeric_slope(lambda x: branch_drop_value('resistance', params, x, RHO, MU), q))


# --- J1：管道（层流 / 过渡 / 湍流 / 粗糙度边界） ----------------------------

def pipe_params(reynolds_target, q=1.0, diameter=0.05, roughness=0.0, length=10.0):
    """反推黏度使指定流量下的 Re 命中目标（层流/过渡/湍流各段都能精确取样）。"""
    area = math.pi * diameter ** 2 / 4
    viscosity = abs(q) * diameter / (area * reynolds_target)
    return {'length_m': length, 'diameter_m': diameter, 'roughness_m': roughness}, viscosity


@pytest.mark.parametrize('reynolds', [100.0, 1000.0, 2600.0, 3150.0, 12000.0, 250000.0])
@pytest.mark.parametrize('q', [0.7, -0.7])
def test_pipe_slope_across_regimes(reynolds, q):
    params, viscosity = pipe_params(reynolds, q)
    value, slope = pipe_drop_and_slope(params, q, RHO, viscosity)
    assert value == pytest.approx(pipe_drop(params, q, RHO, viscosity), rel=0, abs=0)
    numeric = numeric_slope(lambda x: pipe_drop(params, x, RHO, viscosity), q)
    assert_close(slope, numeric, rel=2e-5)


@pytest.mark.parametrize('reynolds', [2300.0, 4000.0])
@pytest.mark.parametrize('q', [0.7, -0.7])
def test_pipe_slope_at_blend_boundaries_uses_right_derivative(reynolds, q):
    """过渡带边界不可导：解析导数采用“进入湍流混合段”的单侧约定。

    沿 |q| 增大方向做单侧差分（q>0 时 h>0，q<0 时 h<0），与实现约定对齐。
    """
    params, viscosity = pipe_params(reynolds, q)
    _, slope = pipe_drop_and_slope(params, q, RHO, viscosity)
    h = abs(q) * 1e-6 * (1 if q > 0 else -1)
    one_sided = (pipe_drop(params, q + h, RHO, viscosity) - pipe_drop(params, q, RHO, viscosity)) / h
    assert_close(slope, one_sided, rel=2e-5)


@pytest.mark.parametrize('roughness', [0.0, 1.5e-6, 4.5e-4, 3e-3])
def test_pipe_roughness_bounds(roughness):
    params = {'length_m': 4.0, 'diameter_m': 0.08, 'roughness_m': roughness}
    value, slope = pipe_drop_and_slope(params, 1.2, RHO, MU)
    assert value == pytest.approx(pipe_drop(params, 1.2, RHO, MU), rel=0, abs=0)
    assert_close(slope, numeric_slope(lambda x: pipe_drop(params, x, RHO, MU), 1.2), rel=1e-4)


def test_pipe_height_constant_has_zero_derivative():
    params = {'length_m': 4.0, 'diameter_m': 0.08, 'roughness_m': 1.5e-6, 'height_m': 12.0}
    value, slope = branch_drop_and_slope('pipe', params, 1.0, RHO, MU)
    flat = {'length_m': 4.0, 'diameter_m': 0.08, 'roughness_m': 1.5e-6}
    assert value == pytest.approx(branch_drop_value('pipe', flat, 1.0, RHO, MU) + RHO * 9.80665 * 12.0, rel=1e-12)
    assert slope == pytest.approx(branch_drop_and_slope('pipe', flat, 1.0, RHO, MU)[1], rel=1e-12)


# --- J1：泵分段线性曲线 -----------------------------------------------------

CURVE = [[0.0, 30.0], [5.0, 26.0], [10.0, 15.0], [14.0, 0.0]]


@pytest.mark.parametrize('flow_m3_h', [0.0, 2.5, 5.0, 8.0, 10.0, 12.5, 14.0, 16.5, -1.0])
@pytest.mark.parametrize('speed', [0.7, 1.0, 1.3])
def test_pump_head_slope(flow_m3_h, speed):
    value, slope = pump_head_and_slope(CURVE, flow_m3_h, speed)
    assert value == pytest.approx(pump_head(CURVE, flow_m3_h, speed), rel=0, abs=0)
    numeric = numeric_slope(lambda x: pump_head(CURVE, x, speed), flow_m3_h)
    # 拐点（5、10、14）采用右段斜率，是单侧约定：差值可能与中心差分差一个段的斜率跳变。
    if any(abs(flow_m3_h - point[0]) < 1e-9 for point in CURVE):
        return
    assert_close(slope, numeric, rel=1e-4)


def test_pump_breakpoint_uses_right_segment():
    _, slope_at_5 = pump_head_and_slope(CURVE, 5.0, 1.0)
    right = (15.0 - 26.0) / (10.0 - 5.0)
    left = (26.0 - 30.0) / (5.0 - 0.0)
    assert slope_at_5 == pytest.approx(right, rel=1e-12), '拐点必须给出明确的单侧（右段）约定'
    assert slope_at_5 != pytest.approx(left, rel=1e-6)


def test__haaland_slope_matches_numeric():
    roughness, diameter = 4.5e-4, 0.08
    for reynolds in (4000.0, 20000.0, 300000.0):
        friction = haaland_friction(roughness, diameter, reynolds)
        analytic = _haaland_slope(roughness, diameter, reynolds, friction)
        h = reynolds * 1e-6
        numeric = (haaland_friction(roughness, diameter, reynolds + h)
                   - haaland_friction(roughness, diameter, reynolds - h)) / (2 * h)
        assert_close(analytic, numeric, rel=1e-5, abs_=1e-12)
