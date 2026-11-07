"""Static conformance checks; this module is not imported by the execution path."""
from .batch import Handle
from .runner_protocol import LocalAcceptanceState, ModuleRunner
from .runtime import InProcessModuleRunner, WorkerProcess


def _all_transports(inprocess: InProcessModuleRunner, worker: WorkerProcess, batch: Handle
                    ) -> tuple[ModuleRunner, ModuleRunner, ModuleRunner]:
    return inprocess, worker, batch


def _local_bookkeeping(inprocess: InProcessModuleRunner) -> LocalAcceptanceState:
    return inprocess
