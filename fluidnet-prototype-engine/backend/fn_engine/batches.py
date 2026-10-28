"""Preview and execute finite scenario batches from immutable saved inputs."""
from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
import json
import logging
import math
from threading import Condition, RLock, Thread

from .batch_models import (
    BatchControlSource, BatchCreateRequest, BatchModuleSource, BatchParameter,
    BatchPlanRequest, BatchPreviewItem, BatchPreviewResponse, BatchScenarioChoice,
    BatchSetupResponse, BatchSource, BatchVariable,
)
from .batch_store import BatchConflict, BatchStore
from .bridge import normalize_prototype_export
from .compiler import CompilationError, compile_project, validate_scenarios
from .jobs import RunManager
from .models import Project, ProjectDocument, RunCommand, RunRequest, Scenario, UnitSpec
from .storage import StorageError, WorkspaceStore

logger = logging.getLogger(__name__)
RATIO = UnitSpec(quantity='ratio', canonical_unit='1', display_unit='1')


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def observation_choices(project: Project) -> list[BatchVariable]:
    definitions = {module.id: module for module in project.modules}
    result = {}
    for node in project.instances:
        definition = definitions[node.module_id]
        specs = {p.id: p for p in definition.parameters}
        for variable in definition.variables:
            if not variable.sampleable:
                continue
            if variable.source == 'parameter':
                spec = specs.get(variable.parameter_id or '')
                if spec is not None and spec.value_type != 'number':
                    continue
            key = node.id + '.' + variable.id
            result[key] = BatchVariable(key=key, label=f'{node.name} · {variable.label}', unit=variable.unit or RATIO)
        for spec in definition.parameters:
            if spec.value_type == 'number':
                key = node.id + '.param.' + spec.id
                result.setdefault(key, BatchVariable(key=key, label=f'{node.name} · {spec.label}', unit=spec.unit or RATIO))
    for coupling in project.thermal_couplings:
        for suffix, label, quantity, canonical, display, scale, offset in (
            ('heat_w', '换热量', 'power', 'W', 'kW', 1000., 0.),
            ('mass_flow_kg_s', '流量', 'mass_flow', 'kg/s', 'kg/s', 1., 0.),
            ('fluid_inlet_temperature_k', '进液温度', 'temperature', 'K', '°C', 1., -273.15),
            ('fluid_outlet_temperature_k', '出液温度', 'temperature', 'K', '°C', 1., -273.15),
            ('refrigerant_temperature_k', '饱和温度', 'temperature', 'K', '°C', 1., -273.15),
            ('state.heat_energy_j', '累计传热量', 'energy', 'J', 'kWh', 3600000., 0.),
        ):
            key = f'coupling.{coupling.id}.{suffix}'
            result[key] = BatchVariable(key=key, label=f'{coupling.id} · {label}', unit=UnitSpec(
                quantity=quantity, canonical_unit=canonical, display_unit=display, display_scale=scale, display_offset=offset))
    for suffix, label, quantity, unit in (
        ('energy_residual_w', '能量残差', 'power', 'W'),
        ('mass_residual_kg_s', '质量残差', 'mass_flow', 'kg/s'),
        ('pressure_residual_pa', '压力残差', 'pressure', 'Pa'),
    ):
        key = 'metrics.' + suffix
        result[key] = BatchVariable(key=key, label=label, unit=UnitSpec(quantity=quantity, canonical_unit=unit, display_unit=unit))
    if project.thermal_couplings:
        for suffix, label, unit, display, scale in (
            ('coupling_heat_w', '盘管总传热量', 'W', 'kW', 1000.),
            ('coupling_heat_energy_j', '累计总传热量', 'J', 'kWh', 3600000.),
        ):
            key = 'metrics.' + suffix
            result[key] = BatchVariable(key=key, label=label, unit=UnitSpec(
                quantity='energy' if unit == 'J' else 'power', canonical_unit=unit, display_unit=display, display_scale=scale))
    return list(result.values())


class BatchService:
    def __init__(self, storage: WorkspaceStore, runner: RunManager):
        self.storage, self.runner = storage, runner
        self.store = BatchStore(storage)
        self.wake = Condition(RLock())
        self.assignment: tuple[str, int] | None = None
        self.generation = 0
        self.thread: Thread | None = None
        self.closed = False
        self.errors: dict[str, str] = {}

    def saved_project(self, project_id, revision):
        saved = self.storage.project(project_id, revision)
        document = ProjectDocument.model_validate(saved['document'])
        if document.project['id'] != project_id:
            raise ValueError('保存文档与项目 ID 不一致')
        project = normalize_prototype_export({'format': 'fluidnet-studio-prototype', 'schema': 1,
            'activeProject': project_id, 'projects': [document.project], 'modules': document.modules})
        # Batch observations have their own explicit list; old view selections must not hide them.
        project.selected_variables = []
        return project, saved['revision']

    def setup(self, project_id, revision=None):
        project, actual_revision = self.saved_project(project_id, revision)
        definitions = {module.id: module for module in project.modules}
        parameters = []
        for node in project.instances:
            for spec in definitions[node.module_id].parameters:
                if spec.value_type != 'number' or not spec.writable:
                    continue
                unit = spec.unit or RATIO
                value = node.parameters.get(spec.id, spec.default)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f'{node.id}.{spec.id} 不是有限数值')
                parameters.append(BatchParameter(instance_id=node.id, instance_name=node.name, parameter_id=spec.id,
                    label=spec.label, unit=unit, value=unit.from_canonical(value),
                    minimum=unit.from_canonical(spec.minimum) if spec.minimum is not None else None,
                    maximum=unit.from_canonical(spec.maximum) if spec.maximum is not None else None))
        return BatchSetupResponse(project_id=project.id, project_name=project.name, revision=actual_revision,
            parameters=parameters, variables=observation_choices(project),
            scenarios=[BatchScenarioChoice(id=s.id, name=s.name) for s in project.scenarios])

    def prepare(self, project_id, request: BatchPlanRequest):
        project, revision = self.saved_project(project_id, request.revision)
        definitions = {module.id: module for module in project.modules}
        available = {variable.key: variable for variable in observation_choices(project)}
        if set(request.variables) - available.keys():
            raise ValueError('所选观察变量未在项目中声明：' + '、'.join(sorted(set(request.variables) - available.keys())))
        items = []
        if request.sweep is not None:
            sweep = request.sweep
            node = next((n for n in project.instances if n.id == sweep.instance_id), None)
            if node is None:
                raise ValueError('扫描目标设备不存在')
            spec = next((p for p in definitions[node.module_id].parameters if p.id == sweep.parameter_id), None)
            if spec is None or spec.value_type != 'number' or not spec.writable:
                raise ValueError('扫描参数必须是设备已声明的可编辑数值参数')
            unit = spec.unit or RATIO
            values = sweep.values
            if values is None:
                interval = sweep.range
                if interval is None:
                    raise ValueError('缺少扫描值')
                values = [interval.start + (interval.stop - interval.start) * i / (interval.count - 1)
                          for i in range(interval.count)]
            if len(set(values)) != len(values):
                raise ValueError('扫描值不能重复')
            for index, value in enumerate(values, 1):
                canonical = unit.to_canonical(value)
                if not math.isfinite(canonical):
                    raise ValueError(f'第 {index} 个扫描值换算后不是有限数值')
                name = f'{node.id} · {spec.label} {value:g} {unit.display_unit}'
                scenario = Scenario(id=f'sweep_{index}', name=name, overrides={node.id: {spec.id: canonical}})
                items.append(BatchPreviewItem(id=f'item-{index}', name=name, scenario=scenario,
                                               parameter_value=value, parameter_unit=unit.display_unit))
        else:
            scenarios = {scenario.id: scenario for scenario in project.scenarios}
            if set(request.scenario_ids) - scenarios.keys():
                raise ValueError('所选工况不存在')
            for index, identifier in enumerate(request.scenario_ids, 1):
                scenario = scenarios[identifier].model_copy(deep=True)
                items.append(BatchPreviewItem(id=f'item-{index}', name=scenario.name, scenario=scenario,
                                               source_scenario_id=identifier))
        project.scenarios = [item.scenario for item in items]
        diagnostics = validate_scenarios(project, definitions)
        errors = [diagnostic for diagnostic in diagnostics if diagnostic.severity == 'error']
        if errors:
            raise ValueError('；'.join(d.message for d in errors))
        # Validate contracts/topology without solving every candidate during preview.
        # Physically unsolvable but well-formed cases become independent failed rows at run time.
        for item in items:
            candidate = self.runner.project_factory(project, item.scenario.id)
            compile_project(candidate)
        snapshot = project.model_dump(mode='json')
        source = BatchSource(project_id=project.id, project_name=project.name, revision=revision,
            snapshot_hash=digest(snapshot),
            modules=[BatchModuleSource(id=m.id, name=m.name, version=m.version, content_hash=m.content_hash,
                                      definition_hash=m.definition_hash or digest(m.model_dump(mode='json'))) for m in project.modules],
            controls=[BatchControlSource(id=s.id, enabled=s.enabled, content_hash=s.content_hash or
                                         sha256(s.source.encode('utf-8')).hexdigest()) for s in project.control_scripts])
        data = {'source': source.model_dump(mode='json'), 'options': request.options.model_dump(mode='json'),
                'variables': [available[key].model_dump(mode='json') for key in request.variables],
                'items': [item.model_dump(mode='json') for item in items]}
        return project, BatchPreviewResponse.model_validate({**data, 'preview_hash': digest(data)})

    def create(self, project_id, request: BatchCreateRequest):
        fingerprint = digest({'project_id': project_id, **request.model_dump(mode='json', exclude={'request_id', 'preview_hash'})})
        existing = self.store.existing(project_id, request.request_id, fingerprint)
        if existing:
            return self.detail(existing)
        if not request.name.strip():
            raise ValueError('批次名称不能为空')
        project, preview = self.prepare(project_id, request)
        if request.preview_hash is not None and request.preview_hash != preview.preview_hash:
            raise BatchConflict('项目或批次配置已变化，请重新预览')
        batch_id = self.store.create(project_id, request.request_id, fingerprint, request.name.strip(),
                                     project.model_dump(mode='json'), preview.model_dump(mode='json'))
        return self.detail(batch_id)

    def detail(self, batch_id):
        result = self.store.detail(batch_id)
        if batch_id in self.errors:
            result['status'], result['error'] = 'failed', self.errors[batch_id]
            for item in result['items']:
                if item['status'] != 'running':
                    continue
                try:
                    stopped = self.runner.snapshot(item['run_id'])['status'] in {
                        'completed', 'failed', 'cancelled', 'interrupted'}
                except KeyError:
                    stopped = True
                if stopped:
                    item['status'] = 'interrupted'
            for state in ('completed', 'failed', 'cancelled', 'interrupted'):
                result[state] = sum(item['status'] == state for item in result['items'])
        return result

    def list(self, project_id=None, offset=0, limit=50):
        result = self.store.list(project_id, offset, limit)
        for summary in result['batches']:
            if summary['id'] in self.errors:
                current = self.detail(summary['id'])
                for key in summary:
                    summary[key] = current[key]
        return result

    def _recover_storage_error(self, batch_id):
        if batch_id in self.errors:
            self._interrupt(batch_id, self.errors[batch_id])
            self.errors.pop(batch_id, None)

    def start(self, batch_id):
        with self.wake:
            if self.closed:
                raise BatchConflict('批次服务已关闭')
            self._recover_storage_error(batch_id)
            if self.store.start(batch_id):
                self.errors.pop(batch_id, None)
                self.generation += 1
                self.assignment = (batch_id, self.generation)
                if self.thread is None:
                    self.thread = Thread(target=self._schedule, name='fluidnet-batches', daemon=True)
                    self.thread.start()
                self.wake.notify_all()
        return self.detail(batch_id)

    def cancel_remaining(self, batch_id):
        with self.wake:
            self._recover_storage_error(batch_id)
            self.store.cancel_remaining(batch_id)
            self.wake.notify_all()
        return self.detail(batch_id)

    def _current(self, ticket):
        with self.wake:
            return not self.closed and self.assignment == ticket

    def _schedule(self):
        while True:
            with self.wake:
                while self.assignment is None and not self.closed:
                    self.wake.wait()
                if self.closed:
                    return
                ticket = self.assignment
            try:
                self._execute(ticket)
            except Exception as error:
                logger.exception('Batch execution interrupted')
                with self.wake:
                    try:
                        self._interrupt(ticket[0], str(error))
                    except Exception:
                        self.errors[ticket[0]] = '批次存档失败，已停止派发：' + str(error)
                        logger.exception('Could not persist batch interruption')
            finally:
                with self.wake:
                    if self.assignment == ticket:
                        self.assignment = None

    def _execute(self, ticket):
        batch_id = ticket[0]
        snapshot, metadata = self.store.snapshot(batch_id), self.store.metadata(batch_id)
        while self._current(ticket):
            next_item = self.store.begin_next(batch_id)
            if next_item is None:
                return
            item_id, scenario_id, run_id = next_item
            if not self._current(ticket):
                return
            request = RunRequest(project=Project.model_validate(snapshot),
                project_revision=metadata['source']['revision'], scenario_id=scenario_id,
                **metadata['options'], history='trend',
                trend_variables=[v['key'] for v in metadata['variables'] if not v['key'].startswith('metrics.')])
            self.runner.submit(request, run_id=run_id)
            while self._current(ticket) and self.store.item_state(batch_id, item_id) == 'running':
                # Terminal writes normally capture results atomically. An archive failure is
                # surfaced from the run manager rather than letting this queue hang forever.
                try:
                    record = self.runner.snapshot(run_id)
                except KeyError:
                    if self.store.item_state(batch_id, item_id) == 'running':
                        raise StorageError('批次运行已消失且结果尚未保存')
                    break
                if record['status'] in {'completed', 'failed', 'cancelled', 'interrupted'}:
                    failure = next((d for d in (record.get('frame') or {}).get('diagnostics', [])
                                    if d['code'] == 'STORAGE_FAILED'), None)
                    if failure is not None:
                        raise StorageError(failure['message'])
                    self.store.capture(record, self.runner.overview(run_id), record['total_rows'])
                with self.wake:
                    self.wake.wait(timeout=.03)
            if self._current(ticket):
                item = next(i for i in self.store.detail(batch_id)['items'] if i['id'] == item_id)
                failure = next((d for d in item['diagnostics'] if d['code'] == 'STORAGE_FAILED'), None)
                if failure is not None:
                    raise StorageError(failure['message'])

    def _interrupt(self, batch_id, error=None):
        detail = self.store.detail(batch_id)
        for item in detail['items']:
            if item['status'] != 'running' or not item['run_id']:
                continue
            try:
                record = self.runner.snapshot(item['run_id'])
                record['status'] = 'interrupted'
                if record.get('frame'):
                    record['frame'].update(status='interrupted', valid=False)
                self.store.capture(record, self.runner.overview(item['run_id']), record['total_rows'])
                try:
                    self.runner.command(item['run_id'], RunCommand(action='stop'))
                except CompilationError as failure:
                    if failure.diagnostic.code != 'RUN_ALREADY_FINISHED':
                        raise
            except KeyError:
                pass
        self.store.interrupt(batch_id, error)

    def close(self):
        with self.wake:
            self.closed = True
            ticket = self.assignment
            self.wake.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=10.)
            if self.thread.is_alive():
                raise StorageError('批次调度尚未退出')
        if ticket is not None:
            self._interrupt(ticket[0])

    def csv(self, batch_id):
        detail = self.detail(batch_id)
        text = StringIO(newline='')
        writer = csv.writer(text)

        def cell(value):
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                return "'" + value
            return value

        variables = detail['variables']
        writer.writerow(['批次', '项目', '项目修订', '输入快照', '工况', '状态', '运行 ID', '仿真时间/s',
                         '扫描值', '扫描单位', '诊断', *[cell(v['label'] + '/' + v['unit']['display_unit']) for v in variables]])
        for item in detail['items']:
            values = []
            for variable in variables:
                value = item['values'].get(variable['key']) if item['status'] == 'completed' else None
                unit = variable['unit']
                values.append((value / unit['display_scale'] + unit['display_offset']) if value is not None else '')
            writer.writerow([cell(detail['name']), cell(detail['project_name']), detail['project_revision'],
                detail['snapshot_hash'], cell(item['name']), item['status'], item['run_id'] or '',
                item['time_s'] if item['time_s'] is not None else '',
                item['parameter_value'] if item['parameter_value'] is not None else '', cell(item['parameter_unit'] or ''),
                cell('；'.join(d['message'] for d in item['diagnostics'] if d.get('severity') != 'info')), *values])
        return '\ufeff' + text.getvalue()
