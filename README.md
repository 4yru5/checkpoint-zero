# checkpoint-zero

A benchmark that runs the **same security review job** three ways, crashes each one
on purpose with `kill -9`, and measures how much work each loses.

| # | Version | Saves progress? | Who resumes after a crash? |
|---|---|---|---|
| 1 | Plain Python script | No | Nobody: starts over |
| 2 | LangGraph + SQLite checkpoints | After every node | You (re-run with the same `thread_id`) |
| 3 | Temporal | After every activity | The Temporal server, automatically |

## Headline results ([full table](EXPERIMENTS.md))

Killed halfway through file 3 of 5 (3 s per file):

| Version | Finished reviews thrown away | Recovery |
|---|---|---|
| Plain script | 2 | manual, from scratch |
| LangGraph, one big node | 2 | manual, but the save point was *before* the big node |
| LangGraph, node per file | **0** | manual, from the last finished file |
| Temporal, no heartbeat | **0** | automatic after 19.5 s (start-to-close timeout) |
| Temporal, 2 s heartbeat | **0** | automatic after **2.0 s** |

And a crash right after writing the report: an *appending* writer produced a **duplicate**;
the *atomic, run-id-keyed* writer did not.

## The job

```mermaid
flowchart LR
    A[list files<br/>target_repo/*.py] --> B[review each file<br/>3 regex rules + 3 s 'LLM' sleep]
    B --> C[write JSON report<br/>expected: 3 findings]
```

`target_repo/` contains deliberately vulnerable code (`eval`, `shell=True`) and a **FAKE** key.
It is only read as text, never executed.

## How each version recovers

```mermaid
sequenceDiagram
    participant J as Job process
    participant S as Saved state
    Note over J: v1 plain script
    J->>J: review 1, 2, 3… 💥 kill -9
    J->>J: (re-run) review 1, 2, 3, 4, 5. Everything again.

    Note over J,S: v2 LangGraph + SqliteSaver (node per file)
    J->>S: checkpoint after file 1
    J->>S: checkpoint after file 2
    J->>J: file 3… 💥 kill -9
    S->>J: (YOU re-run, same thread_id) resume at file 3
```

```mermaid
sequenceDiagram
    participant C as Starter (client)
    participant T as Temporal server (history)
    participant A as Worker A
    participant B as Worker B
    C->>T: start ReviewWorkflow(run_id)
    T->>A: review app.py, config.py ✔ (recorded in history)
    T->>A: review helpers.py
    A--xA: 💥 kill -9
    Note over T: heartbeats stop → after heartbeat_timeout,<br/>schedule retry (attempt 2)
    B->>T: poll for work (just a fresh worker, no resume command)
    T->>B: helpers.py (attempt 2), models.py, utils.py, write report
    T->>C: result: 3 findings
```

## Layout

```
common/review.py        shared job logic + event log + crash hook (same code for every version)
v1_plain/run.py         version 1
v2_langgraph/graph.py   version 2  (--checkpointer none|sqlite, --granularity big|per-file, --report naive|atomic)
v3_temporal/            version 3  (activities.py, workflow.py, worker.py, start.py)
experiments/            crash_test.py (scenarios), measure.py (counts lost work), export_timeline.py (data for the visual replay)
target_repo/            the 5 fixture files being reviewed
```

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# v1 / v2: just run (re-run the same command + --run-id to resume v2)
.venv/bin/python -m v1_plain.run --run-id demo1
.venv/bin/python -m v2_langgraph.graph --run-id demo2

# v3: three terminals
temporal server start-dev                         # 1. server (UI at http://localhost:8233)
.venv/bin/python -m v3_temporal.worker            # 2. worker
.venv/bin/python -m v3_temporal.start --run-id demo3 --heartbeat 2   # 3. start + wait

# all crash experiments (needs the Temporal server running)
.venv/bin/python -m experiments.crash_test all
```

Set `REVIEW_DELAY=0.2` for fast runs. Outputs go to `output/` (git-ignored).

See also: [EXPERIMENTS.md](EXPERIMENTS.md) (numbers), [THINKING.md](THINKING.md) (hypotheses and design),
[LEARNING.md](LEARNING.md) (step-by-step notes), [GLOSSARY.md](GLOSSARY.md).
