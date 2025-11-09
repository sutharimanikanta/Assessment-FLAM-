# import json
# import os
# import signal
# import subprocess
# from multiprocessing import Process
# from time import sleep

# from flam.worker import worker_loop

# PIDS_FILE = os.path.join("data", "workers.pids")

# def _write_pids(pids):
#     os.makedirs("data", exist_ok=True)
#     with open(PIDS_FILE, "w") as f:
#         json.dump(pids, f)


# def _read_pids():
#     if not os.path.exists(PIDS_FILE):
#         return []
#     try:
#         return json.load(open(PIDS_FILE))
#     except Exception:
#         return []

# def start_workers(count=1):
#     os.makedirs("data", exist_ok=True)
#     pids = _read_pids()
#     procs = []
#     for _ in range(count):
#         p = Process(target=worker_loop, args=("data", 0.1, 3.0), daemon=False)
#         p.start()
#         pids.append(p.pid)
#         procs.append(p)
#     _write_pids(pids)
#     print(f"Started {count} worker(s): {pids[-count:]}")

# def _kill_pid(pid):
#     try:
#         if os.name == "nt":
#             try:
#                 os.kill(pid, signal.CTRL_BREAK_EVENT)
#             except Exception:
#                 subprocess.run(
#                     ["taskkill", "/PID", str(pid), "/T", "/F"],
#                     stdout=subprocess.DEVNULL,
#                     stderr=subprocess.DEVNULL,
#                 )
#         else:
#             os.kill(pid, signal.SIGTERM)
#     except Exception:
#         pass

# def stop_workers():
#     pids = _read_pids()
#     if not pids:
#         print("No worker PIDs found.")
#         return

#     for pid in pids:
#         _kill_pid(pid)

#     sleep(1.5)

#     for pid in pids:
#         hb = os.path.join("data", f"worker-{pid}.hb")
#         try:
#             if os.path.exists(hb):
#                 os.remove(hb)
#         except Exception:
#             pass

#     try:
#         os.remove(PIDS_FILE)
#     except Exception:
#         pass
#     print("Workers signaled to stop.")
import json
import os
import signal
import subprocess
from multiprocessing import Process
from time import sleep

from flam.worker import worker_loop

PIDS_FILE = os.path.join("data", "workers.pids")


def _write_pids(pids):
    os.makedirs("data", exist_ok=True)
    with open(PIDS_FILE, "w") as f:
        json.dump(pids, f)

def _read_pids():
    if not os.path.exists(PIDS_FILE):
        return []
    try:
        with open(PIDS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def start_workers(count=1):
    os.makedirs("data", exist_ok=True)
    pids = _read_pids()
    procs = []
    for _ in range(count):
        p = Process(target=worker_loop, args=("data", 0.1, 3.0), daemon=False)
        p.start()
        pids.append(p.pid)
        procs.append(p)
    _write_pids(pids)
    print(f"Started {count} worker(s): {pids[-count:]}")

def _kill_pid(pid):
    try:
        if os.name == "nt":
            # Try a gentle console break first
            try:
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            except Exception:
                # Fall back to taskkill if needed
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        else:
            os.kill(pid, signal.SIGTERM)
    except Exception:
        pass

def stop_workers():
    pids = _read_pids()
    if not pids:
        print("No worker PIDs found.")
        return

    for pid in pids:
        _kill_pid(pid)

    # Let workers exit and clean up their heartbeat files
    sleep(1.5)

    for pid in pids:
        hb = os.path.join("data", f"worker-{pid}.hb")
        try:
            if os.path.exists(hb):
                os.remove(hb)
        except Exception:
            pass

    try:
        os.remove(PIDS_FILE)
    except Exception:
        pass
    print("Workers signaled to stop.")
