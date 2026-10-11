"""Temporal activities: the steps that touch the outside world (files, sleep, report).

Activities can fail and be retried; Temporal records each finished one in the
workflow's history, so a finished activity is never run again after a crash.
"""

from temporalio import activity

from common import review

VERSION = "v3-temporal"


@activity.defn
def list_files_activity() -> list[str]:
    return review.list_files()


@activity.defn
def review_file_activity(run_id: str, name: str) -> list[dict]:
    attempt = activity.info().attempt  # 1 on the first try, 2+ on retries
    # Heartbeat = "I'm still alive" ping to the server. If the pings stop (worker
    # killed), the server notices after heartbeat_timeout and retries elsewhere.
    return review.review_file(VERSION, run_id, name, tick=activity.heartbeat, attempt=attempt)


@activity.defn
def write_report_activity(run_id: str, findings: list[dict]) -> str:
    return review.write_report_atomic(review.build_report(VERSION, run_id, findings))
