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

# Fluid strings: "Water" (HEOS), "HEOS::R134a", "IF97::Water", "INCOMP::MEG[0.3]" (mass fraction).
_BACKENDS = ("HEOS", "INCOMP", "IF97")
_LICENSED = {"REFPROP": "REFPROP 需要用户自备 NIST 许可的动态库，当前版本未接入"}

# AbstractState holds the last flash internally, so each thread keeps its own
# instance per fluid; the solver runs on a 2-thread executor.
_thread_states = threading.local()

FluidKey = tuple[str, str, tuple[float, ...]]  # (backend, fluid name, mass fractions)


def _label(key: FluidKey) -> str:
    backend, name, fractions = key
    suffix = f"[{','.join(f'{x:g}' for x in fractions)}]" if fractions else ""
    return f"{name}{suffix}" if backend == "HEOS" else f"{backend}::{name}{suffix}"


def _abstract_state(key: FluidKey) -> AbstractState:
    states = getattr(_thread_states, "states", None)
    if states is None:
        states = _thread_states.states = {}
    state = states.get(key)
    if state is None:
        backend, name, fractions = key
        try:
            state = AbstractState(backend, name)
        except Exception as exc:
            if "not found" in str(exc):
                raise PropertyError("FLUID_UNKNOWN", f"未知工质 {_label(key)}：{exc}") from exc
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法加载工质 {_label(key)}：{exc}") from exc
        if fractions:
            state.set_mass_fractions(list(fractions))
        states[key] = state
    return state


def _phase_of(key: FluidKey, state: AbstractState) -> str:
    # INCOMP solutions do not implement calc_phase; they are liquids by construction.
    if key[0] == "INCOMP":
        return "liquid"
    return _PHASE_NAMES.get(state.phase(), "unknown")


def _optional(read):
    """A property CoolProp may not define for this backend/state (speed of sound in two-phase, INCOMP)."""
    try:
        value = float(read())
    except Exception:
        return None
    return value if math.isfinite(value) else None


# (CoolProp input pair, argument order) for each supported query. `first`/`second` follow the
# method signatures: PT -> (p, T), PH -> (p, h), PS -> (p, s), PQ -> (p, Q), TQ -> (T, Q).
_INPUTS = {
    "PT": (CP.PT_INPUTS, lambda a, b: (a, b)),
    "PH": (CP.HmassP_INPUTS, lambda a, b: (b, a)),
    "PS": (CP.PSmass_INPUTS, lambda a, b: (a, b)),
    "PQ": (CP.PQ_INPUTS, lambda a, b: (a, b)),
    "TQ": (CP.QT_INPUTS, lambda a, b: (b, a)),
}


@lru_cache(maxsize=32768)
def _flash(key: FluidKey, inputs: str, first: float, second: float) -> FluidState:
    """One CoolProp flash per distinct input, shared by every phase policy of this fluid."""
    if key[0] == "INCOMP" and inputs in ("PQ", "TQ"):
        raise PropertyError("PROPERTY_FAILURE", f"{_label(key)} 是不可压溶液，没有饱和（汽液）状态")
    pair, order = _INPUTS[inputs]
    try:
        state = _abstract_state(key)
        state.update(pair, *order(first, second))
        phase = _phase_of(key, state)
        quality = float(state.Q()) if phase == _TWO_PHASE else None
        # Strictly inside the dome there is no single viscosity, conductivity, cp or cv;
        # CoolProp would return one-sided values, so they are reported as missing. On the
        # saturation lines (Q = 0 or 1) they exist and are read when CoolProp provides them.
        inside_dome = quality is not None and 0.0 < quality < 1.0
        on_line = quality is not None and not inside_dome

        def transport(read):
            if inside_dome:
                return None
            return _optional(read) if on_line else float(read())

        values = {
            "pressure_pa": first if inputs != "TQ" else float(state.p()),
            "temperature_k": second if inputs == "PT" else first if inputs == "TQ" else float(state.T()),
            "enthalpy_j_kg": second if inputs == "PH" else float(state.hmass()),
            "density_kg_m3": float(state.rhomass()),
            "viscosity_pa_s": transport(state.viscosity),
            "specific_heat_j_kg_k": transport(state.cpmass),
            "thermal_conductivity_w_m_k": transport(state.conductivity),
            "entropy_j_kg_k": second if inputs == "PS" else _optional(state.smass),
            "internal_energy_j_kg": _optional(state.umass),
            "cv_j_kg_k": None if inside_dome else _optional(state.cvmass),
            "speed_of_sound_m_s": None if inside_dome else _optional(state.speed_sound),
        }
    except Exception as exc:
        if inputs == "PH":
            raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法从压力/焓计算状态：{exc}") from exc
        raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法计算 {_label(key)} 的状态：{exc}") from exc
    numbers = [value for value in values.values() if value is not None] + ([quality] if quality is not None else [])
    if not all(math.isfinite(value) for value in numbers):
        raise PropertyError("PROPERTY_FAILURE", "CoolProp 返回了非有限物性值")
    return FluidState(phase=phase, quality=quality, **values)


def _check_phase(policy: str, state: FluidState) -> None:
    phase = state.phase
    if policy == "liquid" and ("gas" in phase or phase == _TWO_PHASE):
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相液体约束")
    if policy == "gas" and ("liquid" in phase or phase == _TWO_PHASE):
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相气体约束")
    if policy == "single_phase" and phase == _TWO_PHASE:
        raise PropertyError("PHASE_UNSUPPORTED", f"状态为 {phase}，不满足单相约束")


def _parse_fluid(config: FluidConfig) -> FluidKey:
    """'Water' / 'HEOS::R134a' / 'IF97::Water' / 'INCOMP::MEG[0.3]' -> (backend, name, mass fractions)."""
    if config.composition:
        # Arbitrary component fractions need a mixture setup (mole fractions, fragile
        # two-phase flashes). Keep this explicit instead of silently ignoring them.
        raise PropertyError("COMPOSITION_UNSUPPORTED", "首版 CoolProp 适配器仅接受单一工质名称；组分混合物接口已预留")
    text = config.fluid.strip()
    backend, name = ("HEOS", text)
    if "::" in text:
        prefix, name = text.split("::", 1)
        backend = prefix.strip().upper()
        if backend in _LICENSED:
            raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", _LICENSED[backend])
        if backend not in _BACKENDS:
            raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {prefix} 尚未启用；可用 {'、'.join(_BACKENDS)}")
    name = name.strip()
    if "&" in name:
        raise PropertyError("COMPOSITION_UNSUPPORTED", f"{text}：HEOS 混合物尚未接入；只有 INCOMP 溶液可以写质量分数")
    fractions: tuple[float, ...] = ()
    if "[" in name:
        if not name.endswith("]") or name.count("[") != 1:
            raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的质量分数写法应为 名称[0.3]")
        name, raw = name[:-1].split("[", 1)
        name = name.strip()
        try:
            fractions = tuple(float(part) for part in raw.split(","))
        except ValueError as exc:
            raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的质量分数不是数值") from exc
        if not all(math.isfinite(x) and 0.0 < x < 1.0 for x in fractions):
            raise PropertyError("PROPERTY_RANGE", f"工质 {text} 的质量分数必须在 (0, 1) 内")
    if fractions and backend != "INCOMP":
        raise PropertyError("COMPOSITION_UNSUPPORTED", f"{text}：只有 INCOMP 溶液可以写质量分数；HEOS 混合物尚未接入")
    if not name:
        raise PropertyError("FLUID_UNKNOWN", "工质名称为空")
    return backend, name, fractions


def _freezing_point(key: FluidKey, state: AbstractState, t_min: float, t_max: float) -> float:
    """INCOMP solutions reject temperatures below their concentration-dependent freezing point
    without exposing it; locate it by bisection at atmospheric pressure."""
    last_error: list[str] = []

    def accepts(temperature):
        try:
            state.update(CP.PT_INPUTS, 101325.0, temperature)
            return True
        except Exception as exc:
            last_error[:] = [str(exc)]
            return False
    if accepts(t_min):
        return t_min
    if not accepts(t_max):
        # Usually a mass fraction outside the correlation's range; CoolProp's message says which.
        reason = last_error[0] if last_error else ''
        raise PropertyError("PROPERTY_RANGE", f"{_label(key)} 在其温度范围内没有有效状态，请检查质量分数（CoolProp：{reason}）")
    low, high = t_min, t_max
    for _ in range(60):
        middle = (low + high) / 2
        low, high = (low, middle) if accepts(middle) else (middle, high)
        if high - low < 1e-7:
            break
    return high


@lru_cache(maxsize=256)
def _limits(key: FluidKey) -> tuple[float, float, float | None]:
    state = _abstract_state(key)
    try:
        t_min, t_max = float(state.Tmin()), float(state.Tmax())
        if key[0] == "INCOMP":
            # A water-glycol mixture freezes well above the correlation's Tmin.
            return _freezing_point(key, state, t_min, t_max), t_max, None
        return t_min, t_max, _optional(state.pmax)
    except PropertyError:
        raise
    except Exception as exc:
        raise PropertyError("PROPERTY_FAILURE", f"无法读取 {_label(key)} 的适用范围：{exc}") from exc


def _finite(*values: float, message: str = "物性输入必须是有限数") -> None:
    if not all(math.isfinite(value) for value in values):
        raise PropertyError("PROPERTY_RANGE", message)


def humid_air(temperature: float, pressure: float, relative_humidity: float) -> dict[str, float]:
    """Moist-air psychrometrics (CoolProp HAPropsSI) for module code; not part of the network solve.

    Returns humidity ratio (kg water / kg dry air), dew point, wet bulb (K) and enthalpy per kg dry air.
    """
    temperature, pressure, relative_humidity = float(temperature), float(pressure), float(relative_humidity)
    _finite(temperature, pressure, relative_humidity)
    if temperature <= 0 or pressure <= 0 or not 0.0 < relative_humidity <= 1.0:
        raise PropertyError("PROPERTY_RANGE", "湿空气输入要求温度、压力为正，相对湿度在 (0, 1] 内")
    inputs = ("T", temperature, "P", pressure, "R", relative_humidity)
    try:
        return {
            "humidity_ratio_kg_kg": float(CP.HAPropsSI("W", *inputs)),
            "dew_point_k": float(CP.HAPropsSI("D", *inputs)),
            "wet_bulb_k": float(CP.HAPropsSI("B", *inputs)),
            "enthalpy_j_kg_dry_air": float(CP.HAPropsSI("H", *inputs)),
            "relative_humidity": relative_humidity,
        }
    except Exception as exc:
        raise PropertyError("PROPERTY_FAILURE", f"CoolProp 无法计算湿空气状态：{exc}") from exc


class CoolPropPropertyService:
    """CoolProp adapter used by the solver and by module contexts (`ctx.fluid`).

    The service deliberately exposes a small stable surface. Modules do not
    import CoolProp directly, so a REFPROP or project-specific backend can be
    added later without changing module code.
    """

    backend = "coolprop"

    def __init__(self, config: FluidConfig):
        if config.backend != "coolprop":
            raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {config.backend} 尚未启用")
        self.config = config
        self.key = _parse_fluid(config)
        self.fluid = config.fluid
        self.phase_policy = config.phase_policy

    def _result(self, state: FluidState, check_phase: bool = True) -> FluidState:
        if check_phase:
            _check_phase(self.phase_policy, state)
        # The flash cache is shared; hand out a copy so callers cannot alter it.
        return state.model_copy(update={"composition": {self.fluid: 1.0}})

    def state_pt(self, pressure: float, temperature: float) -> FluidState:
        pressure, temperature = float(pressure), float(temperature)
        _finite(pressure, temperature)
        if pressure <= 0 or temperature <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力和温度必须为正数")
        return self._result(_flash(self.key, "PT", pressure, temperature))

    def state_ph(self, pressure: float, enthalpy: float) -> FluidState:
        pressure, enthalpy = float(pressure), float(enthalpy)
        _finite(pressure, enthalpy)
        if pressure <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数")
        return self._result(_flash(self.key, "PH", pressure, enthalpy))

    def state_ps(self, pressure: float, entropy: float) -> FluidState:
        """State from pressure and specific entropy, e.g. an isentropic compressor outlet."""
        pressure, entropy = float(pressure), float(entropy)
        _finite(pressure, entropy)
        if pressure <= 0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数")
        return self._result(_flash(self.key, "PS", pressure, entropy))

    # Saturation queries are explicit two-phase requests, so the phase policy does not apply.
    def state_pq(self, pressure: float, quality: float) -> FluidState:
        pressure, quality = float(pressure), float(quality)
        _finite(pressure, quality)
        if pressure <= 0 or not 0.0 <= quality <= 1.0:
            raise PropertyError("PROPERTY_RANGE", "压力必须为正数，干度在 [0, 1] 内")
        return self._result(_flash(self.key, "PQ", pressure, quality), check_phase=False)

    def state_tq(self, temperature: float, quality: float) -> FluidState:
        temperature, quality = float(temperature), float(quality)
        _finite(temperature, quality)
        if temperature <= 0 or not 0.0 <= quality <= 1.0:
            raise PropertyError("PROPERTY_RANGE", "温度必须为正数，干度在 [0, 1] 内")
        return self._result(_flash(self.key, "TQ", temperature, quality), check_phase=False)

    def saturation_t(self, pressure: float) -> float:
        """Saturation temperature (K) at the given pressure (pure fluids)."""
        return self.state_pq(pressure, 0.0).temperature_k

    def saturation_p(self, temperature: float) -> float:
        """Saturation pressure (Pa) at the given temperature (pure fluids)."""
        return self.state_tq(temperature, 0.0).pressure_pa

    def limits(self) -> dict[str, float | None]:
        """Validity range of this fluid: t_min_k (INCOMP: freezing point), t_max_k, p_max_pa (None if unknown)."""
        t_min, t_max, p_max = _limits(self.key)
        return {"t_min_k": t_min, "t_max_k": t_max, "p_max_pa": p_max}

    def humid_air(self, temperature: float, pressure: float, relative_humidity: float) -> dict[str, float]:
        return humid_air(temperature, pressure, relative_humidity)


_services: dict[tuple[str, FluidKey, str], CoolPropPropertyService] = {}
_services_lock = threading.Lock()


def is_pure_water(config: FluidConfig) -> bool:
    """True for every spelling of pure water (Water, water, HEOS::Water, IF97::Water).

    The hydraulics use fixed reference water properties for these, so all spellings must
    give identical results. An unparseable fluid string is simply "not water" here.
    """
    try:
        backend, name, fractions = _parse_fluid(config)
    except PropertyError:
        return False
    return backend in ("HEOS", "IF97") and name.lower() == "water" and not fractions


def property_service(config: FluidConfig) -> CoolPropPropertyService:
    # Same check order as before: backend, then composition / fluid string.
    if config.backend != "coolprop":
        raise PropertyError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {config.backend} 尚未启用")
    key = (config.backend, _parse_fluid(config), config.phase_policy)
    with _services_lock:
        service = _services.get(key)
        if service is None:
            service = _services[key] = CoolPropPropertyService(config)
    return service
