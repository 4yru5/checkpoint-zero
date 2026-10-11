# Experiments

All runs: 5 files, `REVIEW_DELAY=3` s per file (ideal job time ≈ 15 s), Python 3.14,
langgraph 1.2.14, temporalio 1.34.0, Temporal dev server 1.32. Correct answer: 3 findings.

Reproduce: `temporal server start-dev` in one terminal, then
`.venv/bin/python -m experiments.crash_test all`. Raw numbers go to `output/results.jsonl`.

**Crash method.** "kill -9 mid-review" = wait for 2 finished reviews, then `SIGKILL` halfway through
review #3 (`helpers.py`). "self-kill after report" = the process `SIGKILL`s itself right after
writing the report, before the step is recorded as done (`CRASH_AT=after_report_write`).

## Results

| # | Scenario | Crash | Reviews redone | Finished reviews thrown away | Recovery gap (s) | Total time (s) | Report writes | Correct report? |
|---|---|---|---|---|---|---|---|---|
| 1 | v1 plain script | kill -9 mid-review | 3 | 2 | 0.1* | 22.7 | 1 | ✅ 3 findings |
| 2 | v2 LangGraph, no checkpointer | kill -9 mid-review | 3 | 2 | 0.4* | 23.1 | 1 | ✅ 3 findings |
| 3 | v2 LangGraph + SQLite, one big node | kill -9 mid-review | 3 | 2 | 0.4* | 23.0 | 1 | ✅ 3 findings |
| 4 | v2 LangGraph + SQLite, node per file | kill -9 mid-review | **1** | **0** | 0.3* | **16.8** | 1 | ✅ 3 findings |
| 5 | v2 per file, **naive** (append) report | self-kill after report | 0 | 0 | 0.4* | 15.4 | 2 | ❌ **duplicate** report line |
| 6 | v2 per file, **atomic** report | self-kill after report | 0 | 0 | 0.4* | 15.4 | 2 | ✅ one file, 3 findings |
| 7 | v3 Temporal, no heartbeat (start-to-close 20 s) | kill -9 worker mid-review | 1 | 0 | **19.5** | 36.2 | 1 | ✅ 3 findings |
| 8 | v3 Temporal, heartbeat 2 s | kill -9 worker mid-review | 1 | 0 | **2.0** | 28.7 | 1 | ✅ 3 findings |
| 9 | v3 Temporal, report crash | self-kill after report | 0 | 0 | 11.0 | 26.1 | 2 | ✅ one file, 3 findings |

\* For v1/v2 the harness resumes **instantly by hand**. In real life the gap is "however long until a
human notices and re-runs the command": minutes or hours. Temporal's gap is automatic.

**Column meanings**
- *Reviews redone*: review starts beyond one per file. Includes the review that was interrupted, which every version must redo.
- *Finished reviews thrown away*: reviews that had **completed** before the crash but were done again. This is pure waste.
- *Recovery gap*: crash → first sign of work resuming.

## What the numbers say

1. **No saving = start over.** v1, LangGraph without a checkpointer, and LangGraph with **one big node**
   all lost the same 2 finished reviews (+7 s). A checkpointer only saves *between* nodes, so a node
   that does all the work is as fragile as no checkpointer at all (rows 3 vs 4).
2. **Granularity is the real fix.** One node per file → only the in-flight review is redone (row 4).
   Worst-case loss = the size of one step.
3. **Saving after a step ≠ the step running once.** The crash came *after* the report was written
   but *before* LangGraph saved that the node finished, so the node ran twice (rows 5–6, *Report writes* = 2).
   Appending made a duplicate. Temp-file + rename keyed by run id made the repeat harmless.
   Temporal behaves the same way (row 9): activities are retried, so they must be idempotent.
4. **Temporal recovers by itself, but only as fast as its timeouts.** With no heartbeat, the server
   couldn't tell the worker was dead until `start_to_close` (20 s) expired. A 2 s heartbeat cut the
   detection time 10× (rows 7 vs 8).
5. **Surprise: the sticky-queue pause.** In row 8, after the retried review finished, the workflow
   sat idle ~10 s. The dead worker had the workflow cached ("sticky"), so the server first offered
   the next step to that dead worker and waited out the sticky timeout. **Confirmed** by Temporal's history:
   event 27 is `WORKFLOW_TASK_TIMED_OUT (SCHEDULE_TO_START)`, exactly 10 s after event 26 scheduled it.
   Only then did the step go to the new worker. The full timeline is in THINKING.md.
