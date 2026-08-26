#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import py_compile
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import venv
from datetime import datetime, timezone
from typing import Any

try:
    import jsonschema
except Exception as exc:  # pragma: no cover
    raise SystemExit(f"jsonschema is required: {exc}")

VERSION = "gen6-capability-forge-r2"
CONTRACT_VERSION = "capability-contract-v1"
EVALUATOR_VERSION = "gen5-nursery-r1"
GOVERNOR_VERSION = "gen6-promotion-governor-r2"
ROOT = pathlib.Path(os.environ.get("OPTIPLEX_FORGE_ROOT", "/var/lib/optiplex-lab/capabilities"))
OBJECTS = ROOT / "objects"
WORKSPACES = ROOT / "workspaces"
ENVS = ROOT / "envs"
REGISTRY = ROOT / "registry.json"
PROVENANCE = ROOT / "provenance.jsonl"
RUN_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_FORGE_RUN_ROOT", "/var/lib/optiplex-lab/capability-runs"))
TRACE = pathlib.Path(os.environ.get("OPTIPLEX_FORGE_TRACE", "/var/lib/optiplex-lab/traces/events.jsonl"))
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
ALLOWED_SIDE_EFFECTS = {"read_files", "write_workspace", "public_network", "service", "subprocess"}
FORBIDDEN_AUTHORITY = {
    "host_credentials", "host_mounts", "host_sockets", "docker_socket", "libvirt_socket",
    "tailscale_socket", "private_network", "production_authority", "safe_mcp_authority",
    "host_repository", "host_repo_write", "lan_access", "tailscale_access",
}
LIFECYCLE = {"EPHEMERAL", "CANDIDATE", "PROMOTED", "SUPERSEDED", "REJECTED", "EXPIRED"}
MAX_SOURCE_BYTES = 512 * 1024
MAX_OUTPUT_BYTES = 256 * 1024
MAX_TIMEOUT_S = 30
MAX_PIP_DEPS = 16
REGRESSION_COMPILER_PATH = pathlib.Path(os.environ.get("OPTIPLEX_REGRESSION_COMPILER_PATH", "/opt/optiplex-lab/regression_compiler.py"))


class ForgeError(RuntimeError):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_json(value: Any) -> str:
    return sha_bytes(canonical_bytes(value))


def safe_write_json(path: pathlib.Path, value: Any, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp, mode)
    tmp.replace(path)


def append_jsonl(path: pathlib.Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def emit(event: str, **fields: Any) -> None:
    rec = {"timestamp": utc(), "tool": "capability_forge", "event": event, "forge_version": VERSION, **fields}
    append_jsonl(PROVENANCE, rec)
    try:
        append_jsonl(TRACE, rec)
    except Exception:
        pass


def init_root() -> None:
    for p in (ROOT, OBJECTS, WORKSPACES, ENVS, RUN_ROOT):
        p.mkdir(parents=True, exist_ok=True)
    if not REGISTRY.exists():
        safe_write_json(REGISTRY, {"version": VERSION, "capabilities": {}})


def load_registry() -> dict[str, Any]:
    init_root()
    try:
        value = json.loads(REGISTRY.read_text())
    except Exception as exc:
        raise ForgeError(f"registry unreadable: {exc}")
    if not isinstance(value, dict) or not isinstance(value.get("capabilities"), dict):
        raise ForgeError("registry malformed")
    return value


def save_registry(reg: dict[str, Any]) -> None:
    reg["version"] = VERSION
    safe_write_json(REGISTRY, reg)


def validate_name(value: str, label: str) -> None:
    if not NAME_RE.fullmatch(value):
        raise ForgeError(f"invalid {label}: {value!r}")


def _scan_forbidden(node: Any, trail: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            key = str(k).lower().replace("-", "_")
            if key in {"authority", "requested_authority", "permissions", "host_access"}:
                words = set(re.findall(r"[a-z0-9_]+", json.dumps(v).lower().replace("-", "_")))
                if words & FORBIDDEN_AUTHORITY:
                    hits.append(f"{trail}.{k}:{sorted(words & FORBIDDEN_AUTHORITY)}")
            hits.extend(_scan_forbidden(v, f"{trail}.{k}"))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hits.extend(_scan_forbidden(v, f"{trail}[{i}]"))
    elif isinstance(node, str):
        normalized = node.lower().replace("-", "_").replace(" ", "_")
        if normalized in FORBIDDEN_AUTHORITY:
            hits.append(f"{trail}:{normalized}")
    return hits


def validate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise ForgeError("contract must be an object")
    required = {
        "schema_version", "name", "version", "purpose", "input_schema", "output_schema",
        "entrypoint", "dependencies", "side_effects", "applicability", "evaluation", "provenance",
        "lifecycle", "ttl",
    }
    missing = sorted(required - set(contract))
    if missing:
        raise ForgeError(f"contract missing fields: {missing}")
    if contract.get("schema_version") != CONTRACT_VERSION:
        raise ForgeError(f"unsupported schema_version: {contract.get('schema_version')!r}")
    name, version = str(contract["name"]), str(contract["version"])
    validate_name(name, "capability name")
    validate_name(version, "capability version")
    if not isinstance(contract.get("purpose"), str) or not contract["purpose"].strip():
        raise ForgeError("purpose must be a non-empty string")
    for k in ("input_schema", "output_schema"):
        if not isinstance(contract.get(k), dict):
            raise ForgeError(f"{k} must be an object")
        try:
            jsonschema.Draft202012Validator.check_schema(contract[k])
        except Exception as exc:
            raise ForgeError(f"invalid {k}: {exc}")
    entry = contract.get("entrypoint")
    if not isinstance(entry, list) or not entry or not all(isinstance(x, str) and x for x in entry):
        raise ForgeError("entrypoint must be a non-empty list[str]")
    if entry[0] not in {"python", "python3"} and pathlib.PurePath(entry[0]).is_absolute():
        raise ForgeError("absolute executable entrypoints are not allowed in capability contracts")
    deps = contract.get("dependencies")
    if not isinstance(deps, dict) or set(deps) - {"pip"}:
        raise ForgeError("dependencies supports only the pip key in Gen5")
    pip_deps = deps.get("pip", [])
    if not isinstance(pip_deps, list) or len(pip_deps) > MAX_PIP_DEPS or not all(isinstance(x, str) and x for x in pip_deps):
        raise ForgeError("dependencies.pip must be a bounded list[str]")
    side = contract.get("side_effects")
    if not isinstance(side, list) or len(side) != len(set(side)):
        raise ForgeError("side_effects must be a unique list")
    unknown_side = sorted(set(side) - ALLOWED_SIDE_EFFECTS)
    if unknown_side:
        raise ForgeError(f"forbidden/unknown side effects: {unknown_side}")
    forbidden = _scan_forbidden(contract)
    if forbidden:
        raise ForgeError(f"forbidden authority declaration: {forbidden[:4]}")
    applicability = contract.get("applicability")
    if not isinstance(applicability, list) or not all(isinstance(x, str) and x.strip() for x in applicability):
        raise ForgeError("applicability must be list[str]")
    evaluation = contract.get("evaluation")
    if not isinstance(evaluation, dict) or not isinstance(evaluation.get("cases"), list) or not evaluation["cases"]:
        raise ForgeError("evaluation.cases must be a non-empty list")
    kinds: set[str] = set()
    names: set[str] = set()
    for case in evaluation["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("name"), str):
            raise ForgeError("every evaluation case requires a name")
        if case["name"] in names:
            raise ForgeError("evaluation case names must be unique")
        names.add(case["name"])
        kind = str(case.get("kind", "positive"))
        if kind not in {"positive", "negative", "adversarial", "property"}:
            raise ForgeError(f"unsupported evaluation kind: {kind}")
        kinds.add(kind)
        if "input" not in case:
            raise ForgeError(f"evaluation case {case['name']} missing input")
        verdict_fields = [x for x in ("expected", "expect_error") if x in case]
        if len(verdict_fields) != 1:
            raise ForgeError(f"evaluation case {case['name']} needs exactly one expected/expect_error")
    if "positive" not in kinds or not ({"negative", "adversarial", "property"} & kinds):
        raise ForgeError("evaluation must include positive and negative/adversarial/property evidence")
    lifecycle = contract.get("lifecycle")
    if lifecycle not in {"EPHEMERAL", "CANDIDATE"}:
        raise ForgeError("new capabilities may start only EPHEMERAL or CANDIDATE")
    ttl = contract.get("ttl")
    if not isinstance(ttl, dict) or not isinstance(ttl.get("hours"), int) or not (0 <= ttl["hours"] <= 24 * 365):
        raise ForgeError("ttl.hours must be an integer from 0 to 8760")
    limits = contract.get("limits", {})
    if not isinstance(limits, dict):
        raise ForgeError("limits must be an object")
    timeout_s = int(limits.get("timeout_s", 10))
    max_output = int(limits.get("max_output_bytes", 64 * 1024))
    if not (1 <= timeout_s <= MAX_TIMEOUT_S):
        raise ForgeError(f"timeout_s must be 1..{MAX_TIMEOUT_S}")
    if not (128 <= max_output <= MAX_OUTPUT_BYTES):
        raise ForgeError(f"max_output_bytes must be 128..{MAX_OUTPUT_BYTES}")
    provenance = contract.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("creator") or not provenance.get("creator_episode"):
        raise ForgeError("provenance requires creator and creator_episode")
    return {"name": name, "version": version, "evaluation_kinds": sorted(kinds), "side_effects": sorted(side)}


def _contract_core(contract: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in contract.items() if k not in {"content_hash"}}


def workspace_hash(workspace: pathlib.Path, contract: dict[str, Any]) -> tuple[str, list[dict[str, Any]], int]:
    files: list[dict[str, Any]] = []
    total = 0
    for p in sorted(x for x in workspace.rglob("*") if x.is_file()):
        rel = p.relative_to(workspace).as_posix()
        if rel in {"gap.json", "seal-result.json"} or rel.startswith(".forge-"):
            continue
        data = p.read_bytes()
        if rel == "capability.json":
            data = canonical_bytes(_contract_core(contract))
        total += len(data)
        if total > MAX_SOURCE_BYTES:
            raise ForgeError(f"capability bundle exceeds {MAX_SOURCE_BYTES} bytes")
        files.append({"path": rel, "sha256": sha_bytes(data), "bytes": len(data)})
    payload = {"contract": _contract_core(contract), "files": files}
    return sha_json(payload), files, total


def object_path(content_hash: str) -> pathlib.Path:
    if not re.fullmatch(r"[0-9a-f]{64}", content_hash):
        raise ForgeError("invalid content hash")
    return OBJECTS / content_hash


def registry_record(reg: dict[str, Any], content_hash: str) -> dict[str, Any]:
    rec = reg["capabilities"].get(content_hash)
    if not isinstance(rec, dict):
        raise ForgeError(f"capability not found: {content_hash}")
    return rec


def resolve_capability(ref: str) -> tuple[str, dict[str, Any]]:
    reg = load_registry()
    if re.fullmatch(r"[0-9a-f]{64}", ref):
        return ref, registry_record(reg, ref)
    matches = [(h, r) for h, r in reg["capabilities"].items() if r.get("name") == ref and r.get("state") not in {"REJECTED", "EXPIRED", "SUPERSEDED"}]
    if len(matches) != 1:
        raise ForgeError(f"capability name {ref!r} resolved to {len(matches)} active candidates; use hash")
    return matches[0]


def tokens(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", text.lower()) if len(x) > 2}


def search(gap: dict[str, Any]) -> list[dict[str, Any]]:
    reg = load_registry()
    desired_name = str(gap.get("desired_name", ""))
    purpose_tokens = tokens(str(gap.get("purpose", "")))
    wanted_tags = {str(x).lower() for x in gap.get("applicability", []) if isinstance(x, str)}
    out = []
    for h, rec in reg["capabilities"].items():
        if rec.get("state") in {"REJECTED", "EXPIRED", "SUPERSEDED"}:
            continue
        score_reasons = []
        if desired_name and rec.get("name") == desired_name:
            score_reasons.append("exact_name")
        tags = {str(x).lower() for x in rec.get("applicability", [])}
        tag_union = wanted_tags | tags
        tag_overlap = len(wanted_tags & tags) / len(tag_union) if tag_union else 0.0
        rec_tokens = tokens(str(rec.get("purpose", "")))
        tok_union = purpose_tokens | rec_tokens
        purpose_overlap = len(purpose_tokens & rec_tokens) / len(tok_union) if tok_union else 0.0
        if tag_overlap >= 0.5:
            score_reasons.append(f"tag_overlap={tag_overlap:.2f}")
        if purpose_overlap >= 0.35:
            score_reasons.append(f"purpose_overlap={purpose_overlap:.2f}")
        if score_reasons:
            out.append({"content_hash": h, "name": rec.get("name"), "version": rec.get("version"), "state": rec.get("state"), "reasons": score_reasons, "tag_overlap": round(tag_overlap, 3), "purpose_overlap": round(purpose_overlap, 3)})
    out.sort(key=lambda x: ("exact_name" not in x["reasons"], -x["tag_overlap"], -x["purpose_overlap"], x["name"] or ""))
    return out


def open_gap(gap: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(gap, dict) or not isinstance(gap.get("purpose"), str) or not gap["purpose"].strip():
        raise ForgeError("gap requires purpose")
    matches = search(gap)
    if matches and ("exact_name" in matches[0]["reasons"] or matches[0]["tag_overlap"] >= 0.75):
        emit("gap_reuse", gap_hash=sha_json(gap), selected=matches[0]["content_hash"], reasons=matches[0]["reasons"])
        return {"action": "REUSE", "gap_hash": sha_json(gap), "selected": matches[0], "matches": matches[:5]}
    workspace_id = f"gap_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    workspace = WORKSPACES / workspace_id
    workspace.mkdir(parents=True, exist_ok=False)
    safe_write_json(workspace / "gap.json", gap)
    emit("gap_workspace_created", gap_hash=sha_json(gap), workspace_id=workspace_id, workspace=str(workspace), matches=len(matches))
    return {"action": "CREATE", "gap_hash": sha_json(gap), "workspace_id": workspace_id, "workspace": str(workspace), "matches": matches[:5]}


def _copy_workspace(workspace: pathlib.Path, dst: pathlib.Path) -> None:
    dst.mkdir(parents=True, exist_ok=False)
    for p in workspace.rglob("*"):
        rel = p.relative_to(workspace)
        if rel.as_posix() in {"gap.json", "seal-result.json"} or rel.as_posix().startswith(".forge-"):
            continue
        q = dst / rel
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
        elif p.is_file():
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)


def seal(workspace_ref: str) -> dict[str, Any]:
    init_root()
    workspace = pathlib.Path(workspace_ref)
    if not workspace.is_absolute():
        workspace = WORKSPACES / workspace_ref
    if not workspace.is_dir():
        raise ForgeError(f"workspace not found: {workspace_ref}")
    contract_path = workspace / "capability.json"
    if not contract_path.is_file():
        raise ForgeError("workspace missing capability.json")
    try:
        contract = json.loads(contract_path.read_text())
    except Exception as exc:
        raise ForgeError(f"capability.json malformed: {exc}")
    summary = validate_contract(contract)
    content_hash, files, total = workspace_hash(workspace, contract)
    dst = object_path(content_hash)
    reg = load_registry()
    if dst.exists():
        rec = registry_record(reg, content_hash)
        rec["duplicate_reuse_count"] = int(rec.get("duplicate_reuse_count", 0)) + 1
        rec["last_seen_at"] = utc()
        save_registry(reg)
        emit("duplicate_reused", content_hash=content_hash, name=rec.get("name"), workspace=str(workspace))
        result = {"state": "DUPLICATE_REUSED", "content_hash": content_hash, "object": str(dst), "record": rec}
        safe_write_json(workspace / "seal-result.json", result)
        return result
    _copy_workspace(workspace, dst)
    contract = dict(contract)
    contract["content_hash"] = content_hash
    safe_write_json(dst / "capability.json", contract)
    gap = {}
    if (workspace / "gap.json").exists():
        try: gap = json.loads((workspace / "gap.json").read_text())
        except Exception: gap = {}
    now = utc()
    evaluator_hash = sha_json({"version": EVALUATOR_VERSION, "evaluation": contract["evaluation"]})
    rec = {
        "name": contract["name"], "version": contract["version"], "content_hash": content_hash,
        "purpose": contract["purpose"], "applicability": contract["applicability"], "state": contract["lifecycle"],
        "created_at": now, "last_seen_at": now, "object": str(dst), "source_files": files, "source_bytes": total,
        "source_hashes": {f["path"]: f["sha256"] for f in files}, "evaluator_hash": evaluator_hash,
        "evaluator_version": EVALUATOR_VERSION, "creator": contract["provenance"].get("creator"),
        "creator_episode": contract["provenance"].get("creator_episode"), "gap_hash": sha_json(gap) if gap else contract["provenance"].get("gap_hash"),
        "side_effects": sorted(contract["side_effects"]), "dependencies": contract["dependencies"],
        "evaluation_runs": 0, "evaluation_passes": 0, "real_task_attempts": 0, "real_task_successes": 0,
        "reuse_count": 0, "duplicate_reuse_count": 0, "governor_decisions": [], "expired_object_removed": False,
    }
    reg["capabilities"][content_hash] = rec
    save_registry(reg)
    emit("sealed", content_hash=content_hash, name=contract["name"], version=contract["version"], state=rec["state"], source_bytes=total, evaluator_hash=evaluator_hash, summary=summary)
    result = {"state": "SEALED", "content_hash": content_hash, "object": str(dst), "record": rec}
    safe_write_json(workspace / "seal-result.json", result)
    return result


def contract_for(content_hash: str) -> tuple[pathlib.Path, dict[str, Any]]:
    root = object_path(content_hash)
    path = root / "capability.json"
    if not path.exists():
        raise ForgeError(f"capability object unavailable: {content_hash}")
    contract = json.loads(path.read_text())
    validate_contract(contract)
    actual, _, _ = workspace_hash(root, contract)
    if actual != content_hash:
        raise ForgeError(f"capability object content hash mismatch: expected {content_hash}, got {actual}")
    return root, contract


def ensure_env(content_hash: str, contract: dict[str, Any]) -> dict[str, Any]:
    deps = list(contract.get("dependencies", {}).get("pip", []))
    if not deps:
        return {"ok": True, "python": "/opt/optiplex-lab/venv/bin/python", "dependency_count": 0, "env": None, "installed": False}
    env_dir = ENVS / content_hash
    marker = env_dir / ".forge-ready.json"
    if marker.exists():
        try:
            meta = json.loads(marker.read_text())
            if meta.get("dependencies_hash") == sha_json(deps):
                return {"ok": True, "python": str(env_dir / "bin/python"), "dependency_count": len(deps), "env": str(env_dir), "installed": False}
        except Exception:
            pass
    if env_dir.exists():
        shutil.rmtree(env_dir)
    started = time.monotonic()
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(env_dir)
        p = subprocess.run([str(env_dir / "bin/python"), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *deps], capture_output=True, text=True, timeout=180, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "dependency install timeout", "dependency_count": len(deps), "duration_ms": round((time.monotonic()-started)*1000, 2)}
    if p.returncode != 0:
        shutil.rmtree(env_dir, ignore_errors=True)
        return {"ok": False, "error": "dependency install failed", "dependency_count": len(deps), "stderr_preview": p.stderr[-1500:], "duration_ms": round((time.monotonic()-started)*1000, 2)}
    meta = {"dependencies_hash": sha_json(deps), "dependencies": deps, "ready_at": utc()}
    safe_write_json(marker, meta)
    return {"ok": True, "python": str(env_dir / "bin/python"), "dependency_count": len(deps), "env": str(env_dir), "installed": True, "duration_ms": round((time.monotonic()-started)*1000, 2)}


def syntax_check(root: pathlib.Path) -> dict[str, Any]:
    checked = []
    for p in sorted(root.rglob("*.py")):
        if ".venv" in p.parts:
            continue
        try:
            compile(p.read_text(encoding="utf-8"), str(p), "exec")
            checked.append(str(p.relative_to(root)))
        except Exception as exc:
            return {"ok": False, "checked": checked, "error": f"{p.name}: {exc}"}
    return {"ok": True, "checked": checked}


def containment_probe() -> dict[str, Any]:
    blocked = []
    unexpected = []
    for host, port in [("192.168.127.1", 8790), ("10.0.0.1", 22), ("172.16.0.1", 22), ("100.64.0.1", 22)]:
        s = socket.socket(); s.settimeout(0.25)
        try:
            s.connect((host, port)); unexpected.append(f"{host}:{port}")
        except OSError:
            blocked.append(f"{host}:{port}")
        finally:
            s.close()
    sockets = [p for p in ["/var/run/docker.sock", "/run/docker.sock", "/var/run/libvirt/libvirt-sock", "/run/libvirt/libvirt-sock", "/var/run/tailscale/tailscaled.sock"] if pathlib.Path(p).exists()]
    host_repo = pathlib.Path("/home/mcp/projects/projects/self-building-computer").exists()
    ok = not unexpected and not sockets and not host_repo
    return {"ok": ok, "blocked": blocked, "unexpected_reachable": unexpected, "host_control_sockets": sockets, "host_repository_present": host_repo}


def _entry_argv(root: pathlib.Path, contract: dict[str, Any], python: str) -> list[str]:
    raw = list(contract["entrypoint"])
    if raw[0] in {"python", "python3"}:
        raw[0] = python
    else:
        exe = root / raw[0]
        if not exe.exists():
            raise ForgeError(f"entrypoint executable missing: {raw[0]}")
        raw[0] = str(exe)
    for i in range(1, len(raw)):
        if raw[i].startswith("-"):
            continue
        candidate = root / raw[i]
        if candidate.exists():
            raw[i] = str(candidate)
    return raw


def invoke_raw(content_hash: str, input_value: Any, *, real_task: bool = False, context: str | None = None, mutate_registry: bool = True) -> dict[str, Any]:
    root, contract = contract_for(content_hash)
    try:
        jsonschema.validate(input_value, contract["input_schema"])
    except Exception as exc:
        result = {"ok": False, "phase": "input_validation", "error": f"{type(exc).__name__}: {exc}"}
        if real_task and mutate_registry:
            record_real_task(content_hash, result, context)
        return result
    dep = ensure_env(content_hash, contract)
    if not dep.get("ok"):
        result = {"ok": False, "phase": "dependencies", "dependency": dep}
        if real_task and mutate_registry:
            record_real_task(content_hash, result, context)
        return result
    run_id = f"cap_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    run_dir = RUN_ROOT / run_id; run_dir.mkdir(parents=True, exist_ok=False)
    safe_write_json(run_dir / "input.json", input_value, 0o600)
    argv = _entry_argv(root, contract, str(dep["python"]))
    timeout_s = int(contract.get("limits", {}).get("timeout_s", 10))
    max_output = int(contract.get("limits", {}).get("max_output_bytes", 64 * 1024))
    env = os.environ.copy(); env.update({"CAPABILITY_ROOT": str(root), "CAPABILITY_RUN_DIR": str(run_dir), "CAPABILITY_CONTENT_HASH": content_hash})
    started = time.monotonic()
    try:
        p = subprocess.run(argv, input=canonical_bytes(input_value) + b"\n", cwd=root, env=env, capture_output=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired as exc:
        result = {"ok": False, "phase": "execute", "error": f"timeout after {timeout_s}s", "exit_code": 124, "duration_ms": round((time.monotonic()-started)*1000, 2), "stdout_bytes": len(exc.stdout or b""), "stderr_bytes": len(exc.stderr or b""), "run_id": run_id, "run_dir": str(run_dir)}
        safe_write_json(run_dir / "result.json", result)
        emit("invoke", content_hash=content_hash, run_id=run_id, ok=False, phase="execute", error="timeout", real_task=real_task)
        if real_task and mutate_registry: record_real_task(content_hash, result, context)
        return result
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    (run_dir / "stdout.bin").write_bytes(p.stdout); (run_dir / "stderr.bin").write_bytes(p.stderr)
    if len(p.stdout) > max_output or len(p.stderr) > max_output:
        result = {"ok": False, "phase": "execute", "error": "excessive output", "exit_code": p.returncode, "stdout_bytes": len(p.stdout), "stderr_bytes": len(p.stderr), "max_output_bytes": max_output, "duration_ms": duration_ms, "run_id": run_id, "run_dir": str(run_dir)}
    elif p.returncode != 0:
        result = {"ok": False, "phase": "execute", "error": f"entrypoint exit {p.returncode}", "exit_code": p.returncode, "stderr_preview": p.stderr.decode(errors="replace")[-1200:], "stdout_preview": p.stdout.decode(errors="replace")[:1200], "duration_ms": duration_ms, "run_id": run_id, "run_dir": str(run_dir)}
    else:
        try:
            output = json.loads(p.stdout.decode())
            jsonschema.validate(output, contract["output_schema"])
            result = {"ok": True, "phase": "complete", "output": output, "exit_code": 0, "stdout_bytes": len(p.stdout), "stderr_bytes": len(p.stderr), "duration_ms": duration_ms, "run_id": run_id, "run_dir": str(run_dir)}
        except Exception as exc:
            result = {"ok": False, "phase": "output_validation", "error": f"{type(exc).__name__}: {exc}", "exit_code": 0, "stdout_preview": p.stdout.decode(errors="replace")[:1200], "duration_ms": duration_ms, "run_id": run_id, "run_dir": str(run_dir)}
    safe_write_json(run_dir / "result.json", result)
    emit("invoke", content_hash=content_hash, run_id=run_id, ok=bool(result.get("ok")), phase=result.get("phase"), real_task=real_task, context_hash=sha_bytes((context or "").encode()) if context else None, duration_ms=duration_ms)
    if real_task and mutate_registry:
        record_real_task(content_hash, result, context)
    return result


def record_real_task(content_hash: str, result: dict[str, Any], context: str | None) -> None:
    reg = load_registry(); rec = registry_record(reg, content_hash)
    rec["real_task_attempts"] = int(rec.get("real_task_attempts", 0)) + 1
    if result.get("ok"):
        rec["real_task_successes"] = int(rec.get("real_task_successes", 0)) + 1
        rec["reuse_count"] = max(0, int(rec["real_task_successes"]) - 1)
    rec["last_real_task_at"] = utc(); rec["last_seen_at"] = utc()
    rec["last_real_task"] = {"ok": bool(result.get("ok")), "run_id": result.get("run_id"), "context_hash": sha_bytes((context or "").encode()) if context else None}
    save_registry(reg)
    emit("real_task_evidence", content_hash=content_hash, ok=bool(result.get("ok")), run_id=result.get("run_id"), real_task_successes=rec["real_task_successes"], reuse_count=rec["reuse_count"])


def evaluate(content_hash: str) -> dict[str, Any]:
    root, contract = contract_for(content_hash)
    started = time.monotonic()
    syntax = syntax_check(root)
    containment_before = containment_probe()
    dep = ensure_env(content_hash, contract) if syntax.get("ok") else {"ok": False, "skipped": True}
    cases = []
    if syntax.get("ok") and dep.get("ok") and containment_before.get("ok"):
        for case in contract["evaluation"]["cases"]:
            inv = invoke_raw(content_hash, case["input"], mutate_registry=False)
            if case.get("expect_error") is True:
                passed = not inv.get("ok")
                detail = {"observed_ok": bool(inv.get("ok")), "phase": inv.get("phase"), "error": inv.get("error")}
            else:
                passed = bool(inv.get("ok")) and inv.get("output") == case.get("expected")
                detail = {"observed_ok": bool(inv.get("ok")), "observed": inv.get("output"), "expected": case.get("expected")}
            cases.append({"name": case["name"], "kind": case.get("kind", "positive"), "passed": passed, "detail": detail, "run_id": inv.get("run_id")})
    containment_after = containment_probe()
    passed = bool(syntax.get("ok") and dep.get("ok") and containment_before.get("ok") and containment_after.get("ok") and cases and all(x["passed"] for x in cases))
    result = {
        "forge_version": VERSION, "evaluator_version": EVALUATOR_VERSION,
        "evaluator_hash": sha_json({"version": EVALUATOR_VERSION, "evaluation": contract["evaluation"]}),
        "content_hash": content_hash, "ok": passed, "syntax": syntax, "dependencies": dep,
        "containment_before": containment_before, "containment_after": containment_after,
        "cases": cases, "passed_cases": sum(1 for x in cases if x["passed"]), "total_cases": len(cases),
        "duration_ms": round((time.monotonic()-started)*1000, 2), "evaluated_at": utc(),
    }
    eval_dir = RUN_ROOT / f"eval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    eval_dir.mkdir(parents=True, exist_ok=False); safe_write_json(eval_dir / "result.json", result)
    result["result_path"] = str(eval_dir / "result.json")
    safe_write_json(eval_dir / "result.json", result)
    reg = load_registry(); rec = registry_record(reg, content_hash)
    rec["evaluation_runs"] = int(rec.get("evaluation_runs", 0)) + 1
    if passed: rec["evaluation_passes"] = int(rec.get("evaluation_passes", 0)) + 1
    rec["last_evaluation"] = {"ok": passed, "result_path": result["result_path"], "evaluator_hash": result["evaluator_hash"], "passed_cases": result["passed_cases"], "total_cases": result["total_cases"]}
    if not passed and rec.get("state") != "PROMOTED":
        rec["state"] = "REJECTED"; rec["rejection_reason"] = "evaluation_failed"
    rec["last_seen_at"] = utc(); save_registry(reg)
    emit("evaluation", content_hash=content_hash, ok=passed, result_path=result["result_path"], evaluator_hash=result["evaluator_hash"], passed_cases=result["passed_cases"], total_cases=result["total_cases"], state=rec["state"])
    return result


def _regression_gate(content_hash: str, rec: dict[str, Any]) -> dict[str, Any]:
    if not REGRESSION_COMPILER_PATH.is_file():
        return {"ok": True, "version": None, "relevant": 0, "passed": 0, "failed": 0, "results": [], "status": "compiler_unavailable"}
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"gen6_regression_{uuid.uuid4().hex}", REGRESSION_COMPILER_PATH)
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load regression compiler")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module.promotion_gate_for_record(rec, lambda inp: invoke_raw(content_hash, inp, mutate_registry=False))
    except Exception as exc:
        return {"ok": False, "version": None, "relevant": 0, "passed": 0, "failed": 1, "results": [], "status": "compiler_error", "error": f"{type(exc).__name__}: {exc}"}

def govern(content_hash: str) -> dict[str, Any]:
    reg = load_registry(); rec = registry_record(reg, content_hash)
    last = rec.get("last_evaluation") or {}
    hard_gates = {
        "object_available": object_path(content_hash).exists(),
        "evaluation_passed": bool(last.get("ok")),
        "evaluator_identity_matches": last.get("evaluator_hash") == rec.get("evaluator_hash"),
        "not_rejected_or_expired": rec.get("state") not in {"REJECTED", "EXPIRED"},
        "authority_contract_valid": True,
    }
    try:
        _, contract = contract_for(content_hash); validate_contract(contract)
    except Exception:
        hard_gates["authority_contract_valid"] = False
        contract = {}
    regression_gate = _regression_gate(content_hash, rec)
    hard_gates["regressions_passed"] = bool(regression_gate.get("ok"))
    evidence = {
        "regressions": regression_gate,
        "task_success": {"attempts": int(rec.get("real_task_attempts", 0)), "successes": int(rec.get("real_task_successes", 0))},
        "tests": {"evaluation_runs": int(rec.get("evaluation_runs", 0)), "evaluation_passes": int(rec.get("evaluation_passes", 0)), "cases_passed": last.get("passed_cases"), "cases_total": last.get("total_cases")},
        "recurrence_reuse": {"reuse_count": int(rec.get("reuse_count", 0)), "duplicate_reuse_count": int(rec.get("duplicate_reuse_count", 0))},
        "overlap": {"same_name_active": sum(1 for h, r in reg["capabilities"].items() if h != content_hash and r.get("name") == rec.get("name") and r.get("state") not in {"REJECTED", "EXPIRED", "SUPERSEDED"})},
        "dependency_cost": {"pip_dependencies": len((rec.get("dependencies") or {}).get("pip", []))},
        "generality": {"applicability_tags": len(rec.get("applicability", []))},
        "side_effects": {"declared": rec.get("side_effects", []), "count": len(rec.get("side_effects", []))},
        "maintenance": {"source_bytes": int(rec.get("source_bytes", 0)), "source_files": len(rec.get("source_files", []))},
    }
    if not all(hard_gates.values()):
        decision = "REJECT"
    elif rec.get("state") == "EPHEMERAL" and int(rec.get("real_task_successes", 0)) == 0:
        decision = "KEEP_EPHEMERAL"
    elif (
        int(rec.get("real_task_successes", 0)) >= 2
        and int(rec.get("reuse_count", 0)) >= 1
        and evidence["overlap"]["same_name_active"] == 0
        and evidence["dependency_cost"]["pip_dependencies"] <= 3
        and evidence["maintenance"]["source_bytes"] <= 128 * 1024
        and evidence["side_effects"]["count"] <= 3
    ):
        decision = "PROMOTE"
    else:
        decision = "KEEP_CANDIDATE" if rec.get("state") != "EPHEMERAL" else "KEEP_EPHEMERAL"
    transition = {"PROMOTE": "PROMOTED", "REJECT": "REJECTED"}.get(decision)
    if transition and rec.get("state") != "EXPIRED":
        rec["state"] = transition
    record = {"at": utc(), "governor_version": GOVERNOR_VERSION, "decision": decision, "hard_gates": hard_gates, "evidence": evidence}
    rec.setdefault("governor_decisions", []).append(record); rec["last_seen_at"] = utc(); save_registry(reg)
    emit("governor_decision", content_hash=content_hash, decision=decision, state=rec.get("state"), hard_gates=hard_gates, evidence=evidence)
    return {"content_hash": content_hash, "decision": decision, "state": rec.get("state"), "hard_gates": hard_gates, "evidence": evidence, "governor_version": GOVERNOR_VERSION}


def expire(content_hash: str, reason: str) -> dict[str, Any]:
    reg = load_registry(); rec = registry_record(reg, content_hash)
    if rec.get("state") == "PROMOTED":
        raise ForgeError("promoted capability cannot be expired directly; supersede it")
    previous = rec.get("state")
    root = object_path(content_hash); env = ENVS / content_hash
    removed = False
    if root.exists(): shutil.rmtree(root); removed = True
    if env.exists(): shutil.rmtree(env)
    rec["state"] = "EXPIRED"; rec["expired_at"] = utc(); rec["expiry_reason"] = reason; rec["expired_object_removed"] = removed; rec["last_seen_at"] = utc()
    save_registry(reg)
    emit("expired", content_hash=content_hash, name=rec.get("name"), previous_state=previous, reason=reason, object_removed=removed, retained_source_hashes=rec.get("source_hashes"), evaluator_hash=rec.get("evaluator_hash"))
    return {"content_hash": content_hash, "previous_state": previous, "state": "EXPIRED", "object_removed": removed, "provenance_retained": PROVENANCE.exists(), "source_hashes_retained": bool(rec.get("source_hashes"))}


def supersede(old_hash: str, new_hash: str) -> dict[str, Any]:
    reg = load_registry(); old = registry_record(reg, old_hash); new = registry_record(reg, new_hash)
    if new.get("state") != "PROMOTED":
        raise ForgeError("replacement must be PROMOTED")
    old["state"] = "SUPERSEDED"; old["superseded_by"] = new_hash; old["superseded_at"] = utc(); save_registry(reg)
    emit("superseded", content_hash=old_hash, superseded_by=new_hash)
    return {"content_hash": old_hash, "state": "SUPERSEDED", "superseded_by": new_hash}


def list_caps() -> list[dict[str, Any]]:
    reg = load_registry()
    return sorted(({k: v for k, v in rec.items() if k not in {"governor_decisions"}} for rec in reg["capabilities"].values()), key=lambda x: (str(x.get("name")), str(x.get("created_at"))))


def show(ref: str) -> dict[str, Any]:
    h, rec = resolve_capability(ref)
    out = dict(rec); out["content_hash"] = h; out["object_available"] = object_path(h).exists()
    if out["object_available"]:
        try: out["contract"] = json.loads((object_path(h) / "capability.json").read_text())
        except Exception: pass
    return out


def selftest() -> dict[str, Any]:
    checks: list[tuple[str, bool, str]] = []
    global ROOT, OBJECTS, WORKSPACES, ENVS, REGISTRY, PROVENANCE, RUN_ROOT, TRACE
    old = (ROOT, OBJECTS, WORKSPACES, ENVS, REGISTRY, PROVENANCE, RUN_ROOT, TRACE)
    try:
        with tempfile.TemporaryDirectory(prefix="forge-selftest-") as td:
            base = pathlib.Path(td)
            ROOT = base / "caps"; OBJECTS = ROOT / "objects"; WORKSPACES = ROOT / "workspaces"; ENVS = ROOT / "envs"; REGISTRY = ROOT / "registry.json"; PROVENANCE = ROOT / "provenance.jsonl"; RUN_ROOT = base / "runs"; TRACE = base / "trace.jsonl"
            init_root()
            gap = open_gap({"desired_name":"echo-json","purpose":"echo typed json","applicability":["json","transform"]})
            ws = pathlib.Path(gap["workspace"])
            contract = {
                "schema_version": CONTRACT_VERSION, "name":"echo-json", "version":"1", "purpose":"echo typed json",
                "input_schema":{"type":"object","required":["value"],"properties":{"value":{"type":"string"}},"additionalProperties":False},
                "output_schema":{"type":"object","required":["value"],"properties":{"value":{"type":"string"}},"additionalProperties":False},
                "entrypoint":["python","main.py"], "dependencies":{"pip":[]}, "side_effects":[], "applicability":["json","transform"],
                "evaluation":{"cases":[
                    {"name":"positive","kind":"positive","input":{"value":"abc"},"expected":{"value":"abc"}},
                    {"name":"invalid","kind":"negative","input":{},"expect_error":True}
                ]},
                "provenance":{"creator":"selftest","creator_episode":"forge-selftest"}, "lifecycle":"EPHEMERAL", "ttl":{"hours":1}, "limits":{"timeout_s":2,"max_output_bytes":4096}
            }
            safe_write_json(ws / "capability.json", contract)
            (ws / "main.py").write_text("import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({'value':x['value']}))\n")
            s = seal(str(ws)); h = s["content_hash"]
            checks.append(("seal_valid", s["state"] == "SEALED", s["state"]))
            ev = evaluate(h); checks.append(("evaluate_positive_negative", ev["ok"] and ev["passed_cases"]==2, str(ev["passed_cases"])))
            inv1 = invoke_raw(h, {"value":"one"}, real_task=True, context="selftest-1")
            inv2 = invoke_raw(h, {"value":"two"}, real_task=True, context="selftest-2")
            checks.append(("real_task_reuse", inv1["ok"] and inv2["ok"], "two invocations"))
            gov = govern(h); checks.append(("promotion_evidence_gate", gov["decision"] == "PROMOTE", gov["decision"]))
            try:
                bad = dict(contract); bad.pop("output_schema"); validate_contract(bad); malformed_ok=False
            except ForgeError: malformed_ok=True
            checks.append(("malformed_rejected", malformed_ok, ""))
            try:
                bad = dict(contract); bad["side_effects"]=["host_mounts"]; validate_contract(bad); auth_ok=False
            except ForgeError: auth_ok=True
            checks.append(("forbidden_authority_rejected", auth_ok, ""))
            dup_gap = open_gap({"desired_name":"new-name","purpose":"unrelated purpose","applicability":["other"]}); dup_ws=pathlib.Path(dup_gap["workspace"]); safe_write_json(dup_ws/"capability.json", contract); (dup_ws/"main.py").write_text((ws/"main.py").read_text()); dup=seal(str(dup_ws))
            checks.append(("content_duplicate_reused", dup["state"]=="DUPLICATE_REUSED", dup["state"]))
            egap=open_gap({"desired_name":"expire-me","purpose":"temporary helper","applicability":["temporary"]}); ews=pathlib.Path(egap["workspace"]); econtract=dict(contract); econtract.update({"name":"expire-me","lifecycle":"EPHEMERAL"}); safe_write_json(ews/"capability.json",econtract); (ews/"main.py").write_text((ws/"main.py").read_text()); es=seal(str(ews)); evaluate(es["content_hash"]); ex=expire(es["content_hash"],"selftest cleanup")
            checks.append(("expire_retains_provenance", ex["state"]=="EXPIRED" and ex["source_hashes_retained"] and ex["provenance_retained"], str(ex)))
    finally:
        ROOT, OBJECTS, WORKSPACES, ENVS, REGISTRY, PROVENANCE, RUN_ROOT, TRACE = old
    return {"version":VERSION,"contract_version":CONTRACT_VERSION,"evaluator_version":EVALUATOR_VERSION,"governor_version":GOVERNOR_VERSION,"passed":sum(1 for _,ok,_ in checks if ok),"total":len(checks),"checks":[{"name":n,"ok":ok,"detail":d} for n,ok,d in checks]}


def parse_json_arg(text: str | None, file_path: str | None) -> Any:
    if text and file_path:
        raise ForgeError("use only one of inline JSON/file")
    if file_path:
        return json.loads(pathlib.Path(file_path).read_text())
    if text:
        return json.loads(text)
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description="Evidence-gated guest-local Capability Forge")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p=sub.add_parser("gap"); p.add_argument("--json"); p.add_argument("--file")
    p=sub.add_parser("search"); p.add_argument("--json"); p.add_argument("--file")
    p=sub.add_parser("validate"); p.add_argument("contract")
    p=sub.add_parser("seal"); p.add_argument("workspace")
    p=sub.add_parser("evaluate"); p.add_argument("capability")
    p=sub.add_parser("invoke"); p.add_argument("capability"); p.add_argument("--input-json"); p.add_argument("--input-file"); p.add_argument("--real-task", action="store_true"); p.add_argument("--context")
    p=sub.add_parser("govern"); p.add_argument("capability")
    p=sub.add_parser("expire"); p.add_argument("capability"); p.add_argument("--reason", required=True)
    p=sub.add_parser("supersede"); p.add_argument("old"); p.add_argument("new")
    sub.add_parser("list")
    p=sub.add_parser("show"); p.add_argument("capability")
    args=ap.parse_args()
    try:
        if args.selftest:
            out=selftest()
        elif args.cmd=="gap": out=open_gap(parse_json_arg(args.json,args.file))
        elif args.cmd=="search": out=search(parse_json_arg(args.json,args.file))
        elif args.cmd=="validate": out={"ok":True,"summary":validate_contract(json.loads(pathlib.Path(args.contract).read_text()))}
        elif args.cmd=="seal": out=seal(args.workspace)
        elif args.cmd=="evaluate": h,_=resolve_capability(args.capability); out=evaluate(h)
        elif args.cmd=="invoke": h,_=resolve_capability(args.capability); out=invoke_raw(h,parse_json_arg(args.input_json,args.input_file),real_task=args.real_task,context=args.context)
        elif args.cmd=="govern": h,_=resolve_capability(args.capability); out=govern(h)
        elif args.cmd=="expire": h,_=resolve_capability(args.capability); out=expire(h,args.reason)
        elif args.cmd=="supersede": old,_=resolve_capability(args.old); new,_=resolve_capability(args.new); out=supersede(old,new)
        elif args.cmd=="list": out=list_caps()
        elif args.cmd=="show": out=show(args.capability)
        else: ap.print_help(); raise SystemExit(2)
        print(json.dumps(out, indent=2, sort_keys=True))
        if args.selftest and out["passed"] != out["total"]: raise SystemExit(1)
        if args.cmd in {"evaluate","invoke"} and not out.get("ok",False): raise SystemExit(1)
    except ForgeError as exc:
        print(json.dumps({"ok":False,"error":str(exc)},indent=2),file=sys.stderr); raise SystemExit(1)


if __name__ == "__main__":
    main()
