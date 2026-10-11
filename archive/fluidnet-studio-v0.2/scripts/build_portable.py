"""Build an isolated Windows distribution and zip, all under this workspace."""
import importlib.metadata
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import venv
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".runtime" / "python"))
sys.path.insert(0, str(ROOT))


def main():
    from fluidnet import __version__
    if os.name != "nt" or sys.maxsize <= 2**32:
        raise RuntimeError("The portable build requires 64-bit Windows and Python")
    if not (ROOT / "web" / "dist" / "index.html").is_file():
        raise RuntimeError("Build the frontend first: npm run build")
    build = (ROOT / "build" / "portable").resolve()
    output = (ROOT / "dist" / "portable" / __version__).resolve()
    if (output / "FluidNetStudio" / "workspace").exists():
        output = output.with_name(__version__ + "-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    environment = (ROOT / "build" / "packaging-python").resolve()
    cache = (ROOT / ".cache" / "pyinstaller").resolve()
    for path in (build, output, environment, cache):
        if not path.is_relative_to(ROOT) or path == ROOT:
            raise RuntimeError("Build path escaped workspace")
        path.mkdir(parents=True, exist_ok=True)
    # Hook subprocesses must not discover unrelated packages or editable installs
    # from the developer's global Python environment.
    venv.EnvBuilder(with_pip=False, system_site_packages=False).create(environment)
    build_env = {**os.environ, "PYTHONPATH": os.pathsep.join((str(ROOT / ".runtime" / "python"), str(ROOT))),
                 "PYTHONNOUSERSITE": "1", "PYINSTALLER_CONFIG_DIR": str(cache)}
    command = [str(environment / "Scripts" / "python.exe"), "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--console",
               "--name", "FluidNetStudio", "--distpath", str(output), "--workpath", str(build),
               "--specpath", str(ROOT / "build"), "--paths", str(ROOT),
               "--paths", str(ROOT / ".runtime" / "python"),
               "--add-data", str(ROOT / "web" / "dist") + os.pathsep + "web/dist",
               "--collect-binaries", "CoolProp", "--collect-submodules", "uvicorn",
               "--hidden-import", "websockets.legacy.server", "--hidden-import", "websockets.server"]
    for module in ("pytest", "_pytest", "matplotlib", "pandas", "torch", "tensorflow", "jax", "cupy", "IPython"):
        command += ["--exclude-module", module]
    for package in ("CoolProp", "numpy", "scipy", "fastapi", "pydantic", "uvicorn", "websockets"):
        command += ["--copy-metadata", package]
    command.append(str(ROOT / "scripts" / "portable_entry.py"))
    subprocess.run(command, cwd=ROOT, env=build_env, check=True)
    folder = output / "FluidNetStudio"
    for name in ("README.md", "requirements.lock.txt"):
        if (ROOT / name).exists():
            shutil.copy2(ROOT / name, folder / name)
    if (ROOT / "docs").exists():
        shutil.copytree(ROOT / "docs", folder / "docs", dirs_exist_ok=True)
    from fluidnet.examples import example_projects, example_templates
    from fluidnet.storage import atomic_json
    examples = folder / "examples"
    examples.mkdir(exist_ok=True)
    for project in example_projects():
        atomic_json(examples / f"{project.id}.json", project.model_dump())
    templates = folder / "templates"
    templates.mkdir(exist_ok=True)
    for template in example_templates():
        atomic_json(templates / f"{template['id']}.json", template)
    atomic_json(folder / "build-info.json", {
        "name": "FluidNetStudio", "version": __version__,
        "python": platform.python_version(), "platform": platform.platform(),
        "architecture": platform.machine(),
        "dependencies": {name: importlib.metadata.version(name) for name in
                         ("CoolProp", "numpy", "scipy", "fastapi", "pydantic", "uvicorn", "websockets")},
    })
    archive = shutil.make_archive(str(ROOT / "dist" / f"FluidNetStudio-Windows-x64-{__version__}"), "zip", output, "FluidNetStudio")
    with open(archive, "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    Path(archive + ".sha256").write_text(f"{digest}  {Path(archive).name}\n", encoding="ascii")
    print(f"Portable distribution: {archive}")


if __name__ == "__main__":
    main()
