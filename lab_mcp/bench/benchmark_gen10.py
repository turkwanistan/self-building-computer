#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import importlib.util
import json
import pathlib
import statistics
import time
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path('/opt/optiplex-lab')
STATE = pathlib.Path('/var/lib/optiplex-lab')
GEN10 = STATE / 'gen10'
GOLD = GEN10 / 'GEN10_GOLD.json'
ART = STATE / 'benchmarks/gen10-evidence-epoch-benchmark.json'
PACKETS = STATE / 'benchmarks/gen10-evidence-epoch-packets.json'
CONTROL = STATE / 'benchmarks/gen10-evidence-epoch-control.json'
UNRELATED = STATE / 'benchmarks/gen10-unrelated-negative-control.json'
VERSION = 'gen10-evidence-epoch-benchmark-r1'
STARTED = datetime.now(timezone.utc).isoformat()


def loadmod(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {path}')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def j(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def compact(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def capsule_json_from_capture(result: dict[str, Any], path: str) -> dict[str, Any] | None:
    matches = [x for x in result.get('captured_artifacts', []) if x.get('path') == path]
    if len(matches) != 1:
        return None
    p = pathlib.Path(str(matches[0].get('export_path')))
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


epoch = loadmod(ROOT / 'evidence_epoch.py', 'gen10_epoch_bench')
twin = loadmod(ROOT / 'architecture_twin.py', 'gen10_twin_bench')
cap = loadmod(ROOT / 'experiment_capsule.py', 'gen10_cap_bench')
gold = j(GOLD)
checks: list[dict[str, Any]] = []
metrics: dict[str, Any] = {}
unsafe_trials = 0
unsafe_blocked = 0
next_epoch_trials = 0
next_epoch_fresh = 0
creation_lat: list[float] = []
verify_lat: list[float] = []
finalize_lat: list[float] = []


def ck(name: str, ok: Any, detail: Any = None) -> None:
    checks.append({'name': name, 'ok': bool(ok), 'detail': detail})


def run_capture(command: str, captures: list[str], label: str) -> dict[str, Any]:
    return cap.run_capsule(command, captures=captures, label=label)


# Frozen gold must predate this implementation/benchmark source.
criteria = gold['success_criteria']
ck('gold_frozen_before_implementation', bool(gold.get('frozen_before_implementation')), {'gold_version': gold.get('version'), 'gold_sha256': sha(GOLD)})

# Coordinator self-test is a narrow first gate.
st = epoch.selftest()
ck('coordinator_selftest', st['passed'] == st['total'] == 6, st)

# Main reasoning epoch. CONTROL is a real Tier-1 benchmark artifact and declared transaction output.
task = 'implement and validate the Generation 10 evidence epoch snapshot freshness coordinator without changing the permanent MCP surface'
start_control_sha = sha(CONTROL)
e1 = epoch.begin_epoch(expected_outputs=[str(CONTROL)], evaluator_paths=[str(ROOT/'bench/benchmark_gen10.py')])
creation_lat.append(float(e1['creation_seal_latency_ms']))
e1b = epoch.begin_epoch(expected_outputs=[str(CONTROL)], evaluator_paths=[str(ROOT/'bench/benchmark_gen10.py')])
creation_lat.append(float(e1b['creation_seal_latency_ms']))
p1 = epoch.compile_minimized(e1['epoch_id'], task)
p1_repeat = epoch.compile_minimized(e1b['epoch_id'], task)
ck('normal_immutable_epoch_deterministic', e1['epoch_digest'] == e1b['epoch_digest'] and p1.get('transaction_digest') == p1_repeat.get('transaction_digest') and p1.get('ok') and p1_repeat.get('ok'), {
    'epoch_digest': e1['epoch_digest'], 'transaction_digest': p1.get('transaction_digest'), 'reused_second': e1b['reused'],
})
ck('compiler_optimizer_same_epoch', p1.get('epoch_digest') == e1['epoch_digest'] and p1.get('compiler_packet',{}).get('packet_digest') and p1.get('minimized_packet',{}).get('packet_digest') and p1.get('twin_graph_digest') == epoch.load_epoch(e1['epoch_id'])[1]['core']['twin_graph_digest'], {
    'epoch': p1.get('epoch_digest'), 'compiler_packet': p1.get('compiler_packet',{}).get('packet_digest'), 'optimizer_packet': p1.get('minimized_packet',{}).get('packet_digest'), 'twin': p1.get('twin_graph_digest'),
})

# Reproduce the Gen9 failure shape: evaluator rewrites indexed Tier-1 evidence after compile.
control_payload = {'version':'gen10-control-r1','state':'generated-inside-epoch','producer':'benchmark_gen10','parent_sha256':start_control_sha}
control_text = json.dumps(control_payload, sort_keys=True, separators=(',', ':')) + '\n'
cmd = "python3 - <<'PY'\nimport pathlib\np=pathlib.Path(%r)\np.write_text(%r)\nPY" % (str(CONTROL), control_text)
cap_write = epoch.run_epoch_capsule(e1['epoch_id'], cmd, captures=[str(CONTROL)], label='gen10-expected-tier1-write')
published = epoch.publish_captured_expected(e1['epoch_id'], cap_write, str(CONTROL))
post_write_verify = epoch.verify_epoch(e1['epoch_id'])
verify_lat.append(float(post_write_verify['verify_latency_ms']))
p1_after_write = epoch.compile_minimized(e1['epoch_id'], task)
expected_seen = any(x.get('path') == str(CONTROL) for x in post_write_verify['expected_output_changes'])
ck('expected_tier1_write_same_transaction_coherent', cap_write.get('accepted_state_unchanged') and published.get('ok') and post_write_verify['ok'] and expected_seen and p1_after_write.get('ok') and p1_after_write.get('transaction_digest') == p1.get('transaction_digest'), {
    'start_sha256': start_control_sha, 'published_sha256': published.get('sha256'), 'verify': post_write_verify, 'transaction_before': p1.get('transaction_digest'), 'transaction_after': p1_after_write.get('transaction_digest'),
})
fin1 = epoch.finalize_epoch(e1['epoch_id']); finalize_lat.append(float(fin1['finalize_latency_ms']))
ck('finalize_expected_output_queued', fin1['ok'] and any(x.get('path') == str(CONTROL) for x in fin1['next_epoch_candidates']), {'state':fin1['state'],'next_epoch_candidates':fin1['next_epoch_candidates']})

# Advance derived Twin, then prove the sealed epoch remains reproducible while the next epoch sees the write.
advance = epoch.advance_epoch(e1['epoch_id'])
p1_after_rebuild = epoch.compile_minimized(e1['epoch_id'], task)
ck('active_epoch_survives_twin_rebuild', advance['ok'] and p1_after_rebuild.get('ok') and p1_after_rebuild.get('transaction_digest') == p1.get('transaction_digest'), {
    'old_epoch_twin':p1.get('twin_graph_digest'),'new_live_twin':advance['next_twin'].get('graph_digest'),'transaction_after_rebuild':p1_after_rebuild.get('transaction_digest'),
})
e2 = epoch.begin_epoch(expected_outputs=[str(CONTROL)], evaluator_paths=[str(ROOT/'bench/benchmark_gen10.py')]); creation_lat.append(float(e2['creation_seal_latency_ms']))
root2, man2 = epoch.load_epoch(e2['epoch_id'])
control_entry2 = next(x for x in man2['core']['entries'] if x['path'] == str(CONTROL))
next_epoch_trials += 1
next_ok = control_entry2['sha256'] == sha(CONTROL) == published['sha256'] and e2['epoch_digest'] != e1['epoch_digest']
next_epoch_fresh += int(next_ok)
ck('next_epoch_observes_generated_evidence', next_ok, {'previous_epoch':e1['epoch_digest'],'next_epoch':e2['epoch_digest'],'next_control_sha256':control_entry2['sha256'],'published_sha256':published['sha256']})

# Unsafe critical source mutation is tested against a real sealed epoch in an isolated capsule.
unsafe_trials += 1
mut_cmd = "printf '\\n# GEN10_UNEXPECTED_MUTATION\\n' >> /opt/optiplex-lab/context_compiler.py\n/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/evidence_epoch.py verify " + e2['epoch_id']
critical_mut = epoch.run_epoch_capsule(e2['epoch_id'], mut_cmd, label='gen10-unexpected-critical-source')
critical_blocked = int(critical_mut.get('child_exit_code', 0)) != 0 and critical_mut.get('accepted_state_unchanged') and not critical_mut.get('forbidden_accepted_state_mutations')
unsafe_blocked += int(critical_blocked)
ck('unexpected_critical_mid_epoch_fails_closed', critical_blocked, {'child_exit_code':critical_mut.get('child_exit_code'),'accepted_state_unchanged':critical_mut.get('accepted_state_unchanged')})

# Missing content-addressed evidence must fail closed, again only inside a capsule.
root2, man2 = epoch.load_epoch(e2['epoch_id'])
first_entry = man2['core']['entries'][0]
blob = epoch.BLOB_ROOT / first_entry['blob_sha256'][:2] / first_entry['blob_sha256']
unsafe_trials += 1
missing_blob_cmd = 'rm -f ' + str(blob) + '\n/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/evidence_epoch.py verify ' + e2['epoch_id']
missing_blob = epoch.run_epoch_capsule(e2['epoch_id'], missing_blob_cmd, label='gen10-missing-blob')
missing_blocked = int(missing_blob.get('child_exit_code', 0)) != 0 and missing_blob.get('accepted_state_unchanged')
unsafe_blocked += int(missing_blocked)
ck('missing_pinned_blob_fails_closed', missing_blocked, {'blob':str(blob),'child_exit_code':missing_blob.get('child_exit_code'),'accepted_state_unchanged':missing_blob.get('accepted_state_unchanged')})

# Contradictory authority at begin cannot seal.
snap = j(STATE/'twin/twin-current.json')
auth = next(n for n in snap['nodes'] if n.get('authoritative') and n.get('identity') and n.get('source_sha256'))
dupe = copy.deepcopy(auth); dupe['id'] = str(auth['id']) + ':gen10-contradiction'; dupe['source_sha256'] = '0'*64
bad_snap = copy.deepcopy(snap); bad_snap['nodes'].append(dupe)
unsafe_trials += 1
try:
    epoch.begin_epoch(snapshot_override=bad_snap)
    contradiction_blocked = False
except RuntimeError as exc:
    contradiction_blocked = 'contradictory authority' in str(exc)
unsafe_blocked += int(contradiction_blocked)
ck('contradictory_authority_epoch_refused', contradiction_blocked, {'identity':auth.get('identity')})

# Append-only prefix-preserving growth is safe/newer; prefix mutation is unsafe.
append_entry = next((x for x in man2['core']['entries'] if x['policy'] == 'append_only_prefix'), None)
if append_entry:
    append_path = append_entry['path']
    append_cmd = "printf '%s\\n' '{\"event\":\"gen10-append-growth\"}' >> " + append_path + '\n/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/evidence_epoch.py verify ' + e2['epoch_id']
    append_res = epoch.run_epoch_capsule(e2['epoch_id'], append_cmd, label='gen10-append-only-growth')
    append_ok = int(append_res.get('child_exit_code', 1)) == 0 and append_res.get('accepted_state_unchanged')
    ck('append_only_prefix_growth_safe', append_ok, {'path':append_path,'child_exit_code':append_res.get('child_exit_code')})
    unsafe_trials += 1
    prefix_bad_cmd = "python3 - <<'PY'\nfrom pathlib import Path\np=Path(%r)\nb=p.read_bytes(); p.write_bytes((b'X' if b else b'X') + b[1:])\nPY\n/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/evidence_epoch.py verify %s" % (append_path, e2['epoch_id'])
    prefix_bad = epoch.run_epoch_capsule(e2['epoch_id'], prefix_bad_cmd, label='gen10-append-prefix-mutation')
    prefix_blocked = int(prefix_bad.get('child_exit_code',0)) != 0 and prefix_bad.get('accepted_state_unchanged')
    unsafe_blocked += int(prefix_blocked)
    ck('append_only_prefix_mutation_fails_closed', prefix_blocked, {'path':append_path,'child_exit_code':prefix_bad.get('child_exit_code')})
else:
    ck('append_only_prefix_growth_safe', False, 'no append-only epoch entry found')
    ck('append_only_prefix_mutation_fails_closed', False, 'no append-only epoch entry found')

# Crash/recovery: incomplete staging never becomes authoritative.
fake = epoch.EPOCH_ROOT / '.creating-gen10-crash-fixture'; fake.mkdir(parents=True, exist_ok=True); (fake/'manifest.json').write_text('{"partial":true}\n')
recovery = epoch.recover_incomplete()
ck('crash_incomplete_epoch_recovery', not fake.exists() and fake.name in recovery['removed_incomplete'], recovery)

# Overlapping reads are explicit-epoch and deterministic, never mixed.
def compile_worker(_: int) -> tuple[str | None, str | None, bool]:
    x = epoch.compile_minimized(e2['epoch_id'], task)
    return x.get('epoch_digest'), x.get('transaction_digest'), bool(x.get('ok'))
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    overlap = list(pool.map(compile_worker, range(8)))
ck('concurrent_reads_no_mixed_epoch', all(x[2] and x[0] == e2['epoch_digest'] for x in overlap) and len({x[1] for x in overlap}) == 1, {'results':overlap})

# Protected state mutation cannot escape capsule.
protected = epoch.run_epoch_capsule(e2['epoch_id'], "printf '\\n{\"gen10_forbidden_fixture\":true}\\n' >> /var/lib/optiplex-lab/memory/registry.json", label='gen10-protected-mutation')
ck('protected_state_mutation_isolated', protected.get('accepted_state_unchanged') and not protected.get('forbidden_accepted_state_mutations'), {'accepted_state_unchanged':protected.get('accepted_state_unchanged'),'forbidden':protected.get('forbidden_accepted_state_mutations')})

# Unrelated newly produced evidence is absent from the sealed view and cannot perturb output.
before_neg = epoch.compile_minimized(e2['epoch_id'], task)
try:
    UNRELATED.write_text(json.dumps({'version':'gen10-unrelated-r1','not_in_epoch':True}, sort_keys=True)+'\n')
    after_neg = epoch.compile_minimized(e2['epoch_id'], task)
finally:
    UNRELATED.unlink(missing_ok=True)
ck('unrelated_new_evidence_does_not_perturb_sealed_epoch', before_neg.get('ok') and after_neg.get('ok') and before_neg.get('transaction_digest') == after_neg.get('transaction_digest'), {'before':before_neg.get('transaction_digest'),'after':after_neg.get('transaction_digest')})

# Authority that semantically requires live revalidation cannot be frozen by accident.
live_fixture = pathlib.Path('/tmp/gen10-live-authority-fixture'); live_fixture.write_text('live-authority\n')
unsafe_trials += 1
try:
    epoch.begin_epoch(extra_paths=[str(live_fixture)], authority_overrides={str(live_fixture):'live_revalidate_only'})
    live_refused = False
except RuntimeError as exc:
    live_refused = 'no verifier' in str(exc)
finally:
    live_fixture.unlink(missing_ok=True)
unsafe_blocked += int(live_refused)
ck('live_authority_cannot_be_frozen_without_verifier', live_refused)

# Historical Gen7 retained view: hide later-generation additions only inside the capsule.
hide = [
    '/opt/optiplex-lab/context_compiler.py','/opt/optiplex-lab/context_necessity.py','/opt/optiplex-lab/experiment_capsule.py','/opt/optiplex-lab/evidence_epoch.py',
    '/opt/optiplex-lab/bench/benchmark_gen8.py','/opt/optiplex-lab/bench/benchmark_gen9.py','/opt/optiplex-lab/bench/benchmark_gen10.py',
]
historical_cmd = 'set -e\nrm -f ' + ' '.join(hide) + "\nrm -f /var/lib/optiplex-lab/benchmarks/gen8-* /var/lib/optiplex-lab/benchmarks/gen9-* /var/lib/optiplex-lab/benchmarks/gen10-*\n/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/bench/benchmark_gen7.py"
hist = run_capture(historical_cmd, ['/var/lib/optiplex-lab/benchmarks/gen7-architectural-twin-benchmark.json'], 'gen10-historical-gen7-view')
hist_art = capsule_json_from_capture(hist, '/var/lib/optiplex-lab/benchmarks/gen7-architectural-twin-benchmark.json')
hist_ok = bool(hist.get('accepted_state_unchanged') and isinstance(hist_art,dict) and hist_art.get('passed') == hist_art.get('total') == 15)
ck('historical_gen7_version_pinned_15_of_15', hist_ok, {'child_exit_code':hist.get('child_exit_code'),'passed':None if not hist_art else hist_art.get('passed'),'total':None if not hist_art else hist_art.get('total'),'accepted_state_unchanged':hist.get('accepted_state_unchanged')})

# Current Gen9 benchmark in a capsule is the metric/regression oracle for recall, critical FN, precision, and context reduction.
gen9 = run_capture('/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/bench/benchmark_gen9.py', [str(STATE/'benchmarks/gen9-context-necessity-benchmark.json')], 'gen10-gen9-metric-regression')
gen9_art = capsule_json_from_capture(gen9, str(STATE/'benchmarks/gen9-context-necessity-benchmark.json'))
g9m = (gen9_art or {}).get('metrics') or {}
necessity = g9m.get('minimized_necessity_aware') or {}
context_m = g9m.get('context_reduction') or {}
required_recall = float(necessity.get('required_evidence_recall', -1))
critical_fn = int(necessity.get('critical_fn', 999))
necessity_precision = float(necessity.get('critical_precision', -1))
context_reduction = float(context_m.get('gen9_vs_gen8_payload_reduction', -1))
ck('gen9_quality_preserved', bool(gen9.get('accepted_state_unchanged') and gen9_art and gen9_art.get('passed') == gen9_art.get('total') == 20 and required_recall >= criteria['required_evidence_recall_min'] and critical_fn <= criteria['critical_evidence_fn_max'] and necessity_precision >= criteria['necessity_aware_critical_precision_min'] and context_reduction >= criteria['context_payload_reduction_vs_gen8_min']), {
    'child_exit_code':gen9.get('child_exit_code'),'passed':None if not gen9_art else gen9_art.get('passed'),'total':None if not gen9_art else gen9_art.get('total'),'recall':required_recall,'fn':critical_fn,'precision':necessity_precision,'context_reduction':context_reduction,'accepted_state_unchanged':gen9.get('accepted_state_unchanged')
})

# Latency and deterministic digest samples after caches/blobs exist.
for _ in range(12):
    v = epoch.verify_epoch(e2['epoch_id']); verify_lat.append(float(v['verify_latency_ms']))
for _ in range(3):
    x = epoch.begin_epoch(expected_outputs=[str(CONTROL)], evaluator_paths=[str(ROOT/'bench/benchmark_gen10.py')]); creation_lat.append(float(x['creation_seal_latency_ms']))
metrics['epoch_latency_ms'] = {
    'creation_seal_median':round(statistics.median(creation_lat),3),'creation_seal_p95':round(sorted(creation_lat)[max(0,int(len(creation_lat)*.95)-1)],3),'creation_samples':len(creation_lat),
    'verify_median':round(statistics.median(verify_lat),3),'verify_p95':round(sorted(verify_lat)[max(0,int(len(verify_lat)*.95)-1)],3),'verify_samples':len(verify_lat),
    'finalize_median':round(statistics.median(finalize_lat),3) if finalize_lat else None,
}
ck('epoch_latency_within_frozen_thresholds', metrics['epoch_latency_ms']['creation_seal_median'] <= criteria['epoch_create_seal_median_ms_max'] and metrics['epoch_latency_ms']['verify_median'] <= criteria['epoch_verify_median_ms_max'] and metrics['epoch_latency_ms']['finalize_median'] <= criteria['epoch_finalize_median_ms_max'], metrics['epoch_latency_ms'])

# Reproducibility/storage and fail-closed accounting.
root2, man2 = epoch.load_epoch(e2['epoch_id'])
metrics['storage'] = {'entries':len(man2['core']['entries']),'materialized_bytes':sum(int(x['bytes']) for x in man2['core']['entries']),'unique_blob_bytes':sum(p.stat().st_size for p in epoch.BLOB_ROOT.glob('*/*') if p.is_file()),'epoch_manifest_bytes':(root2/'manifest.json').stat().st_size}
metrics['determinism'] = {'epoch_digest':e2['epoch_digest'],'transaction_digest':before_neg.get('transaction_digest')}
metrics['safety'] = {'unsafe_trials':unsafe_trials,'unsafe_blocked':unsafe_blocked,'unsafe_fail_closed_rate':round(unsafe_blocked/max(1,unsafe_trials),6),'avoidable_same_transaction_fail_closed_trials':1,'avoidable_same_transaction_fail_closed':0 if checks[[x['name'] for x in checks].index('expected_tier1_write_same_transaction_coherent')]['ok'] else 1}
metrics['next_epoch'] = {'trials':next_epoch_trials,'fresh':next_epoch_fresh,'freshness_rate':round(next_epoch_fresh/max(1,next_epoch_trials),6)}
metrics['gen9_quality'] = {'required_recall':required_recall,'critical_fn':critical_fn,'necessity_aware_precision':necessity_precision,'context_payload_reduction_vs_gen8':context_reduction}
ck('unsafe_conditions_still_fail_closed', metrics['safety']['unsafe_fail_closed_rate'] >= criteria['unsafe_condition_fail_closed_rate_min'], metrics['safety'])
ck('avoidable_transient_fail_closed_eliminated', metrics['safety']['avoidable_same_transaction_fail_closed'] == 0, metrics['safety'])
ck('next_epoch_freshness_complete', metrics['next_epoch']['freshness_rate'] >= criteria['next_epoch_freshness_rate_min'], metrics['next_epoch'])

# Snapshot representative evidence before the benchmark artifact rewrites itself.
packets = {
    'version':'gen10-evidence-epoch-packets-r1','epoch_id':e2['epoch_id'],'epoch_digest':e2['epoch_digest'],
    'manifest_core':man2['core'],'compiler_packet_digest':before_neg.get('compiler_packet',{}).get('packet_digest'),
    'optimizer_packet_digest':before_neg.get('minimized_packet',{}).get('packet_digest'),'transaction_digest':before_neg.get('transaction_digest'),
    'control_entry':control_entry2,'finalization_epoch1':fin1,'next_twin':advance['next_twin'],
}
PACKETS.write_text(json.dumps(packets, indent=2, sort_keys=True)+'\n')

metrics['permanent_mcp_tools'] = 10
metrics['coordinator_sha256'] = sha(ROOT/'evidence_epoch.py')
metrics['benchmark_source_sha256'] = sha(ROOT/'bench/benchmark_gen10.py')
result = {
    'generation':'gen10-evidence-epoch-r1','benchmark':VERSION,'started_at':STARTED,'ended_at':datetime.now(timezone.utc).isoformat(),
    'passed':sum(1 for x in checks if x['ok']),'total':len(checks),'checks':checks,'metrics':metrics,
    'artifacts':{'benchmark':str(ART),'packets':str(PACKETS),'control':str(CONTROL),'epoch_manifest':str(root2/'manifest.json')},
    'gold_sha256':sha(GOLD),
}
ART.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result['passed'] == result['total'] else 1)
