from __future__ import annotations

import math
import time

import numpy as np

from .compiler import compile_project, validate_project
from .errors import ConvergenceError, ModelError
from .hydraulics import BranchLaw, friction_factor, solve_hydraulics, tank_condition
from .models import Project
from .thermal import boundary_mass_flows, solve_thermal


def solve_network(net, volume_states=None, pipe_states=None, dt=None, warm=None):
    temperatures = (warm[1].temperatures.copy() if warm and warm[1] else
                    np.full(len(net.node_ids), net.project.initial_temperature_k))
    hyd_warm = warm[0] if warm else None
    h_warm = warm[1].enthalpies if warm and warm[1] else None
    previous_flows = None
    start = time.perf_counter()
    for outer in range(40):
        hyd = solve_hydraulics(net, temperatures, volume_states, hyd_warm)
        if not net.project.options.thermal:
            return hyd, None, time.perf_counter() - start, outer + 1
        thermal = solve_thermal(net, hyd, h_warm, pipe_states, dt)
        t_change = float(np.max(np.abs(thermal.temperatures - temperatures)))
        q_change = math.inf if previous_flows is None else float(np.max(np.abs(hyd.flows - previous_flows)))
        if t_change < net.project.options.thermal_tolerance_k and q_change < 1e-7:
            return hyd, thermal, time.perf_counter() - start, outer + 1
        temperatures = thermal.temperatures.copy()
        previous_flows = hyd.flows.copy()
        hyd_warm, h_warm = hyd, thermal.enthalpies
    raise ConvergenceError("COUPLING_NOT_CONVERGED", "水力与热力耦合未收敛")


def snapshot(net, hyd, thermal, elapsed_s, outer_iterations, time_s=0, volume_states=None):
    elements = {e.id: e for e in net.project.elements}
    values = {e.id: {} for e in net.project.elements}
    port_values = {}
    temperatures = thermal.temperatures if thermal else np.full(len(net.node_ids), net.project.initial_temperature_k)
    for key, node in net.port_nodes.items():
        port_values[key] = {"pressure_pa": float(hyd.pressures[node]),
                            "temperature_k": float(temperatures[node]), "medium_id": net.node_media[node]}
    diagnostics = [x.to_dict() for x in net.warnings]
    for j, b in enumerate(net.branches):
        q = float(hyd.flows[j])
        up, down = (b.start, b.end) if q >= 0 else (b.end, b.start)
        area = math.pi * b.parameters.get("diameter_m", 0.05) ** 2 / 4
        re = abs(q) * b.parameters.get("diameter_m", 0.05) / (hyd.viscosities[j] * area)
        value = {
            "mass_flow_kg_s": q, "volume_flow_m3_h": q / float(hyd.densities[j]) * 3600,
            "inlet_pressure_pa": float(hyd.pressures[b.start]),
            "outlet_pressure_pa": float(hyd.pressures[b.end]),
            "pressure_drop_pa": float(hyd.pressures[b.start] - hyd.pressures[b.end]),
            "inlet_temperature_k": float(temperatures[up]),
            "temperature_k": float((temperatures[up] + temperatures[down]) / 2),
            "outlet_temperature_k": float(temperatures[down]),
            "density_kg_m3": float(hyd.densities[j]),
            "velocity_m_s": q / float(hyd.densities[j]) / area,
            "reynolds": float(re), "closed": float(b.id in hyd.closed),
        }
        if thermal:
            try:
                outlet_state = net.registry.get(b.medium_id).state_ph(float(hyd.pressures[down]), float(thermal.outlet_enthalpies[j]))
                value["outlet_temperature_k"] = outlet_state.temperature_k
            except ModelError as exc:
                exc.diagnostic.element_id = b.element_id
                raise
            value.update(heat_w=float(thermal.heat_w[j]), power_w=float(thermal.power_w[j]),
                         unmet_heat_w=float(thermal.unmet_heat_w[j]))
        if b.kind == "pipe":
            value["friction_factor"] = friction_factor(re, b.parameters["roughness_m"] / b.parameters["diameter_m"])[0]
            if thermal and b.id in thermal.pipes:
                stored = thermal.pipes[b.id]
                value["stored_energy_j"] = sum(stored["enthalpies"]) * stored["cell_mass_kg"]
        if b.kind == "valve":
            value["opening"] = BranchLaw(b, hyd.densities[j], hyd.viscosities[j]).opening()
        if b.kind == "pump":
            value["speed_ratio"] = b.parameters["speed_ratio"]
            value["head_m"] = BranchLaw(b, hyd.densities[j], hyd.viscosities[j]).pump_head(q)[0]
        prefix = b.path + "." if elements[b.element_id].type in {"heat_exchanger", "three_way"} else ""
        values[b.element_id].update({prefix + key: v for key, v in value.items()})
    boundary_flows = thermal.boundary_flows if thermal else boundary_mass_flows(net, hyd)
    for node, ids in net.boundaries.items():
        for eid in ids:
            e = elements[eid]
            provider = net.registry.get(net.node_media[node])
            fluid = provider.state_pt(float(hyd.pressures[node]), float(temperatures[node]))
            values[eid].update(pressure_pa=float(hyd.pressures[node]), temperature_k=float(temperatures[node]),
                               mass_flow_kg_s=float(boundary_flows[eid]),
                               volume_flow_m3_h=float(boundary_flows[eid]) / fluid.density_kg_m3 * 3600,
                               enthalpy_j_kg=fluid.enthalpy_j_kg)
            if thermal and eid in thermal.boundary_heat:
                values[eid]["boundary_heat_w"] = thermal.boundary_heat[eid]
            if e.type.startswith("tank_"):
                _, fluid, mass, level = tank_condition(net, eid, (volume_states or {}).get(eid))
                values[eid].update(mass_kg=mass, level_m=level, temperature_k=fluid.temperature_k,
                                   enthalpy_j_kg=fluid.enthalpy_j_kg, stored_energy_j=mass * fluid.enthalpy_j_kg)
                if volume_states is None and abs(boundary_flows[eid]) > 1e-7:
                    diagnostics.append({"code": "TANK_FROZEN_LEVEL", "severity": "info", "element_id": eid,
                                        "message": "稳态计算固定当前液位；存在净流入/流出，需用动态运行计算液位变化"})
    for e in net.project.elements:
        if e.type == "junction":
            node = net.port_nodes[f"{e.id}:p1"]
            values[e.id].update(pressure_pa=float(hyd.pressures[node]), temperature_k=float(temperatures[node]))
    return {
        "status": "converged", "valid": True, "time_s": float(time_s),
        "project_id": net.project.id, "project_revision": net.project.revision,
        "elements": values, "ports": port_values, "circuits": net.circuits,
        "media": [m.model_dump() for m in net.project.media],
        "diagnostics": diagnostics,
        "metrics": {"mass_residual_kg_s": hyd.mass_residual,
                    "pressure_residual_pa": hyd.pressure_residual,
                    "energy_residual_w": thermal.energy_residual_w if thermal else None,
                    "hydraulic_iterations": hyd.iterations,
                    "thermal_iterations": thermal.iterations if thermal else 0,
                    "coupling_iterations": outer_iterations, "elapsed_s": elapsed_s,
                    "node_count": len(net.node_ids), "branch_count": len(net.branches)},
        "convergence_history": hyd.history,
    }


def solve_steady(project: Project | dict):
    if isinstance(project, dict):
        project = Project.model_validate(project)
    net = compile_project(project)
    hyd, thermal, elapsed, iterations = solve_network(net)
    return snapshot(net, hyd, thermal, elapsed, iterations)
