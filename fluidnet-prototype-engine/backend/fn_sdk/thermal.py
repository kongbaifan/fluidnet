"""Single-phase sensible heat exchange; capacity rates in W/K, UA in W/K."""
import math


def heat_exchanger_effectiveness(*, ua_w_k: float, capacity_a_w_k: float,
                                 capacity_b_w_k: float, counterflow: bool = True) -> float:
    for name, value in [('ua_w_k', ua_w_k), ('capacity_a_w_k', capacity_a_w_k), ('capacity_b_w_k', capacity_b_w_k)]:
        try:
            valid = not isinstance(value,bool) and isinstance(value,(float,int)) and math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f'{name} must be finite and nonnegative')
    if not isinstance(counterflow,bool):
        raise ValueError('counterflow must be boolean')
    small, large = min(capacity_a_w_k, capacity_b_w_k), max(capacity_a_w_k, capacity_b_w_k)
    if small == 0 or ua_w_k == 0:
        return 0.
    ratio, ntu = small / large, ua_w_k / small
    if not counterflow:
        return -math.expm1(-ntu * (1 + ratio)) / (1 + ratio)
    if abs(1 - ratio) < 1e-9:
        if math.isinf(ntu):
            return 1.
        return ntu / (1 + ntu)
    exponential = math.exp(-ntu * (1 - ratio))
    return (1 - exponential) / (1 - ratio * exponential)
