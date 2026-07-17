from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
LOG_DIR = BASE_DIR / "logs"
CSV_FILE = DATA_DIR / "speedtest_log.csv"

HEADERS = [
    "tanggal",
    "waktu",
    "komputer",
    "wifi",
    "download_mbps",
    "upload_mbps",
    "ping_ms",
    "status",
    "error",
]


@dataclass(frozen=True)
class WifiProfile:
    ssid: str
    password: str = ""
    label: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WifiProfile":
        ssid = str(data.get("ssid", "")).strip()
        if not ssid:
            raise ValueError("Setiap Wi-Fi harus memiliki ssid.")
        return cls(
            ssid=ssid,
            password=str(data.get("password", "")),
            label=str(data.get("label") or ssid),
        )


def setup() -> None:
    for folder in (DATA_DIR, REPORT_DIR, LOG_DIR):
        folder.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=LOG_DIR / "monitor.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )

    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="", encoding="utf-8-sig") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writeheader()


def run(
    args: list[str],
    timeout: int = 240,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def load_config(config_file: Path = CONFIG_FILE) -> dict[str, Any]:
    if not config_file.exists():
        raise FileNotFoundError(
            f"{config_file.name} belum dibuat. Jalankan GUI atau salin config.example.json."
        )

    with config_file.open(encoding="utf-8") as f:
        config = json.load(f)

    profiles = config.get("wifi_profiles") or []
    config["wifi_profiles"] = [profile.__dict__ for profile in map(WifiProfile.from_dict, profiles)]
    if not config["wifi_profiles"]:
        raise ValueError("wifi_profiles di config.json masih kosong.")

    return config


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def connect_wifi(profile: WifiProfile, settle_seconds: int) -> None:
    system = platform.system().lower()
    logging.info("Menghubungkan ke SSID %s di %s", profile.ssid, system)

    if system == "windows":
        connect_wifi_windows(profile)
    elif system == "darwin":
        connect_wifi_macos(profile)
    elif system == "linux":
        connect_wifi_linux(profile)
    else:
        raise RuntimeError(f"OS belum didukung: {platform.system()}")

    time.sleep(settle_seconds)
    if not is_connected_to(profile.ssid):
        raise RuntimeError(f"Komputer belum tersambung ke {profile.ssid}.")


def connect_wifi_windows(profile: WifiProfile) -> None:
    if profile.password:
        add_windows_profile(profile)

    result = run(["netsh", "wlan", "connect", f"name={profile.ssid}", f"ssid={profile.ssid}"], timeout=45)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def add_windows_profile(profile: WifiProfile) -> None:
    import tempfile
    import xml.sax.saxutils as xml_utils

    ssid = xml_utils.escape(profile.ssid)
    password = xml_utils.escape(profile.password)
    profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig><SSID><name>{ssid}</name></SSID></SSIDConfig>
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
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"""
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as temp:
        temp.write(profile_xml)
        temp_path = temp.name

    try:
        result = run(["netsh", "wlan", "add", "profile", f"filename={temp_path}", "user=current"], timeout=45)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    finally:
        Path(temp_path).unlink(missing_ok=True)


def connect_wifi_macos(profile: WifiProfile) -> None:
    device = get_macos_wifi_device()
    args = ["networksetup", "-setairportnetwork", device, profile.ssid]
    if profile.password:
        args.append(profile.password)

    result = run(args, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def get_macos_wifi_device() -> str:
    result = run(["networksetup", "-listallhardwareports"], timeout=30)
    lines = result.stdout.splitlines()
    for index, line in enumerate(lines):
        if "Hardware Port: Wi-Fi" in line or "Hardware Port: AirPort" in line:
            for detail in lines[index + 1 : index + 4]:
                if detail.strip().startswith("Device:"):
                    return detail.split(":", 1)[1].strip()
    raise RuntimeError("Tidak dapat menemukan perangkat Wi-Fi macOS.")


def connect_wifi_linux(profile: WifiProfile) -> None:
    if not command_exists("nmcli"):
        raise RuntimeError("Linux membutuhkan NetworkManager CLI (`nmcli`) untuk koneksi Wi-Fi.")

    args = ["nmcli", "device", "wifi", "connect", profile.ssid]
    if profile.password:
        args.extend(["password", profile.password])

    result = run(args, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def is_connected_to(ssid: str) -> bool:
    system = platform.system().lower()

    if system == "windows":
        result = run(["netsh", "wlan", "show", "interfaces"], timeout=30)
        return result.returncode == 0 and ssid.lower() in result.stdout.lower()

    if system == "darwin":
        device = get_macos_wifi_device()
        result = run(["networksetup", "-getairportnetwork", device], timeout=30)
        return result.returncode == 0 and ssid.lower() in result.stdout.lower()

    if system == "linux":
        result = run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], timeout=30)
        return result.returncode == 0 and f"yes:{ssid}".lower() in result.stdout.lower()

    return False


def perform_speedtest() -> dict[str, float]:
    result = run(
        [sys.executable, "-m", "speedtest", "--json", "--secure"],
        timeout=240,
        env=speedtest_env(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    data = json.loads(result.stdout)
    return {
        "download_mbps": round(float(data["download"]) / 1_000_000, 2),
        "upload_mbps": round(float(data["upload"]) / 1_000_000, 2),
        "ping_ms": round(float(data.get("ping", 0)), 2),
    }


def speedtest_env() -> dict[str, str]:
    env = os.environ.copy()
    try:
        import certifi
    except ImportError:
        return env

    ca_bundle = certifi.where()
    env.setdefault("SSL_CERT_FILE", ca_bundle)
    env.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
    return env


def append_csv(row: dict[str, Any]) -> None:
    with CSV_FILE.open("a", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=HEADERS).writerow(row)


def read_rows() -> list[dict[str, str]]:
    with CSV_FILE.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write_excel(rows: list[dict[str, str]], month_key: str) -> Path:
    output = REPORT_DIR / f"laporan_wifi_{month_key}.xlsx"
    selected = [r for r in rows if r["tanggal"].startswith(month_key)]

    wb = Workbook()
    ws = wb.active
    ws.title = "Hasil Speedtest"
    ws.append([
        "Tanggal",
        "Waktu",
        "Komputer",
        "Wi-Fi",
        "Download (Mbps)",
        "Upload (Mbps)",
        "Ping (ms)",
        "Status",
        "Keterangan",
    ])

    for row in selected:
        ws.append([
            row["tanggal"],
            row["waktu"],
            row["komputer"],
            row["wifi"],
            float(row["download_mbps"]) if row["download_mbps"] else None,
            float(row["upload_mbps"]) if row["upload_mbps"] else None,
            float(row["ping_ms"]) if row["ping_ms"] else None,
            row["status"],
            row["error"],
        ])

    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")

    widths = [13, 11, 24, 23, 18, 17, 12, 12, 50]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + index)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(output)
    return output


def write_daily_pdf(rows: list[dict[str, str]], date_key: str) -> Path:
    output = REPORT_DIR / f"laporan_wifi_{date_key}.pdf"
    selected = [r for r in rows if r["tanggal"] == date_key]

    doc = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A4),
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"Laporan Kecepatan Wi-Fi - {date_key}", styles["Title"]),
        Spacer(1, 5 * mm),
    ]

    table_data = [["Tanggal", "Waktu", "Komputer", "Wi-Fi", "Download", "Upload", "Ping", "Status"]]
    for row in selected:
        table_data.append([
            row["tanggal"],
            row["waktu"],
            row["komputer"],
            row["wifi"],
            f'{row["download_mbps"]} Mbps' if row["download_mbps"] else "-",
            f'{row["upload_mbps"]} Mbps' if row["upload_mbps"] else "-",
            f'{row["ping_ms"]} ms' if row["ping_ms"] else "-",
            row["status"],
        ])

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=[25 * mm, 20 * mm, 42 * mm, 40 * mm, 31 * mm, 29 * mm, 23 * mm, 22 * mm],
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
    ]))
    story.append(table)
    doc.build(story)
    return output


def shutdown_computer(delay_seconds: int = 30) -> None:
    system = platform.system().lower()
    logging.info("Memulai shutdown otomatis untuk %s.", system)

    if system == "windows":
        subprocess.Popen([
            "shutdown",
            "/s",
            "/t",
            str(delay_seconds),
            "/c",
            "Pengujian Wi-Fi selesai dan laporan berhasil disimpan.",
        ], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif system in {"darwin", "linux"}:
        subprocess.Popen(["shutdown", "-h", f"+{max(1, delay_seconds // 60)}"])
    else:
        raise RuntimeError(f"Shutdown belum didukung untuk OS: {platform.system()}")


def run_monitor(config: dict[str, Any], final: bool = False) -> int:
    computer_name = config.get("computer_name") or platform.node() or "Komputer"
    settle_seconds = int(config.get("settle_seconds", 20))
    gap_seconds = int(config.get("gap_between_tests_seconds", 20))
    all_tests_ok = True

    for index, item in enumerate(config["wifi_profiles"]):
        profile = WifiProfile.from_dict(item)
        now = datetime.now()
        row: dict[str, Any] = {
            "tanggal": now.strftime("%Y-%m-%d"),
            "waktu": now.strftime("%H:%M:%S"),
            "komputer": computer_name,
            "wifi": profile.label or profile.ssid,
            "download_mbps": "",
            "upload_mbps": "",
            "ping_ms": "",
            "status": "GAGAL",
            "error": "",
        }

        try:
            connect_wifi(profile, settle_seconds)
            result = perform_speedtest()
            row.update(result)
            row["status"] = "OK"
            logging.info(
                "%s / %s: download=%s upload=%s",
                computer_name,
                profile.label,
                row["download_mbps"],
                row["upload_mbps"],
            )
        except Exception as exc:
            all_tests_ok = False
            row["error"] = str(exc)
            logging.exception("Pengujian gagal untuk %s", profile.label)

        append_csv(row)

        if index < len(config["wifi_profiles"]) - 1:
            time.sleep(gap_seconds)

    reports_ok = False
    try:
        rows = read_rows()
        now = datetime.now()
        write_excel(rows, now.strftime("%Y-%m"))
        write_daily_pdf(rows, now.strftime("%Y-%m-%d"))
        reports_ok = True
    except Exception:
        logging.exception("Gagal membuat laporan Excel/PDF.")

    if final and bool(config.get("shutdown_after_final", False)):
        if all_tests_ok and reports_ok:
            shutdown_computer(int(config.get("shutdown_delay_seconds", 30)))
        else:
            logging.error("Shutdown dibatalkan karena tes atau penyimpanan laporan gagal.")

    return 0 if all_tests_ok and reports_ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor speedtest Wi-Fi lintas OS.")
    parser.add_argument("--config", default=str(CONFIG_FILE), help="Lokasi file konfigurasi JSON.")
    parser.add_argument("--final", action="store_true", help="Run final; shutdown jika diaktifkan di config.")
    args = parser.parse_args()

    setup()
    config = load_config(Path(args.config))
    return run_monitor(config, final=args.final)


if __name__ == "__main__":
    raise SystemExit(main())
