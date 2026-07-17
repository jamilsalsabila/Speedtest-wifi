# COTCH Wi-Fi Monitor Windows — Versi 2

## Pembagian komputer

### Komputer kasir

SSID yang diuji:

- `thisiscotch`
- `COTCH`

Jadwal:

- 08:30
- 09:30
- 10:30
- 11:30
- 12:30
- 13:30
- 14:30
- 15:30
- 16:30
- 17:30
- 18:30
- 19:30
- 20:30

Komputer kasir **tidak shutdown otomatis**.

### Komputer administrasi

SSID:

- `bejakantor`

Jadwal reguler 08:30 sampai 20:30. Pengujian terakhir pukul 21:00.
Setelah tes pukul 21:00 dan laporan berhasil disimpan, komputer shutdown otomatis.

### Komputer ruang IT

SSID:

- `bandunghostel`

Jadwal reguler 08:30 sampai 20:30. Pengujian terakhir pukul 21:00.
Setelah tes pukul 21:00 dan laporan berhasil disimpan, komputer shutdown otomatis.

## Password Wi-Fi

Password sudah dimasukkan dalam file config masing-masing komputer dan digunakan
oleh `create_wifi_profiles.ps1` untuk membuat profil Wi-Fi Windows.

Perhatian: file konfigurasi berisi password dalam bentuk teks biasa. Simpan folder
ini hanya pada komputer yang berwenang dan jangan dibagikan kepada karyawan atau
pihak luar.

## Instalasi

Ekstrak folder ke:

`C:\CotchWifiMonitor`

Instal Python 3.11+ dan centang `Add Python to PATH`.

Buka PowerShell sebagai Administrator.

### Kasir

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\CotchWifiMonitor
.\setup.ps1 -Role kasir
```

### Administrasi

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\CotchWifiMonitor
.\setup.ps1 -Role administrasi
```

### Ruang IT

```powershell
Set-ExecutionPolicy -Scope Process Bypass
cd C:\CotchWifiMonitor
.\setup.ps1 -Role it
```

## Tes manual

```powershell
cd C:\CotchWifiMonitor
.\.venv\Scripts\python.exe .\wifi_speed_monitor_windows.py
```

Jangan menambahkan parameter `--final` ketika melakukan tes manual pada komputer
administrasi atau IT karena parameter tersebut dapat memulai shutdown setelah tes.

## Output

- `data\speedtest_log.csv`
- `reports\laporan_wifi_YYYY-MM.xlsx`
- `reports\laporan_wifi_YYYY-MM-DD.pdf`
- `logs\monitor.log`

## Catatan komputer kasir

Karena komputer kasir berpindah dari `thisiscotch` ke `COTCH`, koneksi internet
komputer dapat terputus singkat pada waktu pengujian. Aplikasi kasir sebaiknya
menggunakan kabel LAN atau pengujian dijalankan saat tidak ada transaksi penting.
