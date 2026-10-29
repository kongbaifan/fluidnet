"""CoolProp 湿空气入口：公共比焓按混合物，输运按干空气。

水源采用 0 °C 液水工程焓参考；不修改 CoolProp 的全局参考态。
"""
from __future__ import annotations

import math
from functools import lru_cache

from CoolProp.CoolProp import HAPropsSI

from .models import FluidState

T0, CP_DA, CP_V, R0 = 273.15, 1006., 1860., 2501000.
AIR_STATE_FIELDS = (
    'humidity_ratio_kg_kg', 'relative_humidity', 'enthalpy_j_kg_dry_air',
    'specific_heat_j_kg_dry_air_k', 'dew_point_k', 'wet_bulb_k',
)
AIR_FLOW_FIELDS = ('dry_air_mass_flow_kg_s', 'water_vapor_mass_flow_kg_s',
                   'inlet_mass_flow_kg_s', 'outlet_mass_flow_kg_s')


class AirPropertyError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def _finite(*values):
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise AirPropertyError('AIR_PROPERTY_RANGE', '湿空气输入必须为有限数值')


def _pt(pressure, temperature):
    _finite(pressure, temperature)
    if not 60000 <= pressure <= 120000 or not 253.15 <= temperature <= 333.15:
        raise AirPropertyError('AIR_PROPERTY_RANGE', '湿空气适用范围：60–120 kPa、−20–60 °C')


def _ha(output, *args):
    try:
        value = float(HAPropsSI(output, *args))
        if not math.isfinite(value):
            raise ValueError('非有限物性')
        return value
    except (ValueError, RuntimeError) as error:
        raise AirPropertyError('AIR_PROPERTY_FAILURE', f'湿空气物性查询 {output} 失败：{error}') from error


def liquid_enthalpy(temperature):
    return 4180. * (temperature - T0)


def vapor_enthalpy(temperature):
    return R0 + CP_V * (temperature - T0)


def saturation_humidity_ratio(temperature_k, pressure_pa):
    _pt(pressure_pa, temperature_k)
    return _ha('W', 'P', pressure_pa, 'T', temperature_k, 'R', 1.)


class MoistAirService:
    """运行内有界精确键缓存；返回副本，避免调用者污染缓存。"""
    def __init__(self):
        self._cached_ptw = lru_cache(maxsize=4096)(self._state_ptw)

    def state_ptw(self, pressure_pa, temperature_k, humidity_ratio_kg_kg):
        _finite(pressure_pa, temperature_k, humidity_ratio_kg_kg)
        return self._cached_ptw(float(pressure_pa), float(temperature_k), float(humidity_ratio_kg_kg)).model_copy(deep=True)

    def _state_ptw(self, p, t, w):
        _pt(p, t)
        if not 0 <= w <= .05:
            raise AirPropertyError('AIR_PROPERTY_RANGE', '含湿量必须在 0–0.05 kg/kg_da 内')
        ws = saturation_humidity_ratio(t, p)
        if w > ws + 1e-11:
            raise AirPropertyError('AIR_HUMIDITY_SUPERSATURATED', '湿空气状态过饱和；请增加除湿或修正负荷')
        # 饱和根的浮点舍入只影响 RH 查询；不修改含湿量或焓账本。
        args = ('P', p, 'T', t, 'W', w)
        h, cp = _ha('H', *args), _ha('C', *args)
        rh = 1. if abs(w-ws) <= 1e-11 else _ha('R', *args)
        return FluidState(pressure_pa=p, temperature_k=t, enthalpy_j_kg=h/(1+w),
            enthalpy_j_kg_dry_air=h, density_kg_m3=1/_ha('Vha', *args),
            viscosity_pa_s=_ha('M', *args), specific_heat_j_kg_k=cp/(1+w),
            specific_heat_j_kg_dry_air_k=cp, humidity_ratio_kg_kg=w, relative_humidity=rh,
            dew_point_k=None if w == 0 else _ha('D', *args), wet_bulb_k=_ha('B', *args),
            phase='gas', composition={'Air': 1/(1+w), 'Water': w/(1+w)})

    def state_phw(self, pressure_pa, enthalpy_j_kg_dry_air, humidity_ratio_kg_kg):
        _finite(pressure_pa, enthalpy_j_kg_dry_air, humidity_ratio_kg_kg)
        if not 60000 <= pressure_pa <= 120000 or not 0 <= humidity_ratio_kg_kg <= .05:
            raise AirPropertyError('AIR_PROPERTY_RANGE', '湿空气压力或含湿量超出适用范围')
        t = _ha('T', 'P', pressure_pa, 'H', enthalpy_j_kg_dry_air, 'W', humidity_ratio_kg_kg)
        for limit in (253.15, 333.15):
            if abs(t-limit) < 1e-8:
                t = limit
        return self.state_ptw(pressure_pa, t, humidity_ratio_kg_kg)

    def humidity_from_rh(self, pressure_pa, temperature_k, relative_humidity):
        _pt(pressure_pa, temperature_k)
        _finite(relative_humidity)
        if not 0 <= relative_humidity <= 1:
            raise AirPropertyError('AIR_PROPERTY_RANGE', '相对湿度必须在 0–1 内')
        return _ha('W', 'P', pressure_pa, 'T', temperature_k, 'R', relative_humidity)

    def saturated_state(self, pressure_pa, temperature_k):
        return self.state_ptw(pressure_pa, temperature_k, saturation_humidity_ratio(temperature_k, pressure_pa))


# 兼容函数名保留入口；质量基准变更由编译器合同版本门禁保护。
def state_pt_w(pressure_pa, temperature_k, humidity_ratio):
    return MoistAirService().state_ptw(pressure_pa, temperature_k, humidity_ratio)


def state_ph_w(pressure_pa, enthalpy_j_kg_da, humidity_ratio):
    return MoistAirService().state_phw(pressure_pa, enthalpy_j_kg_da, humidity_ratio)


def humidity_ratio_from_relative(temperature_k, pressure_pa, relative):
    return MoistAirService().humidity_from_rh(pressure_pa, temperature_k, relative)


def relative_humidity(temperature_k, pressure_pa, humidity_ratio):
    return state_pt_w(pressure_pa, temperature_k, humidity_ratio).relative_humidity


def dew_point_k(temperature_k, pressure_pa, humidity_ratio):
    return state_pt_w(pressure_pa, temperature_k, humidity_ratio).dew_point_k


def enthalpy_j_kg_da(temperature_k, humidity_ratio, pressure_pa=101325.):
    return state_pt_w(pressure_pa, temperature_k, humidity_ratio).enthalpy_j_kg_dry_air


def temperature_from_enthalpy(enthalpy_j_kg_da, humidity_ratio, pressure_pa=101325.):
    return state_ph_w(pressure_pa, enthalpy_j_kg_da, humidity_ratio).temperature_k


def density_kg_m3(pressure_pa, temperature_k, humidity_ratio):
    return state_pt_w(pressure_pa, temperature_k, humidity_ratio).density_kg_m3
