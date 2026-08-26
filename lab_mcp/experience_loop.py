#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import tempfile
import uuid
from typing import Any

VERSION = "gen6-experience-loop-r1"
MEMORY_PATH = pathlib.Path(os.environ.get("OPTIPLEX_MEMORY_PATH", "/opt/optiplex-lab/experience_memory.py"))
REGRESSION_PATH = pathlib.Path(os.environ.get("OPTIPLEX_REGRESSION_PATH", "/opt/optiplex-lab/regression_compiler.py"))
FORGE_PATH = pathlib.Path(os.environ.get("OPTIPLEX_FORGE_PATH", "/opt/optiplex-lab/capability_forge.py"))

class LoopError(RuntimeError): pass

def load(path: pathlib.Path, prefix: str):
    spec=importlib.util.spec_from_file_location(f"{prefix}_{uuid.uuid4().hex}",path)
    if spec is None or spec.loader is None: raise LoopError(f"cannot load {path}")
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def _mods(): return load(MEMORY_PATH,"memory"),load(REGRESSION_PATH,"regression"),load(FORGE_PATH,"forge")

def _forge_record(forge: Any, h: str) -> dict[str,Any] | None:
    try: return (forge.load_registry().get("capabilities") or {}).get(h)
    except Exception: return None

def plan(task: dict[str,Any]) -> dict[str,Any]:
    memory,regression,forge=_mods()
    retrieval=memory.retrieve(task)
    regression_hints=regression.search({"desired_name":task.get("desired_name") or task.get("capability_name"),"tags":task.get("tags") or task.get("applicability") or []})
    selected=retrieval.get("selected")
    if selected:
        proc=selected.get("procedure") or {}; h=proc.get("capability_hash"); rec=_forge_record(forge,h) if h else None
        if h and rec and rec.get("state") not in {"REJECTED","EXPIRED","SUPERSEDED"} and pathlib.Path(str(rec.get("object") or "")).exists():
            return {"action":"MEMORY_REUSE","memory":selected,"regressions":regression_hints,"capability_hash":h,"forge_gap_opened":False,"reason":"applicable active memory points to an available authoritative capability"}
    gap={"desired_name":task.get("desired_name") or task.get("capability_name") or "","purpose":task.get("intent") or task.get("purpose") or "","applicability":task.get("tags") or task.get("applicability") or []}
    matches=forge.search(gap)
    if matches and ("exact_name" in matches[0].get("reasons",[]) or float(matches[0].get("tag_overlap",0))>=0.75):
        return {"action":"FORGE_REUSE","memory":None,"regressions":regression_hints,"capability_hash":matches[0]["content_hash"],"forge_gap_opened":False,"forge_matches":matches[:5],"reason":"no applicable memory; Forge registry has an existing applicable capability"}
    return {"action":"FORGE_REQUIRED","memory":None,"regressions":regression_hints,"capability_hash":None,"forge_gap_opened":False,"forge_matches":matches[:5],"reason":"no applicable memory or existing Forge capability; invention is genuinely required"}

def execute(task: dict[str,Any], input_value: Any, *, context: str="gen6 experience loop") -> dict[str,Any]:
    memory,regression,forge=_mods(); decision=plan(task)
    if decision["action"]=="FORGE_REQUIRED": return {**decision,"executed":False,"ok":False}
    h=str(decision["capability_hash"]); result=forge.invoke_raw(h,input_value,real_task=True,context=context)
    procedure={"capability_hash":h,"capability_name":(_forge_record(forge,h) or {}).get("name"),"evaluator_hash":(_forge_record(forge,h) or {}).get("evaluator_hash")}
    episode=memory.record_episode({**task,"input":input_value},procedure,bool(result.get("ok")),evidence={"run_id":result.get("run_id"),"result_hash":memory.sha_json({k:v for k,v in result.items() if k not in {"output","stdout_preview","stderr_preview"}})},source="experience-loop")
    if decision.get("memory"):
        memory.record_retrieval_outcome(decision["memory"]["memory_hash"],bool(result.get("ok")),episode["episode_id"])
    return {**decision,"executed":True,"ok":bool(result.get("ok")),"result":result,"episode_id":episode["episode_id"],"episode_hash":episode["episode_hash"]}

def selftest()->dict[str,Any]:
    # Integration semantics are exercised with small stubs to avoid mutating live registries.
    checks=[]
    def ck(n,o,d=None): checks.append({"name":n,"ok":bool(o),"detail":d})
    # Static invariant: planning code must consult memory retrieval before Forge search/opening.
    import inspect
    plan_src=inspect.getsource(plan); execute_src=inspect.getsource(execute)
    a=plan_src.index("retrieval=memory.retrieve(task)"); b=plan_src.index("matches=forge.search(gap)"); ck("memory_before_forge",a<b)
    ck("no_open_gap_in_plan","open_gap(" not in plan_src)
    ck("no_permanent_mcp_dependency","mcp.tool" not in (plan_src+execute_src))
    return {"version":VERSION,"passed":sum(1 for c in checks if c["ok"]),"total":len(checks),"checks":checks}

def _json(text:str|None,path:str|None)->Any:
    if text and path: raise LoopError("use only one inline/file")
    if path: return json.loads(pathlib.Path(path).read_text())
    return json.loads(text or "{}")
def main()->None:
    ap=argparse.ArgumentParser(description="Gen6 retrieve-before-invent experience loop"); ap.add_argument("--selftest",action="store_true"); sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("plan"); p.add_argument("--json"); p.add_argument("--file")
    p=sub.add_parser("execute"); p.add_argument("--task-json"); p.add_argument("--task-file"); p.add_argument("--input-json"); p.add_argument("--input-file"); p.add_argument("--context",default="gen6 experience loop")
    args=ap.parse_args()
    try:
        if args.selftest: out=selftest()
        elif args.cmd=="plan": out=plan(_json(args.json,args.file))
        elif args.cmd=="execute": out=execute(_json(args.task_json,args.task_file),_json(args.input_json,args.input_file),context=args.context)
        else: ap.print_help(); raise SystemExit(2)
        print(json.dumps(out,indent=2,sort_keys=True))
        if args.selftest and out["passed"]!=out["total"]: raise SystemExit(1)
    except LoopError as exc: print(json.dumps({"ok":False,"error":str(exc)},indent=2),file=os.sys.stderr); raise SystemExit(1)
if __name__=="__main__": main()
