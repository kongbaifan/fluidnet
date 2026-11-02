"""机房联锁模板：启动顺序 → 压差确认 → 低压差停机 → 工作泵切换。

使用前把下面四个变量路径换成项目中的真实路径（引擎单位：Pa、kg/s、开度 0–1）。
本项目示例见 ``hvac-plant-interlock``（风系统 → 创建风侧示例 → 暖通基础 · 机房联锁启停）。
"""

# 输入
DISCHARGE_PRESSURE = 'Discharge.common.pressure_pa'   # 泵出口总管压力
SUCTION_PRESSURE = 'Suction.common.pressure_pa'       # 泵入口总管压力

# 输出（运行参数）
PUMP1_RUNNING = 'Pump1.param.running'
PUMP2_RUNNING = 'Pump2.param.running'

# 设定
MIN_DP_PA = 20000.
CONFIRM_S = 2.
SWITCH_S = 10.


def initialize(ctx):
    ctx.state['phase'] = 'starting'
    ctx.state['switched'] = False


def step(ctx, dt_s):
    dp = ctx.read(DISCHARGE_PRESSURE) - ctx.read(SUCTION_PRESSURE)
    if ctx.state['phase'] == 'starting':
        # 启动顺序：先起 1 号泵，再确认压差；无压差立即停机并保持联锁。
        ctx.write(PUMP1_RUNNING, 1.)
        if ctx.time_s >= CONFIRM_S:
            if dp < MIN_DP_PA:
                ctx.write(PUMP1_RUNNING, 0.)
                ctx.write(PUMP2_RUNNING, 0.)
                ctx.state['phase'] = 'tripped'
            else:
                ctx.state['phase'] = 'running'
    elif ctx.state['phase'] == 'running' and not ctx.state['switched'] and ctx.time_s >= SWITCH_S:
        # 切换顺序：先启动备用泵，确认后再停原工作泵。
        ctx.write(PUMP2_RUNNING, 1.)
        ctx.write(PUMP1_RUNNING, 0.)
        ctx.state['switched'] = True


def finalize(ctx):
    # 停机顺序：运行结束时两台泵都置停止，由止回阀和真实压差决定是否隔离。
    ctx.write(PUMP1_RUNNING, 0.)
    ctx.write(PUMP2_RUNNING, 0.)
