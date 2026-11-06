from copy import deepcopy

import numpy as np
import pytest

from fn_engine.compiler import compile_project, CompilationError
from fn_engine.hydronic_buffer_example import example
from fn_engine.simulation import SimulationSession
from fn_engine.solver import solve_steady


@pytest.mark.parametrize('reverse',[False,True])
def test_air_water_buffer_energy_storage_and_moisture_share_acceptance(reverse):
    session=SimulationSession(compile_project(example(reverse=reverse)),1.,1.)
    try:
        first=session.initialize();last=session.advance();v=last.variables
        assert v['Buffer.state.mass_kg']==30.
        q=v['Buffer.mass_flow_kg_s'];incoming,outgoing=('out0','in0') if q<0 else ('in0','out0')
        transport=abs(q)*(v[f'Buffer.{incoming}.enthalpy_j_kg']-v[f'Buffer.{outgoing}.enthalpy_j_kg'])
        stored=v['Buffer.state.stored_energy_j']-first.variables['Buffer.state.stored_energy_j']
        assert stored==pytest.approx(transport-v['Buffer.ambient_heat_loss_w'],abs=.02)
        assert abs(v['Buffer.energy_residual_w'])<.001
        assert abs(last.metrics['energy_residual_w'])<.1
        assert abs(last.metrics['moisture_residual_kg_s'])<1e-7
        assert v['Coil.water_heat_w']>0
    finally:session.close()


def test_stagnant_store_changes_without_water_transport():
    session=SimulationSession(compile_project(example(stagnant=True)),1.,1.)
    try:
        first=session.initialize();last=session.advance();v=last.variables
        assert abs(v['Buffer.mass_flow_kg_s'])<1e-8
        assert v['Buffer.state.stored_energy_j']>first.variables['Buffer.state.stored_energy_j']
        assert v['Buffer.state.stored_power_w']==pytest.approx(-v['Buffer.ambient_heat_loss_w'],abs=.001)
    finally:session.close()


def test_failed_step_cannot_advance_buffer_or_air_results(monkeypatch):
    session=SimulationSession(compile_project(example()),1.,1.)
    try:
        initial=session.initialize();old=deepcopy(session.cells);trial=session._trial(1.)
        original=SimulationSession.snapshot
        def reject(self):
            result=original(self);result.valid=False;return result
        monkeypatch.setattr(SimulationSession,'snapshot',reject)
        with pytest.raises(CompilationError):session._accept(1.,*trial)
        assert session.time==0 and session.last_accepted_frame==initial
        assert all(np.array_equal(session.cells[k],v) for k,v in old.items())
    finally:session.close()


def test_buffer_is_not_an_air_device_or_steady_temperature_source():
    with pytest.raises(CompilationError,match='动态'):solve_steady(compile_project(example()))
    p=example();p.circuit_fluids=[]
    with pytest.raises(CompilationError):compile_project(p)


def test_room_and_buffer_trials_roll_back_together_in_three_circuit_system(monkeypatch):
    from fn_engine.chiller_examples import chiller_air_example
    from fn_engine.catalog import catalog_map
    from fn_engine.models import ModuleInstance, Connection, Endpoint
    p=chiller_air_example();p.modules.append(catalog_map()['hydronic_buffer_tank'])
    p.instances.append(ModuleInstance(id='Buffer',module_id='hydronic_buffer_tank',name='冷冻水缓冲',
        parameters={'mass_kg':100.,'temperature_k':285.15}))
    connection=next(c for c in p.connections if c.source.instance_id=='Chiller' and c.source.port_id=='out0')
    end=connection.target;connection.target=Endpoint(instance_id='Buffer',port_id='in0')
    p.connections.append(Connection(id='buffer-out',source=Endpoint(instance_id='Buffer',port_id='out0'),target=end))
    p.solver.dynamic_step_s=1.
    session=SimulationSession(compile_project(p),1.,1.)
    try:
        first=session.initialize();rooms=deepcopy(session.air_rooms);cells=deepcopy(session.cells);trial=session._trial(1.)
        original=SimulationSession.snapshot
        def reject(self):
            frame=original(self);frame.valid=False;return frame
        with monkeypatch.context() as mock:
            mock.setattr(SimulationSession,'snapshot',reject)
            with pytest.raises(CompilationError):session._accept(1.,*trial)
        assert session.time==0 and session.air_rooms==rooms
        assert all(np.array_equal(v,session.cells[k]) for k,v in cells.items())
        session._accept(1.,*session._trial(1.));last=session.last_accepted_frame
        assert last.time_s==1. and last.variables['Buffer.state.temperature_k']!=first.variables['Buffer.state.temperature_k']
        assert last.variables['Room.state.temperature_k']!=first.variables['Room.state.temperature_k']
        assert abs(last.metrics['energy_residual_w'])<.1
    finally:session.close()
