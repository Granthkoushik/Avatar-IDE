from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("avatar.git_manager")

def _run_git(args: list[str], cwd: Path) -> tuple[str, str, int]:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False
        )
        return res.stdout.strip(), res.stderr.strip(), res.returncode
    except Exception as exc:
        logger.error("Git error: %s", exc)
        return "", str(exc), -1

def ensure_git_repo(cwd: Path) -> None:
    """Ensure that the target directory is a Git repository."""
    # Check if .git directory exists
    git_dir = cwd / ".git"
    if not git_dir.exists():
        logger.info("Initializing new Git repository under %s", cwd)
        _run_git(["init"], cwd)
        _run_git(["config", "user.name", "Avatar Agent"], cwd)
        _run_git(["config", "user.email", "avatar@local.agent"], cwd)
        create_checkpoint(cwd, "Initial workspace snapshot")

def create_checkpoint(cwd: Path, message: str) -> str:
    """Create a checkpoint commit of the current workspace state. Return commit hash."""
    ensure_git_repo(cwd)
    # Stage all files
    _run_git(["add", "."], cwd)
    
    # Check if there are changes to commit
    status_out, _, _ = _run_git(["status", "--porcelain"], cwd)
    if not status_out:
        # No changes to commit, return latest commit hash
        latest_hash, _, _ = _run_git(["log", "-1", "--format=%H"], cwd)
        return latest_hash

    # Commit changes
    commit_msg = f"checkpoint: {message}"
    _run_git(["commit", "-m", commit_msg], cwd)
    
    # Get hash
    latest_hash, _, _ = _run_git(["log", "-1", "--format=%H"], cwd)
    logger.info("Created Git checkpoint: %s (%s)", latest_hash, commit_msg)
    return latest_hash

def rollback_to_checkpoint(cwd: Path, commit_hash: str) -> bool:
    """Hard reset the workspace to a specific Git commit hash."""
    ensure_git_repo(cwd)
    _, err, code = _run_git(["reset", "--hard", commit_hash], cwd)
    if code == 0:
        # Run clean to delete untracked files/directories
        _run_git(["clean", "-fd"], cwd)
        logger.info("Successfully rolled back to checkpoint %s", commit_hash)
        return True
    logger.error("Failed to rollback to %s: %s", commit_hash, err)
    return False

def get_checkpoints(cwd: Path) -> list[dict]:
    """Retrieve the list of checkpoints (commits) in the workspace."""
    ensure_git_repo(cwd)
    stdout, _, code = _run_git(["log", "--pretty=format:%H|%ad|%s", "--date=iso"], cwd)
    if code != 0 or not stdout:
        return []
    
    checkpoints = []
    for line in stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commit_hash, date, msg = parts
            if msg.startswith("checkpoint: "):
                msg = msg[len("checkpoint: "):]
            checkpoints.append({
                "hash": commit_hash,
                "date": date,
                "message": msg
            })
    return checkpoints

def get_diff_from_checkpoint(cwd: Path, commit_hash: str) -> str:
    """Get a diff compared to a specific checkpoint."""
    ensure_git_repo(cwd)
    stdout, _, _ = _run_git(["diff", commit_hash], cwd)
    return stdout
