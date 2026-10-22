"""比较器模板（回差 / 双阈值）。

可直接作为 ControlScript.source 使用，实现 initialize / step / finalize 三个同步方法。
使用前请按工程实际变量路径替换：

    input.analog     → 被比较的模拟量（如空调回水温度、压差、功率）
    output.digital   → 数字量输出（1 = 高，0 = 低）

阈值写在 initialize 的 setdefault 里：≥ high 输出 1，≤ low 输出 0，中间保持上一次
输出（回差，避免阈值附近抖动）。运行中也可以通过 ctx.state["low"]/["high"] 改阈值。
"""


def initialize(ctx):
    # 状态初值；state 只允许标量，会被平台持久化到本次运行结束。
    ctx.state.setdefault("output", 0)
    ctx.state.setdefault("low", 0.4)
    ctx.state.setdefault("high", 0.6)


def step(ctx, dt_s):
    value = ctx.read("input.analog")
    output = int(ctx.state.get("output", 0))
    low = float(ctx.state.get("low", 0.4))
    high = float(ctx.state.get("high", 0.6))

    # 中间区间保持输出：只有越过上/下阈值才翻转。
    if value is not None:
        value = float(value)
        if value >= high:
            output = 1
        elif value <= low:
            output = 0

    ctx.write("output.digital", output)
    ctx.state["output"] = output
    ctx.state["low"] = low
    ctx.state["high"] = high


def finalize(ctx):
    pass
