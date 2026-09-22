$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    py -m venv (Join-Path $ProjectRoot '.venv')
    & $Python -m pip install -r (Join-Path $ProjectRoot 'requirements.txt')
}
& $Python (Join-Path $ProjectRoot 'app.py')
