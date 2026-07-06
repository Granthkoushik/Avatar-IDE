from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

logger = logging.getLogger("avatar.executor")

class ExecutionResult:
    def __init__(self, command: str, stdout: str, stderr: str, exit_code: int, duration: float):
        self.command = command
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code
        self.duration = duration

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration": round(self.duration, 3)
        }

async def execute_command(command: str, cwd: Path, timeout: float = 30.0) -> ExecutionResult:
    """Execute a shell command asynchronously, capturing stdout, stderr, and execution time."""
    start_time = time.monotonic()
    logger.info("Executing command: %s (cwd=%s)", command, cwd)

    try:
        # Create subprocess
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd)
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
            exit_code = process.returncode if process.returncode is not None else -1
            stdout = stdout_bytes.decode("utf-8", errors="ignore")
            stderr = stderr_bytes.decode("utf-8", errors="ignore")
        except asyncio.TimeoutError:
            try:
                process.kill()
            except Exception:
                pass
            stdout_bytes, stderr_bytes = await process.communicate()
            exit_code = -1
            stdout = stdout_bytes.decode("utf-8", errors="ignore") + "\n[AVATAR] Command timed out!"
            stderr = stderr_bytes.decode("utf-8", errors="ignore") + "\n[AVATAR] Command timed out!"
            logger.error("Command timed out: %s", command)

    except Exception as exc:
        exit_code = -1
        stdout = ""
        stderr = f"[AVATAR] Failed to launch command: {exc}"
        logger.exception("Failed to launch command %s", command)

    duration = time.monotonic() - start_time
    return ExecutionResult(command, stdout, stderr, exit_code, duration)
