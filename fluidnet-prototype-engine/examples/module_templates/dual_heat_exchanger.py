"""Two single-phase streams with independent properties and conservative sensible heat."""
from fn_sdk import heat_exchanger_effectiveness


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault('transferred_energy_j', 0.)

    def evaluate(self, ctx):
        for channel, port in [('hot', 'hot_in'), ('cold', 'cold_in')]:
            ctx.net.resistance(channel=channel, diameter_m=ctx.parameter('diameter_m'),
                loss_coefficient=ctx.parameter('loss_coefficient'), density_kg_m3=ctx.port(port).density_kg_m3)

    def thermal(self, ctx):
        qh, qc = ctx.channel('hot').mass_flow_kg_s, ctx.channel('cold').mass_flow_kg_s
        hot = ctx.port('hot_in' if qh >= 0 else 'hot_out')
        cold = ctx.port('cold_in' if qc >= 0 else 'cold_out')
        ch, cc = abs(qh)*hot.specific_heat_j_kg_k, abs(qc)*cold.specific_heat_j_kg_k
        epsilon = heat_exchanger_effectiveness(ua_w_k=ctx.parameter('ua_w_k'), capacity_a_w_k=ch,
            capacity_b_w_k=cc, counterflow=(qh >= 0) == (qc >= 0))
        power = epsilon*min(ch, cc)*(hot.temperature_k-cold.temperature_k)
        ctx.heat('hot', -power)
        ctx.heat('cold', power)

    def observe(self, ctx):
        ctx.var('transferred_heat_w', ctx.channel('cold').heat_w)

    def commit_step(self, ctx, dt_s):
        ctx.state['transferred_energy_j'] += ctx.channel('cold').heat_w * dt_s

    def finalize(self, ctx):
        pass
