#!/usr/bin/env python3

import os
import re
import time
import threading
import subprocess
from pathlib import Path


# Directory where FERS creates RunXXX.Y_list.dat files
DATAFILES_DIR = Path("/eos/experiment/newtile/beamtests/26_05_t10/fers_daq/bin/DataFiles")

# External environment and script to launch when a new Run appears
ONLINE_BASE_DIR = Path("/home/iburriel/python")
ONLINE_PYTHON = ONLINE_BASE_DIR / "venv" / "bin" / "python"
ONLINE_SCRIPT = ONLINE_BASE_DIR / "fers_script_OnlineMonitoring.py"

# Polling cadence (seconds)
POLL_SECONDS = 5.0


def scan_run_numbers(data_dir: Path) -> set[int]:
	"""Return all distinct Run numbers seen as Run<id>.<subrun>_list.dat."""
	runs = set()
	pattern = re.compile(r"^Run(\d+)\.\d+_list\.dat$")
	for path in data_dir.glob("Run*.*_list.dat"):
		match = pattern.match(path.name)
		if match:
			runs.add(int(match.group(1)))
	return runs


def validate_paths() -> None:
	if not DATAFILES_DIR.exists():
		raise RuntimeError(f"Data directory not found: {DATAFILES_DIR}")
	if not ONLINE_SCRIPT.exists():
		raise RuntimeError(f"Online monitoring script not found: {ONLINE_SCRIPT}")
	if not ONLINE_PYTHON.exists():
		raise RuntimeError(f"Venv python not found: {ONLINE_PYTHON}")


def launch_online_monitoring(run_number: int) -> None:
	"""
	Launch one detached monitoring process for the detected run.
	Pass run number as env var so the target script can use it if supported.
	"""
	env = os.environ.copy()
	env["NEW_RUN_NUMBER"] = str(run_number)

	# Start detached process and continue watching without blocking.
	process = subprocess.Popen(
		[str(ONLINE_PYTHON), str(ONLINE_SCRIPT)],
		cwd=str(ONLINE_BASE_DIR),
		env=env,
	)
	print(
		f"[LAUNCH] Started monitoring for Run {run_number} "
		f"(pid={process.pid})"
	)
	return process


def main() -> None:
	validate_paths()

	seen_runs = scan_run_numbers(DATAFILES_DIR)
	pending_runs: list[int] = []
	active_process: subprocess.Popen | None = None
	active_run: int | None = None
	if seen_runs:
		print(f"[INIT] Last detected run: Run{max(seen_runs)}")
	else:
		print("[INIT] No runs detected yet")

	print(f"[WATCH] Monitoring {DATAFILES_DIR} every {POLL_SECONDS:.1f}s")
	print("[INFO] Press 's' then Enter to stop the watcher")

	stop_event = threading.Event()

	def read_stop_key() -> None:
		while not stop_event.is_set():
			try:
				user_input = input().strip().lower()
				if user_input == "s":
					stop_event.set()
			except EOFError:
				break

	input_thread = threading.Thread(target=read_stop_key, daemon=True)
	input_thread.start()

	try:
		while not stop_event.is_set():
			current_runs = scan_run_numbers(DATAFILES_DIR)
			new_runs = sorted(current_runs - seen_runs)

			if new_runs:
				for run_number in new_runs:
					print(f"[NEW RUN] Detected Run{run_number}")
					pending_runs.append(run_number)
				seen_runs = current_runs

			if active_process is not None:
				return_code = active_process.poll()
				if return_code is not None:
					print(f"[DONE] Monitoring finished for Run {active_run} (exit={return_code})")
					active_process = None
					active_run = None

			if active_process is None and pending_runs:
				active_run = pending_runs.pop(0)
				active_process = launch_online_monitoring(active_run)

			time.sleep(POLL_SECONDS)

		print("[STOP] Watcher stopped by user")

	except KeyboardInterrupt:
		print("\n[STOP] Watcher interrupted by user")


if __name__ == "__main__":
	main()
