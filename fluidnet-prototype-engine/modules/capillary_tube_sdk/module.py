"""Single-phase capillary; observed velocity comes from the current hydraulic solution."""
import math


from fn_sdk import ModuleContext,DeviceModule


def number(ctx: ModuleContext, name: str) -> float:
    value = ctx.parameter(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be numeric')
    return float(value)


def stored(ctx: ModuleContext, name: str) -> float:
    value = ctx.state.get(name, 0.)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{name} must be numeric')
    return float(value)


class Module:
    def initialize(self, ctx: ModuleContext) -> None:
        ctx.state.setdefault('throughput_kg', 0.)

    def evaluate(self, ctx: ModuleContext) -> None:
        inlet = ctx.port('in0')
        if inlet.quality is not None and 0 <= inlet.quality <= 1:
            raise ValueError('毛细管模型只支持单相液体')
        ctx.net.pipe(channel='main', diameter_m=number(ctx, 'diameter_m'), length_m=number(ctx, 'length_m'),
            roughness_m=number(ctx, 'roughness_m'), density_kg_m3=inlet.density_kg_m3,
            viscosity_pa_s=inlet.viscosity_pa_s)

    def observe(self, ctx: ModuleContext) -> None:
        flow = ctx.channel('main').mass_flow_kg_s
        rho = ctx.port('in0' if flow >= 0 else 'out0').density_kg_m3
        if rho is None or rho <= 0: raise ValueError('host must provide positive density')
        area = math.pi * number(ctx, 'diameter_m') ** 2 / 4
        ctx.var('flow_area_m2', area)
        ctx.var('mean_velocity_m_s', abs(flow) / (rho * area))

    def commit_step(self, ctx: ModuleContext, dt_s: float) -> None:
        ctx.state['throughput_kg'] = stored(ctx, 'throughput_kg') + abs(ctx.channel('main').mass_flow_kg_s) * dt_s

    def finalize(self, ctx: ModuleContext) -> None:
        pass


def typed_module() -> DeviceModule:
    return Module()
