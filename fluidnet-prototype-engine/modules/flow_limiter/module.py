"""分段限流阀示范：过拐点后阻力斜率增大；不是严格流量上限。"""
import math


class Module:
    def initialize(self, ctx):
        ctx.state['transferred_mass_kg'] = 0.0

    def evaluate(self, ctx):
        opening = ctx.parameters['opening_ratio']
        if opening == 0:
            ctx.net.valve(channel='main', kv=1.0, opening=0.0)
            return
        flow = ctx.channel('main').mass_flow_kg_s
        knee = ctx.parameters['knee_flow_kg_s'] * opening
        low = ctx.parameters['low_slope']
        high = ctx.parameters['high_slope']
        magnitude = min(abs(flow), knee) * low + max(0.0, abs(flow) - knee) * high
        ctx.net.pressure_drop(channel='main', pressure_drop_pa=math.copysign(magnitude, flow))

    def observe(self, ctx):
        ctx.var('actual_drop_pa', ctx.channel('main').pressure_drop_pa)

    def commit_step(self, ctx, dt_s):
        ctx.state['transferred_mass_kg'] += abs(ctx.channel('main').mass_flow_kg_s) * dt_s

    def finalize(self, ctx):
        pass
