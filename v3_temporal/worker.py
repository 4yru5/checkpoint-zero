"""The worker: a process that pulls tasks from the Temporal server and runs our code.

Kill it with kill -9 and the server still has the history. Start a new worker and
the workflow continues where it left off, with no "resume" command needed.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from common.review import log_event
from v3_temporal.activities import list_files_activity, review_file_activity, write_report_activity
from v3_temporal.workflow import TASK_QUEUE, ReviewWorkflow


async def main():
    client = await Client.connect("localhost:7233")
    log_event("v3-temporal", "-", "worker_start")
    print("worker running; Ctrl+C or kill to stop", flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:  # our activities are normal (sync) functions
        worker = Worker(client, task_queue=TASK_QUEUE, workflows=[ReviewWorkflow],
                        activities=[list_files_activity, review_file_activity, write_report_activity],
                        activity_executor=pool)
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
