param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("kasir", "administrasi", "it")]
    [string]$Role
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $AppDir ".venv\Scripts\python.exe"
$ScriptFile = Join-Path $AppDir "wifi_speed_monitor_windows.py"

if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment belum ada. Jalankan setup.ps1 terlebih dahulu."
}

$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Highest

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 25)

$regularAction = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$ScriptFile`"" `
    -WorkingDirectory $AppDir

$finalAction = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$ScriptFile`" --final" `
    -WorkingDirectory $AppDir

# Hapus task versi sebelumnya bila ada.
Get-ScheduledTask -TaskName "Cotch WiFi Monitor Reguler" -ErrorAction SilentlyContinue |
    Unregister-ScheduledTask -Confirm:$false
Get-ScheduledTask -TaskName "Cotch WiFi Monitor Final dan Shutdown" -ErrorAction SilentlyContinue |
    Unregister-ScheduledTask -Confirm:$false

if ($Role -eq "kasir") {
    # Kasir: 08:30 sampai 20:30, tidak shutdown.
    $triggers = @()
    for ($hour = 8; $hour -le 20; $hour++) {
        $triggers += New-ScheduledTaskTrigger -Daily -At ((Get-Date).Date.AddHours($hour).AddMinutes(30))
    }

    Register-ScheduledTask `
        -TaskName "Cotch WiFi Monitor Reguler" `
        -Action $regularAction `
        -Trigger $triggers `
        -Principal $Principal `
        -Settings $Settings `
        -Force | Out-Null

    Write-Host "Jadwal kasir aktif: 08:30, 09:30, ... 20:30."
    Write-Host "Komputer kasir tidak akan shutdown otomatis."
}
else {
    # Administrasi dan IT: 08:30 sampai 20:30, lalu final 21:00 + shutdown.
    $triggers = @()
    for ($hour = 8; $hour -le 20; $hour++) {
        $triggers += New-ScheduledTaskTrigger -Daily -At ((Get-Date).Date.AddHours($hour).AddMinutes(30))
    }

    $finalTrigger = New-ScheduledTaskTrigger -Daily -At "21:00"

    Register-ScheduledTask `
        -TaskName "Cotch WiFi Monitor Reguler" `
        -Action $regularAction `
        -Trigger $triggers `
        -Principal $Principal `
        -Settings $Settings `
        -Force | Out-Null

    Register-ScheduledTask `
        -TaskName "Cotch WiFi Monitor Final dan Shutdown" `
        -Action $finalAction `
        -Trigger $finalTrigger `
        -Principal $Principal `
        -Settings $Settings `
        -Force | Out-Null

    Write-Host "Jadwal aktif: 08:30, 09:30, ... 20:30."
    Write-Host "Pukul 21:00 tes terakhir, lalu shutdown jika seluruh proses berhasil."
}
