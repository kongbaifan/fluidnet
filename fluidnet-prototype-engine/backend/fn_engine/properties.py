from __future__ import annotations

import math
from functools import lru_cache

from CoolProp.CoolProp import PhaseSI, PropsSI

from .models import FluidConfig, FluidState


class PropertyError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _fluid_name(config: FluidConfig) -> str:
    if config.composition:
        # CoolProp accepts named mixtures such as Air.mix, while arbitrary
        # component fractions need a dedicated AbstractState configuration.
        # Keep this explicit instead of silently ignoring the composition.
        raise PropertyError("COMPOSITION_UNSUPPORTED", "首版 CoolProp 适配器仅接受单一工质名称；组分混合物接口已预留")
    return config.fluid


class CoolPropPropertyService:
    """Single-phase CoolProp adapter used by module contexts.

    The service deliberately exposes a small stable surface. Modules do not
    import CoolProp directly, so a REFPROP or project-specific backend can be
    added later without changing module code.
    """

    backend = "coolprop"

    def __init__(self, config: FluidConfig):
        if config.backend != "coolprop":
            raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {config.backend} 尚未启用")
        self.config = config
        self.fluid = _fluid_name(config)

    @lru_cache(maxsize=32768)
    def _state_pt_cached(self, pressure_pa: float, temperature_k: float) -> FluidState:
        if not math.isfinite(pressure_pa) or not math.isfinite(temperature_k):
            raise PropertyError("PROPERTY_RANGE", "物性输入必须是有限数")
        if pressure_pa <= 0 or temperature_k <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力和温度必须为正数")
        try:
            phase = str(PhaseSI("P", pressure_pa, "T", temperature_k, self.fluid)).lower()
            values = {
                "enthalpy_j_kg": float(PropsSI("Hmass", "P", pressure_pa, "T", temperature_k, self.fluid)),
                "density_kg_m3": float(PropsSI("Dmass", "P", pressure_pa, "T", temperature_k, self.fluid)),
                "viscosity_pa_s": float(PropsSI("VISCOSITY", "P", pressure_pa, "T", temperature_k, self.fluid)),
                "specific_heat_j_kg_k": float(PropsSI("Cpmass", "P", pressure_pa, "T", temperature_k, self.fluid)),
                "thermal_conductivity_w_m_k": float(PropsSI("CONDUCTIVITY", "P", pressure_pa, "T", temperature_k, self.fluid)),
            }
        except Exception as exc:
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法计算 {self.fluid} 的状态：{exc}") from exc
        if not all(math.isfinite(value) for value in values.values()):
            raise PropertyError("PROPERTY_FAILURE", "CoolProp 返回了非有限物性值")
        if self.config.phase_policy == "liquid" and "gas" in phase:
            raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相液体约束")
        if self.config.phase_policy == "gas" and "liquid" in phase:
            raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相气体约束")
        return FluidState(
            pressure_pa=pressure_pa,
            temperature_k=temperature_k,
            phase=phase,
            composition={self.fluid: 1.0},
            **values,
        )

    def state_pt(self, pressure: float, temperature: float) -> FluidState:
        return self._state_pt_cached(float(pressure), float(temperature))

    @lru_cache(maxsize=32768)
    def _state_ph_cached(self, pressure_pa: float, enthalpy_j_kg: float) -> FluidState:
        if not math.isfinite(pressure_pa) or not math.isfinite(enthalpy_j_kg):
            raise PropertyError("PROPERTY_RANGE", "物性输入必须是有限数")
        try:
            temperature = float(PropsSI("T", "P", pressure_pa, "Hmass", enthalpy_j_kg, self.fluid))
        except Exception as exc:
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法从压力/焓计算状态：{exc}") from exc
        return self._state_pt_cached(pressure_pa, temperature)

    def state_ph(self, pressure: float, enthalpy: float) -> FluidState:
        return self._state_ph_cached(float(pressure), float(enthalpy))


def property_service(config: FluidConfig) -> CoolPropPropertyService:
    return CoolPropPropertyService(config)
