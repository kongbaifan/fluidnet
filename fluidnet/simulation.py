from __future__ import annotations

import copy
import math
import time

import numpy as np

from .catalog import CATALOG, get_parameters
from .compiler import compile_project
from .errors import ConvergenceError, ModelError
from .hydraulics import solve_hydraulics, tank_condition
from .models import Project
from .solver import snapshot, solve_network
from .units import G


def read_variable(frame, path):
    element_id, _, variable = path.partition(".")
    value = frame.get("elements", {}).get(element_id, {}).get(variable)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


class TankEvent(ModelError):
    def __init__(self, code, message, element_id, fraction):
        super().__init__(code, message, element_id)
        self.fraction = min(1.0, max(0.0, fraction))


class SimulationSession:
    """Accepted states are atomic. All trials use the same immutable old state."""
    def __init__(self, project: Project | dict, dt_s=0.1):
        self.project = Project.model_validate(project) if isinstance(project, dict) else project.model_copy(deep=True)
        if not self.project.options.thermal:
            raise ModelError("DYNAMIC_THERMAL_REQUIRED", "慢动态运行需要启用热力计算")
        if not 0.001 <= dt_s <= 60:
            raise ValueError("时间步长需在 0.001 到 60 秒之间")
        self.dt_s = dt_s
        self.net = compile_project(self.project)
        self.time_s = 0.0
        self.status = "paused"
        self.events = []
        self.volumes = {}
        self.pipes = {}
        self.controllers = {}
        self.warm = None
        for e in self.project.elements:
            if e.type.startswith("tank_"):
                _, fluid, _, _ = tank_condition(self.net, e.id)
                p = self.net.parameters[e.id]
                self.volumes[e.id] = {"mass_kg": p["area_m2"] * p["initial_level_m"] * fluid.density_kg_m3,
                                      "enthalpy_j_kg": fluid.enthalpy_j_kg,
                                      "density_kg_m3": fluid.density_kg_m3}
        hyd = solve_hydraulics(self.net, volume_states=self.volumes)
        for j, b in enumerate(self.net.branches):
            if b.kind == "pipe":
                count = int(b.parameters["thermal_cells"])
                provider = self.net.registry.get(b.medium_id)
                fluid = provider.state_pt(float((hyd.pressures[b.start] + hyd.pressures[b.end]) / 2),
                                          b.parameters["initial_temperature_k"])
                volume = math.pi * b.parameters["diameter_m"] ** 2 / 4 * b.parameters["length_m"]
                self.pipes[b.id] = {"enthalpies": [fluid.enthalpy_j_kg] * count,
                                    "cell_mass_kg": volume * fluid.density_kg_m3 / count}
        hyd, thermal, elapsed, outer = solve_network(self.net, self.volumes, self.pipes, 1e-20)
        self.warm = (hyd, thermal)
        self.frame = snapshot(self.net, hyd, thermal, elapsed, outer, 0, self.volumes)
        for e in self.project.elements:
            if e.type == "pid":
                p = self.net.parameters[e.id]
                measured = read_variable(self.frame, p["measurement"])
                if measured is None:
                    raise ModelError("CONTROL_MEASUREMENT_MISSING", f"变量 {p['measurement']} 不存在", e.id)
                error = (p["setpoint"] - measured) * (-1 if p["reverse"] else 1)
                current = self.net.parameters[p["target_element"]][p["target_parameter"]]
                self.controllers[e.id] = {"integral": current - p["kp"] * error, "previous_error": error,
                                          "next_time_s": 0.0, "output": float(current), "error": error}
            elif e.type == "timer":
                self.controllers[e.id] = {"output": self.net.parameters[e.id]["off_value"]}
        self._annotate()

    def set_parameter(self, element_id, parameter, value, record=True):
        element = next((e for e in self.project.elements if e.id == element_id), None)
        if element is None:
            raise ModelError("ELEMENT_MISSING", "受控元件不存在", element_id)
        field = next((p for p in CATALOG[element.type]["parameters"] if p["key"] == parameter), None)
        if not field or not field.get("runtime"):
            raise ModelError("PARAMETER_REQUIRES_REINITIALIZATION", "该参数需要停止并重新初始化", element_id, parameter)
        candidate = element.model_copy(deep=True)
        candidate.parameters[parameter] = value
        validated = get_parameters(candidate)
        element.parameters[parameter] = value
        self.net.parameters[element_id][parameter] = validated[parameter]
        if record:
            self.events.append({"time_s": self.time_s, "type": "parameter", "element_id": element_id,
                                "parameter": parameter, "value": value})

    def _controls(self):
        for e in self.project.elements:
            if e.type not in {"pid", "timer"}:
                continue
            p, state = self.net.parameters[e.id], self.controllers[e.id]
            if not p["enabled"]:
                continue
            if e.type == "timer":
                value = p["on_value"] if p["on_time_s"] <= self.time_s < p["off_time_s"] else p["off_value"]
                state["output"] = value
                self.set_parameter(p["target_element"], p["target_parameter"], value, False)
                continue
            if self.time_s + 1e-10 < state["next_time_s"]:
                continue
            measured = read_variable(self.frame, p["measurement"])
            if measured is None:
                raise ModelError("CONTROL_MEASUREMENT_MISSING", "当前状态中没有控制器需要的测量值", e.id)
            error = (p["setpoint"] - measured) * (-1 if p["reverse"] else 1)
            derivative = (error - state["previous_error"]) / p["period_s"]
            integral = state["integral"] + p["ki"] * error * p["period_s"]
            raw = p["kp"] * error + integral + p["kd"] * derivative
            if ((p["output_min"] <= raw <= p["output_max"])
                    or (raw > p["output_max"] and error < 0)
                    or (raw < p["output_min"] and error > 0)):
                state["integral"] = integral
            output = float(np.clip(p["kp"] * error + state["integral"] + p["kd"] * derivative,
                                   p["output_min"], p["output_max"]))
            state.update(output=output, error=error, previous_error=error,
                         next_time_s=self.time_s + p["period_s"])
            self.set_parameter(p["target_element"], p["target_parameter"], output, False)

    def _next_control_boundary(self, target):
        result = target
        for e in self.project.elements:
            if e.type not in {"pid", "timer"}:
                continue
            p = self.net.parameters[e.id]
            if not p["enabled"]:
                continue
            times = ([self.controllers[e.id]["next_time_s"]] if e.type == "pid"
                     else [p["on_time_s"], p["off_time_s"]])
            for t in times:
                if self.time_s + 1e-10 < t < result:
                    result = t
        return result

    def inventory(self):
        mass = sum(v["mass_kg"] for v in self.volumes.values())
        energy = sum(v["mass_kg"] * v["enthalpy_j_kg"] for v in self.volumes.values())
        for p in self.pipes.values():
            mass += p["cell_mass_kg"] * len(p["enthalpies"])
            energy += p["cell_mass_kg"] * sum(p["enthalpies"])
        return mass, energy

    def _attempt_step(self, dt):
        started = time.perf_counter()
        candidate = copy.deepcopy(self.volumes)
        old_mass, old_energy = self.inventory()
        warm = self.warm
        for iteration in range(50):
            hyd, thermal, _, outer = solve_network(self.net, candidate, self.pipes, dt, warm)
            next_volumes = {}
            maximum_change = 0.0
            for eid, old in self.volumes.items():
                p = self.net.parameters[eid]
                node = self.net.port_nodes[f"{eid}:p1"]
                fluid = self.net.registry.get(self.net.node_media[node]).state_ph(
                    float(hyd.pressures[node]), candidate[eid]["enthalpy_j_kg"])
                mass = old["mass_kg"] - dt * thermal.boundary_flows[eid]
                min_mass = 1e-7
                max_mass = p["capacity_m3"] * fluid.density_kg_m3 * (1 - 1e-8)
                if mass <= min_mass:
                    fraction = (old["mass_kg"] - min_mass) / max(old["mass_kg"] - mass, 1e-30)
                    raise TankEvent("TANK_EMPTY", "水箱到达空箱边界，动态运行已暂停", eid, fraction)
                if mass >= max_mass:
                    fraction = (max_mass - old["mass_kg"]) / max(mass - old["mass_kg"], 1e-30)
                    raise TankEvent("TANK_FULL", "水箱到达容量边界，动态运行已暂停", eid, fraction)
                outgoing = 0.0
                for b, q in zip(self.net.branches, hyd.flows):
                    if b.start == node and q > 0:
                        outgoing += q
                    elif b.end == node and q < 0:
                        outgoing -= q
                incoming_energy = thermal.boundary_energy[eid] + outgoing * candidate[eid]["enthalpy_j_kg"]
                env = self.net.registry.get(self.net.node_media[node]).state_pt(float(hyd.pressures[node]), p["ambient_temperature_k"])
                conductance = p["heat_loss_ua_w_k"] / fluid.cp_j_kg_k
                enthalpy = (old["mass_kg"] * old["enthalpy_j_kg"] + dt * (incoming_energy + p["power_w"] + conductance * env.enthalpy_j_kg)) / (mass + dt * (outgoing + conductance))
                new_fluid = self.net.registry.get(self.net.node_media[node]).state_ph(float(hyd.pressures[node]), enthalpy)
                next_volumes[eid] = {"mass_kg": mass, "enthalpy_j_kg": enthalpy, "density_kg_m3": new_fluid.density_kg_m3}
                maximum_change = max(maximum_change,
                    abs(mass - candidate[eid]["mass_kg"]) / max(1, mass),
                    abs(enthalpy - candidate[eid]["enthalpy_j_kg"]) / max(1, abs(enthalpy)),
                    abs(new_fluid.density_kg_m3 - candidate[eid]["density_kg_m3"]) / new_fluid.density_kg_m3)
            if maximum_change < 1e-10:
                break
            for eid, values in next_volumes.items():
                candidate[eid] = {key: 0.7 * value + 0.3 * candidate[eid][key] for key, value in values.items()}
            warm = (hyd, thermal)
        else:
            raise ConvergenceError("DYNAMIC_NOT_CONVERGED", "容积与网络状态未能在时间步内收敛")
        # Compute external fluxes before committing the candidate state.
        external_mass, external_energy = 0.0, float(sum(thermal.heat_w) + sum(thermal.power_w))
        elements = {e.id: e for e in self.project.elements}
        for node, ids in self.net.boundaries.items():
            for eid in ids:
                if eid in self.volumes:
                    p = self.net.parameters[eid]
                    current = candidate[eid]
                    fluid = self.net.registry.get(self.net.node_media[node]).state_ph(float(hyd.pressures[node]), current["enthalpy_j_kg"])
                    env = self.net.registry.get(self.net.node_media[node]).state_pt(float(hyd.pressures[node]), p["ambient_temperature_k"])
                    external_energy += p["power_w"] + p["heat_loss_ua_w_k"] / fluid.cp_j_kg_k * (env.enthalpy_j_kg - current["enthalpy_j_kg"])
                    continue
                q = thermal.boundary_flows[eid]
                external_mass += q
                boundary_h = thermal.enthalpies[node]
                if q > 0:
                    p = self.net.parameters[eid]
                    boundary_h = self.net.registry.get(self.net.node_media[node]).state_pt(float(hyd.pressures[node]), p.get("temperature_k", self.project.initial_temperature_k)).enthalpy_j_kg
                external_energy += q * boundary_h + thermal.boundary_heat.get(eid, 0.0)
        for b, q in zip(self.net.branches, hyd.flows):
            external_energy -= q * G * b.parameters.get("height_change_m", 0)
        # snapshot may itself detect a phase violation; build it before mutation.
        frame = snapshot(self.net, hyd, thermal, time.perf_counter() - started, outer,
                         self.time_s + dt, next_volumes)
        new_pipes = copy.deepcopy(thermal.pipes)
        self.volumes, self.pipes = next_volumes, new_pipes
        self.time_s += dt
        self.warm = (hyd, thermal)
        self.frame = frame
        new_mass, new_energy = self.inventory()
        self.frame["metrics"].update(
            mass_balance_step_kg=new_mass - old_mass - dt * external_mass,
            energy_balance_step_j=new_energy - old_energy - dt * external_energy,
            integration_iterations=iteration + 1, internal_dt_s=dt,
        )

    def _annotate(self):
        for eid, state in self.controllers.items():
            self.frame["elements"][eid] = {key: float(state[key]) for key in ("output", "error") if key in state}
        mass, energy = self.inventory()
        self.frame["metrics"].update(total_stored_mass_kg=mass, total_stored_energy_j=energy)
        self.frame["simulation_status"] = self.status

    def advance(self, dt_s=None):
        duration = self.dt_s if dt_s is None else dt_s
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("推进时长必须大于零")
        target = self.time_s + duration
        try:
            while self.time_s < target - 1e-10:
                self._controls()
                end = self._next_control_boundary(target)
                trial_dt = end - self.time_s
                for retry in range(20):
                    try:
                        self._attempt_step(trial_dt)
                        break
                    except TankEvent as event:
                        event_step = trial_dt * event.fraction * (1 - 1e-7)
                        if event_step > 1e-6:
                            try:
                                self._attempt_step(event_step)
                            except (TankEvent, ConvergenceError):
                                trial_dt *= 0.5
                                continue
                        self.status = "event"
                        self.frame["diagnostics"].append(event.diagnostic.to_dict())
                        self.events.append({"time_s": self.time_s, "type": "event", **event.diagnostic.to_dict()})
                        self._annotate()
                        return self.frame
                    except ConvergenceError:
                        trial_dt *= 0.5
                        if trial_dt < 1e-4:
                            raise
                else:
                    raise ConvergenceError("MINIMUM_STEP", "无法找到可收敛的内部时间步")
            self._annotate()
            return self.frame
        except ModelError as exc:
            self.status = "failed"
            self.frame = copy.deepcopy(self.frame)
            self.frame["diagnostics"].append(exc.diagnostic.to_dict())
            self.frame["simulation_status"] = "failed"
            self.frame["last_valid_state"] = True
            raise

    def step(self):
        frame = self.advance()
        if self.status not in {"event", "failed"}:
            self.status = "paused"
        self._annotate()
        return frame
