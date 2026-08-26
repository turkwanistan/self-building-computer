#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import tempfile
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

VERSION = "gen6-procedural-memory-r1"
SCHEMA_VERSION = "procedural-memory-v1"
ROOT = pathlib.Path(os.environ.get("OPTIPLEX_MEMORY_ROOT", "/var/lib/optiplex-lab/memory"))
OBJECTS = ROOT / "objects"
REGISTRY = ROOT / "registry.json"
EPISODES = ROOT / "episodes.jsonl"
PROVENANCE = ROOT / "provenance.jsonl"
FORGE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_FORGE_ROOT", "/var/lib/optiplex-lab/capabilities"))
FORGE_REGISTRY = FORGE_ROOT / "registry.json"
FORGE_PROVENANCE = FORGE_ROOT / "provenance.jsonl"
FORGE_RUN_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_FORGE_RUN_ROOT", "/var/lib/optiplex-lab/capability-runs"))
ACTIVE_STATES = {"ACTIVE"}
LIFECYCLE = {"CANDIDATE", "ACTIVE", "SUPERSEDED", "RETIRED"}
STOPWORDS = {"the","and","for","with","from","into","that","this","using","use","one","while","without","return","typed","json","task"}
SENSITIVE_KEYS = {"password","passwd","token","api_key","apikey","authorization","private_key","secret","credential","credentials"}
SENSITIVE_MARKERS = ("-----begin private key-----","authorization: bearer","github_pat_","ghp_")


class MemoryError(RuntimeError):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_json(value: Any) -> str:
    return sha_bytes(canonical_bytes(value))


def safe_write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def append_jsonl(path: pathlib.Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _reject_sensitive(node: Any, trail: str = "$") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if str(k).lower().replace("-", "_") in SENSITIVE_KEYS:
                raise MemoryError(f"sensitive key rejected at {trail}.{k}")
            _reject_sensitive(v, f"{trail}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _reject_sensitive(v, f"{trail}[{i}]")
    elif isinstance(node, str):
        low = node.lower()
        if any(x in low for x in SENSITIVE_MARKERS):
            raise MemoryError(f"sensitive marker rejected at {trail}")


def init_root() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    OBJECTS.mkdir(parents=True, exist_ok=True)
    if not REGISTRY.exists():
        safe_write_json(REGISTRY, {"version": VERSION, "memories": {}})


def load_registry() -> dict[str, Any]:
    init_root()
    try:
        value = json.loads(REGISTRY.read_text())
    except Exception as exc:
        raise MemoryError(f"memory registry unreadable: {exc}")
    if not isinstance(value, dict) or not isinstance(value.get("memories"), dict):
        raise MemoryError("memory registry malformed")
    return value


def save_registry(reg: dict[str, Any]) -> None:
    reg["version"] = VERSION
    safe_write_json(REGISTRY, reg)


def load_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        try:
            v = json.loads(line)
            if isinstance(v, dict): out.append(v)
        except Exception:
            continue
    return out


def _stem_token(x: str) -> str:
    # Small inspectable morphology normalizer; intentionally not an opaque embedding model.
    if len(x) > 5 and x.endswith("ing"):
        x=x[:-3]
        if len(x)>=2 and x[-1]==x[-2]: x=x[:-1]
        if x.endswith("iz"): x += "e"
    elif len(x) > 4 and x.endswith("ies"):
        x=x[:-3]+"y"
    elif len(x) > 4 and x.endswith("ed"):
        x=x[:-2]
    elif len(x) > 3 and x.endswith("s") and not x.endswith("ss"):
        x=x[:-1]
    return x

def tokens(text: str) -> set[str]:
    return {_stem_token(x) for x in re.findall(r"[a-z0-9]+", text.lower()) if len(x) > 2 and x not in STOPWORDS}


def _type_name(v: Any) -> str:
    if v is None: return "null"
    if isinstance(v, bool): return "boolean"
    if isinstance(v, int) and not isinstance(v, bool): return "integer"
    if isinstance(v, float): return "number"
    if isinstance(v, str): return "string"
    if isinstance(v, list): return "array"
    if isinstance(v, dict): return "object"
    return type(v).__name__


def normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(task, dict): raise MemoryError("task must be object")
    intent = str(task.get("intent") or task.get("purpose") or "").strip()
    if not intent: raise MemoryError("task requires intent")
    tags = sorted({str(x).lower().strip() for x in task.get("tags", []) if isinstance(x, str) and x.strip()})
    environment = task.get("environment") or {}
    if not isinstance(environment, dict): raise MemoryError("environment must be object")
    input_value = task.get("input") if "input" in task else None
    input_keys = sorted(input_value.keys()) if isinstance(input_value, dict) else []
    out = {
        "intent": intent,
        "intent_tokens": sorted(tokens(intent)),
        "task_kind": str(task.get("task_kind") or "").strip() or None,
        "tags": tags,
        "environment": environment,
        "input_keys": input_keys,
        "parameter_names": sorted((task.get("parameters") or {}).keys()) if isinstance(task.get("parameters") or {}, dict) else [],
    }
    _reject_sensitive(out)
    return out


def procedure_fingerprint(procedure: dict[str, Any]) -> str:
    refs = {
        "capability_hash": procedure.get("capability_hash"),
        "workflow_ref": procedure.get("workflow_ref"),
        "workflow_hash": procedure.get("workflow_hash"),
        "graph_ref": procedure.get("graph_ref"),
        "graph_hash": procedure.get("graph_hash"),
    }
    refs = {k:v for k,v in refs.items() if v}
    if not refs: raise MemoryError("procedure needs a capability/workflow/graph reference")
    return sha_json(refs)


def record_episode(task: dict[str, Any], procedure: dict[str, Any], success: bool, *, evidence: dict[str, Any] | None = None, source: str = "observed") -> dict[str, Any]:
    init_root()
    norm = normalize_task(task)
    if not isinstance(procedure, dict): raise MemoryError("procedure must be object")
    _reject_sensitive(procedure)
    evidence = evidence or {}
    _reject_sensitive(evidence)
    now = utc()
    core = {
        "schema_version": "procedural-episode-v1",
        "observed_at": now,
        "nonce": uuid.uuid4().hex,
        "task": norm,
        "procedure": procedure,
        "procedure_fingerprint": procedure_fingerprint(procedure),
        "success": bool(success),
        "evidence": evidence,
        "source": source,
    }
    episode_hash = sha_json(core)
    rec = {**core, "episode_id": f"ep_{episode_hash[:20]}", "episode_hash": episode_hash}
    append_jsonl(EPISODES, rec)
    append_jsonl(PROVENANCE, {"timestamp": now, "event":"episode_recorded", "episode_id":rec["episode_id"], "episode_hash":episode_hash, "success":bool(success), "procedure_fingerprint":rec["procedure_fingerprint"], "source":source})
    return rec


def _forge_registry() -> dict[str, Any]:
    try: value=json.loads(FORGE_REGISTRY.read_text())
    except Exception as exc: raise MemoryError(f"Forge registry unavailable: {exc}")
    caps=value.get("capabilities") or {}
    if not isinstance(caps, dict): raise MemoryError("Forge registry malformed")
    return caps


def import_forge_episodes(content_hash: str) -> dict[str, Any]:
    """Import actual Forge real-task outcomes as sanitized procedural episodes.

    Inputs/results are referenced by run/artifact hashes; task bodies are not copied into memory.
    """
    caps=_forge_registry()
    rec=caps.get(content_hash)
    if not isinstance(rec, dict): raise MemoryError(f"capability not found: {content_hash}")
    events=[e for e in load_jsonl(FORGE_PROVENANCE) if e.get("event")=="real_task_evidence" and e.get("content_hash")==content_hash]
    existing={(e.get("evidence") or {}).get("forge_event_hash") for e in load_jsonl(EPISODES)}
    contract_path=pathlib.Path(str(rec.get("object") or ""))/"capability.json"
    contract=json.loads(contract_path.read_text()) if contract_path.exists() else {}
    required_keys=sorted((contract.get("input_schema") or {}).get("required") or [])
    imported=[]
    skipped=0
    for event in events:
        event_hash=sha_json(event)
        if event_hash in existing:
            skipped += 1; continue
        run_id=event.get("run_id")
        input_keys=[]
        run_artifact_hash=None
        if run_id:
            inp=FORGE_RUN_ROOT/str(run_id)/"input.json"
            res=FORGE_RUN_ROOT/str(run_id)/"result.json"
            if inp.exists():
                try:
                    val=json.loads(inp.read_text()); input_keys=sorted(val.keys()) if isinstance(val,dict) else []
                except Exception: pass
            pieces=[]
            for p in (inp,res):
                if p.exists(): pieces.append({"name":p.name,"sha256":sha_bytes(p.read_bytes()),"bytes":p.stat().st_size})
            if pieces: run_artifact_hash=sha_json(pieces)
        # We intentionally index semantic metadata and immutable evidence, not the raw task body.
        task={
            "intent": str(rec.get("purpose") or rec.get("name") or "capability task"),
            "task_kind": f"capability:{rec.get('name')}",
            "tags": list(rec.get("applicability") or []),
            "environment": {"runtime":"mcp-lab","input_schema_hash":sha_json(contract.get("input_schema") or {})},
            "input": {k:None for k in input_keys},
            "parameters": {k:None for k in required_keys},
        }
        procedure={"capability_hash":content_hash,"capability_name":rec.get("name"),"evaluator_hash":rec.get("evaluator_hash")}
        evidence={"forge_event_hash":event_hash,"run_id":run_id,"run_artifact_hash":run_artifact_hash,"evaluator_hash":rec.get("evaluator_hash"),"capability_source_hashes":rec.get("source_hashes")}
        imported.append(record_episode(task,procedure,bool(event.get("ok")),evidence=evidence,source="forge-provenance"))
    return {"content_hash":content_hash,"imported":len(imported),"skipped_existing":skipped,"episodes":[x["episode_id"] for x in imported]}


def _intersection_sets(values: list[set[str]]) -> set[str]:
    if not values: return set()
    out=set(values[0])
    for v in values[1:]: out &= set(v)
    return out


def _common_environment(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    if not episodes: return {}
    envs=[(e.get("task") or {}).get("environment") or {} for e in episodes]
    keys=set(envs[0])
    for env in envs[1:]: keys &= set(env)
    return {k:envs[0][k] for k in sorted(keys) if all(env.get(k)==envs[0][k] for env in envs)}


def _intent_centroid(episodes: list[dict[str, Any]]) -> list[str]:
    if not episodes: return []
    counts=Counter()
    for e in episodes: counts.update(set((e.get("task") or {}).get("intent_tokens") or []))
    threshold=max(1, (len(episodes)+1)//2)
    return sorted(k for k,v in counts.items() if v>=threshold)


def _parameter_hints(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    names=[set((e.get("task") or {}).get("parameter_names") or []) for e in episodes]
    union=set().union(*names) if names else set()
    required=_intersection_sets(names)
    return {"names":sorted(union),"required":sorted(required)}


def _applicability(memory: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    norm=normalize_task(task)
    reasons=[]; mismatches=[]
    mk=memory.get("task_kind")
    if mk and norm.get("task_kind") and mk != norm.get("task_kind"):
        mismatches.append(f"task_kind:{norm.get('task_kind')}!={mk}")
    required_tags=set(memory.get("required_tags") or [])
    tags=set(norm.get("tags") or [])
    missing_tags=sorted(required_tags-tags)
    if missing_tags: mismatches.append(f"missing_tags:{missing_tags}")
    for k,v in (memory.get("preconditions") or {}).items():
        actual=(norm.get("environment") or {}).get(k,"__MISSING__")
        if actual != v: mismatches.append(f"environment:{k}={actual!r}!={v!r}")
    required_input=set(memory.get("required_input_keys") or [])
    missing_input=sorted(required_input-set(norm.get("input_keys") or []))
    if missing_input: mismatches.append(f"missing_input_keys:{missing_input}")
    contraindicated=set(memory.get("contraindication_tags") or []) & tags
    if contraindicated: mismatches.append(f"contraindication_tags:{sorted(contraindicated)}")
    mt=set(memory.get("intent_tokens") or []); tt=set(norm.get("intent_tokens") or [])
    union=mt|tt; intent_overlap=len(mt&tt)/len(union) if union else 0.0
    tag_union=required_tags|tags; tag_overlap=len(required_tags&tags)/len(tag_union) if tag_union else 0.0
    kind_bonus=0.15 if mk and mk==norm.get("task_kind") else 0.0
    score=min(1.0, 0.7*intent_overlap + 0.15*tag_overlap + kind_bonus)
    if intent_overlap>=0.35: reasons.append(f"intent_overlap={intent_overlap:.3f}")
    if tag_overlap>0: reasons.append(f"tag_overlap={tag_overlap:.3f}")
    if kind_bonus: reasons.append("task_kind_match")
    eligible=not mismatches and score>=0.35
    return {"eligible":eligible,"score":round(score,4),"reasons":reasons,"mismatches":mismatches,"intent_overlap":round(intent_overlap,4),"tag_overlap":round(tag_overlap,4),"normalized_task":norm}


def distill(procedure_ref: str, *, supersede_existing: bool = False) -> dict[str, Any]:
    init_root()
    eps=load_jsonl(EPISODES)
    successes=[e for e in eps if e.get("success") and (e.get("procedure") or {}).get("capability_hash")==procedure_ref]
    failures=[e for e in eps if not e.get("success") and (e.get("procedure") or {}).get("capability_hash")==procedure_ref]
    if len(successes)<2:
        return {"ok":False,"decision":"REJECT_INSUFFICIENT_SUCCESS","successes":len(successes),"failures":len(failures)}
    successes=sorted(successes,key=lambda e:str(e.get("observed_at")))
    train=successes[:-1] if len(successes)>=3 else successes
    heldout=successes[-1:] if len(successes)>=3 else []
    tags=_intersection_sets([set((e.get("task") or {}).get("tags") or []) for e in train])
    kinds={((e.get("task") or {}).get("task_kind")) for e in train}
    task_kind=next(iter(kinds)) if len(kinds)==1 else None
    input_required=_intersection_sets([set((e.get("task") or {}).get("input_keys") or []) for e in train])
    evidence=[]
    for e in successes+failures:
        ev=e.get("evidence") or {}
        evidence.append({k:ev.get(k) for k in ("forge_event_hash","run_id","run_artifact_hash","evaluator_hash") if ev.get(k)})
    failure_tags=set()
    for e in failures:
        failure_tags |= set((e.get("task") or {}).get("tags") or []) - tags
    procedure=dict(successes[-1].get("procedure") or {})
    memory={
        "schema_version":SCHEMA_VERSION,
        "distiller_version":VERSION,
        "semantic_intent":str((successes[-1].get("task") or {}).get("intent") or ""),
        "intent_tokens":_intent_centroid(train),
        "task_kind":task_kind,
        "required_tags":sorted(tags),
        "preconditions":_common_environment(train),
        "required_input_keys":sorted(input_required),
        "procedure":procedure,
        "parameter_hints":_parameter_hints(train),
        "source_episode_ids":[e.get("episode_id") for e in successes+failures],
        "source_episode_hashes":[e.get("episode_hash") for e in successes+failures],
        "evidence":evidence,
        "success_count":len(successes),
        "failure_count":len(failures),
        "contraindication_tags":sorted(failure_tags),
        "anti_patterns":["do not bypass applicability/precondition gates","do not treat memory as source authority"] + (["observed failed episodes exist; inspect evidence before broadening applicability"] if failures else []),
        "termination_conditions":["underlying procedure reports success","underlying evaluator/contract remains authoritative"],
        "recency":{"first_observed":successes[0].get("observed_at"),"last_observed":successes[-1].get("observed_at")},
        "environment_applicability":_common_environment(train),
        "authoritative_refs":{"capability_hash":procedure.get("capability_hash"),"evaluator_hash":procedure.get("evaluator_hash")},
        "validation_basis":{"training_episode_ids":[e.get("episode_id") for e in train],"heldout_episode_ids":[e.get("episode_id") for e in heldout]},
    }
    validation=[]
    for e in heldout:
        probe={"intent":(e.get("task") or {}).get("intent"),"task_kind":(e.get("task") or {}).get("task_kind"),"tags":(e.get("task") or {}).get("tags"),"environment":(e.get("task") or {}).get("environment"),"input":{k:None for k in ((e.get("task") or {}).get("input_keys") or [])}}
        validation.append({"episode_id":e.get("episode_id"),"expected":True,"applicability":_applicability(memory,probe)})
    heldout_ok=bool(heldout) and all(v["applicability"]["eligible"] for v in validation)
    active=len(successes)>=3 and heldout_ok and len(memory["intent_tokens"])>0
    initial_state="ACTIVE" if active else "CANDIDATE"
    memory["validation"]={"heldout_required":True,"heldout_passed":heldout_ok,"heldout_count":len(heldout),"checks":validation,"decision":initial_state}
    memory_hash=sha_json(memory)
    path=OBJECTS/f"{memory_hash}.json"
    if not path.exists(): safe_write_json(path,memory)
    reg=load_registry(); memories=reg["memories"]
    if memory_hash not in memories:
        memories[memory_hash]={"memory_hash":memory_hash,"state":initial_state,"created_at":utc(),"object":str(path),"procedure_fingerprint":procedure_fingerprint(procedure),"procedure":procedure,"retrievals":0,"successful_retrievals":0,"failed_retrievals":0,"superseded_by":None,"retired_at":None}
    superseded=[]
    if supersede_existing and initial_state=="ACTIVE":
        for h,r in list(memories.items()):
            if h==memory_hash or r.get("state")!="ACTIVE": continue
            if r.get("procedure_fingerprint")==memories[memory_hash]["procedure_fingerprint"]:
                r["state"]="SUPERSEDED"; r["superseded_by"]=memory_hash; r["superseded_at"]=utc(); superseded.append(h)
    save_registry(reg)
    append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"distilled","memory_hash":memory_hash,"state":initial_state,"success_count":len(successes),"failure_count":len(failures),"heldout_passed":heldout_ok,"superseded":superseded})
    return {"ok":True,"memory_hash":memory_hash,"state":initial_state,"object":str(path),"validation":memory["validation"],"success_count":len(successes),"failure_count":len(failures),"superseded":superseded}


def search(task: dict[str, Any], *, include_candidates: bool = False) -> list[dict[str, Any]]:
    reg=load_registry(); out=[]
    allowed={"ACTIVE"}|({"CANDIDATE"} if include_candidates else set())
    for h,r in reg["memories"].items():
        if r.get("state") not in allowed: continue
        try: memory=json.loads(pathlib.Path(r["object"]).read_text())
        except Exception: continue
        app=_applicability(memory,task)
        if app["eligible"]:
            out.append({"memory_hash":h,"state":r.get("state"),"score":app["score"],"reasons":app["reasons"],"mismatches":app["mismatches"],"procedure":memory.get("procedure"),"semantic_intent":memory.get("semantic_intent"),"authoritative_refs":memory.get("authoritative_refs"),"source_episode_count":len(memory.get("source_episode_ids") or []),"object":r.get("object")})
    out.sort(key=lambda x:(-float(x["score"]),x["memory_hash"]))
    return out


def retrieve(task: dict[str, Any]) -> dict[str, Any]:
    started=time.monotonic(); matches=search(task)
    selected=matches[0] if matches and float(matches[0]["score"])>=0.55 else None
    if selected:
        reg=load_registry(); rec=reg["memories"][selected["memory_hash"]]; rec["retrievals"]=int(rec.get("retrievals",0))+1; rec["last_retrieved_at"]=utc(); save_registry(reg)
    result={"action":"REUSE_MEMORY" if selected else "NO_MEMORY","selected":selected,"matches":matches[:5],"latency_ms":round((time.monotonic()-started)*1000,3),"retrieval_version":VERSION}
    append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"retrieval","task_hash":sha_json(normalize_task(task)),"selected":selected and selected["memory_hash"],"candidate_count":len(matches),"latency_ms":result["latency_ms"]})
    return result


def record_retrieval_outcome(memory_hash: str, success: bool, episode_id: str | None = None) -> dict[str, Any]:
    reg=load_registry(); rec=reg["memories"].get(memory_hash)
    if not isinstance(rec,dict): raise MemoryError("memory not found")
    key="successful_retrievals" if success else "failed_retrievals"; rec[key]=int(rec.get(key,0))+1; rec["last_outcome_at"]=utc(); save_registry(reg)
    append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"retrieval_outcome","memory_hash":memory_hash,"success":bool(success),"episode_id":episode_id})
    return {"memory_hash":memory_hash,"success":bool(success),"successful_retrievals":rec.get("successful_retrievals"),"failed_retrievals":rec.get("failed_retrievals")}


def retire(memory_hash: str, reason: str) -> dict[str, Any]:
    reg=load_registry(); rec=reg["memories"].get(memory_hash)
    if not isinstance(rec,dict): raise MemoryError("memory not found")
    previous=rec.get("state"); rec["state"]="RETIRED"; rec["retired_at"]=utc(); rec["retirement_reason"]=reason; save_registry(reg)
    append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"retired","memory_hash":memory_hash,"previous_state":previous,"reason":reason})
    return {"memory_hash":memory_hash,"previous_state":previous,"state":"RETIRED","provenance_retained":True,"object_retained":pathlib.Path(rec["object"]).exists()}


def show(memory_hash: str) -> dict[str, Any]:
    reg=load_registry(); rec=reg["memories"].get(memory_hash)
    if not isinstance(rec,dict): raise MemoryError("memory not found")
    obj=json.loads(pathlib.Path(rec["object"]).read_text())
    return {"registry":rec,"memory":obj}


def list_memories() -> list[dict[str, Any]]:
    reg=load_registry(); return sorted(reg["memories"].values(),key=lambda x:(str(x.get("state")),str(x.get("created_at"))))


def selftest() -> dict[str, Any]:
    global ROOT,OBJECTS,REGISTRY,EPISODES,PROVENANCE
    old=(ROOT,OBJECTS,REGISTRY,EPISODES,PROVENANCE)
    checks=[]
    def ck(name,ok,detail=None): checks.append({"name":name,"ok":bool(ok),"detail":detail})
    try:
        with tempfile.TemporaryDirectory(prefix="memory-selftest-") as td:
            ROOT=pathlib.Path(td); OBJECTS=ROOT/"objects"; REGISTRY=ROOT/"registry.json"; EPISODES=ROOT/"episodes.jsonl"; PROVENANCE=ROOT/"provenance.jsonl"
            proc={"capability_hash":"a"*64,"capability_name":"normalize","evaluator_hash":"b"*64}
            for i in range(3):
                record_episode({"intent":"normalize record keys and trim strings","task_kind":"normalize-record","tags":["json","normalization"],"environment":{"runtime":"lab"},"input":{"record":{}},"parameters":{"record":None}},proc,True,evidence={"case":i})
            d=distill("a"*64); ck("distill_active",d.get("state")=="ACTIVE",d)
            good=retrieve({"intent":"trim and normalize record keys","task_kind":"normalize-record","tags":["json","normalization"],"environment":{"runtime":"lab"},"input":{"record":{" A ":" x "}}}); ck("retrieve_applicable",good.get("action")=="REUSE_MEMORY",good)
            bad=retrieve({"intent":"trim and normalize csv columns","task_kind":"normalize-csv","tags":["csv","normalization"],"environment":{"runtime":"lab"},"input":{"rows":[]}}); ck("reject_superficial",bad.get("action")=="NO_MEMORY",bad)
            record_episode({"intent":"normalize record keys and trim strings","task_kind":"normalize-record","tags":["json","normalization"],"environment":{"runtime":"lab"},"input":{"record":{}},"parameters":{"record":None}},proc,True,evidence={"case":4})
            d2=distill("a"*64,supersede_existing=True); ck("supersession",bool(d2.get("superseded")),d2)
            rr=retire(d2["memory_hash"],"selftest"); ck("retirement_preserves",rr["object_retained"] and rr["provenance_retained"],rr)
            try: record_episode({"intent":"x","tags":[],"environment":{},"input":{}},proc,True,evidence={"token":"secret"}); sensitive=False
            except MemoryError: sensitive=True
            ck("sensitive_rejected",sensitive)
    finally:
        ROOT,OBJECTS,REGISTRY,EPISODES,PROVENANCE=old
    return {"version":VERSION,"schema_version":SCHEMA_VERSION,"passed":sum(1 for c in checks if c["ok"]),"total":len(checks),"checks":checks}


def _json_arg(text: str | None, path: str | None) -> Any:
    if text and path: raise MemoryError("use only one of --json/--file")
    if path: return json.loads(pathlib.Path(path).read_text())
    if text: return json.loads(text)
    return {}


def main() -> None:
    ap=argparse.ArgumentParser(description="Inspectable procedural memory distiller")
    ap.add_argument("--selftest",action="store_true")
    sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("import-forge"); p.add_argument("capability")
    p=sub.add_parser("record"); p.add_argument("--task-json"); p.add_argument("--task-file"); p.add_argument("--procedure-json"); p.add_argument("--procedure-file"); p.add_argument("--success",action="store_true")
    p=sub.add_parser("distill"); p.add_argument("capability"); p.add_argument("--supersede-existing",action="store_true")
    p=sub.add_parser("search"); p.add_argument("--json"); p.add_argument("--file"); p.add_argument("--include-candidates",action="store_true")
    p=sub.add_parser("retrieve"); p.add_argument("--json"); p.add_argument("--file")
    p=sub.add_parser("retire"); p.add_argument("memory"); p.add_argument("--reason",required=True)
    p=sub.add_parser("show"); p.add_argument("memory")
    sub.add_parser("list")
    args=ap.parse_args()
    try:
        if args.selftest: out=selftest()
        elif args.cmd=="import-forge": out=import_forge_episodes(args.capability)
        elif args.cmd=="record": out=record_episode(_json_arg(args.task_json,args.task_file),_json_arg(args.procedure_json,args.procedure_file),args.success)
        elif args.cmd=="distill": out=distill(args.capability,supersede_existing=args.supersede_existing)
        elif args.cmd=="search": out=search(_json_arg(args.json,args.file),include_candidates=args.include_candidates)
        elif args.cmd=="retrieve": out=retrieve(_json_arg(args.json,args.file))
        elif args.cmd=="retire": out=retire(args.memory,args.reason)
        elif args.cmd=="show": out=show(args.memory)
        elif args.cmd=="list": out=list_memories()
        else: ap.print_help(); raise SystemExit(2)
        print(json.dumps(out,indent=2,sort_keys=True))
        if args.selftest and out["passed"]!=out["total"]: raise SystemExit(1)
    except MemoryError as exc:
        print(json.dumps({"ok":False,"error":str(exc)},indent=2),file=os.sys.stderr); raise SystemExit(1)

if __name__=="__main__": main()
