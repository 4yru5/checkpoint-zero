# Thinking

Hypotheses written *before* running experiments, and the decisions behind the design.

## Hypotheses (and what happened)

| # | Hypothesis (before) | Result (after) |
|---|---|---|
| H1 | The plain script loses the most work: it saves nothing, so a crash loses every finished review. | ✅ Lost 2 finished reviews. Tied with LangGraph-no-checkpointer and LangGraph-one-big-node. |
| H2 | Adding a checkpointer alone fixes lost work. | ❌ Not with one big node: the save happens only when a node returns. Granularity matters as much as the checkpointer. |
| H3 | Checkpointing after every step means each step runs exactly once. | ❌ A crash between "side effect done" and "checkpoint saved" re-runs the step. You get *at-least-once*, not *exactly-once*. |
| H4 | Temporal resumes almost instantly after a worker dies. | ⚠️ Only with heartbeats. Without, it waited for the 20 s start-to-close timeout. Also hit a ~10 s sticky-queue pause. |

## Design decisions

- **Shared job code (`common/review.py`).** All three versions call the same functions, so differences
  in results come from the recovery mechanism only.
- **Fake LLM (`time.sleep`, default 3 s via `REVIEW_DELAY`).** No API key or cost, and each step is slow
  enough to crash mid-way. Set `REVIEW_DELAY=0.2` for quick smoke runs.
- **Fixed answer (3 findings).** Lost or duplicated work shows up as a wrong count or a duplicate report.
- **Event log (`output/events.jsonl`) instead of eyeballing.** Every review start/finish is logged with a
  pid and timestamp, so "lost work" is counted, not guessed.
- **Deterministic crashes.** The harness waits for the 2nd finished review and kills halfway through the
  3rd, instead of "kill after N seconds" (startup time varies, especially for Temporal).
  `CRASH_AT=after_report_write` hits the narrow window between side effect and checkpoint.
- **Scanner skips comment lines.** The fixtures' own warning comments mention `eval(` and `shell=True`;
  a naive grep reports 5 hits (2 false positives). Limitation: code followed by a trailing
  `# comment` is still scanned, which is fine for these fixtures.
- **Report: temp file + `os.replace`, one file per run id.** `os.replace` is atomic on POSIX: readers see
  the old or the new file, never half a file. Same content rewritten = no harm (idempotent).
- **Temporal activities are sync functions in a thread pool.** Simple to read, and `activity.heartbeat`
  is called from the review's 0.5 s "thinking" ticks.

## The sticky-queue surprise (row 8 of EXPERIMENTS.md)

```
 6.0s  helpers.py attempt 1 starts   (worker A)
 7.5s  worker A killed (kill -9)
 9.6s  helpers.py attempt 2 starts   (worker B)   ← heartbeat timeout caught it in ~2 s
12.6s  helpers.py done
22.6s  models.py starts                            ← 10 s of nothing
```
Workers cache running workflows and ask the server to route that workflow's next task to their own
"sticky" queue. Worker A is dead, so the task waited out the sticky schedule-to-start timeout
before falling back to the shared queue that worker B polls. Options: a shorter
`sticky_queue_schedule_to_start_timeout` on the Worker, or graceful shutdown (which releases
stickiness). A real `kill -9` can't shut down gracefully.

## Open questions / next ideas
- Repeat each scenario N times and report mean ± spread (timing currently from single runs).
- Crash the Temporal *server* (not the worker) with a persistent DB (`--db-filename`).
- LangGraph: auto-resume with a supervisor (systemd / a cron loop) to close the "human gap".

**Confirmed (run 2):** `temporal workflow show` lists event 26 `WORKFLOW_TASK_SCHEDULED` at 12.6 s and
event 27 `WORKFLOW_TASK_TIMED_OUT` (timeout type `SCHEDULE_TO_START`) at 22.6 s: the sticky task
waited exactly 10 s for dead worker A, then was rescheduled for worker B. A second full run reproduced
every result in EXPERIMENTS.md to within 0.2 s.
