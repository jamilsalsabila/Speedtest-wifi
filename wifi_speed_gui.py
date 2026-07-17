from __future__ import annotations

import json
import platform
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from install_schedule import generate_times, install_for_current_os
from wifi_speed_monitor import CONFIG_FILE, load_config, run_monitor, setup


class WifiMonitorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Wi-Fi Speed Monitor")
        self.geometry("760x720")
        self.minsize(720, 640)

        self.status_queue: queue.Queue[str] = queue.Queue()
        self.profile_rows: list[dict[str, Any]] = []

        self.computer_name = tk.StringVar(value=platform.node() or "Komputer")
        self.settle_seconds = tk.IntVar(value=20)
        self.gap_seconds = tk.IntVar(value=20)
        self.shutdown_after_final = tk.BooleanVar(value=False)
        self.shutdown_delay = tk.IntVar(value=30)
        self.schedule_enabled = tk.BooleanVar(value=True)
        self.schedule_start = tk.StringVar(value="08:30")
        self.schedule_end = tk.StringVar(value="20:30")
        self.schedule_frequency = tk.IntVar(value=60)
        self.schedule_final_time = tk.StringVar(value="21:00")
        self.schedule_preview = tk.StringVar(value="")

        self._build_ui()
        self._load_existing_config()
        self.after(250, self._poll_status)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        settings = ttk.LabelFrame(root, text="Pengaturan")
        settings.pack(fill=tk.X)
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Nama komputer").grid(row=0, column=0, sticky="w", padx=10, pady=8)
        ttk.Entry(settings, textvariable=self.computer_name).grid(row=0, column=1, sticky="ew", padx=10, pady=8)

        ttk.Label(settings, text="Waktu tunggu koneksi").grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ttk.Spinbox(settings, from_=5, to=180, textvariable=self.settle_seconds, width=8).grid(
            row=1, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Label(settings, text="Jeda antar Wi-Fi").grid(row=2, column=0, sticky="w", padx=10, pady=8)
        ttk.Spinbox(settings, from_=0, to=300, textvariable=self.gap_seconds, width=8).grid(
            row=2, column=1, sticky="w", padx=10, pady=8
        )

        ttk.Checkbutton(
            settings,
            text="Shutdown setelah run final berhasil",
            variable=self.shutdown_after_final,
        ).grid(row=3, column=0, sticky="w", padx=10, pady=8)
        ttk.Spinbox(settings, from_=30, to=3600, textvariable=self.shutdown_delay, width=8).grid(
            row=3, column=1, sticky="w", padx=10, pady=8
        )

        schedule = ttk.LabelFrame(root, text="Jadwal Tes")
        schedule.pack(fill=tk.X, pady=(14, 0))
        schedule.columnconfigure(1, weight=1)
        schedule.columnconfigure(3, weight=1)

        ttk.Checkbutton(schedule, text="Aktifkan jadwal", variable=self.schedule_enabled).grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        ttk.Button(schedule, text="Pasang Jadwal", command=self._install_schedule).grid(
            row=0, column=3, sticky="e", padx=10, pady=8
        )

        ttk.Label(schedule, text="Mulai").grid(row=1, column=0, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_start, width=8).grid(row=1, column=1, sticky="w", padx=10, pady=6)
        ttk.Label(schedule, text="Selesai").grid(row=1, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_end, width=8).grid(row=1, column=3, sticky="w", padx=10, pady=6)

        ttk.Label(schedule, text="Setiap menit").grid(row=2, column=0, sticky="w", padx=10, pady=6)
        ttk.Spinbox(schedule, from_=5, to=1440, increment=5, textvariable=self.schedule_frequency, width=8).grid(
            row=2, column=1, sticky="w", padx=10, pady=6
        )
        ttk.Label(schedule, text="Jam final").grid(row=2, column=2, sticky="w", padx=10, pady=6)
        ttk.Entry(schedule, textvariable=self.schedule_final_time, width=8).grid(
            row=2, column=3, sticky="w", padx=10, pady=6
        )
        ttk.Label(schedule, textvariable=self.schedule_preview).grid(
            row=3, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8)
        )

        for variable in (
            self.schedule_start,
            self.schedule_end,
            self.schedule_frequency,
            self.schedule_final_time,
            self.schedule_enabled,
        ):
            variable.trace_add("write", lambda *_: self._refresh_schedule_preview())

        profiles = ttk.LabelFrame(root, text="Daftar Wi-Fi")
        profiles.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        header = ttk.Frame(profiles)
        header.pack(fill=tk.X, padx=10, pady=(8, 2))
        for index, text in enumerate(("SSID", "Password", "Label laporan")):
            ttk.Label(header, text=text).grid(row=0, column=index, sticky="w", padx=4)
            header.columnconfigure(index, weight=1)

        self.profile_list = ttk.Frame(profiles)
        self.profile_list.pack(fill=tk.BOTH, expand=True, padx=10)

        actions = ttk.Frame(root)
        actions.pack(fill=tk.X, pady=(14, 0))
        ttk.Button(actions, text="Tambah Wi-Fi", command=self._add_profile).pack(side=tk.LEFT)
        ttk.Button(actions, text="Simpan Config", command=self._save_config).pack(side=tk.LEFT, padx=8)
        ttk.Button(actions, text="Jalankan Tes", command=self._run_test).pack(side=tk.LEFT)
        ttk.Button(actions, text="Jalankan Final", command=lambda: self._run_test(final=True)).pack(side=tk.LEFT, padx=8)

        self.status = tk.Text(root, height=7, state=tk.DISABLED, wrap="word")
        self.status.pack(fill=tk.X, pady=(14, 0))

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
        self.shutdown_after_final.set(bool(config.get("shutdown_after_final", False)))
        self.shutdown_delay.set(int(config.get("shutdown_delay_seconds", 30)))
        schedule = config.get("schedule") or {}
        self.schedule_enabled.set(bool(schedule.get("enabled", True)))
        self.schedule_start.set(str(schedule.get("start_time", "08:30")))
        self.schedule_end.set(str(schedule.get("end_time", "20:30")))
        self.schedule_frequency.set(int(schedule.get("frequency_minutes", 60)))
        self.schedule_final_time.set(str(schedule.get("final_time", "21:00")))

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

        ttk.Entry(row_frame, textvariable=ssid).grid(row=0, column=0, sticky="ew", padx=4)
        ttk.Entry(row_frame, textvariable=password, show="*").grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Entry(row_frame, textvariable=label).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(row_frame, text="Hapus", command=lambda: self._remove_profile(row_frame)).grid(
            row=0, column=3, padx=(8, 0)
        )

        for index in range(3):
            row_frame.columnconfigure(index, weight=1)

        self.profile_rows.append({"frame": row_frame, "ssid": ssid, "password": password, "label": label})

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

        if not profiles:
            raise ValueError("Minimal isi satu SSID Wi-Fi.")

        return {
            "computer_name": self.computer_name.get().strip() or platform.node() or "Komputer",
            "settle_seconds": int(self.settle_seconds.get()),
            "gap_between_tests_seconds": int(self.gap_seconds.get()),
            "shutdown_after_final": bool(self.shutdown_after_final.get()),
            "shutdown_delay_seconds": int(self.shutdown_delay.get()),
            "schedule": self._collect_schedule(),
            "wifi_profiles": profiles,
        }

    def _collect_schedule(self) -> dict[str, Any]:
        final_time = self.schedule_final_time.get().strip()
        if final_time:
            generate_times(final_time, final_time, 1)

        schedule = {
            "enabled": bool(self.schedule_enabled.get()),
            "start_time": self.schedule_start.get().strip(),
            "end_time": self.schedule_end.get().strip(),
            "frequency_minutes": int(self.schedule_frequency.get()),
            "final_time": final_time,
        }
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
            self.schedule_preview.set(preview)
        except Exception as exc:
            self.schedule_preview.set(f"Jadwal belum valid: {exc}")

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
            self.status_queue.put("Jadwal berhasil dipasang.")
        except Exception as exc:
            self.status_queue.put(f"Gagal memasang jadwal: {exc}")
        finally:
            self.status_queue.put("__DONE__")

    def _run_worker(self, final: bool) -> None:
        try:
            setup()
            config = load_config(CONFIG_FILE)
            code = run_monitor(config, final=final)
            if code == 0:
                self.status_queue.put("Tes selesai. Laporan tersimpan di folder reports.")
            else:
                self.status_queue.put("Tes selesai dengan error. Cek logs/monitor.log.")
        except Exception as exc:
            self.status_queue.put(f"Tes gagal: {exc}")
        finally:
            self.status_queue.put("__DONE__")

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


if __name__ == "__main__":
    main()
