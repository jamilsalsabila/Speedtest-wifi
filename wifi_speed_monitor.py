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
from openpyxl.chart import Reference, ScatterChart, Series
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

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


def day_name(date_text: str) -> str:
    names = {
        0: "Senin",
        1: "Selasa",
        2: "Rabu",
        3: "Kamis",
        4: "Jumat",
        5: "Sabtu",
        6: "Minggu",
    }
    try:
        return names[datetime.strptime(date_text, "%Y-%m-%d").weekday()]
    except ValueError:
        return "-"


def safe_float(value: str) -> float | None:
    if value in {"", None}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sort_report_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: (r.get("tanggal", ""), r.get("waktu", ""), r.get("wifi", "")))


def write_excel(rows: list[dict[str, str]], month_key: str) -> Path:
    output = REPORT_DIR / f"laporan_wifi_{month_key}.xlsx"
    selected = sort_report_rows([r for r in rows if r["tanggal"].startswith(month_key)])

    wb = Workbook()
    ws = wb.active
    ws.title = "Hasil Speedtest"
    ws.append([
        "Tanggal",
        "Hari",
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
            day_name(row["tanggal"]),
            row["waktu"],
            row["komputer"],
            row["wifi"],
            safe_float(row["download_mbps"]),
            safe_float(row["upload_mbps"]),
            safe_float(row["ping_ms"]),
            row["status"],
            row["error"],
        ])

    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    for cell in ws["J"]:
        cell.alignment = Alignment(vertical="top", wrap_text=True)

    widths = [13, 12, 11, 24, 23, 18, 17, 12, 12, 50]
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    ws["L1"] = "Buka Grafik"
    ws["L1"].hyperlink = "#'Grafik'!A1"
    ws["L1"].font = Font(bold=True, color="FFFFFF")
    ws["L1"].fill = PatternFill("solid", fgColor="4472C4")
    ws["L1"].alignment = Alignment(horizontal="center")
    ws.column_dimensions["L"].width = 16

    write_graph_sheet(wb, selected)
    wb.save(output)
    return output


def write_graph_sheet(wb: Workbook, rows: list[dict[str, str]]) -> None:
    ws = wb.create_sheet("Grafik")
    ws.freeze_panes = "B3"
    ws["A1"] = "Grafik Kecepatan Wi-Fi"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Baris = tanggal/hari, kolom = jam. Nilai memakai rata-rata jika ada beberapa Wi-Fi pada jam yang sama."

    times = sorted({row["waktu"][:5] for row in rows if row.get("waktu")})
    dates = sorted({row["tanggal"] for row in rows if row.get("tanggal")})
    metrics = [
        ("Download (Mbps)", "download_mbps", True),
        ("Upload (Mbps)", "upload_mbps", True),
        ("Ping (ms)", "ping_ms", False),
    ]

    start_row = 4
    for title, key, higher_is_better in metrics:
        start_row = write_metric_matrix(ws, rows, dates, times, title, key, higher_is_better, start_row)
        start_row += 3

    ws.column_dimensions["A"].width = 24
    for column in range(2, len(times) + 2):
        ws.column_dimensions[get_column_letter(column)].width = 11


def write_metric_matrix(
    ws: Any,
    rows: list[dict[str, str]],
    dates: list[str],
    times: list[str],
    title: str,
    metric_key: str,
    higher_is_better: bool,
    start_row: int,
) -> int:
    ws.cell(start_row, 1, title).font = Font(bold=True, size=12)
    header_row = start_row + 1
    ws.cell(header_row, 1, "Tanggal / Hari")
    for column, time_label in enumerate(times, start=2):
        ws.cell(header_row, column, time_label)

    buckets: dict[tuple[str, str], list[float]] = {}
    for row in rows:
        value = safe_float(row.get(metric_key, ""))
        if value is None:
            continue
        key = (row["tanggal"], row["waktu"][:5])
        buckets.setdefault(key, []).append(value)

    for row_index, date_text in enumerate(dates, start=header_row + 1):
        ws.cell(row_index, 1, f"{date_text} ({day_name(date_text)})")
        for column, time_label in enumerate(times, start=2):
            values = buckets.get((date_text, time_label), [])
            if values:
                ws.cell(row_index, column, round(sum(values) / len(values), 2))

    end_row = header_row + len(dates)
    end_column = max(2, len(times) + 1)
    for row in ws.iter_rows(min_row=header_row, max_row=end_row, min_col=1, max_col=end_column):
        for cell in row:
            cell.alignment = Alignment(horizontal="center", vertical="center")
    for cell in ws[header_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")

    if dates and times:
        data_range = f"B{header_row + 1}:{get_column_letter(end_column)}{end_row}"
        start_color, end_color = ("F8696B", "63BE7B")
        if not higher_is_better:
            start_color, end_color = end_color, start_color
        ws.conditional_formatting.add(
            data_range,
            ColorScaleRule(
                start_type="min",
                start_color=start_color,
                mid_type="percentile",
                mid_value=50,
                mid_color="FFEB84",
                end_type="max",
                end_color=end_color,
            ),
        )

        chart_col = end_column + 2
        chart_row_anchor = start_row
        for date_text in dates:
            chart_end_row = write_daily_scatter_chart_data(
                ws,
                buckets,
                times,
                title,
                date_text,
                chart_col,
                chart_row_anchor,
            )
            chart_row_anchor = chart_end_row + 2

    return max(end_row, chart_row_anchor - 2 if dates and times else end_row)


def write_daily_scatter_chart_data(
    ws: Any,
    buckets: dict[tuple[str, str], list[float]],
    times: list[str],
    title: str,
    date_text: str,
    start_col: int,
    start_row: int,
) -> int:
    label = f"{day_name(date_text)}, {date_text}"
    ws.cell(start_row, start_col, label).font = Font(bold=True)
    ws.cell(start_row + 1, start_col, "Jam")
    ws.cell(start_row + 1, start_col + 1, "Index")
    ws.cell(start_row + 1, start_col + 2, title)

    data_row = start_row + 2
    point_index = 1
    for time_label in times:
        values = buckets.get((date_text, time_label), [])
        if not values:
            continue
        ws.cell(data_row, start_col, time_label)
        ws.cell(data_row, start_col + 1, point_index)
        ws.cell(data_row, start_col + 2, round(sum(values) / len(values), 2))
        data_row += 1
        point_index += 1

    if data_row > start_row + 2:
        x_values = Reference(ws, min_col=start_col + 1, min_row=start_row + 2, max_row=data_row - 1)
        y_values = Reference(ws, min_col=start_col + 2, min_row=start_row + 2, max_row=data_row - 1)
        series = Series(y_values, x_values, title=title)
        series.marker.symbol = "circle"
        series.marker.size = 6
        series.graphicalProperties.line.solidFill = "4472C4"

        chart = ScatterChart()
        chart.title = label
        chart.y_axis.title = title
        chart.x_axis.title = "Jam"
        chart.scatterStyle = "lineMarker"
        chart.legend = None
        chart.height = 7
        chart.width = 18
        chart.series.append(series)
        ws.add_chart(chart, f"{get_column_letter(start_col + 4)}{start_row}")

    ws.column_dimensions[get_column_letter(start_col)].width = 11
    ws.column_dimensions[get_column_letter(start_col + 1)].width = 8
    ws.column_dimensions[get_column_letter(start_col + 2)].width = 16
    return max(data_row, start_row + 16)


def write_daily_pdf(rows: list[dict[str, str]], date_key: str) -> Path:
    output = REPORT_DIR / f"laporan_wifi_{date_key}.pdf"
    selected = sort_report_rows([r for r in rows if r["tanggal"] == date_key])

    doc = SimpleDocTemplate(
        str(output),
        pagesize=landscape(A3),
        rightMargin=8 * mm,
        leftMargin=8 * mm,
        topMargin=8 * mm,
        bottomMargin=8 * mm,
    )
    styles = getSampleStyleSheet()
    cell_style = styles["BodyText"]
    cell_style.fontSize = 7
    cell_style.leading = 8
    story = [
        Paragraph(f"Laporan Kecepatan Wi-Fi - {date_key}", styles["Title"]),
        Spacer(1, 5 * mm),
    ]

    table_data = [[
        "Tanggal", "Hari", "Waktu", "Komputer", "Wi-Fi",
        "Download", "Upload", "Ping", "Status", "Keterangan"
    ]]
    for row in selected:
        table_data.append([
            row["tanggal"],
            day_name(row["tanggal"]),
            row["waktu"],
            Paragraph(row["komputer"], cell_style),
            Paragraph(row["wifi"], cell_style),
            f'{row["download_mbps"]} Mbps' if row["download_mbps"] else "-",
            f'{row["upload_mbps"]} Mbps' if row["upload_mbps"] else "-",
            f'{row["ping_ms"]} ms' if row["ping_ms"] else "-",
            row["status"],
            Paragraph(row["error"] or "-", cell_style),
        ])

    table = LongTable(
        table_data,
        repeatRows=1,
        colWidths=[
            25 * mm, 22 * mm, 18 * mm, 42 * mm, 40 * mm,
            29 * mm, 29 * mm, 22 * mm, 18 * mm, 129 * mm,
        ],
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
