#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import time
from collections import defaultdict, deque
from typing import Any

VERSION = "gen8-context-compiler-r1"
SCHEMA_VERSION = 1
SOURCE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_CONTEXT_SOURCE_ROOT", "/opt/optiplex-lab"))
STATE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_CONTEXT_STATE_ROOT", "/var/lib/optiplex-lab"))
TWIN_PATH = pathlib.Path(os.environ.get("OPTIPLEX_CONTEXT_TWIN", "/var/lib/optiplex-lab/twin/twin-current.json"))
CAUSAL_PATH = pathlib.Path(os.environ.get("OPTIPLEX_CONTEXT_CAUSAL", "/var/lib/optiplex-lab/twin/causal-index.json"))
BUILD_PATH = pathlib.Path(os.environ.get("OPTIPLEX_CONTEXT_BUILD", "/etc/optiplex-lab/build.json"))
MEMORY_REGISTRY = pathlib.Path(os.environ.get("OPTIPLEX_MEMORY_ROOT", "/var/lib/optiplex-lab/memory")) / "registry.json"
REGRESSION_REGISTRY = pathlib.Path(os.environ.get("OPTIPLEX_REGRESSION_ROOT", "/var/lib/optiplex-lab/regressions")) / "registry.json"
DEFAULT_BUDGET = 24000

STOPWORDS = {
    "a","an","and","are","as","at","be","before","by","can","change","code","do","for","from","how","i","in","into","is","it","of","on","or","plan","please","should","task","that","the","this","to","use","using","what","when","where","which","why","with","without","lab","optiplex","self","building","computer",
}
GENERIC_TOKENS = {"source","system","current","accepted","generation","file","module","work","real","context"}
DEPENDENCY_RELATIONS = {"imports","depends_on","invokes","consumes","references","generated_from","validates","gates","recovers_to","authoritative_for","protected_by"}
CRITICAL_KINDS = {"source","validation","regression","evaluator","workflow","workflow_graph","build_state","recovery","service"}
SUPPORTING_KINDS = {"capability","procedural_memory","benchmark_artifact","evidence_artifact","artifact","generation","registry"}


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
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stem(token: str) -> str:
    x = token.lower().strip("_-.")
    for suffix in ("ization", "ations", "ation", "ments", "ment", "ingly", "edly", "ing", "ies", "ers", "ed", "es", "s"):
        if len(x) > len(suffix) + 3 and x.endswith(suffix):
            if suffix == "ies": return x[:-3] + "y"
            return x[:-len(suffix)]
    return x


def tokens(text: str) -> list[str]:
    out = []
    for raw in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", text.lower()):
        for part in re.split(r"[_.:/-]+", raw):
            s = stem(part)
            if len(s) >= 3 and s not in STOPWORDS:
                out.append(s)
    return sorted(set(out))


def classify(text: str) -> str:
    t = text.lower().strip()
    # Failure intent outranks all other vocabulary because causal reconstruction is safety-critical.
    if any(x in t for x in ("debug", "failure", "failed", "investigate", "root cause", "trace", "why did", "causal")):
        return "debugging"
    has_source = bool(re.search(r"(?:/[^ ]+|\b[A-Za-z0-9_.-]+\.py\b)", text))
    change_phrase = any(x in t for x in ("source change", "code change", "add support", "change to /", "plan a safe code change", "plan a code change"))
    change_verb = bool(re.search(r"\b(?:modify|implement|refactor|patch|edit|add|alter)\b", t))
    if change_phrase or change_verb or (has_source and re.search(r"\bplan\b", t) and any(x in t for x in ("change","modify","alter","refactor","patch","edit"))):
        return "code_change_planning"
    if any(x in t for x in ("benchmark", "evaluate", "evaluation", "test suite", "acceptance")):
        return "evaluation"
    # Explicit explanatory framing should not become lifecycle execution merely because recovery is discussed.
    if re.match(r"^(?:explain|describe|what is|how does|how do|show how)\b", t):
        return "explanation_architecture"
    if any(x in t for x in ("lifecycle", "recovery", "rollback", "last-known-good", " lkg", "restart", "build metadata", "build.json", "self-update")):
        return "lifecycle_recovery"
    if has_source and re.search(r"\b(?:validation|validate)\b", t):
        return "code_change_planning"
    return "explanation_architecture"


def explicit_refs(text: str) -> list[str]:
    refs = set()
    for m in re.findall(r"/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+", text):
        refs.add(m.rstrip(".,;:)"))
    for m in re.findall(r"\b[A-Za-z0-9_.-]+\.py\b", text): refs.add(m)
    for m in re.findall(r"\b[a-fA-F0-9]{40,64}\b", text): refs.add(m.lower())
    for m in re.findall(r"\b(?:gen\d+[A-Za-z0-9._-]*|[A-Za-z0-9._-]+@[0-9]+)\b", text, flags=re.I): refs.add(m)
    return sorted(refs)


def normalize_task(text: str) -> dict[str, Any]:
    kind = classify(text)
    tt = tokens(text)
    tags = []
    for tag in ("python","json","normalization","transform","workflow","graph","forge","memory","regression","recovery","security","benchmark","twin","causal"):
        if tag in text.lower() or stem(tag) in tt: tags.append(tag)
    return {
        "intent": " ".join(text.strip().split()),
        "tokens": tt,
        "task_kind": kind,
        "tags": sorted(set(tags)),
        "explicit_refs": explicit_refs(text),
    }


def node_text(node: dict[str, Any]) -> str:
    vals = [node.get("id"), node.get("name"), node.get("identity"), node.get("source_path"), node.get("source_sha256"), node.get("generation")]
    vals.append(json.dumps(node.get("metadata") or {}, sort_keys=True))
    return " ".join(str(x) for x in vals if x).lower()


def node_score(node: dict[str, Any], task: dict[str, Any]) -> float:
    hay = node_text(node)
    nt = set(tokens(hay))
    tt = set(task["tokens"]) - GENERIC_TOKENS
    overlap = len(tt & nt)
    score = overlap * 4.0
    for ref in task["explicit_refs"]:
        r = ref.lower()
        if r == str(node.get("id") or "").lower() or r == str(node.get("identity") or "").lower() or r == str(node.get("source_path") or "").lower() or r == str(node.get("source_sha256") or "").lower(): score += 100
        elif r in hay: score += 25
    kind = task["task_kind"]
    nk = node.get("kind")
    if kind == "code_change_planning" and nk == "source": score += 5
    if kind == "debugging" and nk in {"regression","source","evidence_artifact"}: score += 3
    if kind == "evaluation" and nk in {"validation","benchmark_artifact","evaluator","regression"}: score += 4
    if kind == "lifecycle_recovery" and nk in {"build_state","recovery","service","workflow","workflow_graph"}: score += 7
    if kind == "explanation_architecture" and nk in {"source","generation","authority_boundary"}: score += 1
    return score


def current_freshness(node: dict[str, Any]) -> dict[str, Any]:
    path_text = node.get("source_path")
    expected = node.get("source_sha256")
    if not path_text or not expected: return {"state":"not_applicable"}
    p = pathlib.Path(path_text)
    if not p.is_file(): return {"state":"missing","path":path_text,"expected_sha256":expected}
    mode = node.get("freshness_mode") or "hash"
    expected_bytes = node.get("source_bytes")
    if mode == "append_only" and isinstance(expected_bytes, int):
        cur = p.stat().st_size
        if cur < expected_bytes: return {"state":"stale","reason":"append-only source shrank","path":path_text}
        with p.open("rb") as fh: prefix = fh.read(expected_bytes)
        if sha_bytes(prefix) != expected: return {"state":"stale","reason":"append-only prefix changed","path":path_text}
        return {"state":"fresh" if cur == expected_bytes else "newer_evidence_available","path":path_text,"indexed_bytes":expected_bytes,"current_bytes":cur}
    actual = sha_path(p)
    return {"state":"fresh" if actual == expected else "stale","path":path_text,"expected_sha256":expected,"current_sha256":actual}


def source_excerpt(path: pathlib.Path, task_tokens: list[str], max_bytes: int = 1800) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    lines = raw.splitlines()
    if not lines: return None
    candidates: list[tuple[float,int,int,str]] = []
    if path.suffix == ".py":
        try:
            tree = ast.parse(raw)
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and getattr(n, "end_lineno", None):
                    start, end = int(n.lineno), int(n.end_lineno)
                    block = "\n".join(lines[start-1:end])
                    b_tokens = set(tokens(n.name + " " + block[:5000]))
                    score = len(set(task_tokens) & b_tokens) * 5 + (2 if n.name.lower() in " ".join(task_tokens) else 0)
                    candidates.append((score, start, end, block))
        except SyntaxError:
            pass
    if not candidates:
        for i, line in enumerate(lines):
            score = len(set(task_tokens) & set(tokens(line)))
            if score:
                s=max(1,i); e=min(len(lines),i+4); candidates.append((score,s,e,"\n".join(lines[s-1:e])))
    candidates.sort(key=lambda x:(-x[0],x[1],x[2]))
    chosen=[]; used=0; seen=[]
    for score,start,end,block in candidates:
        if score <= 0 and chosen: continue
        if any(not (end < a or start > b) for a,b in seen): continue
        data=block.encode()
        if used + len(data) > max_bytes:
            remain=max_bytes-used
            if remain < 200: continue
            block=data[:remain].decode("utf-8",errors="ignore")
        chosen.append({"start_line":start,"end_line":end,"text":block})
        seen.append((start,end)); used += len(block.encode())
        if used >= max_bytes or len(chosen) >= 2: break
    if not chosen:
        block="\n".join(lines[:min(35,len(lines))])
        block=block.encode()[:max_bytes].decode("utf-8",errors="ignore")
        chosen=[{"start_line":1,"end_line":min(35,len(lines)),"text":block}]
    return {"path":str(path),"excerpts":chosen,"bytes":sum(len(x["text"].encode()) for x in chosen)}


def evidence_from_node(node: dict[str, Any], tier: int, reason: str, task: dict[str, Any], *, relation_status: str = "observed", dependency_path: list[str] | None = None, required: bool = False) -> dict[str, Any]:
    fresh=current_freshness(node)
    rec={
        "evidence_id":node["id"], "kind":node.get("kind"), "priority_tier":tier, "required":bool(required),
        "authoritative":bool(node.get("authoritative")),
        "provenance":{"source_path":node.get("source_path"),"source_sha256":node.get("source_sha256"),"freshness":fresh},
        "relation_status":relation_status,
        "selection_reason":reason,
        "dependency_path":dependency_path or [],
        "structured_fact":{"name":node.get("name"),"identity":node.get("identity"),"generation":node.get("generation"),"metadata":node.get("metadata") or {}},
    }
    sp=node.get("source_path")
    if sp and node.get("kind") == "source" and fresh.get("state") != "missing":
        excerpt=source_excerpt(pathlib.Path(sp), task["tokens"])
        if excerpt: rec["source_excerpt"]=excerpt
    return rec


def security_record(snapshot: dict[str, Any]) -> dict[str, Any]:
    boundaries=[]; prohibited=[]
    for n in snapshot.get("nodes",[]):
        if n.get("kind") == "authority_boundary": boundaries.append({"id":n["id"],"name":n.get("name"),"scope":(n.get("metadata") or {}).get("scope")})
        elif n.get("kind") == "prohibited_target": prohibited.append({"id":n["id"],"name":n.get("name")})
    return {
        "evidence_id":"authority:guest-security-boundary", "kind":"authority_security", "priority_tier":0, "required":True, "authoritative":True,
        "provenance":{"source_path":None,"source_sha256":None,"freshness":{"state":"policy_seed"}}, "relation_status":"observed_policy",
        "selection_reason":"Tier 0 authority/security boundary is never budget-pruned.", "dependency_path":[],
        "structured_fact":{"boundaries":sorted(boundaries,key=lambda x:x["id"]),"prohibited_targets":sorted(prohibited,key=lambda x:x["id"]),"rule":"The VM boundary is the security boundary; host credentials/filesystem/control sockets/private network/production authority remain prohibited."}
    }


def operational_record(snapshot: dict[str, Any]) -> dict[str, Any]:
    build=safe_json(BUILD_PATH); build=build if isinstance(build,dict) else {}
    server=SOURCE_ROOT/"server.py"; lkg=STATE_ROOT/"recovery/server.last-known-good.py"
    tools=sorted(n["name"] for n in snapshot.get("nodes",[]) if n.get("kind")=="mcp_tool")
    return {
        "evidence_id":"operational:accepted-identity", "kind":"operational_identity", "priority_tier":0, "required":True, "authoritative":True,
        "provenance":{"source_path":str(BUILD_PATH),"source_sha256":sha_path(BUILD_PATH),"freshness":{"state":"fresh" if BUILD_PATH.is_file() else "missing"}},
        "relation_status":"observed_runtime", "selection_reason":"Tier 0 current accepted/live identity required to prevent capability/server-generation confusion.", "dependency_path":[],
        "structured_fact":{"generation":build.get("generation"),"build_id":build.get("build_id"),"recovery_state":build.get("recovery_state"),"source_sha256":build.get("source_sha256"),"last_known_good_sha256":build.get("last_known_good_sha256"),"live_server_sha256":sha_path(server),"lkg_sha256":sha_path(lkg),"permanent_mcp_tools":len(tools),"tool_names":tools}
    }


def graph_expansion(snapshot: dict[str, Any], seed_ids: list[str], max_depth: int = 2) -> dict[str, dict[str, Any]]:
    edges=snapshot.get("edges",[]); adj=defaultdict(list)
    kinds={n.get("id"):n.get("kind") for n in snapshot.get("nodes",[]) if isinstance(n,dict)}
    # These are useful evidence endpoints but dangerous traversal hubs: crossing them creates
    # component->generation/registry->every-other-component context explosions.
    stop_hubs={"generation","registry","benchmark_artifact","evidence_artifact","evaluator"}
    for e in edges:
        if e.get("relation") not in DEPENDENCY_RELATIONS: continue
        adj[e["src"]].append((e["dst"],e,"forward"))
        adj[e["dst"]].append((e["src"],e,"reverse"))
    out={}; q=deque((sid,0,[sid]) for sid in sorted(seed_ids)); seen={sid:0 for sid in seed_ids}
    while q:
        cur,depth,path=q.popleft()
        if depth >= max_depth: continue
        for other,e,direction in sorted(adj.get(cur,[]), key=lambda x:(x[0],x[1].get("id",""))):
            nd=depth+1
            candidate={"depth":nd,"path":path+[other],"relation":e.get("relation"),"evidence_kind":e.get("evidence_kind"),"confidence":float(e.get("confidence",0)),"direction":direction}
            old=out.get(other)
            if old is None or nd < old["depth"] or (nd == old["depth"] and candidate["path"] < old["path"]): out[other]=candidate
            # Reverse source edges are downstream consumers (often benchmarks); record the edge but
            # do not traverse through that source. Likewise, stop at registry/generation/artifact hubs.
            # Source dependencies are evidence endpoints. Reverse source edges are downstream
            # consumers, and very high-fanout sources (notably server.py) are architectural hubs;
            # traversing through either creates unrelated context explosions. Low-fanout forward
            # source dependencies may still be traversed to preserve useful transitive evidence.
            source_hub = kinds.get(other)=="source" and len(adj.get(other, [])) > 12
            traversable = not (kinds.get(other)=="source" and direction=="reverse") and not source_hub and kinds.get(other) not in stop_hubs
            if traversable and nd < max_depth and (other not in seen or nd < seen[other]): seen[other]=nd; q.append((other,nd,path+[other]))
    for sid in seed_ids: out.pop(sid,None)
    return out


def load_memory_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    reg=safe_json(MEMORY_REGISTRY)
    if not isinstance(reg,dict): return []
    tt=set(task["tokens"]); text=task["intent"].lower(); out=[]
    for h,r in sorted((reg.get("memories") or {}).items()):
        if not isinstance(r,dict) or r.get("state") != "ACTIVE": continue
        p=pathlib.Path(str(r.get("object") or "")); obj=safe_json(p)
        if not isinstance(obj,dict): continue
        mt=set(obj.get("intent_tokens") or []) | set(tokens(str(obj.get("semantic_intent") or ""))) | set(obj.get("required_tags") or [])
        overlap=len(tt & {stem(str(x)) for x in mt})
        cap=str((obj.get("procedure") or {}).get("capability_name") or "")
        explicit=bool(cap and cap.lower() in text)
        score=(overlap/max(1,len(tt))) + (1.0 if explicit else 0.0)
        if overlap or explicit:
            out.append({"hash":h,"score":round(score,3),"object":str(p),"sha256":sha_path(p),"memory":obj,"registry":r})
    out.sort(key=lambda x:(-x["score"],x["hash"]))
    return out[:5]


def load_regression_candidates(task: dict[str, Any]) -> list[dict[str, Any]]:
    reg=safe_json(REGRESSION_REGISTRY)
    if not isinstance(reg,dict): return []
    tt=set(task["tokens"]); text=task["intent"].lower(); out=[]
    for h,r in sorted((reg.get("regressions") or {}).items()):
        if not isinstance(r,dict) or r.get("state") != "ACTIVE": continue
        p=pathlib.Path(str(r.get("object") or "")); obj=safe_json(p)
        if not isinstance(obj,dict): continue
        hay=json.dumps({"selector":obj.get("selector"),"failure_evidence":obj.get("failure_evidence"),"source_case":obj.get("source_case")},sort_keys=True)
        rt=set(tokens(hay)); overlap=len(tt & rt); explicit=bool(h.lower() in text)
        score=overlap + (10 if explicit else 0)
        # One generic token such as "selftest" is not enough to inject an unrelated regression.
        if explicit or overlap >= 2: out.append({"hash":h,"score":score,"object":str(p),"sha256":sha_path(p),"regression":obj,"registry":r})
    out.sort(key=lambda x:(-x["score"],x["hash"]))
    return out[:5]


def detect_contradictions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    groups=defaultdict(list)
    for n in snapshot.get("nodes",[]):
        if n.get("authoritative") and n.get("identity"): groups[str(n["identity"])].append(n)
    out=[]
    for ident,items in sorted(groups.items()):
        if len(items)<2: continue
        sigs={(x.get("source_sha256"),x.get("generation"),canonical(x.get("metadata") or {}).decode()) for x in items}
        if len(sigs)>1: out.append({"identity":ident,"nodes":sorted(x["id"] for x in items),"reason":"Multiple authoritative records make materially different claims for the same identity."})
    build=safe_json(BUILD_PATH)
    if isinstance(build,dict):
        live=sha_path(SOURCE_ROOT/"server.py"); lkg=sha_path(STATE_ROOT/"recovery/server.last-known-good.py")
        source=build.get("source_sha256"); state=build.get("recovery_state")
        if source and live and source != live: out.append({"identity":"operational-server","reason":"build.source_sha256 differs from live server bytes","build_source_sha256":source,"live_sha256":live})
        if state=="ACCEPTED" and live and lkg and live != lkg: out.append({"identity":"accepted-lkg","reason":"ACCEPTED live server differs from LKG","live_sha256":live,"lkg_sha256":lkg})
    return out


def causal_candidate(task: dict[str, Any], seed_nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if task["task_kind"] not in {"debugging","lifecycle_recovery"}: return None
    idx=safe_json(CAUSAL_PATH)
    if not isinstance(idx,dict): return {"missing":True,"reason":"causal index missing"}
    try: mod=load_module(SOURCE_ROOT/"causal_spine.py","gen8_causal")
    except Exception as exc: return {"missing":True,"reason":f"causal spine unavailable: {type(exc).__name__}"}
    needles=[]
    for ref in task["explicit_refs"]: needles.append(ref)
    for n in seed_nodes[:4]: needles.extend([str(n.get("source_sha256") or ""),str(n.get("name") or ""),str(n.get("identity") or "")])
    needles += [x for x in task["tokens"] if len(x)>=6]
    seen=set()
    for needle in needles:
        needle=needle.strip()
        if not needle or needle in seen: continue
        seen.add(needle)
        try: r=mod.reconstruct(idx,needle,4)
        except Exception: continue
        events=r.get("events") or r.get("matches") or []
        edges=r.get("edges") or r.get("relationships") or []
        if events or edges:
            return {"needle":needle,"result":{"events":events[:12],"edges":edges[:16],"uncertainty":r.get("uncertainty") or [],"digest":idx.get("digest")},"source_sha256":sha_path(CAUSAL_PATH)}
    return {"missing":True,"reason":"No causal event/edge matched task refs or selected components.","causal_digest":idx.get("digest")}


def make_memory_record(item: dict[str, Any]) -> dict[str, Any]:
    obj=item["memory"]
    return {"evidence_id":f"memory:{item['hash']}","kind":"procedural_memory","priority_tier":2,"required":False,"authoritative":False,"provenance":{"source_path":item["object"],"source_sha256":item["sha256"],"freshness":{"state":"fresh" if item["sha256"] else "missing"}},"relation_status":"derived_memory","selection_reason":f"Read-only procedural-memory match score={item['score']}; memory remains advisory, authoritative capability/evaluator refs are retained.","dependency_path":[],"structured_fact":{"semantic_intent":obj.get("semantic_intent"),"procedure":obj.get("procedure"),"authoritative_refs":obj.get("authoritative_refs"),"preconditions":obj.get("preconditions"),"anti_patterns":obj.get("anti_patterns"),"validation":obj.get("validation")}}


def make_regression_record(item: dict[str, Any], required: bool=False) -> dict[str, Any]:
    obj=item["regression"]
    return {"evidence_id":f"regression:{item['hash']}","kind":"regression","priority_tier":1 if required else 2,"required":required,"authoritative":True,"provenance":{"source_path":item["object"],"source_sha256":item["sha256"],"freshness":{"state":"fresh" if item["sha256"] else "missing"}},"relation_status":"observed_registry","selection_reason":f"Active failure regression matches task terms (score={item['score']}).","dependency_path":[],"structured_fact":{"selector":obj.get("selector"),"failure_evidence":obj.get("failure_evidence"),"source_case":obj.get("source_case"),"verification":obj.get("verification"),"minimization":obj.get("minimization")}}


def build_packet(task_text: str, *, budget_bytes: int=DEFAULT_BUDGET, snapshot_path: pathlib.Path=TWIN_PATH, allow_expand: bool=True, snapshot_override: dict[str,Any] | None=None) -> dict[str, Any]:
    task=normalize_task(task_text)
    snapshot=snapshot_override if snapshot_override is not None else safe_json(snapshot_path)
    if not isinstance(snapshot,dict):
        raise RuntimeError(f"Twin snapshot missing or invalid: {snapshot_path}")
    nodes={n["id"]:n for n in snapshot.get("nodes",[]) if isinstance(n,dict) and n.get("id")}
    scores=[(node_score(n,task),n["id"]) for n in nodes.values()]
    scores.sort(key=lambda x:(-x[0],x[1]))
    # Exact explicit refs are authoritative owner anchors. When one exists, do not
    # dilute it with unrelated keyword-scored seeds; dependencies are added by graph expansion.
    exact_seed_ids=[]
    for ref in task["explicit_refs"]:
        rl=ref.lower()
        for n in nodes.values():
            vals=[n.get("id"),n.get("identity"),n.get("source_path"),n.get("source_sha256"),n.get("name")]
            texts=[str(v).lower() for v in vals if v]
            if rl in texts or (len(rl)>=12 and any(x.startswith(rl) for x in texts if re.fullmatch(r"[0-9a-f]{40,64}",x))):
                if n.get("kind") not in {"prohibited_target","authority_boundary","mcp_tool"}: exact_seed_ids.append(n["id"])
    seed_ids=sorted(set(exact_seed_ids))
    # A literal component/capability name in the task is also an exact owner anchor even when
    # it is not a filesystem/hash ref (for example gen5-record-normalizer).
    if not seed_ids:
        intent_lower=task["intent"].lower()
        named=[]
        for n in nodes.values():
            name=str(n.get("name") or "").strip().lower()
            if len(name) >= 5 and name in intent_lower and n.get("kind") not in {"prohibited_target","authority_boundary","mcp_tool"}: named.append(n["id"])
        seed_ids=sorted(set(named))[:3]
    if not seed_ids:
        positive=[(score,nid) for score,nid in scores if score>0 and nodes[nid].get("kind") not in {"prohibited_target","authority_boundary","mcp_tool"}]
        if positive:
            top=positive[0][0]
            # Keep only strongly related peers near the top score, capped at three owners.
            floor=max(4.0, top*0.70)
            seed_ids=[nid for score,nid in positive if score>=floor][:3]
    # Controlled deterministic fallback for broad architecture/lifecycle tasks.
    if not seed_ids:
        preferred={"explanation_architecture":{"source","generation"},"lifecycle_recovery":{"build_state","recovery","service","workflow_graph"},"debugging":{"source","regression","evidence_artifact"},"evaluation":{"validation","benchmark_artifact","source"},"code_change_planning":{"source"}}[task["task_kind"]]
        seed_ids=sorted(n["id"] for n in nodes.values() if n.get("kind") in preferred)[:5]
    seed_nodes=[nodes[x] for x in seed_ids]
    expansion=graph_expansion(snapshot,seed_ids,2)

    records: dict[str,dict[str,Any]]={}
    def add(rec:dict[str,Any]):
        eid=rec["evidence_id"]
        old=records.get(eid)
        if old is None or int(rec["priority_tier"]) < int(old["priority_tier"]): records[eid]=rec

    add(security_record(snapshot)); add(operational_record(snapshot))
    for sid in seed_ids:
        add(evidence_from_node(nodes[sid],1,f"Top deterministic task match (score={node_score(nodes[sid],task):.1f}).",task,required=True))

    for nid,info in sorted(expansion.items(), key=lambda x:(x[1]["depth"],x[0])):
        n=nodes.get(nid)
        if not n: continue
        nk=n.get("kind")
        if nk not in CRITICAL_KINDS | SUPPORTING_KINDS: continue
        # Reverse source edges are usually downstream consumers/tests. Their validations are attached
        # separately by Gen7 impact, so pulling the source bodies creates high-fanout context explosions.
        if nk == "source" and info.get("direction") == "reverse": continue
        # server.py publishes command-path metadata for the whole guest. A lifecycle/recovery task needs
        # server/build/LKG/service + impact validations, not every command implementation body.
        if task["task_kind"] == "lifecycle_recovery" and nk == "source" and info.get("relation") == "references": continue
        tier=1 if info["depth"]==1 and nk in CRITICAL_KINDS else 2
        required=tier==1 and nk in {"validation","regression","recovery","build_state"}
        relation_status="inferred" if info.get("evidence_kind")=="inferred" else "observed"
        add(evidence_from_node(n,tier,f"Dependency/impact path from selected task owner via {info['relation']} ({info['direction']}, depth {info['depth']}).",task,relation_status=relation_status,dependency_path=info["path"],required=required))

    # Explicit impact-derived validations are mandatory Tier 1.
    try: twinmod=load_module(SOURCE_ROOT/"architecture_twin.py","gen8_twin")
    except Exception: twinmod=None
    if twinmod:
        for sid in seed_ids:
            try: imp=twinmod.impact(snapshot,sid,2)
            except Exception: continue
            for vid in imp.get("validations") or []:
                if vid in nodes: add(evidence_from_node(nodes[vid],1,"Gen7 bounded change-impact explicitly selected this validation.",task,dependency_path=[sid,vid],required=True))
            for rid in imp.get("recovery") or []:
                if rid in nodes: add(evidence_from_node(nodes[rid],1,"Gen7 change-impact attached a recovery/build implication.",task,dependency_path=[sid,rid],required=True))

    for mem in load_memory_candidates(task)[:2]:
        rec=make_memory_record(mem)
        memory_required=("memory" in task["tags"] or "reuse" in task["intent"].lower()) and float(mem.get("score",0)) >= 0.5
        if memory_required:
            rec["priority_tier"]=1; rec["required"]=True
            rec["selection_reason"]="Repeated-task intent makes the high-confidence procedural memory task-critical; authoritative capability/evaluator refs remain attached."
        # Prefer the compiler-enriched memory record over the Twin alias for the same immutable object.
        records.pop(f"procedural_memory:{mem['hash']}",None)
        add(rec)
    for reg in load_regression_candidates(task)[:3]: add(make_regression_record(reg,required=task["task_kind"] in {"debugging","evaluation"}))

    causal=causal_candidate(task,seed_nodes)
    causal_missing=False
    if causal and not causal.get("missing"):
        causal_required=task["task_kind"]=="debugging"
        add({"evidence_id":f"causal:{sha_bytes(str(causal['needle']).encode())[:16]}","kind":"causal_evidence","priority_tier":1 if causal_required else 2,"required":causal_required,"authoritative":False,"provenance":{"source_path":str(CAUSAL_PATH),"source_sha256":causal.get("source_sha256"),"freshness":{"state":"fresh" if causal.get("source_sha256") else "missing"}},"relation_status":"causal_or_lineage_only_when_explicit","selection_reason":f"Historical causal lookup matched task needle {causal['needle']!r}; debugging lineage is task-critical." if causal_required else f"Historical causal lookup matched task needle {causal['needle']!r}.","dependency_path":[],"structured_fact":causal["result"]})
    elif causal and causal.get("missing"):
        causal_missing=True

    contradictions=detect_contradictions(snapshot)
    uncertainties=[]
    for rec in records.values():
        state=((rec.get("provenance") or {}).get("freshness") or {}).get("state")
        if state in {"stale","missing","newer_evidence_available"}:
            uncertainties.append({"evidence_id":rec["evidence_id"],"freshness":rec["provenance"]["freshness"],"critical":rec["priority_tier"]<=1})
    if causal_missing: uncertainties.append({"evidence_id":"causal:index","critical":task["task_kind"] in {"debugging","lifecycle_recovery"},"reason":causal.get("reason") if causal else "missing"})
    if contradictions:
        add({"evidence_id":"warning:contradictory-authoritative-evidence","kind":"contradiction_warning","priority_tier":0,"required":True,"authoritative":True,"provenance":{"source_path":None,"source_sha256":None,"freshness":{"state":"contradictory"}},"relation_status":"conflict","selection_reason":"Tier 0 contradictory authoritative claims are surfaced and never silently merged.","dependency_path":[],"structured_fact":{"contradictions":contradictions}})

    fail_closed=bool(contradictions or any(u.get("critical") and (u.get("freshness") or {}).get("state") in {"stale","missing"} for u in uncertainties) or (causal_missing and task["task_kind"] in {"debugging","lifecycle_recovery"}))
    broad_fallback=False
    if fail_closed or not seed_ids:
        broad_fallback=True
        # Conservative bounded fallback: add core Twin/causal/recovery sources, but never claim sufficiency.
        for name in ("architecture_twin.py","causal_spine.py","workflow_graphs.py","code_mode.py"):
            matches=[n for n in nodes.values() if n.get("kind")=="source" and n.get("name")==name]
            for n in matches: add(evidence_from_node(n,2,"Controlled broad fallback because critical evidence is stale/missing/contradictory or owner resolution was inadequate.",task))

    mandatory=sorted((r for r in records.values() if int(r["priority_tier"])<=1),key=lambda r:(r["priority_tier"],r["evidence_id"]))
    optional=sorted((r for r in records.values() if int(r["priority_tier"])>1),key=lambda r:(r["priority_tier"],r["evidence_id"]))
    input_digests={
        "compiler_source_sha256":sha_path(pathlib.Path(__file__)),
        "twin_snapshot_sha256":sha_path(snapshot_path) if snapshot_override is None else sha_bytes(canonical(snapshot)),
        "twin_graph_digest":snapshot.get("graph_digest"),
        "causal_index_sha256":sha_path(CAUSAL_PATH),
        "build_state_sha256":sha_path(BUILD_PATH),
        "memory_registry_sha256":sha_path(MEMORY_REGISTRY),
        "regression_registry_sha256":sha_path(REGRESSION_REGISTRY),
    }
    base={
        "schema_version":SCHEMA_VERSION,"compiler_version":VERSION,"task_text":task["intent"],"task_hash":sha_bytes(task["intent"].encode()),"normalized_task":task,"task_kind":task["task_kind"],
        "generation_build_twin_identity":{"operational_build":safe_json(BUILD_PATH) if isinstance(safe_json(BUILD_PATH),dict) else {},"twin_version":snapshot.get("version"),"twin_graph_digest":snapshot.get("graph_digest")},
        "input_evidence_digests":input_digests,"selected_evidence_records":[],"memories":[],"causal_evidence":[],"regressions":[],"validations":[],"recovery_requirements":[],"authority_security_requirements":[],
        "contradictions":contradictions,"uncertainties":uncertainties,"controlled_broad_fallback":broad_fallback,"fail_closed":fail_closed,
        "omitted_candidate_evidence":[],"budget":{"requested_bytes":int(budget_bytes),"effective_bytes":int(budget_bytes),"bytes_used":0,"token_estimate":0,"expanded":False,"policy":"Tier 0 and required Tier 1 are never budget-pruned; Tier 2 then Tier 3 are pruned first."}
    }
    def enrich(packet:dict[str,Any], selected:list[dict[str,Any]]) -> None:
        packet["selected_evidence_records"]=selected
        packet["memories"]=[r["evidence_id"] for r in selected if r["kind"]=="procedural_memory"]
        packet["causal_evidence"]=[r["evidence_id"] for r in selected if r["kind"]=="causal_evidence"]
        packet["regressions"]=[r["evidence_id"] for r in selected if r["kind"]=="regression"]
        packet["validations"]=[r["evidence_id"] for r in selected if r["kind"] in {"validation","evaluator","benchmark_artifact"}]
        packet["recovery_requirements"]=[r["evidence_id"] for r in selected if r["kind"] in {"recovery","build_state","service"}]
        packet["authority_security_requirements"]=[r["evidence_id"] for r in selected if r["priority_tier"]==0 and r["kind"] in {"authority_security","operational_identity","contradiction_warning"}]

    selected=list(mandatory); enrich(base,selected)
    reserve=240
    min_bytes=len(canonical(base))+reserve
    effective=int(budget_bytes)
    if min_bytes > effective:
        if allow_expand:
            effective=min_bytes
            base["budget"]["effective_bytes"]=effective; base["budget"]["expanded"]=True
        else:
            base["fail_closed"]=True
            base["uncertainties"].append({"critical":True,"reason":"Tier 0 + required Tier 1 exceed requested context budget."})
    omitted=[]
    if min_bytes <= effective or allow_expand:
        for rec in optional:
            test=json.loads(json.dumps(base)); enrich(test,selected+[rec])
            if len(canonical(test))+reserve <= effective: selected.append(rec); enrich(base,selected)
            else: omitted.append({"evidence_id":rec["evidence_id"],"priority_tier":rec["priority_tier"],"reason":f"budget-pruned-tier-{rec['priority_tier']}"})
    selected_ids={r["evidence_id"] for r in selected}
    scored_nonselected=[]
    for score,nid in scores:
        if nid in selected_ids or score<=0: continue
        scored_nonselected.append({"evidence_id":nid,"priority_tier":3,"reason":"candidate not selected: lower task relevance than bounded dependency/impact set","score":round(score,2)})
    for item in omitted + scored_nonselected[:12]:
        test=json.loads(json.dumps(base)); test["omitted_candidate_evidence"]=(base["omitted_candidate_evidence"]+[item])
        if len(canonical(test))+reserve <= effective: base["omitted_candidate_evidence"].append(item)
    enrich(base,selected)
    seed_material={"task_hash":base["task_hash"],"twin":snapshot.get("graph_digest"),"selected":[r["evidence_id"] for r in selected],"compiler":VERSION}
    base["packet_id"]="ctx_"+sha_bytes(canonical(seed_material))[:20]
    digest=sha_bytes(canonical(base)); base["packet_digest"]=digest
    used=len(canonical(base)); base["budget"]["bytes_used"]=used; base["budget"]["token_estimate"]=(used+3)//4
    # Updating budget usage changes canonical size; make the final digest reflect the final deterministic packet.
    base["packet_digest"]=sha_bytes(canonical({k:v for k,v in base.items() if k!="packet_digest"}))
    base["budget"]["bytes_used"]=len(canonical(base)); base["budget"]["token_estimate"]=(base["budget"]["bytes_used"]+3)//4
    if base["budget"]["bytes_used"] > effective:
        base["fail_closed"]=True
        base["uncertainties"].append({"critical":True,"reason":"Final packet metadata exceeded effective byte budget; caller must expand budget."})
    return base


def selftest() -> dict[str, Any]:
    checks=[]
    def check(name:str,ok:bool,detail:Any=None): checks.append({"name":name,"ok":bool(ok),"detail":detail})
    snap=safe_json(TWIN_PATH)
    if not isinstance(snap,dict): return {"version":VERSION,"passed":0,"total":1,"checks":[{"name":"snapshot_available","ok":False}]}
    task="Plan a code change to /opt/optiplex-lab/experience_loop.py and identify validation impact."
    a=build_packet(task,budget_bytes=24000); b=build_packet(task,budget_bytes=24000)
    check("deterministic_packet_digest",a["packet_digest"]==b["packet_digest"],a["packet_digest"])
    check("tier0_authority_retained",{"authority:guest-security-boundary","operational:accepted-identity"}.issubset({r["evidence_id"] for r in a["selected_evidence_records"]}))
    check("source_selected", "source:/opt/optiplex-lab/experience_loop.py" in {r["evidence_id"] for r in a["selected_evidence_records"]})
    low=build_packet(task,budget_bytes=7000)
    check("budget_never_prunes_tier0",all(r["priority_tier"]==0 for r in low["selected_evidence_records"] if r["evidence_id"].startswith(("authority:","operational:"))),low["budget"])
    stale=json.loads(json.dumps(snap))
    for n in stale.get("nodes",[]):
        if n.get("id")=="source:/opt/optiplex-lab/experience_loop.py": n["source_path"]="/tmp/gen8-context-selftest-definitely-missing.py"
    s=build_packet(task,budget_bytes=24000,snapshot_override=stale)
    check("stale_missing_fails_closed",s["fail_closed"] and any((u.get("freshness") or {}).get("state")=="missing" for u in s["uncertainties"]),s["uncertainties"][:3])
    contradiction=json.loads(json.dumps(snap)); src=next((n for n in contradiction["nodes"] if n.get("id")=="build_state:current"),None)
    if src:
        dup=json.loads(json.dumps(src)); dup["id"]="build_state:contradiction-control"; dup["generation"]="contradictory-control"; contradiction["nodes"].append(dup)
    c=build_packet("Explain lifecycle recovery build metadata.",budget_bytes=24000,snapshot_override=contradiction)
    check("contradiction_surfaced",bool(c["contradictions"]) and c["fail_closed"],c["contradictions"][:2])
    return {"version":VERSION,"passed":sum(1 for x in checks if x["ok"]),"total":len(checks),"checks":checks}


def main() -> None:
    ap=argparse.ArgumentParser(description="Gen8 deterministic provenance-backed Context Compiler")
    ap.add_argument("--selftest",action="store_true")
    sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("compile"); p.add_argument("task"); p.add_argument("--budget-bytes",type=int,default=DEFAULT_BUDGET); p.add_argument("--snapshot",default=str(TWIN_PATH)); p.add_argument("--out"); p.add_argument("--no-expand",action="store_true")
    args=ap.parse_args()
    if args.selftest:
        out=selftest(); print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if out["passed"]==out["total"] else 1)
    if args.cmd!="compile": ap.error("compile command required")
    started=time.monotonic(); packet=build_packet(args.task,budget_bytes=max(1024,args.budget_bytes),snapshot_path=pathlib.Path(args.snapshot),allow_expand=not args.no_expand); elapsed=round((time.monotonic()-started)*1000,3)
    if args.out:
        p=pathlib.Path(args.out); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"packet":packet,"compile_latency_ms":elapsed},indent=2,sort_keys=True))
    raise SystemExit(2 if packet.get("fail_closed") else 0)

if __name__=="__main__": main()
