#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT = Path("/home/mcp/projects/projects/self-building-computer")
GUARDRAIL_SOURCE = Path("/home/mcp/projects/projects/optiplex-mcp-agent")
STATE_DIR = Path("/var/lib/mcp-evolution")
STATE_PATH = STATE_DIR / "current.json"
EVENTS_PATH = STATE_DIR / "events.jsonl"
ETC_DIR = Path("/etc/mcp-evolution")
SLOTS_DIR = ETC_DIR / "slots"
RELEASE_ROOT = Path("/opt/mcp/releases")
GUARDRAIL_ROOT = Path("/opt/mcp/guardrails/releases")
RUNTIME_PYTHON = Path("/opt/mcp/runtime-venv/bin/python")
VERIFY = Path("/usr/local/libexec/mcp-evolution-verify-mcp")
EXPECTED_COUNT = 51
EXPECTED_SCHEMA = "195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913"
POLICY_VERSION = "authority-v1"
PORTS = {"blue": 8792, "green": 8793}
GUARDRAIL_PORT = 8795
FRONTDOOR_PORT = 8790


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def die(message: str) -> "NoReturn":
    raise SystemExit(f"ERROR: {message}")


def require_root() -> None:
    if os.geteuid() != 0:
        die("this operation requires root")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any], mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.is_file():
        die("root lifecycle state is not initialized")
    return load_json(STATE_PATH)


def save_state(state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    atomic_json(STATE_PATH, state)


def append_event(event: str, **fields: Any) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    prev_hash = "0" * 64
    if EVENTS_PATH.exists():
        lines = [line for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines:
            prev_hash = json.loads(lines[-1]).get("event_hash", prev_hash)
    payload = {"timestamp": now(), "event": event, "prev_hash": prev_hash, **fields}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["event_hash"] = hashlib.sha256(canonical).hexdigest()
    with EVENTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    os.chmod(EVENTS_PATH, 0o640)


def content_hash(files: list[Path], base: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda p: str(p.relative_to(base))):
        rel = str(path.relative_to(base)).encode()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def source_files(root: Path, package: str) -> list[Path]:
    pkg = root / package
    if not pkg.is_dir():
        die(f"missing source package: {pkg}")
    files = [p for p in pkg.rglob("*.py") if "__pycache__" not in p.parts]
    if not files:
        die(f"no Python source under {pkg}")
    return files


def ensure_clean_secret_scan(files: list[Path]) -> None:
    # Build markers from fragments so a repository-wide secret scan does not
    # flag the scanner source itself.
    bad_markers = [
        ("BEGIN OPENSSH " + "PRIVATE KEY").encode(),
        ("BEGIN " + "PRIVATE KEY").encode(),
        ("OPENAI_" + "API_KEY=").encode(),
        ("CONTROL_PLANE_" + "API_KEY=").encode(),
        ("gh" + "p_").encode(),
        ("github_" + "pat_").encode(),
    ]
    for path in files:
        data = path.read_bytes()
        for marker in bad_markers:
            if marker in data:
                die(f"secret/credential marker {marker!r} found in {path}")


def immutable_copy(files: list[Path], source_root: Path, target: Path) -> None:
    if target.exists():
        return
    temp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    if temp.exists():
        shutil.rmtree(temp)
    for src in files:
        rel = src.relative_to(source_root)
        dst = temp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for path in sorted(temp.rglob("*"), reverse=True):
        if path.is_file():
            path.chmod(0o444)
        elif path.is_dir():
            path.chmod(0o555)
    temp.chmod(0o555)
    temp.rename(target)


def write_env(path: Path, values: dict[str, str]) -> None:
    text = "".join(f"{k}={json.dumps(str(v))}\n" for k, v in values.items())
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#"):
            continue
        key, sep, value = raw.partition("=")
        if not sep:
            continue
        values[key] = json.loads(value)
    return values


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["systemctl", *args], text=True, capture_output=True, check=check, timeout=60)


def wait_port(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.25)
    die(f"127.0.0.1:{port} did not become reachable")


def verify_url(port: int, expected_count: int, expected_schema: str) -> dict[str, Any]:
    result = subprocess.run(
        [str(RUNTIME_PYTHON), str(VERIFY), f"http://127.0.0.1:{port}/mcp", "--expect-count", str(expected_count), "--expect-schema", expected_schema],
        text=True,
        capture_output=True,
        timeout=45,
    )
    if result.returncode:
        die(f"MCP verification failed on {port}: {result.stderr or result.stdout}")
    return json.loads(result.stdout)


def run_as_mcp(python: Path, cwd: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    cmd = ["runuser", "-u", "mcp", "--", str(python), *args]
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)


def verify_fixed_confinement() -> None:
    unit = Path("/etc/systemd/system/mcp-evolution-blue.service").read_text(encoding="utf-8")
    required = [
        "User=mcp",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "PrivateDevices=true",
        "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_INET AF_INET6",
        "IPAddressDeny=any",
        "IPAddressAllow=localhost",
    ]
    missing = [item for item in required if item not in unit]
    if missing:
        die(f"candidate confinement unit missing required directives: {missing}")


def stage_guardrail_release() -> tuple[str, str]:
    files = source_files(GUARDRAIL_SOURCE, "mcp_agent")
    server = GUARDRAIL_SOURCE / "mcp_agent/server.py"
    text = server.read_text(encoding="utf-8")
    if "MCP_AGENT_PORT" not in text or "MCP_AGENT_HOST" not in text:
        die("guardrail source lacks the approved configurable-bind plumbing change")
    ensure_clean_secret_scan(files)
    sha = content_hash(files, GUARDRAIL_SOURCE)
    rid = f"guardrail-gen0-{sha[:12]}"
    target = GUARDRAIL_ROOT / rid
    immutable_copy(files, GUARDRAIL_SOURCE, target)
    manifest = {
        "release_id": rid,
        "source_sha256": sha,
        "authority_delta": "NONE",
        "purpose": "generation-0 protected authority backend with configurable loopback bind",
        "created_at": now(),
    }
    manifest_path = target / "release-manifest.json"
    if not manifest_path.exists():
        manifest_path.parent.chmod(0o755)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest_path.chmod(0o444)
    return rid, sha


def stage_frontend_release(metadata: dict[str, Any], prefix: str = "frontend") -> tuple[str, str, Path]:
    files = source_files(PROJECT, "mcp_frontend")
    pyproject = PROJECT / "pyproject.toml"
    files_for_hash = [*files, pyproject]
    ensure_clean_secret_scan(files_for_hash)
    digest = hashlib.sha256()
    digest.update(content_hash(files_for_hash, PROJECT).encode())
    digest.update(json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode())
    sha = digest.hexdigest()
    rid = f"{prefix}-{sha[:12]}"
    target = RELEASE_ROOT / rid
    if not target.exists():
        temp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
        if temp.exists():
            shutil.rmtree(temp)
        for src in files:
            rel = src.relative_to(PROJECT)
            dst = temp / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        shutil.copy2(pyproject, temp / "pyproject.toml")
        (temp / "release-manifest.json").write_text(
            json.dumps({**metadata, "release_id": rid, "source_sha256": sha, "created_at": now()}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for path in sorted(temp.rglob("*"), reverse=True):
            if path.is_file():
                path.chmod(0o444)
            elif path.is_dir():
                path.chmod(0o555)
        temp.chmod(0o555)
        temp.rename(target)
    return rid, sha, target


def slot_env(slot: str, release_id: str, release_dir: Path, source_sha: str, guardrail_release: str, expected_count: int, expected_schema: str) -> None:
    write_env(
        SLOTS_DIR / f"{slot}.env",
        {
            "RELEASE_ID": release_id,
            "RELEASE_DIR": str(release_dir),
            "SOURCE_SHA256": source_sha,
            "PORT": str(PORTS[slot]),
            "GUARDRAIL_RELEASE_ID": guardrail_release,
            "EXPECTED_TOOL_COUNT": str(expected_count),
            "EXPECTED_SCHEMA_SHA256": expected_schema,
            "POLICY_VERSION": POLICY_VERSION,
        },
    )


def route_slot(slot: str) -> None:
    write_env(ETC_DIR / "frontdoor.env", {"TARGET_SLOT": slot, "TARGET_PORT": str(PORTS[slot])})
    systemctl("restart", "mcp-evolution-frontdoor.service")
    wait_port(FRONTDOOR_PORT)


def bootstrap() -> None:
    require_root()
    if STATE_PATH.exists():
        die("lifecycle already initialized")
    if not RUNTIME_PYTHON.exists() or not VERIFY.exists():
        die("runtime/helper installation incomplete")
    verify_fixed_confinement()

    # Prove both source trees before touching the live route.
    sbc_tests = run_as_mcp(RUNTIME_PYTHON, PROJECT, ["-m", "pytest", "-q"])
    if sbc_tests.returncode:
        die(f"self-building tests failed: {sbc_tests.stdout}{sbc_tests.stderr}")
    guard_tests = run_as_mcp(Path("/home/mcp/agent/.venv/bin/python"), GUARDRAIL_SOURCE, ["-m", "pytest", "-q"], 300)
    if guard_tests.returncode:
        die(f"guardrail regression failed: {guard_tests.stdout}{guard_tests.stderr}")

    guard_id, guard_sha = stage_guardrail_release()
    write_env(ETC_DIR / "guardrail.env", {"RELEASE_ID": guard_id, "RELEASE_DIR": str(GUARDRAIL_ROOT / guard_id), "PORT": str(GUARDRAIL_PORT)})
    systemctl("enable", "--now", "mcp-evolution-guardrail.service")
    wait_port(GUARDRAIL_PORT)
    verify_url(GUARDRAIL_PORT, EXPECTED_COUNT, EXPECTED_SCHEMA)

    baseline_meta = {
        "cycle_id": "bootstrap-blue-green",
        "kind": "BASELINE",
        "authority_delta": "NONE",
        "expected_tool_count": EXPECTED_COUNT,
        "expected_tool_schema_sha256": EXPECTED_SCHEMA,
        "guardrail_release": guard_id,
        "policy_version": POLICY_VERSION,
    }
    release_id, source_sha, release_dir = stage_frontend_release(baseline_meta, "frontend-baseline")
    slot_env("blue", release_id, release_dir, source_sha, guard_id, EXPECTED_COUNT, EXPECTED_SCHEMA)
    systemctl("enable", "mcp-evolution-blue.service")
    systemctl("restart", "mcp-evolution-blue.service")
    wait_port(PORTS["blue"])
    verify_url(PORTS["blue"], EXPECTED_COUNT, EXPECTED_SCHEMA)

    state = {
        "format": 1,
        "state": "STABLE",
        "policy_version": POLICY_VERSION,
        "guardrail_release": guard_id,
        "guardrail_source_sha256": guard_sha,
        "stable": release_id,
        "stable_slot": "blue",
        "candidate": None,
        "candidate_slot": None,
        "previous": None,
        "previous_slot": None,
        "active_slot": "blue",
        "expected_tool_count": EXPECTED_COUNT,
        "expected_tool_schema_sha256": EXPECTED_SCHEMA,
        "security_authority_delta": "NONE",
        "emergency_fallback_service": "mcp-agent.service",
        "rollback_drill_passed": False,
        "initialized_at": now(),
    }
    append_event("blue_green_bootstrap_prepared", stable=release_id, guardrail_release=guard_id, security_delta="NONE")

    # Cut over only after both protected backend and baseline frontend are healthy.
    try:
        systemctl("disable", "--now", "mcp-agent.service")
        route_slot("blue")
        verify_url(FRONTDOOR_PORT, EXPECTED_COUNT, EXPECTED_SCHEMA)
    except BaseException:
        systemctl("stop", "mcp-evolution-frontdoor.service", check=False)
        systemctl("enable", "--now", "mcp-agent.service", check=False)
        raise
    systemctl("enable", "mcp-evolution-frontdoor.service")
    save_state(state)
    append_event("blue_green_bootstrap_activated", stable=release_id, active_slot="blue", security_delta="NONE")
    print(json.dumps(load_state(), indent=2, sort_keys=True))
    print("BLUE_GREEN_BOOTSTRAP_OK")


def stage() -> None:
    require_root()
    state = load_state()
    if state["state"] not in {"STABLE", "LIFECYCLE_ACCEPTED"}:
        die(f"cannot stage from state {state['state']}")
    manifest_path = PROJECT / "candidate/release.json"
    manifest = load_json(manifest_path)
    required = {"cycle_id", "kind", "authority_delta", "expected_tool_count", "expected_tool_schema_sha256"}
    missing = sorted(required - manifest.keys())
    if missing:
        die(f"candidate manifest missing fields: {missing}")
    if manifest["authority_delta"] != "NONE":
        die("candidate requests an authority delta; explicit permission path required")
    expected_count = int(manifest["expected_tool_count"])
    expected_schema = str(manifest["expected_tool_schema_sha256"])
    if not expected_schema or len(expected_schema) != 64:
        die("candidate expected schema hash is invalid")

    tests = run_as_mcp(RUNTIME_PYTHON, PROJECT, ["-m", "pytest", "-q"])
    if tests.returncode:
        die(f"candidate tests failed: {tests.stdout}{tests.stderr}")
    regress = run_as_mcp(Path("/home/mcp/agent/.venv/bin/python"), GUARDRAIL_SOURCE, ["-m", "pytest", "-q"], 300)
    if regress.returncode:
        die(f"guardrail regression failed: {regress.stdout}{regress.stderr}")
    verify_fixed_confinement()

    release_meta = {**manifest, "guardrail_release": state["guardrail_release"], "policy_version": state["policy_version"]}
    release_id, source_sha, release_dir = stage_frontend_release(release_meta)
    inactive = "green" if state["active_slot"] == "blue" else "blue"
    slot_env(inactive, release_id, release_dir, source_sha, state["guardrail_release"], expected_count, expected_schema)
    systemctl("enable", f"mcp-evolution-{inactive}.service")
    systemctl("restart", f"mcp-evolution-{inactive}.service")
    wait_port(PORTS[inactive])
    observed = verify_url(PORTS[inactive], expected_count, expected_schema)

    state.update(
        {
            "state": "READY_TO_ACTIVATE",
            "cycle_id": manifest["cycle_id"],
            "candidate": release_id,
            "candidate_slot": inactive,
            "candidate_source_sha256": source_sha,
            "candidate_expected_tool_count": expected_count,
            "candidate_expected_tool_schema_sha256": expected_schema,
            "security_authority_delta": "NONE",
            "gates": {
                "candidate_tests": "PASS",
                "guardrail_regression": "PASS",
                "secret_scan": "PASS",
                "confinement": "PASS",
                "inactive_slot_smoke": "PASS",
            },
        }
    )
    save_state(state)
    append_event(
        "candidate_ready",
        cycle_id=manifest["cycle_id"],
        release_id=release_id,
        inactive_slot=inactive,
        tool_count=observed["tool_count"],
        schema_sha256=observed["tool_schema_sha256"],
        security_delta="NONE",
    )
    print(json.dumps(state, indent=2, sort_keys=True))
    print(f"READY_TO_ACTIVATE {release_id}")


def activate(release_id: str) -> None:
    require_root()
    state = load_state()
    if state["state"] != "READY_TO_ACTIVATE" or state.get("candidate") != release_id:
        die("release is not the current READY_TO_ACTIVATE candidate")
    slot = state["candidate_slot"]
    verify_url(PORTS[slot], state["candidate_expected_tool_count"], state["candidate_expected_tool_schema_sha256"])
    previous_route = state["active_slot"]
    try:
        route_slot(slot)
        verify_url(FRONTDOOR_PORT, state["candidate_expected_tool_count"], state["candidate_expected_tool_schema_sha256"])
    except BaseException:
        route_slot(previous_route)
        raise
    state["active_slot"] = slot
    state["state"] = "FRESH_SESSION_VERIFY"
    state["activated_at"] = now()
    save_state(state)
    append_event("activated", cycle_id=state["cycle_id"], release_id=release_id, slot=slot, security_delta="NONE")
    print("ACTIVATED_UNPROMOTED")
    print("Refresh/reload Optiplex_MCP and open a fresh ChatGPT session.")
    print("Then read self-building-computer/NEXT_SESSION.md before promotion.")


def accept(cycle_id: str) -> None:
    require_root()
    state = load_state()
    if state["state"] != "FRESH_SESSION_VERIFY" or state.get("cycle_id") != cycle_id:
        die("cycle is not awaiting fresh-session verification")
    state["state"] = "PROMOTE_READY"
    state["fresh_session_accepted_at"] = now()
    save_state(state)
    append_event("fresh_session_verified", cycle_id=cycle_id, release_id=state["candidate"], security_delta="NONE")
    print("PROMOTE_READY")


def promote(cycle_id: str) -> None:
    require_root()
    state = load_state()
    if state["state"] != "PROMOTE_READY" or state.get("cycle_id") != cycle_id:
        die("cycle is not PROMOTE_READY")
    old_stable, old_slot = state["stable"], state["stable_slot"]
    state["previous"] = old_stable
    state["previous_slot"] = old_slot
    state["stable"] = state["candidate"]
    state["stable_slot"] = state["candidate_slot"]
    state["candidate"] = None
    state["candidate_slot"] = None
    state["state"] = "STABLE"
    state["promoted_at"] = now()
    save_state(state)
    append_event("promoted", cycle_id=cycle_id, from_release=old_stable, to_release=state["stable"], security_delta="NONE")
    print(f"PROMOTED {state['stable']}")


def rollback(drill: bool) -> None:
    require_root()
    state = load_state()
    if drill:
        if state["state"] not in {"STABLE", "LIFECYCLE_ACCEPTED"} or not state.get("previous") or not state.get("previous_slot"):
            die("rollback drill requires a promoted stable release with previous release")
        stable_slot = state["stable_slot"]
        previous_slot = state["previous_slot"]
        route_slot(previous_slot)
        verify_url(FRONTDOOR_PORT, state["expected_tool_count"], state["expected_tool_schema_sha256"])
        route_slot(stable_slot)
        verify_url(FRONTDOOR_PORT, state["expected_tool_count"], state["expected_tool_schema_sha256"])
        state["active_slot"] = stable_slot
        state["rollback_drill_passed"] = True
        state["rollback_drill_at"] = now()
        state["state"] = "LIFECYCLE_ACCEPTED"
        save_state(state)
        append_event("rollback_drill_passed", stable=state["stable"], previous=state["previous"], security_delta="NONE")
        print("ROLLBACK_DRILL_PASS LIFECYCLE_ACCEPTED")
        return

    if state["state"] not in {"FRESH_SESSION_VERIFY", "PROMOTE_READY"}:
        die("normal rollback is only valid for an active unpromoted candidate")
    stable_slot = state["stable_slot"]
    failed = state["candidate"]
    route_slot(stable_slot)
    verify_url(FRONTDOOR_PORT, state["expected_tool_count"], state["expected_tool_schema_sha256"])
    state["active_slot"] = stable_slot
    state["state"] = "ROLLED_BACK"
    state["failed_release"] = failed
    state["candidate"] = None
    state["candidate_slot"] = None
    save_state(state)
    append_event("rolled_back", cycle_id=state.get("cycle_id"), failed_release=failed, stable=state["stable"], security_delta="NONE")
    print(f"ROLLED_BACK {failed} -> {state['stable']}")


def status() -> None:
    state = load_state()
    payload = dict(state)
    payload["services"] = {}
    for name in ["mcp-evolution-guardrail.service", "mcp-evolution-blue.service", "mcp-evolution-green.service", "mcp-evolution-frontdoor.service", "mcp-agent.service"]:
        result = systemctl("is-active", name, check=False)
        payload["services"][name] = result.stdout.strip() or result.stderr.strip()
    print(json.dumps(payload, indent=2, sort_keys=True))


def run_slot(slot: str) -> None:
    if slot not in PORTS:
        die("invalid slot")
    env_path = SLOTS_DIR / f"{slot}.env"
    values = read_env(env_path)
    release_dir = Path(values["RELEASE_DIR"]).resolve()
    root = RELEASE_ROOT.resolve()
    if root not in release_dir.parents or not release_dir.is_dir():
        die("invalid release directory")
    env = os.environ.copy()
    env.update(
        {
            "MCP_FRONTEND_HOST": "127.0.0.1",
            "MCP_FRONTEND_PORT": values["PORT"],
            "MCP_GUARDRAIL_URL": f"http://127.0.0.1:{GUARDRAIL_PORT}/mcp",
            "MCP_EXPECTED_TOOL_COUNT": values["EXPECTED_TOOL_COUNT"],
            "MCP_EXPECTED_SCHEMA_SHA256": values["EXPECTED_SCHEMA_SHA256"],
            "MCP_EVOLUTION_RELEASE_ID": values["RELEASE_ID"],
            "MCP_EVOLUTION_SOURCE_SHA256": values["SOURCE_SHA256"],
            "MCP_GUARDRAIL_RELEASE_ID": values["GUARDRAIL_RELEASE_ID"],
            "MCP_POLICY_VERSION": values["POLICY_VERSION"],
            "PYTHONPATH": str(release_dir),
        }
    )
    os.chdir(release_dir)
    os.execve(str(RUNTIME_PYTHON), [str(RUNTIME_PYTHON), "-m", "mcp_frontend.server"], env)


def run_guardrail() -> None:
    values = read_env(ETC_DIR / "guardrail.env")
    release_dir = Path(values["RELEASE_DIR"]).resolve()
    root = GUARDRAIL_ROOT.resolve()
    if root not in release_dir.parents or not release_dir.is_dir():
        die("invalid guardrail release directory")
    env = os.environ.copy()
    env.update({"MCP_AGENT_HOST": "127.0.0.1", "MCP_AGENT_PORT": values["PORT"], "PYTHONPATH": str(release_dir)})
    os.chdir(release_dir)
    os.execve("/home/mcp/agent/.venv/bin/python", ["/home/mcp/agent/.venv/bin/python", "-m", "mcp_agent.server"], env)


def run_frontdoor() -> None:
    values = read_env(ETC_DIR / "frontdoor.env")
    port = int(values["TARGET_PORT"])
    if port not in PORTS.values():
        die("invalid frontdoor target port")
    os.execvp("socat", ["socat", f"TCP-LISTEN:{FRONTDOOR_PORT},bind=127.0.0.1,reuseaddr,fork", f"TCP:127.0.0.1:{port}"])


def main() -> None:
    parser = argparse.ArgumentParser(prog="mcp-evolution")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("bootstrap")
    sub.add_parser("stage")
    act = sub.add_parser("activate"); act.add_argument("release_id")
    acc = sub.add_parser("accept"); acc.add_argument("cycle_id")
    pro = sub.add_parser("promote"); pro.add_argument("cycle_id")
    rb = sub.add_parser("rollback"); rb.add_argument("--drill", action="store_true")
    sub.add_parser("status")
    rs = sub.add_parser("run-slot"); rs.add_argument("slot")
    sub.add_parser("run-guardrail")
    sub.add_parser("run-frontdoor")
    args = parser.parse_args()

    if args.command == "run-slot": run_slot(args.slot)
    elif args.command == "run-guardrail": run_guardrail()
    elif args.command == "run-frontdoor": run_frontdoor()
    elif args.command == "bootstrap": bootstrap()
    elif args.command == "stage": stage()
    elif args.command == "activate": activate(args.release_id)
    elif args.command == "accept": accept(args.cycle_id)
    elif args.command == "promote": promote(args.cycle_id)
    elif args.command == "rollback": rollback(args.drill)
    elif args.command == "status": status()


if __name__ == "__main__":
    main()
