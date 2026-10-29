"""Schema-specific parsing, canonical hashes and pre-execution SDK negotiation."""
import hashlib
import json

from ._module_schema_v1 import ModuleDefinitionV1
from ._module_schema_v2 import ModuleDefinitionV2, ModuleSDKRequirements
from ._module_schema_v3 import ModuleDefinitionV3

CONTRACT_SCHEMAS = {1: ModuleDefinitionV1, 2: ModuleDefinitionV2, 3: ModuleDefinitionV3}
_BASE_CAPABILITIES = frozenset({
    'lifecycle.v1', 'state.json.v1', 'properties.v1',
    'net.pipe', 'net.valve', 'net.pump', 'net.compressor',
})
SDK_CAPABILITIES = {
    '0.1.0': _BASE_CAPABILITIES,
    '0.2.0': _BASE_CAPABILITIES | {'net.resistance', 'hydraulics.v1'},
    '0.3.0': _BASE_CAPABILITIES | {'net.resistance', 'hydraulics.v1', 'context.execution.v1'},
}
SDK_CAPABILITIES['0.4.0'] = SDK_CAPABILITIES['0.3.0'] | {
    'context.log.v1', 'thermal.v1', 'observe.v1', 'thermal.conservative.v1', 'state.transactions.v1'}
SDK_CAPABILITIES['0.5.0'] = SDK_CAPABILITIES['0.4.0'] | {'hydraulic.derivatives.v1', 'composite.v1', 'evaluate.pure.v1'}
SDK_CAPABILITIES['0.5.0'] = SDK_CAPABILITIES['0.5.0'] | {'hydraulic.signed_start.v1'}
SDK_CAPABILITIES['0.6.0'] = SDK_CAPABILITIES['0.5.0'] | {'air.properties.v1', 'air.pass_through.v1'}
STATE_CONTRACT_VERSIONS = frozenset({1})


def air_request_payload(definition, payload):
    """旧协议仅过滤状态字段，不碰用户参数、state 或自定义变量。"""
    if definition.sdk and 'air.pass_through.v1' in definition.sdk.capabilities:
        return payload
    extra = {'humidity_ratio_kg_kg', 'relative_humidity', 'enthalpy_j_kg_dry_air',
             'specific_heat_j_kg_dry_air_k', 'dew_point_k', 'wet_bulb_k',
             'dry_air_mass_flow_kg_s', 'water_vapor_mass_flow_kg_s',
             'inlet_mass_flow_kg_s', 'outlet_mass_flow_kg_s'}
    result = dict(payload)
    if 'request' in result:
        request = dict(result['request'])
        for name in ('trial_ports', 'converged_ports', 'ports', 'channels', 'converged_channels'):
            if name in request:
                request[name] = {key: {k:v for k,v in value.items() if k not in extra}
                                 for key,value in request[name].items()}
        result['request'] = request
    return result


class ModuleCompatibilityError(ValueError):
    def __init__(self, code, message, field):
        self.code, self.field = code, field
        super().__init__(message)


def contract_model(definition):
    """Revalidate even model_copy/attribute edits using the frozen schema parser."""
    parser = CONTRACT_SCHEMAS.get(definition.schema_version)
    if parser is None:
        raise ModuleCompatibilityError('MODULE_SCHEMA_UNSUPPORTED',
            f'不支持的模块合同 schema_version：{definition.schema_version}', 'schema_version')
    # Only module-contract fields participate; catalog presentation fields do not.
    fields = set(ModuleDefinitionV3.model_fields)
    return parser.model_validate(definition.model_dump(mode='json', include=fields))


def _canonical_numbers(value):
    if isinstance(value, dict):
        return {key: _canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def canonical_contract_bytes(definition):
    parser = CONTRACT_SCHEMAS.get(definition.schema_version)
    if parser is None:
        raise ModuleCompatibilityError('MODULE_SCHEMA_UNSUPPORTED',
            f'不支持的模块合同 schema_version：{definition.schema_version}', 'schema_version')
    # Upgrade previews hash edited drafts before reporting incompatible references.
    # Use frozen serialization without rerunning module cross-reference validation.
    module = parser.model_construct(**{name: getattr(definition, name) for name in parser.model_fields})
    if definition.schema_version >= 2:
        sdk = definition.sdk
        module.sdk = ModuleSDKRequirements.model_validate(None if sdk is None else sdk.model_dump(mode='json'))
    payload = module.model_dump(mode='json', exclude={'content_hash', 'definition_hash', 'package_path'})
    return json.dumps(_canonical_numbers(payload), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def definition_hash(definition):
    return hashlib.sha256(canonical_contract_bytes(definition)).hexdigest()


def check_module_compatibility(definition):
    module = contract_model(definition)
    if module.schema_version == 1:
        return
    requirement = module.sdk
    supported = SDK_CAPABILITIES.get(requirement.api_version)
    if supported is None:
        raise ModuleCompatibilityError('MODULE_SDK_UNSUPPORTED',
            f'不支持的 SDK API 版本：{requirement.api_version}；支持 {", ".join(SDK_CAPABILITIES)}', 'sdk.api_version')
    missing = sorted(set(requirement.capabilities) - supported)
    if missing:
        raise ModuleCompatibilityError('MODULE_CAPABILITY_UNSUPPORTED',
            f'SDK {requirement.api_version} 不支持能力：{", ".join(missing)}', 'sdk.capabilities')
    if requirement.state_contract_version not in STATE_CONTRACT_VERSIONS:
        raise ModuleCompatibilityError('MODULE_STATE_CONTRACT_UNSUPPORTED',
            f'不支持的状态合同版本：{requirement.state_contract_version}', 'sdk.state_contract_version')
