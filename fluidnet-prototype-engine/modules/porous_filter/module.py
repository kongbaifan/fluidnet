"""多孔滤芯示范：线性黏性项 + 二次惯性项，压力单位 Pa、流量 kg/s。"""
class Module:
    def initialize(self, ctx):
        ctx.state['transferred_mass_kg'] = 0.0

    def evaluate(self, ctx):
        flow = ctx.channel('main').mass_flow_kg_s
        multiplier = 1.0 + ctx.parameters['clogging_ratio']
        drop = multiplier * (ctx.parameters['linear_coefficient'] * flow
                             + ctx.parameters['quadratic_coefficient'] * flow * abs(flow))
        ctx.net.pressure_drop(channel='main', pressure_drop_pa=drop)

    def observe(self, ctx):
        ctx.var('actual_drop_pa', ctx.channel('main').pressure_drop_pa)

    def commit_step(self, ctx, dt_s):
        ctx.state['transferred_mass_kg'] += abs(ctx.channel('main').mass_flow_kg_s) * dt_s

    def finalize(self, ctx):
        pass
