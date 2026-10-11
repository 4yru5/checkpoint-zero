"""Ask the Temporal server to start a review workflow, then wait for its result.

This is just a client; it does no work itself. It keeps waiting even if every
worker dies, because the workflow lives on the server, not in any one process.
Usage: python -m v3_temporal.start --run-id demo [--heartbeat 2] [--start-to-close 30]
"""

import argparse
import asyncio

from temporalio.client import Client

from v3_temporal.workflow import TASK_QUEUE, ReviewInput, ReviewWorkflow


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default="v3-demo")
    p.add_argument("--start-to-close", type=float, default=30)
    p.add_argument("--heartbeat", type=float, default=0)
    a = p.parse_args()

    client = await Client.connect("localhost:7233")
    result = await client.execute_workflow(  # workflow id = run id, so it's unique per run
        ReviewWorkflow.run, ReviewInput(a.run_id, a.start_to_close, a.heartbeat),
        id=a.run_id, task_queue=TASK_QUEUE)
    print(f"done: {result['finding_count']} findings -> {result['report_path']}")


if __name__ == "__main__":
    asyncio.run(main())
