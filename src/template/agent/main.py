from __future__ import annotations

import argparse
import asyncio
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from shutil import copytree

import logfire
from ipdb import launch_ipdb_on_exception
from pydantic_graph import End, Graph
from pydantic_graph.persistence.file import FileStatePersistence

from ..utils import git
from . import nodes
from .config import Settings
from .env import Env, Metadata
from .state import State


def main():
    """
    Squeeze the external world and distill into the Env fields.
    """
    parser = argparse.ArgumentParser(description="Run me")
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Do not track git state, check branch names and commit/push.",
    )
    parser.add_argument(
        "--no-logfire", action="store_true", help="Run with only local logging."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Drop to a debugger on unhandled exceptions.",
    )
    parser.add_argument(
        "--restore",
        metavar="DIR",
        help="A path of a previous run to resume/fork. A new run id will be generated.",
    )
    configs = []
    for path in Path("config").glob("*.yaml"):
        configs.append(path.name.split(".yaml")[0])
    parser.add_argument("config", choices=configs, help="Config name to use.")

    # TODO: add more args for controlling the script itself
    args = parser.parse_args()
    settings = Settings(config_name=args.config)

    if not args.no_git:
        git.ensure_experiment_branch()

    logfire.configure(
        send_to_logfire=not args.no_logfire,
        scrubbing=False,
    )
    logfire.instrument_openai()
    # TODO: instrument other model providers and APIs
    # https://ai.pydantic.dev/#instrumentation-with-pydantic-logfire

    branch_name = git.current_branch() or "unknown"
    commit_hash = git.current_commit() or "unknown"
    run_name = f"run-{branch_name}-{commit_hash[:8]}"
    run_attrs = {
        # TODO: add LogFire run metadata here
    }
    if url := git.github_commit_link(commit_hash):
        run_attrs["github_commit_link"] = url

    with (
        logfire.span(run_name, _span_name="main", **run_attrs) as root,
        (launch_ipdb_on_exception if args.debug else nullcontext)(),
    ):
        # Your unique identifier for this run (the series of steps tracked as one closed block).
        # NB: Restored/forked runs will get a fresh one too.
        run_id = f"{root.context.trace_id:032x}"

        if not args.no_git:
            with logfire.span("Preparing git commit", _level="debug"):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                commit_msg = f"run-{timestamp}-{run_id}"
                git.commit_and_push(commit_msg)

        # New runs appear on the bottom, automatically "sorted" by timestamp
        run_path = Path("runs") / Path(run_id)
        run_path.mkdir(exist_ok=True, parents=True)
        logfire.notice(f"Run path: {run_path}")

        old_meta: Metadata | None = None
        if args.restore:
            with logfire.span(f"Restoring from {args.restore}"):
                old_path = Path(args.restore)
                if not old_path.exists():
                    raise Exception(f"Restore path does not exist: {args.restore}")
                if not old_path.is_dir():
                    raise Exception(f"Restore path is not a directory: {args.restore}")
                old_meta_path = old_path / Path("metadata.json")
                with old_meta_path.open() as f:
                    old_meta = Metadata.model_validate_json(f.read())
                # XXX: blindly copying the old run path (containing the history file)
                # While this is enough to recover graph state, you may have to write some metadata file
                # to record external resources used like docker image IDs, IPs
                copytree(src=old_path, dst=run_path, dirs_exist_ok=True)

        # This sets a "resource scope" for the run
        # Things created here would be closed/finalized/cleaned on exit.
        # A context manager can be asked to restore the environment to match what the agent previously had.
        with (
            nullcontext(),  # Placeholder
            # TODO: Start the requested services
        ):
            deps = Env(
                settings=settings,
                run_path=run_path,
                # TODO: Put service handles here
            )

            if old_meta:
                ancestor_ids: list[str] = old_meta.ancestor_ids + [old_meta.run_id]
                # TODO: Carry over more information from the previous run
            else:
                ancestor_ids = []
            new_meta = Metadata(
                commit_hash=commit_hash,
                args=args.__dict__,
                run_id=run_id,
                ancestor_ids=ancestor_ids,
                # TODO: Register more env-related metadata here
            )
            new_meta_path = run_path / Path("metadata.json")
            with new_meta_path.open("w") as f:
                f.write(new_meta.model_dump_json(indent=2))

            asyncio.run(agent(deps))


async def agent(deps: Env):
    """
    Prepare and drive the agent loop inside the provided environment.
    """
    # Instantiate the graph
    graph = Graph[State, Env](nodes=nodes.all_nodes)
    start = nodes.Step

    # TODO: You can put more graph-related setup here
    with open(deps.run_path / Path("schema.mmd"), "w") as f:
        f.write(graph.mermaid_code(start_node=start))

    # Initialize the instance
    history_path = deps.run_path / Path("history.json")
    persistence = FileStatePersistence(history_path)
    persistence.set_graph_types(graph)
    if snapshots := await persistence.load_all():
        node, state = restore_snapshot(snapshots, history_path)
    else:
        node = start()
        state = State()
    await graph.initialize(
        node=node,
        state=state,
        persistence=persistence,
    )

    # Hard limit for steps in this run (i.e. without considering snapshot history from the restored runs)
    steps_remaining = deps.settings.agent.MAX_STEPS

    # Run the graph to completion
    while True:
        async with graph.iter_from_persistence(persistence, deps=deps) as running:
            next = await running.next()
            # TODO: add top-level processing related to the running instance
            logfire.debug(f"Running state: {running.state}")

            if isinstance(next, End):
                break
            # TODO: check the extra termination conditions
            steps_remaining -= 1
            if not steps_remaining:
                break

        pass  # State snapshot is taken here and recorded in the file


def restore_snapshot(snapshots: list, history_path: Path):
    # TODO: add snapshot filtering like "drop N last steps"
    node = None
    state: State | None = None
    logfire.debug(f"Loaded {len(snapshots)} snapshots from {history_path}")
    for snapshot in reversed(snapshots):
        if snapshot.kind == "end":
            logfire.debug("Resuming an ended run")
            continue
        if snapshot.kind == "node":
            node = snapshot.node
            if isinstance(node, End):
                logfire.debug(f"Skipping End node {snapshot.id}")
                continue
            logfire.debug(f"Restoring from snapshot {snapshot.id}")
            state = snapshot.state
            break
    if node is None or state is None:
        raise RuntimeError(
            f"No viable snapshots in the persistence file {history_path}"
        )
    return node, state


if __name__ == "__main__":
    main()
