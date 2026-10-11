from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from .errors import ConvergenceError, ModelError
from .hydraulics import BranchLaw
from .units import G


@dataclass
class ThermalResult:
    enthalpies: np.ndarray
    temperatures: np.ndarray
    outlet_enthalpies: np.ndarray
    heat_w: np.ndarray
    power_w: np.ndarray
    unmet_heat_w: np.ndarray
    pipes: dict
    boundary_flows: dict
    boundary_energy: dict
    boundary_heat: dict
    energy_residual_w: float
    iterations: int


def thermal_relations(net, hyd, enthalpies, dynamic_old=None, dt=None):
    n, m = len(net.node_ids), len(net.branches)
    states = [net.registry.get(net.node_media[i]).state_ph(float(hyd.pressures[i]), float(enthalpies[i])) for i in range(n)]
    relations = []
    pipe_updates = {}
    shaft = np.zeros(m)
    requested = np.zeros(m)
    for j, b in enumerate(net.branches):
        p, q = b.parameters, float(hyd.flows[j])
        w = abs(q)
        up, down = (b.start, b.end) if q >= 0 else (b.end, b.start)
        provider = net.registry.get(b.medium_id)
        cp = states[up].cp_j_kg_k
        a, constant = 1.0, -G * p.get("height_change_m", 0) * (1 if q >= 0 else -1)
        if b.kind == "pipe":
            ua = p["heat_loss_ua_w_k"]
            env_h = provider.state_pt(float(hyd.pressures[down]), p["ambient_temperature_k"]).enthalpy_j_kg
            old = (dynamic_old or {}).get(b.id)
            if old is not None and dt is not None:
                old_values = np.array(old["enthalpies"], dtype=float)
                if q < 0:
                    old_values = old_values[::-1]
                count = len(old_values)
                capacity = old["cell_mass_kg"] / dt
                conductance = ua / count / cp
                denominator = capacity + w + conductance
                gravity = constant / count
                a, constant = 1.0, 0.0
                coefficients = []
                for previous in old_values:
                    a = w * a / denominator
                    constant = (w * constant + capacity * previous + conductance * env_h + w * gravity) / denominator
                    coefficients.append((a, constant))
                pipe_updates[b.id] = {"coefficients": coefficients, "reverse": q < 0,
                                      "cell_mass_kg": old["cell_mass_kg"],
                                      "env_h": env_h, "conductance": conductance}
            elif w > 1e-12:
                a = math.exp(-ua / (w * cp))
                constant += (1 - a) * env_h
        elif b.kind == "pump" and p["speed_ratio"] > 0 and w > 1e-12:
            law = BranchLaw(b, hyd.densities[j], hyd.viscosities[j])
            head, _ = law.pump_head(q)
            curve = np.array(p["efficiency_curve"])
            volume_flow = w * 3600 / hyd.densities[j] / p["speed_ratio"]
            if volume_flow < curve[0, 0] - 1e-8 or volume_flow > curve[-1, 0] + 1e-8:
                raise ModelError("PUMP_EFFICIENCY_RANGE", "运行点超出效率曲线范围", b.element_id)
            efficiency = float(PchipInterpolator(curve[:, 0], curve[:, 1])(np.clip(volume_flow, curve[0, 0], curve[-1, 0])))
            shaft[j] = w * G * head / efficiency
            constant += shaft[j] / w
        elif b.kind == "heater":
            requested[j] = p["power_w"]
            actual = float(np.clip(requested[j], -p["capacity_w"], p["capacity_w"]))
            if w < 1e-10 and abs(actual) > 1e-8:
                raise ModelError("NO_FLOW_HEAT", "无流量的无热容设备不能持续加热或冷却，请增加容积设备或关闭热源", b.element_id)
            if w > 1e-10:
                constant += actual / w
        elif b.kind == "temperature_source":
            target = provider.state_pt(float(hyd.pressures[down]), p["target_temperature_k"]).enthalpy_j_kg
            requested[j] = w * (target - enthalpies[up])
            if w > 1e-10:
                if abs(requested[j]) <= p["capacity_w"]:
                    a, constant = 0.0, target
                else:
                    constant += math.copysign(p["capacity_w"], requested[j]) / w
        relations.append(({up: a}, constant, up, down, w))
    exchangers = {}
    for j, b in enumerate(net.branches):
        if b.kind == "heat_exchanger":
            exchangers.setdefault(b.element_id, {})[b.path] = j
    for eid, sides in exchangers.items():
        ia, ib = sides["a"], sides["b"]
        _, _, ua, da, wa = relations[ia]
        _, _, ub, db, wb = relations[ib]
        if min(wa, wb) <= 1e-12:
            continue
        cpa, cpb = states[ua].cp_j_kg_k, states[ub].cp_j_kg_k
        ca, cb = wa * cpa, wb * cpb
        cmin, cmax = min(ca, cb), max(ca, cb)
        ratio = cmin / cmax
        ntu = net.parameters[eid]["ua_w_k"] / cmin
        if abs(1 - ratio) < 1e-8:
            effectiveness = ntu / (1 + ntu)
        else:
            exponential = math.exp(-ntu * (1 - ratio))
            effectiveness = (1 - exponential) / (1 - ratio * exponential)
        conductance = effectiveness * cmin
        offset = (states[ua].temperature_k - enthalpies[ua] / cpa
                  - states[ub].temperature_k + enthalpies[ub] / cpb)
        aw = {ua: 1 - conductance / ca}
        aw[ub] = aw.get(ub, 0) + conductance / (wa * cpb)
        bw = {ub: 1 - conductance / cb}
        bw[ua] = bw.get(ua, 0) + conductance / (wb * cpa)
        relations[ia] = (aw, -conductance * offset / wa, ua, da, wa)
        relations[ib] = (bw, conductance * offset / wb, ub, db, wb)
    return relations, shaft, requested, pipe_updates


def boundary_mass_flows(net, hyd):
    outgoing = np.zeros(len(net.node_ids))
    for b, q in zip(net.branches, hyd.flows):
        outgoing[b.start] += q
        outgoing[b.end] -= q
    flows = {}
    elements = {e.id: e for e in net.project.elements}
    for node, ids in net.boundaries.items():
        for eid in ids:
            e, p = elements[eid], net.parameters[eid]
            if e.type == "flow_boundary":
                flows[eid] = p["mass_flow_kg_s"]
            elif e.type == "demand":
                flows[eid] = -p["demand_kg_s"]
            else:
                flows[eid] = float(outgoing[node] - hyd.injections[node])
    return flows


def solve_thermal(net, hyd, initial_enthalpies=None, dynamic_old=None, dt=None):
    n, m = len(net.node_ids), len(net.branches)
    h = np.array([net.registry.get(net.node_media[i]).state_pt(float(hyd.pressures[i]),
                  net.project.initial_temperature_k).enthalpy_j_kg for i in range(n)]) if initial_enthalpies is None else np.array(initial_enthalpies, copy=True)
    for node, value in hyd.fixed_enthalpies.items():
        h[node] = value
    boundaries = boundary_mass_flows(net, hyd)
    fixed = hyd.fixed_enthalpies
    elements = {e.id: e for e in net.project.elements}
    boundary_in_h = {}
    for node, ids in net.boundaries.items():
        for eid in ids:
            if boundaries[eid] > 0:
                if eid.startswith("__"):
                    continue
                p = net.parameters[eid]
                boundary_in_h[eid] = fixed.get(node) if elements[eid].type.startswith("tank_") else None
                if boundary_in_h[eid] is None:
                    boundary_in_h[eid] = net.registry.get(net.node_media[node]).state_pt(
                        float(hyd.pressures[node]), p.get("temperature_k", net.project.initial_temperature_k)).enthalpy_j_kg
    for iteration in range(net.project.options.max_thermal_iterations):
        try:
            relations, shaft, requested, pipe_updates = thermal_relations(net, hyd, h, dynamic_old, dt)
        except ModelError:
            raise
        rows, cols, values = [], [], []
        rhs = np.zeros(n)
        strength = np.zeros(n)
        def add(row, col, value):
            if row not in fixed and value:
                rows.append(row); cols.append(col); values.append(value)
                strength[row] += abs(value)
        for weights, constant, up, down, w in relations:
            if w <= 1e-12:
                continue
            add(up, up, w)
            for col, value in weights.items():
                add(down, col, -w * value)
            if down not in fixed:
                rhs[down] += w * constant
        for node, ids in net.boundaries.items():
            if node in fixed:
                continue
            for eid in ids:
                q = boundaries[eid]
                if q > 0:
                    rhs[node] += q * boundary_in_h[eid]
                elif q < 0:
                    add(node, node, -q)
        for node in range(n):
            if node in fixed:
                rows.append(node); cols.append(node); values.append(1.0)
                rhs[node] = fixed[node]
            elif strength[node] < 1e-14:
                # A stagnant zero-flux junction has no unique equilibrium temperature.
                # It retains its specified/previous temperature; no energy is transported.
                rows.append(node); cols.append(node); values.append(1.0)
                rhs[node] = h[node]
        matrix = coo_matrix((values, (rows, cols)), shape=(n, n)).tocsc()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", MatrixRankWarning)
                candidate = spsolve(matrix, rhs)
        except (MatrixRankWarning, RuntimeError) as exc:
            raise ConvergenceError("THERMAL_REFERENCE_MISSING", "热力方程欠约束或稳态不存在；检查闭式回路的温度参考、热源与热汇") from exc
        if not np.all(np.isfinite(candidate)):
            raise ConvergenceError("THERMAL_NOT_FINITE", "热力方程没有有限解")
        max_delta = float(np.max(np.abs(candidate - h)))
        if max_delta < net.project.options.thermal_tolerance_k * 3500:
            h = candidate
            break
        h = 0.7 * candidate + 0.3 * h
    else:
        raise ConvergenceError("THERMAL_NOT_CONVERGED", "热力迭代未收敛，请检查能量输入与边界")
    temperatures = []
    for node, enthalpy in enumerate(h):
        try:
            temperatures.append(net.registry.get(net.node_media[node]).state_ph(float(hyd.pressures[node]), float(enthalpy)).temperature_k)
        except ModelError as exc:
            exc.diagnostic.element_id = net.node_ids[node].split(":")[0]
            raise
    # Re-evaluate nonlinear heat transfer at the converged state and measure its
    # actual nodal balance, not merely the linear-system residual.
    relations, shaft, requested, pipe_updates = thermal_relations(net, hyd, h, dynamic_old, dt)
    outlets = np.zeros(m)
    heat = np.zeros(m)
    energy_outgoing = np.zeros(n)
    next_pipes = {}
    for j, (b, relation) in enumerate(zip(net.branches, relations)):
        weights, constant, up, down, w = relation
        outlets[j] = sum(h[col] * value for col, value in weights.items()) + constant
        energy_outgoing[up] += w * h[up]
        energy_outgoing[down] -= w * outlets[j]
        heat[j] = w * (outlets[j] - h[up]) - shaft[j] + w * G * b.parameters.get("height_change_m", 0) * (1 if hyd.flows[j] >= 0 else -1)
        if b.id in pipe_updates:
            data = pipe_updates[b.id]
            cells = np.array([a * h[up] + v for a, v in data["coefficients"]])
            heat[j] = float(np.sum(data["conductance"] * (data["env_h"] - cells)))
            if data["reverse"]:
                cells = cells[::-1]
            next_pipes[b.id] = {"enthalpies": cells.tolist(), "cell_mass_kg": data["cell_mass_kg"]}
    boundary_energy, boundary_heat = {}, {}
    balance = energy_outgoing.copy()
    for node, ids in net.boundaries.items():
        other_energy = 0.0
        for eid in ids:
            q = boundaries[eid]
            energy = q * (boundary_in_h.get(eid, h[node]) if q > 0 else h[node])
            balance[node] -= energy
            if elements[eid].type in {"demand", "flow_boundary"}:
                other_energy += energy
        for eid in ids:
            if elements[eid].type.startswith("tank_"):
                boundary_energy[eid] = float(-energy_outgoing[node] + other_energy)
            elif elements[eid].type == "pressure":
                boundary_heat[eid] = float(balance[node]) if node in fixed else 0.0
    free = [i for i in range(n) if i not in fixed]
    residual = float(np.max(np.abs(balance[free]))) if free else 0.0
    scale = max(1.0, float(np.max(np.abs(energy_outgoing))))
    if residual > max(1.0, 1e-5 * scale):
        raise ConvergenceError("ENERGY_BALANCE", f"热量不平衡 {residual:.5g} W 超出容差")
    unmet = np.zeros(m)
    for j, b in enumerate(net.branches):
        if b.kind in {"heater", "temperature_source"}:
            unmet[j] = requested[j] - heat[j]
    return ThermalResult(h, np.array(temperatures), outlets, heat, shaft, unmet,
                         next_pipes, boundaries, boundary_energy, boundary_heat,
                         residual, iteration + 1)
