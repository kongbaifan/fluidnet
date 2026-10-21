"""B0 independent design point of the NH3/CO2 lumped station (CoolProp PropsSI only; no engine imports).

Rooms are held at the setpoint, the low-pressure drum at the target evaporating pressure and the receiver at the
target condensing pressure. The steady balances of the lumped model (saturated vessels, devices as algebraic
relations) then fix every actuator: cooler fan ratio, pump speed, total compressor load, condenser return-gas
ratio and expansion-valve opening. All balances must close and every actuator must sit inside its range.

    python cases/cold-storage/nh3-co2/tools/verify_station_reference.py --check
    python cases/cold-storage/nh3-co2/tools/verify_station_reference.py --output <new directory>
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

import CoolProp
from CoolProp.CoolProp import PropsSI

ROOT = Path(__file__).resolve().parents[1] / 'station'
NH3, CO2 = 'Ammonia', 'CarbonDioxide'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sat(fluid, key, pressure, quality):
    return float(PropsSI(key, 'P', pressure, 'Q', quality, fluid))


def bisect(f, low, high, tol=1e-12):
    f_low = f(low)
    require(f_low * f(high) < 0, 'no root in bracket')
    for _ in range(200):
        mid = (low + high) / 2
        if (f(mid) < 0) == (f_low < 0):
            low, f_low = mid, f(mid)
        else:
            high = mid
        if high - low < tol:
            break
    return (low + high) / 2


def pump_speed(rule, fan):
    return min(rule['maximum'], max(rule['minimum'], rule['minimum'] + rule['per_mean_fan_ratio'] * fan))


def design(p):
    room, cooler, pump, cascade, comp, cond = (p[k] for k in ('rooms', 'air_cooler', 'pump', 'cascade', 'compressors', 'condenser'))
    t_room, n_rooms = room['setpoint_temperature_k'], room['count']
    envelope = ((room['wall_ua_w_k'] + room['roof_ua_w_k']) * (room['ambient_temperature_k'] - t_room)
                + room['floor_ua_w_k'] * (room['ground_temperature_k'] - t_room))
    room_load = envelope + room['rated_heat_input_w']
    p_lp, p_hp = p['targets']['evaporating_pressure_pa'], p['targets']['condensing_pressure_pa']
    t_nh3 = sat(NH3, 'T', p_lp, 0)

    def co2_state(fan):
        ua = cooler['ua_w_k'] * (cooler['natural_ua_ratio'] + (1 - cooler['natural_ua_ratio']) * fan)
        q_coil = room_load + cooler['fan_power_w'] * fan            # fan heat stays in the room
        t_co2 = t_room - q_coil / ua
        p_co2 = float(PropsSI('P', 'T', t_co2, 'Q', 0, CO2))
        speed = pump_speed(pump['speed_rule'], fan)
        rho = sat(CO2, 'Dmass', p_co2, 0)
        flow = pump['rated_mass_flow_kg_s'] * speed
        w_pump = flow * pump['rated_pressure_rise_pa'] * speed ** 2 / rho / pump['efficiency_ratio']
        return q_coil, t_co2, p_co2, speed, flow, w_pump

    def co2_balance(fan):                                         # CO2 drum: ΣQ_coil + W_pump − Q_hx = 0
        q_coil, t_co2, _, _, _, w_pump = co2_state(fan)
        return n_rooms * q_coil + w_pump - cascade['ua_w_k'] * (t_co2 - t_nh3)

    fan = bisect(co2_balance, .05, 1.)
    q_coil, t_co2, p_co2, speed, flow, w_pump = co2_state(fan)
    latent_co2 = sat(CO2, 'Hmass', p_co2, 1) - sat(CO2, 'Hmass', p_co2, 0)
    per_coil_flow = flow / n_rooms
    require(q_coil < per_coil_flow * latent_co2 * cooler['max_outlet_quality'], 'coil supply-limited at design')
    q_hx = cascade['ua_w_k'] * (t_co2 - t_nh3)
    # NH3 low side: m_comp·(h_v,LP − h_l,HP) = Q_hx (valve feeds receiver liquid, compressors draw drum vapour).
    h_v, s_v, rho_v = (sat(NH3, k, p_lp, 1) for k in ('Hmass', 'Smass', 'Dmass'))
    h_l_hp, rho_l_hp = sat(NH3, 'Hmass', p_hp, 0), sat(NH3, 'Dmass', p_hp, 0)
    m_comp = q_hx / (h_v - h_l_hp)
    h_2s = float(PropsSI('Hmass', 'P', p_hp, 'Smass', s_v, NH3))
    h_2 = h_v + (h_2s - h_v) / comp['isentropic_efficiency']
    t_discharge = float(PropsSI('T', 'P', p_hp, 'Hmass', h_2, NH3))
    shaft = m_comp * (h_2 - h_v)
    total_load = m_comp / (comp['displacement_m3_s'] * comp['volumetric_efficiency'] * rho_v)
    running = math.ceil(total_load / .95 - 1e-9)
    q_cond = m_comp * (h_2 - h_l_hp)
    t_cond = sat(NH3, 'T', p_hp, 0)
    ua_needed = q_cond / (t_cond - cond['wet_bulb_temperature_k'])
    fan_term = cond['natural_ua_ratio'] + (1 - cond['natural_ua_ratio']) * 1.
    return_gas = (ua_needed / (cond['ua_w_k'] * fan_term) - cond['flooded_ua_ratio']) / (1 - cond['flooded_ua_ratio'])
    opening = m_comp / (p['expansion_valve']['kv_m3_h'] / 3600 * math.sqrt(1000 * rho_l_hp * (p_hp - p_lp) / 1e5))
    electric = shaft / comp['motor_efficiency']
    station_in = n_rooms * (room_load + cooler['fan_power_w'] * fan) + w_pump + shaft
    return {
        'room': {'envelope_heat_w': envelope, 'load_w': room_load, 'temperature_k': t_room},
        'cooler': {'fan_ratio': fan, 'refrigerant_heat_w': q_coil, 'outlet_quality': q_coil / per_coil_flow / latent_co2},
        'co2': {'saturation_temperature_k': t_co2, 'pressure_pa': p_co2, 'pump_speed_ratio': speed,
                'pump_mass_flow_kg_s': flow, 'pump_power_w': w_pump},
        'cascade': {'heat_w': q_hx, 'approach_k': t_co2 - t_nh3},
        'nh3_low': {'pressure_pa': p_lp, 'saturation_temperature_k': t_nh3, 'mass_flow_kg_s': m_comp},
        'compressors': {'total_load': total_load, 'running': running, 'load_each': total_load / running,
                        'shaft_power_w': shaft, 'electric_power_w': electric, 'discharge_temperature_k': t_discharge,
                        'pressure_ratio': p_hp / p_lp},
        'condenser': {'pressure_pa': p_hp, 'condensing_temperature_k': t_cond, 'heat_rejection_w': q_cond,
                      'required_ua_w_k': ua_needed, 'fan_ratio': 1., 'return_gas_ratio': return_gas},
        'expansion_valve': {'opening_ratio': opening, 'mass_flow_kg_s': m_comp},
        'balance': {'station_input_w': station_in, 'heat_rejection_w': q_cond, 'residual_w': q_cond - station_in,
                    'electric_power_w': electric + n_rooms * cooler['fan_power_w'] * fan + w_pump + cond['fan_power_w']},
    }


def checks(d, p):
    out = []

    def check(name, ok, detail):
        out.append({'name': name, 'passed': bool(ok), 'detail': detail})
    check('station_energy_balance', abs(d['balance']['residual_w']) < 1e-6 * d['balance']['heat_rejection_w'],
          f'{d["balance"]["residual_w"]:.3e} W')
    check('cooler_fan_in_range', .1 < d['cooler']['fan_ratio'] < .95, f'{d["cooler"]["fan_ratio"]:.4f}')
    check('coil_not_supply_limited', d['cooler']['outlet_quality'] < p['air_cooler']['max_outlet_quality'],
          f'x_out {d["cooler"]["outlet_quality"]:.3f}')
    check('return_gas_in_range', .1 < d['condenser']['return_gas_ratio'] < .95, f'{d["condenser"]["return_gas_ratio"]:.4f}')
    check('valve_in_range', .05 < d['expansion_valve']['opening_ratio'] < .95, f'{d["expansion_valve"]["opening_ratio"]:.4f}')
    check('compressor_load_in_range', .5 < d['compressors']['load_each'] <= .95,
          f'{d["compressors"]["running"]} × {d["compressors"]["load_each"]:.4f}')
    check('pressure_ratio_inside_envelope', d['compressors']['pressure_ratio'] < p['compressors']['max_pressure_ratio'],
          f'{d["compressors"]["pressure_ratio"]:.3f}')
    check('temperature_ladder', d['nh3_low']['saturation_temperature_k'] < d['co2']['saturation_temperature_k']
          < d['room']['temperature_k'] and d['condenser']['condensing_temperature_k'] > p['condenser']['wet_bulb_temperature_k'],
          'T_NH3 < T_CO2 < T_room, T_cond > T_wb')
    target = p['targets']
    check('level_band', target['hp_level_lower'] <= target['hp_level_setpoint'] <= target['hp_level_upper'],
          f'{target["hp_level_lower"]} ≤ {target["hp_level_setpoint"]} ≤ {target["hp_level_upper"]}')
    return out


def build():
    text = (ROOT / 'parameters.json').read_text(encoding='utf-8')
    p = json.loads(text)
    require(p['case_id'] == 'nh3co2-two-room-v1', 'case mismatch')
    d = design(p)
    result = {'schema_version': 1, 'case_id': p['case_id'], 'scope': 'B0 independent steady design point (lumped station)',
              'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'coolprop_version': CoolProp.__version__},
              'input_sha256': {'parameters.json': hashlib.sha256(text.encode('utf-8')).hexdigest()},
              'reference_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'design': d, 'checks': checks(d, p)}
    require(all(c['passed'] for c in result['checks']), 'failed: ' + ', '.join(c['name'] for c in result['checks'] if not c['passed']))
    return result


def compare(expected, actual, path='root'):
    if isinstance(actual, dict):
        require(isinstance(expected, dict) and set(expected) == set(actual), path + ': keys differ')
        for key, value in actual.items():
            if not (path == 'root.environment' and key in ('python', 'platform')):
                compare(expected[key], value, f'{path}.{key}')
    elif isinstance(actual, list):
        require(len(expected) == len(actual), path + ': lengths differ')
        for i, value in enumerate(actual):
            compare(expected[i], value, f'{path}[{i}]')
    elif isinstance(actual, float):
        require(math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-6), path + ': changed')
    else:
        require(expected == actual, path + ': changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true')
    group.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = build()
        output = args.output or ROOT / 'references'
        if args.check:
            compare(json.loads((output / 'design_point.json').read_text(encoding='utf-8')), result)
        else:
            output.mkdir(parents=True, exist_ok=False)
            (output / 'design_point.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        d = result['design']
        print(f'B0 reference {"matches" if args.check else "written"}: {len(result["checks"])} checks')
        print(f'  fan {d["cooler"]["fan_ratio"]:.4f}, T_CO2 {d["co2"]["saturation_temperature_k"] - 273.15:.3f} °C, '
              f'Q_hx {d["cascade"]["heat_w"] / 1000:.3f} kW, compressors {d["compressors"]["running"]} × '
              f'{d["compressors"]["load_each"]:.4f}, return gas {d["condenser"]["return_gas_ratio"]:.4f}, '
              f'valve {d["expansion_valve"]["opening_ratio"]:.4f}, electric {d["balance"]["electric_power_w"] / 1000:.3f} kW')
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(f'B0 reference failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
