$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

pyinstaller --onefile --windowed --name WiFiSpeedMonitor wifi_speed_gui.py

New-Item -ItemType Directory -Force package | Out-Null
Copy-Item dist\WiFiSpeedMonitor.exe package\
Copy-Item config.example.json package\
Copy-Item README.md package\

Write-Host "EXE selesai: package\WiFiSpeedMonitor.exe"
