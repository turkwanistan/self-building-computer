#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import shlex
import sys
from typing import Any, Callable

ENGINE = pathlib.Path('/opt/optiplex-lab/evaluator_mutation_nursery.py')
FIXTURE = pathlib.Path('/opt/optiplex-lab/bench/gen14_fixture_evaluator.py')
TWIN = pathlib.Path('/opt/optiplex-lab/architecture_twin.py')
GOLD = pathlib.Path('/opt/optiplex-lab/bench/GEN14_GOLD.json')
OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen14-evaluator-mutation-benchmark.json')
MUTATION_EVIDENCE = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen14-mutation-evidence.json')
SELF_USE_EVIDENCE = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen14-self-use.json')
ADVERSARIAL_EVIDENCE = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen14-adversarial.json')
GOLD_SHA = '1a30b31a8f87c82428d157c20ddfd7c380289d6dae7447e01d573f2fb499483a'
VERSION = 'gen14-benchmark-r1'


def load(path: pathlib.Path, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    if s is None or s.loader is None:
        raise RuntimeError(f'cannot load {path}')
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def sha_path(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def exc_code(fn: Callable[[], Any]) -> str | None:
    try:
        fn(); return None
    except Exception as exc:
        return str(getattr(exc, 'code', type(exc).__name__))


def summarize_mutation(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r.get(k) for k in (
        'ok','mutation_id','mutation_class','dangerous','check_id','classification','kill_reason',
        'failure_reason','semantic_result_digest','capsule_cleanup'
    )} | {'root_proof': r.get('root_proof')}


def main() -> int:
    n = load(ENGINE, 'gen14_nursery_bench')
    checks: list[dict[str, Any]] = []
    def ck(name: str, ok: Any, detail: Any = None):
        checks.append({'name': name, 'ok': bool(ok), 'detail': detail})

    gold_hash = sha_path(GOLD)
    gold = json.loads(GOLD.read_text())
    ck('frozen_gold_integrity', gold_hash == GOLD_SHA and gold.get('frozen_before_primary_implementation') is True,
       {'expected': GOLD_SHA, 'actual': gold_hash})
    ck('safe_mutation_class_contract', tuple(gold.get('safe_mutation_classes') or []) == tuple(n.SAFE_MUTATION_CLASSES), list(n.SAFE_MUTATION_CLASSES))
    st = n.selftest(); ck('nursery_selftest', st['passed'] == st['total'], st)
    ck('fixture_and_real_evaluator_lineage_available', FIXTURE.is_file() and TWIN.is_file(), {'fixture': sha_path(FIXTURE), 'twin': sha_path(TWIN)})

    internal = ['evidence','freshness','negative_control','threshold','threshold_redundant']
    toy_cases = [
        {'id':'good','args':[{'observed':5,'declared':5,'evidence':'bound','evidence_state':'fresh','negative_control':False}],
         'oracle':[{'path':'ok','op':'equals','value':True}], 'required_internal_checks': internal},
        {'id':'threshold_bad','args':[{'observed':15,'declared':5,'evidence':'bound','evidence_state':'fresh','negative_control':False}],
         'oracle':[{'path':'ok','op':'equals','value':False}], 'required_internal_checks': internal},
        {'id':'missing_evidence','args':[{'observed':5,'declared':5,'evidence_state':'fresh','negative_control':False}],
         'oracle':[{'path':'ok','op':'equals','value':False}], 'required_internal_checks': internal},
        {'id':'stale_evidence','args':[{'observed':5,'declared':5,'evidence':'bound','evidence_state':'stale','negative_control':False}],
         'oracle':[{'path':'ok','op':'equals','value':False}], 'required_internal_checks': internal},
        {'id':'negative_control_bad','args':[{'observed':5,'declared':5,'evidence':'bound','evidence_state':'fresh','negative_control':True}],
         'oracle':[{'path':'ok','op':'equals','value':False}], 'required_internal_checks': internal},
    ]
    fsha = sha_path(FIXTURE)
    mutations = [
        ('threshold_change','THRESHOLD = 10\nREDUNDANT_THRESHOLD = 20','THRESHOLD = 20\nREDUNDANT_THRESHOLD = 20',True,'threshold',None,False),
        ('assertion_delete','checks["negative_control"] = (not NEGATIVE_CONTROL_ENABLED) or (candidate.get("negative_control", False) == NEGATIVE_CONTROL_EXPECTED)  # CHECK_NEGATIVE_CONTROL_SENTINEL','checks["negative_control"] = True  # CHECK_NEGATIVE_CONTROL_REMOVED',True,'negative_control','CHECK_NEGATIVE_CONTROL_SENTINEL',False),
        ('assertion_invert','checks["evidence"] = (not REQUIRE_EVIDENCE) or ("evidence" in candidate)  # CHECK_EVIDENCE_SENTINEL','checks["evidence"] = (not REQUIRE_EVIDENCE) or ("evidence" not in candidate)  # CHECK_EVIDENCE_SENTINEL',True,'evidence',None,False),
        ('fixture_substitute','NEGATIVE_CONTROL_EXPECTED = False','NEGATIVE_CONTROL_EXPECTED = True',True,'negative_control_fixture',None,False),
        ('evidence_omit','REQUIRE_EVIDENCE = True','REQUIRE_EVIDENCE = False',True,'evidence_required',None,False),
        ('stale_evidence_inject','ALLOW_STALE = False','ALLOW_STALE = True',True,'freshness',None,False),
        ('trust_declared_state','TRUST_SOURCE = "observed"','TRUST_SOURCE = "declared"',True,'observed_state',None,False),
        ('scoring_weight_change','WEIGHTS = {"threshold": 3, "threshold_redundant": 3, "evidence": 3, "freshness": 3, "negative_control": 3}','WEIGHTS = {"threshold": 30, "threshold_redundant": 3, "evidence": 3, "freshness": 3, "negative_control": 3}',False,'score_weight',None,True),
        ('fail_open_change','FAIL_CLOSED = True','FAIL_CLOSED = False',True,'fail_closed',None,False),
        ('negative_control_corrupt','NEGATIVE_CONTROL_ENABLED = True','NEGATIVE_CONTROL_ENABLED = False',True,'negative_control',None,False),
    ]
    mutation_results: list[dict[str, Any]] = []
    class_results: dict[str, dict[str, Any]] = {}
    first_spec = None
    for mclass, old, new, dangerous, check_id, marker, redundant in mutations:
        spec = n.make_spec(name='gen14-toy-' + mclass, evaluator_path=str(FIXTURE), evaluator_sha256=fsha,
                           function='evaluate', cases=toy_cases, mutation_class=mclass, old=old, new=new,
                           dangerous=dangerous, check_id=check_id, check_marker=marker,
                           redundancy_candidate=redundant, timeout=4.0)
        if first_spec is None: first_spec = spec
        r = n.run_mutation(spec); mutation_results.append(r); class_results[mclass] = summarize_mutation(r)
        expected = 'SURVIVED_REDUNDANT_OR_EQUIVALENT' if mclass == 'scoring_weight_change' else 'KILLED'
        ck('mutation_class_' + mclass, r.get('classification') == expected and r.get('capsule_cleanup',{}).get('removed') is True, summarize_mutation(r))

    # Evaluator crash, timeout, and malformed result are hostile evaluator behavior and must be killed/fail closed.
    hostile_specs = [
        ('evaluator_crash','assertion_delete','    observed = candidate.get("observed")','    raise SystemExit(7)',2.0),
        ('evaluator_timeout','assertion_delete','    observed = candidate.get("observed")','    import time; time.sleep(2); observed = candidate.get("observed")',0.10),
        ('malformed_evaluator_result','assertion_delete','    return {"ok": ok, "checks": checks, "checks_run": sorted(checks), "critical_failures": critical_failures,\n            "score": score, "score_pass": score_pass, "selected_value": value}','    return object()',2.0),
    ]
    hostile_results = {}
    for name,mclass,old,new,timeout in hostile_specs:
        spec = n.make_spec(name='gen14-'+name, evaluator_path=str(FIXTURE), evaluator_sha256=fsha,
                           function='evaluate', cases=toy_cases, mutation_class=mclass, old=old, new=new,
                           dangerous=True, check_id=name, timeout=timeout)
        r = n.run_mutation(spec); mutation_results.append(r); hostile_results[name] = summarize_mutation(r)
        ck(name + '_fail_closed', r.get('classification') == 'KILLED' and r.get('capsule_cleanup',{}).get('removed') is True, summarize_mutation(r))

    # Real self-use: mutate the accepted Gen7 Twin verifier to ignore stale/missing evidence.
    twin_sha = sha_path(TWIN)
    twin_cases = [
        {'id':'fresh_twin_node','args':[{'nodes':[{'id':'real-twin','source_path':str(TWIN),'source_sha256':twin_sha}]}],
         'oracle':[{'path':'ok','op':'equals','value':True},{'path':'issues','op':'empty'}]},
        {'id':'stale_twin_node','args':[{'nodes':[{'id':'real-twin','source_path':str(TWIN),'source_sha256':'0'*64}]}],
         'oracle':[{'path':'ok','op':'equals','value':False},{'path':'issues','op':'nonempty'}]},
    ]
    self_spec = n.make_spec(name='gen14-self-use-twin-fail-open', evaluator_path=str(TWIN), evaluator_sha256=twin_sha,
                            function='verify', cases=twin_cases, mutation_class='fail_open_change',
                            old='        if f["state"] in {"stale","missing"}: issues.append({"node":n["id"],"freshness":f})',
                            new='        if f["state"] in {"never"}: issues.append({"node":n["id"],"freshness":f})',
                            dangerous=True, check_id='twin_stale_fail_closed', timeout=4.0)
    self_use = n.run_mutation(self_spec); mutation_results.append(self_use)
    ck('real_prior_evaluator_self_use_killed', self_use.get('classification') == 'KILLED' and self_use.get('source',{}).get('accepted_sha256') == twin_sha, summarize_mutation(self_use))
    ck('real_self_use_single_owner_and_protected', self_use.get('root_proof',{}).get('physical_isolation_owner_count') == 1 and self_use.get('root_proof',{}).get('accepted_state_unchanged') is True and not self_use.get('root_proof',{}).get('unexpected_final_mutations'), self_use.get('root_proof'))

    report = n.detection_power(mutation_results)
    ck('overall_mutation_kill_rate', report['overall_mutation_kill_rate'] >= float(gold['thresholds']['overall_mutation_kill_rate_min']), report)
    ck('dangerous_mutation_kill_rate', report['dangerous_mutation_kill_rate'] >= float(gold['thresholds']['dangerous_mutation_kill_rate_min']), report)
    ck('surviving_dangerous_zero', len(report['surviving_dangerous_mutations']) <= int(gold['thresholds']['surviving_dangerous_mutations_max']), report['surviving_dangerous_mutations'])
    ck('unique_check_contribution_reported', bool(report.get('unique_check_contribution')), report.get('unique_check_contribution'))
    ck('redundant_equivalent_reported', 'score_weight' in (report.get('redundant_or_equivalent_candidates') or []), report.get('redundant_or_equivalent_candidates'))

    # Same semantic mutation executed twice must retain content-addressed ID/result identity despite different Capsules.
    d1 = n.run_mutation(first_spec); d2 = n.run_mutation(first_spec)
    ck('deterministic_mutation_identity', d1.get('mutation_id') == d2.get('mutation_id') and d1.get('semantic_result_digest') == d2.get('semantic_result_digest') and d1.get('classification') == d2.get('classification') == 'KILLED',
       {'first': summarize_mutation(d1), 'second': summarize_mutation(d2)})
    ck('deterministic_runs_cleaned', d1.get('capsule_cleanup',{}).get('removed') is True and d2.get('capsule_cleanup',{}).get('removed') is True)

    # Spec/evidence/authority hostile cases rejected before mutation.
    base = n.make_spec(name='gen14-adversarial-base', evaluator_path=str(FIXTURE), evaluator_sha256=fsha,
                       function='evaluate', cases=toy_cases, mutation_class='threshold_change',
                       old='THRESHOLD = 10\nREDUNDANT_THRESHOLD = 20', new='THRESHOLD = 20\nREDUNDANT_THRESHOLD = 20')
    invalid_cases: dict[str, dict[str, Any]] = {}
    def invalid(name: str, mutator: Callable[[dict[str,Any]],None], expected: str):
        s = copy.deepcopy(base); mutator(s); r = n.run_mutation(s); invalid_cases[name] = summarize_mutation(r)
        ck(name, r.get('classification') == 'INVALID_FAIL_CLOSED' and r.get('failure_reason') == expected, summarize_mutation(r))
    invalid('unsafe_mutation_class_rejected', lambda s:s['mutation'].__setitem__('class','production_rewrite'), 'MUTATION_CLASS_UNSAFE')
    invalid('authority_expansion_rejected', lambda s:s.__setitem__('authorities',['evaluation','production']), 'MUTATION_AUTHORITY_INVALID')
    invalid('forged_evaluator_lineage_rejected', lambda s:(s['evaluator'].__setitem__('sha256','0'*64), s['evidence_bindings'].__setitem__('evaluator_sha256','0'*64)), 'EVALUATOR_LINEAGE_MISMATCH')
    invalid('stale_case_binding_rejected', lambda s:s['evidence_bindings'].__setitem__('case_digest','0'*64), 'CASE_BINDING_INVALID')
    invalid('frozen_gold_binding_rejected', lambda s:s['evidence_bindings'].__setitem__('gold_sha256','0'*64), 'GOLD_BINDING_INVALID')
    invalid('self_detection_target_rejected', lambda s:(s['evaluator'].__setitem__('path',str(ENGINE)), s['evaluator'].__setitem__('sha256',sha_path(ENGINE)), s['evidence_bindings'].__setitem__('evaluator_sha256',sha_path(ENGINE))), 'EVALUATOR_TARGET_FORBIDDEN')
    invalid('outside_evaluator_root_rejected', lambda s:s['evaluator'].__setitem__('path','/tmp/evaluator.py'), 'EVALUATOR_PATH_INVALID')
    invalid('unknown_spec_field_rejected', lambda s:s.__setitem__('promote',True), 'SPEC_UNKNOWN_FIELD')

    # Ambiguous exact mutation (matches multiple source locations) fails closed inside isolation and is cleaned.
    ambiguous = copy.deepcopy(base); ambiguous['name']='gen14-ambiguous-match'; ambiguous['mutation']['old']=' = '; ambiguous['mutation']['new']=' = '
    # bindings are unchanged because cases/evaluator remain unchanged; mutation identity changes.
    amb = n.run_mutation(ambiguous); invalid_cases['ambiguous_mutation_match'] = summarize_mutation(amb)
    ck('ambiguous_mutation_match_fail_closed', amb.get('classification') == 'INVALID_FAIL_CLOSED' and amb.get('failure_reason') == 'MUTANT_PREPARATION_FAILED' and amb.get('capsule_cleanup',{}).get('removed') is True, summarize_mutation(amb))

    # Result protocol attacks without trusting evaluator declarations.
    forged = {'version':'gen14-evaluator-envelope-r1','evaluator_digest':'abc','runner_digest':n.RUNNER_DIGEST,
              'expected_case_ids':['a'],'checks_run':[],'skipped_checks':['a'],'case_results':[], 'protocol_violations':[], 'decision':'PASS'}
    vf = n.validate_envelope(forged, expected_case_ids=['a'], evaluator_digest='abc')
    ck('pass_with_skipped_checks_rejected', not vf['ok'] and 'SKIPPED_REQUIRED_CHECKS' in vf['errors'], vf)
    lie = copy.deepcopy(forged); lie.update({'checks_run':['a'],'skipped_checks':[],'case_results':[{'id':'a','oracle_pass':False}],'decision':'PASS'})
    vl = n.validate_envelope(lie, expected_case_ids=['a'], evaluator_digest='abc')
    ck('lying_evaluator_decision_rejected', not vl['ok'] and 'DECLARED_DECISION_MISMATCH' in vl['errors'], vl)
    malformed = n.validate_envelope('PASS', expected_case_ids=['a'], evaluator_digest='abc')
    ck('malformed_envelope_rejected', not malformed['ok'] and 'ENVELOPE_NOT_OBJECT' in malformed['errors'], malformed)

    # Direct Gen13 adversarial context/scope cases, all within one sacrificial physical Capsule.
    h = load(pathlib.Path('/opt/optiplex-lab/hierarchical_experiment.py'), 'gen14_hier_bench')
    adversarial_script = r'''import copy,importlib.util,json,pathlib
p=pathlib.Path('/opt/optiplex-lab/hierarchical_experiment.py'); s=importlib.util.spec_from_file_location('h',p); h=importlib.util.module_from_spec(s); s.loader.exec_module(h)
parent=h.load_current_context(); out={}
def code(fn):
    try: fn(); return None
    except Exception as exc: return getattr(exc,'code',type(exc).__name__)
out['scope_expansion']=code(lambda:h.delegate_context(parent,name='scope',mutation_scope=['/opt/optiplex-lab/bench/**']))
out['authority_expansion']=code(lambda:h.delegate_context(parent,name='auth',authorities=['production']))
child=h.delegate_context(parent,name='valid',mutation_scope=['/root/gen14-adversarial/child/**'],authorities=['evaluation'])
forged=copy.deepcopy(child); forged['semantic_digest']='0'*64
out['forged_parent_context']=code(lambda:h.validate_context(forged,expected_parent=parent))
core=h._child_semantic_core(parent,name='stale',mode='delegated',scope=[],authorities=['evaluation'],evidence=parent['evidence_bindings'],evaluator={},result_policy='fail_closed')
stale=h._bind_context(core,owner_run_id='cap8_stale_owner',parent_binding_digest=parent['binding_digest'])
out['stale_context_binding']=code(lambda:h.validate_context(stale,expected_parent=parent))
out['independent_nested_capsule']=code(lambda:h.delegate_context(parent,name='nested',isolation_mode='independent'))
write_registry=h.run_child(parent,name='accepted-write',command="printf x >> /var/lib/optiplex-lab/capabilities/registry.json",mutation_scope=['/root/gen14-adversarial/child/**'],authorities=['evaluation'])
out['accepted_state_write_status']=[write_registry.get('status'),write_registry.get('failure_reason')]
write_gold=h.run_child(parent,name='gold-write',command="printf x >> /opt/optiplex-lab/bench/GEN14_GOLD.json",mutation_scope=['/root/gen14-adversarial/child/**'],authorities=['evaluation'])
out['frozen_gold_write_status']=[write_gold.get('status'),write_gold.get('failure_reason')]
write_fixture=h.run_child(parent,name='fixture-write',command="printf x >> /opt/optiplex-lab/bench/gen14_fixture_evaluator.py",mutation_scope=['/root/gen14-adversarial/child/**'],authorities=['evaluation'])
out['fixture_outside_evidence_status']=[write_fixture.get('status'),write_fixture.get('failure_reason')]
print(json.dumps(out,sort_keys=True))
'''
    root = h.run_root_experiment('python3 -c ' + shlex.quote(adversarial_script), name='gen14-direct-adversarial',
                                 mutation_scope=['/root/gen14-adversarial/**'], authorities=['evaluation'],
                                 evidence_bindings={'gold_sha256':GOLD_SHA}, expect_json=True, timeout=10.0)
    adv = ((root.get('execution') or {}).get('parsed_result')) or {}
    ck('direct_scope_expansion_rejected', adv.get('scope_expansion') == 'DELEGATED_SCOPE_EXPANSION', adv)
    ck('direct_authority_expansion_rejected', adv.get('authority_expansion') == 'DELEGATED_AUTHORITY_EXPANSION', adv)
    ck('forged_parent_context_rejected', adv.get('forged_parent_context') == 'FORGED_DELEGATION_CONTEXT', adv)
    ck('stale_context_binding_rejected', adv.get('stale_context_binding') == 'STALE_DELEGATION_CONTEXT', adv)
    ck('independent_nested_capsule_rejected', adv.get('independent_nested_capsule') == 'INCOMPATIBLE_NESTED_ISOLATION', adv)
    ck('accepted_state_write_contained', adv.get('accepted_state_write_status') == ['INVALID','UNDECLARED_CHILD_MUTATION'] and root.get('accepted_state_unchanged') is True, {'adv':adv,'root_accepted':root.get('accepted_state_unchanged')})
    ck('frozen_gold_write_contained', adv.get('frozen_gold_write_status') == ['INVALID','UNDECLARED_CHILD_MUTATION'] and root.get('accepted_state_unchanged') is True and sha_path(GOLD) == GOLD_SHA, {'adv':adv,'gold_sha':sha_path(GOLD)})
    ck('fixture_outside_evidence_contained', adv.get('fixture_outside_evidence_status') == ['INVALID','UNDECLARED_CHILD_MUTATION'] and root.get('accepted_state_unchanged') is True, adv)
    cleanup = load(pathlib.Path('/opt/optiplex-lab/experiment_capsule.py'), 'gen14_cap_bench').cleanup(root['capsule_run_id'])
    ck('direct_adversarial_capsule_cleaned', cleanup.get('removed') is True, cleanup)

    # Permanent operational surface is static and server identity is unchanged by this capability.
    build = json.loads(pathlib.Path('/etc/optiplex-lab/build.json').read_text())
    server_sha = sha_path(pathlib.Path('/opt/optiplex-lab/server.py'))
    lkg_sha = sha_path(pathlib.Path('/var/lib/optiplex-lab/recovery/server.last-known-good.py'))
    ck('operational_gen6_server_lkg_unchanged', build.get('generation') == 'gen6-experience-memory-r1' and build.get('source_sha256') == server_sha == lkg_sha and build.get('recovery_state') == 'ACCEPTED', {'build':build.get('build_id'),'server':server_sha,'lkg':lkg_sha})
    server_text = pathlib.Path('/opt/optiplex-lab/server.py').read_text()
    ck('permanent_mcp_surface_static_10', server_text.count('@mcp.tool') == 10, {'decorators':server_text.count('@mcp.tool')})
    ck('no_automatic_promotion_path', 'promote' not in n.run_mutation.__code__.co_names and '/opt/optiplex-lab/server.py' in n.FORBIDDEN_EVALUATOR_TARGETS)

    # Host/control-plane containment remains absent from guest.
    ck('host_repo_not_mounted', not pathlib.Path('/home/mcp/projects/projects/self-building-computer').exists())
    ck('frozen_gold_unchanged_after_benchmark', sha_path(GOLD) == GOLD_SHA, sha_path(GOLD))

    evidence = {
        'version':'gen14-mutation-evidence-r1', 'fixture_sha256':fsha, 'twin_sha256':twin_sha,
        'mutation_classes':class_results, 'hostile_results':hostile_results,
        'detection_power':report, 'deterministic_reruns':[summarize_mutation(d1),summarize_mutation(d2)],
    }
    self_evidence = {'version':'gen14-self-use-r1','target':'architecture_twin.verify','target_sha256':twin_sha,
                     'mutation':'remove stale/missing issue aggregation (fail-open)','result':self_use}
    adversarial = {'version':'gen14-adversarial-r1','spec_rejections':invalid_cases,'direct_gen13':adv,
                   'root_accepted_state_unchanged':root.get('accepted_state_unchanged'),'root_forbidden':root.get('forbidden_accepted_state_mutations') or [],
                   'protocol_checks':{'skipped':vf,'lying_decision':vl,'malformed':malformed},'capsule_cleanup':cleanup}
    atomic_json(MUTATION_EVIDENCE,evidence); atomic_json(SELF_USE_EVIDENCE,self_evidence); atomic_json(ADVERSARIAL_EVIDENCE,adversarial)

    passed = sum(x['ok'] for x in checks); total = len(checks)
    result = {'version':VERSION,'passed':passed,'total':total,'ok':passed==total,'checks':checks,
              'gold_sha256':gold_hash,'engine_sha256':sha_path(ENGINE),'fixture_sha256':fsha,'twin_sha256':twin_sha,
              'detection_power':report,
              'artifacts':{'mutation_evidence':str(MUTATION_EVIDENCE),'self_use':str(SELF_USE_EVIDENCE),'adversarial':str(ADVERSARIAL_EVIDENCE)}}
    atomic_json(OUT,result)
    print(json.dumps({'passed':passed,'total':total,'ok':passed==total,'detection_power':report,'artifact':str(OUT)},indent=2,sort_keys=True))
    return 0 if passed == total else 2


if __name__ == '__main__':
    raise SystemExit(main())
