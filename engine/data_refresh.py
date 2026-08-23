"""Admin-triggered cache refresh jobs (BIXI walk-graph precompute, STM GTFS re-download +
rebuild), run as a real subprocess (the existing standalone script, unmodified) rather than
in-process, so the ~10-15 min OSRM-heavy work never competes with the Flask process's own GIL
for live search requests, and a crash in the job can't take the app down. Each job's in-memory
status is polled by the frontend; app.py supplies the on_success callback that reloads the
now-fresh pickle into its own process memory once the subprocess exits cleanly."""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
JOB_TIMEOUT_SEC = 1800  # 30 min, generous vs. the ~10-15 min real BIXI rebuild observed
# A dev-environment quirk on at least one machine this has run on causes `python app.py` to
# sometimes come up as two independent processes rather than one (see project memory, 2026-08-08
# session), the in-memory `_jobs` dict below only guards against a double-click *within* a
# single process, which doesn't help across that split. LOCK_DIR holds an exclusively-created
# lock file per job as the real cross-process guard, so two processes racing to start the same
# job can't both spawn a rebuild subprocess and stomp on each other's output file.
LOCK_DIR = PROJECT_ROOT / "data" / "raw"
LOCK_STALE_SEC = JOB_TIMEOUT_SEC + 300  # grace period past a job's own timeout before its lock is assumed abandoned (e.g. the holding process was killed before its `finally` ran)

_jobs = {
    "bixi": {"status": "idle", "started_at": None, "finished_at": None, "error": None},
    "stm": {"status": "idle", "started_at": None, "finished_at": None, "error": None},
}
_lock = threading.Lock()


def get_status(name):
    with _lock:
        return dict(_jobs[name])


def _acquire_file_lock(name):
    """Exclusive-create a `.{name}_refresh.lock` file as the cross-process mutex. Returns the
    lock Path on success, None if another process already holds a live one."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCK_DIR / f".{name}_refresh.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return lock_path
    except FileExistsError:
        try:
            age_sec = time.time() - lock_path.stat().st_mtime
        except FileNotFoundError:
            return None  # lock vanished between our failed create and this check, treat as contended, next click retries cleanly
        if age_sec <= LOCK_STALE_SEC:
            return None
        lock_path.unlink(missing_ok=True)  # abandoned by a killed process, reclaim it
        return _acquire_file_lock(name)


def _run_job(name, cmd, on_success):
    with _lock:
        if _jobs[name]["status"] == "running":
            return False
    lock_path = _acquire_file_lock(name)
    if lock_path is None:
        return False
    with _lock:
        _jobs[name] = {"status": "running", "started_at": time.time(), "finished_at": None, "error": None}

    def worker():
        try:
            result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=JOB_TIMEOUT_SEC)
            if result.returncode != 0:
                raise RuntimeError((result.stderr or "").strip()[-2000:] or "subprocess failed with no stderr output")
            on_success()
            with _lock:
                _jobs[name]["status"] = "done"
        except Exception as exc:
            with _lock:
                _jobs[name]["status"] = "failed"
                _jobs[name]["error"] = str(exc)
        finally:
            with _lock:
                _jobs[name]["finished_at"] = time.time()
            lock_path.unlink(missing_ok=True)

    threading.Thread(target=worker, daemon=True).start()
    return True


def start_bixi_refresh(on_success):
    """Rebuilds walk_graph_cache.pkl (BIXI-driven neighbor/edge cache) via the existing
    precompute script, unmodified. on_success is called (in the worker thread, after the
    subprocess exits 0) to reload the new cache into app.py's in-memory walk_graph global."""
    cmd = [PYTHON, str(PROJECT_ROOT / "data" / "scripts" / "precompute_walk_graph.py")]
    return _run_job("bixi", cmd, on_success)


def start_stm_refresh(on_success):
    """Re-downloads STM's GTFS zip and rebuilds transit_cache.pkl from it (+ whatever REM zip
    is already on disk, untouched). on_success reloads the new transit_data into app.py's
    in-memory global."""
    cmd = [PYTHON, str(PROJECT_ROOT / "data" / "scripts" / "refresh_stm.py")]
    return _run_job("stm", cmd, on_success)
