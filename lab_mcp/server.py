from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

HOST = os.environ.get("LAB_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("LAB_MCP_PORT", "8890"))
MAX_OUTPUT = int(os.environ.get("LAB_MCP_MAX_OUTPUT", str(1 << 20)))
JOB_ROOT = Path(os.environ.get("LAB_MCP_JOB_ROOT", "/var/lib/optiplex-lab/jobs"))

mcp = FastMCP("optiplex-lab", host=HOST, port=PORT)
_jobs: dict[str, subprocess.Popen[bytes]] = {}


def _bounded(data: bytes | str) -> str:
    raw = data if isinstance(data, bytes) else data.encode("utf-8", errors="replace")
    if len(raw) <= MAX_OUTPUT:
        return raw.decode("utf-8", errors="replace")
    return raw[: MAX_OUTPUT - 18].decode("utf-8", errors="ignore") + "\n...[truncated]"


@mcp.tool()
def shell(command: str, cwd: str = "/root", timeout: int = 120) -> dict[str, Any]:
    """Run an arbitrary guest command as the lab MCP service user (root by design)."""
    timeout = max(1, min(int(timeout), 3600))
    result = subprocess.run(
        ["/bin/bash", "-lc", command], cwd=cwd, capture_output=True, timeout=timeout, check=False
    )
    return {"exit_code": result.returncode, "stdout": _bounded(result.stdout), "stderr": _bounded(result.stderr)}


@mcp.tool()
def read_file(path: str, max_bytes: int = 1 << 20) -> str:
    """Read any regular file inside the guest."""
    cap = max(1, min(int(max_bytes), MAX_OUTPUT))
    with open(path, "rb") as handle:
        data = handle.read(cap + 1)
    if len(data) > cap:
        raise ValueError("file exceeds requested read limit")
    return data.decode("utf-8", errors="replace")


@mcp.tool()
def write_file(path: str, content: str, mode: int | None = None) -> dict[str, Any]:
    """Write any guest file, creating parent directories when needed."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if mode is not None:
        os.chmod(target, int(mode))
    return {"path": str(target), "bytes": len(content.encode("utf-8"))}


@mcp.tool()
def list_files(path: str = "/", depth: int = 2) -> list[str]:
    """List guest filesystem entries beneath a path to a bounded depth."""
    root = Path(path)
    depth = max(0, min(int(depth), 8))
    base_parts = len(root.resolve().parts)
    out: list[str] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        level = len(current_path.resolve().parts) - base_parts
        if level >= depth:
            dirs[:] = []
        for name in sorted(dirs) + sorted(files):
            out.append(str(current_path / name))
            if len(out) >= 5000:
                return out
    return out


@mcp.tool()
def job(
    action: Literal["start", "status", "logs", "cancel"],
    job_id: str | None = None,
    command: str | None = None,
    cwd: str = "/root",
) -> dict[str, Any]:
    """Start, inspect, log, or cancel an arbitrary long-running guest process."""
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    if action == "start":
        if not command:
            raise ValueError("command is required for start")
        jid = f"job_{uuid.uuid4().hex[:12]}"
        log_path = JOB_ROOT / f"{jid}.log"
        log = open(log_path, "ab", buffering=0)
        proc = subprocess.Popen(
            ["/bin/bash", "-lc", command], cwd=cwd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        log.close()
        _jobs[jid] = proc
        return {"job_id": jid, "pid": proc.pid, "log": str(log_path)}
    if not job_id:
        raise ValueError("job_id is required")
    proc = _jobs.get(job_id)
    log_path = JOB_ROOT / f"{job_id}.log"
    if action == "logs":
        return {"job_id": job_id, "logs": _bounded(log_path.read_bytes() if log_path.exists() else b"")}
    if proc is None:
        return {"job_id": job_id, "state": "unknown-or-finished", "log": str(log_path)}
    code = proc.poll()
    if action == "status":
        return {"job_id": job_id, "pid": proc.pid, "state": "running" if code is None else "finished", "exit_code": code}
    if action == "cancel":
        if code is None:
            os.killpg(proc.pid, signal.SIGTERM)
            time.sleep(0.2)
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
        return {"job_id": job_id, "state": "cancelled", "exit_code": proc.poll()}
    raise ValueError("unsupported action")


@mcp.tool()
def service(action: Literal["start", "stop", "restart", "status", "enable", "disable"], name: str) -> dict[str, Any]:
    """Control an arbitrary systemd service inside the guest."""
    result = subprocess.run(["systemctl", action, name], capture_output=True, text=True, timeout=60, check=False)
    return {"exit_code": result.returncode, "stdout": _bounded(result.stdout), "stderr": _bounded(result.stderr)}


@mcp.tool()
def reboot(confirm: bool = False) -> dict[str, str]:
    """Reboot the disposable guest. Requires confirm=true."""
    if not confirm:
        raise ValueError("set confirm=true to reboot the lab guest")
    subprocess.Popen(["systemctl", "reboot"])
    return {"status": "reboot requested"}


def main() -> None:
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
