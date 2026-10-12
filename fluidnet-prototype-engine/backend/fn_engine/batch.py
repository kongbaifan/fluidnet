"""Bounded Worker shards, isolated module instances, one evaluation RPC per shard."""
from concurrent.futures import ThreadPoolExecutor

from .models import InitializeRequest, EvaluateResponse, CommitStepResponse
from .runtime import WorkerProcess, module_content_hash, module_definition_hash


class Handle:
    def __init__(self, worker, instance, definition, parameters, fluid):
        self.worker, self.id = worker, instance.id
        self.state = {}
        request = InitializeRequest(run_id='worker',instance_id=self.id,
            package={'module_id':definition.id,'version':f'{definition.version}.0.0',
                     'content_hash':module_content_hash(definition),'definition_hash':module_definition_hash(definition)},
            parameters=parameters,fluid=fluid)
        self.state = worker._request({'action':'initialize','instance_id':self.id,
            'definition':definition.model_dump(mode='json'),'request':request.model_dump(mode='json')})['state']

    def update_parameters(self, parameters):
        self.worker._request({'action':'parameters','instance_id':self.id,'parameters':parameters})

    def commit_step(self, request, channels=None):
        if channels is not None:
            request=request.model_copy(update={'converged_channels':channels})
        response=CommitStepResponse.model_validate(self.worker._request({'action':'commit_step','instance_id':self.id,
                                                                       'request':request.model_dump(mode='json')}))
        self.state=dict(response.state)
        return response


class BatchRunners(dict):
    def __init__(self, network, instances):
        super().__init__()
        count=min(network.project.solver.module_parallelism,len(instances))
        self.workers=[]
        self.pool=ThreadPoolExecutor(max_workers=count,thread_name_prefix='fluidnet-modules') if count>1 else None
        try:
            for i in range(count):
                instance=instances[i]
                self.workers.append(WorkerProcess(network.modules[instance.module_id],{},network.project.fluid))
            for i,instance in enumerate(instances):
                self[instance.id]=Handle(self.workers[i%count],instance,network.modules[instance.module_id],
                                         network.parameters[instance.id],network.project.fluid)
        except BaseException:
            self.close()
            raise

    def evaluate(self, requests):
        batches={worker:{} for worker in self.workers}
        for key,request in requests.items():
            batches[self[key].worker][key]={'action':'evaluate','instance_id':key,'request':request.model_dump(mode='json')}
        def execute(item):
            worker,items=item
            return worker._request({'action':'batch','items':items})
        results=list(self.pool.map(execute,batches.items())) if self.pool else [execute(item) for item in batches.items()]
        return {key:EvaluateResponse.model_validate(value) for result in results for key,value in result.items()}

    def close(self):
        if self.pool:
            self.pool.shutdown(wait=True,cancel_futures=True)
        for worker in self.workers:
            worker.close()
