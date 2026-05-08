#!/usr/bin/env python3

import struct
import csv
import re
from pathlib import Path
from influxdb_client import InfluxDBClient, Point, WritePrecision

# ============================================================
# HELPERS
# ============================================================

def ask_run_number():
    while True:
        try:
            return int(input("Enter run number to analyze: ").strip())
        except ValueError:
            print("❌ Please enter a valid integer run number")

def ask_percentage():
    while True:
        try:
            p = float(input("Enter percentage of data to send to InfluxDB (e.g., 1 for 1%, 10 for 10%): ").strip())
            if 0 < p <= 100:
                return p
            else:
                print("Please enter a value between 0 and 100")
        except ValueError:
            print("Please enter a valid number")

def extract_subrun_number(path: Path) -> int:
    """
    Extracts the number after RunXXX. from RunXXX.Y_list.dat
    """
    m = re.search(r"Run\d+\.(\d+)_list\.dat", path.name)
    return int(m.group(1)) if m else -1

# ============================================================
# CONFIG
# ============================================================

DATAFILES_DIR = Path(
    "/eos/experiment/newtile/beamtests/26_05_t10/fers_daq/bin/DataFiles"
)

OUTPUT_CSV_TEMPLATE = "Run{run}.csv"

# -------- InfluxDB ----------
INFLUX_URL = "http://localhost:8086"
INFLUX_ORG = "TestBeam_org"
INFLUX_BUCKET = "Fers_bucket"
INFLUX_TOKEN = "JevdaRydlGQv_xshNvghA45XoivlKYpfnmCUU43BkAKSRh8wQPT_nUbxwt3xEstUbJDOzK4SNd9Lz3GcdCV-1w=="

# ============================================================
# FORMAT DEFINITIONS
# ============================================================

FILE_HEADER_FMT  = "<2s3s H H B H B f Q"
EVENT_HEADER_FMT = "<H B d Q Q Q H"
CHAN_HEADER_FMT  = "<B B"

# ============================================================

def main():

    RUN_NUMBER = ask_run_number()

    # --------------------------------------------------------
    # Find all subrun files
    # --------------------------------------------------------

    input_files = sorted(
        DATAFILES_DIR.glob(f"Run{RUN_NUMBER}.*_list.dat"),
        key=extract_subrun_number
    )

    if not input_files:
        raise RuntimeError(f"No files found for Run {RUN_NUMBER}")

    print(f"[INFO] Found {len(input_files)} files for Run {RUN_NUMBER}")
    for f in input_files:
        print(f"  - {f.name}")

    # --------------------------------------------------------
    # Ask for sampling percentage
    # --------------------------------------------------------

    sampling_percentage = ask_percentage()
    sampling_divisor = int(100 / sampling_percentage)

    OUTPUT_FILE = OUTPUT_CSV_TEMPLATE.format(run=RUN_NUMBER)

    # ========================================================
    # InfluxDB client
    # ========================================================

    influx_client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )

    write_api = influx_client.write_api()

    # ========================================================
    # CSV + INFLUX
    # ========================================================

    with open(OUTPUT_FILE, "w", newline="") as csvfile:

        writer = csv.writer(csvfile)
        writer.writerow([
            "Timestamp_ns",
            "Run",
            "Trigger_Id",
            "Board",
            "Channel",
            "DataType",
            "LG",
            "HG",
            "ToA",
            "ToT"
        ])

        # ====================================================
        # Loop over all subruns
        # ====================================================

        time_epoch_ms = None
        influx_counter = 0

        for input_file in input_files:

            print(f"[INFO] Processing {input_file.name}")

            data = input_file.read_bytes()
            offset = 0

            # ---------------- FILE HEADER (only for .0) --------------------

            if ".0_list.dat" in input_file.name:
                fh = struct.unpack_from(FILE_HEADER_FMT, data, offset)
                offset += struct.calcsize(FILE_HEADER_FMT)

                (
                    _file_fmt,
                    _janus_rel,
                    _board_type,
                    _run,
                    acq_mode,
                    _e_nbins,
                    _time_unit,
                    _time_conv,
                    time_epoch_ms
                ) = fh

                if acq_mode != 3:
                    print(
                        f"[WARNING] Skipping {input_file.name}: "
                        f"acq_mode={acq_mode} (not Spect_Timing)"
                    )
                    continue
            else:
                if time_epoch_ms is None:
                    print(f"[ERROR] Skipping {input_file.name}: no time_epoch_ms from .0 file")
                    continue

            # ---------------- EVENT LOOP --------------------

            while offset < len(data):

                ev_start = offset

                (
                    ev_size,
                    board_id,
                    TStamp_us,
                    _dTRef,
                    Trg_Id,
                    _ch_mask,
                    nhits
                ) = struct.unpack_from(EVENT_HEADER_FMT, data, offset)

                offset += struct.calcsize(EVENT_HEADER_FMT)

                timestamp_ns = int(
                    time_epoch_ms * 1_000_000 + TStamp_us * 1_000
                )

                for _ in range(nhits):

                    ch, dtype = struct.unpack_from(CHAN_HEADER_FMT, data, offset)
                    offset += 2

                    LG = HG = ToA = ToT = None

                    if dtype & 0x01:
                        LG = struct.unpack_from("<H", data, offset)[0]
                        offset += 2
                    if dtype & 0x02:
                        HG = struct.unpack_from("<H", data, offset)[0]
                        offset += 2
                    if dtype & 0x10:
                        ToA = struct.unpack_from("<f", data, offset)[0]
                        offset += 4
                    if dtype & 0x20:
                        ToT = struct.unpack_from("<f", data, offset)[0]
                        offset += 4

                    if dtype == 0:
                        continue

                    # ---------------- CSV ----------------
                    writer.writerow([
                        timestamp_ns,
                        RUN_NUMBER,
                        Trg_Id,
                        board_id,
                        ch,
                        f"0x{dtype:02X}",
                        LG,
                        HG,
                        ToA,
                        ToT
                    ])

                    csvfile.flush()

                    # ---------------- Influx ----------------
                    if influx_counter % sampling_divisor == 0:
                        p = (
                            Point("fers_hits")
                            .tag("run", str(RUN_NUMBER))
                            .tag("board", board_id)
                            .tag("channel", ch)
                            .tag("dtype", f"0x{dtype:02X}")
                            .field("Trigger_Id", int(Trg_Id))
                            .field("LG", LG)
                            .field("HG", HG)
                            .field("ToA", ToA)
                            .field("ToT", ToT)
                            .time(timestamp_ns, WritePrecision.NS)
                        )

                        p._fields = {
                            k: v for k, v in p._fields.items()
                            if v is not None
                        }

                        write_api.write(
                            bucket=INFLUX_BUCKET,
                            org=INFLUX_ORG,
                            record=p
                        )

                    influx_counter += 1

                    write_api.write(
                        bucket=INFLUX_BUCKET,
                        org=INFLUX_ORG,
                        record=p
                    )

                offset = ev_start + ev_size

    # ========================================================
    # CLEAN SHUTDOWN
    # ========================================================

    write_api.flush()
    write_api.close()
    influx_client.close()

    print(f"[DONE] Run {RUN_NUMBER} fully processed")
    print(f"[DONE] CSV written: {OUTPUT_FILE}")

# ============================================================
if __name__ == "__main__":
    main()
