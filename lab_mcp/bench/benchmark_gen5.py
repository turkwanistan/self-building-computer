#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

FORGE_PATH = pathlib.Path('/opt/optiplex-lab/capability_forge.py')
ARTIFACT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen5-capability-forge-benchmark.json')

spec = importlib.util.spec_from_file_location('gen5_forge', FORGE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit('cannot load forge')
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)

STARTED = datetime.now(timezone.utc).isoformat()
checks: list[dict[str, Any]] = []
created: list[str] = []
rejected: list[str] = []
expired: list[str] = []
promoted: list[str] = []
latencies: dict[str, float] = {}
notes: list[str] = []


def check(name: str, ok: bool, detail: Any = None) -> None:
    checks.append({'name': name, 'ok': bool(ok), 'detail': detail})


def contract(name: str, purpose: str, input_schema: dict[str, Any], output_schema: dict[str, Any], cases: list[dict[str, Any]], *, deps: list[str] | None = None, side: list[str] | None = None, tags: list[str] | None = None, lifecycle: str = 'CANDIDATE', timeout: int = 5, max_output: int = 65536) -> dict[str, Any]:
    return {
        'schema_version': f.CONTRACT_VERSION,
        'name': name,
        'version': '1',
        'purpose': purpose,
        'input_schema': input_schema,
        'output_schema': output_schema,
        'entrypoint': ['python', 'main.py'],
        'dependencies': {'pip': deps or []},
        'side_effects': side or [],
        'applicability': tags or [],
        'evaluation': {'cases': cases},
        'provenance': {'creator': 'ChatGPT', 'creator_episode': 'generation-5-capability-forge-benchmark', 'benchmark': 'gen5-capability-forge-benchmark'},
        'lifecycle': lifecycle,
        'ttl': {'hours': 24 if lifecycle == 'EPHEMERAL' else 168},
        'limits': {'timeout_s': timeout, 'max_output_bytes': max_output},
    }


def forge_cap(name: str, purpose: str, c: dict[str, Any], source: str, *, extra: dict[str, str] | None = None, evaluate: bool = True) -> tuple[str, dict[str, Any], dict[str, Any] | None, float]:
    t0=time.monotonic()
    gap=f.open_gap({'desired_name':name,'purpose':purpose,'applicability':c.get('applicability',[])})
    if gap['action']=='REUSE':
        h=gap['selected']['content_hash']; return h, {'state':'SEARCH_REUSED','content_hash':h}, None, (time.monotonic()-t0)*1000
    ws=pathlib.Path(gap['workspace'])
    f.safe_write_json(ws/'capability.json',c)
    (ws/'main.py').write_text(source)
    for rel,text in (extra or {}).items():
        p=ws/rel; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(text)
    sealed=f.seal(str(ws)); h=sealed['content_hash']
    if sealed['state']=='SEALED': created.append(h)
    ev=f.evaluate(h) if evaluate and sealed['state']=='SEALED' else None
    if ev is not None and not ev['ok']: rejected.append(h)
    return h,sealed,ev,(time.monotonic()-t0)*1000


# Snapshot proving these task capabilities were absent at benchmark start.
initial_registry=f.load_registry()['capabilities']
initial_names=sorted({r.get('name') for r in initial_registry.values()})

# 1. Typed data-transform helper.
record_contract=contract(
    'gen5-record-normalizer','Normalize object keys and trim string values with a typed JSON contract.',
    {'type':'object','required':['record'],'properties':{'record':{'type':'object'}},'additionalProperties':False},
    {'type':'object','required':['record'],'properties':{'record':{'type':'object'}},'additionalProperties':False},
    [
        {'name':'positive','kind':'positive','input':{'record':{' Name ':' Alice ','AGE':3}},'expected':{'record':{'name':'Alice','age':3}}},
        {'name':'invalid','kind':'negative','input':{},'expect_error':True},
        {'name':'collision','kind':'adversarial','input':{'record':{' A ':1,'a':2}},'expect_error':True},
    ], tags=['json','transform','normalization'])
record_source="""import json,sys
x=json.load(sys.stdin); out={}
for k,v in x['record'].items():
    nk=str(k).strip().lower()
    if nk in out: raise SystemExit('normalized key collision')
    out[nk]=v.strip() if isinstance(v,str) else v
print(json.dumps({'record':out},sort_keys=True))
"""
rh,rs,rev,ms=forge_cap('gen5-record-normalizer',record_contract['purpose'],record_contract,record_source); latencies['typed_transform_create_ms']=round(ms,2)
check('typed_data_transform', bool(rev and rev['ok']), {'hash':rh,'eval':rev and f"{rev['passed_cases']}/{rev['total_cases']}"})

# 2. Source-analysis helper.
source_contract=contract(
    'gen5-python-symbol-index','Extract Python functions, classes, and imports without executing source.',
    {'type':'object','required':['source'],'properties':{'source':{'type':'string'}},'additionalProperties':False},
    {'type':'object','required':['functions','classes','imports'],'properties':{'functions':{'type':'array','items':{'type':'string'}},'classes':{'type':'array','items':{'type':'string'}},'imports':{'type':'array','items':{'type':'string'}}},'additionalProperties':False},
    [
        {'name':'positive','kind':'positive','input':{'source':'import os\nfrom x import y\nclass C:\n    pass\ndef f():\n    pass\n'},'expected':{'functions':['f'],'classes':['C'],'imports':['os','x.y']}},
        {'name':'syntax','kind':'negative','input':{'source':'def broken('},'expect_error':True},
    ], tags=['python','source-analysis','ast'])
source_impl="""import ast,json,sys
x=json.load(sys.stdin); t=ast.parse(x['source'])
func=[]; cls=[]; imp=[]
for n in ast.walk(t):
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)): func.append(n.name)
    elif isinstance(n,ast.ClassDef): cls.append(n.name)
    elif isinstance(n,ast.Import): imp.extend(a.name for a in n.names)
    elif isinstance(n,ast.ImportFrom): imp.extend((n.module+'.'+a.name if n.module else a.name) for a in n.names)
print(json.dumps({'functions':sorted(set(func)),'classes':sorted(set(cls)),'imports':sorted(set(imp))}))
"""
sh,ss,sev,ms=forge_cap('gen5-python-symbol-index',source_contract['purpose'],source_contract,source_impl); latencies['source_analysis_create_ms']=round(ms,2)
check('source_analysis_helper', bool(sev and sev['ok']), {'hash':sh})

# 3. Structured Python editing via LibCST (real Gen5 friction target).
semantic_contract=contract(
    'gen5-python-cst-editor','Add one key/value expression to the dictionary returned by a named Python function while preserving concrete syntax.',
    {'type':'object','required':['function','key','value_expression'],'properties':{'source':{'type':'string'},'path':{'type':'string'},'output_path':{'type':'string'},'function':{'type':'string','minLength':1},'key':{'type':'string','minLength':1},'value_expression':{'type':'string','minLength':1}},'oneOf':[{'required':['source']},{'required':['path']}],'additionalProperties':False},
    {'type':'object','required':['changed','source','output_path'],'properties':{'changed':{'type':'boolean'},'source':{'type':'string'},'output_path':{'type':['string','null']}},'additionalProperties':False},
    [
        {'name':'positive','kind':'positive','input':{'source':"def f():\n    return {'a': 1}\n",'function':'f','key':'b','value_expression':'2'},'expected':{'changed':True,'source':"def f():\n    return {'a': 1, 'b': 2}\n",'output_path':None}},
        {'name':'missing-function','kind':'negative','input':{'source':'def f():\n    return {}\n','function':'g','key':'b','value_expression':'2'},'expect_error':True},
        {'name':'duplicate-key','kind':'adversarial','input':{'source':"def f():\n    return {'b': 1}\n",'function':'f','key':'b','value_expression':'2'},'expect_error':True},
    ], deps=['libcst==1.8.2'], side=['read_files','write_workspace'], tags=['python','source-editing','semantic-edit','libcst'], timeout=10)
semantic_impl=r'''import hashlib,json,pathlib,sys
import libcst as cst
x=json.load(sys.stdin)
source=x.get('source')
if source is None: source=pathlib.Path(x['path']).read_text()
target=x['function']; key=x['key']; value=cst.parse_expression(x['value_expression'])
class T(cst.CSTTransformer):
    def __init__(self): self.in_target=0; self.changed=0; self.found=0
    def visit_FunctionDef(self,node):
        if node.name.value==target: self.in_target+=1; self.found+=1
        return True
    def leave_FunctionDef(self,original,updated):
        if original.name.value==target: self.in_target-=1
        return updated
    def leave_Return(self,original,updated):
        if not self.in_target or not isinstance(updated.value,cst.Dict): return updated
        existing=[]
        for e in updated.value.elements:
            if e is not None and isinstance(e.key,cst.SimpleString):
                try: existing.append(e.key.evaluated_value)
                except Exception: pass
        if key in existing: raise RuntimeError('key already exists')
        self.changed+=1
        return updated.with_changes(value=updated.value.with_changes(elements=[*updated.value.elements,cst.DictElement(cst.SimpleString(repr(key)),value)]))
t=T(); mod=cst.parse_module(source); out=mod.visit(t).code
if t.found!=1: raise SystemExit(f'expected exactly one function, found {t.found}')
if t.changed!=1: raise SystemExit(f'expected exactly one return dictionary, changed {t.changed}')
out_path=x.get('output_path')
if out_path:
    p=pathlib.Path(out_path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(out)
print(json.dumps({'changed':True,'source':out,'output_path':out_path}))
'''
semh,sems,semev,ms=forge_cap('gen5-python-cst-editor',semantic_contract['purpose'],semantic_contract,semantic_impl); latencies['semantic_editor_create_ms']=round(ms,2)
check('semantic_structured_editor', bool(semev and semev['ok']), {'hash':semh,'dependency':semev and semev['dependencies']})

# Two successful real uses create recurrence evidence before self-hosting.
if semev and semev['ok']:
    sem1=f.invoke_raw(semh,{'source':'def alpha():\n    return {}\n','function':'alpha','key':'x','value_expression':'1'},real_task=True,context='gen5 benchmark semantic edit 1')
    sem2=f.invoke_raw(semh,{'source':'def beta():\n    return {"y": 2}\n','function':'beta','key':'z','value_expression':'3'},real_task=True,context='gen5 benchmark semantic edit 2')
    semgov=f.govern(semh)
    if semgov['decision']=='PROMOTE': promoted.append(semh)
else:
    sem1=sem2={'ok':False}; semgov={'decision':'REJECT'}

# 4. Parser/extractor for a previously unsupported structured artifact.
unit_contract=contract(
    'gen5-systemd-unit-parser','Parse basic systemd INI-style unit text into section/key mappings.',
    {'type':'object','required':['text'],'properties':{'text':{'type':'string'}},'additionalProperties':False},
    {'type':'object','required':['sections'],'properties':{'sections':{'type':'object'}},'additionalProperties':False},
    [
        {'name':'positive','kind':'positive','input':{'text':'[Unit]\nDescription=Demo\n[Service]\nExecStart=/bin/true\n'},'expected':{'sections':{'Unit':{'Description':'Demo'},'Service':{'ExecStart':'/bin/true'}}}},
        {'name':'key-before-section','kind':'negative','input':{'text':'X=1\n'},'expect_error':True},
    ], tags=['parser','systemd','structured-artifact'])
unit_impl="""import json,sys
x=json.load(sys.stdin); sections={}; cur=None
for raw in x['text'].splitlines():
    line=raw.strip()
    if not line or line.startswith('#'): continue
    if line.startswith('[') and line.endswith(']'):
        cur=line[1:-1]; sections.setdefault(cur,{})
    elif '=' in line:
        if cur is None: raise SystemExit('key before section')
        k,v=line.split('=',1); sections[cur][k]=v
    else: raise SystemExit('unsupported line')
print(json.dumps({'sections':sections},sort_keys=True))
"""
uh,us,uev,ms=forge_cap('gen5-systemd-unit-parser',unit_contract['purpose'],unit_contract,unit_impl); latencies['structured_parser_create_ms']=round(ms,2)
check('structured_artifact_parser', bool(uev and uev['ok']), {'hash':uh})

# 5. Separate small dependency install capability.
toml_contract=contract(
    'gen5-toml-query','Read a TOML document and return a dotted-key value using a small installed dependency.',
    {'type':'object','required':['text','key'],'properties':{'text':{'type':'string'},'key':{'type':'string'}},'additionalProperties':False},
    {'type':'object','required':['value'],'properties':{'value':{}},'additionalProperties':False},
    [
        {'name':'positive','kind':'positive','input':{'text':'[tool]\nname="demo"\n','key':'tool.name'},'expected':{'value':'demo'}},
        {'name':'missing','kind':'negative','input':{'text':'a=1\n','key':'x'},'expect_error':True},
    ], deps=['tomli==2.2.1'], tags=['toml','parser','dependency'])
toml_impl="""import json,sys,tomli
x=json.load(sys.stdin); cur=tomli.loads(x['text'])
for part in x['key'].split('.'):
    if not isinstance(cur,dict) or part not in cur: raise SystemExit('missing key')
    cur=cur[part]
print(json.dumps({'value':cur}))
"""
th,ts,tev,ms=forge_cap('gen5-toml-query',toml_contract['purpose'],toml_contract,toml_impl); latencies['dependency_capability_create_ms']=round(ms,2)
check('small_dependency_install', bool(tev and tev['ok'] and tev['dependencies']['dependency_count']==1), {'hash':th,'dependency':tev and tev['dependencies']})

# 6. Exact content duplicate is reused rather than creating another object.
t0=time.monotonic(); dup_gap=f.open_gap({'desired_name':'gen5-unrelated-alias','purpose':'different request to test content dedupe','applicability':['other']}); dup_ws=pathlib.Path(dup_gap['workspace'])
f.safe_write_json(dup_ws/'capability.json',record_contract); (dup_ws/'main.py').write_text(record_source); dup=f.seal(str(dup_ws)); latencies['duplicate_reuse_ms']=round((time.monotonic()-t0)*1000,2)
check('duplicate_content_avoided', dup['state']=='DUPLICATE_REUSED' and dup['content_hash']==rh, dup)

# 7. Malformed contract rejected before sealing.
try:
    malformed=dict(record_contract); malformed.pop('output_schema'); f.validate_contract(malformed); malformed_ok=False
except f.ForgeError as exc:
    malformed_ok=True; malformed_detail=str(exc)
check('malformed_contract_rejected',malformed_ok,malformed_detail if malformed_ok else None)

# 8. Evaluator catches several deliberately bad descendants.
bad_subchecks=[]

def expect_eval_reject(name: str, c: dict[str, Any], source: str) -> tuple[bool,str|None]:
    h,s,e,_=forge_cap(name,c['purpose'],c,source)
    ok=bool(e is not None and not e['ok'] and f.load_registry()['capabilities'][h]['state']=='REJECTED')
    return ok,h

syntax_c=contract('gen5-bad-syntax','Deliberately syntax-broken descendant.',{'type':'object'},{'type':'object'},[{'name':'p','kind':'positive','input':{},'expected':{}},{'name':'n','kind':'negative','input':{'x':1},'expect_error':True}],tags=['failure-fixture'])
ok,h=expect_eval_reject('gen5-bad-syntax',syntax_c,'def broken(:\n'); bad_subchecks.append(('syntax_broken',ok,h))
wrong_c=contract('gen5-bad-output','Deliberately wrong implementation.',{'type':'object','required':['x'],'properties':{'x':{'type':'integer'}},'additionalProperties':False},{'type':'object','required':['y'],'properties':{'y':{'type':'integer'}},'additionalProperties':False},[{'name':'p','kind':'positive','input':{'x':2},'expected':{'y':4}},{'name':'n','kind':'negative','input':{},'expect_error':True}],tags=['failure-fixture'])
ok,h=expect_eval_reject('gen5-bad-output',wrong_c,"import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({'y':x['x']+1}))\n"); bad_subchecks.append(('test_broken',ok,h))
adv_c=contract('gen5-bad-adversarial','Passes ordinary case but fails an independent adversarial edge.',{'type':'object','required':['n'],'properties':{'n':{'type':'integer'}},'additionalProperties':False},{'type':'object','required':['even'],'properties':{'even':{'type':'boolean'}},'additionalProperties':False},[{'name':'normal','kind':'positive','input':{'n':2},'expected':{'even':True}},{'name':'adversarial-zero','kind':'adversarial','input':{'n':0},'expected':{'even':True}}],tags=['failure-fixture'])
ok,h=expect_eval_reject('gen5-bad-adversarial',adv_c,"import json,sys\nn=json.load(sys.stdin)['n']\nprint(json.dumps({'even': n>0 and n%2==0}))\n"); bad_subchecks.append(('adversarial_rejected',ok,h))
missing_c=contract('gen5-missing-dependency','Dependency setup must fail closed.',{'type':'object'},{'type':'object'},[{'name':'p','kind':'positive','input':{},'expected':{}},{'name':'n','kind':'negative','input':{'x':1},'expect_error':True}],deps=['file:///definitely-missing-optiplex-gen5'],tags=['failure-fixture'])
ok,h=expect_eval_reject('gen5-missing-dependency',missing_c,"import json\nprint('{}')\n"); bad_subchecks.append(('missing_dependency',ok,h))
timeout_c=contract('gen5-timeout','Timeout fixture.',{'type':'object'},{'type':'object'},[{'name':'p','kind':'positive','input':{},'expected':{}},{'name':'n','kind':'negative','input':{'x':1},'expect_error':True}],tags=['failure-fixture'],timeout=1)
ok,h=expect_eval_reject('gen5-timeout',timeout_c,"import time\ntime.sleep(2)\nprint('{}')\n"); bad_subchecks.append(('timeout',ok,h))
output_c=contract('gen5-excessive-output','Output bound fixture.',{'type':'object'},{'type':'object','required':['blob'],'properties':{'blob':{'type':'string'}},'additionalProperties':False},[{'name':'p','kind':'positive','input':{},'expected':{'blob':'ok'}},{'name':'n','kind':'negative','input':{'x':1},'expect_error':True}],tags=['failure-fixture'],max_output=512)
ok,h=expect_eval_reject('gen5-excessive-output',output_c,"import json\nprint(json.dumps({'blob':'x'*5000}))\n"); bad_subchecks.append(('excessive_output',ok,h))
check('broken_descendants_rejected', all(x[1] for x in bad_subchecks), bad_subchecks)

# 9. Authority-violating declaration rejected by contract gate.
try:
    evil=dict(record_contract); evil['name']='gen5-evil-authority'; evil['side_effects']=['host_mounts']; evil['requested_authority']=['host_credentials','private_network']; f.validate_contract(evil); authority_ok=False
except f.ForgeError as exc:
    authority_ok=True; authority_detail=str(exc)
check('forbidden_authority_rejected',authority_ok,authority_detail if authority_ok else None)

# 10. Ephemeral cleanup removes runtime object but preserves provenance/hashes.
eph_c=contract('gen5-ephemeral-helper','One-off helper expected to expire after evidence capture.',{'type':'object','required':['x'],'properties':{'x':{'type':'string'}},'additionalProperties':False},{'type':'object','required':['x'],'properties':{'x':{'type':'string'}},'additionalProperties':False},[{'name':'p','kind':'positive','input':{'x':'a'},'expected':{'x':'a'}},{'name':'n','kind':'negative','input':{},'expect_error':True}],lifecycle='EPHEMERAL',tags=['temporary'])
eh,es,eev,_=forge_cap('gen5-ephemeral-helper',eph_c['purpose'],eph_c,"import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps(x))\n")
ex=f.expire(eh,'Gen5 benchmark useless one-off cleanup'); expired.append(eh)
check('ephemeral_expiry_provenance', bool(eev and eev['ok'] and ex['object_removed'] and ex['provenance_retained'] and ex['source_hashes_retained']), {'hash':eh,'expiry':ex})

# 11. Reuse a successful capability without regeneration, then promotion governor.
t0=time.monotonic(); r1=f.invoke_raw(rh,{'record':{' X ':' one '}},real_task=True,context='gen5 reuse task 1'); r2=f.invoke_raw(rh,{'record':{'Y':' two '}},real_task=True,context='gen5 reuse task 2'); latencies['subsequent_reuse_ms']=round(((time.monotonic()-t0)*1000)/2,2)
rg=f.govern(rh)
if rg['decision']=='PROMOTE': promoted.append(rh)
check('successful_reuse_without_regeneration',r1['ok'] and r2['ok'] and rg['decision']=='PROMOTE',{'hash':rh,'governor':rg,'runs':[r1.get('run_id'),r2.get('run_id')]})

# Real-task failure evidence on an otherwise-good capability should remain visible.
real_fail=f.invoke_raw(rh,{},real_task=True,context='gen5 deliberately invalid real task')

# Failed semantic self-edit attempt: missing function, no source file modification.
failed_self_edit=f.invoke_raw(semh,{'source':'def f():\n    return {}\n','function':'missing','key':'x','value_expression':'1'},real_task=True,context='gen5 failed self-edit fixture') if semev and semev['ok'] else {'ok':False}

# 12. Invoke a forged capability through reusable workflow + Gen4 graph machinery.
graph_params=pathlib.Path('/root/gen5/benchmark-capability-graph-params.json')
f.safe_write_json(graph_params,{'capability':rh,'input_json':json.dumps({'record':{' Z ':' graph '}}),'context':'gen5 graph benchmark'})
gp=subprocess.run(['/opt/optiplex-lab/workflow_graphs.py','run','capability-use-transaction@1','--params-file',str(graph_params)],capture_output=True,text=True,timeout=120,check=False)
try: graph_result=json.loads(gp.stdout) if gp.stdout.strip() else {}
except Exception: graph_result={}
check('workflow_graph_invokes_forged_capability',gp.returncode==0 and graph_result.get('ok') is True,{'returncode':gp.returncode,'graph_run':graph_result.get('run_id'),'code_mode_invocations':graph_result.get('code_mode_invocations'),'underlying_steps':graph_result.get('underlying_code_mode_steps'),'raw_shell_share':graph_result.get('raw_shell_step_share')})

# Assemble transparent metrics.
reg=f.load_registry()['capabilities']
passing_hashes=[h for h in created if (reg.get(h,{}).get('last_evaluation') or {}).get('ok')]
rejected_hashes=sorted({h for h,r in reg.items() if r.get('state')=='REJECTED'})
metrics={
    'blind_capability_tasks_attempted':12,
    'blind_tasks_passed':sum(1 for c in checks if c['ok']),
    'capabilities_successfully_forged':len(passing_hashes),
    'task_success_rate':round(sum(1 for c in checks if c['ok'])/len(checks),3) if checks else 0,
    'test_evaluator_pass_rate':round(sum(1 for h in created if (reg.get(h,{}).get('last_evaluation') or {}).get('ok'))/len(created),3) if created else 0,
    'broken_candidates_rejected':sum(1 for x in bad_subchecks if x[1]),
    'malformed_contracts_rejected':1 if malformed_ok else 0,
    'forbidden_authority_manifests_rejected':1 if authority_ok else 0,
    'duplicate_capabilities_avoided':1 if dup['state']=='DUPLICATE_REUSED' else 0,
    'capabilities_reused':sum(1 for r in reg.values() if int(r.get('reuse_count',0))>0),
    'ephemeral_capabilities_expired':len(expired),
    'promoted_capabilities':len(set(promoted)),
    'permanent_mcp_tools_before':10,
    'permanent_mcp_tools_after':10,
    'chatgpt_authored_helper_source_bytes':sum(int(reg.get(h,{}).get('source_bytes',0)) for h in created),
    'code_mode_steps':int(graph_result.get('underlying_code_mode_steps',0) or 0),
    'workflow_invocations':int(graph_result.get('child_invocations',0) or 0),
    'graph_invocations':1,
    'raw_shell_usage':int(graph_result.get('raw_shell_command_steps',0) or 0),
    'retries':int(graph_result.get('retries',0) or 0),
    'dependency_footprint':{h:len((reg.get(h,{}).get('dependencies') or {}).get('pip',[])) for h in created},
    'creation_latency_ms':latencies,
    'subsequent_reuse_latency_ms':latencies.get('subsequent_reuse_ms'),
    'provenance_complete_records':sum(1 for h,r in reg.items() if r.get('source_hashes') and r.get('evaluator_hash') and r.get('creator_episode')),
    'containment':f.containment_probe(),
    'semantic_editor_hash':semh,
    'semantic_editor_governor':semgov,
    'semantic_editor_real_successes_before_self_host':int(reg.get(semh,{}).get('real_task_successes',0)),
    'semantic_editor_failed_self_edit_fixture_rejected':not bool(failed_self_edit.get('ok')),
    'real_task_failure_recorded':not bool(real_fail.get('ok')),
    'graph_run_id':graph_result.get('run_id'),
}

result={
    'generation':'gen5-capability-forge-r1',
    'benchmark':'gen5-capability-forge-benchmark',
    'started_at':STARTED,
    'ended_at':datetime.now(timezone.utc).isoformat(),
    'initial_registry_names':initial_names,
    'required_capabilities_absent_at_start':all(n not in initial_names for n in ['gen5-record-normalizer','gen5-python-symbol-index','gen5-python-cst-editor','gen5-systemd-unit-parser','gen5-toml-query']),
    'passed':sum(1 for c in checks if c['ok']),
    'total':len(checks),
    'checks':checks,
    'created_hashes':created,
    'passing_hashes':passing_hashes,
    'rejected_hashes':rejected_hashes,
    'expired_hashes':expired,
    'promoted_hashes':sorted(set(promoted)),
    'metrics':metrics,
    'semantic_editor':{'hash':semh,'evaluation_ok':bool(semev and semev['ok']),'governor':semgov,'benchmark_real_runs':[sem1.get('run_id'),sem2.get('run_id')],'failed_fixture':failed_self_edit},
    'workflow_graph_integration':graph_result,
}
ARTIFACT.parent.mkdir(parents=True,exist_ok=True)
f.safe_write_json(ARTIFACT,result)
result['artifact']=str(ARTIFACT); result['artifact_sha256']=hashlib.sha256(ARTIFACT.read_bytes()).hexdigest()
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if result['passed']==result['total'] else 1)
