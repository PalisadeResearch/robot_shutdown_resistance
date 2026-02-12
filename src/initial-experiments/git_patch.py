import os

import inspect_ai._eval.task.log
from inspect_ai._util import git


def patched_git_context() -> git.GitContext | None:
    origin = os.getenv("INSPECT_GIT_ORIGIN")
    commit = os.getenv("INSPECT_GIT_COMMIT")

    if origin and commit:
        return git.GitContext(origin=origin, commit=commit, dirty=False)

    return git.git_context()


inspect_ai._eval.task.log.git_context = patched_git_context  # type: ignore
