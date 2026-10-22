"""等百分比调节阀：复刻倍思鹿 ``截止阀_Run.cpp:78-96`` 的 CVF 特性曲线。

倍思鹿取 ``VTYPE=2``（固定等百分比）、``ALF=100``，按

    CVF = (ALF^(VSPACT-1) + LF) / (1 + LF) - 1/ALF

计算当量流通系数，再交给 ``VALVECV_SHUT``/``Netlink_Valve``。本模块把同一
CVF 折算到 FluidNet 内置阀门关系上：``kv_eff = kv_rated·CVF``、``opening=1``；
``opening=0`` 或 CVF 落到 0 时改为 ``opening=0``，由求解器压成零流量约束。
"""

CVF_EPS = 1e-9


class Module:
    def initialize(self, ctx):
        ctx.state.setdefault("throughput_kg", 0.0)

    def evaluate(self, ctx):
        inlet = ctx.port("in0")
        kv_rated = max(float(ctx.parameter("kv_m3_h", 16.0)), CVF_EPS)
        # 参数层已经把开度限制在 [0,1]；这里再夹一次，避免运行期写入越界。
        opening = min(max(float(ctx.parameter("opening_ratio", 0.5)), 0.0), 1.0)
        alf = max(float(ctx.parameter("rangeability_alf", 100.0)), 1.0)
        lf = max(float(ctx.parameter("leakage_fraction", 0.0)), 0.0)

        # 截止阀_Run.cpp:78-96：CVF=(ALF^(VSPACT-1)+LF)/(1+LF)-1/ALF，并夹到非负。
        cvf = (alf ** (opening - 1.0) + lf) / (1.0 + lf) - 1.0 / alf
        cvf = max(cvf, 0.0)

        density_kg_m3 = inlet.density_kg_m3 or float(ctx.parameter("density_kg_m3", 998.2))
        density_kg_m3 = max(float(density_kg_m3), 1e-3)

        if opening <= 0.0 or cvf <= CVF_EPS:
            # 精确关断：求解器把 opening_ratio==0 的阀门支路当作零流量约束。
            ctx.net.valve(
                channel="main",
                kv=kv_rated,
                opening=0.0,
                density_kg_m3=density_kg_m3,
            )
        else:
            ctx.net.valve(
                channel="main",
                kv=kv_rated * cvf,
                opening=1.0,
                density_kg_m3=density_kg_m3,
            )

        ctx.var("cvf", cvf)
        ctx.var("effective_kv_m3_h", kv_rated * cvf)

    def commit_step(self, ctx, dt_s):
        mass_flow_kg_s = abs(ctx.channel("main").mass_flow_kg_s or 0.0)
        ctx.state["throughput_kg"] = float(ctx.state.get("throughput_kg", 0.0)) + mass_flow_kg_s * dt_s

    def finalize(self, ctx):
        pass
