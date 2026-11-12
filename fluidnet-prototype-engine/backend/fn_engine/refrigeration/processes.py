"""Conserved cold-room, frost/water and oil processes on host physical coordinates."""
from functools import lru_cache
import math

from CoolProp.HumidAirProp import HAPropsSI

from ..state_space import PhysicalStateSpace
from .cycle import DeviceRangeError

T0 = 273.15
CP_DRY, CP_VAPOR, CP_ICE, CP_WATER = 1006., 1860., 2100., 4180.
FUSION, VAPORIZATION = 334000., 2500800.
VAPOR_H0 = FUSION + VAPORIZATION  # Ice at 0 C is the water energy reference.


def vapor_h(temperature):
    return VAPOR_H0 + CP_VAPOR * (temperature - T0)


@lru_cache(maxsize=2048)
def humidity_ratio(temperature, pressure, rh):
    try:
        return HAPropsSI('W', 'T', temperature, 'P', pressure, 'R', rh)
    except ValueError as error:
        raise DeviceRangeError('PROCESS_HUMIDITY_RANGE', '热湿状态超出湿空气物性范围') from error


def moist_h(temperature, ratio):
    return CP_DRY * (temperature - T0) + ratio * vapor_h(temperature)


def moist_density(temperature, pressure, ratio):
    return pressure * (1. + ratio) / (287.055 * temperature * (1. + 1.6078 * ratio))


def door_exchange(p, temperature, ratio):
    """Integrate the two hydrostatic opening flows with a dry-mass-balanced neutral plane."""
    ambient = p['ambient_temperature_k']
    w = humidity_ratio(ambient, p['air_pressure_pa'], p['ambient_relative_humidity'])
    inside = moist_density(temperature, p['air_pressure_pa'], ratio)
    outside = moist_density(ambient, p['air_pressure_pa'], w)
    difference = abs(inside - outside)
    a = outside / (1. + w) * math.sqrt(2. * 9.80665 * difference / outside)
    b = inside / (1. + ratio) * math.sqrt(2. * 9.80665 * difference / inside)
    height = p['door_height_m']
    neutral = height * a ** (2. / 3.) / (a ** (2. / 3.) + b ** (2. / 3.)) if a + b > 0. else height / 2.
    exchange = (2. / 3. * p['door_discharge_coefficient'] * p['door_width_m'] * a * (height - neutral) ** 1.5
                + p['mechanical_exchange_kg_s'])
    exchange *= p['door_opening_ratio'] * (1. - p['door_protection_efficiency'])
    return exchange, w, exchange * (moist_h(ambient, w) - moist_h(temperature, ratio))


def goods_enthalpy(p, temperature):
    delta = temperature - p['goods_freezing_temperature_k']
    return p['goods_frozen_cp_j_kg_k'] * delta if delta < 0. else (
        p['goods_latent_heat_j_kg'] + p['goods_unfrozen_cp_j_kg_k'] * delta)


def goods_state(p, energy):
    mass = p['goods_mass_kg']
    if mass <= 0.: return None, None
    h, latent, freeze = energy / mass, p['goods_latent_heat_j_kg'], p['goods_freezing_temperature_k']
    if h < 0.: return freeze + h / p['goods_frozen_cp_j_kg_k'], 1.
    if h <= latent: return freeze, 1. - h / latent
    return freeze + (h - latent) / p['goods_unfrozen_cp_j_kg_k'], 0.


def frost_state(p, mass, energy):
    if mass < -1e-12: raise DeviceRangeError('FROST_MASS_RANGE', '霜/水库存不能为负')
    mass = max(mass, 0.)
    metal = p['metal_heat_capacity_j_k']
    if energy < 0.: return T0 + energy / (metal + mass * CP_ICE), mass, 0.
    if energy <= mass * FUSION: return T0, mass - energy / FUSION, energy / FUSION
    return T0 + (energy - mass * FUSION) / (metal + mass * CP_WATER), 0., mass


class ProcessEngine:
    def __init__(self, network):
        self.network = network
        self.space = PhysicalStateSpace()
        self.rooms = [i.id for i in network.project.instances if i.module_id == 'logistics_cold_room']
        self.frosts = [i.id for i in network.project.instances if i.module_id == 'frost_hotgas_cooler']
        self.oils = [i.id for i in network.project.instances if i.module_id == 'compressor_oil_system']
        self.room_of = {c: room for room, coolers in network.room_cooler_groups.items() for c in coolers}
        self.oil_coolers = {}
        for iid in self.rooms:
            p = network.parameters[iid]
            w = humidity_ratio(p['temperature_k'], p['air_pressure_pa'], p['initial_relative_humidity'])
            mass = p['dry_air_mass_kg'] * w
            self.add(iid, 'water_vapor_mass_kg', 'mass', mass, medium='water', minimum=0.)
            self.add(iid, 'room_energy_j', 'energy', p['heat_capacity_j_k'] * (p['temperature_k'] - T0) + mass * vapor_h(p['temperature_k']))
            self.add(iid, 'goods_energy_j', 'energy', p['goods_mass_kg'] * goods_enthalpy(p, p['goods_initial_temperature_k']))
            self.add(iid, 'net_water_import_kg', 'mass', 0., medium='water', ledger=True)
            self.add(iid, 'infiltration_energy_j', 'energy', 0., ledger=True)
        for iid in self.frosts:
            p = network.parameters[iid]
            mass, delta = p['initial_frost_mass_kg'], p['initial_surface_temperature_k'] - T0
            energy = (p['metal_heat_capacity_j_k'] + mass * CP_ICE) * delta if delta < 0. else (
                mass * FUSION + (p['metal_heat_capacity_j_k'] + mass * CP_WATER) * delta)
            self.add(iid, 'frost_water_mass_kg', 'mass', mass, medium='water', minimum=0.)
            self.add(iid, 'surface_energy_j', 'energy', energy)
            self.add(iid, 'drained_water_kg', 'mass', 0., medium='water', ledger=True, minimum=0.)
            self.add(iid, 'drain_energy_j', 'energy', 0., ledger=True)
        for iid in self.oils:
            p = network.parameters[iid]
            circuit = network.circuit_of[network.vessel(iid, 'in0')]
            coolers = [c for c in self.room_of if network.circuit_of[network.vessel(c, 'in0')] == circuit]
            graph_ids = network.hydraulic_graph.instance_ids if network.hydraulic_graph else set()
            if any(c not in graph_ids or network.kinds[c] not in ('air_cooler', 'network_air_cooler', 'frost_hotgas_cooler') for c in coolers):
                from ..compiler import CompilationError
                raise CompilationError('OIL_COOLER_GRAPH_REQUIRED', '油路换热要求同回路冷风机使用图式供回液网络', iid)
            self.oil_coolers[iid] = coolers
            for group, mass in [('sump', p['initial_sump_mass_kg']), ('separator', p['initial_separator_mass_kg']),
                                ('receiver', 0.), *[(c, 0.) for c in coolers]]:
                self.add(iid, group + '_mass_kg', 'mass', mass, medium='oil', minimum=0.)
                energy = (p['metal_heat_capacity_j_k'] + mass * p['oil_cp_j_kg_k']) * (p['initial_oil_temperature_k'] - T0)
                self.add(iid, group + '_energy_j', 'energy', energy)
        initial = self.space.initial_values()
        self.initial_mass = {medium: self.space.mass(initial, medium) for medium in ('water', 'oil')}

    def add(self, iid, name, quantity, initial, **options):
        return self.space.add(iid, name, quantity, initial, **options)

    @staticmethod
    def key(iid, name): return f'{iid}::{name}'

    def value(self, values, iid, name): return values[self.key(iid, name)]

    def room_state(self, values, iid):
        p = self.network.parameters[iid]
        mass = self.value(values, iid, 'water_vapor_mass_kg')
        energy = self.value(values, iid, 'room_energy_j')
        temperature = T0 + (energy - mass * VAPOR_H0) / (p['heat_capacity_j_k'] + mass * CP_VAPOR)
        if temperature < 180. or temperature > 380.: raise DeviceRangeError('ROOM_PROCESS_RANGE', '库房温度离开热湿参考模型范围', iid)
        return temperature, mass / p['dry_air_mass_kg']

    def oil_temperature(self, values, iid, group):
        p = self.network.parameters[iid]
        return T0 + self.value(values, iid, group + '_energy_j') / (
            p['metal_heat_capacity_j_k'] + self.value(values, iid, group + '_mass_kg') * p['oil_cp_j_kg_k'])

    def initial_modes(self):
        return {iid: {'mode': 0, 'since': 0., 'count': 0, 'latched': False} for iid in self.frosts}

    def temperatures(self, values):
        return {iid: self.room_state(values, iid)[0] for iid in self.rooms}

    def effective_parameters(self, values, modes):
        changes = {}
        for iid in self.frosts:
            p = self.network.parameters[iid]
            surface, ice, _ = frost_state(p, self.value(values, iid, 'frost_water_mass_kg'), self.value(values, iid, 'surface_energy_j'))
            if not 180. <= surface <= 380.: raise DeviceRangeError('FROST_SURFACE_RANGE', '盘管表温离开模型范围', iid)
            mode = modes[iid]['mode']
            resistance = ice / (p['frost_density_kg_m3'] * p['surface_area_m2'] ** 2 * p['frost_conductivity_w_m_k'])
            ua = 1. / (1. / p['ua_w_k'] + resistance) if p['ua_w_k'] > 0. else 0.
            changes[iid] = {**p, '_surface_temperature_k': surface, '_air_ua_w_k': ua,
                '_cooling_enabled': mode in (0, 4), '_hot_enabled': mode == 2,
                '_defrost_mode': mode, 'fan_ratio': p['fan_ratio'] if mode == 0 else 0.}
        for iid in self.oils:
            p = self.network.parameters[iid]
            changes[iid] = {**p, '_oil_temperature_k': self.oil_temperature(values, iid, 'separator')}
            for cooler in self.oil_coolers[iid]:
                target = changes.setdefault(cooler, dict(self.network.parameters[cooler]))
                mass = self.value(values, iid, cooler + '_mass_kg')
                factor = 1. / (1. + p['fouling_per_kg'] * mass)
                if cooler in self.frosts:
                    target['_contact_factor'] = target.get('_contact_factor', 1.) * factor
                else:
                    target['ua_w_k'] *= factor
                target.setdefault('_oil_terms', []).append((iid, self.oil_temperature(values, iid, cooler), p['evaporator_contact_ua_w_k']))
        return changes

    def transition(self, modes, values, time_s):
        events = []
        for iid in self.frosts:
            p, state = self.network.parameters[iid], modes[iid]
            request = p['defrost_request'] >= .5
            if not request: state['latched'] = False
            if request and not state['latched'] and state['mode'] == 0:
                state.update(mode=1, since=time_s, count=state['count'] + 1, latched=True)
                events.append((iid, 1))
            while state['mode']:
                mode = state['mode']
                duration = {1: p['predrain_duration_s'], 2: p['defrost_duration_s'],
                            3: p['drip_duration_s'], 4: p['recool_duration_s']}[mode]
                surface, ice, _ = frost_state(p, self.value(values, iid, 'frost_water_mass_kg'), self.value(values, iid, 'surface_energy_j'))
                complete = mode == 2 and ice < 1e-8 and surface >= p['defrost_end_temperature_k'] - 1e-7
                if not complete and time_s < state['since'] + duration - 1e-9: break
                new = (mode + 1) % 5
                state.update(mode=new, since=time_s if complete else state['since'] + duration)
                events.append((iid, new))
        return events

    def boundaries(self, modes):
        return [state['since'] + {1: self.network.parameters[iid]['predrain_duration_s'],
            2: self.network.parameters[iid]['defrost_duration_s'], 3: self.network.parameters[iid]['drip_duration_s'],
            4: self.network.parameters[iid]['recool_duration_s']}[state['mode']]
            for iid, state in modes.items() if state['mode']]

    def event_fraction(self, old, new, modes):
        fractions = []
        for iid in self.frosts:
            if modes[iid]['mode'] != 2: continue
            p = self.network.parameters[iid]
            def surface(values):
                return (self.value(values, iid, 'surface_energy_j') - FUSION * self.value(values, iid, 'frost_water_mass_kg')
                        - (p['metal_heat_capacity_j_k'] + CP_WATER * self.value(values, iid, 'frost_water_mass_kg')) * (p['defrost_end_temperature_k'] - T0))
            a, b = surface(old), surface(new)
            if a < -1e-5 and b > 1e-5: fractions.append(-a / (b - a))
        return min(fractions, default=1.)

    def apply(self, result, values, modes, temperatures, effective):
        rates = dict.fromkeys(self.space.coordinates, 0.)
        devices = result['devices']
        deposits = dict.fromkeys(self.rooms, 0.)
        for iid in self.frosts:
            p = self.network.parameters[iid]
            state = modes[iid]
            room = self.room_of[iid]
            surface, ice, water = frost_state(p, self.value(values, iid, 'frost_water_mass_kg'), self.value(values, iid, 'surface_energy_j'))
            r = devices[iid]
            deposit = 0.
            if room in self.rooms and state['mode'] == 0:
                room_t, ratio = self.room_state(values, room)
                saturation = humidity_ratio(surface, self.network.parameters[room]['air_pressure_pa'], 1.)
                deposit = p['dry_air_flow_kg_s'] * effective[iid]['fan_ratio'] * p['deposition_effectiveness'] * max(0., ratio - saturation)
                deposits[room] += deposit
            drain = water / p['drain_time_constant_s'] if state['mode'] in (3, 4, 0) else 0.
            hot = r.get('hot_gas_heat_w', 0.)
            electric = p['electric_defrost_power_w'] if state['mode'] == 2 else 0.
            air_heat = r.get('air_sensible_heat_w', r['room_cooling_w'] + r['fan_power_w'])
            drain_h = FUSION + CP_WATER * (surface - T0)
            rates[self.key(iid, 'frost_water_mass_kg')] = deposit - drain
            rates[self.key(iid, 'surface_energy_j')] = air_heat + deposit * vapor_h(temperatures[room]) + hot + electric - (r['refrigerant_heat_w'] - r.get('oil_heat_w', 0.)) - drain * drain_h
            rates[self.key(iid, 'drained_water_kg')] = drain
            rates[self.key(iid, 'drain_energy_j')] = drain * drain_h
            result['boundary_w'] += electric - drain * drain_h
            r.update(frost_mass_kg=ice, melt_water_mass_kg=water, surface_temperature_k=surface,
                     frost_thickness_m=ice / (p['frost_density_kg_m3'] * p['surface_area_m2']),
                     effective_air_ua_w_k=effective[iid]['_air_ua_w_k'], deposition_water_kg_s=deposit,
                     defrost_mode=state['mode'], hot_gas_heat_w=hot, heater_power_w=electric)
        for iid in self.rooms:
            p = self.network.parameters[iid]
            temperature, ratio = self.room_state(values, iid)
            exchange, ambient_w, infiltration = door_exchange(p, temperature, ratio)
            goods_t, frozen = goods_state(p, self.value(values, iid, 'goods_energy_j'))
            goods_heat = p['goods_ua_w_k'] * (goods_t - temperature) if goods_t is not None else 0.
            deposit = deposits[iid]
            moisture = exchange * (ambient_w - ratio)
            r = devices[iid]
            external = r['envelope_heat_w'] + p['heat_input_w']
            rates[self.key(iid, 'water_vapor_mass_kg')] = moisture - deposit
            rates[self.key(iid, 'room_energy_j')] = external + infiltration + goods_heat - r['cooling_power_w'] - deposit * vapor_h(temperature)
            rates[self.key(iid, 'goods_energy_j')] = -goods_heat
            rates[self.key(iid, 'net_water_import_kg')] = moisture
            rates[self.key(iid, 'infiltration_energy_j')] = infiltration
            result['boundary_w'] += infiltration
            r.update(stored_energy_j=self.value(values, iid, 'room_energy_j') + self.value(values, iid, 'goods_energy_j'), humidity_ratio_kg_kg=ratio, goods_temperature_k=goods_t, goods_frozen_ratio=frozen,
                     door_dry_air_flow_kg_s=exchange, infiltration_heat_w=infiltration, temperature_k=temperature)
        for iid in self.oils:
            p = self.network.parameters[iid]
            r = devices[iid]
            coolers = self.oil_coolers[iid]
            carry = min(abs(r['mass_flow_kg_s']) * p['carryover_ratio'], self.value(values, iid, 'sump_mass_kg') / p['sump_draw_time_s'])
            captured, leak = carry * p['separation_efficiency'], carry * (1. - p['separation_efficiency'])
            ret = self.value(values, iid, 'separator_mass_kg') / p['separator_return_time_s'] * p['return_ratio']
            flow = sum(abs(devices[c]['mass_flow_kg_s']) for c in coolers)
            delivered = self.value(values, iid, 'receiver_mass_kg') / p['receiver_transport_time_s'] * min(1., flow / p['oil_reference_flow_kg_s'])
            sump_h = p['oil_cp_j_kg_k'] * (self.oil_temperature(values, iid, 'sump') - T0)
            sep_h = p['oil_cp_j_kg_k'] * (self.oil_temperature(values, iid, 'separator') - T0)
            rec_h = p['oil_cp_j_kg_k'] * (self.oil_temperature(values, iid, 'receiver') - T0)
            cooling = p['oil_cooler_ua_w_k'] * (self.oil_temperature(values, iid, 'separator') - p['oil_sink_temperature_k'])
            rates[self.key(iid, 'sump_mass_kg')] = ret - carry
            rates[self.key(iid, 'sump_energy_j')] = ret * sep_h - carry * sump_h
            rates[self.key(iid, 'separator_mass_kg')] = captured - ret
            rates[self.key(iid, 'separator_energy_j')] = captured * sump_h - ret * sep_h - r['heat_w'] - cooling
            rates[self.key(iid, 'receiver_mass_kg')] = leak - delivered
            rates[self.key(iid, 'receiver_energy_j')] = leak * sump_h - delivered * rec_h
            for cooler in coolers:
                returned = self.value(values, iid, cooler + '_mass_kg') / p['evaporator_return_time_s'] * p['return_ratio']
                inflow = delivered * abs(devices[cooler]['mass_flow_kg_s']) / flow if flow > 0. else 0.
                oil_h = p['oil_cp_j_kg_k'] * (self.oil_temperature(values, iid, cooler) - T0)
                terms = effective.get(cooler, {}).get('_oil_terms', [])
                ref_t = devices[cooler]['evaporating_temperature_k']
                total = sum(ua * (t - ref_t) for _, t, ua in terms)
                requested = p['evaporator_contact_ua_w_k'] * (self.oil_temperature(values, iid, cooler) - ref_t)
                actual = requested * devices[cooler].get('oil_heat_w', 0.) / total if abs(total) > 1e-12 else requested
                rates[self.key(iid, cooler + '_mass_kg')] = inflow - returned
                rates[self.key(iid, cooler + '_energy_j')] = inflow * rec_h - returned * oil_h - actual
                rates[self.key(iid, 'sump_mass_kg')] += returned
                rates[self.key(iid, 'sump_energy_j')] += returned * oil_h
            result['boundary_w'] -= cooling
            r['oil_cooling_w'] = cooling
        result['dt'].update(rates)
        result['physical_rates'] = rates
        return result

    def variables(self, values, modes, result):
        variables = self.space.variables(values)
        for iid in self.rooms:
            temperature, ratio = self.room_state(values, iid)
            variables.update({f'{iid}.state.temperature_k': temperature, f'{iid}.humidity_ratio_kg_kg': ratio})
        for iid in self.frosts:
            variables[f'{iid}.state.defrost_count'] = modes[iid]['count']
        for iid in (*self.rooms, *self.frosts, *self.oils):
            variables.update({f'{iid}.{key}': value for key, value in result['devices'][iid].items()
                              if value is None or isinstance(value, (str, bool, int, float))})
        for iid in self.oils:
            selected = {key: value for key, value in values.items() if self.space.coordinates[key].instance_id == iid}
            mass = self.space.mass(selected, 'oil')
            initial = self.space.mass({key: self.space.coordinates[key].initial for key in selected}, 'oil')
            variables.update({f'{iid}.oil_total_mass_kg': mass, f'{iid}.oil_mass_residual_kg': mass - initial,
                              f'{iid}.oil_energy_j': self.space.energy(selected)})
        return variables
