"""Sampled PID controllers. Only accepted physical states advance their clocks."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .compiler import CompilationError
from .models import PIDController


@dataclass
class PID:
    config: PIDController
    output: float
    integral: float = 0.0
    derivative: float = 0.0
    measurement: float | None = None
    time_s: float | None = None
    next_s: float = 0.0
    reset: bool = True

    def sample(self, time_s, variables):
        c = self.config
        value = variables.get(c.measurement)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise CompilationError('PID_MEASUREMENT_INVALID', f'{c.id} 测量值无效：{c.measurement}')
        error = c.setpoint - value
        proportional = c.kp * error
        if self.reset:
            self.integral = self.output - proportional
            self.derivative = 0.0
            self.reset = False
        elif self.time_s is not None and time_s > self.time_s:
            dt = time_s - self.time_s
            raw = -(value - self.measurement) / dt
            alpha = dt / (c.sample_s + dt)
            self.derivative += alpha * (raw - self.derivative)
            change = c.ki * error * dt
            others = proportional + c.kd * self.derivative
            integral = self.integral + change
            # Conditional integration: grow only up to the value that just saturates, never past it.
            if others + integral > c.maximum and change > 0:
                integral = max(self.integral, c.maximum - others)
            elif others + integral < c.minimum and change < 0:
                integral = min(self.integral, c.minimum - others)
            self.integral = integral
        if c.mode == 'manual':
            self.output = c.manual_output if c.manual_output is not None else self.output
            self.integral = self.output - proportional - c.kd * self.derivative
        else:
            self.output = min(c.maximum, max(c.minimum, proportional + self.integral + c.kd * self.derivative))
        self.measurement, self.time_s = float(value), time_s
        self.next_s = time_s + c.sample_s
        return self.output

    def variables(self):
        c = self.config
        return {f'controller.{c.id}.{key}': value for key, value in {
            'measurement': self.measurement, 'setpoint': c.setpoint, 'output': self.output,
            'integral': self.integral, 'mode': c.mode,
        }.items()}
