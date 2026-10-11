"""Temporal workflow: the ORDER of steps. Temporal saves every step's result in history.

Workflow code must be deterministic (same input -> same steps), because after a crash
Temporal re-runs this function and fast-forwards through steps already in history.
"""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():  # activities do I/O; skip the sandbox for them
    from v3_temporal.activities import (list_files_activity, review_file_activity,
                                        write_report_activity)

TASK_QUEUE = "checkpoint-zero"


@dataclass
class ReviewInput:
    run_id: str
    start_to_close_s: float = 30  # max time ONE attempt of a review may take
    heartbeat_s: float = 0        # 0 = no heartbeat timeout


@workflow.defn
class ReviewWorkflow:
    @workflow.run
    async def run(self, inp: ReviewInput) -> dict:
        quick = timedelta(seconds=10)
        retry = RetryPolicy(initial_interval=timedelta(seconds=1), maximum_attempts=5)
        files = await workflow.execute_activity(list_files_activity, start_to_close_timeout=quick)

        findings = []
        for name in files:
            findings += await workflow.execute_activity(
                review_file_activity, args=[inp.run_id, name],
                start_to_close_timeout=timedelta(seconds=inp.start_to_close_s),
                heartbeat_timeout=timedelta(seconds=inp.heartbeat_s) if inp.heartbeat_s else None,
                retry_policy=retry,
            )

        path = await workflow.execute_activity(
            write_report_activity, args=[inp.run_id, findings],
            start_to_close_timeout=quick, retry_policy=retry)
        return {"finding_count": len(findings), "report_path": path}
