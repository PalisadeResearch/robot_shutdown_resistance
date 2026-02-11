from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .config import Settings


@dataclass
class Env:
    """
    Data here will *not* be a part of a run history.
    """

    settings: Settings
    run_path: Path
    # TODO: add handles and capabilities here
    readme: str = "example"


class Metadata(BaseModel):
    """
    Run metadata to be stored alongside snapshots.
    Can be used to persist extra information outside of graph state or parameters needed to replicate the environment when restoring.
    """

    # Git commit that produced the code and config for this run
    commit_hash: str

    # Parsed CLI args used to start this run
    args: dict[str, Any]

    # Current run_id (should match the directory name)
    run_id: str

    # A chain of run_ids that were used in restoring
    # (empty = fresh run)
    ancestor_ids: list[str] = Field(default_factory=list)

    # TODO: add more things to preseve and track across runs
