param([int]$Port = 8798, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$enginePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $enginePython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw '创建 Python 虚拟环境失败' }
}
$engineReady = & $enginePython -c "import importlib.util; print(all(importlib.util.find_spec(name) for name in ['fn_engine', 'fastapi', 'scipy', 'uvicorn', 'pytest', 'httpx']))"
if ($engineReady -ne 'True') {
    & $enginePython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '安装依赖失败；请重新执行 .venv\Scripts\python -m pip install -r requirements.txt' }
}
$engineArguments = @('-m', 'fn_engine', 'serve', '--port', $Port)
if (-not $NoBrowser) { $engineArguments += '--open' }
& $enginePython @engineArguments
