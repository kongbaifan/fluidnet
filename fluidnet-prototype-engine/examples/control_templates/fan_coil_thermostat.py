"""风机盘管温控模板（分档风机 + 连续水阀）。

可直接作为 ControlScript.source 使用，实现 initialize / step / finalize 三个同步方法。
使用前请按工程实际变量路径替换：

    input.room_temperature_k  → 房间温度（K）
    output.fan_speed          → 风机档位（0/1/2/3，整数）
    output.valve_opening      → 水阀开度（0~1）

参数含义（都在 initialize 的 setdefault 里，可在运行前直接改）：

    setpoint  目标室温，默认 300.15 K（27 °C）
    band      比例带，K；也作为高档位判定上限
    deadband  下死区，K；低于 setpoint − deadband 才停风机

档位：error = room − setpoint
    error >  band      → 3
    error >  0         → 2
    error > −deadband  → 1
    其余               → 0
水阀开度：clamp(error / band, 0, 1)，与档位解耦，供连续调节。
"""


def initialize(ctx):
    ctx.state.setdefault("setpoint", 300.15)
    ctx.state.setdefault("band", 1.0)
    ctx.state.setdefault("deadband", 0.5)
    ctx.state.setdefault("stage", 0)


def step(ctx, dt_s):
    room = ctx.read("input.room_temperature_k")
    setpoint = float(ctx.state.get("setpoint", 300.15))
    band = max(float(ctx.state.get("band", 1.0)), 1e-6)
    deadband = max(float(ctx.state.get("deadband", 0.5)), 0.0)
    stage = int(ctx.state.get("stage", 0))
    valve = 0.0

    if room is not None:
        error = float(room) - setpoint
        if error > band:
            stage = 3
        elif error > 0.0:
            stage = 2
        elif error > -deadband:
            stage = 1
        else:
            stage = 0
        valve = min(max(error / band, 0.0), 1.0)

    ctx.write("output.fan_speed", stage)
    ctx.write("output.valve_opening", valve)
    ctx.state["setpoint"] = setpoint
    ctx.state["band"] = band
    ctx.state["deadband"] = deadband
    ctx.state["stage"] = stage


def finalize(ctx):
    pass
