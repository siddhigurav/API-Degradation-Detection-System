import subprocess
import time
from datetime import datetime

cmd = ["python", "-m", "uvicorn", "src.alerter:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "debug"]

def now():
    return datetime.now().isoformat()

while True:
    print(f"SUPERVISOR: starting uvicorn at {now()}")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    try:
        for line in p.stdout:
            print(line, end='')
    except Exception as e:
        print(f"SUPERVISOR: error reading stdout: {e}")

    ret = p.wait()
    print(f"SUPERVISOR: uvicorn exited with code {ret} at {now()}")
    print("SUPERVISOR: sleeping 5s before restart (Ctrl+C to stop)")
    time.sleep(5)
