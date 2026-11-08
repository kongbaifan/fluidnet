"""Native fluid/air step doubling; speculative paths never promote controls or ledgers."""
from copy import copy, deepcopy
import math

from . import solver as s
from .compiler import CompilationError
from .timestep import TrialFailure, TimeStepExhausted, normalized_error


def initialize_coordinates(session):
    # Freeze enthalpy zero points and equivalent cell masses at the initial state.
    # They are error scales only; the actual thermal equations retain their own coefficients.
    session._adaptive_tank_h0 = {n: v.enthalpy_j_kg for n, v in session.tanks.items()}
    session._adaptive_cell_scales = {}
    thermal = session.result.thermal
    for j, values in session.cells.items():
        branch = session.network.branches[j]
        p = session.network.parameters[branch.instance_id]
        state = thermal.node_states[thermal.upstream[j]]
        definition = session.network.modules[session.network.instances[branch.instance_id].module_id]
        if definition.solver_model == 'closed_buffer_tank':
            mass = p['mass_kg']
        else:
            volume = math.pi * p['diameter_m'] ** 2 / 4. * p['length_m']
            mass = (state.density_kg_m3 * volume + p.get('wall_heat_capacity_j_k', 0.) /
                    state.specific_heat_j_kg_k) / len(values)
        session._adaptive_cell_scales[j] = (mass, list(values))
    initial, _ = coordinates(session)
    session._adaptive_energy_reference = initial


def coordinates(session):
    values, categories = [], []
    def add(value, category):
        values.append(float(value)); categories.append(category)
    for node, state in session.tanks.items():
        add(state.mass_kg, 'mass')
        add(state.mass_kg * (state.enthalpy_j_kg - session._adaptive_tank_h0[node]), 'energy')
    for j, enthalpies in session.cells.items():
        mass, reference = session._adaptive_cell_scales[j]
        for enthalpy, initial in zip(enthalpies, reference, strict=True):
            add(mass * (enthalpy - initial), 'energy')
    for state in session.trapped.values():
        add(state.mass_kg, 'mass'); add(state.internal_energy_j, 'energy')
    for node, state in session.air_rooms.items():
        spec = session.network.air_rooms[node]
        p = session.network.parameters[spec.instance_id]
        add(spec.dry_air_mass_kg * state.humidity_ratio_kg_kg, 'mass')
        add(spec.dry_air_mass_kg * state.enthalpy_j_kg_dry_air +
            p['additional_heat_capacity_j_k'] * (state.temperature_k - 273.15), 'energy')
        add(state.temperature_k, 'temperature')
    return values, categories


def stage(session, trial, h):
    candidate = copy(session)
    candidate.time = session.time + h
    candidate.view, candidate.result, candidate.tanks, candidate.cells, trapped = trial
    candidate.trapped, candidate.trapped_ledgers = trapped
    candidate.air_rooms = {node: item.state for node, item in
                           getattr(candidate.result.thermal, 'air_room_results', {}).items()}
    return candidate


def advance_segment(session, segment):
    """Publish both fine steps only after the whole control/output segment succeeds."""
    worker = copy(session)
    worker.scripts = {key: copy(value) for key, value in session.scripts.items()}
    worker.diagnostics = list(session.diagnostics)
    worker.committed = dict(session.committed)
    worker._control_base = None
    stats_before, next_h = deepcopy(session.step_stats), session.march._next_h

    def trial(h):
        try:
            full = worker._trial(h)
            half = worker._trial(h / 2.)
            middle = stage(worker, half, h / 2.)
            fine = middle._trial(h / 2.)
            for candidate in (full, half, fine):
                event = s._tank_event(worker.network, candidate[2], worker.service)
                if event:
                    code, spec = event
                    raise TrialFailure(f'{code}: {spec.instance_id} 达到液位边界')
        except (CompilationError, ValueError) as failure:
            diagnostic = getattr(failure, 'diagnostic', None)
            # Range checks cannot be bypassed by accepting an out-of-domain trial.
            if s._retryable(failure) or diagnostic and diagnostic.code.startswith(('TRAPPED_', 'AIR_ROOM_')):
                raise TrialFailure(failure) from failure
            raise
        old, categories = coordinates(worker)
        full_values, _ = coordinates(stage(worker, full, h))
        fine_values, _ = coordinates(stage(middle, fine, h / 2.))
        reference = [value if category == 'energy' else 0. for value, category in
                     zip(session._adaptive_energy_reference, categories, strict=True)]
        error = normalized_error(old, full_values, fine_values, categories=categories,
            atol={category: session.timestep.atol(category) for category in set(categories)},
            rtol=session.timestep.rtol, references=reference)
        return (half, fine), error

    def accept(payload, h, error):
        # All devices here are native: no process-owned author state may be promoted speculatively.
        for candidate in payload:
            worker._accept(h / 2., *candidate)

    try:
        session.march.march(segment, trial, accept, time=session.time)
    except Exception as error:
        failed = session.step_stats
        session.step_stats = stats_before
        for key in ('rejected', 'solver_failures', 'min_step_hits', 'max_error_norm',
                    'frame_rejected', 'frame_solver_failures', 'frame_max_error'):
            setattr(session.step_stats, key, getattr(failed, key))
        session.march.stats = session.step_stats
        session.march._next_h = next_h
        if isinstance(error, TimeStepExhausted):
            raise s.SolveFailed(error.code, str(error), frames=list(session.frames)) from error
        raise
    # The acceptance loop has now recorded every accepted pair of fine steps.
    # Preserve those final statistics in partial history if a later segment fails.
    worker.last_accepted_frame = worker.snapshot()
    for key in ('time', 'view', 'result', 'tanks', 'cells', 'trapped', 'trapped_ledgers',
                'committed', 'diagnostics', 'air_rooms', 'air_accumulators', 'last_accepted_frame'):
        setattr(session, key, getattr(worker, key))
    for key, script in session.scripts.items():
        for field in ('state', 'pending', 'next_s', 'last_s', 'samples', 'last_values'):
            setattr(script, field, getattr(worker.scripts[key], field))
    session._control_base = None
