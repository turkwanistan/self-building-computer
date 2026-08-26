#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations
import hashlib, importlib.util, json, pathlib

FORGE='/opt/optiplex-lab/capability_forge.py'
CAP='3a6062a4ea23663c8824f66b98f5fc876fc34f3749bcaec20b4063003b96e936'
OUT=pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen5-semantic-edit-experiment.json')
spec=importlib.util.spec_from_file_location('forge',FORGE); f=importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
variants=[
    "def f():\n    return {'a': 1}\n",
    'def f():\n    return {"a": 1}\n',
    "def f():\n    return { 'a':1 }\n",
    "def f():\n    return {\n        'a': 1,\n    }\n",
    "def f():\n    return {'a': 1,}\n",
]
exact_old="return {'a': 1}"
exact_new="return {'a': 1, 'b': 2}"
rows=[]
for i,src in enumerate(variants):
    exact_matches=src.count(exact_old)
    exact_ok=exact_matches==1
    inp={'source':src,'function':'f','key':'b','value_expression':'2'}
    semantic=f.invoke_raw(CAP,inp,real_task=False,mutate_registry=False)
    rows.append({'variant':i+1,'exact_matches':exact_matches,'exact_ok':exact_ok,'semantic_ok':bool(semantic.get('ok')),'semantic_run_id':semantic.get('run_id')})

# Compare authoring payload for the actual Gen5 lab_status addition against a minimal unique two-line exact-replace anchor.
old_server=pathlib.Path('/var/lib/optiplex-lab/recovery/server.previous-20260826T100045Z.py')
if not old_server.exists():
    candidates=sorted(pathlib.Path('/var/lib/optiplex-lab/recovery').glob('server.previous-*.py'))
    old_server=candidates[-1] if candidates else pathlib.Path('/opt/optiplex-lab/server.py')
lines=old_server.read_text().splitlines(True)
workflow_line=next(x for x in lines if '"workflow_graphs": {' in x)
commands_line=next(x for x in lines if '"commands": {' in x)
exact_anchor=workflow_line+commands_line
forge_expr='{"path": "/opt/optiplex-lab/capability_forge.py", "available": Path("/opt/optiplex-lab/capability_forge.py").is_file(), "sha256": _sha(Path("/opt/optiplex-lab/capability_forge.py").read_bytes()) if Path("/opt/optiplex-lab/capability_forge.py").is_file() else None, "version": "gen5-capability-forge-r1", "registry": "/var/lib/optiplex-lab/capabilities/registry.json"}'
new_commands=commands_line.rstrip('\n')
if new_commands.rstrip().endswith('}}'):
    new_commands=new_commands.rstrip()[:-1]+", 'capability_forge': "+forge_expr+'}\n'
else:
    raise SystemExit('unexpected commands line shape')
exact_new_anchor=workflow_line+new_commands
exact_payload={'path':'/root/gen5/server.gen5.prepared.py','old':exact_anchor,'new':exact_new_anchor}
semantic_payload={'path':'/opt/optiplex-lab/server.py','output_path':'/root/gen5/server.gen5.prepared.py','function':'lab_status','key':'capability_forge','value_expression':forge_expr}
exact_bytes=len(json.dumps(exact_payload,separators=(',',':')).encode())
semantic_bytes=len(json.dumps(semantic_payload,separators=(',',':')).encode())
result={
 'experiment':'gen5-semantic-edit-vs-exact-replace',
 'capability_hash':CAP,
 'format_variants':rows,
 'exact_successes':sum(r['exact_ok'] for r in rows),
 'semantic_successes':sum(r['semantic_ok'] for r in rows),
 'variants_total':len(rows),
 'actual_server_authoring_proxy':{
   'exact_replace_payload_bytes':exact_bytes,
   'semantic_payload_bytes':semantic_bytes,
   'reduction':round(1-semantic_bytes/exact_bytes,3) if exact_bytes else None,
   'exact_anchor_matches_in_gen4_source':old_server.read_text().count(exact_anchor),
   'gen4_source_used':str(old_server),
 },
}
OUT.parent.mkdir(parents=True,exist_ok=True); f.safe_write_json(OUT,result); result['artifact']=str(OUT); result['artifact_sha256']=hashlib.sha256(OUT.read_bytes()).hexdigest()
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if result['semantic_successes']==len(rows) and result['exact_successes']<result['semantic_successes'] else 1)
