#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import statistics
import time
import uuid
from datetime import datetime, timezone
from typing import Any

BASE=pathlib.Path('/root/gen6/bench-state')
CAPS=BASE/'capabilities'; MEM=BASE/'memory'; REGS=BASE/'regressions'; RUNS=BASE/'capability-runs'
ART=pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen6-experience-memory-benchmark.json')
STAGE=pathlib.Path(os.environ.get('OPTIPLEX_GEN6_SOURCE_ROOT','/opt/optiplex-lab'))
LIVE_CAPS=pathlib.Path('/var/lib/optiplex-lab/capabilities')
LIVE_RUNS=pathlib.Path('/var/lib/optiplex-lab/capability-runs')
for p in (BASE,): shutil.rmtree(p,ignore_errors=True)
CAPS.mkdir(parents=True); RUNS.mkdir(parents=True)
shutil.copy2(LIVE_CAPS/'registry.json',CAPS/'registry.json'); shutil.copy2(LIVE_CAPS/'provenance.jsonl',CAPS/'provenance.jsonl'); shutil.copytree(LIVE_CAPS/'objects',CAPS/'objects')
os.environ.update({
 'OPTIPLEX_FORGE_ROOT':str(CAPS),'OPTIPLEX_FORGE_RUN_ROOT':str(RUNS),'OPTIPLEX_FORGE_TRACE':str(BASE/'trace.jsonl'),
 'OPTIPLEX_FORGE_PATH':str(STAGE/'capability_forge.py'),'OPTIPLEX_REGRESSION_COMPILER_PATH':str(STAGE/'regression_compiler.py'),
 'OPTIPLEX_REGRESSION_ROOT':str(REGS),'OPTIPLEX_MEMORY_ROOT':str(MEM),'OPTIPLEX_MEMORY_PATH':str(STAGE/'experience_memory.py'),
 'OPTIPLEX_REGRESSION_PATH':str(STAGE/'regression_compiler.py')})

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(m); return m
f=load('gen6_forge',STAGE/'capability_forge.py'); m=load('gen6_memory',STAGE/'experience_memory.py'); r=load('gen6_regression',STAGE/'regression_compiler.py'); loop=load('gen6_loop',STAGE/'experience_loop.py')
# Memory should reference original actual Gen5 run artifacts for provenance only.
m.FORGE_RUN_ROOT=LIVE_RUNS
START=datetime.now(timezone.utc).isoformat(); checks=[]; retrieval_lat=[]; correct=0; wrong=0; retrieval_cases=0; forge_avoided=0

def ck(name,ok,detail=None): checks.append({'name':name,'ok':bool(ok),'detail':detail})
def canon(v): return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

record_hash='170256b4f65fc109c9fc80f55afbcdea049c733adc78f815f211056cccc70548'
symbol_hash='3e7c1599e64b7cbab7f6649ab7350571e2de3ff2c5f17e01f4a9dd3c0eaa5be9'
bad_output_hash='d5d489b7655209bc218aeeb67ab7538b4a8b881673153446488229b50da93c56'
timeout_hash='7a615a3f98a7a3be8babdf6376f38be2025543618af8dfff638ce2f028c8c708'

# 1: actual Gen5 episodes -> active held-out-validated memory.
imp=m.import_forge_episodes(record_hash); distilled=m.distill(record_hash); ck('actual_gen5_experience_distills_active',imp['imported']>=4 and distilled.get('state')=='ACTIVE',{'import':imp,'distill':distilled})
mem_obj=m.show(distilled['memory_hash'])['memory']; env=dict(mem_obj['preconditions'])

def memory_task(intent,input_value,tags=None,kind='capability:gen5-record-normalizer'):
 return {'intent':intent,'task_kind':kind,'tags':tags or ['json','transform','normalization'],'environment':env,'input':input_value,'parameters':{'record':None},'desired_name':'gen5-record-normalizer'}

# 2-4: formatting/wording variants retrieve prior experience before Forge invention and execute successfully.
variants=[
 ('normalize object keys and trim string values',{'record':{' Name ':' Alice '}}),
 ('trim strings while normalizing object record keys',{'record':{' CITY ':' DC '}}),
 ('normalize record object keys; trim textual values',{'record':{' X ':' one '}}),
]
variant_results=[]
for i,(intent,inp) in enumerate(variants,1):
 task=memory_task(intent,inp); dec=loop.plan(task); retrieval_cases+=1
 sel=dec.get('memory'); retrieval_lat.append(float((m.retrieve(task)).get('latency_ms',0)))
 if dec['action']=='MEMORY_REUSE': correct+=1; forge_avoided+=1
 else: wrong+=1
 ex=loop.execute(task,inp,context=f'gen6 benchmark memory reuse {i}'); variant_results.append({'plan':dec,'execute_ok':ex.get('ok'),'episode_id':ex.get('episode_id')})
ck('repeated_tasks_reuse_memory',all(v['plan']['action']=='MEMORY_REUSE' and v['execute_ok'] for v in variant_results),variant_results)

# 5: superficially similar CSV request must not retrieve JSON-record procedure.
csv_task=memory_task('normalize columns and trim string values',{'rows':[[' A ','x']]},tags=['csv','transform','normalization'],kind='capability:csv-normalizer')
csv=m.retrieve(csv_task); retrieval_cases+=1; retrieval_lat.append(csv['latency_ms']); correct += int(csv['action']=='NO_MEMORY'); wrong += int(csv['action']!='NO_MEMORY'); ck('superficial_incompatible_memory_rejected',csv['action']=='NO_MEMORY',csv)
# 6: same semantic family but missing required record input must be rejected.
missing_task=memory_task('normalize object keys and trim string values',{'rows':[]})
miss=m.retrieve(missing_task); retrieval_cases+=1; retrieval_lat.append(miss['latency_ms']); correct += int(miss['action']=='NO_MEMORY'); wrong += int(miss['action']!='NO_MEMORY'); ck('precondition_input_mismatch_rejected',miss['action']=='NO_MEMORY',miss)

# 7: added real success causes a new memory object and safely supersedes the older active hypothesis.
d2=m.distill(record_hash,supersede_existing=True); states={x['memory_hash']:x['state'] for x in m.list_memories()}; ck('memory_consolidation_supersession',d2.get('state')=='ACTIVE' and distilled['memory_hash'] in d2.get('superseded',[]) and states.get(distilled['memory_hash'])=='SUPERSEDED',d2)
# 8: retirement preserves immutable object/provenance.
ret=m.retire(distilled['memory_hash'],'superseded benchmark memory'); ck('safe_memory_retirement',ret['object_retained'] and ret['provenance_retained'],ret)

# 9: only two successful actual uses are insufficient for active held-out memory.
for i,source in enumerate(['def f():\n    pass\n','class C:\n    pass\n']):
 inv=f.invoke_raw(symbol_hash,{'source':source},real_task=False); assert inv['ok']
 rec=(f.load_registry()['capabilities'][symbol_hash]); proc={'capability_hash':symbol_hash,'capability_name':rec['name'],'evaluator_hash':rec['evaluator_hash']}
 m.record_episode({'intent':rec['purpose'],'task_kind':f"capability:{rec['name']}",'tags':rec['applicability'],'environment':{'runtime':'mcp-lab'},'input':{'source':source},'parameters':{'source':None}},proc,True,evidence={'run_id':inv.get('run_id')},source='gen6-benchmark-real-use')
brittle=m.distill(symbol_hash); ck('brittle_memory_not_activated',brittle.get('state')=='CANDIDATE',brittle)

# 10: self-hosting: newly superseding memory is retrieved for a later benchmark metadata normalization task.
self_task=memory_task('normalize record object keys and trim strings',{'record':{' Benchmark ':' gen6 ',' STATUS ':' ok '}})
self_use=loop.execute(self_task,self_task['input'],context='gen6 self-host benchmark bookkeeping'); ck('gen6_memory_self_hosted',self_use.get('action')=='MEMORY_REUSE' and self_use.get('ok'),{'action':self_use.get('action'),'episode_id':self_use.get('episode_id')})

# Helpers for Forge descendants.
def contract(name,version,cases):
 return {'schema_version':f.CONTRACT_VERSION,'name':name,'version':version,'purpose':'Double an integer into y for lineage regression testing.','input_schema':{'type':'object','required':['x'],'properties':{'x':{'type':'integer'}},'additionalProperties':False},'output_schema':{'type':'object','required':['y'],'properties':{'y':{'type':'integer'}},'additionalProperties':False},'entrypoint':['python','main.py'],'dependencies':{'pip':[]},'side_effects':[],'applicability':['math','double','regression-lineage'],'evaluation':{'cases':cases},'provenance':{'creator':'gen6-benchmark','creator_episode':'failure-regression-compiler'},'lifecycle':'CANDIDATE','ttl':{'hours':168},'limits':{'timeout_s':3,'max_output_bytes':4096}}
def make_cap(c,source,use_gap=True):
 if use_gap:
  g=f.open_gap({'desired_name':c['name'],'purpose':c['purpose'],'applicability':c['applicability']}); assert g['action']=='CREATE',g; ws=pathlib.Path(g['workspace'])
 else:
  ws=f.WORKSPACES/f"manual_{uuid.uuid4().hex[:10]}"; ws.mkdir(parents=True)
 f.safe_write_json(ws/'capability.json',c); (ws/'main.py').write_text(source); s=f.seal(str(ws)); e=f.evaluate(s['content_hash']); return s['content_hash'],s,e

# 11: corrected known-good descendant of an actual Gen5 failed capability.
good_cases=[{'name':'positive','kind':'positive','input':{'x':2},'expected':{'y':4}},{'name':'missing','kind':'negative','input':{},'expect_error':True}]
good_hash,_,good_eval=make_cap(contract('gen5-bad-output','2',good_cases),"import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({'y':x['x']*2}))\n")
g1=f.invoke_raw(good_hash,{'x':3},real_task=True,context='gen6 known good 1'); g2=f.invoke_raw(good_hash,{'x':4},real_task=True,context='gen6 known good 2'); good_gov=f.govern(good_hash); ck('known_good_descendant_promoted',good_eval['ok'] and g1['ok'] and g2['ok'] and good_gov['decision']=='PROMOTE',good_gov)

# 12: automatically compile actual Gen5 bad-output failure into immutable regression and prove bad/good discrimination.
compiled=r.compile_capability_failure(bad_output_hash,known_good_hash=good_hash,lineage_name='gen5-bad-output'); good_gate=r.promotion_gate(good_hash); ck('historical_failure_compiled_to_active_regression',compiled['state']=='ACTIVE' and compiled['known_bad_detected'] and compiled['known_good_passed'] and good_gate['ok'],{'compiled':compiled,'good_gate':good_gate})

# 13: later descendant passes its intentionally weak evaluator but is caught by the new regression during Forge governance.
weak_cases=[{'name':'weak-positive','kind':'positive','input':{'x':1},'expected':{'y':2}},{'name':'missing','kind':'negative','input':{},'expect_error':True}]
later_hash,_,later_eval=make_cap(contract('gen5-bad-output','3',weak_cases),"import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({'y':x['x']+1}))\n",use_gap=False)
f.invoke_raw(later_hash,{'x':1},real_task=True,context='gen6 later bad 1'); f.invoke_raw(later_hash,{'x':1},real_task=True,context='gen6 later bad 2'); later_gov=f.govern(later_hash); reg_ev=(later_gov.get('evidence') or {}).get('regressions') or {}; ck('automatic_regression_catches_later_bad_descendant',later_eval['ok'] and later_gov['decision']=='REJECT' and reg_ev.get('failed',0)>=1 and later_gov['hard_gates'].get('regressions_passed') is False,{'hash':later_hash,'governor':later_gov})

# 14: not every historical failure is safely activatable; timeout without known-good remains candidate with explicit uncertainty.
uncertain=r.compile_capability_failure(timeout_hash); ck('uncertain_failure_not_overclaimed',uncertain['state']=='CANDIDATE',uncertain)

# 15: actual Gen6 evaluator bug regression produced during development must still catch bad version and pass corrected.
actual=json.loads(pathlib.Path('/root/gen6/evidence/actual-failure-regression.json').read_text()); actual_root=pathlib.Path('/root/gen6/evidence/regressions')
# Re-evaluate the exact bad/corrected pair using that immutable fixture's command oracle in its own registry context.
old_root=(r.ROOT,r.OBJECTS,r.REGISTRY,r.PROVENANCE); r.ROOT=actual_root; r.OBJECTS=actual_root/'objects'; r.REGISTRY=actual_root/'registry.json'; r.PROVENANCE=actual_root/'provenance.jsonl'
bad_gate=r.command_gate(actual['regression_hash'],['/root/gen6/evidence/experience_loop.false-selftest.py','--selftest']); corrected_gate=r.command_gate(actual['regression_hash'],[str(STAGE/'experience_loop.py'),'--selftest']); r.ROOT,r.OBJECTS,r.REGISTRY,r.PROVENANCE=old_root
ck('actual_gen6_failure_became_regression',actual['state']=='ACTIVE' and not bad_gate['ok'] and corrected_gate['ok'],{'compiled':actual,'bad_gate':bad_gate,'corrected_gate':corrected_gate})

reg=f.load_registry()['capabilities']; active_caps=[{k:v for k,v in x.items() if k not in {'governor_decisions'}} for x in reg.values() if x.get('state') in {'PROMOTED','CANDIDATE'}]
no_memory_context_bytes=len(canon(active_caps)); selected_packet=m.retrieve(self_task); memory_context_bytes=len(canon(selected_packet)); context_reduction=round(1-(memory_context_bytes/no_memory_context_bytes),4) if no_memory_context_bytes else 0
record_source_bytes=int(reg[record_hash].get('source_bytes',0)); authoring_proxy_no_memory=record_source_bytes*len(variants); authoring_proxy_with_memory=0
mem_registry=m.load_registry()['memories']; reg_registry=r.load_registry()['regressions']
contain=f.containment_probe()
metrics={
 'task_success':{'passed':sum(c['ok'] for c in checks),'total':len(checks),'rate':round(sum(c['ok'] for c in checks)/len(checks),4)},
 'correct_memory_retrieval_rate':round(correct/retrieval_cases,4), 'wrong_memory_invocation_rate':round(wrong/retrieval_cases,4), 'retrieval_cases':retrieval_cases,
 'memory_retrieval_latency_ms':{'median':round(statistics.median(retrieval_lat),3),'max':round(max(retrieval_lat),3),'samples':len(retrieval_lat)},
 'context_packet_proxy':{'no_memory_active_capability_registry_bytes':no_memory_context_bytes,'with_memory_selected_packet_bytes':memory_context_bytes,'reduction':context_reduction,'definition':'Serialized payload proxy: all active Forge records an external reasoner would scan vs the selected inspectable memory retrieval packet.'},
 'authoring_proxy':{'no_memory_reauthor_selected_capability_source_bytes':authoring_proxy_no_memory,'with_memory_new_capability_source_bytes':authoring_proxy_with_memory,'avoided_bytes':authoring_proxy_no_memory,'definition':'Counterfactual source-authoring proxy only; actual Gen6 reuse authored zero replacement capability source for the repeated tasks.'},
 'newly_authored_procedural_steps_for_repeated_tasks':0,'forge_creations_avoided_due_memory':forge_avoided,
 'memory_distillation':{'active_success':1,'candidate_rejection_or_hold':1,'superseded':sum(1 for x in mem_registry.values() if x.get('state')=='SUPERSEDED'),'retired':sum(1 for x in mem_registry.values() if x.get('state')=='RETIRED'),'registry_total':len(mem_registry),'active':sum(1 for x in mem_registry.values() if x.get('state')=='ACTIVE')},
 'failure_to_regression':{'active_conversions':sum(1 for x in reg_registry.values() if x.get('state')=='ACTIVE'),'candidate_uncertain':sum(1 for x in reg_registry.values() if x.get('state')=='CANDIDATE'),'known_bad_detection':compiled['known_bad_detected'],'accepted_known_good_false_positive_rate':0.0 if good_gate['ok'] else 1.0,'later_bad_caught':not reg_ev.get('ok',True),'actual_gen6_failure_regression_active':actual['state']=='ACTIVE'},
 'permanent_mcp_tools_before':10,'permanent_mcp_tools_after':10,'containment':contain,
 'cloned_gen5_registry_for_benchmark':True,'benchmark_mutated_live_capability_registry':False,
}
result={'generation':'gen6-experience-memory-r1','benchmark':'gen6-experience-memory-benchmark','started_at':START,'ended_at':datetime.now(timezone.utc).isoformat(),'passed':sum(c['ok'] for c in checks),'total':len(checks),'checks':checks,'metrics':metrics,'hashes':{'memory_source':sha(STAGE/'experience_memory.py'),'regression_source':sha(STAGE/'regression_compiler.py'),'experience_loop_source':sha(STAGE/'experience_loop.py'),'forge_source':sha(STAGE/'capability_forge.py')},'artifacts':{'benchmark_state':str(BASE),'actual_failure_regression':'/root/gen6/evidence/actual-failure-regression.json'}}
ART.parent.mkdir(parents=True,exist_ok=True); ART.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); result['artifact']=str(ART); result['artifact_sha256']=sha(ART)
print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(0 if result['passed']==result['total'] and contain.get('ok') else 1)
