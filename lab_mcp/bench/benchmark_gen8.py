#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations
import hashlib, importlib.util, json, pathlib, statistics, time
from copy import deepcopy
from datetime import datetime, timezone

ROOT=pathlib.Path('/opt/optiplex-lab')
STATE=pathlib.Path('/var/lib/optiplex-lab')
GEN8=STATE/'gen8'
GOLD=GEN8/'GEN8_GOLD.json'
ART=STATE/'benchmarks/gen8-context-compiler-capsule-benchmark.json'
TWIN=STATE/'twin/twin-current.json'
PRE=GEN8/'PROTECTED_PRE_RETAINED.json'
GEN5_CAP=pathlib.Path('/var/tmp/optiplex-lab-capsules/cap8_20260826T152539Z_a2d9178c/result.json')
GEN5_ART=pathlib.Path('/var/tmp/optiplex-lab-capsules/cap8_20260826T152539Z_a2d9178c/export/captures/var/lib/optiplex-lab/benchmarks/gen5-capability-forge-benchmark.json')
GEN4_CAP=pathlib.Path('/var/tmp/optiplex-lab-capsules/cap8_20260826T160908Z_a0fba037/result.json')
GEN4_ART=pathlib.Path('/var/tmp/optiplex-lab-capsules/cap8_20260826T160908Z_a0fba037/export/captures/var/lib/optiplex-lab/benchmarks/gen4-workflow-graph-benchmark.json')

def loadmod(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
cc=loadmod(ROOT/'context_compiler.py','gen8_cc_bench')
cap=loadmod(ROOT/'experiment_capsule.py','gen8_cap_bench')

def j(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

gold=j(GOLD); snap=j(TWIN); checks=[]; case_results=[]; lat=[]
def ck(name,ok,detail=None): checks.append({'name':name,'ok':bool(ok),'detail':detail})
def ids(packet): return {r['evidence_id'] for r in packet['selected_evidence_records']}
def kinds(packet): return {r['kind'] for r in packet['selected_evidence_records']}
def compile_case(task,budget=48000,allow_expand=True,snapshot=None):
    t=time.monotonic(); p=cc.build_packet(task,budget_bytes=budget,allow_expand=allow_expand,snapshot_override=snapshot); lat.append((time.monotonic()-t)*1000); return p

# 1-7: frozen independent gold cases.
tp=fp=fn=0; all_required=0; all_selected=0; negative_ok=True; kinds_ok=True
packets={}
for case in gold['cases']:
    p=compile_case(case['task']); packets[case['id']]=p
    selected=ids(p); req=set(case.get('required_ids',[])); missing=sorted(req-selected)
    any_ids=set(case.get('required_any_ids',[])); any_ok=(not any_ids) or bool(selected & any_ids)
    req_k=set(case.get('required_kinds',[])); kind_ok=req_k.issubset(kinds(p)); forbidden=sorted(selected & set(case.get('forbidden_ids',[])))
    ok=not missing and any_ok and kind_ok and not forbidden and p['task_kind']==case['task_kind'] and not p['fail_closed']
    critical_pred={r['evidence_id'] for r in p['selected_evidence_records'] if int(r['priority_tier'])<=1}
    tp += len(critical_pred & req); fp += len(critical_pred-req); fn += len(req-critical_pred)
    all_required += len(req); all_selected += len(selected); negative_ok &= not forbidden; kinds_ok &= p['task_kind']==case['task_kind']
    case_results.append({'id':case['id'],'ok':ok,'task_kind':p['task_kind'],'packet_id':p['packet_id'],'packet_digest':p['packet_digest'],'bytes':p['budget']['bytes_used'],'tokens':p['budget']['token_estimate'],'selected':sorted(selected),'required':sorted(req),'missing':missing,'forbidden_present':forbidden,'required_any_ok':any_ok,'required_kinds_ok':kind_ok,'fail_closed':p['fail_closed']})
    ck('gold_'+case['id'],ok,case_results[-1])

# 8: stale/missing critical evidence fails closed and broadens while retaining Tier 0.
stale=deepcopy(snap)
for n in stale['nodes']:
    if n.get('id')=='source:/opt/optiplex-lab/experience_loop.py': n['source_path']='/tmp/gen8-benchmark-missing-critical.py'
sp=compile_case(gold['cases'][0]['task'],snapshot=stale)
stale_ok=sp['fail_closed'] and sp['controlled_broad_fallback'] and {'authority:guest-security-boundary','operational:accepted-identity'}.issubset(ids(sp)) and any((u.get('freshness') or {}).get('state')=='missing' for u in sp['uncertainties'])
ck('stale_missing_fails_closed_or_broadens',stale_ok,{'fail_closed':sp['fail_closed'],'fallback':sp['controlled_broad_fallback'],'uncertainties':sp['uncertainties'][:4]})

# 9: contradictory authoritative evidence is visible and fail-closed.
contr=deepcopy(snap); src=next(n for n in contr['nodes'] if n.get('id')=='build_state:current'); dup=deepcopy(src); dup['id']='build_state:gen8-contradiction-control'; dup['generation']='contradiction-control'; contr['nodes'].append(dup)
cp=compile_case('Explain lifecycle recovery build metadata.',snapshot=contr)
contr_ok=cp['fail_closed'] and bool(cp['contradictions']) and 'warning:contradictory-authoritative-evidence' in ids(cp)
ck('contradiction_surfaced_not_collapsed',contr_ok,{'contradictions':cp['contradictions'][:3],'fail_closed':cp['fail_closed']})

# 10: budget pressure prunes optional evidence before any high-priority evidence.
high=packets['architecture-experience-loop']; highcrit={r['evidence_id'] for r in high['selected_evidence_records'] if int(r['priority_tier'])<=1}; highopt={r['evidence_id'] for r in high['selected_evidence_records'] if int(r['priority_tier'])>1}
found=None
for budget in range(max(8000,high['budget']['bytes_used']-2000),7999,-1000):
    q=compile_case(gold['cases'][0]['task'],budget=budget,allow_expand=False)
    if not q['fail_closed'] and highcrit.issubset(ids(q)) and len(ids(q)&highopt)<len(highopt): found=q; break
budget_ok=found is not None
ck('budget_prunes_optional_before_critical',budget_ok,{'high_bytes':high['budget']['bytes_used'],'high_critical':len(highcrit),'high_optional':len(highopt),'low':None if not found else {'budget':found['budget'],'selected':len(ids(found)),'optional_retained':len(ids(found)&highopt)}})

# 11: deterministic unchanged inputs.
a=compile_case(gold['cases'][1]['task']); b=compile_case(gold['cases'][1]['task'])
det_ok=a['packet_digest']==b['packet_digest'] and a['packet_id']==b['packet_id'] and a['selected_evidence_records']==b['selected_evidence_records']
ck('deterministic_unchanged_inputs',det_ok,{'packet_id':a['packet_id'],'digest':a['packet_digest']})

# 12: answer/task correctness using only packet content for representative modes.
arch=packets['architecture-experience-loop']; life=packets['lifecycle-server']; mem=packets['memory-repeat-normalizer']; dbg=packets['debug-active-regression']
arch_answer={'owner_present':'source:/opt/optiplex-lab/experience_loop.py' in ids(arch),'validators':sorted(arch['validations'])}
life_oper=next((r['structured_fact'] for r in life['selected_evidence_records'] if r['evidence_id']=='operational:accepted-identity'),{})
answer_ok=(arch_answer['owner_present'] and {'validation:selftest:experience_loop','validation:benchmark:benchmark_gen6','validation:benchmark:benchmark_gen7'}.issubset(set(arch_answer['validators'])) and life_oper.get('permanent_mcp_tools')==10 and {'recovery:last-known-good','service:optiplex-lab-mcp.service','build_state:current'}.issubset(set(life['recovery_requirements'])) and 'memory:dee53db47c22a5b338924a9828d95e6cc38319dbaeadf74083e752dc892f0ea5' in mem['memories'] and bool(dbg['causal_evidence']))
ck('task_correctness_from_compiled_context_only',answer_ok,{'architecture_answer':arch_answer,'lifecycle_tools':life_oper.get('permanent_mcp_tools'),'recovery':life['recovery_requirements'],'memory':mem['memories'],'causal':dbg['causal_evidence']})

# 13: critical-evidence ablation: removing the authoritative owner breaks the packet-only architecture answer; removing optional support does not.
owner='source:/opt/optiplex-lab/experience_loop.py'
def architecture_answer_ok(records):
    rr={r['evidence_id'] for r in records}; vv={r['evidence_id'] for r in records if r['kind'] in {'validation','benchmark_artifact','evaluator'}}
    return owner in rr and {'validation:selftest:experience_loop','validation:benchmark:benchmark_gen6','validation:benchmark:benchmark_gen7'}.issubset(vv)
base_records=arch['selected_evidence_records']; no_owner=[r for r in base_records if r['evidence_id']!=owner]; no_optional=[r for r in base_records if int(r['priority_tier'])<=1]
ablation_ok=architecture_answer_ok(base_records) and not architecture_answer_ok(no_owner) and architecture_answer_ok(no_optional)
ck('critical_evidence_ablation',ablation_ok,{'baseline':architecture_answer_ok(base_records),'without_owner':architecture_answer_ok(no_owner),'without_optional':architecture_answer_ok(no_optional)})

# 14: known Gen5 leak case is contained and benchmark itself passes 12/12.
g5=j(GEN5_CAP); g5a=j(GEN5_ART); gen5_ok=g5['ok'] and g5['accepted_state_unchanged'] and not g5['forbidden_accepted_state_mutations'] and g5a.get('passed')==12 and g5a.get('total')==12 and g5a.get('required_capabilities_absent_at_start') is True
ck('gen5_forge_leak_contained',gen5_ok,{'capsule_run':g5['run_id'],'passed':g5a.get('passed'),'total':g5a.get('total'),'forbidden':g5['forbidden_accepted_state_mutations'],'audit':g5.get('allowed_outer_audit_appends')})

# 15: known Gen4 absolute build/service lifecycle case is contained and passes 18/18.
g4=j(GEN4_CAP); g4a=j(GEN4_ART); gen4_ok=g4['ok'] and g4['accepted_state_unchanged'] and not g4['forbidden_accepted_state_mutations'] and (g4a.get('summary') or {}).get('passed')==18 and (g4a.get('summary') or {}).get('total')==18 and (g4a.get('summary') or {}).get('final_live_equals_lkg') is True
ck('gen4_absolute_build_leak_contained',gen4_ok,{'capsule_run':g4['run_id'],'summary':g4a.get('summary'),'forbidden':g4['forbidden_accepted_state_mutations'],'audit':g4.get('allowed_outer_audit_appends')})

# 16: identical capsule recipe is reproducible on unchanged inputs.
r1=cap.run_capsule("printf 'GEN8_REPRO_OK\\n'",label='gen8-repro-control'); r2=cap.run_capsule("printf 'GEN8_REPRO_OK\\n'",label='gen8-repro-control')
repro_ok=r1['ok'] and r2['ok'] and r1['recipe_digest']==r2['recipe_digest'] and r1['capsule_mutation_digest']==r2['capsule_mutation_digest'] and r1['stdout']['sha256']==r2['stdout']['sha256'] and not r1['forbidden_accepted_state_mutations'] and not r2['forbidden_accepted_state_mutations']
ck('capsule_reproducible_identical_recipe',repro_ok,{'runs':[r1['run_id'],r2['run_id']],'recipe_digests':[r1['recipe_digest'],r2['recipe_digest']],'mutation_digests':[r1['capsule_mutation_digest'],r2['capsule_mutation_digest']],'stdout_sha256':[r1['stdout']['sha256'],r2['stdout']['sha256']]})

# 17: context reduction against broad authoritative-read and practical fresh-session source baselines, plus permanent surface invariant.
source_nodes=[n for n in snap['nodes'] if n.get('kind')=='source' and n.get('authoritative') and isinstance(n.get('source_bytes'),int)]
unique={n.get('source_path'):int(n['source_bytes']) for n in source_nodes if n.get('source_path')}; broad=sum(unique.values())
practical_names=['architecture_twin.py','causal_spine.py','experience_loop.py','experience_memory.py','regression_compiler.py','capability_forge.py','workflow_graphs.py','workflow_skills.py','code_mode.py','server.py']
practical=sum(p.stat().st_size for name in practical_names if (p:=ROOT/name).is_file())
packet_bytes=[x['bytes'] for x in case_results]; avg=round(statistics.mean(packet_bytes),2); med=statistics.median(packet_bytes)
reduction={'broad_baseline_bytes':broad,'practical_baseline_bytes':practical,'average_packet_bytes':avg,'median_packet_bytes':med,'broad_reduction':round(1-avg/broad,3) if broad else None,'practical_reduction':round(1-avg/practical,3) if practical else None}
tool_ok=all(next((r['structured_fact'].get('permanent_mcp_tools') for r in p['selected_evidence_records'] if r['evidence_id']=='operational:accepted-identity'),None)==10 for p in packets.values())
reduction_ok=broad>avg and practical>avg and tool_ok
ck('context_reduction_and_permanent_tool_surface',reduction_ok,reduction|{'permanent_mcp_tools':10 if tool_ok else 'mismatch'})

precision=tp/(tp+fp) if tp+fp else 1.0; recall=tp/(tp+fn) if tp+fn else 1.0
lat_sorted=sorted(lat); p95=lat_sorted[min(len(lat_sorted)-1,max(0,int(len(lat_sorted)*0.95)-1))] if lat_sorted else 0
metrics={'gold_sha256':sha(GOLD),'context_selection_precision':round(precision,4),'required_evidence_recall':round(recall,4),'critical_evidence_tp':tp,'critical_evidence_fp':fp,'critical_evidence_fn':fn,'unrelated_context_negative_controls_ok':negative_ok,'task_kind_classification_ok':kinds_ok,'compile_latency_ms':{'median':round(statistics.median(lat),3),'p95':round(p95,3),'max':round(max(lat),3)},'packet_bytes':{'average':avg,'median':med,'min':min(packet_bytes),'max':max(packet_bytes)},'context_reduction':reduction,'permanent_mcp_tools':10 if tool_ok else None,'gen4_capsule_run':g4['run_id'],'gen5_capsule_run':g5['run_id'],'repro_capsule_runs':[r1['run_id'],r2['run_id']]}
passed=sum(1 for x in checks if x['ok']); result={'timestamp':datetime.now(timezone.utc).isoformat(),'version':'gen8-context-capsule-benchmark-r1','gold_frozen_before_evaluation':gold.get('frozen_before_evaluation'),'gold_sha256':sha(GOLD),'checks':checks,'cases':case_results,'metrics':metrics,'passed':passed,'total':len(checks)}
ART.parent.mkdir(parents=True,exist_ok=True); ART.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'output':str(ART),'passed':passed,'total':len(checks),'metrics':metrics},indent=2,sort_keys=True))
raise SystemExit(0 if passed==len(checks) and fn==0 else 1)
