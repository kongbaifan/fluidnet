"""控制脚本模板测试：比较器与风机盘管温控。

模板文件放在 ``examples/control_templates/``，这里按前端/编译器的用法把文件原文作为
``ControlScript.source``，再用 ``ControlRunner`` 在进程内执行 initialize / step，
断言写出的变量值与脚本状态。不依赖 scipy 或 CoolProp。
"""
from pathlib import Path

import pytest

from fn_engine.control import ControlRunner
from fn_engine.models import ControlScript

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "examples" / "control_templates"


def runner_for(filename, script_id, inputs, outputs):
    source = (TEMPLATE_ROOT / filename).read_text(encoding="utf-8")
    script = ControlScript(id=script_id, source=source, inputs=inputs, outputs=outputs)
    return ControlRunner(script)


def initialize(runner):
    return runner.call("initialize", {"values": {}, "state": {}, "time_s": 0.0})


def step(runner, state, values, time_s):
    return runner.call(
        "step",
        {"values": values, "state": state, "time_s": time_s, "dt_s": 0.1},
    )


def test_comparator_template_hysteresis():
    runner = runner_for(
        "comparator.py",
        "comparator_template",
        inputs=["input.analog"],
        outputs=["output.digital"],
    )

    started = initialize(runner)
    assert started["state"] == {"output": 0, "low": 0.4, "high": 0.6}
    assert started["writes"] == {}

    high = step(runner, started["state"], {"input.analog": 0.7}, 0.1)
    assert high["writes"] == {"output.digital": 1}
    assert high["state"]["output"] == 1
    assert high["diagnostics"] == []

    # 0.5 落在 [low, high] 之间：保持上一次输出 1（回差）。
    hold = step(runner, high["state"], {"input.analog": 0.5}, 0.2)
    assert hold["writes"] == {"output.digital": 1}
    assert hold["state"]["output"] == 1

    low = step(runner, hold["state"], {"input.analog": 0.3}, 0.3)
    assert low["writes"] == {"output.digital": 0}
    assert low["state"]["output"] == 0

    # 仍低于下阈值：保持 0。
    hold_low = step(runner, low["state"], {"input.analog": 0.39}, 0.4)
    assert hold_low["writes"] == {"output.digital": 0}
    assert hold_low["state"]["output"] == 0


def test_fan_coil_thermostat_template_stages_and_valve():
    runner = runner_for(
        "fan_coil_thermostat.py",
        "fan_coil_thermostat_template",
        inputs=["input.room_temperature_k"],
        outputs=["output.fan_speed", "output.valve_opening"],
    )

    started = initialize(runner)
    assert started["state"] == {"setpoint": 300.15, "band": 1.0, "deadband": 0.5, "stage": 0}

    # error = 3.0 K > band → 3 档，水阀全开。
    full = step(runner, started["state"], {"input.room_temperature_k": 303.15}, 0.1)
    assert full["writes"] == {"output.fan_speed": 3, "output.valve_opening": 1.0}
    assert full["state"]["stage"] == 3
    assert full["diagnostics"] == []

    # error = 0.5 K：0 < error ≤ band → 2 档；valve = clamp(error/band) = 0.5。
    partial = step(runner, full["state"], {"input.room_temperature_k": 300.65}, 0.2)
    assert partial["writes"] == {"output.fan_speed": 2, "output.valve_opening": 0.5}
    assert partial["state"]["stage"] == 2

    # error = 0.05 K：仍大于 0 → 2 档；valve = 0.05。
    # （按模板注释的分档式 error>0→2，300.2 K 落在 2 档而不是 1 档。）
    just_above = step(runner, partial["state"], {"input.room_temperature_k": 300.2}, 0.3)
    assert just_above["writes"]["output.fan_speed"] == 2
    assert just_above["writes"]["output.valve_opening"] == pytest.approx(0.05)
    assert just_above["state"]["stage"] == 2

    # error = −0.15 K：−deadband < error ≤ 0 → 1 档；valve = clamp(−0.15/1) = 0。
    low = step(runner, just_above["state"], {"input.room_temperature_k": 300.0}, 0.4)
    assert low["writes"] == {"output.fan_speed": 1, "output.valve_opening": 0.0}
    assert low["state"]["stage"] == 1

    # error = −0.65 K < −deadband → 0 档，水阀关闭。
    off = step(runner, low["state"], {"input.room_temperature_k": 299.5}, 0.5)
    assert off["writes"] == {"output.fan_speed": 0, "output.valve_opening": 0.0}
    assert off["state"]["stage"] == 0

    # 比例带内 0.65 K 对应 0.65 开度（模板公式的连续段）。
    proportional = step(runner, off["state"], {"input.room_temperature_k": 300.8}, 0.6)
    assert proportional["writes"]["output.valve_opening"] == pytest.approx(0.65)
    assert proportional["state"]["stage"] == 2

    final = runner.call("finalize", {"values": {}, "state": proportional["state"], "time_s": 0.6})
    assert final["writes"] == {}
    assert final["state"] == proportional["state"]
