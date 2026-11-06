"""Two isolated dry/moist-air streams exchanging sensible heat, without mass transfer."""
from fn_sdk import heat_exchanger_effectiveness


class Module:
    def initialize(self,ctx):
        ctx.state.setdefault('recovered_energy_j',0.)

    def evaluate(self,ctx):
        for side in ('exhaust','supply'):
            a,b=ctx.port(side+'_in'),ctx.port(side+'_out')
            upstream=a if a.pressure_pa>=b.pressure_pa else b
            ctx.net.resistance(channel=side,diameter_m=ctx.parameters[side+'_diameter_m'],
                loss_coefficient=ctx.parameters[side+'_loss_coefficient'],density_kg_m3=upstream.density_kg_m3)

    def thermal(self,ctx):
        flows={s:ctx.channel(s).mass_flow_kg_s for s in ('exhaust','supply')}
        states={s:ctx.port(s+('_in' if q>=0 else '_out')) for s,q in flows.items()}
        capacity={s:abs(flows[s])*states[s].specific_heat_j_kg_k for s in states}
        eps=heat_exchanger_effectiveness(ua_w_k=ctx.parameters['ua_w_k']*(1-ctx.parameters['bypass_ratio']),
            capacity_a_w_k=capacity['exhaust'],capacity_b_w_k=capacity['supply'],
            counterflow=(flows['exhaust']>=0)==(flows['supply']>=0))
        heat=eps*min(capacity.values())*(states['exhaust'].temperature_k-states['supply'].temperature_k)
        ctx.heat('exhaust',-heat);ctx.heat('supply',heat)

    def observe(self,ctx):
        for side in ('exhaust','supply'):
            for end in ('in','out'):
                state=ctx.port(side+'_'+end)
                if state.temperature_k is not None and state.temperature_k<273.15:
                    raise ValueError('AIR_RECOVERY_FROST_RANGE: 首版显热回收仅适用于所有端口不低于0°C')
                if state.relative_humidity is not None and state.relative_humidity>1.+1e-8:
                    raise ValueError('AIR_RECOVERY_CONDENSATION: 首版不处理凝结或结霜')
        ctx.var('recovered_heat_w',ctx.channel('supply').heat_w)
        ctx.var('effective_ua_w_k',ctx.parameters['ua_w_k']*(1-ctx.parameters['bypass_ratio']))

    def commit_step(self,ctx,dt_s):
        ctx.state['recovered_energy_j']+=ctx.channel('supply').heat_w*dt_s

    def finalize(self,ctx):pass
