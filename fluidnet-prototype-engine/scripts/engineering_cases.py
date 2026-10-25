"""Repository-derived acceptance cases; no field calibration or saved user data."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path

from fn_engine.catalog import catalog_map
from fn_engine.examples import pid_example
from fn_engine.models import Connection, Endpoint, ModuleInstance, Project
from fn_engine.module_templates import create_template
from fn_engine.packages import load_module_package
from fn_engine.refrigeration.examples import station_case
from numerics_cases import assemble, dual_loop_project, grid_junction

ROOT = Path(__file__).resolve().parents[1]
CASE_IDS = ('distribution-24', 'distribution-96', 'fan-coil-dynamic',
            'water-glycol-exchanger', 'pid-tank', 'nh3-co2-control')


@dataclass
class EngineeringCase:
    id: str
    name: str
    project: Project
    kind: str = 'steady'
    duration_s: float = 0.
    dt_s: float = 1.
    events: list[dict] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    origin: str = 'repository-derived reference; not field-calibrated'


def parallel_distribution(count: int, *, coils: bool = False) -> Project:
    module = load_module_package(ROOT / 'modules' / ('fan_coil_unit_sdk' if coils else 'programmable_valve_sdk'))
    manifold = grid_junction(count + 1)
    temperature = 285.15 if coils else 293.15
    nodes = [
        ('B1', 'source', {'pressure_pa': 201325., 'temperature_k': temperature}),
        ('B2', 'source', {'pressure_pa': 201325., 'temperature_k': temperature}),
        ('P1', 'pump', {'head_curve': [[0., 32.], [count * 3., 20.], [count * 8., 0.]]}),
        ('L0', 'pipe', {'length_m': 10., 'diameter_m': .15 if count <= 24 else .25}),
        ('JS', manifold.id, {}), ('JR', manifold.id, {}),
    ]
    edges = [('B1:out0', 'P1:in0'), ('P1:out0', 'L0:in0'), ('L0:out0', 'JS:p0'), ('JR:p0', 'B2:out0')]
    for index in range(1, count + 1):
        pipe = {'length_m': 10. + 5. * (index % 4), 'diameter_m': .032 + .004 * (index % 3), 'roughness_m': 1e-5}
        if coils:
            pipe.update(thermal_cells=4, wall_heat_capacity_j_k=5000.)
        parameters = {} if coils else {'kv_m3_h': 8. + 2. * (index % 4), 'opening_ratio': .35 + .1 * (index % 5)}
        nodes += [(f'L{index}', 'pipe', pipe), (f'D{index}', module.id, parameters)]
        edges += [(f'JS:p{index}', f'L{index}:in0'), (f'L{index}:out0', f'D{index}:in0'),
                  (f'D{index}:out0', f'JR:p{index}')]
    project = assemble(f'engineering-distribution-{count}', nodes, edges, [manifold, module])
    project.solver.thermal = coils
    project.solver.property_coupling = 'node' if coils else 'reference'
    return project


def water_glycol_exchanger() -> Project:
    project = dual_loop_project(4)
    exchanger = create_template('heat_exchanger', 'engineering_dual_hx', '水/乙二醇 SDK 双侧换热器')
    old = next(instance for instance in project.instances if instance.id == 'HX')
    old.module_id = exchanger.id
    old.parameters = {'diameter_m': .04, 'loss_coefficient': 10., 'ua_w_k': 4000.}
    project.modules = [m for m in project.modules if m.id != 'exchanger'] + [exchanger, catalog_map()['valve']]
    mapping = {'in0': 'hot_in', 'out0': 'hot_out', 'in1': 'cold_in', 'out1': 'cold_out'}
    for connection in project.connections:
        for endpoint in (connection.source, connection.target):
            if endpoint.instance_id == 'HX':
                endpoint.port_id = mapping[endpoint.port_id]
    for side, boundary in [('h', 'BH'), ('c', 'BC')]:
        valve_id = 'V' + side
        project.instances.append(ModuleInstance(id=valve_id, module_id='valve', name=valve_id,
            parameters={'kv_m3_h': 30., 'opening_ratio': .8}))
        connection = next(c for c in project.connections if c.source.instance_id == boundary)
        connection.source = Endpoint(instance_id=valve_id, port_id='out0')
        project.connections.append(Connection(id='boundary-' + side, source=Endpoint(instance_id=boundary, port_id='out0'),
            target=Endpoint(instance_id=valve_id, port_id='in0')))
    project.solver.property_coupling = 'node'
    return project


def build_case(identifier: str) -> EngineeringCase:
    if identifier in ('distribution-24', 'distribution-96'):
        count = int(identifier.rsplit('-', 1)[-1])
        case = EngineeringCase(identifier, f'{count} 支路泵阀配水网络', parallel_distribution(count),
            sources=['scripts/acceptance_cases.py:parallel', 'scripts/numerics_cases.py:grid_junction',
                     'modules/programmable_valve_sdk'],
            assumptions=['并联支路由参考拓扑扩展；管径 32–40 mm、管长 10–25 m。',
                         '泵曲线按支路数声明缩放，不代表厂家标定。模块源码、版本及能力声明原样保留。'],
            checks=['node_mass_balance', 'pump_branch_mass', 'independent_valve_kv'])
    elif identifier == 'fan-coil-dynamic':
        case = EngineeringCase(identifier, '8 支路风机盘管、管壁/流体热容与泵速阶跃',
            parallel_distribution(8, coils=True), 'dynamic', 20., 1.,
            events=[{'time_s': 10., 'instance_id': 'P1', 'parameter_id': 'speed_ratio', 'value': .65}],
            sources=['modules/fan_coil_unit_sdk', 'scripts/acceptance_cases.py:parallel'],
            assumptions=['水侧入口 12 °C，8 个原版 SDK 风机盘管，每条管路 4 个热容单元。',
                         '10 s 时通过公开运行参数接口将泵速从 1 调到 0.65；未修改只读模块参数。'],
            checks=['node_mass_balance', 'module_energy_ledger', 'independent_coil_ntu'])
    elif identifier == 'water-glycol-exchanger':
        case = EngineeringCase(identifier, '水/30% 乙二醇双侧换热与热侧阀位阶跃', water_glycol_exchanger(),
            'dynamic', 20., 1.,
            events=[{'time_s': 10., 'instance_id': 'Vh', 'parameter_id': 'opening_ratio', 'value': .45}],
            sources=['scripts/numerics_cases.py:dual_loop_project', 'examples/module_templates/dual_heat_exchanger.py'],
            assumptions=['使用原版双侧换热模板，UA=4000 W/K、直径 40 mm、K=10。',
                         '保持原案例工质和边界温度；新增内置阀门，通过阀位改变热侧流量。'],
            checks=['node_mass_balance', 'module_energy_ledger', 'independent_exchanger_ntu', 'two_fluids'])
    elif identifier == 'pid-tank':
        project = pid_example('level')
        module = load_module_package(ROOT / 'modules/programmable_valve_sdk')
        # The shipped SDK valve is read-only. Keep the controlled inlet builtin;
        # the Python outlet still observes changing head and accumulates mass.
        next(i for i in project.instances if i.id == 'V2').module_id = module.id
        project.modules.append(module)
        case = EngineeringCase(identifier, 'PID 液位控制与 Python 出口阀', project, 'dynamic', 30., .5,
            sources=['backend/fn_engine/examples.py:pid_example(level)', 'modules/programmable_valve_sdk'],
            assumptions=['PID 仍控制内置入口阀；Python 出口阀保留只读契约。',
                         '30 s 用于检查控制响应和逐子步质量账本，不作为最终调节时间验收。'],
            checks=['node_mass_balance', 'tank_mass_ledger', 'module_mass_ledger', 'pid_response'])
    elif identifier == 'nh3-co2-control':
        case = EngineeringCase(identifier, 'NH₃/CO₂ 制冷站执行域对照', station_case(), 'scope-control', 60., 10.,
            sources=['backend/fn_engine/refrigeration/examples.py:station_case', 'cases/cold-storage/nh3-co2/station'],
            assumptions=['使用 B 版设计点、五个 PID 回路及原版上层控制脚本。',
                         '制冷站执行域不使用通用水力模块求导/缓存，结果只作执行域对照，不宣称优化收益。'],
            checks=['domain_control'])
    else:
        raise ValueError(f'未知工程案例：{identifier}')
    case.project.solver.hydraulic_method = 'auto'
    case.project.solver.hydraulic_diagnostics = True
    case.project.solver.dynamic_step_s = case.dt_s
    case.project.solver.module_cache = False
    case.project.solver.module_mixed_jacobian = False
    case.project = Project.model_validate(case.project.model_dump(mode='json'))
    return case


def imported_case(path: Path, duration_s: float = 0., dt_s: float = 1.) -> EngineeringCase:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('format') == 'fluidnet-studio-prototype':
        from fn_engine.bridge import normalize_prototype_export
        project = normalize_prototype_export(payload)
    else:
        project = Project.model_validate(payload.get('project', payload))
    return EngineeringCase('imported-project', project.name, project, 'dynamic' if duration_s else 'steady',
        duration_s, dt_s, sources=[str(path.resolve())], assumptions=['仅修改本轮对照的求导/缓存和 Worker 分片选项；不升级模块。'],
        checks=['node_mass_balance'], origin='user-supplied project; external calibration not independently established')
