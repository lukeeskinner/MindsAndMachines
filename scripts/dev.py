"""Run the two local dev processes with a single command; stop both on Ctrl-C."""
import os
from pathlib import Path
import subprocess
import signal
import sys
import time

root = Path(__file__).resolve().parent.parent
os.chdir(root)
processes = []
try:
    processes.append(subprocess.Popen([
        sys.executable, "-m", "uvicorn", "backend.app.main:app",
        "--host", "127.0.0.1", "--port", "8000",
    ], start_new_session=True))
    processes.append(subprocess.Popen(["npm", "--prefix", "frontend", "run", "dev"], start_new_session=True))
    print("Open http://127.0.0.1:5173 — teaching source shown per response. Ctrl-C stops both servers.", flush=True)
    while all(process.poll() is None for process in processes):
        time.sleep(0.3)
except KeyboardInterrupt:
    pass
finally:
    failure = any(p.returncode not in (None, 0, -2) for p in processes)
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    if failure:
        sys.exit(1)
