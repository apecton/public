# Description:
# Git integration helpers — retrieve staged files, diff files, and file content
# from the git index or working tree.

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

_GIT_TIMEOUT = 30  # seconds


def _run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return stdout, raising RuntimeError on failure."""
    log.debug("git %s (cwd=%s)", " ".join(args), cwd)
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=_GIT_TIMEOUT,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git command timed out after {_GIT_TIMEOUT}s") from exc

    if result.returncode != 0:
        raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def get_repo_root(start: Path) -> Path:
    """Return the root of the git repository containing `start`."""
    log.debug("resolving git repo root from %s", start)
    raw = _run_git(["rev-parse", "--show-toplevel"], cwd=start).strip()
    root = Path(raw)
    log.debug("repo root: %s", root)
    return root


def get_staged_files(repo_root: Path, path_filter: Path | None = None) -> list[Path]:
    """Return absolute paths of files currently in the git staging area."""
    log.debug("get_staged_files path_filter=%s", path_filter)
    args = ["diff", "--cached", "--name-only", "--diff-filter=d"]
    if path_filter:
        args += ["--", str(path_filter)]
    raw = _run_git(args, cwd=repo_root)
    files = [repo_root / p.strip() for p in raw.splitlines() if p.strip()]
    log.debug("staged files: %s", files)
    return files


def get_diff_files(repo_root: Path, base_branch: str, path_filter: Path | None = None) -> list[Path]:
    """Return absolute paths of files changed between `base_branch` and HEAD."""
    log.debug("get_diff_files base=%s path_filter=%s", base_branch, path_filter)
    args = ["diff", f"{base_branch}...HEAD", "--name-only", "--diff-filter=d"]
    if path_filter:
        args += ["--", str(path_filter)]
    raw = _run_git(args, cwd=repo_root)
    files = [repo_root / p.strip() for p in raw.splitlines() if p.strip()]
    log.debug("diff files vs %s: %s", base_branch, files)
    return files


def read_staged_content(repo_root: Path, file_path: Path) -> str | None:
    """
    Return the staged (index) content of a file as a string.
    Returns None if the file cannot be read as text (binary).
    """
    relative = file_path.relative_to(repo_root)
    log.debug("reading staged content for %s", relative)
    try:
        content = _run_git(["show", f":{relative.as_posix()}"], cwd=repo_root)
        return content
    except RuntimeError as exc:
        log.debug("could not read staged content for %s: %s", relative, exc)
        return None
