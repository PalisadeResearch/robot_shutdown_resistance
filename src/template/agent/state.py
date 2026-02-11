from __future__ import annotations

from dataclasses import dataclass


@dataclass
class State:
    """
    Data here will be snapshotted at each step and stored in the run history file.
    """

    changeme: int = 0

    # TODO: add "slots" for mutable data here
