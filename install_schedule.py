from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import re
import shlex
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
MONITOR = BASE_DIR / "wifi_speed_monitor.py"
CONFIG_FILE = BASE_DIR / "config.json"
WINDOWS_TASK_NAME = "WiFi Speed Monitor"
WINDOWS_FINAL_TASK_NAME = "WiFi Speed Monitor Final"
MACOS_FINAL_LAUNCH_AGENT_LABEL = "wifi-speed-monitor-final"
CRON_MARKER = "# wifi-speed-monitor"
CRON_MARKER_RE = re.compile(r"# wifi-speed-monitor(?:\s|$)")
LEGACY_WINDOWS_TASK_NAMES = [WINDOWS_TASK_NAME, WINDOWS_FINAL_TASK_NAME]
LEGACY_WINDOWS_TASK_NAMES.extend(f"{WINDOWS_TASK_NAME} {index:02d}" for index in range(1, 145))
LEGACY_MACOS_LAUNCH_AGENT_LABELS = [f"wifi-speed-monitor-{index}" for index in range(1, 145)]
LEGACY_MACOS_LAUNCH_AGENT_LABELS.append(MACOS_FINAL_LAUNCH_AGENT_LABEL)


def run(args: list[str], input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def command_output(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or "").strip() or (result.stdout or "").strip()


def command_stdout_lines(result: subprocess.CompletedProcess[str]) -> list[str]:
    return (result.stdout or "").splitlines()


def scheduler_error(result: subprocess.CompletedProcess[str]) -> RuntimeError:
    output = command_output(result)
    if platform.system().lower() == "windows" and is_access_denied(output):
        output = (
            f"{output}\n\n"
            "Windows menolak akses ke Task Scheduler. Jalankan WiFiSpeedMonitor.exe "
            "atau terminal Python dengan klik kanan lalu Run as administrator, "
            "kemudian klik Pasang Jadwal lagi."
        )
    return RuntimeError(output)


def is_access_denied(output: str) -> bool:
    text = output.lower()
    return "access is denied" in text or "access denied" in text or "akses ditolak" in text


def scheduler_python() -> Path:
    if platform.system().lower() == "windows":
        scripts_dir = BASE_DIR / ".venv" / "Scripts"
        for candidate in (scripts_dir / "pythonw.exe", scripts_dir / "python.exe"):
            if candidate.exists():
                return candidate

        current = Path(sys.executable).resolve()
        pythonw = current.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
        return current

    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return Path(sys.executable).resolve()


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def scheduler_command(final: bool = False) -> list[str]:
    if is_frozen_app():
        command = [str(Path(sys.executable).resolve()), "--monitor"]
    else:
        command = [str(scheduler_python()), str(MONITOR)]

    if final:
        command.append("--final")
    return command


def quote_command(args: list[str]) -> str:
    if platform.system().lower() == "windows":
        return subprocess.list2cmdline(args)
    return " ".join(shlex.quote(arg) for arg in args)


def install_windows(times: list[str], final_time: str | None) -> None:
    uninstall_windows()

    for index, time_value in enumerate(times, start=1):
        task_name = WINDOWS_TASK_NAME if len(times) == 1 else f"{WINDOWS_TASK_NAME} {index:02d}"
        command = quote_command(scheduler_command())
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
            raise scheduler_error(result)

    if final_time:
        command = quote_command(scheduler_command(final=True))
        result = run([
            "schtasks",
            "/Create",
            "/SC",
            "DAILY",
            "/TN",
            WINDOWS_FINAL_TASK_NAME,
            "/TR",
            command,
            "/ST",
            final_time,
            "/F",
        ])
        if result.returncode != 0:
            raise scheduler_error(result)


def install_macos(times: list[str], final_time: str | None) -> None:
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    launch_agents.mkdir(parents=True, exist_ok=True)

    uninstall_macos()

    entries = [(f"wifi-speed-monitor-{i}", time_value, False) for i, time_value in enumerate(times, start=1)]
    if final_time:
        entries.append(("wifi-speed-monitor-final", final_time, True))

    for label, time_value, is_final in entries:
        hour, minute = parse_time(time_value)
        plist = launch_agents / f"local.{label}.plist"
        args = scheduler_command(final=is_final)

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
        unload_macos_launch_agent(label, plist)
        result = load_macos_launch_agent(label, plist)
        if result.returncode != 0:
            raise scheduler_error(result)


def install_linux(times: list[str], final_time: str | None) -> None:
    current = run(["crontab", "-l"])
    lines = [] if current.returncode != 0 else command_stdout_lines(current)
    lines = [line for line in lines if not is_linux_v1_cron_line(line)]

    for time_value in times:
        hour, minute = parse_time(time_value)
        lines.append(
            f"{minute} {hour} * * * cd {shlex.quote(str(BASE_DIR))} && "
            f"{quote_command(scheduler_command())} {CRON_MARKER}"
        )

    if final_time:
        hour, minute = parse_time(final_time)
        lines.append(
            f"{minute} {hour} * * * cd {shlex.quote(str(BASE_DIR))} && "
            f"{quote_command(scheduler_command(final=True))} {CRON_MARKER}"
        )

    result = run(["crontab", "-"], input_text="\n".join(lines) + "\n")
    if result.returncode != 0:
        raise scheduler_error(result)


def uninstall_windows() -> None:
    errors = []
    task_names = windows_app_task_names() or LEGACY_WINDOWS_TASK_NAMES
    for task_name in task_names:
        result = run(["schtasks", "/Delete", "/TN", task_name, "/F"])
        output = command_output(result)
        if result.returncode != 0 and output and "cannot find" not in output.lower():
            errors.append(output)
    if errors:
        output = "\n".join(errors)
        if is_access_denied(output):
            raise RuntimeError(
                f"{output}\n\n"
                "Windows menolak akses saat menghapus task lama. Jalankan aplikasi "
                "dengan Run as administrator, lalu klik Pasang Jadwal atau Hapus Jadwal lagi."
            )
        raise RuntimeError(output)


def uninstall_macos() -> None:
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    errors = []
    labels = sorted(set(macos_app_launch_agent_labels() + LEGACY_MACOS_LAUNCH_AGENT_LABELS))
    for label in labels:
        plist = launch_agents / f"local.{label}.plist"
        unload = unload_macos_launch_agent(label, plist)
        output = command_output(unload)
        if unload.returncode != 0 and plist.exists() and output and not is_missing_macos_service(output):
            errors.append(output)
        plist.unlink(missing_ok=True)
    if errors:
        raise RuntimeError("\n".join(errors))


def is_missing_macos_service(output: str) -> bool:
    normalized = output.lower()
    return any(
        text in normalized
        for text in (
            "could not find specified service",
            "no such process",
            "service is not loaded",
            "no such file",
        )
    )


def macos_gui_domain() -> str:
    return f"gui/{os.getuid()}"


def load_macos_launch_agent(label: str, plist: Path) -> subprocess.CompletedProcess[str]:
    result = run(["launchctl", "bootstrap", macos_gui_domain(), str(plist)])
    if result.returncode == 0:
        return result

    fallback = run(["launchctl", "load", str(plist)])
    if fallback.returncode == 0:
        return fallback

    return result


def unload_macos_launch_agent(label: str, plist: Path) -> subprocess.CompletedProcess[str]:
    service_name = f"{macos_gui_domain()}/local.{label}"
    result = run(["launchctl", "bootout", service_name])
    if result.returncode == 0:
        return result

    fallback = run(["launchctl", "unload", str(plist)])
    if fallback.returncode == 0:
        return fallback

    return result


def uninstall_linux() -> None:
    current = run(["crontab", "-l"])
    if current.returncode != 0:
        return

    lines = [line for line in command_stdout_lines(current) if not is_linux_v1_cron_line(line)]
    if lines:
        result = run(["crontab", "-"], input_text="\n".join(lines) + "\n")
    else:
        result = run(["crontab", "-r"])
    if result.returncode != 0:
        raise scheduler_error(result)


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

    verify_installed_schedule(len(times) + (1 if final_time else 0))


def verify_installed_schedule(expected_count: int) -> None:
    status = schedule_status_for_current_os()
    installed_count = int(status["installed_count"])
    loaded_count = int(status["loaded_count"])
    if installed_count < expected_count or loaded_count < expected_count:
        raise RuntimeError(
            "Jadwal belum terverifikasi di scheduler OS. "
            f"Target {expected_count}, ditemukan {installed_count}, aktif {loaded_count}. "
            f"{format_schedule_status(status)}"
        )


def uninstall_for_current_os() -> None:
    system = platform.system().lower()

    if system == "windows":
        uninstall_windows()
    elif system == "darwin":
        uninstall_macos()
    elif system == "linux":
        uninstall_linux()
    else:
        raise RuntimeError(f"OS belum didukung: {platform.system()}")


def schedule_status_for_current_os() -> dict[str, object]:
    system = platform.system().lower()

    if system == "windows":
        return windows_schedule_status()
    if system == "darwin":
        return macos_schedule_status()
    if system == "linux":
        return linux_schedule_status()
    raise RuntimeError(f"OS belum didukung: {platform.system()}")


def windows_schedule_status() -> dict[str, object]:
    installed = windows_app_task_names()
    return {
        "os": "Windows",
        "installed_count": len(installed),
        "installed": installed,
        "loaded_count": len(installed),
        "loaded": installed,
    }


def windows_app_task_names() -> list[str]:
    result = run(["schtasks", "/Query", "/FO", "CSV", "/NH"])
    if result.returncode != 0:
        return []

    task_names = []
    for row in csv.reader(command_stdout_lines(result)):
        if not row:
            continue
        task_name = windows_task_basename(row[0])
        if is_windows_app_task(task_name) and task_name not in task_names:
            task_names.append(task_name)

    return sorted(task_names, key=windows_task_sort_key)


def windows_task_basename(task_path: str) -> str:
    normalized = task_path.strip().replace("\\", "/").rstrip("/")
    return normalized.rsplit("/", 1)[-1]


def is_windows_app_task(task_name: str) -> bool:
    return (
        task_name == WINDOWS_TASK_NAME
        or task_name == WINDOWS_FINAL_TASK_NAME
        or re.fullmatch(rf"{re.escape(WINDOWS_TASK_NAME)} \d+", task_name) is not None
    )


def windows_task_sort_key(task_name: str) -> tuple[int, int, str]:
    if task_name == WINDOWS_TASK_NAME:
        return (0, 0, task_name)
    match = re.fullmatch(rf"{re.escape(WINDOWS_TASK_NAME)} (\d+)", task_name)
    if match:
        return (1, int(match.group(1)), task_name)
    if task_name == WINDOWS_FINAL_TASK_NAME:
        return (2, 0, task_name)
    return (3, 0, task_name)


def macos_schedule_status() -> dict[str, object]:
    installed = [f"local.{label}" for label in macos_app_launch_agent_labels()]

    loaded = []
    for label in installed:
        result = run(["launchctl", "print", f"{macos_gui_domain()}/{label}"])
        if result.returncode == 0:
            loaded.append(label)

    return {
        "os": "macOS",
        "installed_count": len(installed),
        "installed": installed,
        "loaded_count": len(loaded),
        "loaded": loaded,
    }


def macos_app_launch_agent_labels() -> list[str]:
    launch_agents = Path.home() / "Library" / "LaunchAgents"
    labels = []
    for plist in launch_agents.glob("local.wifi-speed-monitor*.plist"):
        label = plist.stem.removeprefix("local.")
        if is_macos_app_launch_agent(label):
            labels.append(label)
    return sorted(set(labels), key=macos_launch_agent_sort_key)


def is_macos_app_launch_agent(label: str) -> bool:
    return (
        label == MACOS_FINAL_LAUNCH_AGENT_LABEL
        or re.fullmatch(r"wifi-speed-monitor-\d+", label) is not None
    )


def macos_launch_agent_sort_key(label: str) -> tuple[int, int, str]:
    match = re.fullmatch(r"wifi-speed-monitor-(\d+)", label)
    if match:
        return (0, int(match.group(1)), label)
    if label == MACOS_FINAL_LAUNCH_AGENT_LABEL:
        return (1, 0, label)
    return (2, 0, label)


def linux_schedule_status() -> dict[str, object]:
    current = run(["crontab", "-l"])
    installed = []
    if current.returncode == 0:
        installed = [line for line in command_stdout_lines(current) if is_linux_v1_cron_line(line)]
    return {
        "os": "Linux",
        "installed_count": len(installed),
        "installed": installed,
        "loaded_count": len(installed),
        "loaded": installed,
    }


def is_linux_v1_cron_line(line: str) -> bool:
    return CRON_MARKER_RE.search(line) is not None


def format_schedule_status(status: dict[str, object]) -> str:
    installed = list(status.get("installed", []))
    loaded = list(status.get("loaded", []))
    preview = ", ".join(str(item) for item in installed[:5])
    if len(installed) > 5:
        preview += f", ... ({len(installed)} total)"
    if not preview:
        preview = "belum ada jadwal"

    os_name = status.get("os", platform.system())
    return (
        f"{os_name}: {status.get('installed_count', 0)} jadwal ditemukan, "
        f"{status.get('loaded_count', 0)} aktif. {preview}. "
        f"Python scheduler: {scheduler_python()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Pasang jadwal Wi-Fi Speed Monitor.")
    parser.add_argument("--times", nargs="*", default=None, help="Jam tes reguler, contoh: 08:30 12:30")
    parser.add_argument("--final-time", default=None, help="Jam final dengan argumen --final, contoh: 21:00")
    parser.add_argument("--from-config", action="store_true", help="Ambil jadwal dari config.json.")
    parser.add_argument("--delete", action="store_true", help="Hapus jadwal Wi-Fi Speed Monitor dari scheduler OS.")
    parser.add_argument("--status", action="store_true", help="Cek jadwal Wi-Fi Speed Monitor di scheduler OS.")
    args = parser.parse_args()

    if args.status:
        print(format_schedule_status(schedule_status_for_current_os()))
        return 0

    if args.delete:
        uninstall_for_current_os()
        print("Jadwal berhasil dihapus.")
        return 0

    if args.from_config or args.times is None:
        times, final_time = load_schedule_from_config()
    else:
        times, final_time = args.times, args.final_time

    install_for_current_os(times, final_time)

    print("Jadwal berhasil dipasang.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
