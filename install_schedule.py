from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PYTHON = Path(sys.executable).resolve()
MONITOR = BASE_DIR / "wifi_speed_monitor.py"
CONFIG_FILE = BASE_DIR / "config.json"


def run(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=input_text, capture_output=True, text=True, check=False)


def install_windows(times: list[str], final_time: str | None) -> None:
    task_names = ["WiFi Speed Monitor", "WiFi Speed Monitor Final"]
    task_names.extend(f"WiFi Speed Monitor {index:02d}" for index in range(1, 49))
    for task_name in task_names:
        run(["schtasks", "/Delete", "/TN", task_name, "/F"])

    for index, time_value in enumerate(times, start=1):
        task_name = "WiFi Speed Monitor" if len(times) == 1 else f"WiFi Speed Monitor {index:02d}"
        command = f'"{PYTHON}" "{MONITOR}"'
        result = run([
            "schtasks",
            "/Create",
            "/SC",
            "DAILY",
            "/TN",
            task_name,
            "/TR",
            command,
            "/ST",
            time_value,
            "/F",
        ])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    if final_time:
        command = f'"{PYTHON}" "{MONITOR}" --final'
        result = run([
            "schtasks",
            "/Create",
            "/SC",
            "DAILY",
            "/TN",
            "WiFi Speed Monitor Final",
            "/TR",
            command,
            "/ST",
            final_time,
            "/F",
        ])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def install_macos(times: list[str], final_time: str | None) -> None:
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)

    for index in range(1, 49):
        plist = launch_agents / f"local.wifi-speed-monitor-{index}.plist"
        run(["launchctl", "unload", str(plist)])
        plist.unlink(missing_ok=True)
    final_plist = launch_agents / "local.wifi-speed-monitor-final.plist"
    run(["launchctl", "unload", str(final_plist)])
    final_plist.unlink(missing_ok=True)

    entries = [(f"wifi-speed-monitor-{i}", time_value, False) for i, time_value in enumerate(times, start=1)]
    if final_time:
        entries.append(("wifi-speed-monitor-final", final_time, True))

    for label, time_value, is_final in entries:
        hour, minute = parse_time(time_value)
        plist = launch_agents / f"local.{label}.plist"
        args = [str(PYTHON), str(MONITOR)]
        if is_final:
            args.append("--final")

        program_args = "\n".join(f"        <string>{arg}</string>" for arg in args)
        plist.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>local.{label}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>WorkingDirectory</key>
    <string>{BASE_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>{BASE_DIR / "logs" / f"{label}.out.log"}</string>
    <key>StandardErrorPath</key>
    <string>{BASE_DIR / "logs" / f"{label}.err.log"}</string>
</dict>
</plist>
""",
            encoding="utf-8",
        )
        run(["launchctl", "unload", str(plist)])
        result = run(["launchctl", "load", str(plist)])
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def install_linux(times: list[str], final_time: str | None) -> None:
    current = run(["crontab", "-l"])
    lines = [] if current.returncode != 0 else current.stdout.splitlines()
    lines = [line for line in lines if "# wifi-speed-monitor" not in line]

    for time_value in times:
        hour, minute = parse_time(time_value)
        lines.append(
            f"{minute} {hour} * * * cd {shlex.quote(str(BASE_DIR))} && "
            f"{shlex.quote(str(PYTHON))} {shlex.quote(str(MONITOR))} # wifi-speed-monitor"
        )

    if final_time:
        hour, minute = parse_time(final_time)
        lines.append(
            f"{minute} {hour} * * * cd {shlex.quote(str(BASE_DIR))} && "
            f"{shlex.quote(str(PYTHON))} {shlex.quote(str(MONITOR))} --final # wifi-speed-monitor"
        )

    result = run(["crontab", "-"], input_text="\n".join(lines) + "\n")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def parse_time(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"Format jam tidak valid: {value}")
    return hour, minute


def format_time(total_minutes: int) -> str:
    hour, minute = divmod(total_minutes, 60)
    return f"{hour:02d}:{minute:02d}"


def generate_times(start_time: str, end_time: str, frequency_minutes: int) -> list[str]:
    if frequency_minutes <= 0:
        raise ValueError("Interval jadwal harus lebih dari 0 menit.")

    start_hour, start_minute = parse_time(start_time)
    end_hour, end_minute = parse_time(end_time)
    start_total = start_hour * 60 + start_minute
    end_total = end_hour * 60 + end_minute
    if end_total < start_total:
        raise ValueError("Jam selesai tidak boleh lebih awal dari jam mulai.")

    times = []
    current = start_total
    while current <= end_total:
        times.append(format_time(current))
        current += frequency_minutes

    return times


def load_schedule_from_config(config_file: Path = CONFIG_FILE) -> tuple[list[str], str | None]:
    if not config_file.exists():
        return default_regular_times(), None

    with config_file.open(encoding="utf-8") as f:
        config = json.load(f)

    schedule = config.get("schedule") or {}
    times = []
    if schedule.get("enabled", False):
        times = generate_times(
            str(schedule.get("start_time", "08:30")),
            str(schedule.get("end_time", "20:30")),
            int(schedule.get("frequency_minutes", 60)),
        )
    final_time = str(schedule.get("final_time", "")).strip() or None
    if final_time:
        parse_time(final_time)

    return times, final_time


def default_regular_times() -> list[str]:
    return [f"{hour:02d}:30" for hour in range(8, 21)]


def install_for_current_os(times: list[str], final_time: str | None) -> None:
    if not times and not final_time:
        raise ValueError("Tidak ada jadwal yang dipasang. Aktifkan jadwal atau isi jam final.")

    os.chdir(BASE_DIR)
    (BASE_DIR / "logs").mkdir(exist_ok=True)
    system = platform.system().lower()

    if system == "windows":
        install_windows(times, final_time)
    elif system == "darwin":
        install_macos(times, final_time)
    elif system == "linux":
        install_linux(times, final_time)
    else:
        raise RuntimeError(f"OS belum didukung: {platform.system()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pasang jadwal Wi-Fi Speed Monitor.")
    parser.add_argument("--times", nargs="*", default=None, help="Jam tes reguler, contoh: 08:30 12:30")
    parser.add_argument("--final-time", default=None, help="Jam final dengan argumen --final, contoh: 21:00")
    parser.add_argument("--from-config", action="store_true", help="Ambil jadwal dari config.json.")
    args = parser.parse_args()

    if args.from_config or args.times is None:
        times, final_time = load_schedule_from_config()
    else:
        times, final_time = args.times, args.final_time

    install_for_current_os(times, final_time)

    print("Jadwal berhasil dipasang.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
