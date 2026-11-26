"""Railway worker entry point.

Runs the prediction pipeline on a configurable interval. Internet/database
sync can be added before ``run_prediction`` once the source adapter is set.
Secrets are read only from Railway environment variables.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INTERVAL = max(1, int(os.getenv("SYNC_INTERVAL_MINUTES", "5"))) * 60


def run_prediction() -> int:
    command = [sys.executable, "-B", "main.py"]
    result = subprocess.run(command, cwd=ROOT / "ucl_prediction_center", check=False)
    return result.returncode


def main() -> None:
    while True:
        code = run_prediction()
        if code != 0:
            print(f"Prediction run failed with exit code {code}", flush=True)
        else:
            print("Prediction run completed", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
