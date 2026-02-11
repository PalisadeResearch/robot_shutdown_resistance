from __future__ import annotations

from dataclasses import dataclass

import logfire
from pydantic_graph import BaseNode, End

from .env import Env
from .state import State

## Agent's FSM nodes


@dataclass
class Step(BaseNode[State, Env, None]):  # Using State and Env...
    async def run(
        self, ctx
    ) -> Step | End:  # ... do stuff and switch to either Step or End.
        # Mutate the state (persisted in the history file)
        ctx.state.changeme += 1

        # Render some text
        logfire.notice(f"{ctx.state.changeme}: {ctx.deps.readme}")

        # Decide what to do next
        if ctx.state.changeme < 5:
            return Step()
        else:
            return End(data=None)


# TODO: Add more nodes...

all_nodes = (Step,)  # ... and register them all here
