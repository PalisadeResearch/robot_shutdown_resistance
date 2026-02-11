#!/usr/bin/env python3

"""fork_worktree: utility script to create one or many git worktree forks.

Usage:
    fork-worktree [--prefix PREFIX] [--path PATH] [--names NAME1 NAME2 ...] [-r N]

Examples:
    # Create one worktree from current branch
    fork-worktree

    # Create three worktrees with custom names (no need for -r)
    fork-worktree --names feature-a feature-b feature-c

    # Create 5 worktrees based on one name (auto-names 4 additional ones)
    fork-worktree -r 5 --names feature-a

    # Custom prefix and base path
    fork-worktree --prefix custom-exp --path /tmp --names my-experiment
"""

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import argcomplete

from ._fork_worktree_parser import build_parser

REPO_ROOT = Path.cwd()


def sh(args: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a shell command, echoing it. Abort on error."""
    args_ = [str(a) for a in args]
    print("$", " ".join(args_))
    return subprocess.run(args_, check=True, **kwargs)


def ensure_git_repo() -> None:
    if not (REPO_ROOT / ".git").exists():
        print("Error: current directory is not a git repository root.", file=sys.stderr)
        sys.exit(1)


def git_current_branch() -> str:
    """Return the name of the currently checked‑out branch."""
    return (
        subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        .decode()
        .strip()
    )


def git_short_hash(branch: str) -> str:
    """Return the short hash of the given branch."""
    return (
        subprocess.check_output(["git", "rev-parse", "--short", branch])
        .decode()
        .strip()
    )


def sanitize_name(name: str) -> str:
    """Convert a name to a git-friendly format."""
    return "".join(c if c.isalnum() else "-" for c in name).strip("-")


def main(argv: list[str] | None = None) -> None:  # noqa: D401
    """Entry point for script."""
    parser = build_parser()

    if "argcomplete" in sys.modules:
        argcomplete.autocomplete(parser)

    args = parser.parse_args(argv)

    ensure_git_repo()

    username = os.getenv("USER") or os.getlogin()
    prefix = args.prefix

    base_dest = Path(args.path).expanduser() if args.path else REPO_ROOT.parent
    base_branch = git_current_branch()
    commit_hash = git_short_hash(base_branch)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    custom_names = args.names

    num_worktrees = max(args.repeat, len(custom_names)) if custom_names else args.repeat

    for i in range(num_worktrees):
        custom_name_suffix = None

        if custom_names:
            if i < len(custom_names):
                custom_name_suffix = sanitize_name(custom_names[i])
            else:
                suffix_index = i + 1 - len(custom_names)
                custom_name_suffix = f"{sanitize_name(custom_names[-1])}-{suffix_index}"
        else:
            if num_worktrees > 1:
                custom_name_suffix = str(i + 1)

        base_branch_part = f"{prefix}-{username}-{timestamp}-{commit_hash}"

        branch_name = (
            f"{base_branch_part}-{custom_name_suffix}"
            if custom_name_suffix
            else base_branch_part
        )

        dir_name = f"worktree-{branch_name}"
        dest = base_dest / dir_name

        sh(["git", "branch", branch_name, base_branch])

        sh(["git", "worktree", "add", dest, branch_name])

        env_src = REPO_ROOT / ".env"
        if env_src.exists():
            sh(["cp", env_src, f"{dest}/.env"])

        venv_dest = dest / ".venv"

        python3 = shutil.which("python3")
        if python3:
            print(f"Creating minimal .venv with {python3} ...")
            subprocess.run(
                [python3, "-m", "venv", str(venv_dest)], cwd=dest, check=True
            )
        else:
            print("Warning: Could not find Python to create .venv")

        sh(["direnv", "allow", dest])

        if not args.no_open:
            subprocess.Popen(
                ["cursor", "."],
                cwd=dest,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        print(f"Worktree created at {dest} (branch '{branch_name}')")


if __name__ == "__main__":
    main()
