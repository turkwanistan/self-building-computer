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
import signal
import subprocess
import time
from typing import Any

VERSION = "gen13-hierarchical-experiment-isolation-r1"
SCHEMA_VERSION = 1
CAPSULE_PATH = pathlib.Path(os.environ.get("OPTIPLEX_GEN13_CAPSULE_PATH", "/opt/optiplex-lab/experiment_capsule.py"))
CONTEXT_ENV = "OPTIPLEX_GEN13_CONTEXT_B64"
CAPSULE_ENV = "OPTIPLEX_EXPERIMENT_CAPSULE"
RUN_ID_ENV = "OPTIPLEX_CAPSULE_RUN_ID"
RUN_DIR_ENV = "OPTIPLEX_CAPSULE_RUN_DIR"
MAX_DEPTH = 4
HARD_CHILD_FORBIDDEN_EXACT = {
    "/opt/optiplex-lab/server.py",
    "/etc/optiplex-lab/build.json",
    "/var/lib/optiplex-lab/recovery/server.last-known-good.py",
}
HARD_CHILD_FORBIDDEN_PREFIXES = ("/etc/systemd/system/",)


class ExperimentContextError(RuntimeError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ExperimentContextError("MODULE_LOAD_FAILED", f"unable to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _capsule_module():
    return _load(CAPSULE_PATH, "gen13_capsule_backend")


def _require_capsule() -> None:
    if os.environ.get(CAPSULE_ENV) != "1":
        raise ExperimentContextError("PHYSICAL_ISOLATION_REQUIRED", "hierarchical execution requires one active Experiment Capsule owner")


def _owner_run_id(explicit: str | None = None) -> str:
    run_id = explicit or os.environ.get(RUN_ID_ENV, "")
    if not run_id:
        raise ExperimentContextError("ISOLATION_OWNER_MISSING", "active Capsule owner run id is required")
    return run_id


def _normalize_scope_item(item: str) -> dict[str, str]:
    raw = str(item).strip()
    mode = "subtree" if raw.endswith("/**") else "exact"
    raw = raw[:-3] if mode == "subtree" else raw
    if not raw.startswith("/"):
        raise ExperimentContextError("PATH_SCOPE_INVALID", f"delegated path must be absolute: {item}")
    p = pathlib.PurePosixPath(raw)
    if ".." in p.parts or "." in p.parts:
        raise ExperimentContextError("PATH_SCOPE_INVALID", f"delegated path may not traverse: {item}")
    norm = str(p)
    if norm == "/":
        raise ExperimentContextError("PATH_SCOPE_INVALID", "delegating filesystem root is forbidden")
    return {"path": norm, "mode": mode}


def normalize_scope(items: list[str] | tuple[str, ...] | None) -> list[dict[str, str]]:
    seen: dict[tuple[str, str], dict[str, str]] = {}
    for item in items or []:
        rec = _normalize_scope_item(str(item))
        seen[(rec["path"], rec["mode"])] = rec
    return [seen[k] for k in sorted(seen)]


def _scope_contains(parent: dict[str, str], child: dict[str, str]) -> bool:
    pp = pathlib.PurePosixPath(parent["path"])
    cp = pathlib.PurePosixPath(child["path"])
    if parent["mode"] == "exact":
        return child["mode"] == "exact" and cp == pp
    return cp == pp or pp in cp.parents


def scope_is_subset(child_scope: list[dict[str, str]], parent_scope: list[dict[str, str]]) -> bool:
    return all(any(_scope_contains(p, c) for p in parent_scope) for c in child_scope)


def path_allowed(path: str, scope: list[dict[str, str]]) -> bool:
    rec = _normalize_scope_item(path)
    rec["mode"] = "exact"
    return any(_scope_contains(parent, rec) for parent in scope)


def paths_allowed(paths: list[str] | set[str] | tuple[str, ...], scope: list[dict[str, str]]) -> bool:
    return all(path_allowed(str(p), scope) for p in paths)


def mutation_record_allowed(record: dict[str, Any], scope: list[dict[str, str]]) -> bool:
    path = str(record.get("path") or "")
    if path_allowed(path, scope):
        return True
    # OverlayFS may copy up ancestor directory metadata solely to materialize a
    # delegated descendant file. Treat only those structural ancestor records as
    # implied by the descendant delegation; unrelated directory creation still fails.
    if record.get("type") == "dir":
        rp = pathlib.PurePosixPath(path)
        for delegated in scope:
            dp = pathlib.PurePosixPath(delegated["path"])
            if rp in dp.parents:
                return True
    return False


def _hard_child_forbidden(scope: list[dict[str, str]]) -> list[str]:
    bad=[]
    for rec in scope:
        path=rec["path"]
        if path in HARD_CHILD_FORBIDDEN_EXACT or any(path == p.rstrip("/") or path.startswith(p) or (rec["mode"] == "subtree" and p.rstrip("/").startswith(path.rstrip("/") + "/")) for p in HARD_CHILD_FORBIDDEN_PREFIXES):
            bad.append(path + ("/**" if rec["mode"] == "subtree" else ""))
    return sorted(set(bad))


def _root_semantic_core(*, name: str, scope: list[dict[str, str]], authorities: list[str], evidence: dict[str, Any], evaluator: dict[str, Any], result_policy: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "mode": "owner",
        "parent_context_id": None,
        "root_context_id": "SELF",
        "depth": 0,
        "mutation_scope": scope,
        "authorities": sorted(set(authorities)),
        "evidence_bindings": copy.deepcopy(evidence),
        "evaluator": copy.deepcopy(evaluator),
        "lineage": ["SELF"],
        "result_policy": result_policy,
        "cleanup_responsibility": "physical_isolation_owner",
        "isolation_backend": "gen8_experiment_capsule",
    }


def _child_semantic_core(parent: dict[str, Any], *, name: str, mode: str, scope: list[dict[str, str]], authorities: list[str], evidence: dict[str, Any], evaluator: dict[str, Any], result_policy: str) -> dict[str, Any]:
    return {
        "version": VERSION,
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "mode": mode,
        "parent_context_id": parent["context_id"],
        "root_context_id": parent["root_context_id"],
        "depth": int(parent["depth"]) + 1,
        "mutation_scope": scope,
        "authorities": sorted(set(authorities)),
        "evidence_bindings": copy.deepcopy(evidence),
        "evaluator": copy.deepcopy(evaluator),
        "lineage": list(parent["lineage"]) + ["SELF"],
        "result_policy": result_policy,
        "cleanup_responsibility": "physical_isolation_owner",
        "isolation_backend": "gen8_experiment_capsule",
    }


def _bind_context(core: dict[str, Any], *, owner_run_id: str, parent_binding_digest: str | None) -> dict[str, Any]:
    semantic_digest = sha(core)
    context_id = "hx13_" + semantic_digest[:24]
    ctx = copy.deepcopy(core)
    if ctx["depth"] == 0:
        ctx["root_context_id"] = context_id
        ctx["lineage"] = [context_id]
    else:
        ctx["lineage"][-1] = context_id
    binding_core = {
        "semantic_digest": semantic_digest,
        "context_id": context_id,
        "owner_run_id": owner_run_id,
        "parent_binding_digest": parent_binding_digest,
    }
    ctx.update({
        "context_id": context_id,
        "semantic_digest": semantic_digest,
        "owner_run_id": owner_run_id,
        "isolation_owner": "capsule:" + owner_run_id,
        "parent_binding_digest": parent_binding_digest,
        "binding_digest": sha(binding_core),
    })
    return ctx


def _semantic_core_from_context(ctx: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "version","schema_version","name","mode","parent_context_id","root_context_id","depth",
        "mutation_scope","authorities","evidence_bindings","evaluator","lineage","result_policy",
        "cleanup_responsibility","isolation_backend",
    ]
    core = {k: copy.deepcopy(ctx.get(k)) for k in keys}
    if int(core.get("depth") or 0) == 0:
        core["root_context_id"] = "SELF"
        core["lineage"] = ["SELF"]
    else:
        if core.get("lineage"):
            core["lineage"][-1] = "SELF"
    return core


def create_root_context(*, name: str = "root", mutation_scope: list[str] | None = None,
                        authorities: list[str] | None = None, evidence_bindings: dict[str, Any] | None = None,
                        evaluator: dict[str, Any] | None = None, result_policy: str = "fail_closed",
                        owner_run_id: str | None = None) -> dict[str, Any]:
    _require_capsule()
    core = _root_semantic_core(
        name=name,
        scope=normalize_scope(mutation_scope),
        authorities=authorities or [],
        evidence=evidence_bindings or {},
        evaluator=evaluator or {},
        result_policy=result_policy,
    )
    ctx = _bind_context(core, owner_run_id=_owner_run_id(owner_run_id), parent_binding_digest=None)
    validate_context(ctx)
    return ctx


def validate_context(ctx: dict[str, Any], *, expected_parent: dict[str, Any] | None = None,
                     require_current_owner: bool = True) -> dict[str, Any]:
    if not isinstance(ctx, dict):
        raise ExperimentContextError("CONTEXT_INVALID", "experiment context must be an object")
    if ctx.get("version") != VERSION or int(ctx.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ExperimentContextError("CONTEXT_VERSION_INVALID", "unsupported experiment context version")
    depth = int(ctx.get("depth") or 0)
    if depth < 0 or depth > MAX_DEPTH:
        raise ExperimentContextError("DELEGATION_DEPTH_INVALID", f"unsupported delegation depth: {depth}")
    scope = normalize_scope([r["path"] + ("/**" if r.get("mode") == "subtree" else "") for r in ctx.get("mutation_scope") or []])
    if scope != ctx.get("mutation_scope"):
        raise ExperimentContextError("CONTEXT_SCOPE_NONCANONICAL", "mutation scope is not canonical")
    core = _semantic_core_from_context(ctx)
    semantic_digest = sha(core)
    context_id = "hx13_" + semantic_digest[:24]
    if ctx.get("semantic_digest") != semantic_digest or ctx.get("context_id") != context_id:
        raise ExperimentContextError("FORGED_DELEGATION_CONTEXT", "context semantic digest or id mismatch")
    binding = {
        "semantic_digest": semantic_digest,
        "context_id": context_id,
        "owner_run_id": str(ctx.get("owner_run_id") or ""),
        "parent_binding_digest": ctx.get("parent_binding_digest"),
    }
    if ctx.get("binding_digest") != sha(binding):
        raise ExperimentContextError("FORGED_DELEGATION_BINDING", "context owner binding digest mismatch")
    expected_owner = "capsule:" + str(ctx.get("owner_run_id") or "")
    if ctx.get("isolation_owner") != expected_owner:
        raise ExperimentContextError("FORGED_DELEGATION_BINDING", "context isolation owner label mismatches owner binding")
    if require_current_owner:
        _require_capsule()
        if ctx.get("owner_run_id") != _owner_run_id():
            raise ExperimentContextError("STALE_DELEGATION_CONTEXT", "context is bound to a different Capsule owner")
    if depth == 0:
        if ctx.get("mode") != "owner" or ctx.get("parent_context_id") is not None:
            raise ExperimentContextError("ROOT_CONTEXT_INVALID", "root context must own isolation and have no parent")
        if ctx.get("root_context_id") != context_id or ctx.get("lineage") != [context_id]:
            raise ExperimentContextError("ROOT_LINEAGE_INVALID", "root lineage is inconsistent")
    else:
        if ctx.get("mode") not in {"delegated","read_only"}:
            raise ExperimentContextError("DELEGATED_MODE_INVALID", "child cannot own independent isolation")
        if len(ctx.get("lineage") or []) != depth + 1 or (ctx.get("lineage") or [])[-1] != context_id:
            raise ExperimentContextError("LINEAGE_INVALID", "delegation lineage is malformed")
        if ctx.get("root_context_id") != (ctx.get("lineage") or [None])[0]:
            raise ExperimentContextError("ROOT_LINEAGE_MISMATCH", "root identity mismatches lineage")
    if ctx.get("mode") == "read_only" and ctx.get("mutation_scope"):
        raise ExperimentContextError("READ_ONLY_SCOPE_INVALID", "read-only child must have empty mutation scope")
    if expected_parent is not None:
        validate_context(expected_parent, require_current_owner=require_current_owner)
        if ctx.get("parent_context_id") != expected_parent.get("context_id"):
            raise ExperimentContextError("PARENT_ID_MISMATCH", "delegated parent id mismatch")
        if ctx.get("root_context_id") != expected_parent.get("root_context_id"):
            raise ExperimentContextError("ROOT_ID_MISMATCH", "delegated root id mismatch")
        if ctx.get("owner_run_id") != expected_parent.get("owner_run_id"):
            raise ExperimentContextError("ISOLATION_OWNER_MISMATCH", "child changed physical isolation owner")
        if ctx.get("parent_binding_digest") != expected_parent.get("binding_digest"):
            raise ExperimentContextError("PARENT_BINDING_MISMATCH", "child parent binding proof mismatch")
        if not scope_is_subset(ctx.get("mutation_scope") or [], expected_parent.get("mutation_scope") or []):
            raise ExperimentContextError("DELEGATED_SCOPE_EXPANSION", "child mutation scope exceeds parent")
        if not set(ctx.get("authorities") or []).issubset(set(expected_parent.get("authorities") or [])):
            raise ExperimentContextError("DELEGATED_AUTHORITY_EXPANSION", "child authority exceeds parent")
        pe = expected_parent.get("evidence_bindings") or {}
        for key, value in (ctx.get("evidence_bindings") or {}).items():
            if key not in pe or pe[key] != value:
                raise ExperimentContextError("EVIDENCE_BINDING_MISMATCH", f"child evidence differs from parent: {key}")
        if ctx.get("lineage") != list(expected_parent.get("lineage") or []) + [ctx.get("context_id")]:
            raise ExperimentContextError("LINEAGE_PARENT_MISMATCH", "child lineage does not extend parent")
    return ctx


def delegate_context(parent: dict[str, Any], *, name: str, mutation_scope: list[str] | None = None,
                     authorities: list[str] | None = None, evidence_bindings: dict[str, Any] | None = None,
                     evaluator: dict[str, Any] | None = None, read_only: bool = False,
                     result_policy: str = "fail_closed", isolation_mode: str = "delegated") -> dict[str, Any]:
    validate_context(parent)
    if isolation_mode != "delegated":
        raise ExperimentContextError("INCOMPATIBLE_NESTED_ISOLATION", "child may not create an independent Capsule over the same boundary")
    if int(parent["depth"]) + 1 > MAX_DEPTH:
        raise ExperimentContextError("DELEGATION_DEPTH_INVALID", f"maximum delegation depth is {MAX_DEPTH}")
    scope = [] if read_only else normalize_scope(mutation_scope)
    hard_forbidden = _hard_child_forbidden(scope)
    if hard_forbidden:
        raise ExperimentContextError("ACCEPTED_STATE_DELEGATION_FORBIDDEN", "child may not receive operational accepted-state mutation paths", hard_forbidden)
    if not scope_is_subset(scope, parent.get("mutation_scope") or []):
        raise ExperimentContextError("DELEGATED_SCOPE_EXPANSION", "requested child scope exceeds parent scope")
    auth = sorted(set(parent.get("authorities") or [] if authorities is None else authorities))
    if not set(auth).issubset(set(parent.get("authorities") or [])):
        raise ExperimentContextError("DELEGATED_AUTHORITY_EXPANSION", "requested child authority exceeds parent")
    pe = parent.get("evidence_bindings") or {}
    evidence = copy.deepcopy(pe if evidence_bindings is None else evidence_bindings)
    for key, value in evidence.items():
        if key not in pe or pe[key] != value:
            raise ExperimentContextError("EVIDENCE_BINDING_MISMATCH", f"requested child evidence differs from parent: {key}")
    core = _child_semantic_core(
        parent,
        name=name,
        mode="read_only" if read_only else "delegated",
        scope=scope,
        authorities=auth,
        evidence=evidence,
        evaluator=evaluator or {},
        result_policy=result_policy,
    )
    ctx = _bind_context(core, owner_run_id=parent["owner_run_id"], parent_binding_digest=parent["binding_digest"])
    validate_context(ctx, expected_parent=parent)
    return ctx


def encode_context(ctx: dict[str, Any]) -> str:
    validate_context(ctx)
    return base64.urlsafe_b64encode(canonical(ctx)).decode()


def decode_context(encoded: str, *, require_current_owner: bool = True) -> dict[str, Any]:
    try:
        ctx = json.loads(base64.urlsafe_b64decode(encoded.encode()).decode())
    except Exception as exc:
        raise ExperimentContextError("CONTEXT_DECODE_FAILED", f"invalid encoded context: {exc}")
    return validate_context(ctx, require_current_owner=require_current_owner)


def load_current_context() -> dict[str, Any]:
    encoded = os.environ.get(CONTEXT_ENV, "")
    if not encoded:
        raise ExperimentContextError("DELEGATION_CONTEXT_MISSING", "no Gen13 experiment context is active")
    return decode_context(encoded)


def context_env(ctx: dict[str, Any], base: dict[str, str] | None = None) -> dict[str, str]:
    validate_context(ctx)
    env = dict(base or os.environ)
    env[CONTEXT_ENV] = encode_context(ctx)
    env["OPTIPLEX_GEN13_CONTEXT_ID"] = ctx["context_id"]
    env["OPTIPLEX_GEN13_ROOT_CONTEXT_ID"] = ctx["root_context_id"]
    return env


def _record_full_path(rec: dict[str, Any]) -> str:
    return str(pathlib.PurePosixPath(str(rec.get("target_root") or "/")) / pathlib.PurePosixPath(str(rec.get("path") or "")))


def _inventory() -> dict[str, Any]:
    _require_capsule()
    raw_run_dir = os.environ.get(RUN_DIR_ENV, "")
    if not raw_run_dir:
        raise ExperimentContextError("CAPSULE_RUN_DIR_MISSING", "Capsule mutation inventory is unavailable")
    run_dir = pathlib.Path(raw_run_dir)
    return _capsule_module().mutation_inventory(run_dir)


def _inventory_map(inv: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_record_full_path(rec): copy.deepcopy(rec) for rec in inv.get("records") or []}


def mutation_delta(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    b = _inventory_map(before)
    a = _inventory_map(after)
    out=[]
    for path in sorted(set(b) | set(a)):
        if b.get(path) == a.get(path):
            continue
        rec = copy.deepcopy(a.get(path) or b.get(path) or {})
        out.append({
            "path": path,
            "change": "deleted_or_whiteout" if path not in a else ("created" if path not in b else "changed"),
            "type": rec.get("type"),
            "sha256": rec.get("sha256"),
            "bytes": rec.get("bytes"),
            "symlink_target": rec.get("target"),
        })
    return out


def _pids() -> set[int]:
    out=set()
    for p in pathlib.Path('/proc').iterdir():
        if p.name.isdigit():
            out.add(int(p.name))
    return out


def _cleanup_new_processes(before: set[int]) -> dict[str, Any]:
    me=os.getpid()
    initial=sorted(pid for pid in (_pids()-before) if pid != me)
    signaled=[]
    for pid in initial:
        try:
            os.kill(pid, signal.SIGTERM)
            signaled.append(pid)
        except (ProcessLookupError, PermissionError):
            pass
    if signaled:
        time.sleep(0.05)
    remaining=sorted(pid for pid in (_pids()-before) if pid != me)
    for pid in remaining:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    if remaining:
        time.sleep(0.05)
    final=sorted(pid for pid in (_pids()-before) if pid != me)
    return {"detected":initial,"terminated":sorted(set(signaled+remaining)),"remaining":final,"ok":not final}


def _run_process(command: str, *, env: dict[str,str], timeout: float) -> dict[str, Any]:
    proc = subprocess.Popen(['/bin/bash','-lc',command], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, start_new_session=True)
    timed_out=False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
    return {"exit_code":proc.returncode,"timed_out":timed_out,"stdout":stdout,"stderr":stderr}


def execute_current(ctx: dict[str, Any], command: str, *, required_paths: list[str] | None = None,
                    timeout: float = 30.0, expect_json: bool = False) -> dict[str, Any]:
    validate_context(ctx)
    required = sorted(set(str(x) for x in (required_paths or [])))
    if ctx.get("mode") == "read_only" and required:
        raise ExperimentContextError("READ_ONLY_MUTATION_REQUESTED", "read-only context cannot declare mutation paths")
    if not paths_allowed(required, ctx.get("mutation_scope") or []):
        raise ExperimentContextError("REQUIRED_PATH_NOT_DELEGATED", "required path is outside delegated scope", required)
    before_inv=_inventory()
    before_pids=_pids()
    proc=_run_process(command, env=context_env(ctx), timeout=float(timeout))
    cleanup=_cleanup_new_processes(before_pids)
    after_inv=_inventory()
    observed=mutation_delta(before_inv,after_inv)
    unexpected=[x['path'] for x in observed if not mutation_record_allowed(x,ctx.get('mutation_scope') or [])]
    parsed=None
    malformed=False
    if expect_json:
        try:
            parsed=json.loads(proc['stdout'])
        except Exception:
            malformed=True
    reported_mismatch=False
    if isinstance(parsed,dict) and 'reported_mutations' in parsed:
        reported=sorted(str(x) for x in parsed.get('reported_mutations') or [])
        actual=sorted(x['path'] for x in observed)
        reported_mismatch=(reported!=actual)
    status='PASS'
    reason=None
    if proc['timed_out']:
        status='FAIL'; reason='CHILD_TIMEOUT'
    elif proc['exit_code'] != 0:
        status='FAIL'; reason='CHILD_NONZERO'
    elif malformed:
        status='INVALID'; reason='MALFORMED_CHILD_RESULT'
    elif unexpected:
        status='INVALID'; reason='UNDECLARED_CHILD_MUTATION'
    elif reported_mismatch:
        status='INVALID'; reason='CHILD_MUTATION_REPORT_MISMATCH'
    elif cleanup.get('detected'):
        status='INVALID'; reason='CHILD_DESCENDANT_LEAK'
    elif not cleanup['ok']:
        status='CLEANUP_FAILED'; reason='CHILD_PROCESS_CLEANUP_FAILED'
    semantic_core={
        'context_id':ctx['context_id'],
        'context_semantic_digest':ctx['semantic_digest'],
        'status':status,
        'failure_reason':reason,
        'exit_code':proc['exit_code'],
        'timed_out':proc['timed_out'],
        'required_paths':required,
        'observed_mutations':observed,
        'unexpected_mutations':sorted(set(unexpected)),
        'cleanup_ok':cleanup['ok'],
    }
    return {
        'version':VERSION,
        'context_id':ctx['context_id'],
        'parent_context_id':ctx.get('parent_context_id'),
        'root_context_id':ctx['root_context_id'],
        'isolation_owner':ctx['isolation_owner'],
        'owner_run_id':ctx['owner_run_id'],
        'delegated_scope':ctx['mutation_scope'],
        'authorities':ctx['authorities'],
        'evidence_bindings':ctx['evidence_bindings'],
        'evaluator':ctx.get('evaluator') or {},
        'status':status,
        'failure_reason':reason,
        'ok':status=='PASS',
        'exit_code':proc['exit_code'],
        'timed_out':proc['timed_out'],
        'observed_mutations':observed,
        'observed_mutation_digest':sha(observed),
        'unexpected_mutations':sorted(set(unexpected)),
        'cleanup':cleanup,
        'parsed_result':parsed,
        'reported_mutations_match':not reported_mismatch,
        'stdout':proc['stdout'],
        'stderr':proc['stderr'],
        'semantic_result_digest':sha(semantic_core),
    }


def run_child(parent: dict[str, Any], *, name: str, command: str, mutation_scope: list[str] | None = None,
              authorities: list[str] | None = None, evidence_bindings: dict[str, Any] | None = None,
              evaluator: dict[str, Any] | None = None, read_only: bool = False,
              timeout: float = 30.0, expect_json: bool = False, isolation_mode: str = "delegated") -> dict[str, Any]:
    child=delegate_context(parent,name=name,mutation_scope=mutation_scope,authorities=authorities,
                           evidence_bindings=evidence_bindings,evaluator=evaluator,read_only=read_only,
                           isolation_mode=isolation_mode)
    result=execute_current(child,command,timeout=timeout,expect_json=expect_json)
    result['context']=child
    return result


def _bootstrap_command(payload: dict[str, Any]) -> str:
    import shlex
    raw=base64.b64encode(canonical(payload)).decode()
    script=r'''import base64,importlib.util,json,pathlib,sys
cfg=json.loads(base64.b64decode(sys.argv[1]).decode())
p=pathlib.Path('/opt/optiplex-lab/hierarchical_experiment.py')
s=importlib.util.spec_from_file_location('hx13_boot',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
ctx=m.create_root_context(name=cfg['name'],mutation_scope=cfg['mutation_scope'],authorities=cfg['authorities'],evidence_bindings=cfg['evidence_bindings'],evaluator=cfg.get('evaluator'),result_policy=cfg.get('result_policy','fail_closed'))
r=m.execute_current(ctx,cfg['command'],timeout=cfg['timeout'],expect_json=cfg.get('expect_json',False))
print(json.dumps({'context':ctx,'execution':r},sort_keys=True))
raise SystemExit(0 if r['ok'] else 17)
'''
    return "export PYTHONDONTWRITEBYTECODE=1; python3 -c " + shlex.quote(script) + " " + shlex.quote(raw)


def run_root_experiment(command: str, *, name: str = "root", mutation_scope: list[str] | None = None,
                        authorities: list[str] | None = None, evidence_bindings: dict[str, Any] | None = None,
                        evaluator: dict[str, Any] | None = None, timeout: float = 30.0,
                        expect_json: bool = False, result_policy: str = "fail_closed") -> dict[str, Any]:
    if os.environ.get(CAPSULE_ENV) == '1':
        raise ExperimentContextError("AMBIGUOUS_DUAL_ISOLATION_OWNER", "root experiment cannot create a second Capsule inside an active Capsule")
    payload={
        'name':name,
        'mutation_scope':mutation_scope or [],
        'authorities':authorities or [],
        'evidence_bindings':evidence_bindings or {},
        'evaluator':evaluator or {},
        'timeout':float(timeout),
        'expect_json':bool(expect_json),
        'result_policy':result_policy,
        'command':command,
    }
    cap=_capsule_module()
    result=cap.run_capsule(_bootstrap_command(payload),label='gen13-hierarchical-root')
    stdout_path=pathlib.Path(result.get('stdout',{}).get('path',''))
    parsed=None
    if stdout_path.is_file():
        try:
            parsed=json.loads(stdout_path.read_text())
        except Exception:
            parsed=None
    inv_path=pathlib.Path(result.get('run_dir',''))/'capsule-mutations.json'
    inv=json.loads(inv_path.read_text()) if inv_path.is_file() else {'records':[],'digest':None}
    root_scope=normalize_scope(mutation_scope)
    final_paths=sorted({_record_full_path(x) for x in inv.get('records') or [] if x.get('type') in {'file','symlink','special'}})
    unexpected=[p for p in final_paths if not path_allowed(p,root_scope)]
    execution=(parsed or {}).get('execution') if isinstance(parsed,dict) else None
    context=(parsed or {}).get('context') if isinstance(parsed,dict) else None
    semantic_core={
        'context_semantic_digest':(context or {}).get('semantic_digest'),
        'status':(execution or {}).get('status'),
        'semantic_execution_digest':(execution or {}).get('semantic_result_digest'),
        'final_mutation_paths':final_paths,
        'unexpected_final_mutations':unexpected,
    }
    ok=bool(result.get('accepted_state_unchanged')) and bool(execution and execution.get('ok')) and not unexpected
    return {
        'version':VERSION,
        'ok':ok,
        'status':'PASS' if ok else 'FAIL',
        'physical_isolation_owner_count':1,
        'capsule_run_id':result.get('run_id'),
        'capsule_recipe_digest':result.get('recipe_digest'),
        'context':context,
        'execution':execution,
        'final_mutation_paths':final_paths,
        'final_mutation_digest':inv.get('digest'),
        'unexpected_final_mutations':unexpected,
        'accepted_state_unchanged':bool(result.get('accepted_state_unchanged')),
        'forbidden_accepted_state_mutations':result.get('forbidden_accepted_state_mutations') or [],
        'semantic_result_digest':sha(semantic_core),
        'capsule_result':result,
    }


def selftest() -> dict[str, Any]:
    checks=[]
    def ck(name, ok, detail=None):
        checks.append({'name':name,'ok':bool(ok),'detail':detail})
    parent=normalize_scope(['/root/a/**','/opt/optiplex-lab/x.py'])
    ck('scope_subset',scope_is_subset(normalize_scope(['/root/a/b.txt']),parent))
    ck('scope_expansion_rejected',not scope_is_subset(normalize_scope(['/root/z']),parent))
    try:
        normalize_scope(['../bad']); ok=False
    except ExperimentContextError:
        ok=True
    ck('traversal_rejected',ok)
    return {'version':VERSION,'passed':sum(1 for x in checks if x['ok']),'total':len(checks),'checks':checks}


def _error_result(exc: Exception) -> dict[str, Any]:
    if isinstance(exc,ExperimentContextError):
        return {'ok':False,'fail_closed':True,'error_code':exc.code,'error':str(exc),'details':exc.details}
    return {'ok':False,'fail_closed':True,'error_code':'UNEXPECTED_HIERARCHY_FAILURE','error':f'{type(exc).__name__}: {exc}','details':None}


def main() -> int:
    ap=argparse.ArgumentParser(description='Gen13 hierarchical experiment isolation and delegation')
    ap.add_argument('--selftest',action='store_true')
    sub=ap.add_subparsers(dest='cmd')
    p=sub.add_parser('child-run')
    p.add_argument('--name',required=True)
    p.add_argument('--command',required=True)
    p.add_argument('--scope',action='append',default=[])
    p.add_argument('--authority',action='append',default=[])
    p.add_argument('--read-only',action='store_true')
    p.add_argument('--timeout',type=float,default=30.0)
    p.add_argument('--expect-json',action='store_true')
    p.add_argument('--independent-isolation',action='store_true')
    args=ap.parse_args()
    if args.selftest:
        out=selftest(); print(json.dumps(out,indent=2,sort_keys=True)); return 0 if out['passed']==out['total'] else 1
    try:
        if args.cmd=='child-run':
            parent=load_current_context()
            out=run_child(parent,name=args.name,command=args.command,mutation_scope=args.scope,
                          authorities=args.authority or None,read_only=args.read_only,timeout=args.timeout,
                          expect_json=args.expect_json,
                          isolation_mode='independent' if args.independent_isolation else 'delegated')
            print(json.dumps(out,indent=2,sort_keys=True)); return 0 if out['ok'] else 2
        ap.error('command required')
    except Exception as exc:
        print(json.dumps(_error_result(exc),indent=2,sort_keys=True)); return 2


if __name__=='__main__':
    raise SystemExit(main())
