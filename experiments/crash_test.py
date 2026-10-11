"""Crash experiments: start a job, kill -9 it mid-review, recover, then measure.

Usage:
  python -m experiments.crash_test v2-per-file     # one scenario
  python -m experiments.crash_test all             # every scenario, in order
Temporal scenarios need a dev server running: temporal server start-dev
"""

import json
import os
import signal
import subprocess
import sys
import time

from common.review import OUTPUT_DIR, REVIEW_DELAY
from experiments.measure import load_events, summarize

PY = sys.executable
LG = [PY, "-m", "v2_langgraph.graph"]

# kill_after = kill -9 the process halfway through the review that follows the Nth
# finished review. crash_at = the process kills ITSELF at a named point instead.
SCENARIOS = {
    "v1-plain":         dict(cmd=[PY, "-m", "v1_plain.run"], kill_after=2),
    "v2-no-checkpoint": dict(cmd=LG + ["--checkpointer", "none"], kill_after=2),
    "v2-one-big-node":  dict(cmd=LG + ["--granularity", "big"], kill_after=2),
    "v2-per-file":      dict(cmd=LG + ["--granularity", "per-file"], kill_after=2),
    "v2-report-naive":  dict(cmd=LG + ["--report", "naive"], crash_at="after_report_write"),
    "v2-report-atomic": dict(cmd=LG + ["--report", "atomic"], crash_at="after_report_write"),
    "v3-no-heartbeat":  dict(temporal=["--start-to-close", "20"], kill_after=2),
    "v3-heartbeat":     dict(temporal=["--start-to-close", "20", "--heartbeat", "2"], kill_after=2),
    "v3-report-crash":  dict(temporal=["--start-to-close", "20"], crash_at="after_report_write"),
}


def wait_for_done(run_id, n, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        if sum(e["event"] == "review_done" for e in load_events(run_id)) >= n:
            return
        time.sleep(0.1)
    raise TimeoutError(f"{run_id}: never reached {n} finished reviews")


def crash(proc, run_id, sc):
    """Kill proc (or let it kill itself). Returns the moment of the crash."""
    if "crash_at" in sc:
        proc.wait()
    else:
        wait_for_done(run_id, sc["kill_after"])
        time.sleep(REVIEW_DELAY / 2)       # land in the MIDDLE of the next review
        proc.send_signal(signal.SIGKILL)   # same as: kill -9 <pid>
        proc.wait()
    print(f"   💥 pid {proc.pid} died (exit {proc.returncode})", flush=True)
    return time.time()


def run_scenario(name):
    sc = SCENARIOS[name]
    run_id = f"{name}-{int(time.time())}"
    crash_env = {**os.environ, "CRASH_AT": sc.get("crash_at", "")}
    print(f"\n=== {name}  (run_id={run_id}) ===", flush=True)

    if "temporal" in sc:
        worker = [PY, "-m", "v3_temporal.worker"]
        w1 = subprocess.Popen(worker, env=crash_env)
        time.sleep(2)                       # let the worker connect
        starter = subprocess.Popen([PY, "-m", "v3_temporal.start", "--run-id", run_id] + sc["temporal"])
        crash_ts = crash(w1, run_id, sc)
        w2 = subprocess.Popen(worker)       # a fresh worker; nobody tells it what to resume
        starter.wait(timeout=180)
        w2.terminate()
        w2.wait()
    else:
        p = subprocess.Popen(sc["cmd"] + ["--run-id", run_id], env=crash_env)
        crash_ts = crash(p, run_id, sc)
        print("   🔁 resuming by hand: same command, same run id", flush=True)
        subprocess.run(sc["cmd"] + ["--run-id", run_id], check=True)

    result = {"scenario": name, "crash_ts": crash_ts, **summarize(run_id, crash_ts)}
    with open(OUTPUT_DIR / "results.jsonl", "a") as f:
        f.write(json.dumps(result) + "\n")
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    names = list(SCENARIOS) if sys.argv[1:] == ["all"] else sys.argv[1:]
    for n in names:
        run_scenario(n)
