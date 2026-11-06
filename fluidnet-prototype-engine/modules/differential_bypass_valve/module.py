import math
MODE = 'bypass'

class Module:
    def initialize(self,ctx):
        p=ctx.parameters
        if p['maximum_pressure_drop_pa'] <= p['minimum_pressure_drop_pa']:
            raise ValueError('最大允许压差必须大于起调压差')
        ctx.state.setdefault('throughput_kg',0.)
    def operating(self,ctx):
        p=ctx.parameters
        drop=ctx.port('in0').pressure_pa-ctx.port('out0').pressure_pa
        density=(ctx.fluid.state_pt(ctx.port('in0').pressure_pa,ctx.port('in0').temperature_k).density_kg_m3
                 if ctx.port('in0').temperature_k is not None else ctx.port('in0').density_kg_m3)
        if density is None or density<=0: raise ValueError('入口液体密度必须为正')
        if MODE=='bypass':
            opening=min(1.,max(0.,(drop-p['minimum_pressure_drop_pa'])/p['proportional_band_pa']))
            kv=p['kv_m3_h']
        else:
            # Finite maximum Kv: below minimum dp the regulator runs out of authority.
            kv=p['rated_volume_flow_m3_h']/math.sqrt(p['minimum_pressure_drop_pa']/1e5/(density/1000.))
            opening=p['opening_ratio']*min(1.,math.sqrt(p['minimum_pressure_drop_pa']/drop)) if drop>0 else 0.
        return drop,density,kv,opening
    def evaluate(self,ctx):
        drop,density,kv,opening=self.operating(ctx)
        ctx.net.valve(channel='main',kv=kv,opening=opening,density_kg_m3=density)
    def observe(self,ctx):
        p=ctx.parameters
        drop,density,kv,opening=self.operating(ctx)
        if drop>p['maximum_pressure_drop_pa']:
            ctx.diagnostic('REGULATING_VALVE_RANGE',f"压差 {drop:g} Pa 超过允许值 {p['maximum_pressure_drop_pa']:g} Pa",severity='error')
        flow=ctx.channel('main').mass_flow_kg_s
        ctx.var('effective_opening',opening)
        ctx.var('effective_kv_m3_h',kv*opening)
        ctx.var('actual_pressure_drop_pa',drop)
        ctx.var('actual_volume_flow_m3_h',flow/density*3600.)
        ctx.var('regulating',int(MODE=='picv' and p['opening_ratio']>0 and drop>=p['minimum_pressure_drop_pa']))
    def commit_step(self,ctx,dt_s):
        ctx.state['throughput_kg']+=abs(ctx.channel('main').mass_flow_kg_s)*dt_s
    def finalize(self,ctx): pass
