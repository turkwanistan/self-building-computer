#!/usr/bin/env python3
"""Gen15 generic project onboarding engine.

Supports local project roots and deterministic transport manifests for projects that are
intentionally outside the Lab mount. Produces content-addressed onboarding manifests,
namespaced project Twins, task-oriented context packets, and capability-gap analysis.
"""
from __future__ import annotations
import argparse, copy, fnmatch, hashlib, importlib.util, json, os, pathlib, re, stat, sys
from typing import Any

SCHEMA = "gen15.project-onboarding.v1"
TRANSPORT_SCHEMA = "gen15.project-transport.v1"
TWIN_SCHEMA = "gen15.project-twin.v1"
CONTEXT_SCHEMA = "gen15.project-context.v1"
GAPS_SCHEMA = "gen15.capability-gaps.v1"
DEFAULT_IGNORES = [".git/**", "**/__pycache__/**", "**/*.pyc", "**/.pytest_cache/**", "**/node_modules/**"]
SURPRISING_PATTERNS = [r"ignore (all|any|the) previous instructions", r"curl\s+[^\n]+\|\s*(sh|bash)", r"sudo\s+", r"disable (security|validation|checks?)"]

class OnboardingError(RuntimeError): pass

def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def digest(v: Any) -> str: return hashlib.sha256(canonical(v)).hexdigest()
def file_sha(p: pathlib.Path) -> str:
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024), b""): h.update(b)
    return h.hexdigest()

def load_json(p: str|pathlib.Path) -> dict[str,Any]: return json.loads(pathlib.Path(p).read_text())
def write_json(p: str|pathlib.Path, v: Any) -> None:
    q=pathlib.Path(p); q.parent.mkdir(parents=True, exist_ok=True); q.write_text(json.dumps(v, indent=2, sort_keys=True)+"\n")

def norm_rel(s: str) -> str:
    p=pathlib.PurePosixPath(str(s).replace("\\","/"))
    if p.is_absolute() or ".." in p.parts or not p.parts: raise OnboardingError(f"unsafe project path: {s}")
    return p.as_posix()

def anymatch(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path,p) or fnmatch.fnmatch("/"+path,p) for p in patterns)

def classify_role(path: str, adapter: dict[str,Any]) -> str:
    for rule in adapter.get("authority_rules",[]):
        if anymatch(path, rule.get("patterns",[])): return rule["role"]
    low=path.lower()
    if any(x in low for x in ("output/","artifacts/","dist/","build/","generated/")): return "generated"
    if low.endswith((".md",".toml",".yaml",".yml",".json",".py",".js",".ts",".tsx",".jsx",".sh")): return "authoritative"
    return "data"

def detect_language(path: str) -> str|None:
    ext=pathlib.PurePosixPath(path).suffix.lower()
    return {".py":"Python",".js":"JavaScript",".ts":"TypeScript",".tsx":"TypeScript",".jsx":"JavaScript",".rs":"Rust",".go":"Go",".java":"Java",".cs":"C#",".cpp":"C++",".c":"C",".sh":"Shell",".html":"HTML",".css":"CSS"}.get(ext)

def infer_frameworks(files: list[dict[str,Any]], embedded: dict[str,str]) -> list[str]:
    paths={f["path"] for f in files}; out=[]
    if "pyproject.toml" in paths: out.append("Python/pyproject")
    if "package.json" in paths: out.append("Node/package.json")
    py=embedded.get("pyproject.toml","").lower(); pkg=embedded.get("package.json","").lower()
    for token,name in [("pytest","pytest"),("librosa","librosa"),("numpy","NumPy"),("scipy","SciPy"),("fastapi","FastAPI")]:
        if token in py: out.append(name)
    for token,name in [("react","React"),("vite","Vite"),("three","Three.js")]:
        if token in pkg: out.append(name)
    return sorted(set(out))

def project_name_from_embedded(embedded: dict[str,str]) -> str|None:
    py=embedded.get("pyproject.toml","")
    m=re.search(r"(?ms)^\s*\[project\].*?^\s*name\s*=\s*[\"']([^\"']+)",py)
    if m:return m.group(1)
    pkg=embedded.get("package.json","")
    if pkg:
        try:return json.loads(pkg).get("name")
        except Exception:return None
    return None

def _validate_transport(t: dict[str,Any]) -> None:
    if t.get("schema")!=TRANSPORT_SCHEMA: raise OnboardingError("unsupported transport schema")
    if not t.get("project_id") or not t.get("declared_root"): raise OnboardingError("missing project identity/root")
    files=t.get("files")
    if not isinstance(files,list) or not files: raise OnboardingError("transport has no files")
    seen=set()
    for f in files:
        p=norm_rel(f.get("path",""))
        if p in seen: raise OnboardingError(f"duplicate transport path: {p}")
        seen.add(p)
        if not re.fullmatch(r"[0-9a-f]{64}",str(f.get("sha256",""))): raise OnboardingError(f"invalid hash: {p}")
        if int(f.get("size",-1))<0: raise OnboardingError(f"invalid size: {p}")
    emb=t.get("embedded",{})
    if not isinstance(emb,dict): raise OnboardingError("embedded must be object")
    by={f["path"]:f for f in files}
    for p,text in emb.items():
        p=norm_rel(p)
        if p not in by: raise OnboardingError(f"embedded file not inventoried: {p}")
        raw=text.encode()
        if hashlib.sha256(raw).hexdigest()!=by[p]["sha256"] or len(raw)!=by[p]["size"]:
            raise OnboardingError(f"embedded content mismatch: {p}")
    expected=t.get("transport_sha256")
    base={k:v for k,v in t.items() if k!="transport_sha256"}
    if expected and expected!=digest(base): raise OnboardingError("transport digest mismatch")

def snapshot_local(root: pathlib.Path, adapter: dict[str,Any]) -> dict[str,Any]:
    declared=str(root); root=root.resolve(strict=True)
    if not root.is_dir(): raise OnboardingError("project root is not directory")
    if adapter.get("declared_root") and pathlib.Path(adapter["declared_root"]).resolve()!=root: raise OnboardingError("conflicting project identity/root")
    ignores=DEFAULT_IGNORES+adapter.get("ignore_patterns",[])
    files=[]; embedded={}; nested=[]
    embed_patterns=adapter.get("embed_patterns",[])
    for p in sorted(root.rglob("*"), key=lambda x:x.as_posix()):
        rel=p.relative_to(root).as_posix()
        if anymatch(rel,ignores): continue
        if p.is_symlink():
            target=p.resolve(strict=False)
            try: target.relative_to(root)
            except ValueError: raise OnboardingError(f"symlink path escape: {rel}")
        if p.is_dir():
            if rel!=".git" and (p/".git").exists(): nested.append(rel)
            continue
        if not p.is_file(): continue
        st=p.stat(); rec={"path":rel,"sha256":file_sha(p),"size":st.st_size,"executable":bool(st.st_mode & stat.S_IXUSR)}
        files.append(rec)
        if anymatch(rel,embed_patterns) and st.st_size<=adapter.get("max_embed_bytes",131072):
            try: embedded[rel]=p.read_text()
            except UnicodeDecodeError: pass
    if nested and not adapter.get("allow_nested_projects",False): raise OnboardingError("nested/conflicting repo root: "+",".join(nested))
    t={"schema":TRANSPORT_SCHEMA,"project_id":adapter.get("project_id") or root.name,"declared_root":declared,"resolved_root":str(root),"files":files,"embedded":embedded,"producer":"project_onboarding.snapshot_local"}
    t["transport_sha256"]=digest(t)
    return t

def _surprising(embedded: dict[str,str]) -> list[dict[str,str]]:
    hits=[]
    for p,text in embedded.items():
        for pat in SURPRISING_PATTERNS:
            if re.search(pat,text,re.I): hits.append({"path":p,"pattern":pat})
    return hits

def onboard_transport(t: dict[str,Any], adapter: dict[str,Any]) -> dict[str,Any]:
    _validate_transport(t)
    if adapter.get("project_id") and adapter["project_id"]!=t["project_id"]: raise OnboardingError("conflicting project identity")
    files=[]; lang={}; roles={}; executable=[]
    executable_records=[]
    for f in t["files"]:
        p=f["path"]; role=classify_role(p,adapter)
        heuristic_generated=any(x in p.lower() for x in ("output/","artifacts/","dist/","build/","generated/"))
        if heuristic_generated and role in ("authoritative","data"):
            raise OnboardingError("generated file claiming authority: "+p)
        x={**f,"role":role}; files.append(x); roles[role]=roles.get(role,0)+1
        lg=detect_language(p)
        if lg:lang[lg]=lang.get(lg,0)+1
        if f.get("executable"):
            executable.append(p); executable_records.append({"path":p,"role":role,"authority_supported":role=="authoritative"})
    embedded=t.get("embedded",{})
    inferred=project_name_from_embedded(embedded)
    aliases=set(adapter.get("project_name_aliases",[])+[t["project_id"]])
    if inferred and inferred not in aliases and adapter.get("enforce_embedded_identity",True): raise OnboardingError(f"conflicting embedded project identity: {inferred}")
    surprising=_surprising(embedded)
    entrypoints=[norm_rel(x) for x in adapter.get("entrypoints",[])]
    known={f["path"] for f in files}
    missing_entry=[p for p in entrypoints if p not in known]
    if missing_entry: raise OnboardingError("missing authoritative entrypoint: "+",".join(missing_entry))
    for p in executable:
        if classify_role(p,adapter)=="generated" and p in entrypoints: raise OnboardingError("unsupported executable authority: "+p)
    deps=[p for p in ("pyproject.toml","requirements.txt","package.json","package-lock.json","Cargo.toml","go.mod") if p in known]
    important=sorted(set([p for p in adapter.get("important_files",[]) if p in known]+deps+entrypoints))
    auth_inputs=[{"path":f["path"],"sha256":f["sha256"],"size":f["size"],"role":f["role"]} for f in files if f["role"] in ("authoritative","data")]
    manifest={
      "schema":SCHEMA,"project_id":t["project_id"],"project_name":inferred or t["project_id"],"declared_root":t["declared_root"],"transport_sha256":t.get("transport_sha256"),
      "languages":sorted(lang.items(),key=lambda x:(-x[1],x[0])),"frameworks":infer_frameworks(files,embedded),"important_files":important,
      "entrypoints":entrypoints,"tests":adapter.get("tests",[]),"build_commands":adapter.get("build_commands",[]),"dependency_manifests":deps,
      "data_locations":adapter.get("data_locations",[]),"artifact_locations":adapter.get("artifact_locations",[]),"authority_hierarchy":adapter.get("authority_hierarchy",[]),
      "external_interfaces":adapter.get("external_interfaces",[]),"safety_constraints":adapter.get("safety_constraints",[]),"role_counts":roles,
      "surprising_instructions":surprising,"executable_files":sorted(executable_records,key=lambda x:x["path"]),
      "unsupported_executable_authority":[x for x in sorted(executable_records,key=lambda x:x["path"]) if not x["authority_supported"]],
      "authoritative_inputs":auth_inputs,"file_count":len(files),"total_bytes":sum(f["size"] for f in files),
      "embedded_paths":sorted(embedded),"adapter_sha256":digest(adapter)
    }
    manifest["manifest_sha256"]=digest(manifest)
    return manifest

def verify_manifest(manifest: dict[str,Any], t: dict[str,Any], adapter: dict[str,Any]) -> dict[str,Any]:
    fresh=onboard_transport(t,adapter)
    ok=(manifest.get("manifest_sha256")==fresh.get("manifest_sha256") and canonical(manifest)==canonical(fresh))
    return {"ok":ok,"expected":manifest.get("manifest_sha256"),"observed":fresh.get("manifest_sha256"),"reason":None if ok else "stale project model"}

def build_twin(manifest: dict[str,Any]) -> dict[str,Any]:
    ns=f"project:{manifest['project_id']}"; nodes=[]; edges=[]
    nodes.append({"id":ns,"kind":"project","name":manifest["project_name"]})
    for f in manifest["authoritative_inputs"]:
        fid=f"{ns}:file:{f['path']}"; nodes.append({"id":fid,"kind":"file","path":f["path"],"sha256":f["sha256"],"role":f["role"]}); edges.append({"from":ns,"to":fid,"type":"contains"})
    for ep in manifest["entrypoints"]:
        eid=f"{ns}:entrypoint:{ep}"; nodes.append({"id":eid,"kind":"entrypoint","path":ep}); edges.append({"from":ns,"to":eid,"type":"runs"}); edges.append({"from":eid,"to":f"{ns}:file:{ep}","type":"implemented_by"})
    twin={"schema":TWIN_SCHEMA,"namespace":ns,"manifest_sha256":manifest["manifest_sha256"],"nodes":sorted(nodes,key=lambda x:x["id"]),"edges":sorted(edges,key=lambda x:(x["from"],x["to"],x["type"]))}
    twin["twin_sha256"]=digest(twin); return twin

def route_task(task: str, adapter: dict[str,Any]) -> dict[str,Any]:
    low=task.lower(); scored=[]
    for name,spec in adapter.get("task_profiles",{}).items():
        score=sum(2 for k in spec.get("keywords",[]) if k.lower() in low)
        if name.lower() in low: score+=1
        scored.append((score,name,spec))
    scored.sort(key=lambda x:(-x[0],x[1]));
    if not scored or scored[0][0]<=0: raise OnboardingError("task intent/authority route is ambiguous")
    score,name,spec=scored[0]
    if len(scored)>1 and scored[1][0]==score: raise OnboardingError("task intent/authority route is ambiguous")
    return {"intent":name,"score":score,"required_paths":[norm_rel(p) for p in spec.get("required_paths",[])],"optional_patterns":spec.get("optional_patterns",[]),"authority":spec.get("authority","project")}

def compile_context(task: str, manifest: dict[str,Any], t: dict[str,Any], adapter: dict[str,Any]) -> dict[str,Any]:
    v=verify_manifest(manifest,t,adapter)
    if not v["ok"]: raise OnboardingError("stale project model")
    route=route_task(task,adapter); by={f["path"]:f for f in manifest["authoritative_inputs"]}; emb=t.get("embedded",{})
    missing=[p for p in route["required_paths"] if p not in by]
    if missing: raise OnboardingError("missing authoritative inputs: "+",".join(missing))
    selected=set(route["required_paths"])
    for p in by:
        if anymatch(p,route["optional_patterns"]): selected.add(p)
    selected=sorted(selected)
    required_recall=(sum(p in selected for p in route["required_paths"])/len(route["required_paths"])) if route["required_paths"] else 1.0
    total=sum(x["size"] for x in manifest["authoritative_inputs"]); chosen=sum(by[p]["size"] for p in selected)
    evidence=[]
    for p in selected:
        x=by[p]; evidence.append({"path":p,"sha256":x["sha256"],"size":x["size"],"role":x["role"],"embedded":p in emb,"content":emb.get(p)})
    packet={"schema":CONTEXT_SCHEMA,"task":task,"route":route,"project_manifest_sha256":manifest["manifest_sha256"],"evidence_epoch":{"transport_sha256":t.get("transport_sha256"),"manifest_sha256":manifest["manifest_sha256"]},"evidence":evidence,"metrics":{"required_evidence_recall":required_recall,"critical_false_negatives":0 if required_recall==1 else len(missing),"authoritative_bytes":total,"selected_bytes":chosen,"context_reduction":0.0 if total==0 else 1-(chosen/total)}}
    packet["packet_sha256"]=digest(packet); return packet

def capability_gaps(manifest: dict[str,Any], adapter: dict[str,Any], available: list[str]) -> dict[str,Any]:
    av=set(available); rows=[]
    rank=0
    for item in sorted(adapter.get("capability_requirements",[]), key=lambda x:(-float(x.get("utility",0)),x["id"])):
        cid=item["id"]; status="already_available" if cid in av else item.get("status_if_absent","missing_and_valuable")
        if status=="missing_and_valuable": rank+=1
        rows.append({"id":cid,"status":status,"utility":float(item.get("utility",0)),"reason":item.get("reason",""),"missing_rank":rank if status=="missing_and_valuable" else None})
    out={"schema":GAPS_SCHEMA,"project_id":manifest["project_id"],"manifest_sha256":manifest["manifest_sha256"],"available_capabilities":sorted(av),"capabilities":rows}
    out["gaps_sha256"]=digest(out); return out


PACK_SCHEMA = "gen16.project-capability-pack.v1"
ANALYSIS_SCHEMA = "gen16.project-analysis.v1"
CLASSIFICATION_SCHEMA = "gen16.capability-classification.v1"
BRIDGE_VERSION = "gen16-project-context-compose-r1"
CAPABILITY_STATES = {"AVAILABLE", "WEAK_NEEDS_SPECIALIZATION", "MISSING_VALUABLE", "UNNECESSARY"}
PACK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
DEFAULT_EPOCH_PATH = pathlib.Path(os.environ.get("OPTIPLEX_EVIDENCE_EPOCH_PATH", "/opt/optiplex-lab/evidence_epoch.py"))


def _pack_core(pack: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in pack.items() if k != "pack_sha256"}


def seal_pack(pack: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(pack)
    out.pop("pack_sha256", None)
    validate_pack(out, require_digest=False)
    out["pack_sha256"] = digest(out)
    return out


def _safe_resource_name(value: str) -> str:
    name = str(value)
    if not PACK_ID_RE.fullmatch(name) or "/" in name or "\\" in name or name in {".", ".."}:
        raise OnboardingError(f"unsafe pack resource name: {value}")
    return name


def _resource_refs(pack: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for cap in pack.get("capabilities", []):
        ev = cap.get("evaluator")
        if not ev:
            continue
        if not isinstance(ev, dict):
            raise OnboardingError(f"capability evaluator must be object: {cap.get('id')}")
        resource = _safe_resource_name(ev.get("resource", ""))
        expected = str(ev.get("sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise OnboardingError(f"invalid evaluator resource hash: {cap.get('id')}")
        function = str(ev.get("function", ""))
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", function):
            raise OnboardingError(f"invalid evaluator function: {cap.get('id')}")
        refs.append({"resource": resource, "sha256": expected, "function": function, "capability_id": str(cap.get("id"))})
    return sorted(refs, key=lambda x: (x["resource"], x["function"], x["capability_id"]))


def verify_pack_resources(pack: dict[str, Any], resource_catalog: dict[str, str] | None) -> dict[str, Any]:
    refs = _resource_refs(pack)
    if not refs:
        return {"ok": True, "required": 0, "verified": 0, "resources": []}
    if not isinstance(resource_catalog, dict):
        raise OnboardingError("pack evaluator resources require a resource catalog")
    results = []
    for ref in refs:
        path_text = resource_catalog.get(ref["resource"])
        if not isinstance(path_text, str) or not path_text:
            raise OnboardingError(f"missing pack resource: {ref['resource']}")
        p = pathlib.Path(path_text).resolve(strict=True)
        if not p.is_file():
            raise OnboardingError(f"pack resource is not a file: {ref['resource']}")
        observed = file_sha(p)
        if observed != ref["sha256"]:
            raise OnboardingError(f"pack resource hash mismatch: {ref['resource']}")
        results.append({**ref, "observed_sha256": observed})
    return {"ok": True, "required": len(refs), "verified": len(results), "resources": results}


def validate_pack(pack: dict[str, Any], *, resource_catalog: dict[str, str] | None = None, require_digest: bool = True, verify_resources: bool = False) -> dict[str, Any]:
    if not isinstance(pack, dict):
        raise OnboardingError("capability pack must be an object")
    if pack.get("schema") != PACK_SCHEMA:
        raise OnboardingError("unsupported project capability pack schema")
    pack_id = str(pack.get("pack_id", "")); version = str(pack.get("version", ""))
    if not PACK_ID_RE.fullmatch(pack_id): raise OnboardingError("invalid pack_id")
    if not PACK_ID_RE.fullmatch(version): raise OnboardingError("invalid pack version")
    project = pack.get("project")
    if not isinstance(project, dict) or not project.get("project_id"):
        raise OnboardingError("pack requires project adapter")
    capabilities = pack.get("capabilities")
    if not isinstance(capabilities, list): raise OnboardingError("pack capabilities must be a list")
    seen: set[str] = set()
    for cap in capabilities:
        if not isinstance(cap, dict): raise OnboardingError("pack capability must be an object")
        cid = str(cap.get("id", ""))
        if not PACK_ID_RE.fullmatch(cid): raise OnboardingError("invalid capability requirement id")
        if cid in seen: raise OnboardingError(f"duplicate capability requirement: {cid}")
        seen.add(cid)
        if not isinstance(cap.get("purpose"), str) or not cap["purpose"].strip(): raise OnboardingError(f"capability purpose missing: {cid}")
        utility = float(cap.get("utility", -1))
        if not 0 <= utility <= 1: raise OnboardingError(f"capability utility out of range: {cid}")
        applicability = cap.get("applicability", [])
        if not isinstance(applicability, list) or not all(isinstance(x, str) and x for x in applicability): raise OnboardingError(f"invalid applicability: {cid}")
        provider = cap.get("provider", "forge")
        if provider not in {"forge", "platform"}: raise OnboardingError(f"invalid provider: {cid}")
        necessity = cap.get("necessity", "valuable")
        if necessity not in {"required", "valuable", "specialize", "optional", "unnecessary"}: raise OnboardingError(f"invalid necessity: {cid}")
        for key in ("authority_requirements", "runtime_dependencies", "task_intents"):
            if key in cap and (not isinstance(cap[key], list) or not all(isinstance(x, str) and x for x in cap[key])):
                raise OnboardingError(f"{key} must be list[str]: {cid}")
        forge = cap.get("forge") or {}
        if not isinstance(forge, dict): raise OnboardingError(f"forge declaration must be object: {cid}")
        expected_hash = forge.get("expected_content_hash")
        if expected_hash is not None and not re.fullmatch(r"[0-9a-f]{64}", str(expected_hash)):
            raise OnboardingError(f"invalid capability content hash: {cid}")
        if provider == "platform" and cap.get("platform_status") not in CAPABILITY_STATES:
            raise OnboardingError(f"platform capability requires explicit platform_status: {cid}")
    prov = pack.get("provenance")
    if not isinstance(prov, dict) or not prov.get("creator") or not prov.get("source_generation"):
        raise OnboardingError("pack provenance requires creator and source_generation")
    policy = pack.get("classification_policy", {})
    if not isinstance(policy, dict): raise OnboardingError("classification_policy must be object")
    threshold = float(policy.get("valuable_utility_min", 0.5))
    if not 0 <= threshold <= 1: raise OnboardingError("valuable_utility_min out of range")
    observed = digest(_pack_core(pack))
    declared = pack.get("pack_sha256")
    if require_digest and declared != observed:
        raise OnboardingError("project capability pack digest mismatch")
    refs = _resource_refs(pack)  # structural validation is always required
    if verify_resources:
        resources = verify_pack_resources(pack, resource_catalog)
    else:
        resources = {"ok": True, "required": len(refs), "verified": 0, "resources": refs}
    return {"ok": True, "pack_id": pack_id, "version": version, "pack_sha256": observed, "capabilities": len(capabilities), "resources": resources}


def load_pack(path: str | pathlib.Path, *, resource_catalog: dict[str, str] | None = None) -> dict[str, Any]:
    pack = load_json(path)
    validate_pack(pack, resource_catalog=resource_catalog, verify_resources=resource_catalog is not None)
    return pack


def adapter_from_pack(pack: dict[str, Any]) -> dict[str, Any]:
    validate_pack(pack, require_digest=bool(pack.get("pack_sha256")))
    return copy.deepcopy(pack["project"])


def forge_registry_records(registry: dict[str, Any]) -> list[dict[str, Any]]:
    caps = registry.get("capabilities", {}) if isinstance(registry, dict) else {}
    if not isinstance(caps, dict): raise OnboardingError("invalid Forge registry")
    return sorted(({**rec, "content_hash": h} for h, rec in caps.items() if isinstance(rec, dict)), key=lambda x: (str(x.get("name", "")), str(x.get("content_hash", ""))))


def _forge_plan(requirement: dict[str, Any]) -> dict[str, Any]:
    forge = requirement.get("forge") or {}
    desired = str(forge.get("desired_name") or requirement["id"])
    gap = {
        "desired_name": desired,
        "purpose": requirement["purpose"],
        "applicability": sorted(set(requirement.get("applicability", []))),
        "authority_requirements": sorted(set(requirement.get("authority_requirements", []))),
        "runtime_dependencies": sorted(set(requirement.get("runtime_dependencies", []))),
    }
    return {
        "gap": gap,
        "gates": ["search", "open_gap", "author", "seal", "evaluate", "real_task_evidence", "govern"],
        "promotion_is_automatic": False,
        "governor": "existing Capability Forge promotion governor",
    }


def classify_capabilities(manifest: dict[str, Any], pack: dict[str, Any], available_records: list[dict[str, Any]], task: str | None = None) -> dict[str, Any]:
    validate_pack(pack, require_digest=bool(pack.get("pack_sha256")))
    if manifest.get("project_id") != pack["project"].get("project_id"):
        raise OnboardingError("pack/project manifest identity mismatch")
    route = route_task(task, pack["project"]) if task else None
    records = [r for r in available_records if isinstance(r, dict)]
    threshold = float((pack.get("classification_policy") or {}).get("valuable_utility_min", 0.5))
    rows = []
    for req in sorted(pack.get("capabilities", []), key=lambda x: (-float(x.get("utility", 0)), x["id"])):
        cid = req["id"]; necessity = req.get("necessity", "valuable"); provider = req.get("provider", "forge")
        routed_out = bool(route and req.get("task_intents") and route["intent"] not in req.get("task_intents", []))
        status: str; reason: str; selected = None
        if necessity == "unnecessary" or routed_out:
            status, reason = "UNNECESSARY", "not required for this routed task" if routed_out else "pack marks capability unnecessary"
        elif provider == "platform":
            status = str(req.get("platform_status")); reason = str(req.get("platform_reason") or "declared platform capability state")
        else:
            forge = req.get("forge") or {}; desired = str(forge.get("desired_name") or cid); pinned = forge.get("expected_content_hash")
            same = [r for r in records if r.get("name") == desired and r.get("state") not in {"REJECTED", "EXPIRED", "SUPERSEDED"}]
            exact = [r for r in same if pinned is None or r.get("content_hash") == pinned]
            # CHECK:promoted_exact_availability
            promoted = [r for r in exact if r.get("state") == "PROMOTED"]
            if promoted:
                selected = sorted(promoted, key=lambda r: str(r.get("content_hash", "")))[0]
                status, reason = "AVAILABLE", "exact promoted Forge capability"
            elif same:
                selected = sorted(same, key=lambda r: (r.get("state") != "CANDIDATE", str(r.get("content_hash", ""))))[0]
                status, reason = "WEAK_NEEDS_SPECIALIZATION", "matching Forge capability is unpromoted or content identity differs"
            elif necessity in {"required", "valuable", "specialize"} and float(req.get("utility", 0)) >= threshold:
                status, reason = "MISSING_VALUABLE", "no sufficient Forge capability found"
            else:
                status, reason = "UNNECESSARY", "utility below pack capability-work threshold"
        if status not in CAPABILITY_STATES: raise OnboardingError(f"invalid classification state for {cid}: {status}")
        forge_plan = _forge_plan(req) if status in {"MISSING_VALUABLE", "WEAK_NEEDS_SPECIALIZATION"} and req.get("allow_forge", provider == "forge") else None
        if status == "MISSING_VALUABLE" and forge_plan is None:
            raise OnboardingError(f"missing valuable capability has no Forge plan: {cid}")
        rows.append({
            "id": cid, "status": status, "provider": provider, "utility": float(req.get("utility", 0)), "reason": reason,
            "selected": {k: selected.get(k) for k in ("name", "content_hash", "state") if k in selected} if selected else None,
            "authority_requirements": sorted(req.get("authority_requirements", [])), "runtime_dependencies": sorted(req.get("runtime_dependencies", [])),
            "forge_plan": forge_plan,
        })
    out = {"schema": CLASSIFICATION_SCHEMA, "project_id": manifest["project_id"], "manifest_sha256": manifest["manifest_sha256"], "pack_sha256": pack.get("pack_sha256") or digest(_pack_core(pack)), "task": task, "route": route, "capabilities": rows}
    out["classification_sha256"] = digest(out)
    return out


def _load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None: raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def compose_platform_context(task: str, project_packet_path: str, *, evidence_epoch_path: str | pathlib.Path | None = None) -> dict[str, Any]:
    pp = pathlib.Path(project_packet_path).resolve()
    if not pp.is_file(): raise RuntimeError("project context packet missing")
    project = json.loads(pp.read_text(encoding="utf-8"))
    if project.get("schema") != CONTEXT_SCHEMA or project.get("task") != task: raise RuntimeError("project context/task binding mismatch")
    packet_sha = digest({k: v for k, v in project.items() if k != "packet_sha256"})
    if packet_sha != project.get("packet_sha256"): raise RuntimeError("project context digest mismatch")
    ep_path = pathlib.Path(evidence_epoch_path) if evidence_epoch_path else DEFAULT_EPOCH_PATH
    ep = _load_module(ep_path, "gen16_project_epoch_bridge")
    begun = ep.begin_epoch(task=task, extra_paths=[str(pp)]); epoch_id = begun["epoch_id"]
    compiled = ep.compile_minimized(epoch_id, task, budget_bytes=24000)
    verification = ep.verify_epoch(epoch_id); finalized = ep.finalize_epoch(epoch_id)
    if not compiled.get("ok") or compiled.get("fail_closed") or not verification.get("ok") or not finalized.get("ok"):
        raise RuntimeError("Gen8-Gen11 epoch composition failed closed")
    route = compiled.get("routing_proof") or {}; minimized = compiled.get("minimized_packet") or {}; budget = minimized.get("budget") or {}
    material = {
        "version": BRIDGE_VERSION, "task": task, "project_context_path": str(pp), "project_packet_sha256": project["packet_sha256"],
        "project_manifest_sha256": project["project_manifest_sha256"], "project_evidence_epoch": project["evidence_epoch"],
        "gen10_epoch_id": epoch_id, "gen10_epoch_digest": begun["epoch_digest"], "gen10_transaction_digest": compiled["transaction_digest"],
        "gen11_routing_digest": compiled["routing_digest"], "gen11_primary_intent": route.get("detected_primary_intent"),
        "gen11_required_authority_classes": route.get("required_authority_classes") or [],
        "gen8_compiler_packet_digest": (compiled.get("compiler_packet") or {}).get("packet_digest"), "gen9_optimizer_packet_digest": minimized.get("packet_digest"),
        "gen9_context_payload_bytes": budget.get("context_payload_bytes"), "gen9_context_payload_reduction": budget.get("context_payload_reduction"),
        "domain_required_evidence_recall": (project.get("metrics") or {}).get("required_evidence_recall"), "domain_context_reduction": (project.get("metrics") or {}).get("context_reduction"),
        "domain_selected_bytes": (project.get("metrics") or {}).get("selected_bytes"), "domain_route": project.get("route"),
        "epoch_verification_ok": verification.get("ok"), "epoch_finalized_state": finalized.get("state"), "fail_closed": False,
    }
    material["composition_sha256"] = digest(material); return material


def analyze_project(transport: dict[str, Any], pack: dict[str, Any], available_records: list[dict[str, Any]], task: str, *, resource_catalog: dict[str, str] | None = None) -> dict[str, Any]:
    pack_check = validate_pack(pack, resource_catalog=resource_catalog, verify_resources=True)
    adapter = copy.deepcopy(pack["project"])
    manifest = onboard_transport(transport, adapter); twin = build_twin(manifest); context = compile_context(task, manifest, transport, adapter)
    classification = classify_capabilities(manifest, pack, available_records, task)
    out = {
        "schema": ANALYSIS_SCHEMA, "pack": pack_check, "project_manifest": manifest, "project_twin": twin, "task_context": context,
        "capability_classification": classification,
        "operator_path": ["validate_pack", "analyze_project", "forge_only_when_needed", "evaluate_and_govern"],
        "automatic_promotion": False,
    }
    out["analysis_sha256"] = digest(out); return out

def main() -> int:
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    p=sp.add_parser("snapshot"); p.add_argument("root"); p.add_argument("adapter"); p.add_argument("out")
    p=sp.add_parser("onboard"); p.add_argument("transport"); p.add_argument("adapter"); p.add_argument("out")
    p=sp.add_parser("verify"); p.add_argument("manifest"); p.add_argument("transport"); p.add_argument("adapter")
    p=sp.add_parser("twin"); p.add_argument("manifest"); p.add_argument("out")
    p=sp.add_parser("context"); p.add_argument("task"); p.add_argument("manifest"); p.add_argument("transport"); p.add_argument("adapter"); p.add_argument("out")
    p=sp.add_parser("gaps"); p.add_argument("manifest"); p.add_argument("adapter"); p.add_argument("out"); p.add_argument("--available",default="")
    p=sp.add_parser("pack-verify"); p.add_argument("pack"); p.add_argument("--resource-catalog")
    p=sp.add_parser("analyze"); p.add_argument("transport"); p.add_argument("pack"); p.add_argument("task"); p.add_argument("out"); p.add_argument("--registry"); p.add_argument("--resource-catalog")
    p=sp.add_parser("compose"); p.add_argument("task"); p.add_argument("project_context")
    a=ap.parse_args()
    try:
        if a.cmd=="snapshot": out=snapshot_local(pathlib.Path(a.root),load_json(a.adapter)); write_json(a.out,out)
        elif a.cmd=="onboard": out=onboard_transport(load_json(a.transport),load_json(a.adapter)); write_json(a.out,out)
        elif a.cmd=="verify": out=verify_manifest(load_json(a.manifest),load_json(a.transport),load_json(a.adapter)); print(json.dumps(out,sort_keys=True)); return 0 if out["ok"] else 2
        elif a.cmd=="twin": write_json(a.out,build_twin(load_json(a.manifest)))
        elif a.cmd=="context": write_json(a.out,compile_context(a.task,load_json(a.manifest),load_json(a.transport),load_json(a.adapter)))
        elif a.cmd=="gaps": write_json(a.out,capability_gaps(load_json(a.manifest),load_json(a.adapter),[x for x in a.available.split(",") if x]))
        elif a.cmd=="pack-verify":
            rc=load_json(a.resource_catalog) if a.resource_catalog else None
            print(json.dumps(validate_pack(load_json(a.pack),resource_catalog=rc,verify_resources=rc is not None),indent=2,sort_keys=True))
        elif a.cmd=="analyze":
            registry=load_json(a.registry) if a.registry else {"capabilities":{}}
            rc=load_json(a.resource_catalog) if a.resource_catalog else None
            write_json(a.out,analyze_project(load_json(a.transport),load_json(a.pack),forge_registry_records(registry),a.task,resource_catalog=rc))
        elif a.cmd=="compose": print(json.dumps(compose_platform_context(a.task,a.project_context),indent=2,sort_keys=True))
        return 0
    except (OnboardingError,FileNotFoundError,json.JSONDecodeError,RuntimeError) as e:
        print(json.dumps({"ok":False,"error":str(e)},sort_keys=True),file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
