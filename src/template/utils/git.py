from __future__ import annotations

import subprocess
import sys


def current_branch() -> str:
    """Return the name of the current git branch.

    Falls back to an empty string if git command fails (e.g., outside a git repo).
    """

    try:
        result = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return result.strip()
    except Exception:
        # Not a git repository or git not installed
        return ""


def ensure_experiment_branch() -> str:
    """
    Abort execution if current branch does not start with ``experiment``.
    """

    branch = current_branch()
    if not branch or not branch.startswith("experiment"):
        msg = (
            f"[ABORT] Current branch is '{branch or 'unknown'}'. "
            "Switch to an *experiment* branch first (hint: use the `fork-worktree` script)."
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    return branch


def commit_and_push(commit_message: str) -> None:
    """Stage all changes, commit, and push **HEAD** to origin.

    * Adds all modifications (``git add -A``)
    * Creates a commit with the supplied message (tolerates *nothing to commit*)
    * Pushes the current ``HEAD`` to ``origin`` and sets upstream (``-u``)
      – this will create the remote branch if it doesn't exist yet.
    """

    try:
        # Stage everything
        subprocess.run(["git", "add", "-A"], check=True)

        # Create commit (ignore "nothing to commit" situations)
        commit_proc = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True,
            text=True,
        )

        if commit_proc.returncode not in (0, 1):
            # 1 is "nothing to commit" – treat as success
            print(commit_proc.stdout + commit_proc.stderr, file=sys.stderr)
            sys.exit(commit_proc.returncode)

        # Push HEAD; -u sets upstream if needed
        subprocess.run(["git", "push", "-u", "origin", "HEAD"], check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Git operation failed: {exc}", file=sys.stderr)
        sys.exit(exc.returncode)


def current_commit() -> str:
    """Return the short hash of the current git HEAD commit."""
    try:
        result = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return result.strip()
    except Exception:
        return "unknown"


def github_repo_url() -> str:
    """Return the GitHub repository URL from git remote origin.

    Falls back to an empty string if git command fails or URL is not a GitHub URL.
    """
    try:
        result = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        url = result.strip()

        # Convert SSH URL to HTTPS if needed
        if url.startswith("git@github.com:"):
            url = url.replace("git@github.com:", "https://github.com/")

        # Remove .git suffix if present
        if url.endswith(".git"):
            url = url[:-4]

        # Verify it's a GitHub URL
        if url.startswith("https://github.com/"):
            return url
        else:
            return ""
    except Exception:
        return ""


def github_commit_link(commit_hash: str | None = None) -> str:
    """Return the GitHub commit link for the given commit hash.

    Args:
        commit_hash: The commit hash to link to. If None, uses current HEAD.

    Returns:
        The GitHub commit URL, or empty string if unable to construct.
    """
    if commit_hash is None:
        commit_hash = current_commit()

    if commit_hash == "unknown":
        return ""

    repo_url = github_repo_url()
    if not repo_url:
        return ""

    # Get the full commit hash for the link
    try:
        full_hash = subprocess.check_output(
            ["git", "rev-parse", commit_hash],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return f"{repo_url}/commit/{full_hash}"
    except Exception:
        # Fallback to short hash if full hash fails
        return f"{repo_url}/commit/{commit_hash}"
