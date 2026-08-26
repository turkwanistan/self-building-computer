from __future__ import annotations
# GEN6_FINAL_MARKER

import functools
import hashlib
import importlib.metadata
import json
import os
import signal
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

HOST = os.environ.get("LAB_MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("LAB_MCP_PORT", "8890"))
MAX_OUTPUT = int(os.environ.get("LAB_MCP_MAX_OUTPUT", str(1 << 20)))
SPOOL_THRESHOLD = int(os.environ.get("LAB_MCP_SPOOL_THRESHOLD", str(64 << 10)))
PREVIEW_BYTES = int(os.environ.get("LAB_MCP_PREVIEW_BYTES", str(16 << 10)))
JOB_ROOT = Path(os.environ.get("LAB_MCP_JOB_ROOT", "/var/lib/optiplex-lab/jobs"))
TRACE_ROOT = Path(os.environ.get("LAB_MCP_TRACE_ROOT", "/var/lib/optiplex-lab/traces"))
SPOOL_ROOT = Path(os.environ.get("LAB_MCP_SPOOL_ROOT", "/var/lib/optiplex-lab/spool"))
BUILD_FILE = Path(os.environ.get("LAB_MCP_BUILD_FILE", "/etc/optiplex-lab/build.json"))
SKILL_ROOT = Path(os.environ.get("LAB_MCP_SKILL_ROOT", "/opt/optiplex-lab/skills"))
CODE_MODE_PATH = Path(os.environ.get("LAB_CODE_MODE_PATH", "/opt/optiplex-lab/code_mode.py"))
TRACE_MAX_BYTES = int(os.environ.get("LAB_MCP_TRACE_MAX_BYTES", str(2 << 20)))
SPOOL_MAX_BYTES = int(os.environ.get("LAB_MCP_SPOOL_MAX_BYTES", str(64 << 20)))
RUN_ID = f"run_{uuid.uuid4().hex[:12]}"
SOURCE = Path(__file__).resolve()

mcp = FastMCP("optiplex-lab", host=HOST, port=PORT)
_jobs: dict[str, subprocess.Popen[bytes]] = {}

SENSITIVE_MARKERS = (
    b"-----begin private key-----", b"authorization: bearer", b"aws_secret_access_key",
    b"password=", b"passwd=", b"token=", b"api_key=", b"apikey=", b"ghp_", b"github_pat_",
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _looks_sensitive(data: bytes) -> bool:
    low = data[: min(len(data), 1 << 20)].lower()
    return any(marker in low for marker in SENSITIVE_MARKERS)


def _rotate_jsonl(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size >= TRACE_MAX_BYTES:
            for i in range(3, 0, -1):
                src = path.with_suffix(path.suffix + ("" if i == 1 else f".{i-1}"))
                dst = path.with_suffix(path.suffix + f".{i}")
                if src.exists():
                    if i == 3 and dst.exists():
                        dst.unlink()
                    src.replace(dst)
    except Exception:
        pass


def _trim_spool() -> None:
    try:
        files = [p for p in SPOOL_ROOT.rglob("*") if p.is_file()]
        total = sum(p.stat().st_size for p in files)
        if total <= SPOOL_MAX_BYTES:
            return
        for p in sorted(files, key=lambda x: x.stat().st_mtime):
            size = p.stat().st_size
            p.unlink(missing_ok=True)
            total -= size
            if total <= SPOOL_MAX_BYTES * 3 // 4:
                break
    except Exception:
        pass


def _spool(data: bytes, label: str) -> str | None:
    if _looks_sensitive(data):
        return None
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    directory = SPOOL_ROOT / day
    directory.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in label)[:48]
    target = directory / f"{int(time.time()*1000)}-{uuid.uuid4().hex[:8]}-{safe}.log"
    target.write_bytes(data[: MAX_OUTPUT * 16])
    _trim_spool()
    return str(target)


def _render_output(data: bytes | str, label: str, *, existing_path: str | None = None) -> tuple[str, dict[str, Any]]:
    raw = data if isinstance(data, bytes) else data.encode("utf-8", errors="replace")
    meta: dict[str, Any] = {"bytes": len(raw), "sha256": _sha(raw), "spool": None, "truncated": False}
    if len(raw) <= SPOOL_THRESHOLD:
        return raw.decode("utf-8", errors="replace"), meta
    if _looks_sensitive(raw):
        meta["truncated"] = True
        meta["sensitive_spool_suppressed"] = True
        return f"[large output suppressed by sensitive-pattern heuristic; bytes={len(raw)} sha256={meta['sha256']}]", meta
    path = existing_path or _spool(raw, label)
    meta["spool"] = path
    meta["truncated"] = True
    head_n = max(1024, PREVIEW_BYTES * 2 // 3)
    tail_n = max(512, PREVIEW_BYTES - head_n)
    head = raw[:head_n].decode("utf-8", errors="replace")
    tail = raw[-tail_n:].decode("utf-8", errors="replace") if len(raw) > head_n else ""
    marker = f"\n...[full output: {path}; bytes={len(raw)}; sha256={meta['sha256']}]...\n"
    return head + marker + tail, meta


def _arg_summary(tool: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    # Deliberately avoid recording command/content bodies or secret-bearing values.
    values: dict[str, Any] = {}
    if tool == "shell":
        cmd = str(kwargs.get("command", args[0] if args else ""))
        values = {"command_len": len(cmd), "command_sha256": _sha(cmd.encode()), "cwd": kwargs.get("cwd", "/root"), "timeout": kwargs.get("timeout", 120)}
    elif tool == "write_file":
        path = str(kwargs.get("path", args[0] if args else "")); content = str(kwargs.get("content", args[1] if len(args) > 1 else ""))
        values = {"path": path, "content_bytes": len(content.encode()), "content_sha256": _sha(content.encode())}
    elif tool in {"read_file", "read_range", "list_files"}:
        values = {k: v for k, v in kwargs.items() if k in {"path", "max_bytes", "offset", "depth"}}
        if args and "path" not in values: values["path"] = str(args[0])
    elif tool == "job":
        cmd = str(kwargs.get("command") or "")
        values = {"action": kwargs.get("action", args[0] if args else None), "job_id": kwargs.get("job_id"), "cwd": kwargs.get("cwd", "/root")}
        if cmd: values.update({"command_len": len(cmd), "command_sha256": _sha(cmd.encode())})
    elif tool == "service":
        values = {"action": kwargs.get("action", args[0] if args else None), "name": kwargs.get("name", args[1] if len(args) > 1 else None)}
    elif tool == "self_restart":
        values = {"confirm": bool(kwargs.get("confirm", args[0] if args else False))}
    else:
        values = {"arg_count": len(args), "kw_keys": sorted(kwargs.keys())}
    return values


def _result_summary(result: Any) -> dict[str, Any]:
    try:
        encoded = json.dumps(result, default=str, separators=(",", ":")).encode()
    except Exception:
        encoded = repr(result).encode(errors="replace")
    out: dict[str, Any] = {"result_bytes": len(encoded)}
    if isinstance(result, dict):
        for key in ("exit_code", "state", "job_id", "bytes", "eof", "spool", "stdout_spool", "stderr_spool"):
            if key in result: out[key] = result[key]
    return out


def _trace_event(record: dict[str, Any]) -> None:
    try:
        TRACE_ROOT.mkdir(parents=True, exist_ok=True)
        path = TRACE_ROOT / "events.jsonl"
        _rotate_jsonl(path)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    except Exception:
        pass


def traced(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        tool = fn.__name__; started = time.monotonic(); call_id = f"call_{uuid.uuid4().hex[:12]}"
        base = {"timestamp": _utc(), "run_id": RUN_ID, "call_id": call_id, "tool": tool, "args": _arg_summary(tool, args, kwargs)}
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            _trace_event(base | {"duration_ms": round((time.monotonic()-started)*1000, 2), "tool_success": False, "error_class": type(exc).__name__})
            raise
        _trace_event(base | {"duration_ms": round((time.monotonic()-started)*1000, 2), "tool_success": True, "result": _result_summary(result)})
        return result
    return wrapper


def _job_meta_path(jid: str) -> Path:
    return JOB_ROOT / f"{jid}.json"


def _load_job_meta(jid: str) -> dict[str, Any]:
    p = _job_meta_path(jid)
    if not p.exists(): return {}
    try: return json.loads(p.read_text())
    except Exception: return {}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0); return True
    except OSError:
        return False


@mcp.tool()
@traced
def shell(command: str, cwd: str = "/root", timeout: int = 120) -> dict[str, Any]:
    """Run an arbitrary guest command as root; large outputs are spooled with bounded previews."""
    timeout = max(1, min(int(timeout), 3600)); started = time.monotonic()
    result = subprocess.run(["/bin/bash", "-lc", command], cwd=cwd, capture_output=True, timeout=timeout, check=False)
    stdout, sm = _render_output(result.stdout, "shell.stdout"); stderr, em = _render_output(result.stderr, "shell.stderr")
    return {"exit_code": result.returncode, "stdout": stdout, "stderr": stderr, "duration_ms": round((time.monotonic()-started)*1000,2),
            "stdout_bytes": sm["bytes"], "stderr_bytes": em["bytes"], "stdout_spool": sm.get("spool"), "stderr_spool": em.get("spool")}


@mcp.tool()
@traced
def read_file(path: str, max_bytes: int = 1 << 20) -> str:
    """Read a regular guest file when it fits the requested bound; use read_range for large files."""
    cap = max(1, min(int(max_bytes), MAX_OUTPUT))
    with open(path, "rb") as handle: data = handle.read(cap + 1)
    if len(data) > cap: raise ValueError("file exceeds requested read limit; use read_range")
    return data.decode("utf-8", errors="replace")


@mcp.tool()
@traced
def read_range(path: str, offset: int = 0, max_bytes: int = 256 << 10) -> dict[str, Any]:
    """Read a bounded byte range from any guest file, useful for large spool/job artifacts."""
    offset = max(0, int(offset)); cap = max(1, min(int(max_bytes), MAX_OUTPUT))
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(offset); data = f.read(cap)
    return {"path": path, "offset": offset, "bytes": len(data), "size": size, "eof": offset + len(data) >= size, "data": data.decode("utf-8", errors="replace")}


@mcp.tool()
@traced
def write_file(path: str, content: str, mode: int | None = None) -> dict[str, Any]:
    """Write any guest file atomically, creating parent directories when needed."""
    target = Path(path); target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + f".tmp-{uuid.uuid4().hex[:8]}"); tmp.write_text(content, encoding="utf-8")
    if mode is not None: os.chmod(tmp, int(mode))
    tmp.replace(target)
    return {"path": str(target), "bytes": len(content.encode("utf-8")), "sha256": _sha(content.encode())}


@mcp.tool()
@traced
def list_files(path: str = "/", depth: int = 2) -> list[str]:
    """List guest filesystem entries beneath a path to a bounded depth."""
    root = Path(path); depth = max(0, min(int(depth), 8)); base_parts = len(root.resolve().parts); out: list[str] = []
    for current, dirs, files in os.walk(root):
        current_path = Path(current); level = len(current_path.resolve().parts) - base_parts
        if level >= depth: dirs[:] = []
        for name in sorted(dirs) + sorted(files):
            out.append(str(current_path / name))
            if len(out) >= 5000: return out
    return out


@mcp.tool()
@traced
def job(action: Literal["start", "status", "logs", "cancel"], job_id: str | None = None, command: str | None = None, cwd: str = "/root") -> dict[str, Any]:
    """Start/inspect/log/cancel durable guest jobs in independent transient systemd units."""
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    def unit_props(unit: str) -> dict[str, str]:
        r = subprocess.run(["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "ExecMainStatus", "-p", "MainPID"], capture_output=True, text=True, timeout=15, check=False)
        out: dict[str, str] = {}
        for line in r.stdout.splitlines():
            if "=" in line:
                k, v = line.split("=", 1); out[k] = v
        return out
    if action == "start":
        if not command: raise ValueError("command is required for start")
        jid = f"job_{uuid.uuid4().hex[:12]}"; unit = f"optiplex-lab-job-{jid[4:]}"; log_path = JOB_ROOT / f"{jid}.log"
        wrapped = f"exec >>{log_path} 2>&1\ncd {cwd}\n{command}"
        r = subprocess.run(["systemd-run", "--quiet", f"--unit={unit}", "--property=Type=exec", "/bin/bash", "-lc", wrapped], capture_output=True, text=True, timeout=15, check=False)
        if r.returncode != 0: raise RuntimeError(r.stderr.strip() or "systemd-run failed")
        time.sleep(0.05); props = unit_props(unit); pid = int(props.get("MainPID", "0") or 0)
        meta = {"job_id": jid, "unit": unit, "pid": pid, "cwd": cwd, "command_sha256": _sha(command.encode()), "command_len": len(command), "started_at": _utc(), "log": str(log_path)}
        _job_meta_path(jid).write_text(json.dumps(meta, indent=2)+"\n")
        return meta
    if not job_id: raise ValueError("job_id is required")
    log_path = JOB_ROOT / f"{job_id}.log"; meta = _load_job_meta(job_id); unit = str(meta.get("unit") or "")
    if action == "logs":
        if not log_path.exists(): return {"job_id": job_id, "logs": "", "log": str(log_path), "bytes": 0}
        raw = log_path.read_bytes(); preview, om = _render_output(raw, "job.logs", existing_path=str(log_path))
        return {"job_id": job_id, "logs": preview, "log": str(log_path), "bytes": len(raw), "spool": om.get("spool")}
    if unit:
        props = unit_props(unit); active = props.get("ActiveState"); sub = props.get("SubState"); pid = int(props.get("MainPID", "0") or 0); status = int(props.get("ExecMainStatus", "0") or 0)
        if action == "status":
            state = "running" if active == "active" else ("finished" if active in {"inactive", "failed"} else active or "unknown")
            return {"job_id": job_id, "unit": unit, "pid": pid, "state": state, "substate": sub, "exit_code": status if state == "finished" else None, "log": str(log_path)}
        if action == "cancel":
            subprocess.run(["systemctl", "stop", unit], capture_output=True, timeout=15, check=False)
            return {"job_id": job_id, "unit": unit, "state": "cancelled", "log": str(log_path)}
    # Compatibility with Gen-0/early-Gen-1 job metadata.
    proc = _jobs.get(job_id); pid = int(meta.get("pid", 0) or 0); code = proc.poll() if proc is not None else None
    alive = (code is None and proc is not None) or (proc is None and pid > 0 and _pid_alive(pid))
    if action == "status": return {"job_id": job_id, "pid": pid, "state": "running" if alive else "finished-or-unknown", "exit_code": code, "log": str(log_path)}
    if action == "cancel":
        if alive:
            try: os.killpg(int(meta.get("pgid", pid)), signal.SIGTERM)
            except OSError: pass
        return {"job_id": job_id, "state": "cancelled", "log": str(log_path)}
    raise ValueError("unsupported action")


@mcp.tool()
@traced
def service(action: Literal["start", "stop", "restart", "status", "enable", "disable"], name: str) -> dict[str, Any]:
    """Control an arbitrary systemd service inside the guest."""
    result = subprocess.run(["systemctl", action, name], capture_output=True, text=True, timeout=60, check=False)
    stdout, sm = _render_output(result.stdout, "service.stdout"); stderr, em = _render_output(result.stderr, "service.stderr")
    return {"exit_code": result.returncode, "stdout": stdout, "stderr": stderr, "stdout_spool": sm.get("spool"), "stderr_spool": em.get("spool")}


@mcp.tool()
@traced
def lab_status() -> dict[str, Any]:
    """Return self-hosting identity, paths, telemetry/spool statistics, and verification commands."""
    try: build = json.loads(BUILD_FILE.read_text())
    except Exception: build = {"generation": "unknown", "build_id": "unknown"}
    source_bytes = SOURCE.read_bytes()
    trace = TRACE_ROOT / "events.jsonl"
    spools = [p for p in SPOOL_ROOT.rglob("*") if p.is_file()] if SPOOL_ROOT.exists() else []
    skills = sorted(p.parent.name for p in SKILL_ROOT.glob("*/SKILL.md")) if SKILL_ROOT.exists() else []
    workflow_skills = Path("/opt/optiplex-lab/workflow_skills.py")
    workflow_registry = Path("/var/lib/optiplex-lab/workflows")
    registered_workflows = len(list(workflow_registry.glob("*/*.json"))) if workflow_registry.exists() else 0
    workflow_graphs = Path("/opt/optiplex-lab/workflow_graphs.py")
    workflow_graph_registry = Path("/var/lib/optiplex-lab/workflow-graphs")
    registered_graphs = len(list(workflow_graph_registry.glob("*/*.json"))) if workflow_graph_registry.exists() else 0
    return {"name": "optiplex-lab", "generation": build.get("generation"), "build_id": build.get("build_id"), "source_sha256": _sha(source_bytes),
            "pid": os.getpid(), "run_id": RUN_ID, "mcp_version": importlib.metadata.version("mcp"), "tool_surface": 10,
            "trace": {"path": str(trace), "bytes": trace.stat().st_size if trace.exists() else 0},
            "spool": {"root": str(SPOOL_ROOT), "files": len(spools), "bytes": sum(p.stat().st_size for p in spools)},
            "skills": skills, "paths": {"source": str(SOURCE), "build": str(BUILD_FILE), "jobs": str(JOB_ROOT), "recovery": "/var/lib/optiplex-lab/recovery"},
            "code_mode": {"path": str(CODE_MODE_PATH), "available": CODE_MODE_PATH.is_file(), "sha256": _sha(CODE_MODE_PATH.read_bytes()) if CODE_MODE_PATH.is_file() else None, "version": "gen3-code-mode-r1"},
            "reusable_workflows": {"path": str(workflow_skills), "available": workflow_skills.is_file(), "sha256": _sha(workflow_skills.read_bytes()) if workflow_skills.is_file() else None, "version": "gen3-workflow-skills-r1", "registered": registered_workflows},
            "workflow_graphs": {"path": str(workflow_graphs), "available": workflow_graphs.is_file(), "sha256": _sha(workflow_graphs.read_bytes()) if workflow_graphs.is_file() else None, "version": "gen4-workflow-graphs-r1", "registered": registered_graphs},
            "commands": {"self_test": "/opt/optiplex-lab/selftest.py", "benchmark": "/opt/optiplex-lab/bench/benchmark_gen6.py", "failure_miner": "/opt/optiplex-lab/bench/failure_miner.py", "code_mode": "/opt/optiplex-lab/code_mode.py", "workflows": "/opt/optiplex-lab/workflow_skills.py", "graphs": "/opt/optiplex-lab/workflow_graphs.py", "memory": "/opt/optiplex-lab/experience_memory.py", "regressions": "/opt/optiplex-lab/regression_compiler.py", "experience_loop": "/opt/optiplex-lab/experience_loop.py", "rollback": "/usr/local/sbin/optiplex-lab-rollback"},
            "capability_forge": {"path": "/opt/optiplex-lab/capability_forge.py", "available": Path("/opt/optiplex-lab/capability_forge.py").is_file(), "sha256": _sha(Path("/opt/optiplex-lab/capability_forge.py").read_bytes()) if Path("/opt/optiplex-lab/capability_forge.py").is_file() else None, "version": "gen6-capability-forge-r2", "registry": "/var/lib/optiplex-lab/capabilities/registry.json"},
            "procedural_memory": {"path": "/opt/optiplex-lab/experience_memory.py", "available": Path("/opt/optiplex-lab/experience_memory.py").is_file(), "sha256": _sha(Path("/opt/optiplex-lab/experience_memory.py").read_bytes()) if Path("/opt/optiplex-lab/experience_memory.py").is_file() else None, "version": "gen6-procedural-memory-r1", "registry": "/var/lib/optiplex-lab/memory/registry.json"},
            "failure_regressions": {"path": "/opt/optiplex-lab/regression_compiler.py", "available": Path("/opt/optiplex-lab/regression_compiler.py").is_file(), "sha256": _sha(Path("/opt/optiplex-lab/regression_compiler.py").read_bytes()) if Path("/opt/optiplex-lab/regression_compiler.py").is_file() else None, "version": "gen6-failure-regression-r1", "registry": "/var/lib/optiplex-lab/regressions/registry.json"},
            "experience_loop": {"path": "/opt/optiplex-lab/experience_loop.py", "available": Path("/opt/optiplex-lab/experience_loop.py").is_file(), "sha256": _sha(Path("/opt/optiplex-lab/experience_loop.py").read_bytes()) if Path("/opt/optiplex-lab/experience_loop.py").is_file() else None, "version": "gen6-experience-loop-r1"}}


@mcp.tool()
@traced
def self_restart(confirm: bool = False) -> dict[str, str]:
    """Schedule a guest-local MCP restart after this call returns, preserving connector ergonomics."""
    if not confirm: raise ValueError("set confirm=true to restart the Lab MCP")
    unit = f"optiplex-lab-selfrestart-{uuid.uuid4().hex[:8]}"
    result = subprocess.run(["systemd-run", "--quiet", f"--unit={unit}", "--on-active=1s", "/bin/systemctl", "restart", "optiplex-lab-mcp.service"], capture_output=True, text=True, timeout=15, check=False)
    if result.returncode != 0: raise RuntimeError(result.stderr.strip() or "failed to schedule restart")
    return {"status": "restart scheduled", "unit": unit}


@mcp.tool()
@traced
def reboot(confirm: bool = False) -> dict[str, str]:
    """Reboot the disposable guest. Requires confirm=true."""
    if not confirm: raise ValueError("set confirm=true to reboot the lab guest")
    subprocess.Popen(["systemctl", "reboot"])
    return {"status": "reboot requested"}


def main() -> None:
    for p in (JOB_ROOT, TRACE_ROOT, SPOOL_ROOT): p.mkdir(parents=True, exist_ok=True)
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
