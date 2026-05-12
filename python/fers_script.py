#!/usr/bin/env python3

import struct
import csv
import re
import time
import threading
from pathlib import Path
from influxdb_client import InfluxDBClient, Point, WritePrecision

# ============================================================
# HELPERS
# ============================================================

def ask_run_from_available(datafiles_dir: Path):
    """
    Lists all available Run numbers and asks user to select one
    """
    # Find all Run*.*_list.dat files to get available runs
    run_files = sorted(datafiles_dir.glob("Run*.*_list.dat"))
    
    if not run_files:
        raise RuntimeError(f"No run files found in {datafiles_dir}")
    
    # Extract unique run numbers
    available_runs = set()
    for f in run_files:
        m = re.search(r"Run(\d+)\.", f.name)
        if m:
            available_runs.add(int(m.group(1)))
    
    available_runs = sorted(available_runs)
    
    print("\n📁 Available Runs:")
    for idx, run in enumerate(available_runs, 1):
        print(f"  {idx}. Run {run}")
    
    while True:
        try:
            choice = input("\nSelect run number or index: ").strip()
            run_num = int(choice)
            
            if run_num in available_runs:
                return run_num
            elif 1 <= run_num <= len(available_runs):
                return available_runs[run_num - 1]
            else:
                print(f"❌ Please select a valid option (1-{len(available_runs)} or a run number from the list)")
        except ValueError:
            print("❌ Please enter a valid integer")

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

OUTPUT_CSV_TEMPLATE = "/eos/experiment/newtile/beamtests/26_05_t10/prep/led/QC_grafana/fers_csv/Run{run}.csv"

# -------- InfluxDB ----------
INFLUX_URL = "http://localhost:8086"
INFLUX_ORG = "Newtile_Online-org"
INFLUX_BUCKET = "Fers_bucket"
INFLUX_TOKEN = "MreJPVJw6aNMicNfgRoV6Zx57qSX1L-aJ_m92kV_EeqAi6WN4XJTZnh-2PVbTwJJPrMqZyfKggTNYfShzvvhSQ=="

# ============================================================
# FORMAT DEFINITIONS
# ============================================================

FILE_HEADER_FMT  = "<2s3s H H B H B f Q"
EVENT_HEADER_FMT = "<H B d Q Q Q H"
CHAN_HEADER_FMT  = "<B B"

# ============================================================

def main():

    RUN_NUMBER = ask_run_from_available(DATAFILES_DIR)

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
    sampling_divisor = max(1, round(100 / sampling_percentage))

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
        event_counter = 0

        for input_file in input_files:

            print(f"[INFO] Processing {input_file.name}")

            data = input_file.read_bytes()
            offset = 0

            # timeout config: seconds to wait for file growth before skipping
            FILE_GROWTH_TIMEOUT = 720.0
            FILE_GROWTH_POLL = 20.0

            def ensure_bytes_available(required_offset, size):
                nonlocal data
                # if already available, return True
                if required_offset + size <= len(data):
                    return True

                start = time.time()
                last_size = len(data)
                while True:
                    try:
                        file_size = input_file.stat().st_size
                    except Exception:
                        file_size = last_size

                    if file_size > len(data):
                        # file grew: re-read full data buffer
                        data = input_file.read_bytes()
                        return required_offset + size <= len(data)

                    if time.time() - start > FILE_GROWTH_TIMEOUT:
                        return False

                    time.sleep(FILE_GROWTH_POLL)

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

            timed_out = False
            while offset < len(data):

                ev_start = offset

                # ensure event header available
                hdr_size = struct.calcsize(EVENT_HEADER_FMT)
                ok = ensure_bytes_available(offset, hdr_size)
                if not ok:
                    print(f"[TIMEOUT] no growth for {input_file.name}, moving to next subrun file")
                    timed_out = True
                    break

                (
                    ev_size,
                    board_id,
                    TStamp_us,
                    _dTRef,
                    Trg_Id,
                    _ch_mask,
                    nhits,
                ) = struct.unpack_from(EVENT_HEADER_FMT, data, offset)

                offset += hdr_size

                sample_this_event = (event_counter % sampling_divisor == 0)
                event_counter += 1

                timestamp_ns = int(time_epoch_ms * 1_000_000 + TStamp_us * 1_000)

                for _ in range(nhits):

                    # ensure channel header available
                    ch_hdr_size = struct.calcsize(CHAN_HEADER_FMT)
                    ok = ensure_bytes_available(offset, ch_hdr_size)
                    if not ok:
                        print(f"[TIMEOUT] no growth while reading hit header in {input_file.name}")
                        timed_out = True
                        break

                    ch, dtype = struct.unpack_from(CHAN_HEADER_FMT, data, offset)
                    offset += ch_hdr_size

                    LG = HG = ToA = ToT = None

                    if dtype & 0x01:
                        ok = ensure_bytes_available(offset, 2)
                        if not ok:
                            timed_out = True
                            break
                        LG = struct.unpack_from("<H", data, offset)[0]
                        offset += 2
                    if dtype & 0x02:
                        ok = ensure_bytes_available(offset, 2)
                        if not ok:
                            timed_out = True
                            break
                        HG = struct.unpack_from("<H", data, offset)[0]
                        offset += 2
                    if dtype & 0x10:
                        ok = ensure_bytes_available(offset, 4)
                        if not ok:
                            timed_out = True
                            break
                        ToA = struct.unpack_from("<f", data, offset)[0]
                        offset += 4
                    if dtype & 0x20:
                        ok = ensure_bytes_available(offset, 4)
                        if not ok:
                            timed_out = True
                            break
                        ToT = struct.unpack_from("<f", data, offset)[0]
                        offset += 4

                    if timed_out:
                        break

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
                        ToT,
                    ])

                    csvfile.flush()

                    # ---------------- Influx ----------------
                    if sample_this_event:
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

                        p._fields = {k: v for k, v in p._fields.items() if v is not None}
                        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=p)

                if timed_out:
                    break

                # throttle: small sleep every 10 events to avoid outrunning DAQ
                if event_counter % 10 == 0:
                    time.sleep(0.001)

                offset = ev_start + ev_size

            if timed_out:
                # move to next file
                continue

        # ====================================================
        # After all current subrun files: wait for more parts
        # ====================================================

        print("\n[WAITING] All current files processed. Watching for new data...")
        print("[INFO] Press 's' to stop waiting and exit, or wait for more .*_list.dat files...")

        user_stop = threading.Event()

        def wait_for_input():
            while not user_stop.is_set():
                try:
                    user_input = input().strip().lower()
                    if user_input == 's':
                        user_stop.set()
                except EOFError:
                    pass

        input_thread = threading.Thread(target=wait_for_input, daemon=True)
        input_thread.start()

        wait_timeout = FILE_GROWTH_TIMEOUT
        wait_start = time.time()
        last_file_count = len(input_files)

        while not user_stop.is_set():
            # check if new files appeared
            new_files = sorted(
                DATAFILES_DIR.glob(f"Run{RUN_NUMBER}.*_list.dat"),
                key=extract_subrun_number
            )

            if len(new_files) > last_file_count:
                print(f"[NEW FILE] Detected new subrun files! Resuming...")
                input_files = new_files
                break

            if time.time() - wait_start > wait_timeout:
                print(f"[TIMEOUT] No new files for {wait_timeout}s. Exiting...")
                break

            time.sleep(FILE_GROWTH_POLL)

        user_stop.set()

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
