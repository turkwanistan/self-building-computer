#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import contextlib
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import pathlib
import secrets
import shlex
import shutil
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Iterator

VERSION = "gen10-evidence-epoch-r1"
SCHEMA_VERSION = 1
SOURCE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_EPOCH_SOURCE_ROOT", "/opt/optiplex-lab"))
STATE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_EPOCH_STATE_ROOT", "/var/lib/optiplex-lab"))
BUILD_PATH = pathlib.Path(os.environ.get("OPTIPLEX_EPOCH_BUILD", "/etc/optiplex-lab/build.json"))
TWIN_PATH = pathlib.Path(os.environ.get("OPTIPLEX_EPOCH_TWIN", "/var/lib/optiplex-lab/twin/twin-current.json"))
CAUSAL_PATH = pathlib.Path(os.environ.get("OPTIPLEX_EPOCH_CAUSAL", "/var/lib/optiplex-lab/twin/causal-index.json"))
EPOCH_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_EPOCH_ROOT", "/var/lib/optiplex-lab/evidence-epochs"))
BLOB_ROOT = EPOCH_ROOT / "blobs"
EPOCHS_ROOT = EPOCH_ROOT / "epochs"
LOCK_PATH = EPOCH_ROOT / ".coordinator.lock"

PINNED_PLUS_LIVE = {
    "/etc/optiplex-lab/build.json",
    "/opt/optiplex-lab/server.py",
    "/var/lib/optiplex-lab/recovery/server.last-known-good.py",
}
DERIVED_PINNED = {
    "/var/lib/optiplex-lab/twin/twin-current.json",
    "/var/lib/optiplex-lab/twin/causal-index.json",
    "/var/lib/optiplex-lab/twin/twin.sqlite3",
}
DEFAULT_MODULES = (
    "/opt/optiplex-lab/context_compiler.py",
    "/opt/optiplex-lab/context_necessity.py",
    "/opt/optiplex-lab/evidence_epoch.py",
    "/opt/optiplex-lab/architecture_twin.py",
    "/opt/optiplex-lab/causal_spine.py",
    "/opt/optiplex-lab/experiment_capsule.py",
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_path(path: pathlib.Path) -> str | None:
    try:
        return sha_bytes(path.read_bytes()) if path.is_file() else None
    except OSError:
        return None


def safe_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as fh:
        fh.write(payload)
        tmp = pathlib.Path(fh.name)
    tmp.replace(path)


def atomic_bytes(path: pathlib.Path, data: bytes, mode: int = 0o444) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(name, mode)
        pathlib.Path(name).replace(path)
    finally:
        try:
            pathlib.Path(name).unlink()
        except OSError:
            pass


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@contextlib.contextmanager
def coordinator_lock() -> Iterator[None]:
    EPOCH_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def view_path(view_root: pathlib.Path, original: pathlib.Path | str) -> pathlib.Path:
    p = pathlib.Path(str(original))
    return view_root / str(p).lstrip("/")


def _read_prefix(path: pathlib.Path, count: int) -> bytes:
    with path.open("rb") as fh:
        return fh.read(count)


def _blob(data: bytes) -> tuple[str, pathlib.Path, bool]:
    digest = sha_bytes(data)
    target = BLOB_ROOT / digest[:2] / digest
    created = False
    if not target.is_file():
        atomic_bytes(target, data, 0o444)
        created = True
    elif sha_path(target) != digest:
        raise RuntimeError(f"content-addressed blob corrupt: {target}")
    return digest, target, created


def _materialize(blob: pathlib.Path, target: pathlib.Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    try:
        os.link(blob, target)
    except OSError:
        shutil.copy2(blob, target)
    target.chmod(0o444)


def _contradictions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in snapshot.get("nodes", []):
        if isinstance(node, dict) and node.get("authoritative") and node.get("identity"):
            groups.setdefault(str(node["identity"]), []).append(node)
    out: list[dict[str, Any]] = []
    for identity, nodes in sorted(groups.items()):
        if len(nodes) < 2:
            continue
        signatures = {
            (n.get("source_sha256"), n.get("generation"), canonical(n.get("metadata") or {}))
            for n in nodes
        }
        if len(signatures) > 1:
            out.append({"identity": identity, "nodes": sorted(str(n.get("id")) for n in nodes), "reason": "contradictory authoritative claims at epoch creation"})
    build = safe_json(BUILD_PATH)
    if isinstance(build, dict):
        live = sha_path(SOURCE_ROOT / "server.py")
        lkg = sha_path(STATE_ROOT / "recovery/server.last-known-good.py")
        source = build.get("source_sha256")
        if source and live and source != live:
            out.append({"identity": "operational-server", "reason": "build source hash differs from live server", "build_sha256": source, "live_sha256": live})
        if build.get("recovery_state") == "ACCEPTED" and live and lkg and live != lkg:
            out.append({"identity": "accepted-lkg", "reason": "ACCEPTED live server differs from LKG", "live_sha256": live, "lkg_sha256": lkg})
    return out


def _registry_object_paths() -> list[pathlib.Path]:
    paths: set[pathlib.Path] = set()
    for rel in ("capabilities/registry.json", "memory/registry.json", "regressions/registry.json"):
        reg = safe_json(STATE_ROOT / rel)
        if not isinstance(reg, dict):
            continue
        stack: list[Any] = [reg]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                obj = item.get("object")
                if isinstance(obj, str) and obj.startswith("/"):
                    paths.add(pathlib.Path(obj))
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
    return sorted(paths, key=str)


def _workflow_current_paths() -> list[pathlib.Path]:
    root = STATE_ROOT / "workflows"
    return sorted(root.glob("*/CURRENT"), key=str) if root.is_dir() else []


def _policy_for(path: pathlib.Path, mode: str, overrides: dict[str, str]) -> str:
    p = str(path)
    if p in overrides:
        return overrides[p]
    if p in PINNED_PLUS_LIVE or (p.startswith("/etc/systemd/system/") and "optiplex-lab" in p):
        return "pinned_plus_live_revalidate"
    if p in DERIVED_PINNED:
        return "pinned_hash"
    if mode == "append_only":
        return "append_only_prefix"
    return "pinned_hash"


def _capture_entry(path: pathlib.Path, *, expected_sha: str | None, expected_bytes: int | None,
                   freshness_mode: str, policy: str, stage_view: pathlib.Path,
                   critical: bool, created_blobs: set[str]) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"required epoch input missing: {path}")
    current_bytes = path.stat().st_size
    if freshness_mode == "append_only":
        if not isinstance(expected_bytes, int) or not expected_sha:
            expected_bytes = current_bytes
            expected_sha = sha_path(path)
        if current_bytes < expected_bytes:
            raise RuntimeError(f"append-only epoch input shrank before seal: {path}")
        data = _read_prefix(path, expected_bytes)
        if sha_bytes(data) != expected_sha:
            raise RuntimeError(f"append-only epoch input prefix stale before seal: {path}")
        start_sha = expected_sha
        start_bytes = expected_bytes
    else:
        data = path.read_bytes()
        actual = sha_bytes(data)
        if expected_sha and actual != expected_sha:
            raise RuntimeError(f"epoch input stale before seal: {path}: expected {expected_sha}, found {actual}")
        start_sha = actual
        start_bytes = len(data)
    blob_sha, blob, created = _blob(data)
    if created:
        created_blobs.add(blob_sha)
    target = view_path(stage_view, path)
    _materialize(blob, target)
    return {
        "path": str(path),
        "freshness_mode": freshness_mode,
        "policy": policy,
        "critical": bool(critical),
        "sha256": start_sha,
        "bytes": start_bytes,
        "blob_sha256": blob_sha,
        "view_relative": str(path).lstrip("/"),
    }


def _manifest_core(snapshot: dict[str, Any], entries: list[dict[str, Any]], expected_outputs: list[str],
                   evaluators: list[str], authority_overrides: dict[str, str], live_verifiers: dict[str, str],
                   historical_scope: str | None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "coordinator_version": VERSION,
        "twin_graph_digest": snapshot.get("graph_digest"),
        "twin_version": snapshot.get("version"),
        "entries": sorted(entries, key=lambda x: x["path"]),
        "expected_outputs": sorted(set(expected_outputs)),
        "evaluator_paths": sorted(set(evaluators)),
        "authority_overrides": dict(sorted(authority_overrides.items())),
        "live_verifiers": dict(sorted(live_verifiers.items())),
        "historical_scope": historical_scope,
    }


def begin_epoch(*, expected_outputs: list[str] | None = None, evaluator_paths: list[str] | None = None,
                extra_paths: list[str] | None = None, authority_overrides: dict[str, str] | None = None,
                live_verifiers: dict[str, str] | None = None, snapshot_override: dict[str, Any] | None = None,
                historical_scope: str | None = None) -> dict[str, Any]:
    started = time.monotonic()
    expected_outputs = sorted(set(expected_outputs or []))
    evaluator_paths = sorted(set(evaluator_paths or []))
    authority_overrides = dict(authority_overrides or {})
    live_verifiers = dict(live_verifiers or {})
    for path, policy in authority_overrides.items():
        if policy not in {"pinned_hash", "append_only_prefix", "pinned_plus_live_revalidate", "live_revalidate_only"}:
            raise ValueError(f"unknown epoch authority policy {policy}: {path}")
        if policy == "live_revalidate_only" and path not in live_verifiers:
            raise RuntimeError(f"live-revalidate-only authority has no verifier and cannot be safely sealed: {path}")
    snapshot = copy.deepcopy(snapshot_override) if snapshot_override is not None else safe_json(TWIN_PATH)
    if not isinstance(snapshot, dict):
        raise RuntimeError("Twin snapshot missing or invalid")
    conflicts = _contradictions(snapshot)
    if conflicts:
        raise RuntimeError("epoch cannot seal with contradictory authority: " + json.dumps(conflicts, sort_keys=True))

    specs: dict[str, dict[str, Any]] = {}
    for item in snapshot.get("inputs", []):
        if not isinstance(item, dict) or not item.get("path"):
            continue
        specs[str(item["path"])] = {
            "expected_sha": item.get("sha256"), "expected_bytes": item.get("bytes"),
            "mode": str(item.get("freshness_mode") or "hash"), "critical": True,
        }
    for raw in [str(TWIN_PATH), str(CAUSAL_PATH), *DEFAULT_MODULES, *evaluator_paths, *(extra_paths or [])]:
        p = pathlib.Path(raw)
        if not p.is_file():
            if raw in (str(CAUSAL_PATH),) and historical_scope:
                continue
            raise RuntimeError(f"explicit epoch input missing: {p}")
        specs.setdefault(raw, {"expected_sha": sha_path(p), "expected_bytes": p.stat().st_size, "mode": "hash", "critical": True})
    for p in [*_registry_object_paths(), *_workflow_current_paths()]:
        if p.is_file():
            specs.setdefault(str(p), {"expected_sha": sha_path(p), "expected_bytes": p.stat().st_size, "mode": "hash", "critical": False})
    # Explicit live-only authorities still need starting provenance, even though frozen bytes never satisfy them.
    for raw in authority_overrides:
        p = pathlib.Path(raw)
        if not p.is_file():
            raise RuntimeError(f"authority input missing: {p}")
        specs.setdefault(raw, {"expected_sha": sha_path(p), "expected_bytes": p.stat().st_size, "mode": "hash", "critical": True})

    EPOCH_ROOT.mkdir(parents=True, exist_ok=True)
    BLOB_ROOT.mkdir(parents=True, exist_ok=True)
    EPOCHS_ROOT.mkdir(parents=True, exist_ok=True)
    stage = EPOCH_ROOT / f".creating-{os.getpid()}-{secrets.token_hex(4)}"
    stage_view = stage / "view"
    stage_view.mkdir(parents=True)
    entries: list[dict[str, Any]] = []
    created_blobs: set[str] = set()
    try:
        for raw in sorted(specs):
            spec = specs[raw]
            path = pathlib.Path(raw)
            policy = _policy_for(path, spec["mode"], authority_overrides)
            entries.append(_capture_entry(path, expected_sha=spec["expected_sha"], expected_bytes=spec["expected_bytes"],
                                          freshness_mode=spec["mode"], policy=policy, stage_view=stage_view,
                                          critical=bool(spec.get("critical")), created_blobs=created_blobs))
        core = _manifest_core(snapshot, entries, expected_outputs, evaluator_paths, authority_overrides, live_verifiers, historical_scope)
        digest = sha_bytes(canonical(core))
        epoch_id = "ep10_" + digest
        manifest = {
            "epoch_id": epoch_id,
            "epoch_digest": digest,
            "created_at": utc(),
            "core": core,
            "protected_start_digest": None,
            "state": "SEALED",
        }
        # Protected-state provenance is audit metadata, deliberately excluded from deterministic epoch identity.
        cap_path = stage_view / "opt/optiplex-lab/experiment_capsule.py"
        if cap_path.is_file():
            cap = load_module(cap_path, "gen10_epoch_protected_begin")
            manifest["protected_start_digest"] = cap.protected_manifest().get("digest")
        atomic_json(stage / "manifest.json", manifest)
        (stage / "SEALED").write_text(digest + "\n", encoding="utf-8")
        destination = EPOCHS_ROOT / epoch_id
        reused = False
        with coordinator_lock():
            if destination.exists():
                existing = safe_json(destination / "manifest.json")
                if not isinstance(existing, dict) or existing.get("epoch_digest") != digest or (destination / "SEALED").read_text().strip() != digest:
                    raise RuntimeError(f"existing epoch directory failed integrity: {destination}")
                shutil.rmtree(stage)
                reused = True
                manifest = existing
            else:
                stage.replace(destination)
        verify = verify_epoch(epoch_id, allow_expected_changes=True)
        if not verify["ok"]:
            raise RuntimeError("newly sealed epoch failed verification: " + json.dumps(verify["unsafe"], sort_keys=True))
        return {
            "ok": True, "epoch_id": epoch_id, "epoch_digest": digest, "reused": reused,
            "entries": len(entries), "materialized_bytes": sum(int(x["bytes"]) for x in entries),
            "new_blob_bytes": sum((BLOB_ROOT / h[:2] / h).stat().st_size for h in created_blobs if (BLOB_ROOT / h[:2] / h).is_file()),
            "append_only_newer_at_begin": verify["append_only_growth"],
            "creation_seal_latency_ms": round((time.monotonic() - started) * 1000, 3),
            "manifest": str((EPOCHS_ROOT / epoch_id / "manifest.json")),
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _epoch_dir(epoch_id: str) -> pathlib.Path:
    candidate = EPOCHS_ROOT / epoch_id
    if candidate.is_dir():
        return candidate
    if not epoch_id.startswith("ep10_"):
        candidate = EPOCHS_ROOT / ("ep10_" + epoch_id)
        if candidate.is_dir():
            return candidate
    raise RuntimeError(f"sealed epoch not found: {epoch_id}")


def load_epoch(epoch_id: str) -> tuple[pathlib.Path, dict[str, Any]]:
    root = _epoch_dir(epoch_id)
    manifest = safe_json(root / "manifest.json")
    if not isinstance(manifest, dict):
        raise RuntimeError("epoch manifest missing/invalid")
    core = manifest.get("core")
    digest = sha_bytes(canonical(core)) if isinstance(core, dict) else None
    if digest != manifest.get("epoch_digest") or manifest.get("epoch_id") != "ep10_" + str(digest):
        raise RuntimeError("epoch manifest digest mismatch")
    try:
        marker = (root / "SEALED").read_text(encoding="utf-8").strip()
    except OSError:
        marker = ""
    if marker != digest:
        raise RuntimeError("epoch is not atomically sealed")
    return root, manifest


def _classify_entry(entry: dict[str, Any], *, expected_outputs: set[str], live_verifiers: dict[str, str],
                    allow_expected_changes: bool) -> dict[str, Any]:
    path = pathlib.Path(entry["path"])
    policy = str(entry["policy"])
    start_sha = str(entry["sha256"])
    start_bytes = int(entry["bytes"])
    if not path.is_file():
        return {"path": str(path), "state": "unsafe", "reason": "live critical evidence missing", "policy": policy}
    if policy == "append_only_prefix":
        cur_bytes = path.stat().st_size
        if cur_bytes < start_bytes:
            return {"path": str(path), "state": "unsafe", "reason": "append-only evidence shrank", "policy": policy}
        prefix_sha = sha_bytes(_read_prefix(path, start_bytes))
        if prefix_sha != start_sha:
            return {"path": str(path), "state": "unsafe", "reason": "append-only prefix changed", "policy": policy, "prefix_sha256": prefix_sha}
        return {"path": str(path), "state": "unchanged" if cur_bytes == start_bytes else "append_only_growth", "policy": policy,
                "start_bytes": start_bytes, "current_bytes": cur_bytes}
    actual = sha_path(path)
    if policy == "live_revalidate_only":
        verifier = live_verifiers.get(str(path))
        if verifier == "sha256_unchanged":
            ok = actual == start_sha
            return {"path": str(path), "state": "unchanged" if ok else "unsafe", "policy": policy,
                    "reason": None if ok else "live-only authority verifier rejected changed content", "current_sha256": actual}
        return {"path": str(path), "state": "unsafe", "policy": policy, "reason": "live-only authority verifier unavailable"}
    if actual == start_sha:
        return {"path": str(path), "state": "unchanged", "policy": policy}
    if policy == "pinned_plus_live_revalidate":
        return {"path": str(path), "state": "unsafe", "policy": policy, "reason": "live safety/recovery authority changed during epoch", "start_sha256": start_sha, "current_sha256": actual}
    if str(path) in expected_outputs and allow_expected_changes:
        return {"path": str(path), "state": "expected_output", "policy": policy, "start_sha256": start_sha, "current_sha256": actual}
    if str(path) in DERIVED_PINNED:
        return {"path": str(path), "state": "derived_newer_for_next_epoch", "policy": policy, "start_sha256": start_sha, "current_sha256": actual}
    return {"path": str(path), "state": "unsafe", "policy": policy, "reason": "unexpected pinned critical evidence mutation", "start_sha256": start_sha, "current_sha256": actual}


def verify_epoch(epoch_id: str, *, allow_expected_changes: bool = True) -> dict[str, Any]:
    started = time.monotonic()
    root, manifest = load_epoch(epoch_id)
    core = manifest["core"]
    unsafe: list[dict[str, Any]] = []
    expected: list[dict[str, Any]] = []
    append_growth: list[dict[str, Any]] = []
    derived_newer: list[dict[str, Any]] = []
    unchanged = 0
    expected_outputs = set(str(x) for x in core.get("expected_outputs", []))
    live_verifiers = {str(k): str(v) for k, v in (core.get("live_verifiers") or {}).items()}
    entry_paths: set[str] = set()
    for entry in core.get("entries", []):
        entry_paths.add(str(entry["path"]))
        blob = BLOB_ROOT / str(entry["blob_sha256"])[:2] / str(entry["blob_sha256"])
        view = root / "view" / str(entry["view_relative"])
        if not blob.is_file() or sha_path(blob) != entry["blob_sha256"]:
            unsafe.append({"path": entry["path"], "state": "unsafe", "reason": "missing/corrupt pinned content-addressed blob"})
            continue
        if not view.is_file() or sha_path(view) != entry["blob_sha256"]:
            unsafe.append({"path": entry["path"], "state": "unsafe", "reason": "missing/corrupt materialized epoch view"})
            continue
        item = _classify_entry(entry, expected_outputs=expected_outputs, live_verifiers=live_verifiers, allow_expected_changes=allow_expected_changes)
        state = item["state"]
        if state == "unsafe": unsafe.append(item)
        elif state == "expected_output": expected.append(item)
        elif state == "append_only_growth": append_growth.append(item)
        elif state == "derived_newer_for_next_epoch": derived_newer.append(item)
        else: unchanged += 1
    for raw in sorted(expected_outputs - entry_paths):
        p = pathlib.Path(raw)
        if p.exists():
            expected.append({"path": raw, "state": "expected_output_new", "current_sha256": sha_path(p), "current_bytes": p.stat().st_size if p.is_file() else None})
    return {
        "ok": not unsafe, "epoch_id": manifest["epoch_id"], "epoch_digest": manifest["epoch_digest"],
        "unsafe": unsafe, "expected_output_changes": expected, "append_only_growth": append_growth,
        "derived_newer_for_next_epoch": derived_newer, "unchanged_entries": unchanged,
        "verify_latency_ms": round((time.monotonic() - started) * 1000, 3),
    }


def _redirect_snapshot(snapshot: dict[str, Any], root: pathlib.Path, entries: list[dict[str, Any]]) -> dict[str, Any]:
    out = copy.deepcopy(snapshot)
    mapped = {str(e["path"]): root / "view" / str(e["view_relative"]) for e in entries}
    for node in out.get("nodes", []):
        raw = node.get("source_path")
        if raw in mapped:
            node["source_path"] = str(mapped[raw])
    for inp in out.get("inputs", []):
        raw = inp.get("path")
        if raw in mapped:
            inp["path"] = str(mapped[raw])
    return out


def _patch_compiler(cc: Any, root: pathlib.Path) -> None:
    view = root / "view"
    cc.SOURCE_ROOT = view / "opt/optiplex-lab"
    cc.STATE_ROOT = view / "var/lib/optiplex-lab"
    cc.TWIN_PATH = view / "var/lib/optiplex-lab/twin/twin-current.json"
    cc.CAUSAL_PATH = view / "var/lib/optiplex-lab/twin/causal-index.json"
    cc.BUILD_PATH = view / "etc/optiplex-lab/build.json"
    cc.MEMORY_REGISTRY = view / "var/lib/optiplex-lab/memory/registry.json"
    cc.REGRESSION_REGISTRY = view / "var/lib/optiplex-lab/regressions/registry.json"
    original_safe_json = cc.safe_json
    original_sha_path = cc.sha_path
    def map_read(path: pathlib.Path) -> pathlib.Path:
        p = pathlib.Path(path)
        if str(p).startswith(str(view)):
            return p
        candidate = view_path(view, p)
        return candidate if candidate.exists() else p
    def epoch_safe_json(path: pathlib.Path) -> Any:
        return original_safe_json(map_read(path))
    def epoch_sha_path(path: pathlib.Path) -> str | None:
        return original_sha_path(map_read(path))
    cc.safe_json = epoch_safe_json
    cc.sha_path = epoch_sha_path


def _patch_optimizer(opt: Any, root: pathlib.Path) -> None:
    view = root / "view"
    opt.WORKFLOW_ROOT = view / "var/lib/optiplex-lab/workflows"
    def validation_source_score(rec: dict[str, Any], requested_atoms: list[str]) -> dict[str, Any] | None:
        sf = rec.get("structured_fact") or {}
        raw = sf.get("identity") or (sf.get("metadata") or {}).get("command")
        if not raw:
            return None
        original = pathlib.Path(str(raw).split()[0])
        path = view_path(view, original)
        if not path.is_file():
            return None
        content = path.read_text(encoding="utf-8", errors="replace").lower()
        covered: list[str] = []
        hits = 0
        for atom in requested_atoms:
            terms = opt.LIFECYCLE_ATOMS[atom]
            atom_hits = sum(content.count(term) for term in terms)
            if atom_hits:
                covered.append(atom); hits += atom_hits
        return {"source_path": str(original), "covered_atoms": covered, "coverage": len(covered), "hits": hits, "source_sha256": sha_path(path)}
    opt._validation_source_score = validation_source_score


def compile_minimized(epoch_id: str, task: str, *, budget_bytes: int = 48000) -> dict[str, Any]:
    verification = verify_epoch(epoch_id, allow_expected_changes=True)
    if not verification["ok"]:
        return {"ok": False, "fail_closed": True, "epoch_id": epoch_id, "verification": verification, "reason": "epoch verification failed before compile"}
    root, manifest = load_epoch(epoch_id)
    view = root / "view"
    cc = load_module(view / "opt/optiplex-lab/context_compiler.py", "gen10_epoch_cc_" + manifest["epoch_digest"][:12])
    opt = load_module(view / "opt/optiplex-lab/context_necessity.py", "gen10_epoch_opt_" + manifest["epoch_digest"][:12])
    _patch_compiler(cc, root); _patch_optimizer(opt, root)
    snapshot = safe_json(view / "var/lib/optiplex-lab/twin/twin-current.json")
    if not isinstance(snapshot, dict):
        raise RuntimeError("epoch Twin missing")
    redirected = _redirect_snapshot(snapshot, root, manifest["core"]["entries"])
    raw = cc.build_packet(task, budget_bytes=budget_bytes, snapshot_override=redirected)
    minimized = opt.minimize_packet(raw)
    material = {
        "epoch_digest": manifest["epoch_digest"],
        "compiler_packet_digest": raw.get("packet_digest"),
        "optimizer_packet_digest": minimized.get("packet_digest"),
        "task_hash": raw.get("task_hash"),
    }
    return {
        "ok": not bool(raw.get("fail_closed") or minimized.get("fail_closed")),
        "fail_closed": bool(raw.get("fail_closed") or minimized.get("fail_closed")),
        "epoch_id": manifest["epoch_id"], "epoch_digest": manifest["epoch_digest"],
        "twin_graph_digest": manifest["core"].get("twin_graph_digest"),
        "compiler_packet": raw, "minimized_packet": minimized,
        "transaction_digest": sha_bytes(canonical(material)), "verification": verification,
    }


def finalize_epoch(epoch_id: str) -> dict[str, Any]:
    started = time.monotonic()
    root, manifest = load_epoch(epoch_id)
    verification = verify_epoch(epoch_id, allow_expected_changes=True)
    result = {
        "version": VERSION,
        "epoch_id": manifest["epoch_id"], "epoch_digest": manifest["epoch_digest"],
        "ok": verification["ok"], "state": "FINALIZED" if verification["ok"] else "FAILED_CLOSED",
        "unsafe": verification["unsafe"],
        "next_epoch_candidates": sorted(
            [*verification["expected_output_changes"], *verification["append_only_growth"], *verification["derived_newer_for_next_epoch"]],
            key=lambda x: (str(x.get("path")), str(x.get("state"))),
        ),
        "verification_digest": sha_bytes(canonical({k: v for k, v in verification.items() if not k.endswith("latency_ms")})),
        "finalized_at": utc(),
    }
    result["finalize_latency_ms"] = round((time.monotonic() - started) * 1000, 3)
    with coordinator_lock():
        atomic_json(root / "finalization.json", result)
    return result


def advance_epoch(epoch_id: str) -> dict[str, Any]:
    root, manifest = load_epoch(epoch_id)
    fin = safe_json(root / "finalization.json")
    if not isinstance(fin, dict) or not fin.get("ok"):
        fin = finalize_epoch(epoch_id)
    if not fin.get("ok"):
        raise RuntimeError("cannot advance a failed-closed epoch")
    twin_path = root / "view/opt/optiplex-lab/architecture_twin.py"
    twin = load_module(twin_path, "gen10_epoch_advance_" + manifest["epoch_digest"][:12])
    build = twin.build_all(
        source_root=SOURCE_ROOT,
        state_root=STATE_ROOT,
        build_file=BUILD_PATH,
        recovery_root=STATE_ROOT / "recovery",
        twin_root=STATE_ROOT / "twin",
    )
    return {"ok": True, "from_epoch": manifest["epoch_id"], "next_twin": build, "next_epoch_required": bool(fin.get("next_epoch_candidates"))}


def run_epoch_capsule(epoch_id: str, command: str, *, captures: list[str] | None = None,
                      label: str = "gen10-epoch-evaluator") -> dict[str, Any]:
    root, manifest = load_epoch(epoch_id)
    view = root / "view"
    cap = load_module(view / "opt/optiplex-lab/experiment_capsule.py", "gen10_epoch_capsule_" + manifest["epoch_digest"][:12])
    prelude = ["set -euo pipefail"]
    for entry in manifest["core"].get("entries", []):
        if entry.get("policy") == "live_revalidate_only":
            continue
        src = root / "view" / str(entry["view_relative"])
        dst = pathlib.Path(str(entry["path"]))
        prelude.append(f"mkdir -p {shlex.quote(str(dst.parent))}")
        prelude.append(f"cp -f {shlex.quote(str(src))} {shlex.quote(str(dst))}")
    wrapped = "\n".join(prelude) + "\n" + command
    return cap.run_capsule(wrapped, captures=captures or [], label=label)


def publish_captured_expected(epoch_id: str, capsule_result: dict[str, Any], path: str) -> dict[str, Any]:
    root, manifest = load_epoch(epoch_id)
    expected = set(str(x) for x in manifest["core"].get("expected_outputs", []))
    if path not in expected:
        raise RuntimeError(f"refusing to publish undeclared epoch output: {path}")
    if not capsule_result.get("accepted_state_unchanged") or capsule_result.get("forbidden_accepted_state_mutations"):
        raise RuntimeError("refusing output publication from unsafe capsule")
    matches = [x for x in capsule_result.get("captured_artifacts", []) if str(x.get("path")) == path]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one captured artifact for {path}")
    src = pathlib.Path(str(matches[0]["export_path"]))
    if not src.is_file():
        raise RuntimeError("captured expected output unavailable")
    dst = pathlib.Path(path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=str(dst.parent), delete=False) as fh:
        fh.write(src.read_bytes()); tmp = pathlib.Path(fh.name)
    tmp.replace(dst)
    return {"ok": True, "path": path, "sha256": sha_path(dst), "bytes": dst.stat().st_size, "from_capsule": capsule_result.get("run_id")}


def recover_incomplete() -> dict[str, Any]:
    EPOCH_ROOT.mkdir(parents=True, exist_ok=True)
    removed: list[str] = []
    with coordinator_lock():
        for p in sorted(EPOCH_ROOT.glob(".creating-*"), key=str):
            if p.is_dir():
                removed.append(p.name); shutil.rmtree(p, ignore_errors=False)
    return {"ok": True, "removed_incomplete": removed, "authoritative_epochs": len([p for p in EPOCHS_ROOT.glob("ep10_*") if (p / "SEALED").is_file()]) if EPOCHS_ROOT.is_dir() else 0}


def selftest() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def ck(name: str, ok: bool, detail: Any = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    base = {"schema_version": 1, "coordinator_version": VERSION, "twin_graph_digest": "g", "twin_version": "t", "entries": [], "expected_outputs": [], "evaluator_paths": [], "authority_overrides": {}, "live_verifiers": {}, "historical_scope": None}
    ck("canonical_digest_deterministic", sha_bytes(canonical(base)) == sha_bytes(canonical(copy.deepcopy(base))))
    try:
        begin_epoch(extra_paths=["/tmp/gen10-no-such-authority"], authority_overrides={"/tmp/gen10-no-such-authority": "live_revalidate_only"})
        refused = False
    except RuntimeError as exc:
        refused = "no verifier" in str(exc)
    ck("live_only_without_verifier_refused", refused)
    with tempfile.TemporaryDirectory(prefix="gen10-epoch-selftest-") as td:
        p = pathlib.Path(td) / "trace.jsonl"; p.write_bytes(b"a\n")
        entry = {"path": str(p), "policy": "append_only_prefix", "sha256": sha_bytes(b"a\n"), "bytes": 2}
        p.write_bytes(b"a\nb\n")
        x = _classify_entry(entry, expected_outputs=set(), live_verifiers={}, allow_expected_changes=True)
        ck("append_only_growth_classified", x["state"] == "append_only_growth", x)
        p.write_bytes(b"x\nb\n")
        y = _classify_entry(entry, expected_outputs=set(), live_verifiers={}, allow_expected_changes=True)
        ck("append_only_prefix_mutation_unsafe", y["state"] == "unsafe", y)
        q = pathlib.Path(td) / "source.py"; q.write_bytes(b"one")
        e2 = {"path": str(q), "policy": "pinned_hash", "sha256": sha_bytes(b"one"), "bytes": 3}
        q.write_bytes(b"two")
        z = _classify_entry(e2, expected_outputs=set(), live_verifiers={}, allow_expected_changes=True)
        ck("unexpected_pinned_change_unsafe", z["state"] == "unsafe", z)
        z2 = _classify_entry(e2, expected_outputs={str(q)}, live_verifiers={}, allow_expected_changes=True)
        ck("declared_output_classified", z2["state"] == "expected_output", z2)
    return {"version": VERSION, "passed": sum(1 for x in checks if x["ok"]), "total": len(checks), "checks": checks}


def main() -> None:
    ap = argparse.ArgumentParser(description="Gen10 deterministic Evidence Epoch / Snapshot Freshness Coordinator")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("begin"); p.add_argument("--expect-output", action="append", default=[]); p.add_argument("--evaluator", action="append", default=[]); p.add_argument("--extra-path", action="append", default=[]); p.add_argument("--historical-scope")
    p = sub.add_parser("verify"); p.add_argument("epoch")
    p = sub.add_parser("compile"); p.add_argument("epoch"); p.add_argument("task"); p.add_argument("--budget-bytes", type=int, default=48000)
    p = sub.add_parser("finalize"); p.add_argument("epoch")
    p = sub.add_parser("advance"); p.add_argument("epoch")
    sub.add_parser("recover")
    args = ap.parse_args()
    if args.selftest:
        out = selftest(); print(json.dumps(out, indent=2, sort_keys=True)); raise SystemExit(0 if out["passed"] == out["total"] else 1)
    if args.cmd == "begin": out = begin_epoch(expected_outputs=args.expect_output, evaluator_paths=args.evaluator, extra_paths=args.extra_path, historical_scope=args.historical_scope)
    elif args.cmd == "verify": out = verify_epoch(args.epoch)
    elif args.cmd == "compile": out = compile_minimized(args.epoch, args.task, budget_bytes=max(1024, args.budget_bytes))
    elif args.cmd == "finalize": out = finalize_epoch(args.epoch)
    elif args.cmd == "advance": out = advance_epoch(args.epoch)
    elif args.cmd == "recover": out = recover_incomplete()
    else: ap.error("command required")
    print(json.dumps(out, indent=2, sort_keys=True))
    raise SystemExit(0 if out.get("ok", True) else 2)


if __name__ == "__main__":
    main()
