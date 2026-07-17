# Wi-Fi Speed Monitor

Aplikasi untuk menjalankan speedtest Wi-Fi secara manual atau terjadwal di
Windows, Linux, dan macOS. Hasil tes disimpan sebagai CSV, laporan Excel bulanan,
PDF harian, dan log aplikasi.

Versi baru ini tidak lagi terikat ke nama cafe, SSID, atau password tertentu.
Daftar Wi-Fi bisa diisi lewat GUI atau file `config.json`.

## Fitur

- GUI untuk mengisi nama komputer, SSID, password, label laporan, jadwal tes, dan opsi shutdown.
- CLI untuk dijalankan manual atau lewat scheduler.
- Koneksi Wi-Fi lintas OS:
  - Windows: `netsh`
  - Linux: `nmcli` / NetworkManager
  - macOS: `networksetup`
- Output:
  - `data/speedtest_log.csv`
  - `reports/laporan_wifi_YYYY-MM.xlsx`
  - `reports/laporan_wifi_YYYY-MM-DD.pdf`
  - `logs/monitor.log`

## Instalasi

Gunakan Python 3.11 atau lebih baru.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe wifi_speed_gui.py
```

### Linux / macOS

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python wifi_speed_gui.py
```

Linux membutuhkan NetworkManager CLI:

```bash
nmcli --version
```

GUI membutuhkan Tkinter. Jika `python wifi_speed_gui.py` menampilkan error
`No module named '_tkinter'`, pasang varian Python yang membawa Tkinter.
Contoh di Ubuntu/Debian:

```bash
sudo apt install python3-tk
```

Di macOS, Python dari python.org biasanya sudah menyertakan Tkinter. Beberapa
instalasi Homebrew mungkin perlu paket Tk terpisah atau Python dari python.org.

## Konfigurasi

Cara termudah adalah membuka GUI:

```bash
python wifi_speed_gui.py
```

Isi daftar Wi-Fi, lalu klik `Simpan Config`. File `config.json` akan dibuat.
Password tersimpan sebagai teks biasa, jadi simpan folder ini hanya di komputer
yang berwenang.

Alternatifnya, salin `config.example.json` menjadi `config.json` dan edit isinya.

```json
{
  "computer_name": "Komputer 1",
  "settle_seconds": 20,
  "gap_between_tests_seconds": 20,
  "shutdown_after_final": false,
  "shutdown_delay_seconds": 30,
  "schedule": {
    "enabled": true,
    "start_time": "08:30",
    "end_time": "20:30",
    "frequency_minutes": 60,
    "final_time": "21:00"
  },
  "wifi_profiles": [
    {
      "ssid": "Nama WiFi",
      "password": "password-wifi",
      "label": "Nama WiFi"
    }
  ]
}
```

## Menjalankan Tes

Via GUI, klik `Jalankan Tes`.

Via CLI:

```bash
python wifi_speed_monitor.py
```

Run final:

```bash
python wifi_speed_monitor.py --final
```

Shutdown hanya dijalankan pada `--final` jika `shutdown_after_final` bernilai
`true` dan semua tes serta laporan berhasil.

## Memasang Jadwal

Jadwal bisa diatur lewat GUI pada bagian `Jadwal Tes`:

- `Mulai`: jam tes pertama.
- `Selesai`: batas jam tes reguler terakhir.
- `Setiap menit`: interval tes.
- `Jam final`: run tambahan dengan argumen `--final`.

Klik `Pasang Jadwal` setelah konfigurasi disimpan. Contoh: mulai `08:30`,
selesai `20:30`, setiap `60` menit akan membuat jadwal 08:30, 09:30, 10:30,
dan seterusnya sampai 20:30.

Jika jadwal sudah tidak dibutuhkan, klik `Hapus Jadwal` di GUI. Aplikasi hanya
menghapus jadwal milik Wi-Fi Speed Monitor:

- Windows: task bernama `WiFi Speed Monitor`.
- Linux: baris cron dengan marker `# wifi-speed-monitor`.
- macOS: LaunchAgent `local.wifi-speed-monitor-*.plist`.

Via CLI, `install_schedule.py` otomatis membaca jadwal dari `config.json`:

```bash
python install_schedule.py
```

Atau ambil eksplisit dari config:

```bash
python install_schedule.py --from-config
```

Argumen manual tetap tersedia:

```bash
python install_schedule.py --times 08:00 12:00 18:00 --final-time 21:00
```

Hapus jadwal via CLI:

```bash
python install_schedule.py --delete
```

Catatan izin:

- Windows mungkin perlu Command Prompt/PowerShell Administrator untuk memasang
  task tertentu atau membuat profil Wi-Fi.
- Linux membutuhkan `nmcli`; shutdown biasanya perlu izin sistem.
- macOS mungkin meminta izin jaringan atau akses administrator tergantung
  pengaturan perangkat.

## Struktur File

```text
wifi_speed_monitor.py  # CLI utama dan logika speedtest
wifi_speed_gui.py      # GUI konfigurasi dan tes manual
install_schedule.py    # pemasang jadwal Windows/Linux/macOS
config.example.json    # contoh konfigurasi
legacy/                # versi lama khusus COTCH/Windows
```

## Migrasi Dari Versi Lama

File lama khusus Windows dan config spesifik COTCH dipindahkan ke `legacy/`.
Gunakan GUI atau `config.example.json` untuk membuat konfigurasi baru yang
sesuai dengan lokasi dan perangkat masing-masing.
