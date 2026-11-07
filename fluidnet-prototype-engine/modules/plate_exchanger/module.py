"""Independent hydraulic sides and lumped fouling resistances; no physical storage."""
from fn_sdk import heat_exchanger_effectiveness


class Module:
    def initialize(self,ctx):
        ctx.state.setdefault('transferred_energy_j',0.)

    def ua(self,ctx):
        clean=ctx.parameters['clean_ua_w_k']
        return 1./(1./clean+ctx.parameters['hot_fouling_resistance_k_w']+ctx.parameters['cold_fouling_resistance_k_w']) if clean>0 else 0.

    def evaluate(self,ctx):
        for side in ('hot','cold'):
            a,b=ctx.port(side+'_in'),ctx.port(side+'_out')
            inlet=a if a.pressure_pa>=b.pressure_pa else b
            ctx.net.resistance(channel=side,diameter_m=ctx.parameters[side+'_diameter_m'],
                               loss_coefficient=ctx.parameters[side+'_loss_coefficient'],density_kg_m3=inlet.density_kg_m3)

    def thermal(self,ctx):
        qh,qc=ctx.channel('hot').mass_flow_kg_s,ctx.channel('cold').mass_flow_kg_s
        hot=ctx.port('hot_in' if qh>=0 else 'hot_out')
        cold=ctx.port('cold_in' if qc>=0 else 'cold_out')
        ch,cc=abs(qh)*hot.specific_heat_j_kg_k,abs(qc)*cold.specific_heat_j_kg_k
        epsilon=heat_exchanger_effectiveness(ua_w_k=self.ua(ctx),capacity_a_w_k=ch,capacity_b_w_k=cc,counterflow=(qh>=0)==(qc>=0))
        power=epsilon*min(ch,cc)*(hot.temperature_k-cold.temperature_k)
        ctx.heat('hot',-power);ctx.heat('cold',power)

    def observe(self,ctx):
        ctx.var('effective_ua_w_k',self.ua(ctx))
        ctx.var('transferred_heat_w',ctx.channel('cold').heat_w)
        for side in ('hot','cold'):
            ctx.var(side+'_pressure_drop_pa',ctx.channel(side).pressure_drop_pa)

    def commit_step(self,ctx,dt_s):
        ctx.state['transferred_energy_j']+=ctx.channel('cold').heat_w*dt_s

    def finalize(self,ctx):
        pass
