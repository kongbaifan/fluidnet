"""接受子步上的候选累计量。失败和重试不修改已接受账本。"""
from copy import deepcopy

from .moist_air import vapor_enthalpy

ACCUMULATORS = {
    'cooling_coil':{'condensate_kg':'condensate_kg_s','cooling_energy_j':'cooling_load_w'},
    'humidifier':{'water_added_kg':'moisture_addition_kg_s','heating_energy_j':'heat_w'},
    'air_room':{'moisture_added_kg':'moisture_load_kg_s','load_energy_j':None},
    'cooling_tower_moist':{'evaporated_kg':'evaporation_kg_s','drift_kg':'drift_kg_s',
                          'blowdown_kg':'blowdown_kg_s','makeup_kg':'makeup_kg_s','heat_rejected_j':'heat_rejected_w'},
}


def initial_accumulators(network):
    return {inst.id:{key:0. for key in ACCUMULATORS[kind]}
            for inst in network.instances.values()
            if (kind:=network.modules[inst.module_id].solver_model) in ACCUMULATORS}


def advance_accumulators(network,accepted,result,dt):
    from .solver import snapshot
    values=snapshot(network,result).variables
    candidate=deepcopy(accepted)
    for iid,ledger in candidate.items():
        kind=network.modules[network.instances[iid].module_id].solver_model
        params=network.parameters[iid]
        for target,source in ACCUMULATORS[kind].items():
            rate=(params['sensible_load_w']+params['moisture_load_kg_s']*vapor_enthalpy(params['moisture_source_temperature_k'])
                  if source is None else values[f'{iid}.{source}'])
            ledger[target]+=rate*dt
    return candidate
