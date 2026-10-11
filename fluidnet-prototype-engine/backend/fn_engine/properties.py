from __future__ import annotations

import math
import threading
from functools import lru_cache

import CoolProp.CoolProp as CP
from CoolProp import AbstractState

from .models import FluidConfig, FluidState


class PropertyError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


# CoolProp phase indices -> the lowercase names PhaseSI reports: "liquid", "gas",
# "supercritical_gas", "twophase", ... The phase policy matches on these substrings.
_PHASE_NAMES = {getattr(CP, name): name[len("iphase_"):] for name in dir(CP) if name.startswith("iphase_")}
_TWO_PHASE = "twophase"

# AbstractState holds the last flash internally, so each thread keeps its own
# instance per fluid; the solver runs on a 2-thread executor.
_thread_states = threading.local()


def _abstract_state(fluid: str) -> AbstractState:
    states = getattr(_thread_states, "states", None)
    if states is None:
        states = _thread_states.states = {}
    state = states.get(fluid)
    if state is None:
        state = states[fluid] = AbstractState("HEOS", fluid)
    return state


@lru_cache(maxsize=32768)
def _flash(fluid: str, inputs: str, pressure_pa: float, second: float) -> FluidState:
    """One CoolProp flash per distinct input, shared by every phase policy of this fluid.

    `second` is the temperature (K) for "PT" and the specific enthalpy (J/kg) for "PH".
    """
    try:
        state = _abstract_state(fluid)
        if inputs == "PT":
            state.update(CP.PT_INPUTS, pressure_pa, second)
        else:
            state.update(CP.HmassP_INPUTS, second, pressure_pa)
        phase = _PHASE_NAMES.get(state.phase(), "unknown")
        two_phase = phase == _TWO_PHASE
        values = {
            "temperature_k": second if inputs == "PT" else float(state.T()),
            "enthalpy_j_kg": second if inputs == "PH" else float(state.hmass()),
            "density_kg_m3": float(state.rhomass()),
            # A homogeneous two-phase state has no single viscosity, conductivity or cp;
            # CoolProp would return one-sided values, so they are reported as missing.
            "viscosity_pa_s": None if two_phase else float(state.viscosity()),
            "specific_heat_j_kg_k": None if two_phase else float(state.cpmass()),
            "thermal_conductivity_w_m_k": None if two_phase else float(state.conductivity()),
        }
        quality = float(state.Q()) if two_phase else None
    except Exception as exc:
        if inputs == "PT":
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法计算 {fluid} 的状态：{exc}") from exc
        raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法从压力/焓计算状态：{exc}") from exc
    numbers = [value for value in values.values() if value is not None] + ([quality] if quality is not None else [])
    if not all(math.isfinite(value) for value in numbers):
        raise PropertyError("PROPERTY_FAILURE", "CoolProp 返回了非有限物性值")
    return FluidState(pressure_pa=pressure_pa, phase=phase, quality=quality, composition={fluid: 1.0}, **values)


def _check_phase(policy: str, state: FluidState) -> None:
    phase = state.phase
    if policy == "liquid" and ("gas" in phase or phase == _TWO_PHASE):
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相液体约束")
    if policy == "gas" and ("liquid" in phase or phase == _TWO_PHASE):
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相气体约束")
    if policy == "single_phase" and phase == _TWO_PHASE:
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相约束")


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
        self.phase_policy = config.phase_policy

    def _result(self, state: FluidState) -> FluidState:
        _check_phase(self.phase_policy, state)
        # The flash cache is shared; hand out a copy so callers cannot alter it.
        return state.model_copy(update={"composition": dict(state.composition)})

    def state_pt(self, pressure: float, temperature: float) -> FluidState:
        pressure, temperature = float(pressure), float(temperature)
        if not math.isfinite(pressure) or not math.isfinite(temperature):
            raise PropertyError("PROPERTY_RANGE", "物性输入必须是有限数")
        if pressure <= 0 or temperature <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力和温度必须为正数")
        return self._result(_flash(self.fluid, "PT", pressure, temperature))

    def state_ph(self, pressure: float, enthalpy: float) -> FluidState:
        pressure, enthalpy = float(pressure), float(enthalpy)
        if not math.isfinite(pressure) or not math.isfinite(enthalpy):
            raise PropertyError("PROPERTY_RANGE", "物性输入必须是有限数")
        if pressure <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数")
        return self._result(_flash(self.fluid, "PH", pressure, enthalpy))


_services: dict[tuple[str, str, str], CoolPropPropertyService] = {}
_services_lock = threading.Lock()


def property_service(config: FluidConfig) -> CoolPropPropertyService:
    # Same check order as before: backend, then composition.
    if config.backend != "coolprop":
        raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {config.backend} 尚未启用")
    key = (config.backend, _fluid_name(config), config.phase_policy)
    with _services_lock:
        service = _services.get(key)
        if service is None:
            service = _services[key] = CoolPropPropertyService(config)
    return service
