"""One source of truth for the editor, model validator, and runtime controls."""
from __future__ import annotations

import math
from copy import deepcopy

from .errors import ModelError


def number(key, label, default, unit="", minimum=None, maximum=None, runtime=False,
           positive=False):
    return {"key": key, "label": label, "default": default, "unit": unit,
            "kind": "number", "min": minimum, "max": maximum,
            "positive": positive, "runtime": runtime}


def text(key, label, default="", runtime=False):
    return {"key": key, "label": label, "default": default, "kind": "text",
            "runtime": runtime}


def boolean(key, label, default=False, runtime=False):
    return {"key": key, "label": label, "default": default, "kind": "boolean",
            "runtime": runtime}


def port(name, label, group="fluid", side="left", required=True):
    return {"id": name, "label": label, "group": group, "side": side,
            "required": required}


TWO_PORTS = [port("in", "入口 / 参考正向", side="left"),
             port("out", "出口 / 参考正向", side="right")]
DIAMETER = number("diameter_m", "实际内径", 0.05, "m", positive=True)
LOSS = number("loss_coefficient", "局部阻力系数 K", 1.0, "", minimum=0)
TEMPERATURE = number("temperature_k", "初始 / 边界温度", 293.15, "K", positive=True)
BOUNDARY_PORTS = [port("p1", "端口 1", side="left", required=False),
                  port("p2", "端口 2", side="right", required=False)]


def spec(name, category, icon, ports, parameters, description, **extra):
    return {"name": name, "category": category, "icon": icon, "ports": ports,
            "parameters": parameters, "description": description, "version": 1,
            "supported_media": ["water"], **extra}


CATALOG = {
    "pressure": spec("定压水源", "边界与连接", "reservoir", BOUNDARY_PORTS, [
        number("pressure_pa", "绝对压力", 301325, "Pa", positive=True), TEMPERATURE,
        boolean("temperature_fixed", "恒温边界", True),
    ], "提供压力参考；恒温时作为理想热库，边界热量单独计入收支。", boundary=True),
    "flow_boundary": spec("指定流量", "边界与连接", "flow", [port("p", "流体端口", side="right")], [
        number("mass_flow_kg_s", "向网络注入流量（负值为取水）", 0.2, "kg/s", runtime=True),
        TEMPERATURE,
    ], "给定质量流量和注入温度，仍需为连通区域设置压力参考。", boundary=True),
    "demand": spec("用水需求", "边界与连接", "demand", [port("p", "取水端口")], [
        number("demand_kg_s", "用水量", 0.2, "kg/s", minimum=0, runtime=True),
    ], "从网络取出给定质量流量。", boundary=True),
    "junction": spec("连接节点", "边界与连接", "junction", [
        port("p1", "端口 1", side="left", required=False),
        port("p2", "端口 2", side="right", required=False),
        port("p3", "端口 3", side="bottom", required=False),
        port("p4", "端口 4", side="top", required=False),
    ], [], "所有端口等压，按质量流量和比焓混合。"),
    "pipe": spec("管道", "管路", "pipe", TWO_PORTS, [
        number("length_m", "长度", 20, "m", positive=True), DIAMETER,
        number("roughness_m", "绝对粗糙度", 0.000045, "m", minimum=0),
        number("loss_coefficient", "附加局部阻力 K", 0, "", minimum=0),
        number("height_change_m", "沿参考方向的高差", 0, "m"),
        number("heat_loss_ua_w_k", "整段管道散热 UA", 0, "W/K", minimum=0),
        number("ambient_temperature_k", "环境温度", 293.15, "K", positive=True),
        number("thermal_cells", "热单元数", 10, "", minimum=1, maximum=100),
        number("initial_temperature_k", "管内初始温度", 293.15, "K", positive=True),
    ], "Darcy–Weisbach 管阻、Colebrook 摩阻及有限体积热输运。"),
    "resistance": spec("局部阻力", "管路", "resistance", TWO_PORTS,
        [DIAMETER, LOSS, number("height_change_m", "高差", 0, "m")],
        "弯头、过滤器等的等效阻力。系数由用户提供。"),
    "valve": spec("调节阀", "泵与阀门", "valve", TWO_PORTS, [
        number("kv_m3_h", "全开 Kv", 16, "m³/h", positive=True),
        number("opening", "开度", 1, "", minimum=0, maximum=1, runtime=True),
        {"key": "characteristic", "label": "开度特性", "kind": "select",
         "default": "linear", "choices": ["linear", "equal_percentage"], "runtime": False},
        number("rangeability", "等百分比可调比", 50, "", minimum=1),
    ], "Kv 以水在 1 bar 压差下的 m³/h 定义；关闭时施加零流量约束。"),
    "check_valve": spec("止回阀", "泵与阀门", "check", TWO_PORTS, [DIAMETER, LOSS],
        "只允许参考方向流动，采用开启/关闭约束切换。"),
    "three_way": spec("三通调节阀", "泵与阀门", "threeway", [
        port("common", "公共口"), port("a", "A 口", side="right"),
        port("b", "B 口", side="bottom"),
    ], [number("kv_m3_h", "每通路全开 Kv", 16, "m³/h", positive=True),
        number("opening", "A 路开度（B 路为 1−A）", 0.5, "", minimum=0, maximum=1, runtime=True)],
        "两条耦合开度通路，可以分流或混流。"),
    "pump": spec("变速离心泵", "泵与阀门", "pump", TWO_PORTS, [
        number("speed_ratio", "转速比", 1, "", minimum=0, maximum=2, runtime=True),
        {"key": "head_curve", "label": "[流量 m³/h, 扬程 m] 曲线", "kind": "curve",
         "default": [[0, 20], [5, 18], [10, 12], [15, 0]], "runtime": False},
        {"key": "efficiency_curve", "label": "[流量 m³/h, 效率] 曲线", "kind": "curve",
         "default": [[0, 0.5], [5, 0.72], [10, 0.78], [15, 0.6]], "runtime": False},
        DIAMETER, number("off_loss_coefficient", "停泵通流阻力 K", 5, "", minimum=0),
    ], "单调 PCHIP 曲线与相似定律；停泵按被动阻力通流，止回阀可另行配置。"),
    "heater": spec("加热 / 冷却", "热设备", "heater", TWO_PORTS, [
        number("power_w", "热功率（负值为冷却）", 1000, "W", runtime=True),
        number("capacity_w", "最大热功率绝对值", 10000, "W", minimum=0), DIAMETER, LOSS,
    ], "按实际热功率改变比焓；无流量时不允许无热容元件持续供热。"),
    "temperature_source": spec("温度调节设备", "热设备", "thermal", TWO_PORTS, [
        number("target_temperature_k", "目标出口温度", 313.15, "K", positive=True, runtime=True),
        number("capacity_w", "最大加热 / 冷却能力", 20000, "W", minimum=0), DIAMETER, LOSS,
    ], "受容量限制的出口温度调节，报告未满足的热量需求。"),
    "heat_exchanger": spec("水—水换热器", "热设备", "exchanger", [
        port("a_in", "A 侧入口", "a", "left"), port("a_out", "A 侧出口", "a", "right"),
        port("b_in", "B 侧入口", "b", "left"), port("b_out", "B 侧出口", "b", "right"),
    ], [number("ua_w_k", "总传热能力 UA", 2000, "W/K", minimum=0), DIAMETER, LOSS],
        "逆流 ε–NTU 模型；两侧独立分配介质，仅交换热量。"),
    "tank_open": spec("开式水箱", "容积设备", "tank", BOUNDARY_PORTS, [
        number("area_m2", "截面积", 1, "m²", positive=True),
        number("capacity_m3", "总容量", 2, "m³", positive=True),
        number("initial_level_m", "初始液位", 1, "m", minimum=0),
        number("surface_pressure_pa", "表面绝对压力", 101325, "Pa", positive=True),
        TEMPERATURE, number("power_w", "外加热功率", 0, "W", runtime=True),
        number("heat_loss_ua_w_k", "散热 UA", 0, "W/K", minimum=0),
        number("ambient_temperature_k", "环境温度", 293.15, "K", positive=True),
    ], "完全混合水箱，存储质量与焓，底部端口压力由液位决定。", boundary=True),
    "tank_gas": spec("气垫蓄水罐", "容积设备", "gas_tank", BOUNDARY_PORTS, [
        number("area_m2", "截面积", 1, "m²", positive=True),
        number("capacity_m3", "总容量", 2, "m³", positive=True),
        number("initial_level_m", "初始液位", 1, "m", minimum=0),
        number("gas_pressure_pa", "初始气垫绝对压力", 201325, "Pa", positive=True),
        number("polytropic_index", "气垫多方指数", 1, "", minimum=1, maximum=1.67),
        TEMPERATURE, number("power_w", "外加热功率", 0, "W", runtime=True),
        number("heat_loss_ua_w_k", "散热 UA", 0, "W/K", minimum=0),
        number("ambient_temperature_k", "环境温度", 293.15, "K", positive=True),
    ], "水侧质量、焓积累与气垫多方关系耦合；不代表支持气体管网。", boundary=True),
    "sensor": spec("测量段", "测量与控制", "sensor", TWO_PORTS, [],
        "理想无损测量段，提供压力、温度和流量变量。"),
    "pid": spec("PID 控制器", "测量与控制", "pid", [], [
        text("measurement", "测量变量", "pipe.mass_flow_kg_s"),
        text("target_element", "受控元件 ID", "valve"),
        text("target_parameter", "受控参数", "opening"),
        number("setpoint", "目标值（SI）", 1, "", runtime=True),
        number("kp", "比例增益", 0.1), number("ki", "积分增益", 0.01, minimum=0),
        number("kd", "微分增益", 0, minimum=0),
        number("output_min", "输出下限", 0), number("output_max", "输出上限", 1),
        number("period_s", "控制周期", 0.1, "s", positive=True),
        boolean("reverse", "反作用", False), boolean("enabled", "启用", True, True),
    ], "固定仿真周期、输出限幅与条件积分抗饱和。稳态保持手动输出。", control=True),
    "timer": spec("定时 / 开关控制", "测量与控制", "timer", [], [
        text("target_element", "受控元件 ID", "valve"),
        text("target_parameter", "受控参数", "opening"),
        number("on_time_s", "开启时间", 5, "s", minimum=0),
        number("off_time_s", "关闭时间", 30, "s", minimum=0),
        number("on_value", "开启值", 1), number("off_value", "关闭值", 0),
        boolean("enabled", "启用", True, True),
    ], "在指定仿真时刻切换执行器，也可通过启用开关手动控制。", control=True),
}


VARIABLES = {
    "mass_flow_kg_s": ("质量流量", "kg/s"), "volume_flow_m3_h": ("体积流量", "m³/h"),
    "pressure_pa": ("节点绝对压力", "Pa"), "inlet_pressure_pa": ("入口绝对压力", "Pa"),
    "outlet_pressure_pa": ("出口绝对压力", "Pa"), "pressure_drop_pa": ("压差", "Pa"),
    "temperature_k": ("温度", "K"), "inlet_temperature_k": ("实际上游温度", "K"),
    "outlet_temperature_k": ("实际下游温度", "K"), "velocity_m_s": ("流速", "m/s"),
    "reynolds": ("雷诺数", ""), "friction_factor": ("Darcy 摩阻系数", ""),
    "head_m": ("泵扬程", "m"), "power_w": ("轴功率", "W"),
    "heat_w": ("实际热量", "W"), "unmet_heat_w": ("未满足热量", "W"),
    "boundary_heat_w": ("热边界输入", "W"), "level_m": ("液位", "m"),
    "mass_kg": ("存水量", "kg"), "enthalpy_j_kg": ("比焓", "J/kg"),
    "stored_energy_j": ("储存焓", "J"), "density_kg_m3": ("密度", "kg/m³"),
    "opening": ("开度", ""), "speed_ratio": ("转速比", ""),
    "output": ("控制输出", ""), "error": ("控制偏差", ""), "closed": ("关闭状态", ""),
}


def get_parameters(element):
    definition = CATALOG.get(element.type)
    if definition is None:
        raise ModelError("COMPONENT_UNSUPPORTED", f"未知元件类型：{element.type}", element.id)
    if element.version != 1:
        raise ModelError("COMPONENT_VERSION", "元件版本不受支持", element.id)
    values = {p["key"]: deepcopy(p["default"]) for p in definition["parameters"]}
    unknown = set(element.parameters) - set(values)
    if unknown:
        raise ModelError("PARAMETER_UNKNOWN", f"未知参数：{', '.join(sorted(unknown))}", element.id)
    values.update(element.parameters)
    for p in definition["parameters"]:
        value = values[p["key"]]
        try:
            if p["kind"] == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("必须是有限数")
                if p.get("positive") and value <= 0:
                    raise ValueError("必须大于 0")
                if p.get("min") is not None and value < p["min"]:
                    raise ValueError(f"不能小于 {p['min']}")
                if p.get("max") is not None and value > p["max"]:
                    raise ValueError(f"不能大于 {p['max']}")
                if p["key"] == "thermal_cells" and int(value) != value:
                    raise ValueError("必须是整数")
            elif p["kind"] == "boolean" and not isinstance(value, bool):
                raise ValueError("必须为布尔值")
            elif p["kind"] == "select" and value not in p["choices"]:
                raise ValueError("选项无效")
            elif p["kind"] == "text" and not isinstance(value, str):
                raise ValueError("必须为文本")
            elif p["kind"] == "curve":
                if not isinstance(value, list) or len(value) < 2:
                    raise ValueError("曲线至少需要两个点")
                if any(not isinstance(x, list) or len(x) != 2 or any(
                        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                        for v in x) for x in value):
                    raise ValueError("曲线必须为有限数值的 [横坐标, 纵坐标] 数组")
                if any(x[0] < 0 or x[1] < 0 for x in value):
                    raise ValueError("曲线坐标不能为负")
                if any(b[0] <= a[0] for a, b in zip(value, value[1:])):
                    raise ValueError("流量坐标必须严格递增")
                if p["key"] == "head_curve":
                    if value[0][0] != 0 or any(b[1] > a[1] for a, b in zip(value, value[1:])):
                        raise ValueError("扬程曲线必须从零流量开始，且单调不增")
                elif any(not 0 < point[1] <= 1 for point in value):
                    raise ValueError("效率必须大于 0 且不大于 1")
        except ValueError as exc:
            raise ModelError("PARAMETER_INVALID", f"{p['label']}：{exc}", element.id, p["key"]) from exc
    if element.type.startswith("tank_"):
        volume = values["area_m2"] * values["initial_level_m"]
        if not 0 < volume < values["capacity_m3"]:
            raise ModelError("TANK_INITIAL_STATE", "初始存水体积必须大于零且小于总容量", element.id)
    if element.type == "pid" and values["output_max"] <= values["output_min"]:
        raise ModelError("CONTROL_LIMITS", "输出上限必须大于下限", element.id)
    if element.type == "timer" and values["off_time_s"] <= values["on_time_s"]:
        raise ModelError("CONTROL_TIMES", "关闭时刻必须晚于开启时刻", element.id)
    return values


def catalog_json():
    return {"components": [{"type": key, **value} for key, value in CATALOG.items()],
            "variables": {key: {"label": value[0], "unit": value[1]} for key, value in VARIABLES.items()}}
