"""湿空气（moist air）教学用物性：含湿量、相对湿度、湿空气焓与温度换算。

用于 `SolverOptions.moist_air=True` 的空气网络：热力层把含湿量 w 作为与焓并列的
输运标量；本模块只提供纯函数，不做 EOS 反算（空气按理想气体混合物处理）。

约定：
* w 为含湿量，kg 水 / kg 干空气；
* 湿空气比焓按每 kg 干空气计：
  h = cp_da·(T−T0) + w·(r0 + cp_v·(T−T0))，T0 = 273.15 K；
* 饱和水蒸气压力用 Magnus 近似（教学用，误差约 0.3%，不替代 CoolProp 湿空气查询）；
* 密度按理想气体混合物近似：ρ = p·(1+w) / (R_da·T·(1+1.6078·w))。
"""
from __future__ import annotations

from .models import FluidState

T0 = 273.15
CP_DA = 1006.0            # J/(kg_da·K)
CP_V = 1860.0             # J/(kg_v·K)
R0 = 2.501e6              # J/kg_v，0 °C 汽化潜热
R_DA = 287.05             # J/(kg_da·K)
MU_DA = 1.82e-5           # Pa·s，干空气动力黏度（教学常数）
WATER_VAPOR_RATIO = 1.6078  # R_da / R_v


def saturation_pressure_pa(temperature_k: float) -> float:
    """饱和水蒸气分压（Magnus 近似）。"""
    celsius = temperature_k - T0
    return 611.2 * pow(2.718281828459045, 17.62 * celsius / (243.12 + celsius))


def saturation_humidity_ratio(temperature_k: float, pressure_pa: float) -> float:
    """给定温度与总压下的饱和含湿量。"""
    saturation = saturation_pressure_pa(temperature_k)
    if saturation >= pressure_pa:
        return float("inf")
    return 0.622 * saturation / (pressure_pa - saturation)


def humidity_ratio_from_relative(temperature_k: float, pressure_pa: float, relative: float) -> float:
    """由相对湿度求含湿量；`relative` 取 0–1。"""
    saturation = saturation_pressure_pa(temperature_k) * min(max(relative, 0.0), 1.0)
    if saturation >= pressure_pa:
        return float("inf")
    return 0.622 * saturation / (pressure_pa - saturation)


def relative_humidity(temperature_k: float, pressure_pa: float, humidity_ratio: float) -> float:
    """由含湿量求相对湿度（0–1）：RH = p_v / p_sat(T)，p_v = p·w/(0.622+w)。"""
    saturation = saturation_pressure_pa(temperature_k)
    if saturation <= 0.0:
        return 0.0
    vapor_pressure = pressure_pa * humidity_ratio / (0.622 + humidity_ratio)
    return min(max(vapor_pressure / saturation, 0.0), 1.0)


def dew_point_k(temperature_k: float, pressure_pa: float, humidity_ratio: float) -> float:
    """露点温度（Magnus 反算）。"""
    import math
    pressure_vapor = pressure_pa * humidity_ratio / (0.622 + humidity_ratio)
    if pressure_vapor <= 0.0:
        return T0
    log_ratio = math.log(pressure_vapor / 611.2)
    return T0 + 243.12 * log_ratio / (17.62 - log_ratio)


def enthalpy_j_kg_da(temperature_k: float, humidity_ratio: float) -> float:
    """湿空气比焓（每 kg 干空气）。"""
    celsius = temperature_k - T0
    return CP_DA * celsius + humidity_ratio * (R0 + CP_V * celsius)


def temperature_from_enthalpy(enthalpy_j_kg_da: float, humidity_ratio: float) -> float:
    """由湿空气比焓与含湿量反算温度。"""
    denominator = CP_DA + CP_V * humidity_ratio
    if denominator <= 0.0:
        raise ValueError("含湿量无效，无法反算湿空气温度")
    celsius = (enthalpy_j_kg_da - R0 * humidity_ratio) / denominator
    return T0 + celsius


def mixture_cp_j_kg_k(humidity_ratio: float) -> float:
    """每 kg 干空气的湿空气定压比热。"""
    return CP_DA + CP_V * humidity_ratio


def density_kg_m3(pressure_pa: float, temperature_k: float, humidity_ratio: float) -> float:
    """湿空气密度（理想气体混合物近似）。"""
    return pressure_pa * (1.0 + humidity_ratio) / (R_DA * temperature_k * (1.0 + WATER_VAPOR_RATIO * humidity_ratio))


def state_ph_w(pressure_pa: float, enthalpy_j_kg_da: float, humidity_ratio: float) -> FluidState:
    """湿空气状态：由 p、h、w 反求温度（每 kg 干空气口径）。"""
    temperature = temperature_from_enthalpy(enthalpy_j_kg_da, humidity_ratio)
    return FluidState(pressure_pa=pressure_pa, temperature_k=temperature, enthalpy_j_kg=enthalpy_j_kg_da,
                      density_kg_m3=density_kg_m3(pressure_pa, temperature, humidity_ratio),
                      viscosity_pa_s=MU_DA, specific_heat_j_kg_k=mixture_cp_j_kg_k(humidity_ratio),
                      phase="gas", quality=None, humidity_ratio_kg_kg=humidity_ratio,
                      composition={"water": humidity_ratio / (1.0 + humidity_ratio)})


def state_pt_w(pressure_pa: float, temperature_k: float, humidity_ratio: float) -> FluidState:
    """湿空气状态：由 p、T、w 直接得到。"""
    return FluidState(pressure_pa=pressure_pa, temperature_k=temperature_k,
                      enthalpy_j_kg=enthalpy_j_kg_da(temperature_k, humidity_ratio),
                      density_kg_m3=density_kg_m3(pressure_pa, temperature_k, humidity_ratio),
                      viscosity_pa_s=MU_DA, specific_heat_j_kg_k=mixture_cp_j_kg_k(humidity_ratio),
                      phase="gas", quality=None, humidity_ratio_kg_kg=humidity_ratio,
                      composition={"water": humidity_ratio / (1.0 + humidity_ratio)})
