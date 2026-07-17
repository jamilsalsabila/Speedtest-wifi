param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("kasir", "administrasi", "it")]
    [string]$Role
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Assert-Administrator {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Jalankan PowerShell sebagai Administrator."
    }
}

Assert-Administrator

Write-Host "Memeriksa Python..."
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "Python belum terpasang. Instal Python 3.11+ dan centang Add Python to PATH."
}

Write-Host "Membuat virtual environment..."
& python -m venv "$AppDir\.venv"

Write-Host "Memasang library..."
& "$AppDir\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$AppDir\.venv\Scripts\python.exe" -m pip install -r "$AppDir\requirements.txt"

$configSource = Join-Path $AppDir "config_$Role.json"
Copy-Item $configSource (Join-Path $AppDir "config.json") -Force

Write-Host "Membuat profil Wi-Fi Windows..."
& powershell.exe -ExecutionPolicy Bypass -File "$AppDir\create_wifi_profiles.ps1" -Role $Role

Write-Host "Mengaktifkan jadwal..."
& powershell.exe -ExecutionPolicy Bypass -File "$AppDir\install_tasks.ps1" -Role $Role

Write-Host ""
Write-Host "Instalasi selesai untuk role: $Role"
Write-Host "Tes manual:"
Write-Host "  $AppDir\.venv\Scripts\python.exe $AppDir\wifi_speed_monitor_windows.py"
