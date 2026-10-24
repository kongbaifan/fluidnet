"""Bounded Worker shards, isolated module instances, one evaluation RPC per shard."""
from concurrent.futures import ThreadPoolExecutor

from .models import InitializeRequest, EvaluateResponse, ModuleStepCandidate, ModuleThermalResponse, ModuleDerivativeResponse
from .compiler import instance_fluids
from .module_contracts import check_module_compatibility
from .module_execution import InvocationState, new_identity
from .runtime import WorkerProcess, module_content_hash, module_definition_hash


class Handle:
    def __init__(self, worker, instance, definition, parameters, fluid, port_fluids=None, *, run_id=None):
        self.worker, self.id = worker, instance.id
        self.state = {}
        self.state_revision = 0
        self._accepted_candidate = None
        self.execution = InvocationState(run_id, self.id)
        worker._invocations[self.id] = self.execution
        worker._definitions[self.id] = definition
        request = InitializeRequest(run_id=self.execution.run_id,instance_id=self.id,
            package={'module_id':definition.id,'version':f'{definition.version}.0.0',
                     'content_hash':module_content_hash(definition),'definition_hash':module_definition_hash(definition)},
            parameters=parameters,fluid=fluid,port_fluids=port_fluids or {},context=self.execution.context())
        request.cache_enabled = worker.cache_enabled
        self.state = worker._request({'action':'initialize','instance_id':self.id,
            'definition':definition.model_dump(mode='json'),'request':request.model_dump(mode='json')})['state']

    def update_parameters(self, parameters):
        self.worker._request({'action':'parameters','instance_id':self.id,'parameters':parameters})

    def commit_step(self, request, channels=None):
        from .module_state import checked_state
        candidate=self.prepare_step(request,channels)
        if candidate != self._accepted_candidate:
            if candidate.base_revision != self.state_revision:
                from .runtime import RuntimeErrorBase
                raise RuntimeErrorBase('模块候选已过期',code='MODULE_REVISION_CONFLICT')
            self.state=checked_state(candidate.result.state)
            self.state_revision+=1
            self._accepted_candidate=candidate
        self.synchronize_state(candidate)
        return candidate.result

    def prepare_step(self, request, channels=None):
        if channels is not None:
            request = request.model_copy(update={'converged_channels': channels})
        request = request.model_copy(update={'context': request.context if request.context is not None else self.execution.context()})
        return ModuleStepCandidate.model_validate(self.worker._request({'action': 'prepare_step', 'instance_id': self.id,
            'request': request.model_dump(mode='json'), 'base_revision': self.state_revision, 'state': self.state}))

    def synchronize_state(self, candidate):
        response=self.worker._request({'action': 'synchronize_state', 'instance_id': self.id,
                                       'candidate': candidate.model_dump(mode='json')})
        if response.get('ok') is not True or response.get('revision') != candidate.base_revision+1:
            from .runtime import RuntimeErrorBase
            raise RuntimeErrorBase('Worker 状态同步回执无效',code='MODULE_SYNC_ACK_INVALID')

    def discard_candidate(self):
        self.worker._request({'action': 'discard_candidate', 'instance_id': self.id})

    def phase_call(self, phase, request):
        response = self.worker._request({'action': phase, 'instance_id': self.id, 'request': request.model_dump(mode='json')})
        parser = {'thermal':ModuleThermalResponse, 'jacobian':ModuleDerivativeResponse}.get(phase, EvaluateResponse)
        return parser.model_validate(response)


class BatchRunners(dict):
    def __init__(self, network, instances, *, run_id=None):
        super().__init__()
        for instance in instances:
            check_module_compatibility(network.modules[instance.module_id])
        run_id = run_id or new_identity('run')
        count=min(network.project.solver.module_parallelism,len(instances))
        self.workers=[]
        self.pool=ThreadPoolExecutor(max_workers=count,thread_name_prefix='fluidnet-modules') if count>1 else None
        try:
            for i in range(count):
                instance=instances[i]
                self.workers.append(WorkerProcess(network.modules[instance.module_id],{},instance_fluids(network,instance.id)[0],
                                                 run_id=run_id, instance_id=instance.id, cache_enabled=network.project.solver.module_cache))
            for i,instance in enumerate(instances):
                fluid,port_fluids=instance_fluids(network,instance.id)
                self[instance.id]=Handle(self.workers[i%count],instance,network.modules[instance.module_id],
                                         network.parameters[instance.id],fluid,port_fluids,run_id=run_id)
        except BaseException:
            self.close()
            raise

    def evaluate(self, requests):
        batches={worker:{} for worker in self.workers}
        for key,request in requests.items():
            handle=self[key]
            definition=handle.worker._definitions[key]
            if handle.worker.cache_enabled and definition.pure_evaluate:
                request=request.model_copy(update={'readonly_state':{},'state_revision':handle.state_revision})
            if request.context is None:
                request=request.model_copy(update={'context':self[key].execution.context()})
            batches[self[key].worker][key]={'action':'evaluate','instance_id':key,'request':request.model_dump(mode='json')}
        def execute(item):
            worker,items=item
            return worker._request({'action':'batch','items':items})
        results=list(self.pool.map(execute,batches.items())) if self.pool else [execute(item) for item in batches.items()]
        return {key:EvaluateResponse.model_validate(value) for result in results for key,value in result.items()}

    @property
    def request_count(self):
        """B0 观测器：所有分片 Worker 的累计 RPC 数（一个分片一次 evaluate = 一次 RPC）。"""
        return sum(worker.request_count for worker in self.workers)

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=True,cancel_futures=True)
        for worker in self.workers:
            worker.close()
