from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Protocol

from CoolProp.CoolProp import PropsSI

from .errors import ModelError
from .models import MediumDefinition


@dataclass(frozen=True)
class FluidState:
    pressure_pa: float
    temperature_k: float
    enthalpy_j_kg: float
    density_kg_m3: float
    viscosity_pa_s: float
    cp_j_kg_k: float
    conductivity_w_m_k: float
    phase: str = "liquid"
    mass_fractions: tuple[float, ...] = (1.0,)
    quality: float | None = None

    def to_dict(self):
        return asdict(self)


class PropertyProvider(Protocol):
    capabilities: frozenset[str]
    def state_pt(self, pressure: float, temperature: float) -> FluidState: ...
    def state_ph(self, pressure: float, enthalpy: float) -> FluidState: ...


class IF97Water:
    capabilities = frozenset({"liquid", "pt", "ph", "transport", "saturation"})

    def __init__(self, medium: MediumDefinition):
        self.definition = medium
        if (medium.kind != "water" or medium.components != ["Water"]
                or medium.mass_fractions != [1.0] or medium.phase_policy != "liquid"
                or medium.backend_fluid != "IF97::Water"):
            raise ModelError("MEDIUM_UNSUPPORTED", "IF97 适配器仅支持单相纯液态水")
        self.fingerprint = hashlib.sha256(
            medium.model_dump_json().encode("utf-8")
        ).hexdigest()

    def saturation_pressure(self, temperature):
        try:
            return float(PropsSI("P", "T", temperature, "Q", 0, "IF97::Water"))
        except Exception as exc:
            raise ModelError("PROPERTY_RANGE", f"水的温度超出液态适用范围：{temperature:.4g} K") from exc

    @lru_cache(maxsize=32768)
    def state_pt(self, pressure: float, temperature: float):
        if not math.isfinite(pressure) or not math.isfinite(temperature):
            raise ModelError("PROPERTY_RANGE", "物性输入必须是有限数")
        if not 273.16 <= temperature < 647.096 or not 611.657 < pressure <= 100e6:
            raise ModelError("PROPERTY_RANGE", f"状态超出 IF97 液态水范围：{pressure:.5g} Pa，{temperature:.5g} K")
        psat = self.saturation_pressure(temperature)
        if pressure <= psat + 1:
            raise ModelError("PHASE_UNSUPPORTED", f"状态不在单相液态区：压力 {pressure:.4g} Pa，饱和压力 {psat:.4g} Pa")
        try:
            values = [float(PropsSI(key, "P", pressure, "T", temperature, "IF97::Water"))
                      for key in ("Hmass", "Dmass", "VISCOSITY", "Cpmass", "CONDUCTIVITY")]
        except Exception as exc:
            raise ModelError("PROPERTY_FAILURE", str(exc)) from exc
        if not all(math.isfinite(v) for v in values):
            raise ModelError("PROPERTY_FAILURE", "物性后端返回了非有限数")
        return FluidState(pressure, temperature, *values)

    @lru_cache(maxsize=32768)
    def state_ph(self, pressure: float, enthalpy: float):
        try:
            temperature = float(PropsSI("T", "P", pressure, "Hmass", enthalpy, "IF97::Water"))
            # IF97's backward T(p,h) correlation is approximate. Refine against
            # the forward equation to preserve enthalpy and round-trip accuracy.
            for _ in range(8):
                actual_h = float(PropsSI("Hmass", "P", pressure, "T", temperature, "IF97::Water"))
                cp = float(PropsSI("Cpmass", "P", pressure, "T", temperature, "IF97::Water"))
                change = (actual_h - enthalpy) / cp
                temperature -= change
                if abs(change) < 1e-10:
                    break
        except Exception as exc:
            raise ModelError("PROPERTY_RANGE", f"压力/焓状态无法求得液态物性：{exc}") from exc
        return self.state_pt(pressure, temperature)


PROVIDERS: dict[str, type] = {"coolprop_if97": IF97Water}
FLOW_MODELS = {"quasi_incompressible_liquid": frozenset({"water"})}


class MediumRegistry:
    def __init__(self, definitions: list[MediumDefinition]):
        self.definitions = {m.id: m for m in definitions}
        self._providers: dict[str, PropertyProvider] = {}

    def get(self, medium_id: str) -> PropertyProvider:
        if medium_id in self._providers:
            return self._providers[medium_id]
        medium = self.definitions.get(medium_id)
        if medium is None:
            raise ModelError("MEDIUM_MISSING", f"介质 {medium_id} 不存在")
        if medium.kind not in FLOW_MODELS["quasi_incompressible_liquid"]:
            raise ModelError("FLOW_MODEL_UNSUPPORTED", f"{medium.name} 已保留定义，但首版尚未实现其网络求解模型")
        factory = PROVIDERS.get(medium.backend)
        if factory is None:
            raise ModelError("PROPERTY_BACKEND_UNSUPPORTED", f"物性后端 {medium.backend} 尚未启用")
        provider = factory(medium)
        if not {"liquid", "pt", "ph", "transport"}.issubset(provider.capabilities):
            raise ModelError("PROPERTY_CAPABILITY", "物性提供器不满足液态网络模型的能力要求")
        self._providers[medium_id] = provider
        return provider


def media_catalog():
    return [
        {"kind": "water", "name": "液态水", "enabled": True,
         "backend": "coolprop_if97", "model": "quasi_incompressible_liquid",
         "description": "单相液态水 · IF97 · 水力与热力"},
        *[{"kind": key, "name": name, "enabled": False, "backend": None,
           "model": None, "description": note}
          for key, name, note in [
              ("air", "空气", "预留物性与低压气流模型"),
              ("natural_gas", "燃气", "预留组分与可压缩流动模型"),
              ("steam", "蒸汽", "预留气相与相变模型"),
              ("refrigerant", "制冷剂", "预留工质、相态与设备适配"),
              ("mixture", "混合物", "预留变长组分与质量分数"),
          ]],
    ]
