"""困液定容压力第一阶段原型（I0–I4）的纯函数、编译期与限定动态场景验收。

证据数字见 docs/numerics/results/I0.md–I4.md。范围硬边界：只支持 HEOS 纯水单相液体、
单一均匀容积、两端全关的被动段；I0–I4 不是“完整隔离段功能完成”，完整开闭周期属 I5–I9。
"""
import pytest

from fn_engine import trapped as tr
from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, FluidConfig, ModuleInstance, Project
from fn_engine.properties import property_service
from fn_engine.solver import SolveFailed, solve_dynamic, solve_steady
from fn_engine.simulation import SimulationSession

WATER = property_service(FluidConfig())
LAMINAR = {'length_m': 10., 'diameter_m': .01, 'roughness_m': 0.}
PARAMS = dict(volume_m3=.01, wall_heat_capacity_j_k=2000., initial_temperature_k=293.15,
              initial_pressure_pa=101325., heat_input_w=0., heat_loss_ua_w_k=0., ambient_temperature_k=293.15)


# ---------------------------------------------------------------- helpers

def _inst(instance_id, kind, **parameters):
    return ModuleInstance(id=instance_id, module_id=kind, name=instance_id, parameters=parameters)


def _link(cid, source, target):
    (si, sp), (ti, tp) = source.split(':'), target.split(':')
    return Connection(id=cid, source=Endpoint(instance_id=si, port_id=sp),
                      target=Endpoint(instance_id=ti, port_id=tp))


def spec_of(**overrides):
    params = dict(PARAMS) | overrides
    return tr.build_spec('CV1', 0, params, WATER)[0]


def state_of_spec(spec):
    return tr.initial_state(WATER, spec)


def trapped_project(fluid='Water', volume=None, wall=2000., t0=293.15, p0=101325., heat=0., ua=0.,
                    ambient=293.15, valve_open=False, extra_instances=(), extra_links=()):
    """B1 → L1 → V1(关) → CV → V2(关) → L2 → B2：两端关闭的被动段。"""
    cat = catalog_map()
    kinds = ['source', 'pipe', 'valve', 'closed_volume']
    instances = [
        _inst('B1', 'source', pressure_pa=200000., temperature_k=293.15),
        _inst('L1', 'pipe', **LAMINAR),
        _inst('V1', 'valve', kv_m3_h=1., opening_ratio=.5 if valve_open else 0.),
        _inst('CV1', 'closed_volume', volume_m3=.01 if volume is None else volume, wall_heat_capacity_j_k=wall,
              initial_temperature_k=t0, initial_pressure_pa=p0, heat_input_w=heat, heat_loss_ua_w_k=ua,
              ambient_temperature_k=ambient),
        _inst('V2', 'valve', kv_m3_h=1., opening_ratio=0.),
        _inst('L2', 'pipe', **LAMINAR),
        _inst('B2', 'source', pressure_pa=150000., temperature_k=293.15),
    ]
    links = [
        _link('e1', 'B1:out0', 'L1:in0'), _link('e2', 'L1:out0', 'V1:in0'), _link('e3', 'V1:out0', 'CV1:in0'),
        _link('e4', 'CV1:out0', 'V2:in0'), _link('e5', 'V2:out0', 'L2:in0'), _link('e6', 'L2:out0', 'B2:out0'),
    ]
    for item in extra_instances:
        kinds.append(item.module_id)
        instances.append(item)
    links.extend(extra_links)
    project = Project(id='trapped', name='trapped',
                      fluid=FluidConfig(fluid=fluid),
                      modules=[cat[k] for k in dict.fromkeys(kinds)],
                      instances=instances, connections=links)
    return project


def acceptance_case(duration=60., **kwargs):
    """运行 I4 验收算例，返回帧与编译后的网络。"""
    network = compile_project(trapped_project(**kwargs))
    return solve_dynamic(network, duration, 1.), network


def isochore_state(density, temperature):
    """独立 EOS 路径：固定 T 求 p 使 ρ(p,T)=density（PT flash，不经过 DU）。"""
    lo, hi = 1e5, 1e9
    for _ in range(80):
        mid = .5 * (lo + hi)
        if WATER.state_pt(mid, temperature).density_kg_m3 < density:
            lo = mid
        else:
            hi = mid
    return WATER.state_pt(.5 * (lo + hi), temperature)


# ---------------------------------------------------------------- I0：参考状态与积分原语

def test_initial_state_roundtrips_through_state_du():
    spec = spec_of()
    fluid = tr.state_of(WATER, spec, tr.initial_state(WATER, spec))
    assert fluid.pressure_pa == pytest.approx(101325., abs=1e-3)
    assert fluid.temperature_k == pytest.approx(293.15, abs=1e-6)
    assert fluid.density_kg_m3 == pytest.approx(spec.initial_mass_kg / spec.volume_m3, rel=1e-12)


def test_isochoric_pressure_rise_matches_independent_pt_flash():
    """恒温封闭：固定 V、M 时沿等容线改变 T，DU 逆算压力与独立 PT flash 吻合。"""
    # 50 MPa 起始密度（约 1020 kg/m³）高于 283–353 K 的饱和液密度，等容线全程保持单相压缩液。
    spec = spec_of(initial_pressure_pa=5.0e7)
    density = spec.initial_mass_kg / spec.volume_m3
    assert density > 1019.
    worst = 0.
    for temperature in (283.15, 293.15, 303.15, 323.15, 343.15, 353.15):
        reference = isochore_state(density, temperature)
        state = tr.TrappedState(spec.initial_mass_kg, spec.initial_mass_kg * reference.internal_energy_j_kg)
        fluid = tr.state_of(WATER, spec, state)
        worst = max(worst, abs(fluid.pressure_pa - reference.pressure_pa))
        assert abs(fluid.pressure_pa - reference.pressure_pa) <= max(10., 1e-5 * abs(reference.pressure_pa))
        assert fluid.temperature_k == pytest.approx(temperature, abs=1e-6)
    assert worst < .01  # I0 证据记录：最大压力闭合差远小于 10 Pa 门限


def test_adiabatic_isentropic_compression_reference_closes_the_du_path():
    """绝热压缩解析参照：独立 (p,s) 等熵路径构造压缩终态，再由 DU 逆算 p/T。

    刚性封闭体本身不做边界体积功，因此这里验证的是状态函数在压缩方向的闭合，不是定容运行算例。
    """
    start = WATER.state_pt(101325., 293.15)
    entropy = start.entropy_j_kg_k
    for ratio in (1.02, 1.05, 1.10):
        target = start.density_kg_m3 * ratio
        lo, hi = 101325., 5e8
        for _ in range(80):
            mid = .5 * (lo + hi)
            if WATER.state_ps(mid, entropy).density_kg_m3 < target:
                lo = mid
            else:
                hi = mid
        reference = WATER.state_ps(.5 * (lo + hi), entropy)
        spec = spec_of(volume_m3=1.0)  # 单位体积：M/V 直接取参照终态密度
        state = tr.TrappedState(reference.density_kg_m3,
                                reference.density_kg_m3 * reference.internal_energy_j_kg)
        fluid = tr.state_of(WATER, spec, state)
        assert fluid.density_kg_m3 == pytest.approx(reference.density_kg_m3, rel=1e-12)
        assert abs(fluid.pressure_pa - reference.pressure_pa) <= max(10., 1e-5 * abs(reference.pressure_pa))
        assert fluid.temperature_k == pytest.approx(reference.temperature_k, abs=1e-3)


def test_adiabatic_hold_keeps_mass_and_energy_exactly():
    spec = spec_of()
    state = tr.initial_state(WATER, spec)
    fluid = tr.state_of(WATER, spec, state)
    ledger = tr.TrappedLedger(initial_total_energy_j=tr.total_energy_j(spec, state, fluid))
    for _ in range(100):
        step = tr.advance(WATER, spec, state, 1.)
        state, ledger = step.state, tr.record_heat(ledger, step.heat_flow_w, 1.)
    assert state == tr.initial_state(WATER, spec)  # 绝热无热流：状态逐位不变
    assert tr.relative_mass_drift(spec, state) == 0.
    assert tr.energy_residual_j(ledger, spec, state, tr.state_of(WATER, spec, state)) == 0.


def test_heating_energy_ledger_and_wall_energy():
    spec = spec_of(heat_input_w=10000.)
    state = tr.initial_state(WATER, spec)
    fluid = tr.state_of(WATER, spec, state)
    ledger = tr.TrappedLedger(initial_total_energy_j=tr.total_energy_j(spec, state, fluid))
    for _ in range(60):
        step = tr.advance(WATER, spec, state, 1.)
        state, ledger = step.state, tr.record_heat(ledger, step.heat_flow_w, 1.)
    fluid = tr.state_of(WATER, spec, state)
    assert fluid.temperature_k > 293.15 and fluid.pressure_pa > 101325.
    assert ledger.cumulative_heat_j == pytest.approx(600000., rel=1e-12)
    assert tr.energy_residual_j(ledger, spec, state, fluid) == pytest.approx(0., abs=1e-3)  # 实测约 4e-6 J
    # 管壁与流体同温：管壁储能 = C_wall·(T − T_ref)，总储能 = U + 管壁储能。
    wall = tr.wall_energy_j(spec, fluid)
    assert wall == pytest.approx(2000. * (fluid.temperature_k - 293.15), rel=1e-12)
    assert tr.total_energy_j(spec, state, fluid) == pytest.approx(state.internal_energy_j + wall, rel=1e-12)


def test_cooling_with_heat_loss_matches_first_order_convergence():
    # 起始压力取 5 MPa，使 0.5–1 K 的定容冷却仍在单相液体范围内（近常压的饱和液冷却会闪发两相）。
    spec = spec_of(initial_temperature_k=323.15, initial_pressure_pa=5.0e6, heat_loss_ua_w_k=20.)
    start = tr.initial_state(WATER, spec)
    duration = 30.

    def run(dt):
        steps = int(round(duration / dt))
        state, ledger = start, tr.TrappedLedger(
            initial_total_energy_j=tr.total_energy_j(spec, start, tr.state_of(WATER, spec, start)))
        for _ in range(steps):
            step = tr.advance(WATER, spec, state, dt)
            state, ledger = step.state, tr.record_heat(ledger, step.heat_flow_w, dt)
        fluid = tr.state_of(WATER, spec, state)
        return fluid, tr.energy_residual_j(ledger, spec, state, fluid), tr.energy_scale_j(ledger, spec, state, fluid)

    reference, residual_reference, scale = run(duration / 384.)
    coarse, residual_coarse, _ = run(10.)
    fine, residual_fine, _ = run(1.25)
    assert reference.temperature_k < 323.15 and coarse.temperature_k < 323.15
    # 一阶隐式 Euler：coarse/fine 与细步参考的末温差随步长按比例缩小。
    ratio = abs(coarse.temperature_k - reference.temperature_k) / max(abs(fine.temperature_k - reference.temperature_k), 1e-15)
    assert 4. < ratio < 16., ratio
    for residual in (residual_reference, residual_coarse, residual_fine):
        assert abs(residual) <= max(1., 1e-6 * scale)


def test_two_phase_state_is_rejected():
    spec = spec_of(initial_temperature_k=373.0, initial_pressure_pa=500000.)
    assert tr.state_of(WATER, spec, tr.initial_state(WATER, spec)).phase == 'liquid'
    state = tr.initial_state(WATER, spec)
    with pytest.raises(tr.TrappedError) as error:
        tr.advance(WATER, spec, state, 1., heat_input_w=-20000.)
    assert error.value.code == tr.TRAPPED_PHASE_UNSUPPORTED
    assert '两相' in str(error.value) or 'twophase' in str(error.value)


def test_pressure_limit_is_rejected_without_clamping():
    spec = spec_of(initial_temperature_k=500., initial_pressure_pa=9.9e8)
    state = tr.initial_state(WATER, spec)
    with pytest.raises(tr.TrappedError) as error:
        tr.advance(WATER, spec, state, 1., heat_input_w=2.0e5)
    assert error.value.code == tr.TRAPPED_PRESSURE_LIMIT
    assert '1e+09' in str(error.value) or '1000000000' in str(error.value)


def test_initial_state_must_be_single_phase_liquid():
    params = dict(PARAMS, initial_temperature_k=400., initial_pressure_pa=50000.)
    with pytest.raises(tr.TrappedError) as error:
        tr.build_spec('CV1', 0, params, WATER)
    assert error.value.code == tr.TRAPPED_PHASE_UNSUPPORTED


def test_volume_must_be_given_explicitly():
    with pytest.raises(tr.TrappedError) as error:
        tr.build_spec('CV1', 0, dict(PARAMS, volume_m3=0.), WATER)
    assert error.value.code == tr.TRAPPED_VOLUME_REQUIRED


def test_initial_pressure_above_the_fluid_limit_is_rejected():
    with pytest.raises(tr.TrappedError) as error:
        tr.build_spec('CV1', 0, dict(PARAMS, initial_pressure_pa=1.5e9), WATER)
    assert error.value.code == tr.TRAPPED_INITIAL_STATE_INVALID
    assert 'p_max' in str(error.value) or '1000000000' in str(error.value) or '1e+09' in str(error.value)


@pytest.mark.parametrize('fluid', ['HEOS::R134a', 'IF97::Water'])
def test_only_heos_pure_water_is_accepted(fluid):
    service = property_service(FluidConfig(fluid=fluid))
    with pytest.raises(tr.TrappedError) as error:
        tr.build_spec('CV1', 0, PARAMS, service)
    assert error.value.code == tr.TRAPPED_FLUID_UNSUPPORTED


# ---------------------------------------------------------------- I1：编译期识别与拒绝

def test_closed_volume_compiles_and_supplies_the_pressure_reference():
    network = compile_project(trapped_project())
    spec = next(iter(network.trapped.values()))
    assert spec.instance_id == 'CV1'
    assert network.fixed_pressures[spec.node] == pytest.approx(101325.)
    assert network.fixed_temperatures[spec.node] == pytest.approx(293.15)
    assert any(d.code == 'TRAPPED_PROTOTYPE_ONLY' and d.severity == 'info' for d in network.diagnostics)
    # 稳态把封闭容积当成初态压力参考的大容器（定容状态只在动态步里积分），端口压力应等于初压。
    frame = solve_steady(network)
    assert frame.variables['CV1.in0.pressure_pa'] == pytest.approx(101325., abs=1e-3)
    assert 'CV1.state.pressure_pa' not in frame.variables  # 稳态不积分困液状态，不伪装成动态结果


def test_open_valve_at_start_is_rejected():
    with pytest.raises(CompilationError) as error:
        compile_project(trapped_project(valve_open=True))
    assert error.value.diagnostic.code == 'TRAPPED_NOT_CLOSED'
    assert 'V1' in str(error.value)


def test_mixing_with_an_open_tank_is_rejected():
    tank = _inst('TK1', 'tank', level_m=1., area_m2=.01, height_m=3.)
    with pytest.raises(CompilationError) as error:
        compile_project(trapped_project(extra_instances=(tank,)))
    assert error.value.diagnostic.code == 'TRAPPED_TANK_MIXED'


def _custom_project(instances, connections):
    cat = catalog_map()
    kinds = list(dict.fromkeys(kind for _, kind, _ in instances))
    return Project(id='custom', name='custom', modules=[cat[k] for k in kinds],
                   instances=[_inst(instance_id, kind, **params) for instance_id, kind, params in instances],
                   connections=[_link(f'e{n}', source, target) for n, (source, target) in enumerate(connections)])


def test_pressure_source_on_the_same_node_is_rejected():
    # B1 直接接在 CV 入口节点：压力边界与困液容积争同一个压力参考。
    project = _custom_project([
        ('B1', 'source', {'pressure_pa': 200000., 'temperature_k': 293.15}),
        ('V1', 'valve', {'kv_m3_h': 1., 'opening_ratio': 0.}),
        ('L1', 'pipe', LAMINAR),
        ('B2', 'source', {'pressure_pa': 150000., 'temperature_k': 293.15}),
        ('CV1', 'closed_volume', PARAMS),
    ], [('B1:out0', 'CV1:in0'), ('CV1:out0', 'V1:in0'), ('V1:out0', 'L1:in0'), ('L1:out0', 'B2:out0')])
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'TRAPPED_PRESSURE_REFERENCE_CONFLICT'


def test_two_volumes_in_series_are_rejected():
    # 两个封闭容积经关闭阀门分隔，各自仍是单节点；第一阶段只允许一个。
    project = _custom_project([
        ('B1', 'source', {'pressure_pa': 200000., 'temperature_k': 293.15}),
        ('B2', 'source', {'pressure_pa': 150000., 'temperature_k': 293.15}),
        ('L1', 'pipe', LAMINAR), ('L2', 'pipe', LAMINAR),
        ('J1', 'junction', {'elevation_m': 0.}), ('J2', 'junction', {'elevation_m': 0.}),
        ('V1', 'valve', {'kv_m3_h': 1., 'opening_ratio': 0.}),
        ('V2', 'valve', {'kv_m3_h': 1., 'opening_ratio': 0.}),
        ('V3', 'valve', {'kv_m3_h': 1., 'opening_ratio': 0.}),
        ('V4', 'valve', {'kv_m3_h': 1., 'opening_ratio': 0.}),
        ('CV1', 'closed_volume', PARAMS),
        ('CV2', 'closed_volume', PARAMS),
    ], [('B1:out0', 'L1:in0'), ('L1:out0', 'J1:in0'), ('J1:out0', 'V1:in0'), ('V1:out0', 'CV1:in0'),
        ('CV1:out0', 'V2:in0'), ('V2:out0', 'J2:in0'), ('J2:out0', 'L2:in0'), ('L2:out0', 'B2:out0'),
        ('J1:out1', 'V3:in0'), ('V3:out0', 'CV2:in0'), ('CV2:out0', 'V4:in0'), ('V4:out0', 'J2:out1')])
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'TRAPPED_MULTIVOLUME_UNSUPPORTED'


def test_missing_volume_is_rejected_at_compile_time():
    with pytest.raises(CompilationError) as error:
        compile_project(trapped_project(volume=0.))
    assert error.value.diagnostic.code == 'TRAPPED_VOLUME_REQUIRED'


def test_non_heos_project_fluid_is_rejected_at_compile_time():
    with pytest.raises(CompilationError) as error:
        compile_project(trapped_project(fluid='HEOS::R134a'))
    assert error.value.diagnostic.code in {'TRAPPED_FLUID_UNSUPPORTED', 'PHASE_UNSUPPORTED', 'PROPERTY_FAILURE'}


# ---------------------------------------------------------------- I2/I3：限定动态场景与守恒门

def _gates(frame, service=WATER):
    """冻结的 I2 数值门：质量漂移、能量账本残差、独立 EOS 路径压力闭合。

    独立路径是 PT flash 按 ρ(p,T)=M/V 反解等容压力（不经过 state_du），因此能发现 DU 逆算的
    系统性偏差，而不是用同一条 DU 路径自证。
    """
    scale = frame.metrics['trapped_energy_scale_j']
    residual = frame.metrics['trapped_energy_residual_j']
    pressure = frame.variables['CV1.state.pressure_pa']
    temperature = frame.variables['CV1.state.temperature_k']
    density = frame.metrics['trapped_density_kg_m3']
    reference = isochore_state(density, temperature)
    return {
        'mass_drift': abs(frame.metrics['trapped_relative_mass_drift']),
        'mass_gate': 1e-10,
        'residual': abs(residual),
        'residual_gate': max(1., 1e-6 * scale),
        'pressure_difference': abs(pressure - reference.pressure_pa),
        'pressure_gate': max(10., 1e-5 * abs(reference.pressure_pa)),
        'scale': scale,
        'reference': reference.pressure_pa,
    }


def test_closed_heating_run_meets_the_conservation_gates():
    frames, _ = acceptance_case(heat=20000.)
    assert len(frames) == 61
    worst_residual = max_scale = worst_pressure = max_reference = 0.
    for frame in frames:
        gates = _gates(frame)
        assert gates['mass_drift'] <= gates['mass_gate']
        assert gates['residual'] <= gates['residual_gate']
        assert gates['pressure_difference'] <= gates['pressure_gate']
        worst_residual = max(worst_residual, gates['residual'])
        max_scale = max(max_scale, gates['scale'])
        worst_pressure = max(worst_pressure, gates['pressure_difference'])
        max_reference = max(max_reference, abs(gates['reference']))
    assert worst_residual <= max(1., 1e-6 * max_scale)
    assert worst_pressure <= max(10., 1e-5 * max_reference)
    first, last = frames[0], frames[-1]
    assert first.variables['CV1.state.pressure_pa'] == pytest.approx(101325., abs=.1)
    assert last.variables['CV1.state.temperature_k'] > 300.
    assert last.variables['CV1.state.cumulative_heat_j'] == pytest.approx(20000. * 60., rel=1e-12)


def test_heat_loss_run_meets_the_conservation_gates():
    # 5 MPa 起的定容散热：0.5 K 级温降对应约 0.6 MPa 压降，仍保持单相液体。
    frames, _ = acceptance_case(t0=323.15, p0=5.0e6, ua=20., ambient=313.15, duration=120.)
    assert frames[-1].variables['CV1.state.temperature_k'] < 323.15
    assert frames[-1].variables['CV1.state.pressure_pa'] < frames[0].variables['CV1.state.pressure_pa']
    for frame in frames:
        gates = _gates(frame)
        assert gates['mass_drift'] <= gates['mass_gate']
        assert gates['residual'] <= gates['residual_gate']
        assert gates['pressure_difference'] <= gates['pressure_gate']


def test_runtime_reopening_is_rejected_before_effect_with_a_release_ledger():
    session = SimulationSession(compile_project(trapped_project(heat=10000.)), 20., 1.)
    try:
        session.initialize()
        session.advance()
        trapped_before = session.trapped[3]
        ledger_before = session.trapped_ledgers[3]
        pressure_before = session.snapshot().variables['CV1.state.pressure_pa']
        with pytest.raises(CompilationError) as error:
            session.set_parameter('V1', 'opening_ratio', .5)
        assert error.value.diagnostic.code == 'TRAPPED_OPEN_UNSUPPORTED'
        message = str(error.value)
        assert '释放账本' in message and 'I5–I9' in message
        assert 'M=' in message and 'p=' in message
        # 拒绝发生在生效前：accepted 库存与账本不变，阀门仍关。
        assert session.trapped[3] == trapped_before
        assert session.trapped_ledgers[3] == ledger_before
        assert next(b for b in session.network.branches if b.instance_id == 'V1').closed is True
        # 被拒绝的开阀请求不会污染后续推进：状态仍按定容热量收支前进。
        frame = session.advance()
        assert frame.variables['CV1.state.pressure_pa'] > pressure_before
    finally:
        session.close()


def test_failed_substep_does_not_commit_the_trapped_state():
    """冷却到两相：失败子步不提交，帧时间与库存停在最后一次 accepted 状态。"""
    with pytest.raises(SolveFailed) as error:
        solve_dynamic(compile_project(trapped_project(t0=373.0, p0=500000., heat=-20000.)), 10., 1.)
    assert error.value.diagnostic.code == tr.TRAPPED_PHASE_UNSUPPORTED
    frames = error.value.frames
    assert frames and frames[-1].time_s == 0.
    frame = frames[-1]
    assert frame.metrics['trapped_energy_residual_j'] == 0.
    assert abs(frame.metrics['trapped_relative_mass_drift']) <= 1e-10
    assert frame.variables['CV1.state.temperature_k'] == pytest.approx(373.0, abs=1e-6)


def test_pressure_limit_stops_and_keeps_the_accepted_history():
    with pytest.raises(SolveFailed) as error:
        solve_dynamic(compile_project(trapped_project(t0=500., p0=9.9e8, heat=1.0e5)), 10., 1.)
    assert error.value.diagnostic.code == tr.TRAPPED_PRESSURE_LIMIT
    frames = error.value.frames
    assert frames[-1].time_s < 10.
    assert frames[-1].variables['CV1.state.pressure_pa'] <= 1e9
    for frame in frames:
        gates = _gates(frame)
        assert gates['residual'] <= gates['residual_gate']


def test_frames_expose_the_trapped_state_and_the_prototype_scope():
    frames, _ = acceptance_case(duration=5.)
    frame = frames[-1]
    for key in ('CV1.state.pressure_pa', 'CV1.state.temperature_k', 'CV1.state.mass_kg',
                'CV1.state.volume_m3', 'CV1.state.internal_energy_j', 'CV1.state.total_energy_j',
                'CV1.state.cumulative_heat_j', 'CV1.state.relative_mass_drift'):
        assert key in frame.variables
    for key in ('trapped_mass_kg', 'trapped_pressure_pa', 'trapped_temperature_k',
                'trapped_energy_residual_j', 'trapped_energy_scale_j', 'trapped_relative_mass_drift'):
        assert key in frame.metrics
    codes = {d.code for d in frame.diagnostics}
    assert 'TRAPPED_PROTOTYPE_ONLY' in codes
    assert 'DYNAMIC_IMPLICIT_EULER' in codes
    # 能力边界写进每一帧：只标“单容积封闭原型”，不标“完整隔离段功能完成”。
    prototype = next(d for d in frame.diagnostics if d.code == 'TRAPPED_PROTOTYPE_ONLY')
    assert 'I0–I4' in prototype.message and 'I5–I9' not in prototype.message
    assert '完整开闭周期' in prototype.message


def test_setting_trapped_heat_input_at_runtime_is_applied():
    session = SimulationSession(compile_project(trapped_project()), 10., 1.)
    try:
        session.initialize()
        session.advance()
        before = session.trapped_ledgers[3]
        session.set_parameter('CV1', 'heat_input_w', 50000.)
        session.advance()
        assert session.trapped_ledgers[3].cumulative_heat_j > before.cumulative_heat_j
        frame = session.snapshot()
        assert frame.metrics['trapped_temperature_k'] > 293.15
    finally:
        session.close()
