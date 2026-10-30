from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from .module_contracts import contract_model
from .models import (ModuleDefinition, ModulePackageRef, ModuleSaveRequest,
                     ModuleTestRequest, ModuleVersionInfo, ModuleVersionResponse)
from .runtime import design_source, module_content_hash, module_definition_hash, module_source


def load_module_package(path: str | Path) -> ModuleDefinition:
    """Load the versioned module-package directory into the Pydantic manifest."""
    root = Path(path)
    manifest_path = root / "manifest.json"
    source_path = root / "module.py"
    if not manifest_path.exists() or not source_path.exists():
        raise ValueError(f"模块包缺少 manifest.json 或 module.py：{root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = source_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    declared = manifest.get("content_hash")
    if declared and declared != digest:
        raise ValueError(f"模块包内容哈希不一致：{root}")
    # design.py is optional and covered by definition_hash, not content_hash (runtime code only).
    sources = {"runtime": source}
    if (root / "design.py").exists():
        sources["design"] = (root / "design.py").read_text(encoding="utf-8")
    payload = {**manifest, "source": sources, "runtime": "python",
               "content_hash": digest, "package_path": str(root)}
    definition = ModuleDefinition.model_validate(payload)
    digest = module_definition_hash(definition)
    if definition.definition_hash and definition.definition_hash != digest:
        raise ValueError(f"模块包契约哈希不一致：{root}")
    definition.definition_hash = digest
    return definition


def discover_module_packages(root: str | Path) -> list[ModuleDefinition]:
    base = Path(root)
    if not base.exists():
        return []
    definitions = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "manifest.json").exists():
            definitions.append(load_module_package(child))
    return definitions


def package_ref(module: ModuleDefinition) -> ModulePackageRef:
    return ModulePackageRef(module_id=module.id, version=f"{module.version}.0.0",
                            content_hash=module.content_hash or module_content_hash(module),
                            definition_hash=module.definition_hash)


class ModuleVersionConflict(ValueError):
    pass


class ModuleSaveInvalid(ValueError):
    def __init__(self, diagnostics, replay=None):
        self.diagnostics = diagnostics
        self.replay = replay
        super().__init__("；".join(d.message for d in diagnostics))


class ModuleStore:
    """Immutable, locally persisted releases; seed packages are read-only."""

    def __init__(self, seed_root: Path, storage_root: Path):
        self.seed_root = seed_root
        self.root = storage_root
        self.lock = Lock()

    def definitions(self) -> list[ModuleDefinition]:
        definitions = {(m.id, m.version): m for m in discover_module_packages(self.seed_root)}
        if self.root.exists():
            for manifest in sorted(self.root.glob("module-*/v*/manifest.json")):
                module = load_module_package(manifest.parent)
                definitions[(module.id, module.version)] = module
        return list(definitions.values())

    def latest(self) -> list[ModuleDefinition]:
        latest: dict[str, ModuleDefinition] = {}
        for module in self.definitions():
            if module.id not in latest or module.version > latest[module.id].version:
                latest[module.id] = module
        return sorted(latest.values(), key=lambda module: module.id)

    def versions(self, module_id: str) -> list[ModuleVersionInfo]:
        modules = sorted((m for m in self.definitions() if m.id == module_id), key=lambda m: m.version, reverse=True)
        return [ModuleVersionInfo.model_validate(self.release(m).model_dump(include=set(ModuleVersionInfo.model_fields))) for m in modules]

    def get(self, module_id: str, version: int) -> ModuleVersionResponse:
        module = next((m for m in self.definitions() if m.id == module_id and m.version == version), None)
        if module is None:
            raise KeyError("模块版本不存在")
        return self.release(module)

    def release(self, module: ModuleDefinition) -> ModuleVersionResponse:
        if module.package_path is None:
            raise ValueError('模块版本缺少包路径')
        receipt_path = Path(module.package_path) / "release.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
        evidence_directory = Path(module.package_path) / 'evidence'
        evidence = list(receipt.get('validation_evidence', []))
        if evidence_directory.is_dir():
            evidence.extend(json.loads(path.read_text(encoding='utf-8')) for path in sorted(evidence_directory.glob('*.json')))
        receipt['validation_evidence'] = evidence
        return ModuleVersionResponse(module=module, package=package_ref(module), **receipt)

    def add_evidence(self, module_id, version, evidence):
        module = self.get(module_id, version).module
        if (evidence.content_hash, evidence.definition_hash) != (module.content_hash, module.definition_hash):
            raise ValueError('验证证据与模块双哈希不匹配')
        directory = self.root / f'module-{module_id}' / f'v{version}' / 'evidence'
        if not directory.parent.exists():
            raise ValueError('种子模块只读；请先保存本地版本后添加证据')
        payload = evidence.model_dump_json(indent=2) + '\n'
        digest = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        with self.lock:
            directory.mkdir(exist_ok=True)
            target = directory / f'{digest}.json'
            if not target.exists():
                with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.pending',dir=directory,delete=False) as stream:
                    pending=Path(stream.name)
                    stream.write(payload);stream.flush();os.fsync(stream.fileno())
                try:
                    os.rename(pending,target)
                finally:
                    if pending.exists():pending.unlink()
        return self.get(module_id, version)

    def save(self, request: ModuleSaveRequest) -> ModuleVersionResponse:
        from .bench import run_module_test
        from .catalog import catalog_map
        from .module_validation import validate_module_definition
        from .models import Diagnostic

        # Lock covers the test too: only the checked definition can become this version.
        with self.lock:
            current = next((m for m in self.latest() if m.id == request.module.id), None)
            latest_version = current.version if current else 0
            if request.module.id in catalog_map():
                raise ModuleVersionConflict("内置模块 ID 不能用于保存 Python 模块，请新建模块标识")
            if latest_version != request.expected_latest_version:
                raise ModuleVersionConflict(f"模块已有 v{latest_version}，请刷新版本列表后基于最新版本保存；当前草稿已保留")
            module = request.module.model_copy(deep=True, update={
                "version": latest_version + 1, "content_hash": None, "definition_hash": None, "package_path": None})
            validation = validate_module_definition(module)
            if not validation.valid:
                raise ModuleSaveInvalid(validation.diagnostics)
            normalize = lambda text: text.replace("\r\n", "\n").replace("\r", "\n")
            runtime, design = normalize(module_source(module)), normalize(design_source(module))
            module.source = {"runtime": runtime, **({"design": design} if design.strip() else {})}
            module.content_hash = module_content_hash(module)
            module.definition_hash = module_definition_hash(module)
            from .refrigeration.bench import effective_test_conditions
            actual_conditions = effective_test_conditions(module,request.test)
            try:
                test_result = run_module_test(ModuleTestRequest(module=module, **actual_conditions.model_dump()))
            except ValueError as error:
                raise ModuleSaveInvalid(getattr(error,'diagnostics',[]) or
                    [Diagnostic(code=getattr(error, "code", "MODULE_TEST_FAILED"), message=str(error))],replay=getattr(error,'replay',None)) from error
            missing = [v.id for v in module.variables if v.source in {'derived', 'state'} and f'D1.{v.id}' not in test_result.frame.variables]
            if missing:
                raise ModuleSaveInvalid([Diagnostic(code='MODULE_OUTPUT_MISSING', message=f'试算未返回已声明输出：{missing}', field='variables')])
            receipt = {"created_at": datetime.now(timezone.utc).isoformat(), "release_notes": request.release_notes,
                       "tested": True, "test_conditions": actual_conditions.model_dump(mode="json"),
                       "test_result": test_result.model_dump(mode="json")}
            conditions = json.dumps(actual_conditions.model_dump(mode='json'), sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode('utf-8')
            receipt['validation_evidence'] = [{'level':'L3', 'status':'passed', 'source':'engine module bench',
                'content_hash':module.content_hash, 'definition_hash':module.definition_hash,
                'input_hash':hashlib.sha256(conditions).hexdigest(), 'engine_version':'0.5.0',
                'sdk_version':module.sdk.api_version if module.sdk else 'legacy-v1',
                'tolerances':{'pressure_pa':1., 'mass_flow_kg_s':1e-8}}]
            parent = self.root / f"module-{module.id}"
            target = parent / f"v{module.version}"
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".pending-", dir=parent) as pending:
                temporary = Path(pending)
                manifest = contract_model(module).model_dump(mode="json", exclude={"source", "package_path"})
                (temporary / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (temporary / "module.py").write_text(runtime, encoding="utf-8", newline="")
                if design.strip():
                    (temporary / "design.py").write_text(design, encoding="utf-8", newline="")
                (temporary / "release.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                try:
                    os.rename(temporary, target)
                except OSError:
                    if target.exists():
                        raise ModuleVersionConflict("该版本已由其他请求保存，请刷新版本列表；旧版本未覆盖")
                    raise
            return self.get(module.id, module.version)
