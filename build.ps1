[CmdletBinding()]
param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) {
    py -m venv .venv
}

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt

if ($Clean) {
    $BuildDir = Join-Path $ProjectRoot 'build'
    $ReleaseDir = Join-Path $ProjectRoot 'release'
    if ((Test-Path -LiteralPath $BuildDir) -and $BuildDir.StartsWith($ProjectRoot)) { Remove-Item -LiteralPath $BuildDir -Recurse -Force }
    if ((Test-Path -LiteralPath $ReleaseDir) -and $ReleaseDir.StartsWith($ProjectRoot)) { Remove-Item -LiteralPath $ReleaseDir -Recurse -Force }
}

$IconPath = Join-Path $ProjectRoot 'assets\app.ico'
if (-not (Test-Path -LiteralPath $IconPath)) {
    Add-Type -AssemblyName System.Drawing
    $bitmap = New-Object System.Drawing.Bitmap 256, 256
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.Clear([System.Drawing.Color]::FromArgb(17, 19, 24))
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(109, 120, 247))
    $graphics.FillEllipse($brush, 42, 35, 172, 172)
    $white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(244, 245, 248))
    $graphics.FillEllipse($white, 102, 95, 52, 52)
    $graphics.FillPolygon($white, [System.Drawing.Point[]]@((New-Object System.Drawing.Point 128,55),(New-Object System.Drawing.Point 146,81),(New-Object System.Drawing.Point 110,81)))
    $graphics.FillPolygon($white, [System.Drawing.Point[]]@((New-Object System.Drawing.Point 187,121),(New-Object System.Drawing.Point 161,103),(New-Object System.Drawing.Point 161,139)))
    $graphics.FillPolygon($white, [System.Drawing.Point[]]@((New-Object System.Drawing.Point 128,187),(New-Object System.Drawing.Point 110,161),(New-Object System.Drawing.Point 146,161)))
    $graphics.FillPolygon($white, [System.Drawing.Point[]]@((New-Object System.Drawing.Point 69,121),(New-Object System.Drawing.Point 95,103),(New-Object System.Drawing.Point 95,139)))
    $icon = [System.Drawing.Icon]::FromHandle($bitmap.GetHicon())
    $stream = [System.IO.File]::Create($IconPath)
    $icon.Save($stream)
    $stream.Close()
    $graphics.Dispose(); $bitmap.Dispose(); $brush.Dispose(); $white.Dispose(); $icon.Dispose()
}

$AssetData = "$ProjectRoot\assets\icon.svg;assets"
$VersionInfo = Join-Path $ProjectRoot 'version_info.txt'
$OriginalPath = $env:PATH
$env:PATH = "$ProjectRoot\.venv\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
try {
    & $Python -m PyInstaller `
        --clean `
        --noconfirm `
        --onefile `
        --windowed `
        --name ChromecastRemote `
        --icon $IconPath `
        --version-file $VersionInfo `
        --add-data $AssetData `
        --exclude-module PySide6.QtNetwork `
        --exclude-module PySide6.QtNetworkAuth `
        --distpath release `
        --workpath build/pyinstaller `
        --specpath build `
        app.py
} finally {
    $env:PATH = $OriginalPath
}

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

Write-Host "Build complete: $ProjectRoot\release\ChromecastRemote.exe" -ForegroundColor Green
