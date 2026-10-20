"""A0 independent cold-storage inputs and thermodynamic reference (no engine imports)."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import CoolProp
from CoolProp.CoolProp import PropsSI


CASE_ROOT = Path(__file__).resolve().parents[1]
INPUT_ROOT = CASE_ROOT / "single-room-minus18"
INPUT_NAMES = ("parameters.json", "scenarios.json", "sources.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def finite_number(value, label, positive=False, nonnegative=False):
    require(not isinstance(value, bool) and isinstance(value, (int, float)), f"{label}: expected number")
    require(math.isfinite(value), f"{label}: expected finite number")
    if positive:
        require(value > 0, f"{label}: must be positive")
    if nonnegative:
        require(value >= 0, f"{label}: must be nonnegative")
    return value


def validate_inputs(parameters, scenario_data, sources):
    for name, data in zip(INPUT_NAMES, (parameters, scenario_data, sources)):
        require(data["schema_version"] == 1, f"{name}: unsupported schema")
        require(data["case_id"] == "single-room-minus18-v1", f"{name}: case mismatch")
    require(parameters["unit_system"] == "SI", "parameters must use SI")
    room, goods, machine = (parameters[key] for key in ("room", "goods", "refrigeration"))
    for group_name, group in (("room", room), ("goods", goods), ("refrigeration", machine)):
        for key, value in group.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                finite_number(value, f"{group_name}.{key}", positive=key != "lighting_power_w")
    goods_range = goods["valid_temperature_range_k"]
    require(len(goods_range) == 2 and 0 < goods_range[0] < goods_range[1], "invalid frozen goods range")
    require(goods_range[0] <= goods["initial_temperature_k"] <= goods_range[1], "initial goods outside range")
    require(goods_range[0] <= room["setpoint_temperature_k"] <= goods_range[1], "setpoint outside goods range")
    require(goods["ua_mass_scaling"] == "proportional_to_total_mass", "unsupported goods UA rule")
    for key in ("isentropic_efficiency", "volumetric_efficiency", "motor_efficiency"):
        require(0 < machine[key] <= 1, f"invalid {key}")
    require(0 < machine["capacity_ratio_minimum"] <= machine["nominal_capacity_ratio"]
            <= machine["capacity_ratio_maximum"] <= 1, "invalid capacity range")
    require(machine["rated_condensing_temperature_k"] > room["ambient_temperature_k"], "no condensing approach")
    require(machine["rated_evaporating_temperature_k"] < room["setpoint_temperature_k"], "no evaporating approach")
    require(machine["motor_loss_destination"] == "external_environment", "unsupported motor heat allocation")
    require(machine["superheat_location"] == "evaporator", "unsupported superheat allocation")
    control, defrost = parameters["control"], parameters["defrost"]
    require(control["stop_temperature_k"] < room["setpoint_temperature_k"] < control["start_temperature_k"],
            "invalid thermostat hysteresis")
    for key in ("sample_s", "minimum_on_s", "minimum_off_s"):
        finite_number(control[key], f"control.{key}", positive=True)
    for key in ("heater_power_w", "heating_duration_s", "drip_wait_s"):
        finite_number(defrost[key], f"defrost.{key}", positive=True)
    require(0 <= defrost["room_heat_fraction"] <= 1, "invalid defrost heat fraction")
    for key in ("publish_interval_s", "internal_step_maximum_s"):
        finite_number(parameters["numerics"][key], f"numerics.{key}", positive=True)

    expected_ids = {f"A-S{i:02d}" for i in range(1, 8)}
    scenarios = scenario_data["scenarios"]
    require(len(scenarios) == 7 and {item["id"] for item in scenarios} == expected_ids,
            "expected exactly A-S01 through A-S07")
    summaries = []
    for scenario in scenarios:
        duration = finite_number(scenario["duration_s"], scenario["id"] + ".duration_s", positive=True)
        require(scenario["control_modes"] and set(scenario["control_modes"]) <= {"on_off", "variable_capacity"},
                "unknown control mode")
        for key, value in scenario["overrides"].items():
            require(key == "refrigeration.rated_cooling_power_w", f"unvalidated override: {key}")
            finite_number(value, key, positive=True)
        events = scenario["events"]
        require(len({item["id"] for item in events}) == len(events), "duplicate event ID")
        prior_time, prior_defrost_end = -1, -1
        for event in events:
            label = scenario["id"] + "." + event["id"]
            time_s = finite_number(event["time_s"], label + ".time_s", nonnegative=True)
            require(prior_time <= time_s < duration, label + ": events must be sorted and within run")
            prior_time = time_s
            event_type = event["type"]
            if event_type == "door_heat":
                seconds = finite_number(event["duration_s"], label + ".duration_s", positive=True)
                finite_number(event["heat_w"], label + ".heat_w", nonnegative=True)
                require(time_s + seconds <= duration, label + ": event extends beyond run")
            elif event_type == "goods_addition":
                finite_number(event["mass_kg"], label + ".mass_kg", positive=True)
                temperature = finite_number(event["temperature_k"], label + ".temperature_k", positive=True)
                require(goods_range[0] <= temperature <= goods_range[1], label + ": goods not in frozen range")
            elif event_type == "ambient_temperature":
                finite_number(event["temperature_k"], label + ".temperature_k", positive=True)
            elif event_type == "electric_defrost":
                require(time_s >= prior_defrost_end, label + ": overlapping defrost")
                prior_defrost_end = time_s + defrost["heating_duration_s"] + defrost["drip_wait_s"]
                require(prior_defrost_end <= duration, label + ": recovery extends beyond run")
            else:
                raise ValueError(label + ": unknown event type " + event_type)
        summaries.append({"id": scenario["id"], "name": scenario["name"], "duration_s": duration,
                          "event_count": len(events), "control_modes": scenario["control_modes"]})
    source_ids = [source["id"] for source in sources["sources"]]
    require(len(source_ids) == len(set(source_ids)), "duplicate source ID")
    require(not sources["site_data_available"] and not sources["manufacturer_data_available"],
            "reference v1 only accepts declared demonstration assumptions")
    return summaries


def thermodynamic_state(fluid, pressure_pa, enthalpy_j_kg):
    quality = float(PropsSI("Q", "P", pressure_pa, "Hmass", enthalpy_j_kg, fluid))
    return {
        "pressure_pa": pressure_pa,
        "enthalpy_j_kg": enthalpy_j_kg,
        "temperature_k": float(PropsSI("T", "P", pressure_pa, "Hmass", enthalpy_j_kg, fluid)),
        "entropy_j_kg_k": float(PropsSI("Smass", "P", pressure_pa, "Hmass", enthalpy_j_kg, fluid)),
        "density_kg_m3": float(PropsSI("Dmass", "P", pressure_pa, "Hmass", enthalpy_j_kg, fluid)),
        "quality": quality if 0 <= quality <= 1 else None,
    }


def cycle_point(machine, evaporating_k, condensing_k, capacity_ratio, displacement_m3_s=None):
    limits = machine["model_limits"]
    for key, temperature in (("evaporating_temperature_k", evaporating_k), ("condensing_temperature_k", condensing_k)):
        low, high = limits[key]
        require(low <= temperature <= high, f"{key} outside declared limits")
    require(machine["capacity_ratio_minimum"] <= capacity_ratio <= machine["capacity_ratio_maximum"],
            "capacity outside declared limits")
    fluid = machine["fluid"]
    evaporating_pa = float(PropsSI("P", "T", evaporating_k, "Q", 1, fluid))
    condensing_pa = float(PropsSI("P", "T", condensing_k, "Q", 0, fluid))
    pressure_ratio = condensing_pa / evaporating_pa
    require(1 < pressure_ratio <= limits["pressure_ratio_maximum"], "pressure ratio outside declared limits")
    h1 = float(PropsSI("Hmass", "P", evaporating_pa, "T", evaporating_k + machine["superheat_k"], fluid))
    s1 = float(PropsSI("Smass", "P", evaporating_pa, "T", evaporating_k + machine["superheat_k"], fluid))
    rho1 = float(PropsSI("Dmass", "P", evaporating_pa, "T", evaporating_k + machine["superheat_k"], fluid))
    h2s = float(PropsSI("Hmass", "P", condensing_pa, "Smass", s1, fluid))
    h2 = h1 + (h2s - h1) / machine["isentropic_efficiency"]
    h3 = float(PropsSI("Hmass", "P", condensing_pa, "T", condensing_k - machine["subcooling_k"], fluid))
    h4 = h3
    require(h1 > h4 and h2 > h1, "cycle has no positive cooling/work")
    if displacement_m3_s is None:
        require(capacity_ratio == machine["nominal_capacity_ratio"], "derive displacement only at rated capacity")
        rated_mass_flow = machine["rated_cooling_power_w"] / (h1 - h4)
        displacement_m3_s = rated_mass_flow / (rho1 * machine["volumetric_efficiency"] * capacity_ratio)
    mass_flow = displacement_m3_s * rho1 * machine["volumetric_efficiency"] * capacity_ratio
    cooling = mass_flow * (h1 - h4)
    shaft = mass_flow * (h2 - h1)
    rejection = mass_flow * (h2 - h3)
    electric = shaft / machine["motor_efficiency"]
    total_electric = electric + machine["evaporator_fan_power_w"] + machine["condenser_fan_power_w"]
    states = {str(index): thermodynamic_state(fluid, pressure, enthalpy) for index, pressure, enthalpy in (
        (1, evaporating_pa, h1), (2, condensing_pa, h2), (3, condensing_pa, h3), (4, evaporating_pa, h4))}
    require(states["2"]["temperature_k"] <= limits["discharge_temperature_maximum_k"],
            "discharge temperature outside declared limits")
    require(states["4"]["quality"] is not None, "throttling outlet must be two-phase in reference case")
    return {"evaporating_temperature_k": evaporating_k, "condensing_temperature_k": condensing_k,
            "capacity_ratio": capacity_ratio, "displacement_m3_s": displacement_m3_s,
            "mass_flow_kg_s": mass_flow, "pressure_ratio": pressure_ratio,
            "cooling_power_w": cooling, "shaft_power_w": shaft, "compressor_electric_power_w": electric,
            "condenser_rejection_power_w": rejection, "auxiliary_electric_power_w": total_electric - electric,
            "total_electric_power_w": total_electric, "cop_compressor_electric": cooling / electric,
            "cop_system_instantaneous": cooling / total_electric,
            "energy_residual_w": rejection - cooling - shaft,
            "isentropic_discharge_enthalpy_j_kg": h2s, "states": states}


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reference():
    inputs = [json.loads((INPUT_ROOT / name).read_text(encoding="utf-8")) for name in INPUT_NAMES]
    parameters, scenarios, sources = inputs
    summary = validate_inputs(parameters, scenarios, sources)
    room, goods, machine = (parameters[key] for key in ("room", "goods", "refrigeration"))
    wall_area = 2 * (room["length_m"] + room["width_m"]) * room["height_m"]
    floor_area = room["length_m"] * room["width_m"]
    delta_ambient = room["ambient_temperature_k"] - room["setpoint_temperature_k"]
    wall_load = wall_area * room["wall_u_w_m2_k"] * delta_ambient
    roof_load = floor_area * room["roof_u_w_m2_k"] * delta_ambient
    floor_load = floor_area * room["floor_u_w_m2_k"] * (room["ground_temperature_k"] - room["setpoint_temperature_k"])
    envelope_load = wall_load + roof_load + floor_load
    rated = cycle_point(machine, machine["rated_evaporating_temperature_k"], machine["rated_condensing_temperature_k"],
                        machine["nominal_capacity_ratio"])
    displacement = rated["displacement_m3_s"]
    points = {
        "rated": rated,
        "lower_evaporation": cycle_point(machine, 241.15, 313.15, 1.0, displacement),
        "high_condensation": cycle_point(machine, 245.15, 319.15, 1.0, displacement),
        "half_capacity": cycle_point(machine, 245.15, 313.15, 0.5, displacement),
    }
    checks = []

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("input_geometry", math.isclose(wall_area, 144) and math.isclose(floor_area, 80), "wall=144 m2, roof/floor=80 m2")
    check("envelope_load", math.isclose(envelope_load, 2864, abs_tol=1e-8), f"calculated {envelope_load:.6f} W")
    check("rated_cooling", math.isclose(rated["cooling_power_w"], machine["rated_cooling_power_w"], rel_tol=1e-12),
          "displacement derived once from declared rating")
    for name, point in points.items():
        state1, state2, state3, state4 = (point["states"][str(index)] for index in range(1, 5))
        scale = max(point["condenser_rejection_power_w"], point["cooling_power_w"], point["shaft_power_w"])
        check(name + ".energy_balance", abs(point["energy_residual_w"]) <= max(1.0, 1e-6 * scale),
              f"residual {point['energy_residual_w']:.12g} W")
        check(name + ".positive_powers", all(point[key] > 0 for key in ("mass_flow_kg_s", "cooling_power_w", "shaft_power_w")),
              "positive mass flow, cooling and compression work")
        check(name + ".compression_entropy", state2["entropy_j_kg_k"] > state1["entropy_j_kg_k"],
              "irreversible adiabatic compression increases entropy")
        check(name + ".throttle", state4["enthalpy_j_kg"] == state3["enthalpy_j_kg"] and 0 < state4["quality"] < 1,
              "isenthalpic expansion with wet outlet")
        check(name + ".carnot_bound", 0 < point["cooling_power_w"] / point["shaft_power_w"]
              < point["evaporating_temperature_k"] / (point["condensing_temperature_k"] - point["evaporating_temperature_k"]),
              "shaft-based cycle COP below saturation-temperature Carnot COP")
        check(name + ".fixed_displacement", point["displacement_m3_s"] == displacement,
              "all non-rated points retain rated displacement")
    check("half_capacity_scaling", math.isclose(points["half_capacity"]["cooling_power_w"],
          rated["cooling_power_w"] / 2, rel_tol=1e-12), "same temperatures/efficiencies, half mass flow and cooling")
    check("high_condensation_cop", points["high_condensation"]["cop_compressor_electric"] < rated["cop_compressor_electric"],
          "higher condensing temperature reduces COP at fixed evaporation")
    s07 = next(item for item in scenarios["scenarios"] if item["id"] == "A-S07")
    check("insufficient_capacity_design", s07["overrides"]["refrigeration.rated_cooling_power_w"] < envelope_load,
          "S07 rated cooling below target envelope load alone")
    require(all(item["passed"] for item in checks), "failed checks: " + ", ".join(item["name"] for item in checks if not item["passed"]))
    return {"schema_version": 1, "case_id": parameters["case_id"],
            "scope": "A0 independent inputs and fixed-boundary cycle points; no dynamic room/product validation",
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "coolprop_version": CoolProp.__version__},
            "input_sha256": {name: fingerprint(INPUT_ROOT / name) for name in INPUT_NAMES},
            "reference_script_sha256": fingerprint(Path(__file__)),
            "geometry": {"volume_m3": floor_area * room["height_m"], "wall_area_m2": wall_area,
                         "roof_area_m2": floor_area, "floor_area_m2": floor_area,
                         "wall_heat_w": wall_load, "roof_heat_w": roof_load, "floor_heat_w": floor_load,
                         "target_envelope_heat_w": envelope_load,
                         "goods_heat_capacity_j_k": goods["mass_kg"] * goods["specific_heat_j_kg_k"]},
            "design": {"fixed_displacement_m3_s": displacement,
                       "condenser_ua_w_k": rated["condenser_rejection_power_w"]
                       / (machine["rated_condensing_temperature_k"] - room["ambient_temperature_k"])},
            "workpoints": points, "scenarios": summary, "checks": checks}


def compare_reference(expected, actual, path="root"):
    if isinstance(actual, dict):
        require(isinstance(expected, dict) and set(expected) == set(actual), path + ": keys differ")
        for key, value in actual.items():
            if path == "root.environment" and key in {"platform", "python"}:
                continue
            compare_reference(expected[key], value, path + "." + key)
    elif isinstance(actual, list):
        require(isinstance(expected, list) and len(expected) == len(actual), path + ": lengths differ")
        for index, value in enumerate(actual):
            compare_reference(expected[index], value, f"{path}[{index}]")
    elif isinstance(actual, float):
        require(isinstance(expected, (int, float)) and math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-6),
                path + ": numerical reference changed")
    else:
        require(expected == actual, path + ": reference changed")


def report_text(result):
    rows = []
    for name, point in result["workpoints"].items():
        rows.append(f"| {name} | {point['evaporating_temperature_k'] - 273.15:.1f} | "
                    f"{point['condensing_temperature_k'] - 273.15:.1f} | {point['cooling_power_w'] / 1000:.4f} | "
                    f"{point['compressor_electric_power_w'] / 1000:.4f} | {point['cop_compressor_electric']:.4f} |")
    hashes = "\n".join(f"- `{name}`：`{digest}`" for name, digest in result["input_sha256"].items())
    return (
        "# A0 独立参考验证\n\n"
        f"生成时间：{datetime.now(timezone.utc).isoformat()}。\n\n"
        "结果：七组工况输入校验通过；四个循环工作点通过质量流量、状态与热力检查。\n\n"
        f"检查：**{len(result['checks'])} 项通过**。CoolProp {result['environment']['coolprop_version']}，"
        f"Python {result['environment']['python']}。\n\n"
        "直接调用 CoolProp PropsSI，根据等熵效率、节流等焓与焓差计算，未导入引擎求解器。"
        "本报告验证声明假设下的独立基准，未验证真实厂家性能、动态库温或工作台流程。\n\n"
        "| 工作点 | 蒸发 °C | 冷凝 °C | 制冷 kW | 压缩机电功率 kW | 机组 COP |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n\n"
        f"围护漏热：**{result['geometry']['target_envelope_heat_w']:.0f} W**。"
        f"额定反算固定排量：**{result['design']['fixed_displacement_m3_s'] * 3600:.4f} m³/h**；"
        f"设计冷凝器 UA：**{result['design']['condenser_ua_w_k']:.4f} W/K**。\n\n"
        "非额定工作点使用相同排量；高冷凝工况不能替代库房环境扰动的动态验证。\n\n"
        "输入哈希：\n\n" + hashes + "\n\n"
        f"脚本 SHA-256：`{result['reference_script_sha256']}`。\n\n"
        "详细状态、残差、环境与全部检查见 [workpoints.json](workpoints.json)。\n\n"
        "下一步：设计热连接、状态/事件合同与会话入口，再完成库房 + 理想恒容量冷源的 A1 产品流程。\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare current inputs/calculations with stored reference")
    mode.add_argument("--output", type=Path, help="write evidence to a new directory (existing paths refused)")
    args = parser.parse_args()
    try:
        result = build_reference()
        output = args.output if args.output is not None else INPUT_ROOT / "references"
        if args.check:
            expected = json.loads((output / "workpoints.json").read_text(encoding="utf-8"))
            compare_reference(expected, result)
        else:
            output.mkdir(parents=True, exist_ok=False)
            (output / "workpoints.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                                   encoding="utf-8")
            (output / "VALIDATION.md").write_text(report_text(result), encoding="utf-8")
        print(f"A0 reference {'matches' if args.check else 'written'}: {len(result['checks'])} checks, "
              f"7 scenarios, envelope {result['geometry']['target_envelope_heat_w']:.0f} W")
        for name, point in result["workpoints"].items():
            print(f"  {name}: cooling={point['cooling_power_w'] / 1000:.4f} kW, "
                  f"compressor electricity={point['compressor_electric_power_w'] / 1000:.4f} kW, "
                  f"COP={point['cop_compressor_electric']:.4f}")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"A0 reference failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
