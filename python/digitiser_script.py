#!/usr/bin/env python3
from pathlib import Path
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import csv
import re

# ============================================================
# CONFIG
# ============================================================

BASE_ROOT = "/eos/experiment/newtile/beamtests/26_05_t10/digi_raw"
OUT_DIR = "digitiser_csv"
FALLBACK_OUT_DIR = "digitiser_csv"

SAMPLE_PERIOD_NS = 2          # 500 MS/s → 2 ns
BASELINE_SAMPLES = 50

# ---- Downsampling for plotting ----
MAX_PLOT_POINTS = 2000
ENABLE_WAVE_PLOTTING = True

# ---- InfluxDB ----
INFLUX_URL = "http://localhost:8086"
INFLUX_ORG = "TestBeam_org"
INFLUX_BUCKET = "Digitiser_bucket"
INFLUX_TOKEN = "JevdaRydlGQv_xshNvghA45XoivlKYpfnmCUU43BkAKSRh8wQPT_nUbxwt3xEstUbJDOzK4SNd9Lz3GcdCV-1w=="

# ---- Board ----
FIXED_BOARD_ID = 31

# ============================================================
# HELPERS
# ============================================================

def compute_decimation(n_samples, max_points):
    if n_samples <= max_points:
        return 1
    return max(1, n_samples // max_points)


def detect_event_folders(root_dir):
    folders = []
    for p in Path(root_dir).iterdir():
        if p.is_dir() and p.name.isdigit():
            folders.append((int(p.name), p))
    return [path for _, path in sorted(folders)]


def detect_wave_blocks(base_dir):
    blocks = set()
    for f in Path(base_dir).glob("wave*_*.txt"):
        m = re.match(r"wave(\d{10})_", f.name)
        if m:
            blocks.add(int(m.group(1)))
    return sorted(blocks)


def parse_channel_from_filename(path):
    m = re.match(r"wave\d{10}_\d+_(\d+)\.txt$", path.name)
    return int(m.group(1)) if m else None


def parse_filename_metadata(path):
    """
    Parse: wave<EVTID>_<BOARD>_<CHANNEL>.txt
    Force board = FIXED_BOARD_ID for Grafana
    """
    m = re.match(r"wave(\d{10})_(\d+)_(\d+)\.txt$", path.name)
    if not m:
        return None, None, None

    channel = int(m.group(3))
    board = FIXED_BOARD_ID
    return board, channel


def get_output_dir():
    try:
        out = Path(OUT_DIR)
        out.mkdir(parents=True, exist_ok=True)
        return out
    except PermissionError:
        fallback = Path.cwd() / FALLBACK_OUT_DIR
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

# ============================================================
# PARSE + DOWNSAMPLE MULTI-EVENT WAVEFORM FILE
# ============================================================

def parse_wave_file(path, write_api, acq_id, csv_dir=None):

    # ---------- filename metadata ----------
    board, channel = parse_filename_metadata(path)
    if board is None:
        print(f"WARNING: Cannot parse filename {path.name}")
        return False

    with open(path) as f:
        lines = f.readlines()

    writer = None
    csv_file = None
    if csv_dir:
        csv_path = csv_dir / f"digitiser_{acq_id}_{path.stem}.csv"
        csv_file = open(csv_path, "w", newline="")
        writer = csv.writer(csv_file)
        writer.writerow([
            "acq_id",
            "board",
            "channel",
            "event",
            "sample",
            "time_ns",
            "ADC",
            "ADC_corr"
        ])

    i = 0
    n_lines = len(lines)

    while i < n_lines:

        line = lines[i].strip()

        # ---------- EVENT HEADER ----------
        if line.startswith("Record Length"):
            record_length = int(line.split(":")[1].strip())

            event_number = None
            i += 1

            # parse header fields
            while i < n_lines:
                header = lines[i].strip()

                if header.startswith("Event Number"):
                    event_number = int(header.split(":")[1].strip())

                # header ends when ADC data begins
                if header.isdigit():
                    break

                i += 1

            if event_number is None:
                print(f"WARNING: Event number not found in {path.name}")
                continue

            # ---------- READ ADC SAMPLES ----------
            adc_values = []
            for _ in range(record_length):
                if i >= n_lines:
                    break
                adc_values.append(int(lines[i].strip()))
                i += 1

            if len(adc_values) < BASELINE_SAMPLES:
                continue

            # ---------- PROCESS EVENT ----------
            baseline = sum(adc_values[:BASELINE_SAMPLES]) / BASELINE_SAMPLES
            decimation = compute_decimation(len(adc_values), MAX_PLOT_POINTS)

            for sample_idx in range(0, len(adc_values), decimation):
                adc = adc_values[sample_idx]
                adc_corr = adc - baseline
                ts = sample_idx * SAMPLE_PERIOD_NS

                if ENABLE_WAVE_PLOTTING:
                    p = (
                        Point("digitiser_waveform")
                        .tag("acq_id", acq_id)
                        .tag("board", str(board))
                        .tag("channel", str(channel))
                        .tag("event", str(event_number))
                        .field("ADC", adc)
                        .field("ADC_corr", adc_corr)
                        .field("sample_idx", sample_idx)
                        .time(ts)
                    )
                    write_api.write(
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        record=p
                    )

                if writer:
                    writer.writerow([
                        acq_id,
                        board,
                        channel,
                        event_number,
                        sample_idx,
                        ts,
                        adc,
                        adc_corr
                    ])

        else:
            i += 1

    if csv_file:
        csv_file.close()

    return True

# ============================================================
# MAIN
# ============================================================

def main():

    root = Path(BASE_ROOT)
    event_folders = detect_event_folders(root)

    for i, f in enumerate(event_folders):
        print(f"[{i}] {f.name}")

    idx = int(input("Select event folder: "))
    base = event_folders[idx]
    acq_id = base.name

    wave_blocks = detect_wave_blocks(base)
    for i, w in enumerate(wave_blocks):
        print(f"[{i}] wave{w:010d}")

    choice = input("Select wave block (or 'a'): ").strip().lower()
    blocks = wave_blocks if choice == "a" else [wave_blocks[int(choice)]]

    ch = input("Select channel (0-7 or 'all'): ").strip().lower()
    selected_channel = None if ch == "all" else int(ch)

    csv_dir = get_output_dir()

    influx = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )
    write_api = influx.write_api(write_options=SYNCHRONOUS)

    for block in blocks:
        prefix = f"wave{block:010d}"
        for file in sorted(base.glob(f"{prefix}_*_*.txt")):
            file_ch = parse_channel_from_filename(file)
            if selected_channel is not None and file_ch != selected_channel:
                continue

            print("Processing", file.name)
            parse_wave_file(file, write_api, acq_id, csv_dir)

    write_api.close()
    influx.close()

    print("[DONE]")

# ============================================================
if __name__ == "__main__":
    main()
