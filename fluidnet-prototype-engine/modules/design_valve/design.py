"""Liquid Kv sizing. Design conditions do not replace network boundaries."""
import math


def design(ctx):
    flow = ctx.parameter('design_flow_m3_s')
    drop = ctx.parameter('design_pressure_drop_pa')
    pressure = ctx.parameter('design_inlet_pressure_pa')
    temperature = ctx.parameter('design_temperature_k')
    opening = ctx.parameter('opening_ratio')
    if flow <= 0 or drop <= 0 or opening <= 0:
        raise ValueError('目标流量、设计压差和设计开度必须大于零')
    if pressure <= drop:
        raise ValueError('设计进口绝压必须大于压差，出口绝压须为正')
    inlet = ctx.fluid.state_pt(pressure, temperature)
    outlet = ctx.fluid.state_ph(pressure-drop, inlet.enthalpy_j_kg)
    if 'liquid' not in inlet.phase.lower() or 'liquid' not in outlet.phase.lower():
        raise ValueError('选型示例只支持进口与出口均为单相液体')
    kv = flow * 3600. / opening * math.sqrt(inlet.density_kg_m3 / 1000. / (drop / 1e5))
    ctx.set('kv_m3_h', kv)
    ctx.log(f'设计入口密度 {inlet.density_kg_m3:.4f} kg/m³；所需 Kv {kv:.6g} m³/h。')
    ctx.log('Kv 为所需流通能力，实际运行流量仍由管网求解；未校核厂家气蚀、噪声或阀权度。')
