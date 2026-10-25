"""SDK 0.3.0 time-dependent equation; unpublished example, not a seed version."""
from __future__ import annotations

import math
from fn_sdk import DeviceModule, ModuleContext


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state.setdefault('commit_count', 0)

    def evaluate(self, ctx: ModuleContext) -> None:
        time_s = ctx.time_s
        if ctx.phase != 'evaluate' or time_s is None:
            raise ValueError('evaluate requires a host evaluation time')
        # Identity is for tracing; only physical inputs/time enter the equation.
        kv = 10.0 * (1.0 + 0.1 * math.sin(time_s))
        ctx.net.valve(channel='main', kv=kv, opening=0.8)
        ctx.var('evaluation_time_s', time_s)

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        if ctx.phase != 'commit_step' or ctx.execution.dt_s != dt_s:
            raise ValueError('commit callback must carry its own dt')
        count = ctx.state.get('commit_count', 0)
        if isinstance(count, bool) or not isinstance(count, int):
            raise ValueError('commit_count must be an integer')
        ctx.state['commit_count'] = count + 1

    def finalize(self, ctx: ModuleContext) -> None:
        pass


def typed_module() -> DeviceModule:
    return Module()
