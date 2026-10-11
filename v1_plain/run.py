"""Version 1: a plain Python script. Nothing is saved while it runs.

If it crashes, re-running it starts from file #1 again: all finished reviews are lost.
Usage: python -m v1_plain.run --run-id demo
"""

import argparse

from common.review import build_report, list_files, log_event, review_file, write_report_atomic

VERSION = "v1-plain"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default="v1-demo")
    run_id = parser.parse_args().run_id

    log_event(VERSION, run_id, "process_start")
    findings = []  # lives only in RAM: a crash wipes it
    for name in list_files():
        print(f"reviewing {name} ...", flush=True)
        findings += review_file(VERSION, run_id, name)

    path = write_report_atomic(build_report(VERSION, run_id, findings))
    print(f"done: {len(findings)} findings -> {path}")


if __name__ == "__main__":
    main()
