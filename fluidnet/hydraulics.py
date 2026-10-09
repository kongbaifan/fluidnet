from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve

from .compiler import Branch, Network, UnionFind
from .errors import ConvergenceError, ModelError
from .units import G


@dataclass
class HydraulicResult:
    pressures: np.ndarray
    flows: np.ndarray
    densities: np.ndarray
    viscosities: np.ndarray
    closed: set[str]
    fixed: dict[int, float]
    injections: np.ndarray
    fixed_enthalpies: dict[int, float]
    iterations: int
    mass_residual: float
    pressure_residual: float
    history: list[dict]


def tank_condition(net, element_id, state=None):
    e = next(e for e in net.project.elements if e.id == element_id)
    p = net.parameters[element_id]
    node = net.port_nodes[f"{element_id}:p1"]
    provider = net.registry.get(net.node_media[node])
    surface = p.get("surface_pressure_pa", p.get("gas_pressure_pa", 101325.0))
    reference = provider.state_pt(surface, p["temperature_k"])
    initial_volume = p["area_m2"] * p["initial_level_m"]
    mass = state["mass_kg"] if state else initial_volume * reference.density_kg_m3
    density = state.get("density_kg_m3", reference.density_kg_m3) if state else reference.density_kg_m3
    volume = mass / density
    if e.type == "tank_gas":
        gas_volume = p["capacity_m3"] - volume
        if gas_volume <= 0:
            raise ModelError("TANK_FULL", "气垫罐没有剩余气体容积", element_id)
        surface = p["gas_pressure_pa"] * ((p["capacity_m3"] - initial_volume) / gas_volume) ** p["polytropic_index"]
    level = volume / p["area_m2"]
    pressure = surface + density * G * level
    fluid = provider.state_ph(pressure, state["enthalpy_j_kg"]) if state else provider.state_pt(pressure, p["temperature_k"])
    return pressure, fluid, mass, level


def boundary_values(net: Network, volume_states=None):
    elements = {e.id: e for e in net.project.elements}
    fixed, enthalpies = {}, {}
    injections = np.zeros(len(net.node_ids))
    for node, ids in net.boundaries.items():
        for eid in ids:
            e, p = elements[eid], net.parameters[eid]
            if e.type == "flow_boundary":
                injections[node] += p["mass_flow_kg_s"]
                continue
            if e.type == "demand":
                injections[node] -= p["demand_kg_s"]
                continue
            try:
                if e.type == "pressure":
                    pressure = p["pressure_pa"]
                    fluid = net.registry.get(net.node_media[node]).state_pt(pressure, p["temperature_k"])
                    temperature_fixed = p["temperature_fixed"]
                else:
                    pressure, fluid, _, _ = tank_condition(net, eid, (volume_states or {}).get(eid))
                    temperature_fixed = True
            except ModelError as exc:
                exc.diagnostic.element_id = eid
                raise
            if node in fixed:
                raise ModelError("BOUNDARY_CONFLICT", "同一理想节点连接了多个定压或容积边界，请用管路连接", eid)
            fixed[node] = pressure
            if temperature_fixed:
                enthalpies[node] = fluid.enthalpy_j_kg
    return fixed, injections, enthalpies


def check_anchors(net, fixed, closed):
    connected = UnionFind(range(len(net.node_ids)))
    for b in net.branches:
        if b.id not in closed:
            connected.union(b.start, b.end)
    anchored = {connected.find(i) for i in fixed}
    for i, key in enumerate(net.node_ids):
        if connected.find(i) not in anchored:
            raise ModelError("PRESSURE_REFERENCE_MISSING", "连通区域缺少压力参考；关阀后的孤岛需要容积设备或定压边界", key.split(":")[0])


def friction_factor(reynolds, relative_roughness):
    """Darcy factor and df/dRe, with a C1 transition between 2300 and 4000."""
    re = abs(reynolds)
    if re <= 0:
        return 0.0, 0.0
    laminar, dlaminar = 64 / re, -64 / re ** 2
    if re <= 2300:
        return laminar, dlaminar
    y = -1.8 * math.log10((relative_roughness / 3.7) ** 1.11 + 6.9 / re)
    for _ in range(12):
        term = relative_roughness / 3.7 + 2.51 * y / re
        value = y + 2 * math.log10(term)
        slope = 1 + 2 / math.log(10) * 2.51 / re / term
        update = value / slope
        y -= update
        if abs(update) < 1e-12:
            break
    term = relative_roughness / 3.7 + 2.51 * y / re
    dy = (2 / math.log(10) * 2.51 * y / re ** 2 / term) / (1 + 2 / math.log(10) * 2.51 / re / term)
    turbulent, dturbulent = 1 / y ** 2, -2 * dy / y ** 3
    if re >= 4000:
        return turbulent, dturbulent
    t = (re - 2300) / 1700
    s, ds = t * t * (3 - 2 * t), 6 * t * (1 - t) / 1700
    return ((1 - s) * laminar + s * turbulent,
            (1 - s) * dlaminar + s * dturbulent + ds * (turbulent - laminar))


class BranchLaw:
    def __init__(self, branch: Branch, density, viscosity):
        self.b, self.p = branch, branch.parameters
        self.rho, self.mu = density, viscosity
        self.area = math.pi * self.p.get("diameter_m", 0.05) ** 2 / 4
        self.pump_curve = None
        if branch.kind == "pump":
            data = np.asarray(self.p["head_curve"], dtype=float)
            self.pump_curve = PchipInterpolator(data[:, 0], data[:, 1], extrapolate=False)
            self.curve_end = data[-1, 0]

    def opening(self):
        x = self.p.get("opening", 1.0)
        if self.b.path == "b" and self.b.kind == "valve":
            x = 1 - x
        if self.p.get("characteristic") == "equal_percentage" and x > 0:
            ratio = self.p["rangeability"]
            return x if ratio == 1 else (ratio ** x - 1) / (ratio - 1)
        return x

    def pump_head(self, q):
        speed = self.p["speed_ratio"]
        if speed <= 0:
            return 0.0, 0.0
        x = q * 3600 / self.rho / speed
        edge = min(max(x, 0), self.curve_end)
        # Tangent continuation is only for Newton iterates; the final operating point
        # must lie within the supplied curve and is checked by solve_hydraulics.
        value = float(self.pump_curve(edge))
        derivative = float(self.pump_curve.derivative()(edge))
        value += derivative * (x - edge)
        return speed ** 2 * value, speed * derivative * 3600 / self.rho

    def loss(self, q):
        p, rho, mu, area = self.p, self.rho, self.mu, self.area
        absolute = abs(q)
        if self.b.kind == "valve":
            kv = p["kv_m3_h"] * max(self.opening(), 1e-15)
            coefficient = 1e5 * 3600 ** 2 / (1000 * rho * kv ** 2)
            return coefficient * q * absolute, 2 * coefficient * max(absolute, 1e-12)
        if self.b.kind == "pump" and p["speed_ratio"] > 0:
            head, derivative = self.pump_head(q)
            return -rho * G * head, -rho * G * derivative
        diameter = p.get("diameter_m", 0.05)
        length = p.get("length_m", 0.0) if self.b.kind == "pipe" else 0.0
        k = p.get("loss_coefficient", 0.0)
        if self.b.kind == "pump":
            k = p["off_loss_coefficient"]
        re_per_q = diameter / (mu * area)
        re = absolute * re_per_q
        coefficient = 1 / (2 * rho * area ** 2)
        gravity = rho * G * p.get("height_change_m", 0)
        if length and re <= 2300:
            linear = 128 * mu * length / (math.pi * rho * diameter ** 4)
            return (linear * q + coefficient * k * q * absolute + gravity,
                    linear + 2 * coefficient * k * absolute)
        if length:
            f, df = friction_factor(re, p["roughness_m"] / diameter)
        else:
            f, df = 0.0, 0.0
        total = f * length / diameter + k
        derivative = coefficient * (2 * total * absolute + length / diameter * df * re_per_q * q ** 2)
        return coefficient * total * q * absolute + gravity, max(derivative, 1e-12)


def solve_hydraulics(net: Network, temperatures=None, volume_states=None, warm=None):
    options = net.project.options
    n, m = len(net.node_ids), len(net.branches)
    fixed, injections, fixed_h = boundary_values(net, volume_states)
    if not fixed:
        raise ModelError("PRESSURE_REFERENCE_MISSING", "每个连通区域至少需要一个定压或容积边界")
    unknown = [i for i in range(n) if i not in fixed]
    uindex = {node: i for i, node in enumerate(unknown)}
    nu = len(unknown)
    initial_pressure = sum(fixed.values()) / len(fixed)
    pressures = np.full(n, initial_pressure) if warm is None else np.array(warm.pressures, copy=True)
    flows = np.full(m, 0.01) if warm is None else np.array(warm.flows, copy=True)
    for i, pressure in fixed.items():
        pressures[i] = pressure
    temperatures = (np.full(n, net.project.initial_temperature_k) if temperatures is None
                    else np.array(temperatures))
    for i, h in fixed_h.items():
        temperatures[i] = net.registry.get(net.node_media[i]).state_ph(pressures[i], h).temperature_k
    closed = set() if warm is None else set(warm.closed)
    closed.intersection_update({b.id for b in net.branches if b.kind == "check_valve"})
    for b in net.branches:
        if b.kind == "valve" and BranchLaw(b, 1000, 0.001).opening() <= 0:
            closed.add(b.id)
    total_iterations, history = 0, []
    qscale = max(1.0, float(np.max(np.abs(injections))))
    pscale = max(1e5, max(fixed.values()) - min(fixed.values()))
    scales = np.r_[np.full(nu, pscale), np.full(m, qscale)]
    previous_densities = None
    for property_iteration in range(12):
        laws = []
        for b in net.branches:
            temp = float((temperatures[b.start] + temperatures[b.end]) / 2)
            pressure = float((pressures[b.start] + pressures[b.end]) / 2)
            try:
                state = net.registry.get(b.medium_id).state_pt(pressure, temp)
            except ModelError as exc:
                exc.diagnostic.element_id = b.element_id
                raise
            laws.append(BranchLaw(b, state.density_kg_m3, state.viscosity_pa_s))
        densities = np.array([law.rho for law in laws])
        viscosities = np.array([law.mu for law in laws])

        def evaluate(pvalues, qvalues, jacobian=False):
            mass = -injections.copy()
            energy = np.zeros(m)
            rows, cols, values = [], [], []
            for j, (b, law) in enumerate(zip(net.branches, laws)):
                q = qvalues[j]
                mass[b.start] += q
                mass[b.end] -= q
                if b.id in closed:
                    energy[j] = q / qscale
                    if jacobian:
                        rows.append(nu + j); cols.append(nu + j); values.append(1)
                else:
                    loss, gradient = law.loss(q)
                    energy[j] = (pvalues[b.start] - pvalues[b.end] - loss) / pscale
                    if jacobian:
                        for node, sign in ((b.start, 1), (b.end, -1)):
                            if node in uindex:
                                rows.append(nu + j); cols.append(uindex[node]); values.append(sign)
                        rows.append(nu + j); cols.append(nu + j); values.append(-gradient * qscale / pscale)
                if jacobian:
                    for node, sign in ((b.start, 1), (b.end, -1)):
                        if node in uindex:
                            rows.append(uindex[node]); cols.append(nu + j); values.append(sign)
            result = np.r_[mass[unknown] / qscale, energy]
            matrix = coo_matrix((values, (rows, cols)), shape=(nu + m, nu + m)).tocsc() if jacobian else None
            return result, matrix

        for active_iteration in range(24):
            check_anchors(net, fixed, closed)
            for iteration in range(options.max_iterations):
                total_iterations += 1
                residual, matrix = evaluate(pressures, flows, True)
                norm = float(np.linalg.norm(residual, ord=np.inf))
                history.append({"iteration": total_iterations, "scaled_residual": norm})
                if norm < 1e-10:
                    break
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", MatrixRankWarning)
                        delta = spsolve(matrix, -residual) * scales
                except (MatrixRankWarning, RuntimeError) as exc:
                    raise ConvergenceError("SINGULAR_NETWORK", "网络约束不独立或流量不唯一，请检查理想短路、孤岛和边界") from exc
                if not np.all(np.isfinite(delta)):
                    raise ConvergenceError("SINGULAR_NETWORK", "稀疏方程求解失败，请检查网络约束")
                merit = float(residual @ residual)
                alpha = 1.0
                for _ in range(30):
                    trial_p, trial_q = pressures.copy(), flows + alpha * delta[nu:]
                    trial_p[unknown] += alpha * delta[:nu]
                    trial, _ = evaluate(trial_p, trial_q)
                    if float(trial @ trial) < merit * (1 - 1e-4 * alpha) or np.max(np.abs(trial)) < 1e-10:
                        pressures, flows = trial_p, trial_q
                        break
                    alpha *= 0.5
                else:
                    raise ConvergenceError("HYDRAULIC_LINE_SEARCH", "水力迭代无法继续下降，请检查边界与设备运行范围")
            else:
                raise ConvergenceError("HYDRAULIC_NOT_CONVERGED", f"水力迭代超过 {options.max_iterations} 次")
            changed = False
            for j, b in enumerate(net.branches):
                if b.kind != "check_valve":
                    continue
                if b.id not in closed and flows[j] < -1e-9:
                    closed.add(b.id); changed = True
                elif b.id in closed and pressures[b.start] - pressures[b.end] > 1e-4:
                    closed.remove(b.id); changed = True
            if not changed:
                break
        else:
            raise ConvergenceError("VALVE_STATE_CYCLE", "止回阀状态未能稳定")
        if previous_densities is not None and np.max(np.abs(densities - previous_densities) / densities) < 1e-9:
            break
        previous_densities = densities.copy()
    else:
        raise ConvergenceError("PROPERTY_COUPLING", "压力与物性耦合未收敛")
    residual, _ = evaluate(pressures, flows)
    mass_residual = float(np.max(np.abs(residual[:nu])) * qscale) if nu else 0.0
    pressure_residual = max((abs(pressures[b.start] - pressures[b.end] - laws[j].loss(flows[j])[0])
                             for j, b in enumerate(net.branches) if b.id not in closed), default=0.0)
    for node, p in enumerate(pressures):
        try:
            net.registry.get(net.node_media[node]).state_pt(float(p), float(temperatures[node]))
        except ModelError as exc:
            exc.diagnostic.element_id = net.node_ids[node].split(":")[0]
            raise
    for j, b in enumerate(net.branches):
        if b.kind == "pump" and b.parameters["speed_ratio"] > 0:
            operating = flows[j] * 3600 / densities[j] / b.parameters["speed_ratio"]
            if operating < -1e-7 or operating > laws[j].curve_end * (1 + 1e-7):
                raise ModelError("PUMP_CURVE_RANGE", f"泵运行点 {operating:.4g} m³/h 超出输入曲线范围", b.element_id)
    return HydraulicResult(pressures, flows, densities, viscosities, closed, fixed,
                           injections, fixed_h, total_iterations, mass_residual,
                           float(pressure_residual), history)
