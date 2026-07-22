from __future__ import annotations

import json
import platform
import queue
import sys
import threading

if "--monitor" in sys.argv:
    from wifi_speed_monitor import main as monitor_main

    monitor_args = ["wifi_speed_monitor.py"]
    if "--final" in sys.argv:
        monitor_args.append("--final")
    sys.argv = monitor_args
    raise SystemExit(monitor_main())

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any

from install_schedule import (
    format_schedule_status,
    generate_times,
    install_for_current_os,
    schedule_status_for_current_os,
    uninstall_for_current_os,
)
from wifi_speed_monitor import CONFIG_FILE, load_config, run_monitor, setup


class WifiMonitorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Wi-Fi Speed Monitor")
        self.geometry("860x760")
        self.minsize(780, 680)

        self.status_queue: queue.Queue[str] = queue.Queue()
        self.profile_rows: list[dict[str, Any]] = []

        self.computer_name = tk.StringVar(value=platform.node() or "Komputer")
        self.settle_seconds = tk.IntVar(value=20)
        self.gap_seconds = tk.IntVar(value=20)
        self.connection_retries = tk.IntVar(value=2)
        self.restore_connection_after_tests = tk.BooleanVar(value=True)
        self.test_current_connection = tk.BooleanVar(value=False)
        self.current_connection_label = tk.StringVar(value="Ethernet / Koneksi Aktif")
        self.speedtest_backend = tk.StringVar(value="speedtest_cli")
        self.ookla_cli_path = tk.StringVar(value="")
        self.ookla_server_id = tk.StringVar(value="")
        self.shutdown_after_final = tk.BooleanVar(value=False)
        self.shutdown_delay = tk.IntVar(value=30)
        self.schedule_enabled = tk.BooleanVar(value=True)
        self.schedule_start = tk.StringVar(value="08:30")
        self.schedule_end = tk.StringVar(value="20:30")
        self.schedule_frequency = tk.IntVar(value=60)
        self.schedule_final_time = tk.StringVar(value="21:00")
        self.schedule_active_start_date = tk.StringVar(value=date.today().isoformat())
        self.schedule_active_days = tk.IntVar(value=0)
        self.schedule_active_until_date = tk.StringVar(value="")
        self.schedule_preview = tk.StringVar(value="")
        self.email_enabled = tk.BooleanVar(value=False)
        self.email_smtp_host = tk.StringVar(value="")
        self.email_smtp_port = tk.IntVar(value=587)
        self.email_use_tls = tk.BooleanVar(value=True)
        self.email_use_ssl = tk.BooleanVar(value=False)
        self.email_username = tk.StringVar(value="")
        self.email_password = tk.StringVar(value="")
        self.email_from = tk.StringVar(value="")
        self.email_to = tk.StringVar(value="")
        self.email_subject = tk.StringVar(value="Laporan Wi-Fi {date}")
        self.email_attach_excel = tk.BooleanVar(value=True)
        self.email_attach_pdf = tk.BooleanVar(value=True)
        self.email_weekdays = [tk.BooleanVar(value=False) for _ in range(7)]
        self.email_dates = tk.StringVar(value="")

        self._build_ui()
        self._load_existing_config()
        self.after(250, self._poll_status)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)

        config_tab = ttk.Frame(notebook, padding=14)
        run_tab = ttk.Frame(notebook, padding=14)
        email_tab = ttk.Frame(notebook, padding=14)
        help_tab = ttk.Frame(notebook, padding=14)
        notebook.add(config_tab, text="1. Konfigurasi")
        notebook.add(run_tab, text="2. Jadwal & Tes")
        notebook.add(email_tab, text="3. Email")
        notebook.add(help_tab, text="Bantuan")

        intro = ttk.Label(
            config_tab,
            text="Mulai dari sini: isi identitas komputer, atur koneksi, lalu tambahkan daftar Wi-Fi yang akan dites.",
            wraplength=760,
        )
        intro.pack(fill=tk.X, pady=(0, 10))

        settings = ttk.LabelFrame(config_tab, text="Langkah 1 - Identitas dan opsi koneksi")
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Nama komputer").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(settings, textvariable=self.computer_name).grid(row=0, column=1, sticky="ew", padx=10, pady=8)

        ttk.Label(settings, text="Waktu tunggu koneksi").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        self._number_with_unit(settings, self.settle_seconds, "detik", 5, 180).grid(
            row=1, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Label(settings, text="Jeda antar Wi-Fi").grid(row=2, column=0, sticky="w", padx=10, pady=8)
        self._number_with_unit(settings, self.gap_seconds, "detik", 0, 300).grid(
            row=2, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Checkbutton(
            settings,
            text="Shutdown setelah run final berhasil",
            variable=self.shutdown_after_final,
        ).grid(row=5, column=0, sticky="w", padx=10, pady=8)
        self._number_with_unit(settings, self.shutdown_delay, "detik", 30, 3600).grid(
            row=5, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Label(settings, text="Retry koneksi").grid(row=3, column=0, sticky="w", padx=10, pady=8)
        self._number_with_unit(settings, self.connection_retries, "kali", 0, 5).grid(
            row=3, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Checkbutton(
            settings,
            text="Kembalikan koneksi setelah tes",
            variable=self.restore_connection_after_tests,
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=8)

        ttk.Checkbutton(
            settings,
            text="Tes Ethernet / koneksi aktif",
            variable=self.test_current_connection,
        ).grid(row=6, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(settings, textvariable=self.current_connection_label).grid(
            row=6, column=1, sticky="ew", padx=10, pady=8
        )

        ttk.Label(settings, text="Backend speedtest").grid(row=7, column=0, sticky="w", padx=10, pady=8)
        ttk.Combobox(
            settings,
            textvariable=self.speedtest_backend,
            values=("speedtest_cli", "ookla_cli"),
            state="readonly",
            width=18,
        ).grid(row=7, column=1, sticky="w", padx=10, pady=8)

        ttk.Label(settings, text="Ookla CLI path").grid(row=8, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(settings, textvariable=self.ookla_cli_path).grid(row=8, column=1, sticky="ew", padx=10, pady=8)
        ttk.Label(settings, text="Server ID").grid(row=8, column=2, sticky="w", padx=10, pady=8)
        ttk.Entry(settings, textvariable=self.ookla_server_id, width=12).grid(
            row=8, column=3, sticky="w", padx=10, pady=8
        )

        profiles = ttk.LabelFrame(config_tab, text="Langkah 2 - Daftar Wi-Fi")
        profiles.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        header = ttk.Frame(profiles)
        header.pack(fill=tk.X, padx=10, pady=(8, 2))
        for index, text in enumerate(("SSID", "Password", "", "Nama di laporan")):
            ttk.Label(header, text=text).grid(row=0, column=index, sticky="w", padx=4)
        for index in (0, 1, 3):
            header.columnconfigure(index, weight=1)

        self.profile_list = ttk.Frame(profiles)
        self.profile_list.pack(fill=tk.BOTH, expand=True, padx=10)

        config_actions = ttk.Frame(config_tab)
        config_actions.pack(fill=tk.X, pady=(14, 0))
        ttk.Button(config_actions, text="Tambah Wi-Fi", command=self._add_profile).pack(side=tk.LEFT)
        ttk.Button(config_actions, text="Simpan Config", command=self._save_config).pack(side=tk.LEFT, padx=8)

        run_intro = ttk.Label(
            run_tab,
            text="Setelah konfigurasi tersimpan, pilih jalankan tes manual atau pasang jadwal otomatis.",
            wraplength=760,
        )
        run_intro.pack(fill=tk.X, pady=(0, 10))

        schedule = ttk.LabelFrame(run_tab, text="Langkah 3 - Jadwal otomatis")
        schedule.pack(fill=tk.X)
        schedule.columnconfigure(1, weight=1)
        schedule.columnconfigure(3, weight=1)

        ttk.Checkbutton(schedule, text="Aktifkan jadwal", variable=self.schedule_enabled).grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        ttk.Button(schedule, text="Cek Jadwal", command=self._check_schedule).grid(
            row=0, column=1, sticky="e", padx=10, pady=8
        )
        ttk.Button(schedule, text="Pasang Jadwal", command=self._install_schedule).grid(
            row=0, column=2, sticky="e", padx=10, pady=8
        )
        ttk.Button(schedule, text="Hapus Jadwal", command=self._delete_schedule).grid(
            row=0, column=3, sticky="e", padx=10, pady=8
        )

        ttk.Label(schedule, text="Mulai").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_start, width=8).grid(row=1, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(schedule, text="Selesai").grid(row=1, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_end, width=8).grid(row=1, column=3, sticky="w", padx=10, pady=6)

        ttk.Label(schedule, text="Interval").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        self._number_with_unit(schedule, self.schedule_frequency, "menit", 5, 1440, increment=5).grid(
            row=2, column=1, sticky="w", padx=10, pady=6
        )
        ttk.Label(schedule, text="Jam final").grid(row=2, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_final_time, width=8).grid(
            row=2, column=3, sticky="w", padx=10, pady=6
        )

        ttk.Label(schedule, text="Mulai aktif tanggal").grid(row=3, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_active_start_date, width=12).grid(
            row=3, column=1, sticky="w", padx=10, pady=6
        )
        ttk.Label(schedule, text="Aktif selama").grid(row=3, column=2, sticky="w", padx=10, pady=6)
        self._number_with_unit(schedule, self.schedule_active_days, "hari", 0, 3650).grid(
            row=3, column=3, sticky="w", padx=10, pady=6
        )

        ttk.Label(schedule, text="Sampai tanggal").grid(row=4, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_active_until_date, width=12).grid(
            row=4, column=1, sticky="w", padx=10, pady=6
        )
        ttk.Label(schedule, textvariable=self.schedule_preview).grid(
            row=5, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8)
        )

        for variable in (
            self.schedule_start,
            self.schedule_end,
            self.schedule_frequency,
            self.schedule_final_time,
            self.schedule_enabled,
            self.schedule_active_start_date,
            self.schedule_active_days,
            self.schedule_active_until_date,
        ):
            variable.trace_add("write", lambda *_: self._refresh_schedule_preview())

        actions = ttk.LabelFrame(run_tab, text="Langkah 4 - Jalankan tes")
        actions.pack(fill=tk.X, pady=(14, 0))
        ttk.Button(actions, text="Simpan Config", command=self._save_config).pack(side=tk.LEFT, padx=10, pady=10)
        ttk.Button(actions, text="Jalankan Tes Sekarang", command=self._run_test).pack(side=tk.LEFT, padx=(0, 8), pady=10)
        ttk.Button(actions, text="Jalankan Final", command=lambda: self._run_test(final=True)).pack(
            side=tk.LEFT, padx=(0, 8), pady=10
        )

        status_box = ttk.LabelFrame(run_tab, text="Hasil proses")
        status_box.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        self.status = tk.Text(status_box, height=11, state=tk.DISABLED, wrap="word")
        self.status.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_email_tab(email_tab)

        help_text = tk.Text(help_tab, height=20, state=tk.NORMAL, wrap="word")
        help_text.pack(fill=tk.BOTH, expand=True)
        help_text.insert(
            tk.END,
            "Cara pakai cepat:\n\n"
            "1. Buka tab 1. Konfigurasi.\n"
            "2. Isi Nama komputer.\n"
            "3. Isi waktu tunggu koneksi, jeda antar Wi-Fi, dan retry koneksi.\n"
            "   Biarkan Kembalikan koneksi setelah tes aktif jika komputer biasa memakai ethernet atau Wi-Fi lain.\n"
            "4. Aktifkan Tes Ethernet / koneksi aktif jika ingin speedtest koneksi yang sedang dipakai tanpa pindah Wi-Fi.\n"
            "5. Tambahkan SSID Wi-Fi, password, dan nama di laporan jika ingin tes Wi-Fi juga. Nama di laporan akan tampil di kolom Wi-Fi pada Excel/PDF.\n"
            "6. Icon mata menampilkan password, icon mata dicoret menyembunyikan password kembali.\n"
            "7. Klik Simpan Config.\n\n"
            "Tes manual:\n"
            "1. Buka tab 2. Jadwal & Tes.\n"
            "2. Klik Jalankan Tes Sekarang.\n"
            "3. Lihat ringkasan OK/GAGAL di Hasil proses.\n\n"
            "Jadwal otomatis:\n"
            "1. Aktifkan jadwal.\n"
            "2. Isi jam mulai, jam selesai, interval menit, dan jam final jika diperlukan.\n"
            "3. Isi tanggal mulai aktif, durasi hari, atau tanggal sampai aktif jika jadwal hanya sementara.\n"
            "4. Klik Pasang Jadwal.\n"
            "5. Klik Cek Jadwal untuk memastikan scheduler OS sudah aktif.\n\n"
            "Email laporan:\n"
            "1. Buka tab 3. Email.\n"
            "2. Aktifkan kirim email laporan, isi SMTP, email tujuan, dan jadwal hari/tanggal.\n"
            "3. Email dikirim setelah run final dan laporan berhasil dibuat, sebelum shutdown otomatis.\n\n"
            "Shutdown:\n"
            "Komputer hanya akan shutdown setelah run final berhasil jika checkbox Shutdown setelah run final berhasil dicentang.\n\n"
            "Jika SSID tidak ditemukan atau password salah, aplikasi tetap membuat laporan dengan status GAGAL, Tipe Error, dan Keterangan.",
        )
        help_text.configure(state=tk.DISABLED)

    def _build_email_tab(self, email_tab: ttk.Frame) -> None:
        intro = ttk.Label(
            email_tab,
            text="Opsional: kirim laporan setelah run final selesai, sebelum shutdown otomatis dijalankan.",
            wraplength=760,
        )
        intro.pack(fill=tk.X, pady=(0, 10))

        smtp = ttk.LabelFrame(email_tab, text="SMTP")
        smtp.pack(fill=tk.X)
        smtp.columnconfigure(1, weight=1)
        smtp.columnconfigure(3, weight=1)

        ttk.Checkbutton(smtp, text="Aktifkan kirim email laporan", variable=self.email_enabled).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=8
        )
        ttk.Checkbutton(smtp, text="STARTTLS", variable=self.email_use_tls).grid(
            row=0, column=2, sticky="w", padx=10, pady=8
        )
        ttk.Checkbutton(smtp, text="SSL", variable=self.email_use_ssl).grid(
            row=0, column=3, sticky="w", padx=10, pady=8
        )

        ttk.Label(smtp, text="SMTP host").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(smtp, textvariable=self.email_smtp_host).grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        ttk.Label(smtp, text="Port").grid(row=1, column=2, sticky="w", padx=10, pady=6)
        self._number_with_unit(smtp, self.email_smtp_port, "", 1, 65535).grid(
            row=1, column=3, sticky="w", padx=10, pady=6
        )

        ttk.Label(smtp, text="Username").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(smtp, textvariable=self.email_username).grid(row=2, column=1, sticky="ew", padx=10, pady=6)
        ttk.Label(smtp, text="Password").grid(row=2, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(smtp, textvariable=self.email_password, show="*").grid(row=2, column=3, sticky="ew", padx=10, pady=6)

        message = ttk.LabelFrame(email_tab, text="Pesan dan lampiran")
        message.pack(fill=tk.X, pady=(14, 0))
        message.columnconfigure(1, weight=1)

        ttk.Label(message, text="Dari").grid(row=0, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(message, textvariable=self.email_from).grid(row=0, column=1, sticky="ew", padx=10, pady=6)
        ttk.Label(message, text="Tujuan").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(message, textvariable=self.email_to).grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        ttk.Label(message, text="Subject").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(message, textvariable=self.email_subject).grid(row=2, column=1, sticky="ew", padx=10, pady=6)
        ttk.Checkbutton(message, text="Lampirkan Excel harian", variable=self.email_attach_excel).grid(
            row=3, column=0, sticky="w", padx=10, pady=6
        )
        ttk.Checkbutton(message, text="Lampirkan PDF harian", variable=self.email_attach_pdf).grid(
            row=3, column=1, sticky="w", padx=10, pady=6
        )

        timing = ttk.LabelFrame(email_tab, text="Kapan dikirim")
        timing.pack(fill=tk.X, pady=(14, 0))
        ttk.Label(timing, text="Hari final").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        weekday_frame = ttk.Frame(timing)
        weekday_frame.grid(row=0, column=1, sticky="w", padx=10, pady=8)
        for index, name in enumerate(("Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min")):
            ttk.Checkbutton(weekday_frame, text=name, variable=self.email_weekdays[index]).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(timing, text="Tanggal khusus").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(timing, textvariable=self.email_dates).grid(row=1, column=1, sticky="ew", padx=10, pady=6)
        timing.columnconfigure(1, weight=1)
        ttk.Label(
            timing,
            text="Pisahkan dengan koma. Contoh: 2026-07-22, 2026-08-22, 2026-09-22. Jika hari dan tanggal kosong, email dikirim setiap run final.",
            wraplength=740,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 8))

    def _number_with_unit(
        self,
        parent: ttk.Frame,
        variable: tk.IntVar,
        unit: str,
        from_: int,
        to: int,
        increment: int = 1,
    ) -> ttk.Frame:
        frame = ttk.Frame(parent)
        ttk.Spinbox(frame, from_=from_, to=to, increment=increment, textvariable=variable, width=8).pack(side=tk.LEFT)
        ttk.Label(frame, text=unit).pack(side=tk.LEFT, padx=(6, 0))
        return frame

    def _load_existing_config(self) -> None:
        if CONFIG_FILE.exists():
            try:
                config = load_config(CONFIG_FILE)
            except Exception as exc:
                self._log(f"Gagal membaca config lama: {exc}")
                config = {}
        else:
            config = {}

        self.computer_name.set(config.get("computer_name") or self.computer_name.get())
        self.settle_seconds.set(int(config.get("settle_seconds", 20)))
        self.gap_seconds.set(int(config.get("gap_between_tests_seconds", 20)))
        self.connection_retries.set(int(config.get("connection_retries", 2)))
        self.restore_connection_after_tests.set(bool(config.get("restore_connection_after_tests", True)))
        self.test_current_connection.set(bool(config.get("test_current_connection", False)))
        self.current_connection_label.set(str(config.get("current_connection_label") or "Ethernet / Koneksi Aktif"))
        self.speedtest_backend.set(str(config.get("speedtest_backend", "speedtest_cli")))
        self.ookla_cli_path.set(str(config.get("ookla_cli_path", "")))
        self.ookla_server_id.set(str(config.get("ookla_server_id", "")))
        self.shutdown_after_final.set(bool(config.get("shutdown_after_final", False)))
        self.shutdown_delay.set(int(config.get("shutdown_delay_seconds", 30)))
        schedule = config.get("schedule") or {}
        self.schedule_enabled.set(bool(schedule.get("enabled", True)))
        self.schedule_start.set(str(schedule.get("start_time", "08:30")))
        self.schedule_end.set(str(schedule.get("end_time", "20:30")))
        self.schedule_frequency.set(int(schedule.get("frequency_minutes", 60)))
        self.schedule_final_time.set(str(schedule.get("final_time", "21:00")))
        self.schedule_active_start_date.set(str(schedule.get("active_start_date") or date.today().isoformat()))
        self.schedule_active_days.set(int(schedule.get("active_days", 0)))
        self.schedule_active_until_date.set(str(schedule.get("active_until_date", "")))
        email = config.get("email_report") or {}
        self.email_enabled.set(bool(email.get("enabled", False)))
        self.email_smtp_host.set(str(email.get("smtp_host", "")))
        self.email_smtp_port.set(int(email.get("smtp_port", 587)))
        self.email_use_tls.set(bool(email.get("use_tls", True)))
        self.email_use_ssl.set(bool(email.get("use_ssl", False)))
        self.email_username.set(str(email.get("username", "")))
        self.email_password.set(str(email.get("password", "")))
        self.email_from.set(str(email.get("from", "")))
        self.email_to.set(str(email.get("to", "")))
        self.email_subject.set(str(email.get("subject", "Laporan Wi-Fi {date}")))
        self.email_attach_excel.set(bool(email.get("attach_excel", True)))
        self.email_attach_pdf.set(bool(email.get("attach_pdf", True)))
        weekdays = {int(day) for day in email.get("weekdays", []) if str(day).strip() != ""}
        for index, variable in enumerate(self.email_weekdays):
            variable.set(index in weekdays)
        self.email_dates.set(", ".join(str(item) for item in email.get("dates", [])))

        for profile in config.get("wifi_profiles", []):
            self._add_profile(profile)

        if not self.profile_rows:
            self._add_profile()

        self._refresh_schedule_preview()

    def _add_profile(self, data: dict[str, str] | None = None) -> None:
        row_frame = ttk.Frame(self.profile_list)
        row_frame.pack(fill=tk.X, pady=4)

        ssid = tk.StringVar(value=(data or {}).get("ssid", ""))
        password = tk.StringVar(value=(data or {}).get("password", ""))
        label = tk.StringVar(value=(data or {}).get("label", ""))
        password_visible = tk.BooleanVar(value=False)

        ttk.Entry(row_frame, textvariable=ssid).grid(row=0, column=0, sticky="ew", padx=4)
        password_entry = ttk.Entry(row_frame, textvariable=password, show="*")
        password_entry.grid(row=0, column=1, sticky="ew", padx=4)
        self._create_eye_toggle(row_frame, password_entry, password_visible).grid(row=0, column=2, padx=(0, 4))
        ttk.Entry(row_frame, textvariable=label).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(row_frame, text="Hapus", command=lambda: self._remove_profile(row_frame)).grid(
            row=0, column=4, padx=(8, 0)
        )

        for index in (0, 1, 3):
            row_frame.columnconfigure(index, weight=1)

        self.profile_rows.append({"frame": row_frame, "ssid": ssid, "password": password, "label": label})

    def _toggle_password(self, entry: ttk.Entry, visible: tk.BooleanVar) -> None:
        visible.set(not visible.get())
        entry.configure(show="" if visible.get() else "*")

    def _create_eye_toggle(self, parent: ttk.Frame, entry: ttk.Entry, visible: tk.BooleanVar) -> tk.Canvas:
        canvas = tk.Canvas(parent, width=30, height=24, highlightthickness=1, highlightbackground="#B7B7B7")
        canvas.configure(background="white", cursor="hand2")
        self._draw_eye_icon(canvas, visible.get())

        def toggle(_event: tk.Event) -> None:
            self._toggle_password(entry, visible)
            self._draw_eye_icon(canvas, visible.get())

        canvas.bind("<Button-1>", toggle)
        return canvas

    def _draw_eye_icon(self, canvas: tk.Canvas, visible: bool) -> None:
        canvas.delete("all")
        color = "#333333"
        canvas.create_arc(5, 6, 25, 19, start=20, extent=140, style=tk.ARC, outline=color, width=2)
        canvas.create_arc(5, 5, 25, 18, start=200, extent=140, style=tk.ARC, outline=color, width=2)
        canvas.create_oval(12, 9, 18, 15, fill=color, outline=color)
        if visible:
            canvas.create_line(6, 20, 24, 4, fill=color, width=2)

    def _remove_profile(self, frame: ttk.Frame) -> None:
        self.profile_rows = [row for row in self.profile_rows if row["frame"] is not frame]
        frame.destroy()
        if not self.profile_rows:
            self._add_profile()

    def _collect_config(self) -> dict[str, Any]:
        profiles = []
        for row in self.profile_rows:
            ssid = row["ssid"].get().strip()
            if not ssid:
                continue
            label = row["label"].get().strip() or ssid
            profiles.append({
                "ssid": ssid,
                "password": row["password"].get(),
                "label": label,
            })

        if not profiles and not bool(self.test_current_connection.get()):
            raise ValueError("Minimal isi satu SSID Wi-Fi atau aktifkan Tes Ethernet / koneksi aktif.")

        return {
            "computer_name": self.computer_name.get().strip() or platform.node() or "Komputer",
            "settle_seconds": int(self.settle_seconds.get()),
            "gap_between_tests_seconds": int(self.gap_seconds.get()),
            "connection_retries": int(self.connection_retries.get()),
            "restore_connection_after_tests": bool(self.restore_connection_after_tests.get()),
            "test_current_connection": bool(self.test_current_connection.get()),
            "current_connection_label": self.current_connection_label.get().strip() or "Ethernet / Koneksi Aktif",
            "speedtest_backend": self.speedtest_backend.get().strip() or "speedtest_cli",
            "ookla_cli_path": self.ookla_cli_path.get().strip(),
            "ookla_server_id": self.ookla_server_id.get().strip(),
            "shutdown_after_final": bool(self.shutdown_after_final.get()),
            "shutdown_delay_seconds": int(self.shutdown_delay.get()),
            "schedule": self._collect_schedule(),
            "email_report": self._collect_email_report(),
            "wifi_profiles": profiles,
        }

    def _collect_email_report(self) -> dict[str, Any]:
        raw_dates = [item.strip() for item in self.email_dates.get().replace(";", ",").split(",") if item.strip()]
        for value in raw_dates:
            parse_date(value)

        email = {
            "enabled": bool(self.email_enabled.get()),
            "send_after_final": True,
            "smtp_host": self.email_smtp_host.get().strip(),
            "smtp_port": int(self.email_smtp_port.get()),
            "use_tls": bool(self.email_use_tls.get()),
            "use_ssl": bool(self.email_use_ssl.get()),
            "username": self.email_username.get().strip(),
            "password": self.email_password.get(),
            "from": self.email_from.get().strip(),
            "to": self.email_to.get().strip(),
            "subject": self.email_subject.get().strip() or "Laporan Wi-Fi {date}",
            "attach_excel": bool(self.email_attach_excel.get()),
            "attach_pdf": bool(self.email_attach_pdf.get()),
            "weekdays": [index for index, variable in enumerate(self.email_weekdays) if variable.get()],
            "dates": raw_dates,
        }

        if email["enabled"]:
            if not email["smtp_host"]:
                raise ValueError("SMTP host wajib diisi jika kirim email aktif.")
            if not email["from"] and not email["username"]:
                raise ValueError("Email pengirim atau username wajib diisi jika kirim email aktif.")
            if not email["to"]:
                raise ValueError("Email tujuan wajib diisi jika kirim email aktif.")
            if not email["attach_excel"] and not email["attach_pdf"]:
                raise ValueError("Minimal pilih satu lampiran email: Excel atau PDF.")
            if email["use_ssl"] and email["use_tls"]:
                raise ValueError("Pilih salah satu: STARTTLS atau SSL, jangan keduanya.")

        return email

    def _collect_schedule(self) -> dict[str, Any]:
        final_time = self.schedule_final_time.get().strip()
        if final_time:
            generate_times(final_time, final_time, 1)

        active_start_date = self.schedule_active_start_date.get().strip()
        active_days = int(self.schedule_active_days.get())
        active_until_date = self.schedule_active_until_date.get().strip()
        if active_start_date:
            parse_date(active_start_date)
        if active_days < 0:
            raise ValueError("Aktif selama tidak boleh kurang dari 0 hari.")
        if active_until_date:
            parse_date(active_until_date)
        elif active_days > 0:
            start = parse_date(active_start_date or date.today().isoformat())
            active_until_date = (start + timedelta(days=active_days - 1)).isoformat()

        schedule = {
            "enabled": bool(self.schedule_enabled.get()),
            "start_time": self.schedule_start.get().strip(),
            "end_time": self.schedule_end.get().strip(),
            "frequency_minutes": int(self.schedule_frequency.get()),
            "final_time": final_time,
            "active_start_date": active_start_date,
            "active_days": active_days,
            "active_until_date": active_until_date,
        }
        if schedule["active_start_date"] and schedule["active_until_date"]:
            if parse_date(schedule["active_until_date"]) < parse_date(schedule["active_start_date"]):
                raise ValueError("Tanggal sampai aktif tidak boleh lebih awal dari tanggal mulai aktif.")
        if schedule["enabled"]:
            generate_times(
                schedule["start_time"],
                schedule["end_time"],
                int(schedule["frequency_minutes"]),
            )
        return schedule

    def _save_config(self) -> bool:
        try:
            config = self._collect_config()
            CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Config gagal disimpan", str(exc))
            return False

        self._log(f"Config tersimpan: {CONFIG_FILE}")
        return True

    def _refresh_schedule_preview(self) -> None:
        try:
            if not self.schedule_enabled.get():
                self.schedule_preview.set("Jadwal reguler nonaktif.")
                return
            times = generate_times(
                self.schedule_start.get().strip(),
                self.schedule_end.get().strip(),
                int(self.schedule_frequency.get()),
            )
            preview = ", ".join(times[:8])
            if len(times) > 8:
                preview += f", ... ({len(times)} jadwal)"
            else:
                preview += f" ({len(times)} jadwal)"
            final_time = self.schedule_final_time.get().strip()
            if final_time:
                preview += f"; final {final_time}"
            active_text = self._schedule_active_text()
            if active_text:
                preview += f"; {active_text}"
            self.schedule_preview.set(preview)
        except Exception as exc:
            self.schedule_preview.set(f"Jadwal belum valid: {exc}")

    def _schedule_active_text(self) -> str:
        start_text = self.schedule_active_start_date.get().strip()
        days = int(self.schedule_active_days.get())
        until_text = self.schedule_active_until_date.get().strip()
        if until_text:
            return f"aktif sampai {until_text}"
        if days > 0:
            start = parse_date(start_text or date.today().isoformat())
            until = start + timedelta(days=days - 1)
            return f"aktif {days} hari sampai {until.isoformat()}"
        if start_text:
            return f"aktif mulai {start_text}"
        return ""

    def _run_test(self, final: bool = False) -> None:
        if not self._save_config():
            return

        self._set_buttons_state(tk.DISABLED)
        mode = "final" if final else "manual"
        self._log(f"Memulai tes {mode}...")

        thread = threading.Thread(target=self._run_worker, args=(final,), daemon=True)
        thread.start()

    def _install_schedule(self) -> None:
        if not self._save_config():
            return

        self._set_buttons_state(tk.DISABLED)
        self._log("Memasang jadwal...")
        thread = threading.Thread(target=self._install_schedule_worker, daemon=True)
        thread.start()

    def _install_schedule_worker(self) -> None:
        try:
            schedule = self._collect_schedule()
            times = []
            if schedule["enabled"]:
                times = generate_times(
                    schedule["start_time"],
                    schedule["end_time"],
                    int(schedule["frequency_minutes"]),
                )
            final_time = schedule["final_time"] or None
            install_for_current_os(times, final_time)
            status = schedule_status_for_current_os()
            self.status_queue.put(f"Jadwal berhasil dipasang. {format_schedule_status(status)}")
        except Exception as exc:
            self.status_queue.put(f"Gagal memasang jadwal: {exc}")
        finally:
            self.status_queue.put("__DONE__")

    def _check_schedule(self) -> None:
        self._set_buttons_state(tk.DISABLED)
        self._log("Mengecek jadwal...")
        thread = threading.Thread(target=self._check_schedule_worker, daemon=True)
        thread.start()

    def _check_schedule_worker(self) -> None:
        try:
            status = schedule_status_for_current_os()
            self.status_queue.put(format_schedule_status(status))
        except Exception as exc:
            self.status_queue.put(f"Gagal mengecek jadwal: {exc}")
        finally:
            self.status_queue.put("__DONE__")

    def _delete_schedule(self) -> None:
        if not messagebox.askyesno("Hapus Jadwal", "Hapus jadwal Wi-Fi Speed Monitor dari scheduler OS ini?"):
            return

        self._set_buttons_state(tk.DISABLED)
        self._log("Menghapus jadwal...")
        thread = threading.Thread(target=self._delete_schedule_worker, daemon=True)
        thread.start()

    def _delete_schedule_worker(self) -> None:
        try:
            uninstall_for_current_os()
            status = schedule_status_for_current_os()
            self.status_queue.put(f"Jadwal berhasil dihapus. {format_schedule_status(status)}")
        except Exception as exc:
            self.status_queue.put(f"Gagal menghapus jadwal: {exc}")
        finally:
            self.status_queue.put("__DONE__")

    def _run_worker(self, final: bool) -> None:
        try:
            setup()
            config = load_config(CONFIG_FILE)
            code = run_monitor(
                config,
                final=final,
                result_callback=self._queue_test_result,
                enforce_schedule_lifecycle=False,
            )
            if code == 0:
                self.status_queue.put("Tes selesai. Laporan tersimpan di folder reports.")
            else:
                self.status_queue.put("Tes selesai dengan error. Cek logs/monitor.log.")
        except Exception as exc:
            self.status_queue.put(f"Tes gagal: {exc}")
        finally:
            self.status_queue.put("__DONE__")

    def _queue_test_result(self, row: dict[str, Any]) -> None:
        if row.get("status") == "INFO":
            self.status_queue.put(f"{row['wifi']}: {row.get('error') or ''}")
        elif row.get("status") == "OK":
            self.status_queue.put(
                f"{row['wifi']}: OK - Download {row['download_mbps']} Mbps, "
                f"Upload {row['upload_mbps']} Mbps, Ping {row['ping_ms']} ms"
            )
        else:
            self.status_queue.put(
                f"{row['wifi']}: GAGAL [{row.get('error_type') or 'UNKNOWN'}] {row.get('error') or ''}"
            )

    def _poll_status(self) -> None:
        while not self.status_queue.empty():
            message = self.status_queue.get()
            if message == "__DONE__":
                self._set_buttons_state(tk.NORMAL)
            else:
                self._log(message)
        self.after(250, self._poll_status)

    def _set_buttons_state(self, state: str) -> None:
        for child in self.winfo_children():
            self._set_state_recursive(child, state)

    def _set_state_recursive(self, widget: tk.Widget, state: str) -> None:
        if isinstance(widget, ttk.Button):
            widget.configure(state=state)
        for child in widget.winfo_children():
            self._set_state_recursive(child, state)

    def _log(self, message: str) -> None:
        self.status.configure(state=tk.NORMAL)
        self.status.insert(tk.END, message + "\n")
        self.status.see(tk.END)
        self.status.configure(state=tk.DISABLED)


def main() -> None:
    app = WifiMonitorApp()
    app.mainloop()


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Format tanggal harus YYYY-MM-DD: {value}") from exc


if __name__ == "__main__":
    main()
