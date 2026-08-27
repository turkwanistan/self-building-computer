from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shlex
from typing import Any

VERSION = "gen14-evaluator-mutation-nursery-r1"
SPEC_VERSION = "gen14-mutation-spec-r1"
RESULT_VERSION = "gen14-mutation-result-r1"
FROZEN_GOLD_SHA256 = "1a30b31a8f87c82428d157c20ddfd7c380289d6dae7447e01d573f2fb499483a"
GUEST_GOLD_PATH = pathlib.Path("/opt/optiplex-lab/bench/GEN14_GOLD.json")
HIERARCHY_PATH = pathlib.Path("/opt/optiplex-lab/hierarchical_experiment.py")
WORKSPACE_ROOT = pathlib.Path("/root/gen14-nursery")
SAFE_MUTATION_CLASSES = (
    "threshold_change", "assertion_delete", "assertion_invert", "fixture_substitute",
    "evidence_omit", "stale_evidence_inject", "trust_declared_state",
    "scoring_weight_change", "fail_open_change", "negative_control_corrupt",
)
ALLOWED_AUTHORITIES = {"evaluation", "evidence_read"}
FORBIDDEN_EVALUATOR_TARGETS = {
    "/opt/optiplex-lab/server.py",
    "/opt/optiplex-lab/evaluator_mutation_nursery.py",
}
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class NurseryError(RuntimeError):
    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(raw).hexdigest()


def sha_path(path: pathlib.Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise NurseryError("MODULE_LOAD_FAILED", f"unable to load module {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hierarchy_module():
    if not HIERARCHY_PATH.is_file():
        raise NurseryError("GEN13_HIERARCHY_MISSING", "Gen13 hierarchical isolation module is required")
    return _load_module(HIERARCHY_PATH, "gen14_hierarchy")


def _gold_integrity() -> dict[str, Any]:
    actual = sha_path(GUEST_GOLD_PATH)
    if actual is not None and actual != FROZEN_GOLD_SHA256:
        raise NurseryError("FROZEN_GOLD_MISMATCH", "guest frozen Gen14 gold differs from compiled acceptance identity", {"expected": FROZEN_GOLD_SHA256, "actual": actual})
    return {"expected_sha256": FROZEN_GOLD_SHA256, "guest_path": str(GUEST_GOLD_PATH), "guest_sha256": actual}


def _strict_keys(obj: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise NurseryError("SPEC_UNKNOWN_FIELD", f"unknown field(s) in {where}", unknown)


def _normalize_case(case: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(case, dict):
        raise NurseryError("CASE_INVALID", "case must be an object")
    _strict_keys(case, {"id", "args", "kwargs", "oracle", "required_internal_checks"}, "case")
    cid = str(case.get("id") or "")
    if not cid or not re.match(r"^[A-Za-z0-9_.:-]+$", cid):
        raise NurseryError("CASE_ID_INVALID", "case id must be stable and simple", cid)
    args = case.get("args") or []
    kwargs = case.get("kwargs") or {}
    oracle = case.get("oracle") or []
    req = case.get("required_internal_checks") or []
    if not isinstance(args, list) or not isinstance(kwargs, dict) or not isinstance(oracle, list) or not isinstance(req, list):
        raise NurseryError("CASE_SHAPE_INVALID", f"case {cid} has invalid args/kwargs/oracle/check shape")
    norm_oracle = []
    for i, assertion in enumerate(oracle):
        if not isinstance(assertion, dict):
            raise NurseryError("ORACLE_INVALID", f"case {cid} oracle #{i} must be object")
        _strict_keys(assertion, {"path", "op", "value"}, f"case {cid} oracle")
        op = str(assertion.get("op") or "")
        if op not in {"equals", "not_equals", "contains", "truthy", "falsy", "nonempty", "empty"}:
            raise NurseryError("ORACLE_OPERATOR_INVALID", f"case {cid} oracle operator unsupported", op)
        path = str(assertion.get("path") or "")
        if not path:
            raise NurseryError("ORACLE_PATH_INVALID", f"case {cid} oracle path required")
        rec = {"path": path, "op": op}
        if "value" in assertion:
            rec["value"] = copy.deepcopy(assertion["value"])
        norm_oracle.append(rec)
    return {"id": cid, "args": copy.deepcopy(args), "kwargs": copy.deepcopy(kwargs), "oracle": norm_oracle,
            "required_internal_checks": sorted(set(str(x) for x in req))}


def _semantic_spec(spec: dict[str, Any], *, verify_lineage: bool) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise NurseryError("SPEC_INVALID", "mutation spec must be an object")
    _strict_keys(spec, {"version", "name", "evaluator", "cases", "mutation", "authorities", "evidence_bindings", "timeout"}, "spec")
    if spec.get("version") != SPEC_VERSION:
        raise NurseryError("SPEC_VERSION_INVALID", "unsupported mutation spec version", spec.get("version"))
    name = str(spec.get("name") or "")
    if not name or len(name) > 120:
        raise NurseryError("SPEC_NAME_INVALID", "mutation spec name required and bounded")
    evaluator = spec.get("evaluator") or {}
    if not isinstance(evaluator, dict):
        raise NurseryError("EVALUATOR_INVALID", "evaluator must be object")
    _strict_keys(evaluator, {"path", "sha256", "adapter", "function"}, "evaluator")
    path_text = str(evaluator.get("path") or "")
    path = pathlib.Path(path_text)
    if not path.is_absolute() or ".." in path.parts or not path_text.startswith("/opt/optiplex-lab/") or path.suffix != ".py":
        raise NurseryError("EVALUATOR_PATH_INVALID", "evaluator must be an absolute Python source beneath /opt/optiplex-lab", path_text)
    if path_text in FORBIDDEN_EVALUATOR_TARGETS or path.name == "mcp_probe.py":
        raise NurseryError("EVALUATOR_TARGET_FORBIDDEN", "nursery cannot target operational/self-detection/recursive probe source", path_text)
    expected_sha = str(evaluator.get("sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise NurseryError("EVALUATOR_SHA_INVALID", "evaluator SHA256 required")
    actual_sha = sha_path(path)
    if verify_lineage and actual_sha != expected_sha:
        raise NurseryError("EVALUATOR_LINEAGE_MISMATCH", "evaluator source does not match pinned lineage", {"path": path_text, "expected": expected_sha, "actual": actual_sha})
    if evaluator.get("adapter") != "python_function":
        raise NurseryError("EVALUATOR_ADAPTER_INVALID", "only python_function adapter is supported in Gen14")
    function = str(evaluator.get("function") or "")
    if not _IDENTIFIER.fullmatch(function):
        raise NurseryError("EVALUATOR_FUNCTION_INVALID", "evaluator function must be a simple identifier", function)
    raw_cases = spec.get("cases") or []
    if not isinstance(raw_cases, list) or not raw_cases:
        raise NurseryError("CASES_REQUIRED", "at least one candidate case is required")
    cases = [_normalize_case(x) for x in raw_cases]
    ids = [x["id"] for x in cases]
    if len(ids) != len(set(ids)):
        raise NurseryError("CASE_ID_DUPLICATE", "candidate case ids must be unique", ids)
    mutation = spec.get("mutation") or {}
    if not isinstance(mutation, dict):
        raise NurseryError("MUTATION_INVALID", "mutation must be object")
    _strict_keys(mutation, {"class", "operator", "old", "new", "dangerous", "check_id", "check_marker", "redundancy_candidate"}, "mutation")
    mclass = str(mutation.get("class") or "")
    if mclass not in SAFE_MUTATION_CLASSES:
        raise NurseryError("MUTATION_CLASS_UNSAFE", "unsupported/unsafe evaluator mutation class", mclass)
    if mutation.get("operator") != "replace_text":
        raise NurseryError("MUTATION_OPERATOR_INVALID", "Gen14 safe operator is exact replace_text on copied evaluator source")
    old, new = mutation.get("old"), mutation.get("new")
    if not isinstance(old, str) or not old:
        raise NurseryError("MUTATION_OLD_INVALID", "exact old source text is required")
    if not isinstance(new, str):
        raise NurseryError("MUTATION_NEW_INVALID", "replacement source text must be a string")
    authorities = sorted(set(str(x) for x in (spec.get("authorities") or [])))
    if not authorities or not set(authorities).issubset(ALLOWED_AUTHORITIES):
        raise NurseryError("MUTATION_AUTHORITY_INVALID", "authorities must be a non-empty subset of evaluation/evidence_read", authorities)
    evidence = spec.get("evidence_bindings") or {}
    if not isinstance(evidence, dict):
        raise NurseryError("EVIDENCE_BINDING_INVALID", "evidence_bindings must be object")
    _strict_keys(evidence, {"gold_sha256", "case_digest", "evaluator_sha256"}, "evidence_bindings")
    case_digest = sha(cases)
    if str(evidence.get("gold_sha256") or "") != FROZEN_GOLD_SHA256:
        raise NurseryError("GOLD_BINDING_INVALID", "mutation spec must bind frozen Gen14 gold")
    if str(evidence.get("case_digest") or "") != case_digest:
        raise NurseryError("CASE_BINDING_INVALID", "mutation spec case binding digest mismatch", {"expected": case_digest, "got": evidence.get("case_digest")})
    if str(evidence.get("evaluator_sha256") or "") != expected_sha:
        raise NurseryError("EVALUATOR_BINDING_INVALID", "evidence binding must match evaluator lineage")
    timeout = float(spec.get("timeout") or 10.0)
    if not (0.05 <= timeout <= 60.0):
        raise NurseryError("TIMEOUT_INVALID", "timeout must be within 0.05..60 seconds")
    return {
        "version": SPEC_VERSION, "name": name,
        "evaluator": {"path": path_text, "sha256": expected_sha, "adapter": "python_function", "function": function},
        "cases": cases,
        "mutation": {"class": mclass, "operator": "replace_text", "old": old, "new": new,
                     "dangerous": bool(mutation.get("dangerous", True)),
                     "check_id": str(mutation.get("check_id") or "") or None,
                     "check_marker": str(mutation.get("check_marker") or "") or None,
                     "redundancy_candidate": bool(mutation.get("redundancy_candidate", False))},
        "authorities": authorities,
        "evidence_bindings": {"gold_sha256": FROZEN_GOLD_SHA256, "case_digest": case_digest, "evaluator_sha256": expected_sha},
        "timeout": timeout,
    }


def validate_spec(spec: dict[str, Any], *, verify_lineage: bool = True) -> dict[str, Any]:
    _gold_integrity()
    core = _semantic_spec(spec, verify_lineage=verify_lineage)
    mutation_id = "mu14_" + sha(core)[:24]
    return {"semantic_spec": core, "mutation_id": mutation_id, "semantic_digest": sha(core),
            "workspace": str(WORKSPACE_ROOT / mutation_id)}


def make_spec(*, name: str, evaluator_path: str, evaluator_sha256: str, function: str,
              cases: list[dict[str, Any]], mutation_class: str, old: str, new: str,
              dangerous: bool = True, check_id: str | None = None, check_marker: str | None = None,
              redundancy_candidate: bool = False, authorities: list[str] | None = None,
              timeout: float = 10.0) -> dict[str, Any]:
    normalized_cases = [_normalize_case(x) for x in cases]
    return {
        "version": SPEC_VERSION, "name": name,
        "evaluator": {"path": evaluator_path, "sha256": evaluator_sha256, "adapter": "python_function", "function": function},
        "cases": normalized_cases,
        "mutation": {"class": mutation_class, "operator": "replace_text", "old": old, "new": new,
                     "dangerous": dangerous, "check_id": check_id, "check_marker": check_marker,
                     "redundancy_candidate": redundancy_candidate},
        "authorities": authorities or ["evaluation", "evidence_read"],
        "evidence_bindings": {"gold_sha256": FROZEN_GOLD_SHA256, "case_digest": sha(normalized_cases), "evaluator_sha256": evaluator_sha256},
        "timeout": timeout,
    }


RUNNER_SOURCE = r'''import importlib.util,json,pathlib,sys,traceback

def load(path):
    s=importlib.util.spec_from_file_location("gen14_mutant_eval",path)
    if s is None or s.loader is None: raise RuntimeError("load failed")
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def resolve(value,path):
    cur=value
    for part in path.split('.'):
        if isinstance(cur,dict) and part in cur: cur=cur[part]
        elif isinstance(cur,list) and part.isdigit() and int(part)<len(cur): cur=cur[int(part)]
        else: return False,None
    return True,cur

def oracle(raw, assertions):
    details=[]
    for a in assertions:
        exists,actual=resolve(raw,a['path']); op=a['op']; exp=a.get('value'); ok=False
        if exists:
            if op=='equals': ok=actual==exp
            elif op=='not_equals': ok=actual!=exp
            elif op=='contains':
                try: ok=exp in actual
                except Exception: ok=False
            elif op=='truthy': ok=bool(actual)
            elif op=='falsy': ok=not bool(actual)
            elif op=='nonempty':
                try: ok=len(actual)>0
                except Exception: ok=False
            elif op=='empty':
                try: ok=len(actual)==0
                except Exception: ok=False
        details.append({'path':a['path'],'op':op,'expected':exp if 'value' in a else None,'exists':exists,'actual':actual,'pass':bool(ok)})
    return all(x['pass'] for x in details),details

cfg=json.loads(pathlib.Path(sys.argv[1]).read_text())
module=load(pathlib.Path(sys.argv[2])); fn=getattr(module,cfg['function'])
case_results=[]; checks_run=[]; skipped=[]; protocol=[]
for case in cfg['cases']:
    cid=case['id']
    try:
        raw=fn(*case['args'],**case['kwargs'])
        ok,details=oracle(raw,case['oracle'])
        internal=[]
        if isinstance(raw,dict):
            internal=[str(x) for x in (raw.get('checks_run') or [])]
            critical=raw.get('critical_failures') or []
            if raw.get('ok') is True and critical:
                ok=False; protocol.append({'case':cid,'code':'CRITICAL_FAILURE_HIDDEN_BY_PASS','critical_failures':critical})
        required=case.get('required_internal_checks') or []
        missing=sorted(set(required)-set(internal))
        if missing:
            ok=False; protocol.append({'case':cid,'code':'REQUIRED_INTERNAL_CHECKS_MISSING','missing':missing,'claimed':internal})
        case_results.append({'id':cid,'oracle_pass':bool(ok),'oracle_details':details,'raw_result':raw,'internal_checks_run':internal})
        checks_run.append(cid)
    except Exception as exc:
        skipped.append(cid)
        case_results.append({'id':cid,'oracle_pass':False,'error_class':type(exc).__name__,'error':str(exc),'traceback':traceback.format_exc(limit=3)})
all_ok=(not skipped and not protocol and all(x.get('oracle_pass') for x in case_results))
print(json.dumps({'version':'gen14-evaluator-envelope-r1','evaluator_digest':cfg['evaluator_digest'],'runner_digest':cfg['runner_digest'],'expected_case_ids':[x['id'] for x in cfg['cases']],'checks_run':checks_run,'skipped_checks':skipped,'case_results':case_results,'protocol_violations':protocol,'decision':'PASS' if all_ok else 'FAIL'},sort_keys=True))
'''
RUNNER_DIGEST = sha(RUNNER_SOURCE.encode())


def _runner_command(config_path: pathlib.Path, source_path: pathlib.Path) -> str:
    return "export PYTHONDONTWRITEBYTECODE=1; python3 -c " + shlex.quote(RUNNER_SOURCE) + " " + shlex.quote(str(config_path)) + " " + shlex.quote(str(source_path))


def validate_envelope(envelope: Any, *, expected_case_ids: list[str], evaluator_digest: str,
                      runner_digest: str = RUNNER_DIGEST) -> dict[str, Any]:
    errors = []
    if not isinstance(envelope, dict):
        return {"ok": False, "errors": ["ENVELOPE_NOT_OBJECT"], "derived_decision": "FAIL"}
    if envelope.get("version") != "gen14-evaluator-envelope-r1": errors.append("ENVELOPE_VERSION")
    if envelope.get("evaluator_digest") != evaluator_digest: errors.append("EVALUATOR_DIGEST_MISMATCH")
    if envelope.get("runner_digest") != runner_digest: errors.append("RUNNER_DIGEST_MISMATCH")
    expected = list(expected_case_ids)
    if envelope.get("expected_case_ids") != expected: errors.append("EXPECTED_CASE_BINDING_MISMATCH")
    if envelope.get("checks_run") != expected: errors.append("CHECKS_RUN_MISMATCH")
    if envelope.get("skipped_checks") not in ([], None): errors.append("SKIPPED_REQUIRED_CHECKS")
    rows = envelope.get("case_results")
    if not isinstance(rows, list) or [x.get("id") for x in rows if isinstance(x, dict)] != expected:
        errors.append("CASE_RESULTS_MISMATCH")
    if envelope.get("protocol_violations"): errors.append("PROTOCOL_VIOLATION")
    derived = "PASS" if isinstance(rows, list) and len(rows) == len(expected) and all(isinstance(x, dict) and x.get("oracle_pass") is True for x in rows) and not envelope.get("protocol_violations") else "FAIL"
    if envelope.get("decision") != derived: errors.append("DECLARED_DECISION_MISMATCH")
    if envelope.get("decision") not in {"PASS", "FAIL"}: errors.append("DECISION_INVALID")
    return {"ok": not errors, "errors": sorted(set(errors)), "derived_decision": derived}


def _prepare_command(core: dict[str, Any], mutation_id: str, workspace: pathlib.Path) -> str:
    payload = base64.b64encode(canonical({"spec": core, "mutation_id": mutation_id, "workspace": str(workspace), "runner_digest": RUNNER_DIGEST})).decode()
    script = r'''import base64,hashlib,json,pathlib,sys
cfg=json.loads(base64.b64decode(sys.argv[1]).decode()); spec=cfg['spec']; ws=pathlib.Path(cfg['workspace'])
ws.mkdir(parents=True,exist_ok=True); baseline=ws/'baseline.py'; mutant=ws/'mutant.py'; cases=ws/'cases.json'
src=pathlib.Path(spec['evaluator']['path']).read_text(encoding='utf-8')
old=spec['mutation']['old']; new=spec['mutation']['new']; count=src.count(old)
if count != 1: raise RuntimeError(f'MUTATION_MATCH_COUNT:{count}')
baseline.write_text(src,encoding='utf-8'); mutant.write_text(src.replace(old,new,1),encoding='utf-8')
def h(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
case_cfg={'function':spec['evaluator']['function'],'cases':spec['cases'],'runner_digest':cfg['runner_digest'],'evaluator_digest':h(baseline)}
cases.write_text(json.dumps(case_cfg,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps({'baseline_path':str(baseline),'mutant_path':str(mutant),'cases_path':str(cases),'baseline_sha256':h(baseline),'mutant_sha256':h(mutant),'case_config_sha256':h(cases),'mutation_match_count':count},sort_keys=True))
'''
    return "export PYTHONDONTWRITEBYTECODE=1; python3 -c " + shlex.quote(script) + " " + shlex.quote(payload)


def _inside(spec: dict[str, Any]) -> dict[str, Any]:
    validated = validate_spec(spec, verify_lineage=True)
    core, mutation_id = validated["semantic_spec"], validated["mutation_id"]
    workspace = pathlib.Path(validated["workspace"])
    hier = _hierarchy_module()
    parent = hier.load_current_context()
    if parent.get("mode") != "owner":
        raise NurseryError("NURSERY_PARENT_INVALID", "nursery must begin in Gen13 root owner context")
    prep = hier.run_child(parent, name="gen14-prepare-mutant", command=_prepare_command(core, mutation_id, workspace),
                          mutation_scope=[str(workspace) + "/**"], authorities=core["authorities"],
                          evaluator={"engine": VERSION, "mutation_id": mutation_id, "phase": "prepare"},
                          expect_json=True, timeout=core["timeout"])
    if not prep.get("ok") or not isinstance(prep.get("parsed_result"), dict):
        return {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "MUTANT_PREPARATION_FAILED", "preparation": prep}
    prepared = prep["parsed_result"]
    if prepared.get("baseline_sha256") != core["evaluator"]["sha256"] or prepared.get("mutation_match_count") != 1:
        return {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "EVALUATOR_LINEAGE_OR_MUTATION_AMBIGUOUS", "preparation": prep}
    case_ids = [x["id"] for x in core["cases"]]
    cases_path, baseline_path, mutant_path = pathlib.Path(prepared["cases_path"]), pathlib.Path(prepared["baseline_path"]), pathlib.Path(prepared["mutant_path"])
    baseline = hier.run_child(parent, name="gen14-baseline-evaluator", command=_runner_command(cases_path, baseline_path),
                              authorities=core["authorities"], evaluator={"engine": VERSION, "mutation_id": mutation_id, "phase": "baseline"},
                              read_only=True, expect_json=True, timeout=core["timeout"])
    baseline_env = baseline.get("parsed_result")
    baseline_validation = validate_envelope(baseline_env, expected_case_ids=case_ids, evaluator_digest=prepared["baseline_sha256"])
    if not baseline.get("ok") or not baseline_validation["ok"] or baseline_validation["derived_decision"] != "PASS":
        return {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "BASELINE_EVALUATOR_OR_ORACLE_INVALID", "baseline": baseline, "baseline_validation": baseline_validation}
    mutant_cfg = json.loads(cases_path.read_text(encoding="utf-8")); mutant_cfg["evaluator_digest"] = prepared["mutant_sha256"]
    mutant_cfg_path = workspace / "mutant-cases.json"
    cfg_payload = base64.b64encode(canonical(mutant_cfg)).decode()
    write_script = "import base64,pathlib,sys; pathlib.Path(sys.argv[1]).write_bytes(base64.b64decode(sys.argv[2]))"
    cfg_write = hier.run_child(parent, name="gen14-bind-mutant-cases",
                               command="python3 -c " + shlex.quote(write_script) + " " + shlex.quote(str(mutant_cfg_path)) + " " + shlex.quote(cfg_payload),
                               mutation_scope=[str(workspace) + "/**"], authorities=core["authorities"], timeout=core["timeout"])
    if not cfg_write.get("ok"):
        return {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "MUTANT_CASE_BIND_FAILED"}
    mutant = hier.run_child(parent, name="gen14-mutated-evaluator", command=_runner_command(mutant_cfg_path, mutant_path),
                            authorities=core["authorities"], evaluator={"engine": VERSION, "mutation_id": mutation_id, "phase": "mutant"},
                            read_only=True, expect_json=True, timeout=core["timeout"])
    mutant_env = mutant.get("parsed_result")
    mutant_validation = validate_envelope(mutant_env, expected_case_ids=case_ids, evaluator_digest=prepared["mutant_sha256"])
    marker, check_id = core["mutation"].get("check_marker"), core["mutation"].get("check_id")
    if marker and marker not in mutant_path.read_text(encoding="utf-8"):
        for row in (mutant_env or {}).get("case_results") or []:
            if check_id and check_id in (row.get("internal_checks_run") or []):
                mutant_validation = {**mutant_validation, "ok": False,
                                     "errors": sorted(set((mutant_validation.get("errors") or []) + ["CLAIMED_REMOVED_CHECK_RAN"]))}
                break
    if not mutant.get("ok") or not mutant_validation["ok"]:
        classification, kill_reason = "KILLED", "MUTANT_EXECUTION_OR_PROTOCOL_FAILURE"
    elif mutant_validation["derived_decision"] != "PASS":
        classification, kill_reason = "KILLED", "INDEPENDENT_ORACLE_MISMATCH"
    elif core["mutation"]["dangerous"]:
        classification, kill_reason = "SURVIVED_DANGEROUS", None
    else:
        classification, kill_reason = "SURVIVED_REDUNDANT_OR_EQUIVALENT", None
    semantic_core = {
        "mutation_id": mutation_id, "spec_semantic_digest": validated["semantic_digest"],
        "mutation_class": core["mutation"]["class"], "dangerous": core["mutation"]["dangerous"],
        "classification": classification, "kill_reason": kill_reason,
        "baseline_decision": baseline_validation["derived_decision"], "mutant_decision": mutant_validation["derived_decision"],
        "baseline_cases": (baseline_env or {}).get("case_results"), "mutant_cases": (mutant_env or {}).get("case_results"),
        "baseline_sha256": prepared["baseline_sha256"], "mutant_sha256": prepared["mutant_sha256"], "runner_digest": RUNNER_DIGEST,
    }
    return {
        "version": RESULT_VERSION, "ok": classification != "SURVIVED_DANGEROUS", "mutation_id": mutation_id,
        "spec_semantic_digest": validated["semantic_digest"], "mutation_class": core["mutation"]["class"],
        "dangerous": core["mutation"]["dangerous"], "check_id": check_id,
        "redundancy_candidate": core["mutation"].get("redundancy_candidate", False),
        "classification": classification, "kill_reason": kill_reason,
        "baseline_validation": baseline_validation, "mutant_validation": mutant_validation,
        "baseline_result": baseline_env, "mutant_result": mutant_env,
        "source": {"accepted_sha256": core["evaluator"]["sha256"], "baseline_sha256": prepared["baseline_sha256"], "mutant_sha256": prepared["mutant_sha256"]},
        "candidate_binding": {"case_digest": core["evidence_bindings"]["case_digest"], "case_ids": case_ids, "baseline_mutant_same_cases": True},
        "provenance": {"physical_isolation_owner": parent.get("isolation_owner"), "root_context_id": parent.get("root_context_id"),
                       "prepare_context_id": prep.get("context_id"), "baseline_context_id": baseline.get("context_id"),
                       "mutant_context_id": mutant.get("context_id"), "prepare_observed_mutations": prep.get("observed_mutations") or [],
                       "mutant_observed_mutations": mutant.get("observed_mutations") or [], "authorities": core["authorities"],
                       "workspace_scope": str(workspace) + "/**"},
        "semantic_result_digest": sha(semantic_core),
    }


def _inside_command(spec: dict[str, Any]) -> str:
    payload = base64.b64encode(canonical(spec)).decode()
    script = r'''import base64,importlib.util,json,pathlib,sys
spec=json.loads(base64.b64decode(sys.argv[1]).decode())
p=pathlib.Path('/opt/optiplex-lab/evaluator_mutation_nursery.py')
s=importlib.util.spec_from_file_location('gen14_inside',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
try: out=m._inside(spec)
except Exception as exc: out={'version':m.RESULT_VERSION,'ok':False,'classification':'INVALID_FAIL_CLOSED','failure_reason':getattr(exc,'code',type(exc).__name__),'error':str(exc),'detail':getattr(exc,'detail',None)}
print(json.dumps(out,sort_keys=True))
'''
    return "export PYTHONDONTWRITEBYTECODE=1; python3 -c " + shlex.quote(script) + " " + shlex.quote(payload)


def run_mutation(spec: dict[str, Any]) -> dict[str, Any]:
    root = None
    out: dict[str, Any]
    try:
        validated = validate_spec(spec, verify_lineage=True)
        core, mutation_id, workspace = validated["semantic_spec"], validated["mutation_id"], validated["workspace"]
        hier = _hierarchy_module()
        root = hier.run_root_experiment(
            _inside_command(spec), name="gen14-evaluator-mutation-" + mutation_id,
            mutation_scope=[workspace + "/**"], authorities=core["authorities"],
            evidence_bindings={**core["evidence_bindings"], "mutation_id": mutation_id},
            evaluator={"engine": VERSION, "evaluator_path": core["evaluator"]["path"], "evaluator_sha256": core["evaluator"]["sha256"]},
            timeout=min(60.0, core["timeout"] * 5.0 + 5.0), expect_json=True)
        inner = ((root.get("execution") or {}).get("parsed_result")) if isinstance(root, dict) else None
        if not root.get("accepted_state_unchanged") or root.get("forbidden_accepted_state_mutations"):
            out = {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "ACCEPTED_STATE_MUTATION_DETECTED", "root": root}
        elif root.get("physical_isolation_owner_count") != 1:
            out = {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "PHYSICAL_ISOLATION_OWNER_AMBIGUOUS", "root": root}
        elif not isinstance(inner, dict):
            out = {"version": RESULT_VERSION, "ok": False, "mutation_id": mutation_id, "classification": "INVALID_FAIL_CLOSED", "failure_reason": "NURSERY_RESULT_MALFORMED", "root": root}
        else:
            out = copy.deepcopy(inner)
            out["root_proof"] = {"physical_isolation_owner_count": root.get("physical_isolation_owner_count"),
                                 "accepted_state_unchanged": root.get("accepted_state_unchanged"),
                                 "forbidden_accepted_state_mutations": len(root.get("forbidden_accepted_state_mutations") or []),
                                 "unexpected_final_mutations": root.get("unexpected_final_mutations") or [],
                                 "final_mutation_paths": root.get("final_mutation_paths") or [],
                                 "root_semantic_result_digest": root.get("semantic_result_digest")}
            out["ok"] = bool(out.get("ok")) and bool(root.get("ok"))
    except NurseryError as exc:
        out = {"version": RESULT_VERSION, "ok": False, "classification": "INVALID_FAIL_CLOSED", "failure_reason": exc.code, "error": str(exc), "detail": exc.detail}
    except Exception as exc:
        out = {"version": RESULT_VERSION, "ok": False, "classification": "INVALID_FAIL_CLOSED", "failure_reason": type(exc).__name__, "error": str(exc)}
    if isinstance(root, dict) and root.get("capsule_run_id"):
        try:
            cap = _load_module(pathlib.Path("/opt/optiplex-lab/experiment_capsule.py"), "gen14_capsule_cleanup")
            out["capsule_cleanup"] = cap.cleanup(str(root["capsule_run_id"]))
        except Exception as exc:
            out["ok"] = False
            out["cleanup_failure"] = {"error_class": type(exc).__name__, "error": str(exc)}
    return out


def detection_power(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [r for r in results if r.get("classification") in {"KILLED", "SURVIVED_REDUNDANT_OR_EQUIVALENT", "SURVIVED_DANGEROUS"}]
    killed = [r for r in valid if r.get("classification") == "KILLED"]
    dangerous = [r for r in valid if r.get("dangerous")]
    dangerous_killed = [r for r in dangerous if r.get("classification") == "KILLED"]
    survivors = [r for r in valid if r.get("classification") == "SURVIVED_DANGEROUS"]
    invalid = [r for r in results if r.get("classification") == "INVALID_FAIL_CLOSED"]
    by_class: dict[str, dict[str, int]] = {}
    for r in valid:
        cls = str(r.get("mutation_class") or "unknown")
        row = by_class.setdefault(cls, {"total": 0, "killed": 0, "survived_dangerous": 0, "survived_redundant_or_equivalent": 0})
        row["total"] += 1
        if r.get("classification") == "KILLED": row["killed"] += 1
        elif r.get("classification") == "SURVIVED_DANGEROUS": row["survived_dangerous"] += 1
        else: row["survived_redundant_or_equivalent"] += 1
    unique = sorted({str(r.get("check_id")) for r in killed if r.get("check_id")})
    redundant = sorted({str(r.get("check_id") or r.get("mutation_id")) for r in valid if r.get("classification") == "SURVIVED_REDUNDANT_OR_EQUIVALENT" and r.get("redundancy_candidate")})
    semantic_view = [{k: r.get(k) for k in ("mutation_id", "mutation_class", "dangerous", "classification", "semantic_result_digest")} for r in valid]
    return {"version": "gen14-detection-power-r1", "attempted": len(results), "valid_mutants": len(valid), "killed": len(killed),
            "overall_mutation_kill_rate": round(len(killed) / len(valid), 6) if valid else 0.0,
            "dangerous_mutants": len(dangerous), "dangerous_killed": len(dangerous_killed),
            "dangerous_mutation_kill_rate": round(len(dangerous_killed) / len(dangerous), 6) if dangerous else 0.0,
            "surviving_dangerous_mutations": [{"mutation_id": r.get("mutation_id"), "class": r.get("mutation_class"), "check_id": r.get("check_id")} for r in survivors],
            "invalid_fail_closed": len(invalid), "by_class": dict(sorted(by_class.items())),
            "unique_check_contribution": unique, "redundant_or_equivalent_candidates": redundant,
            "semantic_digest": sha(semantic_view)}


def selftest() -> dict[str, Any]:
    checks = []
    def ck(name: str, ok: Any, detail: Any = None): checks.append({"name": name, "ok": bool(ok), "detail": detail})
    ck("safe_classes_10", len(SAFE_MUTATION_CLASSES) == 10 and len(set(SAFE_MUTATION_CLASSES)) == 10)
    ck("runner_digest_stable", RUNNER_DIGEST == sha(RUNNER_SOURCE.encode()))
    fake = {"version": "gen14-evaluator-envelope-r1", "evaluator_digest": "a", "runner_digest": RUNNER_DIGEST,
            "expected_case_ids": ["x"], "checks_run": [], "skipped_checks": ["x"], "case_results": [], "protocol_violations": [], "decision": "PASS"}
    v = validate_envelope(fake, expected_case_ids=["x"], evaluator_digest="a")
    ck("skipped_check_pass_rejected", not v["ok"] and "SKIPPED_REQUIRED_CHECKS" in v["errors"])
    fake2 = {"version": "gen14-evaluator-envelope-r1", "evaluator_digest": "a", "runner_digest": "forged",
             "expected_case_ids": ["x"], "checks_run": ["x"], "skipped_checks": [], "case_results": [{"id": "x", "oracle_pass": True}], "protocol_violations": [], "decision": "PASS"}
    v2 = validate_envelope(fake2, expected_case_ids=["x"], evaluator_digest="a")
    ck("runner_forgery_rejected", not v2["ok"] and "RUNNER_DIGEST_MISMATCH" in v2["errors"])
    report = detection_power([
        {"classification": "KILLED", "dangerous": True, "mutation_class": "threshold_change", "mutation_id": "a", "check_id": "threshold", "semantic_result_digest": "x"},
        {"classification": "SURVIVED_REDUNDANT_OR_EQUIVALENT", "dangerous": False, "mutation_class": "scoring_weight_change", "mutation_id": "b", "check_id": "score", "redundancy_candidate": True, "semantic_result_digest": "y"},
    ])
    ck("detection_power_metrics", report["overall_mutation_kill_rate"] == 0.5 and report["dangerous_mutation_kill_rate"] == 1.0 and report["redundant_or_equivalent_candidates"] == ["score"], report)
    return {"version": VERSION, "passed": sum(x["ok"] for x in checks), "total": len(checks), "checks": checks}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Gen14 isolated evaluator mutation nursery")
    ap.add_argument("--selftest", action="store_true"); ap.add_argument("--spec")
    args = ap.parse_args()
    if args.selftest:
        out = selftest(); print(json.dumps(out, indent=2, sort_keys=True)); return 0 if out["passed"] == out["total"] else 2
    if not args.spec: ap.error("--spec required unless --selftest")
    spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8")); out = run_mutation(spec)
    print(json.dumps(out, indent=2, sort_keys=True)); return 0 if out.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
