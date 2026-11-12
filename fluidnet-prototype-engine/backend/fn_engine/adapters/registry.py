"""One dispatcher for Python callers and HTTP. Registrations belong to the host application."""
from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
import json
import logging
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ValidationError

from .. import __version__
from .contracts import AdapterCatalog, AdapterDescription, AdapterError, AdapterRequest, AdapterResult, correlate_failure
from .units import UnitRule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdapterDefinition:
    adapter_id: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[Any], Any]
    version: int = 1
    input_units: Mapping[str, UnitRule] = field(default_factory=dict)
    output_units: Mapping[str, UnitRule] = field(default_factory=dict)

    def __post_init__(self):
        # A caller may retain its original dict; later changes must not alter a registered contract.
        object.__setattr__(self, 'input_units', MappingProxyType(dict(self.input_units)))
        object.__setattr__(self, 'output_units', MappingProxyType(dict(self.output_units)))
        for model, units in ((self.input_model, self.input_units), (self.output_model, self.output_units)):
            if set(units) - model.model_fields.keys():
                raise ValueError('Unit fields must exist as top-level model fields')
            if any(not isinstance(rule, UnitRule) for rule in units.values()):
                raise ValueError('Unit fields require UnitRule definitions')
        if not callable(self.handler):
            raise ValueError('Adapter handler must be callable')
        self.describe()  # Validate identifiers/version and ensure both schemas can be advertised.

    def describe(self) -> AdapterDescription:
        return AdapterDescription(adapter_id=self.adapter_id, version=self.version, description=self.description,
            input_schema=self.input_model.model_json_schema(), output_schema=self.output_model.model_json_schema(),
            input_units={key: rule.describe() for key, rule in self.input_units.items()},
            output_units={key: rule.describe() for key, rule in self.output_units.items()})


def _finite_json(value: Any) -> None:
    json.dumps(value, allow_nan=False)


def _validation_error(error: ValidationError) -> AdapterError:
    first = error.errors(include_url=False, include_input=False, include_context=False)[0]
    path = '.'.join(str(part) for part in first['loc'])
    return AdapterError('ADAPTER_INPUT_INVALID', first['msg'], field=path or None)


class AdapterRegistry:
    def __init__(self, definitions: Iterable[AdapterDefinition] = ()):
        self._definitions: dict[tuple[str, int], AdapterDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AdapterDefinition) -> None:
        """Register at server startup; duplicate IDs/versions are never silently overwritten."""
        key = (definition.adapter_id, definition.version)
        if key in self._definitions:
            raise ValueError(f'Adapter already registered: {key}')
        self._definitions[key] = definition

    def _get(self, adapter_id: str, version: int) -> AdapterDefinition:
        definition = self._definitions.get((adapter_id, version))
        if definition is None:
            raise AdapterError('ADAPTER_NOT_FOUND', f'没有适配器 {adapter_id!r} 的版本 {version}', status=404)
        return definition

    def catalog(self) -> AdapterCatalog:
        return AdapterCatalog(adapters=[self._definitions[key].describe() for key in sorted(self._definitions)])

    def describe(self, adapter_id: str, version: int = 1) -> AdapterDescription:
        return self._get(adapter_id, version).describe()

    def execute(self, request: AdapterRequest | Mapping[str, Any]) -> AdapterResult:
        if not isinstance(request, (AdapterRequest, Mapping)):
            raise AdapterError('ADAPTER_INPUT_INVALID', '计算请求应为对象')
        # Inspect raw fields before serialization: mutated models may contain cycles/non-JSON values.
        body = dict(request)
        try:
            # Revalidate model instances too, rather than trusting caller mutation after construction.
            request = AdapterRequest.model_validate(body)
        except ValidationError as error:
            failure = _validation_error(error)
            correlate_failure(failure.detail, body)
            raise failure from error
        try:
            return self._execute(request)
        except AdapterError as error:
            error.detail.adapter_id = request.adapter_id
            error.detail.version = request.version
            error.detail.request_id = request.request_id
            raise

    def _execute(self, request: AdapterRequest) -> AdapterResult:
        definition = self._get(request.adapter_id, request.version)
        inputs = deepcopy(request.inputs)
        try:
            _finite_json(inputs)
        except (TypeError, ValueError, OverflowError) as error:
            raise AdapterError('ADAPTER_INPUT_INVALID', '输入应为有限 JSON 数据', field='inputs') from error

        for key, unit in request.input_units.items():
            if key not in definition.input_units or key not in inputs:
                raise AdapterError('ADAPTER_UNIT_INVALID', f'输入 {key!r} 未声明单位或未提供数值', field=f'input_units.{key}')
            rule = definition.input_units[key]
            try:
                inputs[key] = rule.convert(inputs[key], unit, rule.canonical_unit)
            except ValueError as error:
                raise AdapterError('ADAPTER_UNIT_INVALID', str(error), field=f'input_units.{key}') from error
        # Reject wrong result units before invoking a potentially expensive solver/Worker.
        for key, unit in request.output_units.items():
            if key not in definition.output_units:
                raise AdapterError('ADAPTER_UNIT_INVALID', f'输出 {key!r} 未声明可转换单位', field=f'output_units.{key}')
            try:
                definition.output_units[key].check(unit)
            except ValueError as error:
                raise AdapterError('ADAPTER_UNIT_INVALID', str(error), field=f'output_units.{key}') from error
        try:
            values = definition.input_model.model_validate(inputs)
        except ValidationError as error:
            failure = _validation_error(error)
            failure.detail.field = 'inputs' + ('.'+failure.detail.field if failure.detail.field else '')
            raise failure from error
        try:
            raw = definition.handler(values)
        except AdapterError:
            raise
        except (ValueError, OSError) as error:
            details = getattr(error, 'diagnostics', None)
            diagnostic = getattr(error, 'diagnostic', None)
            if not details and diagnostic is not None:
                details = [diagnostic]
            diagnostics = [item.model_dump(mode='json') if isinstance(item, BaseModel) else item for item in (details or [])]
            code = getattr(error, 'code', None)
            if not diagnostics and code:
                diagnostics = [{'code': str(code), 'message': str(error)}]
            raise AdapterError('ADAPTER_CALCULATION_FAILED', str(error), diagnostics=diagnostics) from error
        except Exception as error:
            logger.exception('Adapter %s failed', request.adapter_id)
            raise AdapterError('ADAPTER_INTERNAL_ERROR', '计算服务内部错误', status=500) from error
        try:
            output = definition.output_model.model_validate(raw.model_dump() if isinstance(raw, BaseModel) else raw)
            outputs = output.model_dump(mode='json')
            units = {key: request.output_units.get(key, rule.canonical_unit) for key, rule in definition.output_units.items()}
            for key, rule in definition.output_units.items():
                # Undefined physical outputs (e.g. dew point for completely dry air) stay null.
                if outputs.get(key) is not None:
                    outputs[key] = rule.convert(outputs[key], rule.canonical_unit, units[key])
            _finite_json(outputs)
            return AdapterResult(adapter_id=request.adapter_id, version=request.version, request_id=request.request_id,
                                 engine_version=__version__, outputs=outputs, output_units=units)
        except (ValueError, TypeError, OverflowError) as error:
            logger.exception('Adapter %s returned invalid output', request.adapter_id)
            raise AdapterError('ADAPTER_OUTPUT_INVALID', '适配器输出不符合结果合同', status=500) from error
