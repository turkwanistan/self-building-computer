#!/usr/bin/env python3
"""Gen15 generic project onboarding engine.

Supports local project roots and deterministic transport manifests for projects that are
intentionally outside the Lab mount. Produces content-addressed onboarding manifests,
namespaced project Twins, task-oriented context packets, and capability-gap analysis.
"""
from __future__ import annotations
import argparse, fnmatch, hashlib, json, os, pathlib, re, stat, sys
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

def main() -> int:
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="cmd",required=True)
    p=sp.add_parser("snapshot"); p.add_argument("root"); p.add_argument("adapter"); p.add_argument("out")
    p=sp.add_parser("onboard"); p.add_argument("transport"); p.add_argument("adapter"); p.add_argument("out")
    p=sp.add_parser("verify"); p.add_argument("manifest"); p.add_argument("transport"); p.add_argument("adapter")
    p=sp.add_parser("twin"); p.add_argument("manifest"); p.add_argument("out")
    p=sp.add_parser("context"); p.add_argument("task"); p.add_argument("manifest"); p.add_argument("transport"); p.add_argument("adapter"); p.add_argument("out")
    p=sp.add_parser("gaps"); p.add_argument("manifest"); p.add_argument("adapter"); p.add_argument("out"); p.add_argument("--available",default="")
    a=ap.parse_args()
    try:
        if a.cmd=="snapshot": out=snapshot_local(pathlib.Path(a.root),load_json(a.adapter)); write_json(a.out,out)
        elif a.cmd=="onboard": out=onboard_transport(load_json(a.transport),load_json(a.adapter)); write_json(a.out,out)
        elif a.cmd=="verify": out=verify_manifest(load_json(a.manifest),load_json(a.transport),load_json(a.adapter)); print(json.dumps(out,sort_keys=True)); return 0 if out["ok"] else 2
        elif a.cmd=="twin": write_json(a.out,build_twin(load_json(a.manifest)))
        elif a.cmd=="context": write_json(a.out,compile_context(a.task,load_json(a.manifest),load_json(a.transport),load_json(a.adapter)))
        elif a.cmd=="gaps": write_json(a.out,capability_gaps(load_json(a.manifest),load_json(a.adapter),[x for x in a.available.split(",") if x]))
        return 0
    except (OnboardingError,FileNotFoundError,json.JSONDecodeError) as e:
        print(json.dumps({"ok":False,"error":str(e)},sort_keys=True),file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
