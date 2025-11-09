# # This code implements a background job worker. It repeatedly fetches jobs from a job queue (database), executes them, updates job status, handles retries with exponential backoff, and writes a heartbeat file so the system knows the worker is alive
# import os
# import signal
# import time
# from datetime import datetime, timedelta
# from threading import Event

# from flam.db.base import get_session
# from flam.executor import run_command
# from flam.queue_manager import claim_next_job, move_to_dead
# from flam.config import get_int, get_float

# _shutdown = Event()  # just a flag to signal shutdown


# def _handle_signal(signum, frame):
#     _shutdown.set()


# # signal handling
# signal.signal(signal.SIGINT, _handle_signal)
# try:
#     signal.signal(signal.SIGTERM, _handle_signal)
# except Exception:
#     pass  # Windows may not have SIGTERM


# def _heartbeat(path):
#     try:
#         with open(path, "w") as f:
#             f.write(str(time.time()))
#     except Exception:
#         pass


# def worker_loop(heartbeat_dir="data", poll_interval=0.1, max_backoff_cap=3.0):
#     os.makedirs(heartbeat_dir, exist_ok=True)
#     hb_path = os.path.join(heartbeat_dir, f"worker-{os.getpid()}.hb")

#     session = get_session()

#     while not _shutdown.is_set():
#         _heartbeat(hb_path)

#         job = claim_next_job(session)
#         if not job:
#             time.sleep(poll_interval)
#             continue

#         exit_code, stdout, stderr = run_command(job.command)
#         # Print job output to console
#         if stdout:
#             print(f"[JOB {job.id} OUTPUT]:\n{stdout}")

#         if stderr:
#             print(f"[JOB {job.id} ERROR]:\n{stderr}")

#         if exit_code == 0:
#             job.status = "completed"
#             job.last_error = None
#             job.next_run_at = None
#             session.commit()
#         else:
#             job.attempts += 1
#             job.last_error = stderr or "Command failed"
#             max_retries = job.max_retries or get_int("max_retries", 3)
#             backoff_base = get_float("backoff_base", 2.0)

#             if job.attempts >= max_retries:
#                 move_to_dead(job, session)
#             else:
#                 delay = min((backoff_base**job.attempts), max_backoff_cap)
#                 job.status = "pending"
#                 # job.next_run_at = datetime.utcnow() + timedelta(seconds=delay)
#                 job.next_run_at = datetime.now() + timedelta(seconds=delay)

#                 session.commit()

#         if _shutdown.is_set():
#             break

#     try:
#         os.remove(hb_path)
#     except Exception:
#         pass


# if __name__ == "__main__":
#     worker_loop()
# Background worker: claims jobs, runs commands, prints output, retries with backoff, writes heartbeat.
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from threading import Event

from flam.db.base import get_session
from flam.executor import run_command
from flam.queue_manager import claim_next_job, move_to_dead
from flam.config import get_int, get_float

_shutdown = Event()


def _handle_signal(signum, frame):
    _shutdown.set()


# Register signals (SIGTERM may not exist on Windows)
signal.signal(signal.SIGINT, _handle_signal)
try:
    signal.signal(signal.SIGTERM, _handle_signal)
except Exception:
    pass

def _heartbeat(path: str):
    try:
        with open(path, "w") as f:
            f.write(str(time.time()))
    except Exception:
        # Heartbeat should never crash the worker
        pass

def worker_loop(heartbeat_dir="data", poll_interval=0.2, max_backoff_cap=3.0):
    os.makedirs(heartbeat_dir, exist_ok=True)
    hb_path = os.path.join(heartbeat_dir, f"worker-{os.getpid()}.hb")
    session = get_session()

    print(f"[worker {os.getpid()}] started. heartbeat={hb_path}")

    while not _shutdown.is_set():
        _heartbeat(hb_path)

        job = claim_next_job(session)
        if not job:
            time.sleep(poll_interval)
            continue

        print(f"[worker {os.getpid()}] running job '{job.id}': {job.command}")

        exit_code, stdout, stderr = run_command(job.command)

        # Always echo outputs so the CLI shows something useful.
        if stdout:
            print(f"[job {job.id}] STDOUT:\n{stdout}")
        if stderr:
            print(f"[job {job.id}] STDERR:\n{stderr}")

        if exit_code == 0:
            job.status = "completed"
            job.last_error = None
            job.next_run_at = None
            session.commit()
            print(f"[worker {os.getpid()}] job '{job.id}' -> completed")
        else:
            job.attempts += 1
            job.last_error = stderr or "Command failed"

            max_retries = job.max_retries or get_int("max_retries", 3)
            backoff_base = get_float("backoff_base", 2.0)

            if job.attempts >= max_retries:
                move_to_dead(job, session)
                print(
                    f"[worker {os.getpid()}] job '{job.id}' -> DLQ (attempts={job.attempts})"
                )
            else:
                # exponential backoff with cap
                delay = min((backoff_base**job.attempts), max_backoff_cap)
                job.status = "pending"
                # store next_run_at in UTC
                job.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                session.commit()
                print(
                    f"[worker {os.getpid()}] job '{job.id}' failed (attempts={job.attempts}); retry in {delay:.2f}s"
                )

        if _shutdown.is_set():
            break

    # Cleanup heartbeat
    try:
        os.remove(hb_path)
    except Exception:
        pass
    print(f"[worker {os.getpid()}] stopped.")
