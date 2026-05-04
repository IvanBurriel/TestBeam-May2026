#!/usr/bin/env python3
from pathlib import Path
from influxdb_client import InfluxDBClient, Point, WriteOptions
import re

# ============================================================
# CONFIG
# ============================================================

BASE_DIR = "/work/FCC/TB2026/Data/digi_raw/1776260783"
SAMPLE_PERIOD_NS = 2            # 500 MS/s → 2 ns
BASELINE_SAMPLES = 50           # samples used to compute baseline

# InfluxDB
INFLUX_URL = "http://localhost:8087"
INFLUX_ORG = "TestBeam_org"
INFLUX_BUCKET = "Digitiser_bucket_abs"
INFLUX_TOKEN = "Kr73sktQb-QMH3rCNCPuMdgh8d3HSdb8vseQ6Jp8PukdVNcDkttpWaSG3rZ8JrWn6TMt4K8v3i0nx5OBhtXFSg=="

# ============================================================
# DETECT AVAILABLE WAVE BLOCKS
# ============================================================

def detect_wave_blocks(base_dir):
    blocks = set()
    for f in Path(base_dir).glob("wave*_0_*.txt"):
        m = re.match(r"wave(\d{10})_", f.name)
        if m:
            blocks.add(int(m.group(1)))
    return sorted(blocks)

# ============================================================
# PARSE WAVE FILE WITH BASELINE SUBTRACTION
# ============================================================

def parse_wave_file(path, write_api, run_name, acq_id):

    with open(path, "r") as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):

        if not lines[i].startswith("Record Length"):
            i += 1
            continue

        # ---------- EVENT HEADER ----------
        board = int(lines[i+1].split(":")[1])
        channel = int(lines[i+2].split(":")[1])
        event = int(lines[i+3].split(":")[1])

        ro_sec = int(lines[i+7].split(":")[1])
        ro_ns  = int(lines[i+8].split(":")[1])
        event_time_ns = ro_sec * 1_000_000_000 + ro_ns

        i += 9  # first ADC sample

        # ---------- READ ALL SAMPLES ----------
        adc_values = []

        while i < len(lines) and lines[i].strip().isdigit():
            adc_values.append(int(lines[i].strip()))
            i += 1

        if len(adc_values) < BASELINE_SAMPLES:
            continue

        # ---------- BASELINE ----------
        baseline = sum(adc_values[:BASELINE_SAMPLES]) / BASELINE_SAMPLES

        # ---------- WRITE TO INFLUX ----------
        for sample_idx, adc in enumerate(adc_values):
            ts = event_time_ns + sample_idx * SAMPLE_PERIOD_NS
            adc_corr = adc - baseline

            p = (
                Point("digitiser_samples")
                .tag("run", run_name)
                .tag("acq_id", acq_id)
                .tag("board", board)
                .tag("channel", channel)
                .tag("event", event)
                .field("ADC", adc)
                .field("ADC_corr", adc_corr)
                .field("sample", sample_idx)
                .time(ts)
            )

            write_api.write(
                bucket=INFLUX_BUCKET,
                org=INFLUX_ORG,
                record=p
            )

# ============================================================
# MAIN
# ============================================================

def main():

    base = Path(BASE_DIR)
    acq_id = base.name

    # ---------- SELECT WAVE BLOCK ----------
    wave_blocks = detect_wave_blocks(base)
    if not wave_blocks:
        print("No wave files found.")
        return

    print("\nAvailable wave blocks:")
    for i, w in enumerate(wave_blocks):
        print(f"  [{i}] Events {w} – {w + 999}")

    idx = int(input("\nSelect wave block index: ").strip())
    start_event = wave_blocks[idx]

    # ---------- RUN NAME ----------
    run_name = input("Enter logical run name (e.g. 1, 2, 311): ").strip()

    print(f"\nSelected wave block : {start_event}")
    print(f"Logical run name   : {run_name}")
    print(f"Acquisition ID    : {acq_id}\n")

    # ---------- INFLUX ----------
    influx = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )

    write_api = influx.write_api(
        write_options=WriteOptions(batch_size=5000)
    )

    prefix = f"wave{start_event:010d}"

    for file in base.glob(f"{prefix}_*_*.txt"):
        print(f"Processing {file.name}")
        parse_wave_file(file, write_api, run_name, acq_id)

    write_api.flush()
    influx.close()

    print("\n[DONE]")
    print(f"Run    : {run_name}")
    print(f"Wave   : {start_event}")
    print(f"acq_id : {acq_id}")

# ============================================================
if __name__ == "__main__":
    main()
