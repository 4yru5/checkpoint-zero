"""Turn the latest crash-test results into timeline data for the visual replay page.

Each review becomes a bar with a status:
  first        - the first finished review of that file (useful work)
  interrupted  - started, then the process was killed mid-way
  retry        - redoing a review that was interrupted (unavoidable)
  redo         - redoing a review that had ALREADY FINISHED (pure waste)
Usage: python -m experiments.export_timeline > timeline.json
"""

import json

from common.review import OUTPUT_DIR
from experiments.measure import load_events


def latest_results():
    """Last result per scenario, in the order they first appear."""
    out = {}
    with open(OUTPUT_DIR / "results.jsonl") as f:
        for line in f:
            r = json.loads(line)
            out[r["scenario"]] = r
    return list(out.values())


def timeline(result):
    events = [e for e in load_events(result["run_id"]) if e["event"] != "process_start"]
    t0 = events[0]["ts"]
    pids = list(dict.fromkeys(e["pid"] for e in events))  # first process = lane 0, next = lane 1
    if "crash_ts" in result:
        crash = result["crash_ts"] - t0
    else:  # older results: crash = first sign of the new process, minus the measured gap
        first_after = min(e["ts"] for e in events if e["pid"] != pids[0])
        crash = first_after - result["recovery_gap_s"] - t0

    bars, open_starts, finished = [], {}, set()
    for e in events:
        t, lane, f = round(e["ts"] - t0, 2), pids.index(e["pid"]), e.get("file")
        if e["event"] == "review_start":
            if f in finished:
                status = "redo"
            elif f in open_starts:  # an earlier attempt never finished: close it as interrupted
                bars.append({**open_starts.pop(f), "end": round(crash, 2), "status": "interrupted"})
                status = "retry"
            else:
                status = "first"
            open_starts[f] ={"file": f, "lane": lane, "start": t, "status": status, "attempt": e.get("attempt")}
        elif e["event"] == "review_done":
            bar = open_starts.pop(f)
            bars.append({**bar, "end": t})
            finished.add(f)
    for bar in open_starts.values():  # never finished: the crash cut it off
        bars.append({**bar, "end": round(crash, 2), "status": "interrupted"})

    reports = [{"t": round(e["ts"] - t0, 2), "lane": pids.index(e["pid"]), "mode": e.get("mode")}
               for e in events if e["event"] == "report_written"]
    keep = ["scenario", "reviews_redone", "finished_reviews_lost", "recovery_gap_s",
            "wall_s", "report_writes", "naive_report_lines", "finding_count", "run_id"]
    return {**{k: result[k] for k in keep}, "crash": round(crash, 2),
            "bars": sorted(bars, key=lambda b: b["start"]), "reports": reports}


if __name__ == "__main__":
    print(json.dumps([timeline(r) for r in latest_results()], indent=1))
