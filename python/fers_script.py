#!/usr/bin/env python3
import struct
import csv
from pathlib import Path
from influxdb_client import InfluxDBClient, Point, WriteOptions

# ============================================================
# CONFIG
# ============================================================

INPUT_FILE = "/work/FCC/TB2026/Data/fers_raw/Run311.0_list.dat"
OUTPUT_FILE = "Run311_decoded_clean.csv"

# -------- InfluxDB ----------
INFLUX_URL = "http://localhost:8087"
INFLUX_ORG = "TestBeam_org"
INFLUX_BUCKET = "Fers_bucket_abs"
INFLUX_TOKEN = "Kr73sktQb-QMH3rCNCPuMdgh8d3HSdb8vseQ6Jp8PukdVNcDkttpWaSG3rZ8JrWn6TMt4K8v3i0nx5OBhtXFSg=="

RUN_NUMBER = 311

# ============================================================
# FORMAT DEFINITIONS
# ============================================================

FILE_HEADER_FMT = "<2s3s H H B H B f Q"
EVENT_HEADER_FMT = "<H B d Q Q Q H"
CHAN_HEADER_FMT  = "<B B"

# ============================================================

def main():

    data = Path(INPUT_FILE).read_bytes()
    offset = 0

    # ========================================================
    # InfluxDB client (batch MODE PRO)
    # ========================================================

    influx_client = InfluxDBClient(
        url=INFLUX_URL,
        token=INFLUX_TOKEN,
        org=INFLUX_ORG
    )

    write_api = influx_client.write_api(
        write_options=WriteOptions(
            batch_size=5000,
            flush_interval=1000,
            retry_interval=5000,
            jitter_interval=0
        )
    )

    # ========================================================
    # FILE HEADER
    # ========================================================

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
        raise RuntimeError(f"acq_mode={acq_mode}, expected Spect_Timing (3)")

    # ========================================================
    # CSV
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
        # EVENT LOOP
        # ====================================================

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

            # -------- Absolute timestamp --------
            timestamp_ns = int(time_epoch_ms * 1e6 + TStamp_us * 1e3)

            # =================================================
            # PAYLOAD
            # =================================================

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

                # ---------------- Influx ----------------
                p = (
                    Point("fers_hits")
                    .tag("run", RUN_NUMBER)
                    .tag("board", board_id)
                    .tag("channel", ch)
                    .tag("dtype", f"0x{dtype:02X}")
                    # ---------- FIELDS ----------
                    .field("Trigger_Id", int(Trg_Id))      # <<< AÑADIDO
                    .field("LG", LG)
                    .field("HG", HG)
                    .field("ToA", ToA)
                    .field("ToT", ToT)
                    .time(timestamp_ns)
                )

                # Remove None fields
                p._fields = {k: v for k, v in p._fields.items() if v is not None}

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

    print(f"[DONE] CSV written   : {OUTPUT_FILE}")
    print(f"[DONE] Influx bucket : {INFLUX_BUCKET}")
    print("[DONE] Trigger_Id stored as field (ready for HG vs Trigger_Id)")

# ============================================================
if __name__ == "__main__":
    main()
