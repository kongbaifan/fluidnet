from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

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
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
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
        latest = {}
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
        receipt_path = Path(module.package_path) / "release.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
        return ModuleVersionResponse(module=module, package=package_ref(module), **receipt)

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
            try:
                test_result = run_module_test(ModuleTestRequest(module=module, **request.test.model_dump()))
            except ValueError as error:
                raise ModuleSaveInvalid([Diagnostic(code=getattr(error, "code", "MODULE_TEST_FAILED"), message=str(error))]) from error
            missing = [v.id for v in module.variables if v.source in {'derived', 'state'} and f'D1.{v.id}' not in test_result.frame.variables]
            if missing:
                raise ModuleSaveInvalid([Diagnostic(code='MODULE_OUTPUT_MISSING', message=f'试算未返回已声明输出：{missing}', field='variables')])
            receipt = {"created_at": datetime.now(timezone.utc).isoformat(), "release_notes": request.release_notes,
                       "tested": True, "test_conditions": request.test.model_dump(mode="json"),
                       "test_result": test_result.model_dump(mode="json")}
            parent = self.root / f"module-{module.id}"
            target = parent / f"v{module.version}"
            parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".pending-", dir=parent) as pending:
                temporary = Path(pending)
                manifest = module.model_dump(mode="json", exclude={"source", "package_path"})
                (temporary / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (temporary / "module.py").write_text(module.source["runtime"], encoding="utf-8", newline="")
                if "design" in module.source:
                    (temporary / "design.py").write_text(module.source["design"], encoding="utf-8", newline="")
                (temporary / "release.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                try:
                    os.rename(temporary, target)
                except OSError:
                    if target.exists():
                        raise ModuleVersionConflict("该版本已由其他请求保存，请刷新版本列表；旧版本未覆盖")
                    raise
            return self.get(module.id, module.version)
