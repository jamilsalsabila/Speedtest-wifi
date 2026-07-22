# Wi-Fi Speed Monitor

Aplikasi untuk menjalankan speedtest Wi-Fi secara manual atau terjadwal di
Windows, Linux, dan macOS. Hasil tes disimpan sebagai CSV, laporan Excel bulanan,
PDF harian, dan log aplikasi.

Versi baru ini tidak lagi terikat ke nama cafe, SSID, atau password tertentu.
Daftar Wi-Fi bisa diisi lewat GUI atau file `config.json`.

## Fitur

- GUI untuk mengisi nama komputer, SSID, password, nama di laporan, backend speedtest, tes Ethernet/koneksi aktif, jadwal tes, dan opsi shutdown.
- Tab email opsional untuk mengirim laporan setelah run final pada hari atau tanggal tertentu.
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

Laporan Excel berisi sheet `Hasil Speedtest` dan `Grafik`. Sheet `Grafik`
dibuat otomatis sebagai matriks tanggal/hari pada baris dan jam pada kolom,
dengan heatmap serta grafik garis untuk download, upload, dan ping. Data
Ethernet/koneksi aktif dan tiap Wi-Fi dipisahkan agar tidak dirata-ratakan
bersama pada jam yang sama. PDF harian memakai ukuran A3 landscape supaya tabel
panjang tidak mudah terpotong.

## Instalasi

Gunakan Python 3.11 atau lebih baru.

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe wifi_speed_gui.py
```

### Windows EXE

File `.exe` dibuat otomatis oleh GitHub Actions pada workflow `Build Windows EXE`.
Cara mengambilnya:

1. Buka tab **Actions** di repository GitHub.
2. Pilih workflow **Build Windows EXE** yang terbaru.
3. Download artifact **WiFiSpeedMonitor-Windows**.
4. Extract file zip, lalu jalankan `WiFiSpeedMonitor.exe`.

Jika ingin build lokal di Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows_exe.ps1
```

Hasilnya ada di `package\WiFiSpeedMonitor.exe`.

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

Jika speedtest di macOS gagal dengan error `CERTIFICATE_VERIFY_FAILED`, update
dependency lalu jalankan ulang aplikasi:

```bash
./.venv/bin/python -m pip install -r requirements.txt
```

Aplikasi memakai bundle sertifikat dari `certifi` untuk membantu Python
mengenali sertifikat HTTPS yang dipakai `speedtest-cli`.

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
  "connection_retries": 2,
  "restore_connection_after_tests": true,
  "test_current_connection": false,
  "current_connection_label": "Ethernet / Koneksi Aktif",
  "speedtest_backend": "speedtest_cli",
  "ookla_cli_path": "",
  "ookla_server_id": "",
  "shutdown_after_final": false,
  "shutdown_delay_seconds": 30,
  "schedule": {
    "enabled": true,
    "start_time": "08:30",
    "end_time": "20:30",
    "frequency_minutes": 60,
    "final_time": "21:00",
    "active_start_date": "2026-07-20",
    "active_days": 0,
    "active_until_date": ""
  },
  "email_report": {
    "enabled": false,
    "send_after_final": true,
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "use_tls": true,
    "use_ssl": false,
    "username": "user@example.com",
    "password": "app-password",
    "from": "user@example.com",
    "to": "tujuan@example.com",
    "subject": "Laporan Wi-Fi {date}",
    "attach_excel": true,
    "attach_pdf": true,
    "weekdays": [5],
    "dates": ["2026-07-22", "2026-08-22", "2026-09-22"]
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

Jika SSID tidak ditemukan, password salah, adapter Wi-Fi bermasalah, atau
speedtest gagal karena internet belum tersedia, aplikasi akan tetap menulis
baris laporan dengan `status` = `GAGAL`, `Tipe Error`, dan detail di kolom
`Keterangan`. Koneksi Wi-Fi dicoba ulang sesuai nilai `connection_retries`.

Jika `restore_connection_after_tests` bernilai `true`, aplikasi menyimpan SSID
Wi-Fi awal sebelum tes dan mengembalikannya setelah semua tes selesai. Jika
sebelumnya tidak ada Wi-Fi aktif, Wi-Fi akan diputus setelah tes sehingga
komputer bisa kembali mengandalkan ethernet atau koneksi utama OS.

Jika `test_current_connection` bernilai `true`, aplikasi akan menjalankan satu
speedtest pada koneksi yang sedang aktif tanpa mengganti Wi-Fi. Jika komputer
sedang memakai kabel ethernet, baris laporan ini merepresentasikan koneksi
ethernet. Setelah itu aplikasi tetap bisa melanjutkan tes Wi-Fi dari daftar
SSID jika daftar Wi-Fi diisi.

Field `speedtest_backend` menentukan mesin speedtest yang dipakai:

- `speedtest_cli`: memakai library Python `speedtest-cli`.
- `ookla_cli`: memakai Ookla official CLI eksternal.

Jika memakai `ookla_cli`, isi `ookla_cli_path` dengan path executable Ookla CLI.
Di macOS yang memasang Ookla CLI via Homebrew, field ini boleh dikosongkan jika
command `speedtest` sudah tersedia di `PATH`. Field `ookla_server_id` opsional.
Jika kosong, Ookla CLI memilih server terbaik secara otomatis.

Hasil bisa berbeda antar backend karena pemilihan server, metode pengujian,
adapter jaringan yang aktif, kondisi Wi-Fi/ethernet, firewall/proxy, dan beban
komputer saat tes.

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
Jika checkbox `Shutdown setelah run final berhasil` tidak dicentang di GUI,
komputer tidak akan shutdown.

## Email Laporan

Email laporan bersifat opsional dan diatur dari tab `3. Email`. Jika aktif,
aplikasi akan mengirim laporan setelah run final dan setelah Excel/PDF berhasil
dibuat. Pengiriman dilakukan sebelum shutdown otomatis.

Jadwal kirim bisa dibatasi dengan:

- Hari final, misalnya centang `Sab` untuk setiap Sabtu.
- Tanggal khusus, misalnya `2026-07-22, 2026-08-22, 2026-09-22`.

Jika hari dan tanggal khusus kosong, email dikirim setiap run final. Lampiran
default adalah Excel bulanan dan PDF harian. Gunakan app password SMTP jika
provider email membutuhkannya. Password email tersimpan di `config.json` sebagai
teks biasa, jadi simpan folder aplikasi hanya di komputer yang berwenang.

## Memasang Jadwal

Jadwal bisa diatur lewat GUI pada bagian `Jadwal Tes`:

- `Mulai`: jam tes pertama.
- `Selesai`: batas jam tes reguler terakhir.
- `Interval (menit)`: jarak antar tes otomatis.
- `Jam final`: run tambahan dengan argumen `--final`.
- `Mulai aktif tanggal`: tanggal pertama jadwal boleh menjalankan tes.
- `Aktif selama`: durasi aktif dalam hari. Isi `0` untuk tanpa batas.
- `Sampai tanggal`: tanggal terakhir jadwal aktif. Jika kosong dan `Aktif
  selama` lebih dari `0`, tanggal selesai dihitung otomatis dari tanggal mulai.

Klik `Pasang Jadwal` setelah konfigurasi disimpan. Contoh: mulai `08:30`,
selesai `20:30`, setiap `60` menit akan membuat jadwal 08:30, 09:30, 10:30,
dan seterusnya sampai 20:30.

Jika masa aktif jadwal sudah lewat, run scheduler berikutnya akan menghapus
jadwal Wi-Fi Speed Monitor dari scheduler OS secara otomatis lalu berhenti
tanpa menjalankan speedtest.

Klik `Cek Jadwal` untuk memastikan scheduler OS sudah berisi jadwal aplikasi.
Setelah `Pasang Jadwal`, aplikasi juga melakukan verifikasi otomatis dan
menampilkan jumlah jadwal yang ditemukan.

Scheduler otomatis memakai Python dari `.venv` project jika tersedia. Ini
penting supaya jadwal terpasang memakai dependency yang sama dengan GUI. Jika
sebelumnya jadwal pernah dibuat sebelum `.venv` siap, klik `Pasang Jadwal`
ulang agar path Python di scheduler diperbarui.
Di Windows, scheduler memakai `pythonw.exe` jika tersedia supaya jendela
terminal tidak muncul saat jadwal berjalan.
Jika aplikasi dijalankan dari `WiFiSpeedMonitor.exe`, scheduler Windows akan
menjalankan EXE yang sama dengan argumen `--monitor`, jadi Python tidak perlu
dibuka lewat terminal.
Jika `Pasang Jadwal` menampilkan `Access denied`, jalankan aplikasi dengan
klik kanan **Run as administrator** lalu pasang jadwal ulang. Ini biasanya
terjadi jika task lama dibuat oleh Administrator, user lain, atau dibatasi
policy Windows.

Jika jadwal sudah tidak dibutuhkan, klik `Hapus Jadwal` di GUI. Aplikasi hanya
menghapus jadwal milik Wi-Fi Speed Monitor:

- Windows: task bernama `WiFi Speed Monitor`, `WiFi Speed Monitor NN`, dan
  `WiFi Speed Monitor Final`.
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

Cek status jadwal via CLI:

```bash
python install_schedule.py --status
```

Catatan izin:

- Windows mungkin perlu Command Prompt/PowerShell Administrator untuk memasang
  task tertentu atau membuat profil Wi-Fi.
- Jika profil Wi-Fi Windows sudah dibuat oleh user lain atau Group Policy,
  aplikasi tidak menimpa profil tersebut dan akan memakai profil Windows yang
  sudah ada untuk mencoba koneksi.
- Linux membutuhkan `nmcli`; jika koneksi Wi-Fi tersimpan sudah ada,
  aplikasi akan mencoba memakai koneksi NetworkManager tersebut dan memperbarui
  password dari konfigurasi jika password diisi.
- Shutdown di Linux biasanya perlu izin sistem.
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
