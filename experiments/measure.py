"""Turn the event log into numbers: how much work was repeated after a crash?

Usage: python -m experiments.measure <run_id>
"""

import json
import sys
from collections import Counter

from common.review import EVENTS_FILE, OUTPUT_DIR, list_files


def load_events(run_id):
    if not EVENTS_FILE.exists():
        return []
    with open(EVENTS_FILE) as f:
        return [e for e in map(json.loads, f) if e["run_id"] == run_id]


def summarize(run_id, crash_ts=None):
    events = load_events(run_id)
    starts = Counter(e["file"] for e in events if e["event"] == "review_start")
    dones = Counter(e["file"] for e in events if e["event"] == "review_done")
    reports = [e for e in events if e["event"] == "report_written"]
    n_files = len(list_files())

    naive_lines = 0
    if (OUTPUT_DIR / "reports_naive.jsonl").exists():
        with open(OUTPUT_DIR / "reports_naive.jsonl") as f:
            naive_lines = sum(json.loads(line)["run_id"] == run_id for line in f)
    report_file = OUTPUT_DIR / f"report_{run_id}.json"
    finding_count = json.loads(report_file.read_text())["finding_count"] if report_file.exists() else None

    after = [e["ts"] for e in events if crash_ts and e["ts"] > crash_ts]
    return {
        "run_id": run_id,
        # every review start beyond the first per file = repeated work
        "reviews_started": sum(starts.values()),
        "reviews_redone": sum(starts.values()) - n_files,
        # reviews that had FINISHED before the crash but were thrown away and done again
        "finished_reviews_lost": sum(max(0, c - 1) for c in dones.values()),
        "processes": len({e["pid"] for e in events}),
        "recovery_gap_s": round(min(after) - crash_ts, 1) if after else None,
        "wall_s": round(reports[-1]["ts"] - events[0]["ts"], 1) if reports else None,
        "report_writes": len(reports),
        "naive_report_lines": naive_lines,
        "finding_count": finding_count,
    }


if __name__ == "__main__":
    print(json.dumps(summarize(sys.argv[1]), indent=2))
