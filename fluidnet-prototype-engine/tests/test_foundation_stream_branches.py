"""Real reservoir-boundary branches, hydrostatic ports and conserved fluxes."""
import pytest

from fn_engine.catalog import catalog_map
from fn_engine.compiler import CompilationError, compile_project
from fn_engine.models import Connection, Endpoint, ModuleInstance
from fn_engine.refrigeration.stream_example import stream_example
from fn_engine.solver import solve_dynamic


def branch_project(tap=False):
    catalog = catalog_map()
    project = stream_example(True)
    project.instances.extend([
        ModuleInstance(id='HighSplit', module_id='refrigerant_header', name='独立供液分支'),
        ModuleInstance(id='FlashBranch', module_id='enthalpy_valve', name='闪发支路',
                       parameters={'kv_m3_h': .005}),
    ])
    next(i for i in project.instances if i.id == 'Low').module_id = 'lp_drum_multi'
    edge = next(e for e in project.connections
                if e.source.instance_id == 'High' and e.source.port_id == 'liquid')
    target = edge.target.model_copy(deep=True)
    edge.target = Endpoint(instance_id='HighSplit', port_id='in0')
    project.connections.extend([
        Connection(id='split-subcooler', source=Endpoint(instance_id='HighSplit', port_id='out0'), target=target),
        Connection(id='split-flash', source=Endpoint(instance_id='HighSplit', port_id='out1'),
                   target=Endpoint(instance_id='FlashBranch', port_id='in0')),
        Connection(id='flash-low', source=Endpoint(instance_id='FlashBranch', port_id='out0'),
                   target=Endpoint(instance_id='Low', port_id='in2')),
    ])
    if tap:
        high = next(i for i in project.instances if i.id == 'High')
        high.module_id = 'headed_receiver'
        allowed = {p.id for p in catalog[high.module_id].parameters}
        high.parameters = {k: v for k, v in high.parameters.items() if k in allowed}
        edge.source.port_id = 'tap0'
    project.modules = [m for key, m in catalog.items()
                       if key in {i.module_id for i in project.instances}]
    return project


@pytest.mark.parametrize('tap', [False, True])
def test_two_independent_paths_share_exactly_one_reservoir_inventory(tap):
    network = compile_project(branch_project(tap))
    assert network.stream_paths['Valve']['source'][0] == 'High'
    assert network.stream_paths['FlashBranch']['source'][0] == 'High'
    frames = solve_dynamic(network, .2, .2)
    assert frames[-1].valid
    for frame in frames:
        assert abs(frame.metrics['mass_residual_kg_circuit0']) < 1e-8
        assert abs(frame.metrics['energy_residual_j']) < .05
        v = frame.variables
        assert v['Valve.inlet_enthalpy_j_kg'] == v['Subcooler.outlet_enthalpy_j_kg']
        assert v['FlashBranch.inlet_enthalpy_j_kg'] == v['High.liquid_enthalpy_j_kg']


def test_hydrostatic_head_reaches_each_branch_without_changing_source_phase_enthalpy():
    frame = solve_dynamic(compile_project(branch_project(True)), .1, .1)[0]
    v = frame.variables
    expected = v['High.state.pressure_pa'] + v['High.liquid_density_kg_m3'] * 9.80665 * (
        v['High.state.level_m'] - v['High.param.tap0_height_ratio'] * v['High.param.diameter_m'])
    assert v['FlashBranch.inlet_pressure_pa'] == pytest.approx(expected)
    assert v['Subcooler.inlet_pressure_pa'] == pytest.approx(expected)
    assert v['FlashBranch.outlet_enthalpy_j_kg'] == v['High.liquid_enthalpy_j_kg']


def test_closing_one_branch_does_not_close_the_other():
    open_project = branch_project()
    closed_project = open_project.model_copy(deep=True)
    next(i for i in closed_project.instances if i.id == 'FlashBranch').parameters['opening_ratio'] = 0.
    a = solve_dynamic(compile_project(open_project), .1, .1)[0].variables
    b = solve_dynamic(compile_project(closed_project), .1, .1)[0].variables
    assert b['FlashBranch.mass_flow_kg_s'] == 0.
    assert b['Valve.mass_flow_kg_s'] == pytest.approx(a['Valve.mass_flow_kg_s'], rel=1e-12)


def test_shared_finite_pipe_requires_graph_hydraulics_instead_of_duplicate_evaluation():
    project = branch_project()
    project.instances.append(ModuleInstance(id='SharedPipe', module_id='refrigerant_line', name='共享管'))
    edge = next(e for e in project.connections if e.target.instance_id == 'HighSplit')
    edge.target = Endpoint(instance_id='SharedPipe', port_id='in0')
    project.connections.append(Connection(id='shared-split', source=Endpoint(instance_id='SharedPipe', port_id='out0'),
                                          target=Endpoint(instance_id='HighSplit', port_id='in0')))
    project.modules.append(catalog_map()['refrigerant_line'])
    with pytest.raises(CompilationError) as error:
        compile_project(project)
    assert error.value.diagnostic.code == 'STREAM_SERIAL_REQUIRED'
