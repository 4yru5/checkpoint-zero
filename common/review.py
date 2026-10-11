"""The review job's building blocks, shared by all three versions.

Every version calls these same functions, so the ONLY difference between
versions is how they save progress and recover from a crash.
"""

import json
import os
import re
import signal
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIR = ROOT / "target_repo"
OUTPUT_DIR = ROOT / "output"
EVENTS_FILE = OUTPUT_DIR / "events.jsonl"

# How long each file review "thinks". Stands in for a slow LLM call.
REVIEW_DELAY = float(os.environ.get("REVIEW_DELAY", "3"))

RULES = {
    "code-injection-eval": re.compile(r"\beval\s*\("),
    "command-injection-shell-true": re.compile(r"\bshell\s*=\s*True\b"),
    # A variable whose name contains key/secret/token/password, set to a string literal of 8+ chars.
    "hardcoded-secret": re.compile(
        r"""(?i)\b\w*(key|secret|token|password)\w*\s*=\s*["'][^"']{8,}["']"""
    ),
}


def log_event(version, run_id, event, **extra):
    """Append one line to the event log. Experiments count these lines to measure lost work."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    record = {"ts": time.time(), "version": version, "run_id": run_id,
              "event": event, "pid": os.getpid(), **extra}
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def maybe_crash(point):
    """Crash-injection hook: if CRASH_AT names this point, kill our own process with SIGKILL.

    SIGKILL is the same signal `kill -9` sends: no cleanup, no goodbye, instant death.
    """
    if os.environ.get("CRASH_AT") == point:
        print(f"💥 CRASH_AT={point}: killing myself with SIGKILL", flush=True)
        os.kill(os.getpid(), signal.SIGKILL)


def list_files():
    return sorted(p.name for p in TARGET_DIR.glob("*.py"))


def review_file(version, run_id, name, tick=None, **extra):
    """Scan one file with the regex rules, then 'think' for REVIEW_DELAY seconds.

    `tick` is called every 0.5 s while thinking. Temporal uses it to send heartbeats.
    """
    log_event(version, run_id, "review_start", file=name, **extra)
    findings = []
    for lineno, line in enumerate((TARGET_DIR / name).read_text().splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue  # skip comment lines, otherwise the fixture's own warnings are false positives
        for rule, pattern in RULES.items():
            if pattern.search(line):
                findings.append({"file": name, "line": lineno, "rule": rule, "code": line.strip()})

    deadline = time.time() + REVIEW_DELAY  # the fake "LLM call"
    while time.time() < deadline:
        time.sleep(min(0.5, deadline - time.time()))
        if tick:
            tick()

    log_event(version, run_id, "review_done", file=name, findings=len(findings), **extra)
    return findings


def build_report(version, run_id, findings):
    findings = sorted(findings, key=lambda f: (f["file"], f["line"]))
    return {"run_id": run_id, "version": version,
            "finding_count": len(findings), "findings": findings}


def write_report_naive(report):
    """NOT idempotent: appends a line every time it runs. If the step repeats, so does the line."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "reports_naive.jsonl", "a") as f:
        f.write(json.dumps(report) + "\n")
    log_event(report["version"], report["run_id"], "report_written", mode="naive")
    maybe_crash("after_report_write")  # stage 5: die AFTER the side effect, BEFORE the checkpoint
    return str(OUTPUT_DIR / "reports_naive.jsonl")


def write_report_atomic(report):
    """Idempotent: one file per run id, written to a temp file, then renamed into place.

    Rename (os.replace) is atomic: readers see the old file or the new file, never half
    of one. Running it twice just overwrites the same file with the same content.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    final = OUTPUT_DIR / f"report_{report['run_id']}.json"
    tmp = final.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(report, f, indent=2)
        f.flush()
        os.fsync(f.fileno())  # make sure the bytes are on disk before the rename
    os.replace(tmp, final)
    log_event(report["version"], report["run_id"], "report_written", mode="atomic")
    maybe_crash("after_report_write")
    return str(final)
