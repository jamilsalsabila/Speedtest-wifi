param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("kasir", "administrasi", "it")]
    [string]$Role
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $AppDir "config_$Role.json"

if (-not (Test-Path $ConfigPath)) {
    throw "Config tidak ditemukan: $ConfigPath"
}

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

foreach ($wifi in $config.wifi_profiles) {
    $ssid = [string]$wifi.ssid
    $password = [string]$wifi.password
    $escapedSsid = [System.Security.SecurityElement]::Escape($ssid)
    $escapedPassword = [System.Security.SecurityElement]::Escape($password)

    $profileXml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$escapedSsid</name>
    <SSIDConfig>
        <SSID>
            <name>$escapedSsid</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>$escapedPassword</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"@

    $tempFile = Join-Path $env:TEMP ("wifi_" + [guid]::NewGuid().ToString() + ".xml")
    Set-Content -Path $tempFile -Value $profileXml -Encoding UTF8

    try {
        & netsh wlan add profile filename="$tempFile" user=all | Out-Null
        Write-Host "Profil Wi-Fi tersimpan: $ssid"
    }
    finally {
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
    }
}
