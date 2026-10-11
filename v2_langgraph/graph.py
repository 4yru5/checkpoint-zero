"""Version 2: the review job as a LangGraph graph, optionally saved to SQLite.

Flags let us replay each stage of the project:
  --checkpointer none|sqlite   stage 2 (no saving) vs stage 3 (save after every node)
  --granularity  big|per-file  stage 4: one node reviews ALL files, or one node run per file
  --report       naive|atomic  stage 5: appending report (duplicates) vs atomic rename

Resuming is manual: run the SAME command again with the SAME --run-id (= thread_id).
"""

import argparse
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from common.review import (OUTPUT_DIR, build_report, list_files, log_event, review_file,
                           write_report_atomic, write_report_naive)


class State(TypedDict, total=False):
    """The 'clipboard' passed between nodes. With a checkpointer, it's saved after each node."""
    run_id: str
    version: str
    files: list[str]
    index: int        # per-file mode: which file to review next
    findings: list[dict]
    report_path: str


def build_graph(granularity, report_mode):
    write = write_report_atomic if report_mode == "atomic" else write_report_naive

    def list_node(state):
        return {"files": list_files(), "index": 0, "findings": []}

    def review_all_node(state):
        # ONE node does all 5 reviews. A checkpoint only happens when the node RETURNS,
        # so a crash halfway through loses every review done inside this node.
        found = []
        for name in state["files"]:
            found += review_file(state["version"], state["run_id"], name)
        return {"findings": found}

    def review_one_node(state):
        # One file per node run. After each return, LangGraph saves a checkpoint,
        # so a crash loses at most the ONE file in progress.
        name = state["files"][state["index"]]
        found = review_file(state["version"], state["run_id"], name)
        return {"findings": state["findings"] + found, "index": state["index"] + 1}

    def more_files(state):
        return "review_one" if state["index"] < len(state["files"]) else "write_report"

    def report_node(state):
        report = build_report(state["version"], state["run_id"], state["findings"])
        return {"report_path": write(report)}

    g = StateGraph(State)
    g.add_node("list_files", list_node)
    g.add_node("write_report", report_node)
    g.add_edge(START, "list_files")
    if granularity == "big":
        g.add_node("review_all", review_all_node)
        g.add_edge("list_files", "review_all")
        g.add_edge("review_all", "write_report")
    else:
        g.add_node("review_one", review_one_node)
        # loop: review_one -> review_one -> ... The list names the possible next nodes,
        # so LangGraph can draw (and check) the graph before it runs.
        g.add_conditional_edges("list_files", more_files, ["review_one", "write_report"])
        g.add_conditional_edges("review_one", more_files, ["review_one", "write_report"])
    g.add_edge("write_report", END)
    return g


def run(graph, run_id, version):
    config = {"configurable": {"thread_id": run_id}}  # thread_id = the name of this run's save slot
    saved = graph.get_state(config) if graph.checkpointer else None
    if saved and saved.next:
        print(f"♻️  checkpoint found for {run_id}: resuming at {saved.next}", flush=True)
        result = graph.invoke(None, config)  # None = "don't restart, continue from the save"
    elif saved and saved.values:
        print(f"✅ {run_id} already finished: nothing to do", flush=True)
        result = saved.values  # empty `next` + saved values = the graph reached END
    else:
        print(f"▶️  no checkpoint for {run_id}: starting fresh", flush=True)
        result = graph.invoke({"run_id": run_id, "version": version}, config)
    print(f"done: {len(result['findings'])} findings -> {result['report_path']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default="v2-demo")
    p.add_argument("--checkpointer", choices=["none", "sqlite"], default="sqlite")
    p.add_argument("--granularity", choices=["big", "per-file"], default="per-file")
    p.add_argument("--report", choices=["naive", "atomic"], default="atomic")
    a = p.parse_args()
    version = f"v2-langgraph-{a.checkpointer}-{a.granularity}-{a.report}"
    log_event(version, a.run_id, "process_start")
    g = build_graph(a.granularity, a.report)

    if a.checkpointer == "none":
        run(g.compile(), a.run_id, version)
    else:
        OUTPUT_DIR.mkdir(exist_ok=True)
        with SqliteSaver.from_conn_string(str(OUTPUT_DIR / "langgraph_checkpoints.sqlite")) as saver:
            run(g.compile(checkpointer=saver), a.run_id, version)


if __name__ == "__main__":
    main()
