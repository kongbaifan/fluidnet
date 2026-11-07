"""Level geometry of a straight horizontal circular cylinder (no heads or tilt)."""
import math


def _fraction(value):
    if not math.isfinite(value) or not 0. <= value <= 1.:
        raise ValueError('比例必须为 0–1 之间的有限数值')
    return value


def horizontal_volume(diameter_m, length_m):
    """Internal volume of the cylindrical shell; diameter and length are independent inputs."""
    if any(not math.isfinite(v) or v <= 0. for v in (diameter_m, length_m)):
        raise ValueError('卧式圆筒内径与直筒长度必须为有限正数')
    result = math.pi/4.*diameter_m**2*length_m
    if not math.isfinite(result) or result <= 0.:
        raise ValueError('卧式圆筒几何容积必须为有限正数')
    return result


def horizontal_volume_fraction(height_ratio):
    """Fraction of total volume below h/D, including the exact empty and full endpoints."""
    value = _fraction(height_ratio)
    if value in (0., .5, 1.):
        return value
    if value > .5:
        return 1.-horizontal_volume_fraction(1.-value)
    angle = 2.*math.asin(math.sqrt(value))
    if angle < 1e-3:
        # theta - sin(2 theta)/2 loses precision near the bottom of the cylinder.
        square = angle*angle
        segment = angle**3*(2./3. + square*(-2./15. + square*(4./315. - 2./2835.*square)))
    else:
        segment = angle-math.sin(angle)*math.cos(angle)
    return segment/math.pi


def horizontal_height_ratio(volume_fraction):
    """Monotone inverse of horizontal_volume_fraction; returns h/D, not volume fraction."""
    value = _fraction(volume_fraction)
    if value in (0., .5, 1.):
        return value
    if value > .5:
        return 1.-horizontal_height_ratio(1.-value)
    # Small-depth asymptote: fraction ~ 16/(3*pi) * (h/D)**1.5.
    # Its estimate is below the root; twice the estimate bounds the lower half.
    estimate = math.exp((math.log(value)+math.log(3.*math.pi/16.))*2./3.)
    low, high = 0., min(.5, 2.*estimate)
    for _ in range(64):
        middle = (low+high)/2.
        if horizontal_volume_fraction(middle) < value:
            low = middle
        else:
            high = middle
    return (low+high)/2.


def headed_volume(diameter_m, length_m):
    return horizontal_volume(diameter_m,length_m)+math.pi*diameter_m**3/6.


def headed_fraction(height_ratio, diameter_m, length_m):
    t=_fraction(height_ratio);r=diameter_m/2.;h=diameter_m*t
    cylinder=horizontal_volume(diameter_m,length_m)*horizontal_volume_fraction(t)
    heads=math.pi*h*h*(r-h/3.)
    return (cylinder+heads)/headed_volume(diameter_m,length_m)


def headed_height_ratio(volume_fraction, diameter_m, length_m):
    target=_fraction(volume_fraction);low,high=0.,1.
    for _ in range(60):
        mid=(low+high)/2.
        if headed_fraction(mid,diameter_m,length_m)<target:low=mid
        else:high=mid
    return (low+high)/2.
