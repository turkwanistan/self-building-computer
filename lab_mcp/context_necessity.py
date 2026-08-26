#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import pathlib
import re
import time
from collections import defaultdict
from typing import Any

VERSION = "gen9-context-necessity-r1"
SCHEMA_VERSION = 1
HERE = pathlib.Path(__file__).resolve().parent
COMPILER_PATH = HERE / "context_compiler.py"
WORKFLOW_ROOT = pathlib.Path("/var/lib/optiplex-lab/workflows")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(data).hexdigest()


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def compiler_module():
    return load_module(COMPILER_PATH, "gen9_context_compiler")


def _text(packet: dict[str, Any]) -> str:
    return str(packet.get("task_text") or (packet.get("normalized_task") or {}).get("intent") or "")


def _kind(packet: dict[str, Any]) -> str:
    return str(packet.get("task_kind") or (packet.get("normalized_task") or {}).get("task_kind") or "")


def _records(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [copy.deepcopy(r) for r in (packet.get("selected_evidence_records") or []) if isinstance(r, dict) and r.get("evidence_id")]


def _freshness_state(rec: dict[str, Any]) -> str:
    return str((((rec.get("provenance") or {}).get("freshness") or {}).get("state") or "not_applicable"))


def _critical_safety_block(packet: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if packet.get("fail_closed"):
        reasons.append("gen8_packet_fail_closed")
    if packet.get("contradictions"):
        reasons.append("authoritative_contradiction")
    for u in packet.get("uncertainties") or []:
        if not isinstance(u, dict) or not u.get("critical"):
            continue
        state = str(((u.get("freshness") or {}).get("state") or ""))
        if state in {"stale", "missing", "changed", "contradictory"} or (not state and u.get("reason")):
            reasons.append("critical_uncertainty")
            break
    for rec in _records(packet):
        if int(rec.get("priority_tier", 9)) <= 1 and _freshness_state(rec) in {"stale", "missing", "changed", "contradictory"}:
            reasons.append(f"critical_{_freshness_state(rec)}")
            break
    return bool(reasons), sorted(set(reasons))


def _explicit_owner_ids(packet: dict[str, Any], records: list[dict[str, Any]]) -> set[str]:
    refs = {str(x).lower() for x in ((packet.get("normalized_task") or {}).get("explicit_refs") or [])}
    out: set[str] = set()
    for r in records:
        if r.get("kind") != "source":
            continue
        sf = r.get("structured_fact") or {}
        values = [r.get("evidence_id"), sf.get("identity"), (r.get("provenance") or {}).get("source_path")]
        for value in values:
            if not value:
                continue
            v = str(value).lower()
            base = pathlib.PurePosixPath(v).name
            if v in refs or base in refs:
                out.add(str(r["evidence_id"]))
    return out


def _exact_hash_or_id_requested(rec: dict[str, Any], packet: dict[str, Any]) -> bool:
    text = _text(packet).lower()
    eid = str(rec.get("evidence_id") or "").lower()
    # An explicit evidence ID locks that exact record regardless of kind. A filesystem
    # path, however, names its source owner; validation/workflow aliases that happen
    # to share the same identity must not inherit the source's explicit-owner lock.
    if eid and eid in text:
        return True
    if rec.get("kind") == "source":
        for value in ((rec.get("provenance") or {}).get("source_path"), (rec.get("structured_fact") or {}).get("identity")):
            if value and str(value).lower() in text:
                return True
    return False


def _obligation_ids(packet: dict[str, Any], records: list[dict[str, Any]]) -> tuple[set[str], list[dict[str, Any]]]:
    kind = _kind(packet)
    text = _text(packet).lower()
    owners = _explicit_owner_ids(packet, records)
    locked: set[str] = set(owners)
    obligations: list[dict[str, Any]] = []

    tier0 = {str(r["evidence_id"]) for r in records if int(r.get("priority_tier", 9)) == 0}
    locked |= tier0
    obligations.append({"name": "authority_security", "witnesses": sorted(tier0), "required": True})
    if owners:
        obligations.append({"name": "explicit_task_owner", "witnesses": sorted(owners), "required": True})

    if kind == "lifecycle_recovery":
        ids = {str(r["evidence_id"]) for r in records if r.get("kind") in {"build_state", "recovery", "service"}}
        locked |= ids
        obligations.append({"name": "lifecycle_state", "witnesses": sorted(ids), "required": True})
    elif kind == "debugging":
        ids = {str(r["evidence_id"]) for r in records if r.get("kind") in {"regression", "causal_evidence"}}
        locked |= ids
        obligations.append({"name": "failure_lineage", "witnesses": sorted(ids), "required": True})

    if "reuse" in text or "memory" in text:
        ids = {str(r["evidence_id"]) for r in records if r.get("kind") in {"procedural_memory", "capability", "evaluator"}}
        locked |= ids
        if ids:
            obligations.append({"name": "reuse_authority", "witnesses": sorted(ids), "required": True})

    explicit = {str(r["evidence_id"]) for r in records if _exact_hash_or_id_requested(r, packet)}
    locked |= explicit
    if explicit:
        obligations.append({"name": "explicit_evidence", "witnesses": sorted(explicit), "required": True})
    return locked, obligations


def _semantic_fingerprint(rec: dict[str, Any]) -> str:
    prov = rec.get("provenance") or {}
    sf = copy.deepcopy(rec.get("structured_fact") or {})
    # Source excerpts are presentation, not semantic identity.
    material = {
        "kind": rec.get("kind"),
        "authoritative": bool(rec.get("authoritative")),
        "source_path": prov.get("source_path"),
        "source_sha256": prov.get("source_sha256"),
        "structured_fact": sf,
        "relation_status": rec.get("relation_status"),
    }
    return sha(material)


def _deduplicate(records: list[dict[str, Any]], locked: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in records:
        groups[_semantic_fingerprint(r)].append(r)
    keep: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    for fp in sorted(groups):
        group = groups[fp]
        if len(group) == 1:
            keep.extend(group)
            continue
        # Never discard a locked representative. Otherwise choose strongest deterministic representative.
        group.sort(key=lambda r: (0 if str(r["evidence_id"]) in locked else 1, int(r.get("priority_tier", 9)), 0 if r.get("authoritative") else 1, str(r["evidence_id"])))
        winner = group[0]
        keep.append(winner)
        for r in group[1:]:
            if str(r["evidence_id"]) in locked:
                keep.append(r)
                continue
            removed.append({"evidence_id": r["evidence_id"], "rule": "semantic_duplicate", "dominated_by": winner["evidence_id"], "fingerprint": fp})
    keep.sort(key=lambda r: (int(r.get("priority_tier", 9)), str(r["evidence_id"])))
    return keep, removed


def _historical_scope(text: str) -> bool:
    t = text.lower()
    return any(x in t for x in ("historical", "history", "version-pinned", "version pinned", "as-of", "as of", "retained regression", "older version"))


def _target_benchmark_generation(packet: dict[str, Any]) -> int | None:
    if _kind(packet) != "evaluation":
        return None
    m = re.search(r"benchmark_gen(\d+)\.py", _text(packet), flags=re.I)
    return int(m.group(1)) if m else None


def _evaluation_generation_scope(packet: dict[str, Any], records: list[dict[str, Any]], locked: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target = _target_benchmark_generation(packet)
    text = _text(packet).lower()
    if target is None or any(x in text for x in ("all dependencies", "retained regressions", "full regression", "cross-generation")):
        return records, []
    owner_ids = _explicit_owner_ids(packet, records)
    owner_identities = set()
    for r in records:
        if str(r["evidence_id"]) in owner_ids:
            sf = r.get("structured_fact") or {}
            if sf.get("identity"): owner_identities.add(str(sf["identity"]))
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    target_token = f"gen{target}-"
    for r in records:
        eid = str(r["evidence_id"])
        if eid in locked:
            kept.append(r); continue
        if r.get("kind") == "validation":
            ident = str((r.get("structured_fact") or {}).get("identity") or "")
            if ident and ident in owner_identities:
                removed.append({"evidence_id": eid, "rule": "evaluation_owner_alias", "dominated_by": sorted(owner_ids)})
                continue
        if r.get("kind") == "source" and int(r.get("priority_tier", 9)) <= 1:
            gen = str((r.get("structured_fact") or {}).get("generation") or "").lower()
            reason = str(r.get("selection_reason") or "")
            path = r.get("dependency_path") or []
            from_owner = bool(path and str(path[0]) in owner_ids) or "dependency/impact path from selected task owner" in reason.lower()
            if from_owner and gen and target_token not in gen:
                removed.append({"evidence_id": eid, "rule": "evaluation_generation_scope", "target_generation": target, "record_generation": gen, "proof": "predecessor-generation dependency is retained execution/regression context, not primary authoritative evidence for the explicitly versioned benchmark task"})
                continue
        kept.append(r)
    return kept, removed


def _workflow_active_versions(records: list[dict[str, Any]], override: dict[str, str] | None = None) -> dict[str, str]:
    result = {str(k): str(v) for k, v in (override or {}).items()}
    names = {str((r.get("structured_fact") or {}).get("name") or "") for r in records if r.get("kind") == "workflow"}
    for name in sorted(n for n in names if n and n not in result):
        p = WORKFLOW_ROOT / name / "CURRENT"
        try:
            v = p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if v:
            result[name] = v
    return result


def _workflow_version_dominance(packet: dict[str, Any], records: list[dict[str, Any]], locked: set[str], active_override: dict[str, str] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    active = _workflow_active_versions(records, active_override)
    if _historical_scope(_text(packet)) or not active:
        return records, [], active
    kept=[]; removed=[]
    for r in records:
        if r.get("kind") != "workflow" or str(r["evidence_id"]) in locked:
            kept.append(r); continue
        sf=r.get("structured_fact") or {}; name=str(sf.get("name") or ""); version=str((sf.get("metadata") or {}).get("version") or "")
        if name in active and version and version != active[name]:
            removed.append({"evidence_id":r["evidence_id"],"rule":"active_workflow_version_dominance","workflow":name,"record_version":version,"active_version":active[name]})
        else:
            kept.append(r)
    return kept, removed, active


LIFECYCLE_ATOMS = {
    "recovery_lkg": ("recovery", "rollback", "last-known-good", "last_known_good", "lkg"),
    "restart_service": ("restart", "service"),
    "build_identity": ("build", "build.json", "source_sha256", "last_known_good_sha256", "build metadata"),
}


def _lifecycle_requested_atoms(text: str) -> list[str]:
    t=text.lower(); out=[]
    for name,terms in LIFECYCLE_ATOMS.items():
        if any(term in t for term in terms): out.append(name)
    return out or ["recovery_lkg"]


def _validation_source_score(rec: dict[str, Any], requested_atoms: list[str]) -> dict[str, Any] | None:
    sf=rec.get("structured_fact") or {}; raw=sf.get("identity") or (sf.get("metadata") or {}).get("command")
    if not raw: return None
    path=pathlib.Path(str(raw).split()[0])
    try: content=path.read_text(encoding="utf-8",errors="replace").lower()
    except OSError: return None
    covered=[]; hits=0
    for atom in requested_atoms:
        terms=LIFECYCLE_ATOMS[atom]
        atom_hits=sum(content.count(term) for term in terms)
        if atom_hits: covered.append(atom); hits += atom_hits
    return {"source_path":str(path),"covered_atoms":covered,"coverage":len(covered),"hits":hits,"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}


def _lifecycle_minimize(packet: dict[str, Any], records: list[dict[str, Any]], locked: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if _kind(packet) != "lifecycle_recovery":
        return records, [], []
    text=_text(packet).lower()
    workflow_in_scope=any(x in text for x in ("workflow", "transaction", "promotion", "promote", "accept-current", "accept current"))
    owner_ids=_explicit_owner_ids(packet,records)
    removed=[]; temp=[]
    for r in records:
        eid=str(r["evidence_id"])
        if eid in locked:
            temp.append(r); continue
        if not workflow_in_scope and r.get("kind") in {"workflow","workflow_graph"}:
            removed.append({"evidence_id":eid,"rule":"reverse_consumer_not_task_evidence","proof":"workflow/transaction consumers are outside the lifecycle state/validation question and no workflow intent is present"})
            continue
        temp.append(r)

    candidates=[]
    for r in temp:
        if r.get("kind") != "validation" or int(r.get("priority_tier",9)) > 1:
            continue
        if str(r["evidence_id"]) in locked:
            continue
        reason=str(r.get("selection_reason") or "")
        path=r.get("dependency_path") or []
        broad=("bounded change-impact" in reason.lower()) and bool(path) and (not owner_ids or str(path[0]) in owner_ids)
        if broad: candidates.append(r)
    requested=_lifecycle_requested_atoms(_text(packet)); scored=[]
    for r in candidates:
        s=_validation_source_score(r,requested)
        if s: scored.append((r,s))
    witness=[]
    if len(candidates) > 1 and scored:
        full=[(r,s) for r,s in scored if s["coverage"] == len(requested)]
        ranked=sorted(full,key=lambda rs:(-rs[1]["coverage"],-rs[1]["hits"],str(rs[0]["evidence_id"])))
        if ranked:
            best=ranked[0]
            # Require a unique evidence score; ties fail conservative and keep all.
            unique=len(ranked)==1 or (best[1]["coverage"],best[1]["hits"]) != (ranked[1][1]["coverage"],ranked[1][1]["hits"])
            if unique:
                keep_id=str(best[0]["evidence_id"]); witness=[{"evidence_id":keep_id,**best[1],"requested_atoms":requested}]
                out=[]
                for r in temp:
                    eid=str(r["evidence_id"])
                    if r in candidates and eid != keep_id:
                        score=next((s for rr,s in scored if rr is r),None)
                        removed.append({"evidence_id":eid,"rule":"lifecycle_validation_witness_dominance","dominated_by":keep_id,"candidate_score":score,"winner_score":best[1],"requested_atoms":requested})
                    else: out.append(r)
                temp=out
    return temp, removed, witness


def _tier2_obligation(packet: dict[str, Any], rec: dict[str, Any]) -> bool:
    text=_text(packet).lower(); kind=str(rec.get("kind") or "")
    if _exact_hash_or_id_requested(rec,packet): return True
    if kind=="causal_evidence" and any(x in text for x in ("historical", "history", "causal", "failure", "trace", "why did")): return True
    if kind=="regression" and "regression" in text: return True
    if kind=="generation" and any(x in text for x in ("generation", "lineage", "historical", "history")): return True
    if kind=="registry" and "registry" in text: return True
    if kind in {"procedural_memory","capability","evaluator"} and any(x in text for x in ("memory", "reuse", "capability", "evaluator")): return True
    if kind in {"workflow","workflow_graph"} and any(x in text for x in ("workflow", "transaction", "graph")): return True
    if kind in {"artifact","benchmark_artifact","evidence_artifact"} and any(x in text for x in ("artifact", "evidence file", "provenance file")): return True
    return False


def _drop_unobligated_tier2(packet: dict[str, Any], records: list[dict[str, Any]], locked: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept=[]; removed=[]
    for r in records:
        eid=str(r["evidence_id"])
        if eid in locked or int(r.get("priority_tier",9)) <= 1 or _tier2_obligation(packet,r):
            kept.append(r)
        else:
            removed.append({"evidence_id":eid,"rule":"unobligated_budget_prunable_evidence","priority_tier":r.get("priority_tier"),"proof":"Gen8 marks Tier 2/3 budget-prunable and this record carries no explicit task or safety obligation"})
    return kept, removed


def _enrich(packet: dict[str, Any], selected: list[dict[str, Any]]) -> None:
    packet["selected_evidence_records"]=selected
    packet["memories"]=[r["evidence_id"] for r in selected if r.get("kind")=="procedural_memory"]
    packet["causal_evidence"]=[r["evidence_id"] for r in selected if r.get("kind")=="causal_evidence"]
    packet["regressions"]=[r["evidence_id"] for r in selected if r.get("kind")=="regression"]
    packet["validations"]=[r["evidence_id"] for r in selected if r.get("kind") in {"validation","evaluator","benchmark_artifact"}]
    packet["recovery_requirements"]=[r["evidence_id"] for r in selected if r.get("kind") in {"recovery","build_state","service"}]
    packet["authority_security_requirements"]=[r["evidence_id"] for r in selected if int(r.get("priority_tier",9))==0 and r.get("kind") in {"authority_security","operational_identity","contradiction_warning"}]


def context_projection(packet: dict[str, Any]) -> dict[str, Any]:
    """Return only context-bearing fields; necessity audit metadata is deliberately out-of-band."""
    keys=("schema_version","compiler_version","optimizer_version","task_text","task_hash","normalized_task","task_kind","generation_build_twin_identity","input_evidence_digests","selected_evidence_records","memories","causal_evidence","regressions","validations","recovery_requirements","authority_security_requirements","contradictions","uncertainties","controlled_broad_fallback","fail_closed")
    return {k:packet.get(k) for k in keys if k in packet}


def minimize_packet(packet: dict[str, Any], *, active_versions: dict[str, str] | None=None) -> dict[str, Any]:
    baseline=copy.deepcopy(packet)
    records=_records(baseline)
    blocked,block_reasons=_critical_safety_block(baseline)
    locked,obligations=_obligation_ids(baseline,records)
    removed: list[dict[str, Any]]=[]
    witness_proofs: list[dict[str, Any]]=[]
    active: dict[str,str]={}

    if blocked:
        selected=records
    else:
        selected,rem=_deduplicate(records,locked); removed.extend(rem)
        selected,rem=_evaluation_generation_scope(baseline,selected,locked); removed.extend(rem)
        selected,rem,active=_workflow_version_dominance(baseline,selected,locked,active_versions); removed.extend(rem)
        selected,rem,wit=_lifecycle_minimize(baseline,selected,locked); removed.extend(rem); witness_proofs.extend(wit)
        selected,rem=_drop_unobligated_tier2(baseline,selected,locked); removed.extend(rem)

    selected=sorted(selected,key=lambda r:(int(r.get("priority_tier",9)),str(r["evidence_id"])))
    out=copy.deepcopy(baseline)
    compiler_packet_digest=str(baseline.get("packet_digest") or sha(context_projection(baseline)))
    out["compiler_packet_digest"]=compiler_packet_digest
    out["optimizer_version"]=VERSION
    _enrich(out,selected)
    out["necessity_proof"]={
        "version":VERSION,
        "baseline_packet_digest":compiler_packet_digest,
        "minimization_blocked":blocked,
        "block_reasons":block_reasons,
        "obligations":obligations,
        "locked_evidence_ids":sorted(locked),
        "active_workflow_versions":dict(sorted(active.items())),
        "witness_proofs":witness_proofs,
        "removed":sorted(removed,key=lambda x:(str(x.get("rule")),str(x.get("evidence_id")))),
        "retained_evidence_ids":[str(r["evidence_id"]) for r in selected],
    }
    # The downstream context size excludes the proof audit by design; audit remains attached for inspection.
    baseline_context_bytes=len(canonical(context_projection(baseline)))
    minimized_context_bytes=len(canonical(context_projection(out)))
    old_budget=copy.deepcopy(baseline.get("budget") or {})
    out["budget"]={**old_budget,
        "compiler_reported_bytes_used":old_budget.get("bytes_used"),
        "baseline_context_payload_bytes":baseline_context_bytes,
        "bytes_used":minimized_context_bytes,
        "context_payload_bytes":minimized_context_bytes,
        "context_payload_reduction":round((baseline_context_bytes-minimized_context_bytes)/baseline_context_bytes,6) if baseline_context_bytes else 0.0,
        "token_estimate":(minimized_context_bytes+3)//4,
    }
    digest_material={"optimizer":VERSION,"compiler_packet_digest":compiler_packet_digest,"context":context_projection(out),"proof":out["necessity_proof"]}
    out["packet_id"]="ctx9_"+sha(digest_material)[:20]
    out["packet_digest"]=sha(digest_material)
    out["optimizer_digest"]=out["packet_digest"]
    return out


def compile_minimized(task: str, *, budget_bytes: int=24000, allow_expand: bool=True, snapshot_override: dict[str,Any] | None=None, active_versions: dict[str,str] | None=None) -> dict[str, Any]:
    cc=compiler_module()
    packet=cc.build_packet(task,budget_bytes=budget_bytes,allow_expand=allow_expand,snapshot_override=snapshot_override)
    return minimize_packet(packet,active_versions=active_versions)


def selftest() -> dict[str, Any]:
    checks=[]
    def ck(name: str, ok: bool, detail: Any=None): checks.append({"name":name,"ok":bool(ok),"detail":detail})
    base={
        "schema_version":1,"compiler_version":"synthetic","task_text":"Explain source /opt/x.py.","task_kind":"explanation_architecture","normalized_task":{"task_kind":"explanation_architecture","intent":"Explain source /opt/x.py.","explicit_refs":["/opt/x.py"]},"fail_closed":False,"contradictions":[],"uncertainties":[],"selected_evidence_records":[
            {"evidence_id":"authority:test","kind":"authority_security","priority_tier":0,"required":True,"authoritative":True,"provenance":{"freshness":{"state":"policy_seed"}},"structured_fact":{"rule":"safe"}},
            {"evidence_id":"source:/opt/x.py","kind":"source","priority_tier":1,"required":True,"authoritative":True,"provenance":{"source_path":"/opt/x.py","source_sha256":"a","freshness":{"state":"fresh"}},"structured_fact":{"identity":"/opt/x.py","generation":"gen9-test"}},
            {"evidence_id":"generation:test","kind":"generation","priority_tier":2,"required":False,"authoritative":False,"provenance":{"freshness":{"state":"not_applicable"}},"structured_fact":{"identity":"gen9-test"}},
        ],"budget":{}
    }
    a=minimize_packet(base); b=minimize_packet(base)
    ids={r["evidence_id"] for r in a["selected_evidence_records"]}
    ck("tier0_and_owner_locked",{"authority:test","source:/opt/x.py"}.issubset(ids),sorted(ids))
    ck("unobligated_tier2_removed","generation:test" not in ids,a["necessity_proof"]["removed"])
    ck("deterministic_digest",a["packet_digest"]==b["packet_digest"],a["packet_digest"])

    stale=copy.deepcopy(base); stale["fail_closed"]=True; stale["uncertainties"]=[{"critical":True,"freshness":{"state":"missing"}}]
    s=minimize_packet(stale)
    ck("fail_closed_blocks_minimization",s["necessity_proof"]["minimization_blocked"] and len(s["selected_evidence_records"])==len(stale["selected_evidence_records"]),s["necessity_proof"]["block_reasons"])

    dup=copy.deepcopy(base); clone=copy.deepcopy(dup["selected_evidence_records"][2]); clone["evidence_id"]="generation:test-duplicate"; dup["selected_evidence_records"].append(clone)
    d=minimize_packet(dup)
    ck("semantic_duplicate_collapsed",sum(1 for x in d["necessity_proof"]["removed"] if x["rule"]=="semantic_duplicate")==1,d["necessity_proof"]["removed"])

    eval_alias={"schema_version":1,"compiler_version":"synthetic","task_text":"Evaluate /opt/bench/benchmark_gen7.py and identify its authoritative evaluation evidence.","task_kind":"evaluation","normalized_task":{"task_kind":"evaluation","intent":"Evaluate /opt/bench/benchmark_gen7.py and identify its authoritative evaluation evidence.","explicit_refs":["/opt/bench/benchmark_gen7.py"]},"fail_closed":False,"contradictions":[],"uncertainties":[],"selected_evidence_records":[
      {"evidence_id":"authority:test","kind":"authority_security","priority_tier":0,"required":True,"authoritative":True,"provenance":{"freshness":{"state":"policy_seed"}},"structured_fact":{"rule":"safe"}},
      {"evidence_id":"source:/opt/bench/benchmark_gen7.py","kind":"source","priority_tier":1,"required":True,"authoritative":True,"provenance":{"source_path":"/opt/bench/benchmark_gen7.py","source_sha256":"a","freshness":{"state":"fresh"}},"structured_fact":{"identity":"/opt/bench/benchmark_gen7.py","generation":"gen7-test"}},
      {"evidence_id":"validation:benchmark:benchmark_gen7","kind":"validation","priority_tier":1,"required":True,"authoritative":True,"provenance":{"source_path":"/opt/bench/benchmark_gen7.py","source_sha256":"a","freshness":{"state":"fresh"}},"structured_fact":{"identity":"/opt/bench/benchmark_gen7.py","generation":"gen7-test"}}],"budget":{}}
    ea=minimize_packet(eval_alias); eaids={r["evidence_id"] for r in ea["selected_evidence_records"]}
    ck("evaluation_source_path_does_not_lock_validation_alias","source:/opt/bench/benchmark_gen7.py" in eaids and "validation:benchmark:benchmark_gen7" not in eaids,sorted(eaids))

    wf={"schema_version":1,"compiler_version":"synthetic","task_text":"Explain the current deploy workflow transaction.","task_kind":"explanation_architecture","normalized_task":{"task_kind":"explanation_architecture","intent":"Explain the current deploy workflow transaction.","explicit_refs":[]},"fail_closed":False,"contradictions":[],"uncertainties":[],"selected_evidence_records":[
      {"evidence_id":"authority:test","kind":"authority_security","priority_tier":0,"required":True,"authoritative":True,"provenance":{"freshness":{"state":"policy_seed"}},"structured_fact":{"rule":"safe"}},
      {"evidence_id":"workflow:deploy@1","kind":"workflow","priority_tier":1,"required":False,"authoritative":True,"provenance":{"freshness":{"state":"fresh"}},"structured_fact":{"name":"deploy","metadata":{"version":"1"}}},
      {"evidence_id":"workflow:deploy@2","kind":"workflow","priority_tier":1,"required":False,"authoritative":True,"provenance":{"freshness":{"state":"fresh"}},"structured_fact":{"name":"deploy","metadata":{"version":"2"}}}],"budget":{}}
    w=minimize_packet(wf,active_versions={"deploy":"2"}); wids={r["evidence_id"] for r in w["selected_evidence_records"]}
    ck("active_workflow_version_dominance",wids=={"authority:test","workflow:deploy@2"},sorted(wids))
    hist=copy.deepcopy(wf); hist["task_text"]="Explain historical deploy workflow versions."; hist["normalized_task"]["intent"]=hist["task_text"]
    h=minimize_packet(hist,active_versions={"deploy":"2"}); hids={r["evidence_id"] for r in h["selected_evidence_records"]}
    ck("historical_disables_version_collapse",{"workflow:deploy@1","workflow:deploy@2"}.issubset(hids),sorted(hids))
    return {"version":VERSION,"passed":sum(1 for x in checks if x["ok"]),"total":len(checks),"checks":checks}


def main() -> None:
    ap=argparse.ArgumentParser(description="Gen9 deterministic proof-carrying Context Necessity Optimizer")
    ap.add_argument("--selftest",action="store_true")
    sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("minimize"); p.add_argument("task"); p.add_argument("--budget-bytes",type=int,default=24000); p.add_argument("--out")
    p=sub.add_parser("packet"); p.add_argument("path"); p.add_argument("--out")
    args=ap.parse_args()
    if args.selftest:
        out=selftest(); print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if out["passed"]==out["total"] else 1)
    started=time.monotonic()
    if args.cmd=="minimize": out=compile_minimized(args.task,budget_bytes=max(1024,args.budget_bytes))
    elif args.cmd=="packet": out=minimize_packet(json.loads(pathlib.Path(args.path).read_text()))
    else: ap.error("minimize or packet command required")
    latency=round((time.monotonic()-started)*1000,3)
    target=getattr(args,"out",None)
    if target: pathlib.Path(target).write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"packet":out,"minimize_total_latency_ms":latency},indent=2,sort_keys=True))
    raise SystemExit(2 if out.get("fail_closed") else 0)


if __name__=="__main__": main()
