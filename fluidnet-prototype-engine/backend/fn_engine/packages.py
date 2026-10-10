from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import ModuleDefinition


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
    payload = {**manifest, "source": {"runtime": source}, "runtime": "python",
               "content_hash": digest, "package_path": str(root)}
    return ModuleDefinition.model_validate(payload)


def discover_module_packages(root: str | Path) -> list[ModuleDefinition]:
    base = Path(root)
    if not base.exists():
        return []
    definitions = []
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "manifest.json").exists():
            definitions.append(load_module_package(child))
    return definitions
