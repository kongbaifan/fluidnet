"""RF-0 experiment: real station equations/Worker/transactions, no public compiler bypass.

Only this explicit harness can replace a previously validated built-in throttle.
Production API compilation and publication remain closed to refrigeration Python modules.
"""
from contextlib import contextmanager
from copy import deepcopy
import math
from pathlib import Path
import time

from fn_engine.compiler import compile_project
from fn_engine.models import CommitStepRequest, Diagnostic, EvaluateRequest, ModuleDefinition, PortState, RunFrame
from fn_engine.module_execution import begin_module_step, new_identity
from fn_engine.module_transactions import ModuleStepTransaction
from fn_engine.refrigeration import devices
from fn_engine.refrigeration.station import StationSession, evaluate
from fn_engine.runtime import RuntimeErrorBase, WorkerProcess, module_content_hash, module_definition_hash
from fn_engine.solver import SolveFailed

ROOT = Path(__file__).resolve().parents[1]


class TracedWorker(WorkerProcess):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actions, self.rpc_seconds = {}, 0.

    def _request_impl(self, payload):
        action = payload['action']
        self.actions[action] = self.actions.get(action,0)+1
        started = time.perf_counter()
        try:
            return super()._request_impl(payload)
        finally:
            self.rpc_seconds += time.perf_counter()-started


def throttle_module(source=None):
    """Schema 2 is a transport carrier, not an advertised refrigeration capability.

Schema 3 is frozen to fluid applicability; RF-1 needs a new schema/SDK contract.
"""
    from fn_engine.catalog import catalog_map
    reference = catalog_map()['expansion_valve']
    result = ModuleDefinition(schema_version=2, id='rf0_python_throttle', name='RF-0 Python 节流验证',
        runtime='python', entrypoint='module:Module', ports=deepcopy(reference.ports),
        parameters=deepcopy(reference.parameters), sdk={'api_version':'0.6.0',
            'capabilities':['context.execution.v1','state.transactions.v1']},
        variables=[{'id':key,'label':key,'quantity':quantity,'source':'derived',
                    'unit':{'quantity':quantity,'canonical_unit':unit,'display_unit':unit}}
                   for key,quantity,unit in [('mass_flow_kg_s','mass_flow','kg/s'),('effective_kv_m3_h','volume_flow','m3/h')]],
        source={'runtime':source if source is not None else
                (ROOT/'examples/refrigeration_extensions/rf0_throttle.py').read_text(encoding='utf-8')})
    result.content_hash = module_content_hash(result)
    result.definition_hash = module_definition_hash(result)
    return result


def compile_probe(project, replacements):
    """Check the original topology first, then explicitly attach experimental algorithms.

Never remove public compiler checks or advertise this project as normal API input.
"""
    network = compile_project(project.model_copy(deep=True))
    if network.execution_domain != 'refrigeration' or project.thermal_couplings:
        raise ValueError('RF-0 只验证纯集总制冷站')
    if project.solver.time_step.enabled:
        raise ValueError('RF-0 暂不验证自适应步加倍；RF-2 接入前保持拒绝')
    if not replacements:
        raise ValueError('RF-0 至少指定一台节流设备')
    for iid, definition in replacements.items():
        if network.kinds.get(iid) != 'expansion_valve':
            raise ValueError('RF-0 只替换已有等焓节流设备')
        reference = network.modules[network.instances[iid].module_id]
        if definition.runtime != 'python' or definition.channels or definition.state_model or definition.composite:
            raise ValueError('RF-0 作者设备不能声明通路、物理储量或组合')
        if [p.model_dump() for p in definition.ports] != [p.model_dump() for p in reference.ports]:
            raise ValueError('RF-0 必须保留节流设备的端口角色')
        if [p.model_dump() for p in definition.parameters] != [p.model_dump() for p in reference.parameters]:
            raise ValueError('RF-0 参数合同必须与被替换节流阀相同')
        if module_content_hash(definition) != definition.content_hash or module_definition_hash(definition) != definition.definition_hash:
            raise ValueError('RF-0 模块双哈希不一致')
        if definition.id in network.modules:
            raise ValueError('RF-0 模块标识冲突')
        frozen = definition.model_copy(deep=True)
        network.modules[frozen.id] = frozen
        network.instances[iid].module_id = frozen.id
    # The experiment records the actual Python definitions in its input snapshot.
    used = {instance.module_id for instance in network.instances.values()}
    network.project = network.project.model_copy(deep=True, update={
        'instances':list(network.instances.values()), 'modules':[network.modules[key] for key in sorted(used)]})
    return network


class ProbeSession(StationSession):
    """Candidate evaluations share the station's (M,U,T) state; parent accepts once per segment."""

    def __init__(self, network, duration_s, dt_s, *, timeout_s=10):
        self.evaluations = self.derivatives = self.newton_solves = 0
        self._candidate_time = self._provisional_time = 0.
        self._collecting = False
        self._trial_result = None
        self._pending_transaction = None
        self.last_ports, self.last_requests = {}, {}
        self.last_commit_requests = {}
        self.last_transaction = None
        super().__init__(network, duration_s, dt_s)
        run_id = new_identity('rf0')
        self.runners = {iid:TracedWorker(network.modules[instance.module_id], deepcopy(network.parameters[iid]),
            network.vessel_fluids[network.vessel(iid,'in0')], run_id=run_id, instance_id=iid, timeout_s=timeout_s)
            for iid,instance in network.instances.items() if network.modules[instance.module_id].runtime == 'python'}

    def initialize(self):
        if self.frames:
            return self.frames[-1]
        try:
            for runner in self.runners.values():
                runner.initialize()
                runner.execution.accepted_time_s = 0.
            return super().initialize()
        except BaseException:
            self.close()
            raise

    def _valve(self, iid, service, parameters, high, low):
        if iid not in self.runners:
            return devices.valve_flow(service,parameters,high.pressure_pa,low.pressure_pa)
        runner = self.runners[iid]
        if runner.parameters != parameters:
            runner.update_parameters(parameters)
        liquid = service.state_pq(high.pressure_pa,0.)
        ports = {'in0':PortState(pressure_pa=high.pressure_pa,temperature_k=liquid.temperature_k,
                    enthalpy_j_kg=liquid.enthalpy_j_kg,density_kg_m3=liquid.density_kg_m3,quality=0.),
                 'out0':PortState(pressure_pa=low.pressure_pa)}
        request = EvaluateRequest(run_id=runner.execution.run_id,instance_id=iid,iteration_id=self.evaluations,
            time_s=self._candidate_time,trial_ports=ports,context=runner.execution.context())
        self.evaluations += 1
        response = runner.evaluate(request)
        if response.relations or set(response.variables) != {'mass_flow_kg_s','effective_kv_m3_h'}:
            self._invalid(iid,'RF-0 返回合同不匹配')
        if any(item.severity == 'error' for item in response.diagnostics):
            raise RuntimeErrorBase('RF-0 作者报告错误',code='RF0_OUTPUT_INVALID',diagnostics=response.diagnostics)
        mass, kv = response.variables['mass_flow_kg_s'], response.variables['effective_kv_m3_h']
        if any(isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0
               for value in (mass,kv)):
            self._invalid(iid,'RF-0 流量和有效 Kv 必须为有限非负数')
        drop = high.pressure_pa-low.pressure_pa
        ceiling = parameters['kv_m3_h']/3600*math.sqrt(1000*liquid.density_kg_m3*max(drop,0)/1e5)
        if kv>parameters['kv_m3_h'] or mass>ceiling*(1+1e-12) or (drop<=0 or parameters['opening_ratio']==0) and mass!=0:
            self._invalid(iid,'RF-0 输出超出单向关断与额定 Kv 范围')
        expected = kv/3600*math.sqrt(1000*liquid.density_kg_m3*max(drop,0)/1e5)
        if not math.isclose(mass,expected,rel_tol=1e-10,abs_tol=1e-12):
            self._invalid(iid,'RF-0 流量与有效 Kv、压差、密度不一致')
        flashed = service.state_ph(low.pressure_pa,liquid.enthalpy_j_kg) if drop>0 else None
        # Enthalpy and the pair of signed vessel fluxes belong to the host.
        ports['in0'].mass_flow_kg_s = mass
        ports['out0'] = PortState(pressure_pa=low.pressure_pa,enthalpy_j_kg=liquid.enthalpy_j_kg,
            temperature_k=flashed.temperature_k if flashed else None,quality=flashed.quality if flashed else None,
            mass_flow_kg_s=-mass)
        self.last_ports[iid], self.last_requests[iid] = ports, request
        return {'mass_flow_kg_s':mass,'pressure_drop_pa':drop,'enthalpy_j_kg':liquid.enthalpy_j_kg,
                'outlet_quality':flashed.quality if flashed else None,'effective_kv_m3_h':kv}

    def _invalid(self, iid, message):
        raise RuntimeErrorBase(message,code='RF0_OUTPUT_INVALID',diagnostics=[Diagnostic(code='RF0_OUTPUT_INVALID',
            message=message,instance_id=iid,phase='evaluate',time_s=self._candidate_time)])

    def _evaluate(self, masses, energies, temperatures):
        return evaluate(self.network,self.services,masses,energies,temperatures,valve_evaluator=self._valve)

    def _derivative(self, x, base):
        self.derivatives += 1
        return super()._derivative(x,base)

    def _solve(self, x_old, h):
        self.newton_solves += 1
        self._candidate_time = self._provisional_time+h
        x,result = super()._solve(x_old,h)
        self._trial_result = result,h
        return x,result

    def _powers(self, result):
        powers = super()._powers(result)
        for iid in self.runners:
            powers[(iid,'transferred_mass_kg')] = result['devices'][iid]['mass_flow_kg_s']
        # In fixed-step integration this hook is reached only after a trial passes
        # the vessel checks. It also locates the next candidate time after halving.
        if self._collecting and self._trial_result is not None and self._trial_result[0] is result:
            self._provisional_time += self._trial_result[1]
            self._trial_result = None
        return powers

    @contextmanager
    def _segment_transaction(self):
        self._pending_transaction = None
        begin_module_step(self.runners)
        try:
            with super()._segment_transaction():
                try:
                    yield
                    self._pending_transaction.promote()
                except RuntimeErrorBase as error:
                    diagnostic = error.diagnostics[0] if error.diagnostics else None
                    failure = SolveFailed(error.code,str(error),diagnostic.instance_id if diagnostic else None)
                    if diagnostic is not None:
                        failure.diagnostic = diagnostic.model_copy(update={'code':error.code})
                        failure.diagnostics = error.diagnostics
                    raise failure from error
        except Exception:
            if self._pending_transaction is not None:
                self._pending_transaction.discard()
            self.close()
            raise
        # Synchronization is AFTER parent acceptance, outside the rollback scope.
        transaction = self._pending_transaction
        self.last_transaction = transaction
        try:
            transaction.synchronize()
        except RuntimeErrorBase as error:
            if not self.frames or self.frames[-1].time_s < self.time:
                self.publish()
            self.close()
            raise SolveFailed(error.code,str(error),None,list(self.frames)) from error

    def _advance_heat(self, step):
        self._provisional_time = self.time
        self._collecting = True
        try:
            super()._advance_heat(step)
        finally:
            self._collecting = False
        self._candidate_time = self.time
        self._current()  # final endpoint evaluation, retained for snapshot/report reads
        transaction = ModuleStepTransaction(self.runners,next(iter(self.runners.values())).execution.step_id,self.time)
        self._pending_transaction = transaction
        for iid,runner in self.runners.items():
            request = CommitStepRequest(run_id=runner.execution.run_id,instance_id=iid,time_s=self.time,dt_s=step,
                converged_ports=self.last_ports[iid],context=runner.execution.context(port_data='converged'))
            self.last_commit_requests[iid] = request
            transaction.prepare(iid,request,{})
        transaction.validate()
        # Validate the complete prospective frame before lifting module state.
        frame = self.snapshot()
        for iid,candidate in transaction.candidates.items():
            frame.variables.update({f'{iid}.state.{key}':value for key,value in candidate.result.state.items()})
        RunFrame.model_validate_json(frame.model_dump_json())

    def snapshot(self):
        frame = super().snapshot()
        for iid,runner in self.runners.items():
            frame.variables.update({f'{iid}.state.{key}':value for key,value in runner.state.items()})
        return frame
