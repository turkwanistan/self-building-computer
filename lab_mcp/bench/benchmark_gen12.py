#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import shutil
import tempfile
import time
from datetime import datetime, timezone

ENGINE = pathlib.Path('/opt/optiplex-lab/counterfactual_replay.py')
EPOCH = pathlib.Path('/opt/optiplex-lab/evidence_epoch.py')
TWIN = pathlib.Path('/opt/optiplex-lab/architecture_twin.py')
CAPSULE = pathlib.Path('/opt/optiplex-lab/experiment_capsule.py')
HERE = pathlib.Path(__file__).resolve()
ARTIFACT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen12-counterfactual-replay-benchmark.json')
FUTURE = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen12-future-tier1-evidence.json')
TASK = 'Implement a safe source change to /opt/optiplex-lab/counterfactual_replay.py and evaluate it; do not restart, reboot, promote, or change live state.'


def load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha_path(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    started = time.monotonic()
    eng = load(ENGINE, 'gen12_bench_engine')
    epoch = load(EPOCH, 'gen12_bench_epoch')
    cap = load(CAPSULE, 'gen12_bench_capsule')

    # The benchmark source itself is a new Tier-1 input; refresh before sealing.
    import subprocess
    subprocess.run([str(TWIN), 'build'], check=True, stdout=subprocess.DEVNULL)
    v = subprocess.run([str(TWIN), 'verify'], check=True, capture_output=True, text=True)
    twin_verify = json.loads(v.stdout)
    twin = json.loads(pathlib.Path('/var/lib/optiplex-lab/twin/twin-current.json').read_text())
    if not twin_verify.get('ok') or twin_verify.get('newer_evidence_available'):
        raise RuntimeError('Twin not fresh before Gen12 benchmark epoch')

    ep = epoch.begin_epoch(
        task=TASK,
        evaluator_paths=[str(ENGINE)],
        extra_paths=[str(ENGINE), str(HERE)],
        expected_outputs=[str(ARTIFACT), str(FUTURE)],
    )
    epoch_id = ep['epoch_id']
    _epoch_root, manifest = epoch.load_epoch(epoch_id)
    route = copy.deepcopy(manifest['core']['routing_proof'])
    base_common = {
        'schema_version': 1,
        'base_epoch_id': epoch_id,
        'base_epoch_digest': ep['epoch_digest'],
        'base_twin_graph_digest': manifest['core']['twin_graph_digest'],
        'base_routing_digest': route['routing_digest'],
        'original_decision': {'decision': 'accepted Gen12 engine invariants'},
        'evaluator': {'kind':'python_function','module_path':str(ENGINE),'function':'engine_invariants'},
    }
    checks = []
    evidence = {}

    def check(cid: str, ok: bool, details=None):
        checks.append({'id':cid,'pass':bool(ok),'details':details})

    # A. no-op baseline reproduction.
    noop = {**copy.deepcopy(base_common), 'alternative': {'type':'noop'}}
    a1 = eng.replay(noop)
    check('A1_noop_ok', a1.get('ok') is True, a1 if not a1.get('ok') else None)
    check('A2_baseline_reproduced', a1.get('baseline_semantic_digest') == a1.get('alternative_semantic_digest') and not a1.get('changed'))
    check('A3_baseline_invariant_true', (a1.get('baseline_result') or {}).get('authority_monotonic') is True)

    # B. deterministic repeated replay identity and semantics.
    a2 = eng.replay(noop)
    check('B1_replay_identity_deterministic', a1.get('replay_digest') == a2.get('replay_digest'))
    check('B2_semantic_result_deterministic', a1.get('result_digest') == a2.get('result_digest') and a1.get('alternative_semantic_digest') == a2.get('alternative_semantic_digest'))

    # C. real implementation overlay, twice, in one Capsule isolation owner each time.
    impl = {**copy.deepcopy(base_common), 'alternative': {
        'type':'implementation_change',
        'isolation_owner':'replay',
        'allowed_effect_paths':[str(ENGINE)],
        'operations':[{'op':'replace_text','path':str(ENGINE),'old':'"authority_monotonic": True,','new':'"authority_monotonic": False,'}],
    }}
    live_engine_before = sha_path(ENGINE)
    protected_before = cap.protected_manifest()
    c1 = eng.replay(impl)
    c2 = eng.replay(impl)
    protected_after = cap.protected_manifest()
    forbidden, allowed_audit = cap.compare_manifests(protected_before, protected_after)
    check('C1_implementation_executes', c1.get('ok') is True and (c1.get('alternative_result') or {}).get('authority_monotonic') is False, c1 if not c1.get('ok') else None)
    check('C2_implementation_delta_attributed', c1.get('changed') is True and (c1.get('attribution') or {}).get('correct') is True and (c1.get('comparison') or {}).get('declared_effect_paths') == [str(ENGINE)])
    check('C3_implementation_deterministic_semantics', c1.get('replay_digest') == c2.get('replay_digest') and c1.get('result_digest') == c2.get('result_digest') and c1.get('alternative_semantic_digest') == c2.get('alternative_semantic_digest'))
    check('C4_single_isolation_owner', (c1.get('execution_provenance') or {}).get('isolation_owner') == 'replay' and (c1.get('execution_provenance') or {}).get('unexpected_mutations') == [])
    check('C5_live_engine_unchanged', sha_path(ENGINE) == live_engine_before)
    check('C6_protected_state_unchanged', not forbidden, {'forbidden':forbidden,'allowed_audit':allowed_audit})

    # D. explicit alternate routing interpretation: preserve all base safety authority, add causal history.
    alt_authorities = sorted(set(route['required_authority_classes']) | {'causal_history'})
    route_obligations = copy.deepcopy(route.get('mandatory_evidence_obligations') or []) + [
        {'authority_class':'causal_history','evidence_requirement':'causal_or_historical_source','safety_critical':False}
    ]
    routing = {**copy.deepcopy(base_common), 'alternative': {
        'type':'intent_routing', 'primary_intent':'evaluation_benchmarking',
        'secondary_intents':['implementation_change'],
        'required_authority_classes':alt_authorities,
        'mandatory_evidence_obligations':route_obligations,
        'reason':'Gen12 explicit routing counterfactual',
    }}
    d = eng.replay(routing)
    check('D1_routing_replay_ok', d.get('ok') is True, d if not d.get('ok') else None)
    check('D2_routing_diff_explicit', (d.get('comparison') or {}).get('primary_intent') == ['implementation_change','evaluation_benchmarking'] and 'causal_history' in (d.get('comparison') or {}).get('authority_added', []))
    check('D3_routing_obligations_explicit', (d.get('comparison') or {}).get('evidence_obligations_changed') is True)

    # E. alternate evaluator over identical base evidence/implementation.
    evaluator_alt = {**copy.deepcopy(base_common), 'alternative': {
        'type':'evaluator',
        'evaluator': {'kind':'python_function','module_path':str(ENGINE),'function':'selftest'},
    }}
    e = eng.replay(evaluator_alt)
    check('E1_evaluator_replay_ok', e.get('ok') is True and e.get('changed') is True, e if not e.get('ok') else None)
    check('E2_evaluator_identity_is_delta', (e.get('comparison') or {}).get('baseline_evaluator_digest') != (e.get('comparison') or {}).get('alternative_evaluator_digest'))

    # F. create next-epoch evidence after sealing. It must be absent from historical epoch.
    FUTURE.parent.mkdir(parents=True, exist_ok=True)
    FUTURE.write_text(json.dumps({'tier':1,'created_after_epoch':epoch_id,'future_only':True}, sort_keys=True)+'\n')
    entries = {x['path'] for x in manifest['core']['entries']}
    check('F1_future_evidence_absent_from_sealed_epoch', str(FUTURE) not in entries)
    selection = {**copy.deepcopy(base_common),
        'original_decision': {'selected_paths':[str(ENGINE)]},
        'alternative': {'type':'authority_evidence_selection','selected_paths':['/opt/optiplex-lab/task_routing.py']}}
    f = eng.replay(selection)
    check('F2_historical_selection_base_only', f.get('ok') is True and (f.get('comparison') or {}).get('historical_leakage') == 0 and (f.get('comparison') or {}).get('selected_from_base_only') is True, f if not f.get('ok') else None)

    # G/H. Irrelevant declared implementation change is a semantic negative control.
    irrelevant = {**copy.deepcopy(base_common), 'alternative': {
        'type':'implementation_change','isolation_owner':'replay','allowed_effect_paths':[str(ENGINE)],
        'operations':[{'op':'append_text','path':str(ENGINE),'text':'\n# gen12 irrelevant replay-only comment\n'}],
    }}
    g = eng.replay(irrelevant)
    check('G1_irrelevant_overlay_executes', g.get('ok') is True, g if not g.get('ok') else None)
    check('H1_irrelevant_overlay_no_semantic_perturbation', g.get('baseline_semantic_digest') == g.get('alternative_semantic_digest') and not g.get('changed'))

    # I. adversarial fail-closed cases.
    bad_epoch = copy.deepcopy(noop); bad_epoch['base_epoch_digest'] = '0'*64
    i_epoch = eng.replay(bad_epoch)
    check('I1_wrong_epoch_fail_closed', i_epoch.get('fail_closed') and i_epoch.get('error_code') == 'WRONG_EPOCH_DIGEST')

    bad_route = copy.deepcopy(noop); bad_route['base_routing_digest'] = '1'*64
    i_route = eng.replay(bad_route)
    check('I2_route_mismatch_fail_closed', i_route.get('fail_closed') and i_route.get('error_code') == 'ROUTING_DIGEST_MISMATCH')

    # Missing blob without touching the real content-addressed store.
    orig_blob = eng.BLOB_ROOT
    try:
        temp = pathlib.Path(tempfile.mkdtemp(prefix='gen12-missing-blob-'))
        eng.BLOB_ROOT = temp / 'blobs'; eng.BLOB_ROOT.mkdir()
        i_blob = eng.replay(noop)
    finally:
        eng.BLOB_ROOT = orig_blob
        shutil.rmtree(temp, ignore_errors=True)
    check('I3_missing_blob_fail_closed', i_blob.get('fail_closed') and i_blob.get('error_code') == 'MISSING_CONTENT_ADDRESSED_BLOB')

    undeclared = {**copy.deepcopy(base_common), 'alternative': {
        'type':'implementation_change','isolation_owner':'replay','allowed_effect_paths':[str(ENGINE)],
        'operations':[{'op':'append_text','path':'/opt/optiplex-lab/task_routing.py','text':'\n# forbidden undeclared\n'}]}}
    i_und = eng.replay(undeclared)
    check('I4_undeclared_mutation_fail_closed', i_und.get('fail_closed') and i_und.get('error_code') == 'UNDECLARED_SOURCE_MUTATION')

    history_leak = {**copy.deepcopy(base_common), 'original_decision': {'selected_paths':[str(ENGINE)]},
        'alternative': {'type':'authority_evidence_selection','selected_paths':[str(FUTURE)]}}
    i_hist = eng.replay(history_leak)
    check('I5_historical_leak_fail_closed', i_hist.get('fail_closed') and i_hist.get('error_code') == 'HISTORICAL_EVIDENCE_LEAKAGE')

    weakened = {**copy.deepcopy(base_common), 'alternative': {
        'type':'intent_routing', 'primary_intent':'evaluation_benchmarking',
        'required_authority_classes':[x for x in route['required_authority_classes'] if x != 'guest_security_boundary']}}
    i_weak = eng.replay(weakened)
    check('I6_authority_weakening_fail_closed', i_weak.get('fail_closed') and i_weak.get('error_code') == 'UNSAFE_AUTHORITY_WEAKENING')

    contradictory = {**copy.deepcopy(base_common), 'alternative': {
        'type':'intent_routing','authority_assertions':[
            {'authority_class':'guest_security_boundary','required':True},
            {'authority_class':'guest_security_boundary','required':False},
        ]}}
    i_contra = eng.replay(contradictory)
    check('I7_contradictory_authority_fail_closed', i_contra.get('fail_closed') and i_contra.get('error_code') == 'CONTRADICTORY_AUTHORITY')

    mutate_current = {**copy.deepcopy(base_common), 'alternative': {
        'type':'implementation_change','isolation_owner':'replay','allowed_effect_paths':['/opt/optiplex-lab/server.py'],
        'operations':[{'op':'append_text','path':'/opt/optiplex-lab/server.py','text':'\n# must never happen\n'}]}}
    i_current = eng.replay(mutate_current)
    check('I8_current_state_mutation_fail_closed', i_current.get('fail_closed') and i_current.get('error_code') == 'ACCEPTED_STATE_MUTATION_FORBIDDEN')

    live_only = {**copy.deepcopy(base_common), 'original_decision': {'selected_paths':[str(ENGINE)]},
        'alternative': {'type':'authority_evidence_selection','selected_paths':[str(ENGINE)],'freeze_live_only_authority':True}}
    i_live = eng.replay(live_only)
    check('I9_live_authority_unvalidated_fail_closed', i_live.get('fail_closed') and i_live.get('error_code') == 'LIVE_AUTHORITY_VALIDATION_REQUIRED')

    nested = copy.deepcopy(impl); nested['alternative']['isolation_owner'] = 'child'; nested['alternative']['child_isolation_proof'] = {'owner':'child'}
    i_nested = eng.replay(nested)
    check('I10_unsafe_nested_isolation_not_guessed', i_nested.get('fail_closed') and i_nested.get('error_code') == 'ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION')

    # Final invariants and metrics.
    passed = sum(1 for x in checks if x['pass'])
    total = len(checks)
    deterministic_trials = [
        a1.get('replay_digest') == a2.get('replay_digest') and a1.get('result_digest') == a2.get('result_digest'),
        c1.get('replay_digest') == c2.get('replay_digest') and c1.get('result_digest') == c2.get('result_digest'),
    ]
    baseline_trials = [a1.get('baseline_semantic_digest') == a1.get('alternative_semantic_digest')]
    attribution_trials = [
        (c1.get('attribution') or {}).get('correct') is True,
        (d.get('attribution') or {}).get('correct') is True,
        (e.get('attribution') or {}).get('correct') is True,
        (f.get('attribution') or {}).get('correct') is True,
        (g.get('attribution') or {}).get('correct') is True,
    ]
    unsafe = [i_epoch,i_route,i_blob,i_und,i_hist,i_weak,i_contra,i_current,i_live,i_nested]
    result = {
        'version':'gen12-counterfactual-replay-benchmark-r1',
        'generated_at':utc(),
        'passed':passed,'total':total,'ok':passed==total,
        'checks':checks,
        'metrics':{
            'deterministic_replay_rate':sum(deterministic_trials)/len(deterministic_trials),
            'baseline_reproduction_rate':sum(baseline_trials)/len(baseline_trials),
            'declared_delta_attribution_correctness':sum(attribution_trials)/len(attribution_trials),
            'unsafe_cases_rejected':sum(bool(x.get('fail_closed')) for x in unsafe),
            'unsafe_cases_total':len(unsafe),
            'unsafe_authority_weakening_accepted':0 if i_weak.get('fail_closed') else 1,
            'historical_evidence_leakage':0 if i_hist.get('fail_closed') else 1,
            'forbidden_accepted_state_mutations':len(forbidden),
            'implementation_replay_semantic_delta':c1.get('changed'),
            'negative_control_semantic_delta':g.get('changed'),
            'single_isolation_owner':(c1.get('execution_provenance') or {}).get('isolation_owner'),
        },
        'base_epoch':{
            'epoch_id':epoch_id,'epoch_digest':ep['epoch_digest'],'routing_digest':route['routing_digest'],
            'twin_graph_digest':manifest['core']['twin_graph_digest'],'entry_count':len(manifest['core']['entries']),
            'routing_primary':route['detected_primary_intent'],'routing_secondary':route['secondary_intents'],
        },
        'entry_twin':{'nodes':len(twin.get('nodes',[])),'edges':len(twin.get('edges',[])),'inputs':len(twin.get('inputs',[])),'graph_digest':twin.get('graph_digest')},
        'engine_sha256':sha_path(ENGINE),'benchmark_sha256':sha_path(HERE),
        'future_evidence_path':str(FUTURE),
        'protected':{'forbidden_changes':forbidden,'allowed_audit':allowed_audit},
        'evidence':{
            'noop':a1,'implementation':c1,'routing':d,'evaluator':e,'historical_selection':f,'irrelevant':g,
            'unsafe_error_codes':[x.get('error_code') for x in unsafe],
        },
        'duration_ms':round((time.monotonic()-started)*1000,3),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({k:result[k] for k in ['ok','passed','total','metrics','base_epoch','entry_twin','engine_sha256','benchmark_sha256','duration_ms']},indent=2,sort_keys=True))
    return 0 if result['ok'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
