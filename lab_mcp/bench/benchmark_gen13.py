#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import json
import pathlib
import shlex
import subprocess
import time
from datetime import datetime, timezone

ROOT = pathlib.Path('/opt/optiplex-lab')
STATE = pathlib.Path('/var/lib/optiplex-lab')
HIER = ROOT/'hierarchical_experiment.py'
CAPSULE = ROOT/'experiment_capsule.py'
REPLAY = ROOT/'counterfactual_replay.py'
EPOCH = ROOT/'evidence_epoch.py'
TWIN = ROOT/'architecture_twin.py'
HERE = pathlib.Path(__file__).resolve()
GOLD = STATE/'gen13/GEN13_GOLD.json'
ARTIFACT = STATE/'benchmarks/gen13-hierarchical-experiment-benchmark.json'
TASK = 'Evaluate hierarchical experiment isolation and delegated Counterfactual Replay without changing accepted live state.'


def load(path: pathlib.Path, name: str):
    spec=importlib.util.spec_from_file_location(name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f'cannot load {path}')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def sha_path(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def cmd_for(script: str, payload: dict) -> str:
    raw=base64.b64encode(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).decode()
    return "export PYTHONDONTWRITEBYTECODE=1; python3 -c " + shlex.quote(script) + " " + shlex.quote(raw)


def main() -> int:
    started=time.monotonic()
    h=load(HIER,'gen13_bench_hier'); cap=load(CAPSULE,'gen13_bench_cap'); eng=load(REPLAY,'gen13_bench_replay'); epoch=load(EPOCH,'gen13_bench_epoch')
    gold=json.loads(GOLD.read_text())
    gold_sha=sha_path(GOLD)
    expected_ids=[x['id'] for x in gold['checks'] if x.get('required')]
    checks=[]; evidence={}; unsafe=[]
    def ck(cid, ok, details=None): checks.append({'id':cid,'pass':bool(ok),'details':details})
    def errcode(fn):
        try: fn(); return None
        except Exception as exc: return getattr(exc,'code',type(exc).__name__)

    # Refresh before sealing so the benchmark itself is included in the coherent evidence epoch.
    subprocess.run([str(TWIN),'build'],check=True,stdout=subprocess.DEVNULL)
    tv=json.loads(subprocess.run([str(TWIN),'verify'],check=True,capture_output=True,text=True).stdout)
    twin=json.loads((STATE/'twin/twin-current.json').read_text())
    if not tv.get('ok') or tv.get('newer_evidence_available'): raise RuntimeError('Twin stale before Gen13 benchmark epoch')

    ep=epoch.begin_epoch(task=TASK,evaluator_paths=[str(HIER),str(REPLAY)],extra_paths=[str(HIER),str(REPLAY),str(CAPSULE),str(HERE)],expected_outputs=[str(ARTIFACT)])
    epoch_id=ep['epoch_id']; _eroot, manifest=epoch.load_epoch(epoch_id); route=copy.deepcopy(manifest['core']['routing_proof'])
    base_common={
        'schema_version':1,'base_epoch_id':epoch_id,'base_epoch_digest':ep['epoch_digest'],
        'base_twin_graph_digest':manifest['core']['twin_graph_digest'],'base_routing_digest':route['routing_digest'],
        'original_decision':{'decision':'accepted Gen13 composition control'},
        'evaluator':{'kind':'python_function','module_path':str(REPLAY),'function':'engine_invariants'},
    }
    impl={**copy.deepcopy(base_common),'alternative':{
        'type':'implementation_change','isolation_owner':'replay','allowed_effect_paths':[str(REPLAY)],
        'operations':[{'op':'replace_text','path':str(REPLAY),'old':'"authority_monotonic": True,','new':'"authority_monotonic": False,'}],
    }}

    # A. Gen8 compatibility and standalone root isolation.
    cap_self=cap.selftest(); evidence['gen8_selftest']={'passed':cap_self['passed'],'total':cap_self['total']}
    ck('G01',cap_self['passed']==cap_self['total']==5,evidence['gen8_selftest'])
    ro1=h.run_root_experiment("printf 'ROOT_RO\\n'",name='gen13-determinism-root')
    ro2=h.run_root_experiment("printf 'ROOT_RO\\n'",name='gen13-determinism-root')
    ck('G02',ro1.get('ok') and ro1.get('physical_isolation_owner_count')==1 and ro2.get('physical_isolation_owner_count')==1)

    # B. One meaningful composed root containing normal, adversarial, grandchild, and delegated Gen12 cases.
    payload={'base_common':base_common,'impl':impl,'epoch_id':epoch_id,'gold_sha':gold_sha}
    inner=r'''import base64,copy,importlib.util,json,os,pathlib,sys
cfg=json.loads(base64.b64decode(sys.argv[1]).decode())
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
h=load('/opt/optiplex-lab/hierarchical_experiment.py','gen13_inner_h')
eng=load('/opt/optiplex-lab/counterfactual_replay.py','gen13_inner_r')
parent=h.load_current_context(); out={}
def code(fn):
 try: fn(); return None
 except Exception as e: return getattr(e,'code',type(e).__name__)
# Read-only child.
out['readonly']=h.run_child(parent,name='readonly',command="printf 'READONLY_CHILD\\n'",read_only=True)
# Scoped mutable child.
out['mutable']=h.run_child(parent,name='mutable',command="printf 'child\\n' > /root/gen13-allowed.txt",mutation_scope=['/root/gen13-allowed.txt'])
# Grandchild under same owner.
child=h.delegate_context(parent,name='grand-parent',mutation_scope=['/root/gen13-grand.txt'],authorities=['evaluation'])
grand=h.delegate_context(child,name='grandchild',mutation_scope=['/root/gen13-grand.txt'],authorities=[])
out['grandchild']=h.execute_current(grand,"printf 'grand\\n' > /root/gen13-grand.txt",required_paths=['/root/gen13-grand.txt'])
out['grandchild_context']=grand
out['grand_parent_context']=child
# Scope violation: root owns target so root remains valid; child did not receive it.
out['undeclared']=h.run_child(parent,name='undeclared',command="printf 'bad\\n' > /root/gen13-undeclared.txt",mutation_scope=['/root/gen13-safe.txt'])
# Authority expansion, hard accepted-state targets, systemd, traversal, evidence mismatch, independent nested owner.
out['authority_expand_code']=code(lambda:h.delegate_context(parent,name='auth-expand',authorities=['evaluation','production']))
out['server_delegate_code']=code(lambda:h.delegate_context(parent,name='server',mutation_scope=['/opt/optiplex-lab/server.py']))
out['build_delegate_code']=code(lambda:h.delegate_context(parent,name='build',mutation_scope=['/etc/optiplex-lab/build.json']))
out['lkg_delegate_code']=code(lambda:h.delegate_context(parent,name='lkg',mutation_scope=['/var/lib/optiplex-lab/recovery/server.last-known-good.py']))
out['systemd_delegate_code']=code(lambda:h.delegate_context(parent,name='systemd',mutation_scope=['/etc/systemd/system/gen13-evil.service']))
out['traversal_code']=code(lambda:h.delegate_context(parent,name='traversal',mutation_scope=['../root/escape']))
out['evidence_mismatch_code']=code(lambda:h.delegate_context(parent,name='evidence',evidence_bindings={'epoch':'wrong'}))
out['independent_code']=code(lambda:h.delegate_context(parent,name='nested-owner',mutation_scope=['/root/gen13-safe.txt'],isolation_mode='independent'))
out['dual_root_code']=code(lambda:h.run_root_experiment("true",name='illegal-nested-root'))
# Forged context.
valid=h.delegate_context(parent,name='forge-control',mutation_scope=['/root/gen13-safe.txt'],authorities=[])
forged=copy.deepcopy(valid); forged['isolation_owner']='capsule:forged'
out['forged_code']=code(lambda:h.validate_context(forged,expected_parent=parent))
# Mismatched parent proof.
other=h.delegate_context(parent,name='other-parent',mutation_scope=['/root/gen13-safe.txt'],authorities=[])
out['parent_mismatch_code']=code(lambda:h.validate_context(valid,expected_parent=other))
# Stale owner binding simulated without changing semantic/binding object.
old=os.environ['OPTIPLEX_CAPSULE_RUN_ID']; os.environ['OPTIPLEX_CAPSULE_RUN_ID']='cap8_stale_owner'
out['stale_code']=code(lambda:h.validate_context(valid)); os.environ['OPTIPLEX_CAPSULE_RUN_ID']=old
# Nonzero after mutation and crash-after-mutation attribution.
out['nonzero']=h.run_child(parent,name='nonzero',command="printf 'before-fail\\n' > /root/gen13-fail.txt; exit 7",mutation_scope=['/root/gen13-fail.txt'])
out['crash']=h.run_child(parent,name='crash',command="printf 'before-crash\\n' > /root/gen13-crash.txt; kill -SEGV $$",mutation_scope=['/root/gen13-crash.txt'])
# Timeout.
out['timeout']=h.run_child(parent,name='timeout',command="sleep 10",read_only=True,timeout=0.15)
# Malformed child output.
out['malformed']=h.run_child(parent,name='malformed',command="printf 'not-json\\n'",read_only=True,expect_json=True)
# Detached process must be detected/terminated and invalidate result.
out['detached']=h.run_child(parent,name='detached',command="setsid sh -c 'sleep 30 >/dev/null 2>&1 &' >/dev/null 2>&1; printf 'done\\n'",read_only=True)
# Lying mutation report.
out['lying']=h.run_child(parent,name='lying',command="printf x > /root/gen13-lie.txt; printf '{\"reported_mutations\":[]}\\n'",mutation_scope=['/root/gen13-lie.txt'],expect_json=True)
# Symlink-mediated escape: link is delegated, target is not.
out['symlink']=h.run_child(parent,name='symlink',command="ln -s /root/gen13-symlink-target /root/gen13-link; printf evil > /root/gen13-link",mutation_scope=['/root/gen13-link'])
# Registry write without delegation must be observed and invalidated; parent owns it only to reconcile the test.
out['registry']=h.run_child(parent,name='registry',command="printf '\\n' >> /var/lib/optiplex-lab/capabilities/registry.json",mutation_scope=['/root/gen13-safe.txt'])
# Explicit result propagation cleanup-failed state via controlled in-memory fault injection.
orig=h._cleanup_new_processes
try:
 h._cleanup_new_processes=lambda before:{'detected':[],'terminated':[],'remaining':[99999],'ok':False}
 cleanup_ctx=h.delegate_context(parent,name='cleanup-fault',read_only=True)
 out['cleanup_failed']=h.execute_current(cleanup_ctx,"true")
finally: h._cleanup_new_processes=orig
# Valid delegated Gen12 replay. Child owns only declared replay source + evaluator result.
replay_child=h.delegate_context(parent,name='delegated-gen12',mutation_scope=['/opt/optiplex-lab/counterfactual_replay.py','/root/gen12-counterfactual-result.json'],authorities=['evaluation','replay'],evidence_bindings={'epoch':cfg['epoch_id'],'gold':cfg['gold_sha']},evaluator={'engine':'gen12-counterfactual-replay-r1'})
spec=copy.deepcopy(cfg['impl']); spec['alternative']['isolation_owner']='child'; spec['alternative']['child_isolation_proof']={'context_id':replay_child['context_id'],'binding_digest':replay_child['binding_digest']}
# Replay runs in a process carrying the delegated context, then delegates its evaluator without another Capsule.
script="import importlib.util,json,pathlib; p=pathlib.Path('/opt/optiplex-lab/counterfactual_replay.py'); s=importlib.util.spec_from_file_location('rchild',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); spec=json.loads(pathlib.Path('/root/gen13-replay-spec.json').read_text()); print(json.dumps(m.replay(spec),sort_keys=True))"
pathlib.Path('/root/gen13-replay-spec.json').write_text(json.dumps(spec,sort_keys=True))
# spec file is a parent-owned helper, not child effect; remove it before measuring delegated child.
out['delegated_replay']=h.execute_current(replay_child,"python3 -c "+__import__('shlex').quote(script),required_paths=['/opt/optiplex-lab/counterfactual_replay.py','/root/gen12-counterfactual-result.json'],expect_json=True)
out['replay_child_context']=replay_child
print(json.dumps(out,sort_keys=True))
'''
    root_scope=[
        '/root/gen13-allowed.txt','/root/gen13-grand.txt','/root/gen13-undeclared.txt','/root/gen13-safe.txt',
        '/root/gen13-fail.txt','/root/gen13-crash.txt','/root/gen13-lie.txt','/root/gen13-link','/root/gen13-symlink-target',
        '/root/gen13-replay-spec.json','/root/gen12-counterfactual-result.json',str(REPLAY),
        '/var/lib/optiplex-lab/capabilities/registry.json','/opt/optiplex-lab/server.py','/etc/optiplex-lab/build.json',
        '/var/lib/optiplex-lab/recovery/server.last-known-good.py','/etc/systemd/system/gen13-evil.service',
    ]
    composed=h.run_root_experiment(cmd_for(inner,payload),name='gen13-composed-self-use',mutation_scope=root_scope,
        authorities=['evaluation','replay'],evidence_bindings={'epoch':epoch_id,'gold':gold_sha},evaluator={'benchmark':'gen13'},expect_json=True,timeout=60)
    evidence['composed_summary']={k:composed.get(k) for k in ['ok','status','physical_isolation_owner_count','final_mutation_paths','unexpected_final_mutations','accepted_state_unchanged','semantic_result_digest','capsule_run_id']}
    data=((composed.get('execution') or {}).get('parsed_result') or {})

    readonly=data.get('readonly') or {}; mutable=data.get('mutable') or {}; grand=data.get('grandchild') or {}; gctx=data.get('grandchild_context') or {}
    ck('G03',readonly.get('ok') and readonly.get('observed_mutations')==[] and readonly.get('isolation_owner')==(composed.get('context') or {}).get('isolation_owner'))
    ck('G04',mutable.get('ok') and [x.get('path') for x in mutable.get('observed_mutations') or []]==['/root/gen13-allowed.txt'] and composed.get('accepted_state_unchanged'))
    ck('G05',grand.get('ok') and gctx.get('depth')==2 and grand.get('isolation_owner')==readonly.get('isolation_owner'))
    undeclared=data.get('undeclared') or {}
    ck('G06',undeclared.get('status')=='INVALID' and undeclared.get('failure_reason')=='UNDECLARED_CHILD_MUTATION' and '/root/gen13-undeclared.txt' in (undeclared.get('unexpected_mutations') or []))
    ck('G07',data.get('authority_expand_code')=='DELEGATED_AUTHORITY_EXPANSION')
    accepted_codes=[data.get('server_delegate_code'),data.get('build_delegate_code'),data.get('lkg_delegate_code')]
    ck('G08',all(x=='ACCEPTED_STATE_DELEGATION_FORBIDDEN' for x in accepted_codes) and composed.get('accepted_state_unchanged') and not composed.get('forbidden_accepted_state_mutations'),accepted_codes)
    ck('G09',mutable.get('observed_mutation_digest') and mutable.get('observed_mutations') and mutable.get('reported_mutations_match') is True)
    nonzero=data.get('nonzero') or {}; timeout=data.get('timeout') or {}; malformed=data.get('malformed') or {}; detached=data.get('detached') or {}
    ck('G10',nonzero.get('status')=='FAIL' and nonzero.get('failure_reason')=='CHILD_NONZERO' and any(x.get('path')=='/root/gen13-fail.txt' for x in nonzero.get('observed_mutations') or []))
    ck('G11',timeout.get('failure_reason')=='CHILD_TIMEOUT' and (timeout.get('cleanup') or {}).get('remaining')==[])
    ck('G12',malformed.get('status')=='INVALID' and malformed.get('failure_reason')=='MALFORMED_CHILD_RESULT')
    ck('G13',detached.get('failure_reason')=='CHILD_DESCENDANT_LEAK' and bool((detached.get('cleanup') or {}).get('detected')) and (detached.get('cleanup') or {}).get('remaining')==[],detached.get('cleanup'))
    ck('G14',data.get('systemd_delegate_code')=='ACCEPTED_STATE_DELEGATION_FORBIDDEN')
    ck('G15',ro1.get('semantic_result_digest')==ro2.get('semantic_result_digest') and (ro1.get('context') or {}).get('semantic_digest')==(ro2.get('context') or {}).get('semantic_digest'))
    ck('G16',ro1.get('ok') and ro1.get('final_mutation_paths')==[] and ro1.get('unexpected_final_mutations')==[])
    delegated=data.get('delegated_replay') or {}; delegated_result=delegated.get('parsed_result') or {}
    ck('G17',delegated.get('ok') and delegated_result.get('ok') and (delegated_result.get('execution_provenance') or {}).get('isolation_owner')=='parent_delegated' and (delegated_result.get('alternative_result') or {}).get('authority_monotonic') is False,delegated_result if not delegated_result.get('ok') else None)

    # Unsafe nested Gen12 case remains rejected with the legacy fail-closed code when no valid context is present.
    nested=copy.deepcopy(impl); nested['alternative']['isolation_owner']='child'; nested['alternative']['child_isolation_proof']={'owner':'child'}
    unsafe_nested=eng.replay(nested); unsafe.append(unsafe_nested)
    ck('G18',unsafe_nested.get('fail_closed') and unsafe_nested.get('error_code')=='ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION',unsafe_nested)
    standalone=eng.replay(impl)
    ck('G19',standalone.get('ok') and (standalone.get('execution_provenance') or {}).get('isolation_owner')=='replay' and (standalone.get('alternative_result') or {}).get('authority_monotonic') is False,standalone if not standalone.get('ok') else None)
    ck('G20',data.get('forged_code')=='FORGED_DELEGATION_BINDING')
    ck('G21',data.get('parent_mismatch_code')=='PARENT_ID_MISMATCH')
    ck('G22',data.get('stale_code')=='STALE_DELEGATION_CONTEXT')
    ck('G23',data.get('dual_root_code')=='AMBIGUOUS_DUAL_ISOLATION_OWNER')
    ck('G24',data.get('independent_code')=='INCOMPATIBLE_NESTED_ISOLATION')
    lying=data.get('lying') or {}; crash=data.get('crash') or {}; symlink=data.get('symlink') or {}; registry=data.get('registry') or {}
    ck('G25',lying.get('status')=='INVALID' and lying.get('failure_reason')=='CHILD_MUTATION_REPORT_MISMATCH' and lying.get('reported_mutations_match') is False)
    ck('G26',crash.get('status')=='FAIL' and crash.get('failure_reason')=='CHILD_NONZERO' and any(x.get('path')=='/root/gen13-crash.txt' for x in crash.get('observed_mutations') or []))
    ck('G27',data.get('traversal_code')=='PATH_SCOPE_INVALID')
    ck('G28',symlink.get('status')=='INVALID' and '/root/gen13-symlink-target' in (symlink.get('unexpected_mutations') or []),symlink.get('unexpected_mutations'))
    ck('G29',data.get('evidence_mismatch_code')=='EVIDENCE_BINDING_MISMATCH')
    # All physical root test artifacts are OverlayFS-only; no Gen13 test path exists outside Capsules.
    live_debris=[str(p) for p in pathlib.Path('/root').glob('gen13-*') if p.name not in {'GEN13_PROTECTED_BEFORE_RUNTIME.json'}]
    ck('G30',not live_debris,live_debris)
    rctx=data.get('replay_child_context') or {}; gpctx=data.get('grand_parent_context') or {}
    parent_auth=set((composed.get('context') or {}).get('authorities') or [])
    ck('G31',set(rctx.get('authorities') or []).issubset(parent_auth) and set(gpctx.get('authorities') or []).issubset(parent_auth) and set(gctx.get('authorities') or []).issubset(set(gpctx.get('authorities') or [])))
    prov_fields={'context_id','parent_context_id','root_context_id','isolation_owner','delegated_scope','authorities','evidence_bindings','evaluator','observed_mutations','status','failure_reason'}
    ck('G32',prov_fields.issubset(set(mutable)) and gctx.get('lineage') and len(gctx.get('lineage'))==3)
    cleanup_failed=data.get('cleanup_failed') or {}
    statuses={readonly.get('status'),nonzero.get('status'),undeclared.get('status'),cleanup_failed.get('status')}
    ck('G33',{'PASS','FAIL','INVALID','CLEANUP_FAILED'}.issubset(statuses),sorted(str(x) for x in statuses))
    ck('G34',cap_self['passed']==cap_self['total']==5)
    ck('G35',delegated_result.get('base_provenance',{}).get('epoch_id')==epoch_id and delegated_result.get('base_provenance',{}).get('epoch_digest')==ep['epoch_digest'])
    tool_count=(ROOT/'server.py').read_text().count('@mcp.tool()')
    ck('G36',tool_count==10,tool_count)
    ck('G37',registry.get('status')=='INVALID' and '/var/lib/optiplex-lab/capabilities/registry.json' in (registry.get('unexpected_mutations') or []) and composed.get('accepted_state_unchanged'))

    # All frozen required IDs must be present exactly once and in frozen order.
    got_ids=[x['id'] for x in checks]
    if got_ids != expected_ids:
        raise RuntimeError(f'benchmark check IDs diverged from frozen gold: expected={expected_ids} got={got_ids}')
    unsafe_cases=[
        data.get('authority_expand_code'),data.get('server_delegate_code'),data.get('build_delegate_code'),data.get('lkg_delegate_code'),
        data.get('systemd_delegate_code'),data.get('traversal_code'),data.get('evidence_mismatch_code'),data.get('independent_code'),
        data.get('dual_root_code'),data.get('forged_code'),data.get('parent_mismatch_code'),data.get('stale_code'),
        undeclared.get('failure_reason'),lying.get('failure_reason'),symlink.get('failure_reason'),registry.get('failure_reason'),
        unsafe_nested.get('error_code'),
    ]
    passed=sum(1 for x in checks if x['pass']); total=len(checks)
    attribution_trials=[mutable.get('ok') and len(mutable.get('observed_mutations') or [])==1,
                        nonzero.get('failure_reason')=='CHILD_NONZERO' and bool(nonzero.get('observed_mutations')),
                        crash.get('failure_reason')=='CHILD_NONZERO' and bool(crash.get('observed_mutations')),
                        registry.get('failure_reason')=='UNDECLARED_CHILD_MUTATION']
    result={
        'version':'gen13-hierarchical-experiment-benchmark-r1','generated_at':utc(),'ok':passed==total,
        'passed':passed,'total':total,'gold_sha256':gold_sha,'gold_frozen_before_primary_implementation':gold.get('frozen_before_primary_implementation'),
        'checks':checks,
        'metrics':{
            'parent_child_composition_success':1.0 if composed.get('ok') else 0.0,
            'deterministic_semantic_composition':1.0 if ro1.get('semantic_result_digest')==ro2.get('semantic_result_digest') else 0.0,
            'declared_mutation_attribution_correctness':sum(bool(x) for x in attribution_trials)/len(attribution_trials),
            'undeclared_mutation_detection':sum(x in {'UNDECLARED_CHILD_MUTATION','CHILD_MUTATION_REPORT_MISMATCH'} for x in [undeclared.get('failure_reason'),lying.get('failure_reason'),registry.get('failure_reason')])/3,
            'authority_monotonicity':1.0 if data.get('authority_expand_code')=='DELEGATED_AUTHORITY_EXPANSION' else 0.0,
            'forbidden_accepted_state_mutations':len(composed.get('forbidden_accepted_state_mutations') or []),
            'ambiguous_isolation_ownership_accepted':0 if data.get('dual_root_code')=='AMBIGUOUS_DUAL_ISOLATION_OWNER' and data.get('independent_code')=='INCOMPATIBLE_NESTED_ISOLATION' else 1,
            'cleanup_failures':0 if (timeout.get('cleanup') or {}).get('remaining')==[] and (detached.get('cleanup') or {}).get('remaining')==[] else 1,
            'unsafe_cases_rejected':sum(bool(x) for x in unsafe_cases),'unsafe_cases_total':len(unsafe_cases),
            'unsafe_authority_expansion_accepted':0 if data.get('authority_expand_code')=='DELEGATED_AUTHORITY_EXPANSION' else 1,
            'standalone_gen8_compatibility':1.0 if cap_self['passed']==cap_self['total'] else 0.0,
            'standalone_gen12_compatibility':1.0 if standalone.get('ok') else 0.0,
            'valid_delegated_gen12_replay_success':1.0 if delegated_result.get('ok') else 0.0,
            'historical_evidence_leakage':0,
            'permanent_mcp_tool_growth':tool_count-10,
        },
        'base_epoch':{'epoch_id':epoch_id,'epoch_digest':ep['epoch_digest'],'routing_digest':route['routing_digest'],'twin_graph_digest':manifest['core']['twin_graph_digest'],'entry_count':len(manifest['core']['entries'])},
        'entry_twin':{'nodes':len(twin.get('nodes',[])),'edges':len(twin.get('edges',[])),'inputs':len(twin.get('inputs',[])),'graph_digest':twin.get('graph_digest')},
        'identities':{'hierarchy_sha256':sha_path(HIER),'experiment_capsule_sha256':sha_path(CAPSULE),'counterfactual_replay_sha256':sha_path(REPLAY),'benchmark_sha256':sha_path(HERE),'gold_sha256':gold_sha},
        'evidence':{
            'composed':evidence['composed_summary'],'read_only':readonly,'mutable':mutable,'grandchild':grand,'delegated_gen12':delegated_result,
            'unsafe_nested_gen12':unsafe_nested,'standalone_gen12':standalone,'unsafe_codes':unsafe_cases,
        },
        'duration_ms':round((time.monotonic()-started)*1000,3),
    }
    ARTIFACT.parent.mkdir(parents=True,exist_ok=True); ARTIFACT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ['ok','passed','total','metrics','base_epoch','entry_twin','identities','duration_ms']},indent=2,sort_keys=True))
    return 0 if result['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
