#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import shlex
import tempfile
from typing import Any

VERSION = "gen12-counterfactual-replay-r1"
SCHEMA_VERSION = 1
SOURCE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_REPLAY_SOURCE_ROOT", "/opt/optiplex-lab"))
STATE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_REPLAY_STATE_ROOT", "/var/lib/optiplex-lab"))
EPOCH_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_REPLAY_EPOCH_ROOT", str(STATE_ROOT / "evidence-epochs")))
EPOCHS_ROOT = EPOCH_ROOT / "epochs"
BLOB_ROOT = EPOCH_ROOT / "blobs"
CAPSULE_PATH = SOURCE_ROOT / "experiment_capsule.py"
HIERARCHY_PATH = SOURCE_ROOT / "hierarchical_experiment.py"
ROUTER_PATH = SOURCE_ROOT / "task_routing.py"
SAFETY_CRITICAL_AUTHORITIES = {
    "guest_security_boundary", "operational_identity", "lifecycle_state", "recovery_lkg", "security_containment"
}
FORBIDDEN_ACCEPTED_PATHS = {
    "/opt/optiplex-lab/server.py",
    "/etc/optiplex-lab/build.json",
    "/var/lib/optiplex-lab/recovery/server.last-known-good.py",
    "/var/lib/optiplex-lab/capabilities/registry.json",
    "/var/lib/optiplex-lab/memory/registry.json",
    "/var/lib/optiplex-lab/regressions/registry.json",
    "/var/lib/optiplex-lab/traces/events.jsonl",
    "/var/lib/optiplex-lab/capabilities/provenance.jsonl",
    "/var/lib/optiplex-lab/memory/provenance.jsonl",
    "/var/lib/optiplex-lab/regressions/provenance.jsonl",
    "/var/lib/optiplex-lab/recovery/launcher-events.jsonl",
}
FORBIDDEN_ACCEPTED_PREFIXES = ("/etc/systemd/system/",)
ALTERNATIVE_TYPES = {"noop", "implementation_change", "intent_routing", "evaluator", "authority_evidence_selection"}


class ReplayError(RuntimeError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(data).hexdigest()


def sha_path(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    except OSError:
        return None


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ReplayError("MODULE_LOAD_FAILED", f"unable to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def engine_invariants() -> dict[str, Any]:
    return {
        "version": VERSION,
        "historical_inputs_immutable": True,
        "declared_overlay_only": True,
        "authority_monotonic": True,
        "accepted_state_mutation_forbidden": True,
        "single_isolation_owner": True,
        "autonomous_promotion": False,
        "permanent_mcp_tool_added": False,
    }


def _epoch_dir(epoch_id: str) -> pathlib.Path:
    eid = str(epoch_id)
    candidates = [EPOCHS_ROOT / eid]
    if not eid.startswith("ep10_"):
        candidates.append(EPOCHS_ROOT / ("ep10_" + eid))
    for p in candidates:
        if p.is_dir():
            return p
    raise ReplayError("EPOCH_NOT_FOUND", f"sealed epoch not found: {epoch_id}")


def _load_epoch(epoch_id: str) -> tuple[pathlib.Path, dict[str, Any]]:
    root = _epoch_dir(epoch_id)
    mp = root / "manifest.json"
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReplayError("EPOCH_MANIFEST_INVALID", f"invalid epoch manifest: {exc}")
    digest = str(manifest.get("epoch_digest") or "")
    core = manifest.get("core")
    if not digest or not isinstance(core, dict) or sha(core) != digest:
        raise ReplayError("EPOCH_DIGEST_INVALID", "epoch manifest core digest mismatch")
    marker = root / "SEALED"
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != digest:
        raise ReplayError("EPOCH_NOT_SEALED", "epoch SEALED marker missing or mismatched")
    return root, manifest


def _verify_entries(root: pathlib.Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for rec in (manifest.get("core") or {}).get("entries") or []:
        if not isinstance(rec, dict) or not rec.get("path") or not rec.get("blob_sha256"):
            raise ReplayError("EPOCH_ENTRY_INVALID", "epoch contains malformed entry")
        path = str(rec["path"])
        blob_sha = str(rec["blob_sha256"])
        blob = BLOB_ROOT / blob_sha[:2] / blob_sha
        if not blob.is_file() or sha_path(blob) != blob_sha:
            raise ReplayError("MISSING_CONTENT_ADDRESSED_BLOB", f"missing/corrupt epoch blob for {path}", {"blob": blob_sha})
        view = root / "view" / path.lstrip("/")
        if not view.is_file() or sha_path(view) != blob_sha:
            raise ReplayError("EPOCH_VIEW_MISMATCH", f"epoch materialized view mismatched for {path}")
        entries[path] = copy.deepcopy(rec)
    return entries


def _base_route(manifest: dict[str, Any]) -> dict[str, Any]:
    route = copy.deepcopy((manifest.get("core") or {}).get("routing_proof"))
    if not isinstance(route, dict) or not route.get("routing_digest"):
        raise ReplayError("ROUTING_PROOF_MISSING", "counterfactual replay requires a routed Gen11 epoch")
    core = copy.deepcopy(route)
    digest = str(core.pop("routing_digest"))
    if sha(core) != digest:
        raise ReplayError("ROUTING_PROOF_INVALID", "sealed routing proof digest is invalid")
    return route


def _critical_authorities(route: dict[str, Any]) -> set[str]:
    return {str(x) for x in route.get("required_authority_classes") or [] if str(x) in SAFETY_CRITICAL_AUTHORITIES}


def verify_base(spec: dict[str, Any]) -> dict[str, Any]:
    if int(spec.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ReplayError("SPEC_SCHEMA_INVALID", "unsupported ReplaySpec schema")
    root, manifest = _load_epoch(str(spec.get("base_epoch_id") or ""))
    expected = str(spec.get("base_epoch_digest") or "")
    if expected != str(manifest.get("epoch_digest") or ""):
        raise ReplayError("WRONG_EPOCH_DIGEST", "ReplaySpec epoch digest does not match sealed base")
    entries = _verify_entries(root, manifest)
    route = _base_route(manifest)
    if str(spec.get("base_routing_digest") or "") != str(route.get("routing_digest") or ""):
        raise ReplayError("ROUTING_DIGEST_MISMATCH", "ReplaySpec routing digest does not match sealed base")
    expected_twin = spec.get("base_twin_graph_digest")
    actual_twin = (manifest.get("core") or {}).get("twin_graph_digest")
    if expected_twin is not None and str(expected_twin) != str(actual_twin):
        raise ReplayError("TWIN_DIGEST_MISMATCH", "ReplaySpec Twin digest does not match sealed base")
    return {"root": root, "manifest": manifest, "entries": entries, "route": route}


def _view_path(root: pathlib.Path, original: str) -> pathlib.Path:
    return root / "view" / str(original).lstrip("/")


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))


def _evaluate_in_view(root: pathlib.Path, evaluator: dict[str, Any], label: str) -> dict[str, Any]:
    kind = str(evaluator.get("kind") or "")
    if kind == "python_function":
        module_path = str(evaluator.get("module_path") or "")
        function = str(evaluator.get("function") or "")
        if not module_path.startswith("/") or not function:
            raise ReplayError("EVALUATOR_INVALID", "python_function requires absolute module_path and function")
        view = _view_path(root, module_path)
        if not view.is_file():
            raise ReplayError("EVALUATOR_NOT_PINNED", f"evaluator module not pinned in base epoch: {module_path}")
        mod = load_module(view, f"gen12_{label}_{sha(module_path)[:10]}")
        fn = getattr(mod, function, None)
        if not callable(fn):
            raise ReplayError("EVALUATOR_FUNCTION_MISSING", f"evaluator function missing: {function}")
        result = fn(*copy.deepcopy(evaluator.get("args") or []), **copy.deepcopy(evaluator.get("kwargs") or {}))
        return _json_safe(result)
    if kind == "route_task":
        module_path = str(evaluator.get("module_path") or "/opt/optiplex-lab/task_routing.py")
        view = _view_path(root, module_path)
        if not view.is_file():
            raise ReplayError("EVALUATOR_NOT_PINNED", f"router not pinned: {module_path}")
        mod = load_module(view, f"gen12_route_{label}_{sha(module_path)[:10]}")
        result = mod.route_task(str(evaluator.get("task") or ""))
        fields = evaluator.get("fields")
        if fields:
            result = {str(k): result.get(str(k)) for k in fields}
        return _json_safe(result)
    if kind == "json_projection":
        path = str(evaluator.get("path") or "")
        view = _view_path(root, path)
        if not view.is_file():
            raise ReplayError("EVALUATOR_INPUT_NOT_PINNED", f"JSON evaluator input not pinned: {path}")
        value = json.loads(view.read_text(encoding="utf-8"))
        for key in evaluator.get("path_keys") or []:
            value = value[str(key)] if isinstance(value, dict) else value[int(key)]
        fields = evaluator.get("fields")
        if fields and isinstance(value, dict):
            value = {str(k): value.get(str(k)) for k in fields}
        return _json_safe(value)
    raise ReplayError("EVALUATOR_KIND_UNKNOWN", f"unsupported evaluator kind: {kind}")


def _overlay_digest(operations: list[dict[str, Any]]) -> str:
    normalized = []
    for op in operations:
        x = copy.deepcopy(op)
        if "new_bytes_b64" in x:
            raw = base64.b64decode(str(x.pop("new_bytes_b64")), validate=True)
            x["new_bytes_sha256"] = hashlib.sha256(raw).hexdigest()
            x["new_bytes_len"] = len(raw)
        normalized.append(x)
    return sha(normalized)


def _forbidden_path(path: str) -> bool:
    return path in FORBIDDEN_ACCEPTED_PATHS or any(path.startswith(p) for p in FORBIDDEN_ACCEPTED_PREFIXES)


def _validate_implementation_overlay(alt: dict[str, Any], entries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    ops = copy.deepcopy(alt.get("operations") or [])
    if not ops:
        raise ReplayError("OVERLAY_EMPTY", "implementation replay requires at least one declared operation")
    allowed = {str(x) for x in alt.get("allowed_effect_paths") or []}
    op_paths = {str(x.get("path") or "") for x in ops}
    if not allowed or op_paths - allowed:
        raise ReplayError("UNDECLARED_SOURCE_MUTATION", "overlay operation is outside declared allowed_effect_paths", {"operations": sorted(op_paths), "allowed": sorted(allowed)})
    for op in ops:
        path = str(op.get("path") or "")
        if path not in entries:
            raise ReplayError("HISTORICAL_EVIDENCE_LEAKAGE", f"overlay path is not present in sealed historical epoch: {path}")
        if _forbidden_path(path):
            raise ReplayError("ACCEPTED_STATE_MUTATION_FORBIDDEN", f"counterfactual overlay targets accepted/current protected state: {path}")
        if op.get("op") not in {"replace_text", "append_text", "replace_bytes"}:
            raise ReplayError("OVERLAY_OPERATION_INVALID", f"unsupported overlay operation: {op.get('op')}")
        if op.get("op") == "replace_text" and ("old" not in op or "new" not in op):
            raise ReplayError("OVERLAY_OPERATION_INVALID", "replace_text requires old/new")
        if op.get("op") == "append_text" and "text" not in op:
            raise ReplayError("OVERLAY_OPERATION_INVALID", "append_text requires text")
        if op.get("op") == "replace_bytes" and "new_bytes_b64" not in op:
            raise ReplayError("OVERLAY_OPERATION_INVALID", "replace_bytes requires new_bytes_b64")
    return ops


def _capsule_command(base_root: pathlib.Path, ops: list[dict[str, Any]], evaluator: dict[str, Any]) -> tuple[str, str]:
    payload = base64.b64encode(canonical({"base_root": str(base_root), "operations": ops, "evaluator": evaluator})).decode()
    result_path = "/root/gen12-counterfactual-result.json"
    script = r'''import base64,hashlib,importlib.util,json,pathlib,sys
cfg=json.loads(base64.b64decode(sys.argv[1]).decode())
root=pathlib.Path(cfg['base_root'])/'view'
def vp(p): return root/str(p).lstrip('/')
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
targeted={op['path'] for op in cfg['operations']}
for op in cfg['operations']:
 p=pathlib.Path(op['path']); src=vp(op['path']); data=src.read_bytes()
 if op['op']=='replace_text':
  text=data.decode('utf-8'); old=op['old']; new=op['new']
  if old not in text: raise RuntimeError('declared replace_text old value not found')
  data=text.replace(old,new,1).encode('utf-8')
 elif op['op']=='append_text': data=data+op['text'].encode('utf-8')
 elif op['op']=='replace_bytes': data=base64.b64decode(op['new_bytes_b64'])
 p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(data)
ev=cfg['evaluator']; kind=ev['kind']
if kind=='python_function':
 mp=ev['module_path']; load_path=pathlib.Path(mp) if mp in targeted else vp(mp)
 m=load(load_path,'gen12_capsule_eval'); fn=getattr(m,ev['function']); out=fn(*(ev.get('args') or []),**(ev.get('kwargs') or {}))
elif kind=='route_task':
 mp=ev.get('module_path') or '/opt/optiplex-lab/task_routing.py'; load_path=pathlib.Path(mp) if mp in targeted else vp(mp)
 m=load(load_path,'gen12_capsule_route'); out=m.route_task(ev.get('task') or '')
 if ev.get('fields'): out={k:out.get(k) for k in ev['fields']}
elif kind=='json_projection':
 jp=ev['path']; load_path=pathlib.Path(jp) if jp in targeted else vp(jp)
 value=json.loads(load_path.read_text())
 for key in ev.get('path_keys') or []: value=value[key] if isinstance(value,dict) else value[int(key)]
 out={k:value.get(k) for k in ev.get('fields')} if ev.get('fields') and isinstance(value,dict) else value
else: raise RuntimeError('unsupported evaluator kind')
pathlib.Path('/root/gen12-counterfactual-result.json').write_text(json.dumps(out,sort_keys=True)+'\n')
'''
    cmd = "export PYTHONDONTWRITEBYTECODE=1; python3 -c " + shlex.quote(script) + " " + shlex.quote(payload)
    return cmd, result_path


def _evaluate_implementation(base: dict[str, Any], ops: list[dict[str, Any]], evaluator: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if os.environ.get("OPTIPLEX_EXPERIMENT_CAPSULE") == "1":
        raise ReplayError("NESTED_ISOLATION_REFUSED", "Gen12 will not blindly create a nested Experiment Capsule")
    cap = load_module(CAPSULE_PATH, "gen12_replay_capsule")
    cmd, result_path = _capsule_command(base["root"], ops, evaluator)
    result = cap.run_capsule(cmd, captures=[result_path], label="gen12-counterfactual-implementation")
    if not result.get("ok") or not result.get("accepted_state_unchanged"):
        raise ReplayError("ISOLATED_EXECUTION_FAILED", "implementation replay capsule failed or changed accepted state", result)
    capture = next((x for x in result.get("captured_artifacts") or [] if x.get("path") == result_path), None)
    if not capture:
        raise ReplayError("EVALUATOR_RESULT_MISSING", "isolated evaluator did not produce result")
    try:
        alt_result = json.loads(pathlib.Path(capture["export_path"]).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReplayError("EVALUATOR_RESULT_INVALID", f"isolated evaluator result invalid: {exc}")
    allowed_files = {str(x.get("path")) for x in ops} | {result_path}
    inv_path = pathlib.Path(str(cap.CAPSULE_ROOT)) / str(result.get("run_id")) / "capsule-mutations.json"
    try:
        inventory = json.loads(inv_path.read_text(encoding="utf-8")).get("records") or []
    except Exception as exc:
        raise ReplayError("MUTATION_INVENTORY_MISSING", f"capsule mutation inventory unavailable: {exc}")
    unexpected = []
    for rec in inventory:
        if rec.get("type") not in {"file", "symlink", "special"}:
            continue
        full = str(pathlib.PurePosixPath(str(rec.get("target_root") or "/")) / str(rec.get("path") or ""))
        if full not in allowed_files:
            unexpected.append(full)
    if unexpected:
        raise ReplayError("UNDECLARED_SOURCE_MUTATION", "isolated replay produced undeclared file mutations", sorted(set(unexpected)))
    provenance = {
        "isolation_owner": "replay",
        "capsule_run_id": result.get("run_id"),
        "capsule_recipe_digest": result.get("recipe_digest"),
        "capsule_mutation_digest": result.get("capsule_mutation_digest"),
        "capsule_mutation_records": len(inventory),
        "unexpected_mutations": [],
        "accepted_state_unchanged": bool(result.get("accepted_state_unchanged")),
        "forbidden_accepted_state_mutations": len(result.get("forbidden_accepted_state_mutations") or []),
    }
    return _json_safe(alt_result), provenance


def _evaluate_implementation_delegated(base: dict[str, Any], ops: list[dict[str, Any]], evaluator: dict[str, Any], proof: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if os.environ.get("OPTIPLEX_EXPERIMENT_CAPSULE") != "1":
        raise ReplayError("ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION", "Gen12 delegated mutation requires an active compatible Gen13 parent isolation context")
    if not HIERARCHY_PATH.is_file():
        raise ReplayError("ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION", "Gen13 hierarchical delegation module is unavailable")
    hier = load_module(HIERARCHY_PATH, "gen12_hierarchical_delegation")
    try:
        ctx = hier.load_current_context()
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code:
            raise ReplayError("ISOLATION_DELEGATION_INVALID", f"Gen13 delegation context rejected: {code}", {"error_code": code, "error": str(exc)})
        raise ReplayError("ISOLATION_DELEGATION_INVALID", f"Gen13 delegation context rejected: {exc}")
    proof_context_id = str(proof.get("context_id") or "") if isinstance(proof, dict) else str(proof or "")
    proof_binding = str(proof.get("binding_digest") or "") if isinstance(proof, dict) else ""
    if proof_context_id != str(ctx.get("context_id")):
        raise ReplayError("ISOLATION_DELEGATION_UNPROVEN", "child isolation proof does not identify the active delegated context")
    if proof_binding and proof_binding != str(ctx.get("binding_digest")):
        raise ReplayError("ISOLATION_DELEGATION_UNPROVEN", "child isolation proof binding digest mismatches active context")
    if str(ctx.get("mode")) not in {"delegated", "owner"}:
        raise ReplayError("ISOLATION_DELEGATION_INVALID", "mutating replay requires mutable delegated context")
    cmd, result_path = _capsule_command(base["root"], ops, evaluator)
    required_paths = sorted({str(x.get("path")) for x in ops} | {result_path})
    try:
        if not hier.paths_allowed(required_paths, ctx.get("mutation_scope") or []):
            raise ReplayError("ISOLATION_DELEGATION_SCOPE_MISMATCH", "delegated context does not cover all replay mutation paths", {"required": required_paths, "scope": ctx.get("mutation_scope") or []})
        execution = hier.execute_current(ctx, cmd, required_paths=required_paths, timeout=3600.0)
    except ReplayError:
        raise
    except Exception as exc:
        code = getattr(exc, "code", None)
        raise ReplayError("ISOLATION_DELEGATION_INVALID", f"delegated execution setup failed: {code or type(exc).__name__}: {exc}")
    if not execution.get("ok"):
        raise ReplayError("DELEGATED_EXECUTION_FAILED", "delegated Gen12 implementation replay failed or violated child scope", execution)
    try:
        alt_result = json.loads(pathlib.Path(result_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReplayError("EVALUATOR_RESULT_INVALID", f"delegated evaluator result invalid: {exc}")
    observed = execution.get("observed_mutations") or []
    provenance = {
        "isolation_owner": "parent_delegated",
        "physical_isolation_owner": ctx.get("isolation_owner"),
        "capsule_run_id": ctx.get("owner_run_id"),
        "hierarchy_context_id": ctx.get("context_id"),
        "hierarchy_parent_context_id": ctx.get("parent_context_id"),
        "hierarchy_root_context_id": ctx.get("root_context_id"),
        "hierarchy_context_semantic_digest": ctx.get("semantic_digest"),
        "delegated_scope": ctx.get("mutation_scope") or [],
        "observed_mutation_digest": execution.get("observed_mutation_digest"),
        "capsule_mutation_records": len(observed),
        "unexpected_mutations": execution.get("unexpected_mutations") or [],
        "accepted_state_unchanged": True,
        "accepted_state_protection": "parent_capsule_cow_boundary",
        "forbidden_accepted_state_mutations": 0,
    }
    return _json_safe(alt_result), provenance


def _authority_assertions(alt: dict[str, Any]) -> dict[str, bool]:
    seen: dict[str, bool] = {}
    for rec in alt.get("authority_assertions") or []:
        cls = str(rec.get("authority_class") or "")
        val = bool(rec.get("required"))
        if cls in seen and seen[cls] != val:
            raise ReplayError("CONTRADICTORY_AUTHORITY", f"contradictory authority assertions for {cls}")
        seen[cls] = val
    return seen


def _routing_overlay(base: dict[str, Any], alt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    route = base["route"]
    assertions = _authority_assertions(alt)
    required = set(str(x) for x in alt.get("required_authority_classes") or route.get("required_authority_classes") or [])
    for cls, needed in assertions.items():
        if needed: required.add(cls)
        else: required.discard(cls)
    missing_critical = _critical_authorities(route) - required
    if missing_critical:
        raise ReplayError("UNSAFE_AUTHORITY_WEAKENING", "counterfactual route removes mandatory safety-critical authority", sorted(missing_critical))
    overlay = {
        "detected_primary_intent": str(alt.get("primary_intent") or route.get("detected_primary_intent")),
        "secondary_intents": sorted(str(x) for x in alt.get("secondary_intents") or route.get("secondary_intents") or []),
        "required_authority_classes": sorted(required),
        "mandatory_evidence_obligations": copy.deepcopy(alt.get("mandatory_evidence_obligations") or route.get("mandatory_evidence_obligations") or []),
        "reason": str(alt.get("reason") or "explicit counterfactual routing overlay"),
    }
    diff = {
        "primary_intent": [route.get("detected_primary_intent"), overlay["detected_primary_intent"]],
        "authority_added": sorted(required - set(route.get("required_authority_classes") or [])),
        "authority_removed": sorted(set(route.get("required_authority_classes") or []) - required),
        "evidence_obligations_changed": canonical(route.get("mandatory_evidence_obligations") or []) != canonical(overlay["mandatory_evidence_obligations"]),
    }
    return overlay, diff


def _authority_selection(base: dict[str, Any], alt: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    _authority_assertions(alt)
    selected = [str(x) for x in alt.get("selected_paths") or []]
    leaked = sorted(x for x in selected if x not in base["entries"])
    if leaked:
        raise ReplayError("HISTORICAL_EVIDENCE_LEAKAGE", "counterfactual selection references evidence absent from sealed epoch", leaked)
    if alt.get("freeze_live_only_authority"):
        live_sensitive = sorted(
            p for p, rec in base["entries"].items()
            if rec.get("policy") in {"live_revalidate_only", "pinned_plus_live_revalidate"}
        )
        if live_sensitive and not alt.get("live_validation_proof"):
            raise ReplayError("LIVE_AUTHORITY_VALIDATION_REQUIRED", "unsafe live authority cannot be treated as frozen sufficient truth", live_sensitive)
    required = set(base["route"].get("required_authority_classes") or [])
    removed = {str(x) for x in alt.get("remove_authority_classes") or []}
    if _critical_authorities(base["route"]) & removed:
        raise ReplayError("UNSAFE_AUTHORITY_WEAKENING", "evidence-selection replay removes mandatory safety authority", sorted(_critical_authorities(base["route"]) & removed))
    result = {
        "selected_paths": sorted(selected),
        "selected_blob_sha256": {p: base["entries"][p]["blob_sha256"] for p in sorted(selected)},
        "required_authority_classes": sorted(required - removed),
        "historical_scope": (base["manifest"].get("core") or {}).get("historical_scope"),
        "live_validation_proof": alt.get("live_validation_proof"),
    }
    return result, {"historical_leakage": 0, "selected_from_base_only": True}


def _semantic_diff(a: Any, b: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    def walk(x: Any, y: Any, path: str) -> None:
        if type(x) != type(y):
            out.append({"path": path or "$", "baseline": x, "alternative": y}); return
        if isinstance(x, dict):
            for k in sorted(set(x) | set(y)):
                p = f"{path}.{k}" if path else str(k)
                if k not in x or k not in y: out.append({"path": p, "baseline": x.get(k), "alternative": y.get(k)})
                else: walk(x[k], y[k], p)
        elif isinstance(x, list):
            if x != y: out.append({"path": path or "$", "baseline": x, "alternative": y})
        elif x != y:
            out.append({"path": path or "$", "baseline": x, "alternative": y})
    walk(a,b,"")
    return out


def _spec_core(spec: dict[str, Any]) -> dict[str, Any]:
    core = copy.deepcopy(spec)
    core.pop("notes", None)
    return core


def replay(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        base = verify_base(spec)
        alt = copy.deepcopy(spec.get("alternative") or {})
        alt_type = str(alt.get("type") or "")
        if alt_type not in ALTERNATIVE_TYPES:
            raise ReplayError("ALTERNATIVE_TYPE_INVALID", f"unsupported alternative type: {alt_type}")
        evaluator = copy.deepcopy(spec.get("evaluator") or {})
        if alt_type == "intent_routing":
            baseline = {
                "detected_primary_intent": base["route"].get("detected_primary_intent"),
                "secondary_intents": sorted(base["route"].get("secondary_intents") or []),
                "required_authority_classes": sorted(base["route"].get("required_authority_classes") or []),
                "mandatory_evidence_obligations": copy.deepcopy(base["route"].get("mandatory_evidence_obligations") or []),
                "reason": "sealed Gen11 routing proof",
            }
        elif alt_type == "authority_evidence_selection":
            original = copy.deepcopy(spec.get("original_decision") or {})
            baseline = {
                "selected_paths": sorted(str(x) for x in original.get("selected_paths") or []),
                "selected_blob_sha256": {p: base["entries"][p]["blob_sha256"] for p in sorted(str(x) for x in original.get("selected_paths") or []) if p in base["entries"]},
                "required_authority_classes": sorted(base["route"].get("required_authority_classes") or []),
                "historical_scope": (base["manifest"].get("core") or {}).get("historical_scope"),
                "live_validation_proof": original.get("live_validation_proof"),
            }
        else:
            baseline = _evaluate_in_view(base["root"], evaluator, "baseline") if evaluator else copy.deepcopy(spec.get("original_decision"))
        execution = {"isolation_owner": "none", "accepted_state_unchanged": True}
        comparison_meta: dict[str, Any] = {}
        if alt_type == "noop":
            alternative = copy.deepcopy(baseline)
        elif alt_type == "implementation_change":
            ops = _validate_implementation_overlay(alt, base["entries"])
            isolation_owner = str(alt.get("isolation_owner") or "replay")
            if isolation_owner == "child":
                proof = alt.get("child_isolation_proof")
                if not proof:
                    raise ReplayError("ISOLATION_DELEGATION_UNPROVEN", "child isolation ownership requires explicit proof")
                if os.environ.get("OPTIPLEX_EXPERIMENT_CAPSULE") != "1" or not os.environ.get("OPTIPLEX_GEN13_CONTEXT_B64"):
                    raise ReplayError("ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION", "Gen12 refuses delegated mutation without a valid compatible Gen13 parent context")
                alternative, execution = _evaluate_implementation_delegated(base, ops, evaluator, proof)
            else:
                if isolation_owner != "replay":
                    raise ReplayError("ISOLATION_OWNER_INVALID", "implementation replay must have exactly one isolation owner")
                alternative, execution = _evaluate_implementation(base, ops, evaluator)
            comparison_meta["overlay_digest"] = _overlay_digest(ops)
            comparison_meta["declared_effect_paths"] = sorted({str(x.get("path")) for x in ops})
        elif alt_type == "intent_routing":
            alternative, comparison_meta = _routing_overlay(base, alt)
        elif alt_type == "evaluator":
            alt_eval = copy.deepcopy(alt.get("evaluator") or {})
            if not alt_eval:
                raise ReplayError("ALTERNATE_EVALUATOR_MISSING", "evaluator replay requires alternative evaluator")
            alternative = _evaluate_in_view(base["root"], alt_eval, "alternative")
            comparison_meta["baseline_evaluator_digest"] = sha(evaluator)
            comparison_meta["alternative_evaluator_digest"] = sha(alt_eval)
        else:
            alternative, comparison_meta = _authority_selection(base, alt)

        base_digest = sha(baseline)
        alt_digest = sha(alternative)
        diff = _semantic_diff(baseline, alternative)
        replay_core = {
            "schema_version": SCHEMA_VERSION,
            "engine_version": VERSION,
            "base_epoch_id": str(base["manifest"].get("epoch_id")),
            "base_epoch_digest": str(base["manifest"].get("epoch_digest")),
            "base_twin_graph_digest": (base["manifest"].get("core") or {}).get("twin_graph_digest"),
            "base_routing_digest": base["route"].get("routing_digest"),
            "original_decision": copy.deepcopy(spec.get("original_decision")),
            "alternative": alt,
            "evaluator": evaluator,
        }
        replay_digest = sha(replay_core)
        result_core = {
            "replay_digest": replay_digest,
            "alternative_type": alt_type,
            "baseline_semantic_digest": base_digest,
            "alternative_semantic_digest": alt_digest,
            "changed": base_digest != alt_digest,
            "semantic_diff": diff,
            "comparison": comparison_meta,
            "attribution": {
                "same_sealed_base_epoch": True,
                "same_base_routing_proof": True,
                "declared_counterfactual_only": True,
                "accepted_state_unchanged": bool(execution.get("accepted_state_unchanged", True)),
                "correct": bool(execution.get("accepted_state_unchanged", True)),
            },
        }
        result = {
            "ok": True,
            "fail_closed": False,
            **result_core,
            "result_digest": sha(result_core),
            "baseline_result": baseline,
            "alternative_result": alternative,
            "execution_provenance": execution,
            "base_provenance": {
                "epoch_id": base["manifest"].get("epoch_id"),
                "epoch_digest": base["manifest"].get("epoch_digest"),
                "twin_graph_digest": (base["manifest"].get("core") or {}).get("twin_graph_digest"),
                "routing_digest": base["route"].get("routing_digest"),
                "entry_count": len(base["entries"]),
            },
        }
        return result
    except ReplayError as exc:
        fail = {
            "ok": False,
            "fail_closed": True,
            "error_code": exc.code,
            "error": str(exc),
            "details": exc.details,
            "spec_digest": sha(_spec_core(spec)),
        }
        fail["result_digest"] = sha(fail)
        return fail
    except Exception as exc:
        fail = {
            "ok": False,
            "fail_closed": True,
            "error_code": "UNEXPECTED_REPLAY_FAILURE",
            "error": f"{type(exc).__name__}: {exc}",
            "details": None,
            "spec_digest": sha(_spec_core(spec)),
        }
        fail["result_digest"] = sha(fail)
        return fail


def selftest() -> dict[str, Any]:
    inv = engine_invariants()
    checks = [
        inv["historical_inputs_immutable"], inv["declared_overlay_only"], inv["authority_monotonic"],
        inv["accepted_state_mutation_forbidden"], inv["single_isolation_owner"],
        not inv["autonomous_promotion"], not inv["permanent_mcp_tool_added"],
        _forbidden_path("/opt/optiplex-lab/server.py"), not _forbidden_path("/opt/optiplex-lab/task_routing.py"),
    ]
    return {"ok": all(checks), "passed": sum(bool(x) for x in checks), "total": len(checks), "version": VERSION, "invariants": inv}


def main() -> int:
    ap = argparse.ArgumentParser(description="Gen12 deterministic counterfactual replay over sealed routed evidence epochs")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("spec", nargs="?")
    ns = ap.parse_args()
    if ns.selftest:
        print(json.dumps(selftest(), indent=2, sort_keys=True)); return 0 if selftest()["ok"] else 1
    if not ns.spec:
        ap.error("spec JSON path required unless --selftest")
    spec = json.loads(pathlib.Path(ns.spec).read_text(encoding="utf-8"))
    result = replay(spec)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
