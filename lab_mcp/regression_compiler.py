#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

VERSION="gen6-failure-regression-r1"
SCHEMA_VERSION="failure-regression-v1"
ROOT=pathlib.Path(os.environ.get("OPTIPLEX_REGRESSION_ROOT","/var/lib/optiplex-lab/regressions"))
OBJECTS=ROOT/"objects"
REGISTRY=ROOT/"registry.json"
PROVENANCE=ROOT/"provenance.jsonl"
FORGE_PATH=pathlib.Path(os.environ.get("OPTIPLEX_FORGE_PATH","/opt/optiplex-lab/capability_forge.py"))
FORGE_ROOT=pathlib.Path(os.environ.get("OPTIPLEX_FORGE_ROOT","/var/lib/optiplex-lab/capabilities"))
FORGE_REGISTRY=FORGE_ROOT/"registry.json"
LIFECYCLE={"CANDIDATE","ACTIVE","RETIRED"}

class RegressionError(RuntimeError): pass

def utc()->str: return datetime.now(timezone.utc).isoformat()
def canonical_bytes(v:Any)->bytes: return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def sha_bytes(v:bytes)->str: return hashlib.sha256(v).hexdigest()
def sha_json(v:Any)->str: return sha_bytes(canonical_bytes(v))

def safe_write_json(path:pathlib.Path,value:Any)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+f".tmp-{uuid.uuid4().hex[:8]}"); tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); tmp.replace(path)

def append_jsonl(path:pathlib.Path,value:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as fh: fh.write(json.dumps(value,sort_keys=True,separators=(",",":"))+"\n")

def init_root()->None:
    ROOT.mkdir(parents=True,exist_ok=True); OBJECTS.mkdir(parents=True,exist_ok=True)
    if not REGISTRY.exists(): safe_write_json(REGISTRY,{"version":VERSION,"regressions":{}})

def load_registry()->dict[str,Any]:
    init_root()
    try:v=json.loads(REGISTRY.read_text())
    except Exception as exc: raise RegressionError(f"regression registry unreadable: {exc}")
    if not isinstance(v,dict) or not isinstance(v.get("regressions"),dict): raise RegressionError("regression registry malformed")
    return v

def save_registry(reg:dict[str,Any])->None: reg["version"]=VERSION; safe_write_json(REGISTRY,reg)

def _forge_registry()->dict[str,Any]:
    try:v=json.loads(FORGE_REGISTRY.read_text())
    except Exception as exc: raise RegressionError(f"Forge registry unavailable: {exc}")
    caps=v.get("capabilities") or {}
    if not isinstance(caps,dict): raise RegressionError("Forge registry malformed")
    return caps

def _load_forge():
    spec=importlib.util.spec_from_file_location(f"forge_for_regression_{uuid.uuid4().hex}",FORGE_PATH)
    if spec is None or spec.loader is None: raise RegressionError("cannot load Forge")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def _oracle_pass(result:dict[str,Any],fixture:dict[str,Any])->bool:
    oracle=fixture.get("oracle") or {}
    if oracle.get("expect_error") is True: return not bool(result.get("ok"))
    return bool(result.get("ok")) and result.get("output")==oracle.get("expected")

def _selector_matches(record:dict[str,Any],selector:dict[str,Any])->bool:
    name=selector.get("name")
    if name and record.get("name")!=name: return False
    required=set(selector.get("applicability_all") or [])
    if required and not required.issubset(set(record.get("applicability") or [])): return False
    evaluator=selector.get("evaluator_hash")
    if evaluator and record.get("evaluator_hash")!=evaluator: return False
    return True

def _run_fixture(fixture:dict[str,Any],invoke_fn:Callable[[Any],dict[str,Any]])->dict[str,Any]:
    t0=time.monotonic()
    if fixture.get("fixture_type")!="capability_io": return {"ok":False,"supported":False,"reason":"non-replayable fixture type","duration_ms":round((time.monotonic()-t0)*1000,3)}
    result=invoke_fn(fixture.get("input"))
    passed=_oracle_pass(result,fixture)
    return {"ok":passed,"supported":True,"observed_ok":bool(result.get("ok")),"phase":result.get("phase"),"run_id":result.get("run_id"),"duration_ms":round((time.monotonic()-t0)*1000,3)}

def _store_fixture(fixture:dict[str,Any],state:str)->tuple[str,dict[str,Any]]:
    if state not in LIFECYCLE: raise RegressionError("invalid regression lifecycle")
    fixture={**fixture,"schema_version":SCHEMA_VERSION,"compiler_version":VERSION}
    h=sha_json(fixture); path=OBJECTS/f"{h}.json"
    if not path.exists(): safe_write_json(path,fixture)
    reg=load_registry(); rec=reg["regressions"].get(h)
    if not isinstance(rec,dict):
        rec={"regression_hash":h,"state":state,"created_at":utc(),"object":str(path),"selector":fixture.get("selector"),"known_bad_hash":fixture.get("known_bad_hash"),"known_good_hash":fixture.get("known_good_hash"),"failure_evidence":fixture.get("failure_evidence"),"replay_count":0,"failure_count":0}
        reg["regressions"][h]=rec; save_registry(reg)
    return h,rec

def _evaluation_failure_case(rec:dict[str,Any],contract:dict[str,Any],case_name:str|None)->dict[str,Any]|None:
    cases=((contract.get("evaluation") or {}).get("cases") or [])
    if case_name:
        for c in cases:
            if c.get("name")==case_name: return c
        raise RegressionError(f"case not found: {case_name}")
    last=rec.get("last_evaluation") or {}; path=pathlib.Path(str(last.get("result_path") or ""))
    if path.exists():
        try:
            result=json.loads(path.read_text()); failed=[c for c in result.get("cases",[]) if not c.get("passed")]
            if failed:
                failed_name=failed[0].get("name")
                for c in cases:
                    if c.get("name")==failed_name: return c
        except Exception: pass
    return cases[0] if cases else None

def _candidate_input_reductions(value:Any):
    if isinstance(value,dict):
        for k in list(value):
            c=dict(value); c.pop(k,None); yield c,f"remove-key:{k}"
    if isinstance(value,list):
        for i in range(len(value)-1,-1,-1): yield value[:i],f"truncate-list:{i}"

def compile_capability_failure(failed_hash:str,*,known_good_hash:str|None=None,case_name:str|None=None,lineage_name:str|None=None)->dict[str,Any]:
    caps=_forge_registry(); bad=caps.get(failed_hash)
    if not isinstance(bad,dict): raise RegressionError(f"failed capability not found: {failed_hash}")
    bad_obj=pathlib.Path(str(bad.get("object") or "")); contract_path=bad_obj/"capability.json"
    if not contract_path.exists():
        fixture={"fixture_type":"nonreplayable","selector":{"name":lineage_name or bad.get("name")},"known_bad_hash":failed_hash,"known_good_hash":known_good_hash,"failure_evidence":{"reason":"capability object unavailable","state":bad.get("state"),"evaluator_hash":bad.get("evaluator_hash")},"uncertainty":"No immutable capability object remains; retained as candidate evidence only."}
        h,_=_store_fixture(fixture,"CANDIDATE"); return {"ok":True,"regression_hash":h,"state":"CANDIDATE","reason":"nonreplayable"}
    contract=json.loads(contract_path.read_text())
    case=_evaluation_failure_case(bad,contract,case_name)
    if not case:
        fixture={"fixture_type":"nonreplayable","selector":{"name":lineage_name or bad.get("name")},"known_bad_hash":failed_hash,"known_good_hash":known_good_hash,"failure_evidence":{"reason":"no evaluation case available","state":bad.get("state"),"evaluator_hash":bad.get("evaluator_hash")},"uncertainty":"Failure cannot be converted to an executable oracle automatically."}
        h,_=_store_fixture(fixture,"CANDIDATE"); return {"ok":True,"regression_hash":h,"state":"CANDIDATE","reason":"no-case"}
    oracle={"expect_error":True} if case.get("expect_error") is True else {"expected":case.get("expected")}
    fixture={"fixture_type":"capability_io","selector":{"name":lineage_name or bad.get("name")},"input":case.get("input"),"oracle":oracle,"source_case":case.get("name"),"known_bad_hash":failed_hash,"known_good_hash":known_good_hash,"failure_evidence":{"capability_state":bad.get("state"),"evaluator_hash":bad.get("evaluator_hash"),"evaluation_result":(bad.get("last_evaluation") or {}).get("result_path"),"source_hashes":bad.get("source_hashes")},"minimization":{"method":"greedy-structure-reduction","attempted":0,"accepted":0,"uncertainty":"Best-effort structural minimization only; causal minimality is not claimed."}}
    forge=_load_forge()
    def invoke_hash(h:str,input_value:Any)->dict[str,Any]: return forge.invoke_raw(h,input_value,mutate_registry=False)
    bad_result=invoke_hash(failed_hash,fixture["input"]); known_bad_detected=not _oracle_pass(bad_result,fixture)
    if not known_bad_detected:
        # If the chosen case no longer reproduces, retain evidence but do not activate it.
        fixture["uncertainty"]="Selected historical case did not reproduce against known-bad object at compile time."
    good_pass=None
    if known_good_hash:
        if known_good_hash not in caps: raise RegressionError(f"known-good capability not found: {known_good_hash}")
        good_result=invoke_hash(known_good_hash,fixture["input"]); good_pass=_oracle_pass(good_result,fixture)
    # Greedy minimization must preserve bad detection and known-good pass when a good reference exists.
    current=fixture["input"]
    for candidate,op in list(_candidate_input_reductions(current)):
        fixture["minimization"]["attempted"]+=1
        bad_r=invoke_hash(failed_hash,candidate); bad_still=not _oracle_pass(bad_r,{**fixture,"input":candidate})
        good_still=True
        if known_good_hash:
            good_r=invoke_hash(known_good_hash,candidate); good_still=_oracle_pass(good_r,{**fixture,"input":candidate})
        if bad_still and good_still:
            current=candidate; fixture["minimization"]["accepted"]+=1; fixture["minimization"]["last_operation"]=op
    fixture["input"]=current
    fixture["verification"]={"known_bad_detected":known_bad_detected,"known_good_passed":good_pass,"compiled_at":utc()}
    state="ACTIVE" if known_bad_detected and good_pass is True else "CANDIDATE"
    if state=="CANDIDATE" and known_good_hash is None: fixture["uncertainty"]="No accepted known-good reference supplied; fixture is retained but not used as a promotion hard gate."
    h,_=_store_fixture(fixture,state)
    append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"compiled","regression_hash":h,"state":state,"known_bad_hash":failed_hash,"known_good_hash":known_good_hash,"known_bad_detected":known_bad_detected,"known_good_passed":good_pass,"source_case":case.get("name")})
    return {"ok":True,"regression_hash":h,"state":state,"known_bad_detected":known_bad_detected,"known_good_passed":good_pass,"minimization":fixture["minimization"],"fixture":fixture}

def relevant_for_record(record:dict[str,Any])->list[dict[str,Any]]:
    reg=load_registry(); out=[]
    for h,r in reg["regressions"].items():
        if r.get("state")!="ACTIVE": continue
        try: fixture=json.loads(pathlib.Path(r["object"]).read_text())
        except Exception: continue
        if _selector_matches(record,fixture.get("selector") or {}): out.append({"regression_hash":h,"fixture":fixture,"registry":r})
    return out

def search(task:dict[str,Any])->list[dict[str,Any]]:
    name=task.get("desired_name") or task.get("capability_name"); tags=set(task.get("tags") or task.get("applicability") or [])
    pseudo={"name":name,"applicability":sorted(tags)}; out=[]
    for item in relevant_for_record(pseudo):
        out.append({"regression_hash":item["regression_hash"],"selector":item["fixture"].get("selector"),"failure_evidence":item["fixture"].get("failure_evidence"),"source_case":item["fixture"].get("source_case")})
    return out

def promotion_gate_for_record(record:dict[str,Any],invoke_fn:Callable[[Any],dict[str,Any]])->dict[str,Any]:
    relevant=relevant_for_record(record); results=[]
    for item in relevant:
        rr=_run_fixture(item["fixture"],invoke_fn); results.append({"regression_hash":item["regression_hash"],**rr})
        reg=load_registry(); rec=reg["regressions"][item["regression_hash"]]; rec["replay_count"]=int(rec.get("replay_count",0))+1
        if not rr.get("ok"): rec["failure_count"]=int(rec.get("failure_count",0))+1
        rec["last_replayed_at"]=utc(); save_registry(reg)
    ok=all(r.get("ok") for r in results)
    return {"ok":ok,"version":VERSION,"relevant":len(results),"passed":sum(1 for r in results if r.get("ok")),"failed":sum(1 for r in results if not r.get("ok")),"results":results}

def promotion_gate(content_hash:str)->dict[str,Any]:
    caps=_forge_registry(); rec=caps.get(content_hash)
    if not isinstance(rec,dict): raise RegressionError("capability not found")
    forge=_load_forge(); return promotion_gate_for_record(rec,lambda inp: forge.invoke_raw(content_hash,inp,mutate_registry=False))


def _run_argv(argv: list[str], timeout_s: int = 30) -> dict[str, Any]:
    started=time.monotonic()
    try:
        r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout_s,check=False)
        return {"exit_code":r.returncode,"stdout_sha256":sha_bytes(r.stdout.encode()),"stderr_sha256":sha_bytes(r.stderr.encode()),"duration_ms":round((time.monotonic()-started)*1000,3)}
    except subprocess.TimeoutExpired:
        return {"exit_code":124,"timeout":True,"duration_ms":round((time.monotonic()-started)*1000,3)}

def compile_command_failure(*, selector_name: str, bad_argv: list[str], good_argv: list[str], expected_exit: int = 0, timeout_s: int = 30, evidence: dict[str,Any] | None = None) -> dict[str,Any]:
    if not selector_name or not bad_argv or not good_argv: raise RegressionError("selector_name, bad_argv, and good_argv are required")
    bad=_run_argv(bad_argv,timeout_s); good=_run_argv(good_argv,timeout_s)
    known_bad_detected=bad.get("exit_code")!=expected_exit; known_good_passed=good.get("exit_code")==expected_exit
    fixture={"fixture_type":"command_exit","selector":{"name":selector_name},"oracle":{"expected_exit":expected_exit},"argv_suffix":bad_argv[1:],"timeout_s":timeout_s,"known_bad_hash":sha_json({"argv":bad_argv,"result":bad}),"known_good_hash":sha_json({"argv":good_argv,"result":good}),"failure_evidence":evidence or {},"verification":{"known_bad_detected":known_bad_detected,"known_good_passed":known_good_passed,"bad_result":bad,"good_result":good,"compiled_at":utc()},"uncertainty":"Command fixture protects the observed externally visible exit behavior; it does not claim a unique internal root cause."}
    state="ACTIVE" if known_bad_detected and known_good_passed else "CANDIDATE"
    h,_=_store_fixture(fixture,state); append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"compiled_command_failure","regression_hash":h,"state":state,"selector_name":selector_name,"known_bad_detected":known_bad_detected,"known_good_passed":known_good_passed})
    return {"ok":True,"regression_hash":h,"state":state,"known_bad_detected":known_bad_detected,"known_good_passed":known_good_passed,"verification":fixture["verification"]}

def command_gate(regression_hash: str, candidate_argv: list[str]) -> dict[str,Any]:
    shown=show(regression_hash); fixture=shown["fixture"]
    if fixture.get("fixture_type")!="command_exit": raise RegressionError("regression is not command_exit")
    result=_run_argv(candidate_argv,int(fixture.get("timeout_s",30))); expected=int((fixture.get("oracle") or {}).get("expected_exit",0)); ok=result.get("exit_code")==expected
    return {"ok":ok,"regression_hash":regression_hash,"expected_exit":expected,"result":result}

def retire(regression_hash:str,reason:str)->dict[str,Any]:
    reg=load_registry(); rec=reg["regressions"].get(regression_hash)
    if not isinstance(rec,dict): raise RegressionError("regression not found")
    previous=rec.get("state"); rec["state"]="RETIRED"; rec["retired_at"]=utc(); rec["retirement_reason"]=reason; save_registry(reg)
    append_jsonl(PROVENANCE,{"timestamp":utc(),"event":"retired","regression_hash":regression_hash,"previous_state":previous,"reason":reason})
    return {"regression_hash":regression_hash,"previous_state":previous,"state":"RETIRED","object_retained":pathlib.Path(rec["object"]).exists()}
def list_regressions()->list[dict[str,Any]]:
    return sorted(load_registry()["regressions"].values(),key=lambda x:(str(x.get("state")),str(x.get("created_at"))))
def show(h:str)->dict[str,Any]:
    rec=load_registry()["regressions"].get(h)
    if not isinstance(rec,dict): raise RegressionError("regression not found")
    return {"registry":rec,"fixture":json.loads(pathlib.Path(rec["object"]).read_text())}

def selftest()->dict[str,Any]:
    global ROOT,OBJECTS,REGISTRY,PROVENANCE
    old=(ROOT,OBJECTS,REGISTRY,PROVENANCE); checks=[]
    def ck(n,o,d=None): checks.append({"name":n,"ok":bool(o),"detail":d})
    try:
        with tempfile.TemporaryDirectory(prefix="regression-selftest-") as td:
            ROOT=pathlib.Path(td); OBJECTS=ROOT/"objects"; REGISTRY=ROOT/"registry.json"; PROVENANCE=ROOT/"provenance.jsonl"
            fixture={"fixture_type":"capability_io","selector":{"name":"double"},"input":{"x":2},"oracle":{"expected":{"y":4}},"known_bad_hash":"a"*64,"known_good_hash":"b"*64,"failure_evidence":{"source":"selftest"}}
            h,_=_store_fixture(fixture,"ACTIVE"); ck("immutable_store",pathlib.Path(load_registry()["regressions"][h]["object"]).exists(),h)
            rec={"name":"double","applicability":["math"]}
            good=promotion_gate_for_record(rec,lambda x:{"ok":True,"output":{"y":x["x"]*2},"phase":"complete"}); ck("good_passes",good["ok"] and good["relevant"]==1,good)
            bad=promotion_gate_for_record(rec,lambda x:{"ok":True,"output":{"y":x["x"]+1},"phase":"complete"}); ck("bad_caught",not bad["ok"] and bad["failed"]==1,bad)
            none=promotion_gate_for_record({"name":"other","applicability":[]},lambda x:{"ok":False}); ck("irrelevant_not_run",none["ok"] and none["relevant"]==0,none)
            rr=retire(h,"selftest"); ck("retire_preserves",rr["object_retained"],rr)
    finally: ROOT,OBJECTS,REGISTRY,PROVENANCE=old
    return {"version":VERSION,"schema_version":SCHEMA_VERSION,"passed":sum(1 for c in checks if c["ok"]),"total":len(checks),"checks":checks}

def main()->None:
    ap=argparse.ArgumentParser(description="Failure-to-regression compiler")
    ap.add_argument("--selftest",action="store_true"); sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("compile-capability"); p.add_argument("failed"); p.add_argument("--known-good"); p.add_argument("--case"); p.add_argument("--lineage-name")
    p=sub.add_parser("compile-command"); p.add_argument("--selector",required=True); p.add_argument("--bad-json",required=True); p.add_argument("--good-json",required=True); p.add_argument("--expected-exit",type=int,default=0)
    p=sub.add_parser("command-gate"); p.add_argument("regression"); p.add_argument("--argv-json",required=True)
    p=sub.add_parser("gate"); p.add_argument("capability")
    p=sub.add_parser("search"); p.add_argument("--json"); p.add_argument("--file")
    p=sub.add_parser("retire"); p.add_argument("regression"); p.add_argument("--reason",required=True)
    p=sub.add_parser("show"); p.add_argument("regression"); sub.add_parser("list")
    args=ap.parse_args()
    try:
        if args.selftest: out=selftest()
        elif args.cmd=="compile-capability": out=compile_capability_failure(args.failed,known_good_hash=args.known_good,case_name=args.case,lineage_name=args.lineage_name)
        elif args.cmd=="compile-command": out=compile_command_failure(selector_name=args.selector,bad_argv=json.loads(args.bad_json),good_argv=json.loads(args.good_json),expected_exit=args.expected_exit)
        elif args.cmd=="command-gate": out=command_gate(args.regression,json.loads(args.argv_json))
        elif args.cmd=="gate": out=promotion_gate(args.capability)
        elif args.cmd=="search":
            v=json.loads(pathlib.Path(args.file).read_text()) if args.file else json.loads(args.json or "{}")
            out=search(v)
        elif args.cmd=="retire": out=retire(args.regression,args.reason)
        elif args.cmd=="show": out=show(args.regression)
        elif args.cmd=="list": out=list_regressions()
        else: ap.print_help(); raise SystemExit(2)
        print(json.dumps(out,indent=2,sort_keys=True))
        if args.selftest and out["passed"]!=out["total"]: raise SystemExit(1)
        if args.cmd=="gate" and not out.get("ok"): raise SystemExit(1)
    except RegressionError as exc:
        print(json.dumps({"ok":False,"error":str(exc)},indent=2),file=os.sys.stderr); raise SystemExit(1)
if __name__=="__main__": main()
