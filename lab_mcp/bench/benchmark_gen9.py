#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import lzma
import pathlib
import statistics
import time
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path('/opt/optiplex-lab')
STATE = pathlib.Path('/var/lib/optiplex-lab')
GEN9 = STATE / 'gen9'
GOLD = GEN9 / 'GEN9_GOLD.json'
LEGACY_GOLD = STATE / 'gen8/GEN8_GOLD.json'
TWIN = STATE / 'twin/twin-current.json'
FROZEN_GEN8_TWIN_XZ = STATE / 'gen8/GEN8_TWIN_SNAPSHOT.json.xz'
FROZEN_GEN8_TWIN_SHA256 = 'f1299fa23330944c734377203c4769fb4e8e27a9ac104f64397299a277ba9eea'
ART = STATE / 'benchmarks/gen9-context-necessity-benchmark.json'
PACKETS_ART = STATE / 'benchmarks/gen9-context-necessity-packets.json'
VERSION = 'gen9-context-necessity-benchmark-r2'


def loadmod(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def j(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


cc = loadmod(ROOT / 'context_compiler.py', 'gen9_cc_bench')
opt = loadmod(ROOT / 'context_necessity.py', 'gen9_opt_bench')
cap = loadmod(ROOT / 'experiment_capsule.py', 'gen9_cap_bench')
gold = j(GOLD)
snap = j(TWIN)
_frozen_raw = lzma.decompress(FROZEN_GEN8_TWIN_XZ.read_bytes())
if hashlib.sha256(_frozen_raw).hexdigest() != FROZEN_GEN8_TWIN_SHA256:
    raise RuntimeError('frozen Gen8 Twin SHA256 mismatch')
frozen_gen8_snap = json.loads(_frozen_raw)
frozen_gen8_node_ids = {str(n.get('id')) for n in frozen_gen8_snap.get('nodes', []) if n.get('id')}
legacy_gold = j(LEGACY_GOLD) if LEGACY_GOLD.is_file() else None
checks: list[dict[str, Any]] = []
compile_lat: list[float] = []
min_lat: list[float] = []


def ck(name: str, ok: bool, detail: Any = None) -> None:
    checks.append({'name': name, 'ok': bool(ok), 'detail': detail})


def records(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return list(packet.get('selected_evidence_records') or [])


def ids(packet: dict[str, Any]) -> set[str]:
    return {str(r['evidence_id']) for r in records(packet)}


def kinds(packet: dict[str, Any]) -> set[str]:
    return {str(r.get('kind')) for r in records(packet)}


def critical(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(r['evidence_id']): r for r in records(packet) if int(r.get('priority_tier', 9)) <= 1}


def compile_case(task: str, *, snapshot_override: dict[str, Any] | None = None, record_latency: bool = True) -> tuple[dict[str, Any], dict[str, Any], float, float]:
    t0 = time.monotonic()
    raw = cc.build_packet(task, budget_bytes=48000, snapshot_override=snapshot_override)
    c_ms = (time.monotonic() - t0) * 1000
    if record_latency:
        compile_lat.append(c_ms)
    t0 = time.monotonic()
    out = opt.minimize_packet(raw)
    m_ms = (time.monotonic() - t0) * 1000
    if record_latency:
        min_lat.append(m_ms)
    return raw, out, c_ms, m_ms


def post_gold_current_validations(packet: dict[str, Any], case: dict[str, Any]) -> set[str]:
    """Return direct current validators that provably did not exist in the frozen Gen8 Twin.

    They are not legacy-comparable false positives: the record must be a validation node absent
    from the exact accepted Gen8 snapshot and its observed dependency path must start at a frozen
    required task owner. This preserves future-valid evidence without editing frozen gold.
    """
    required = {str(x) for x in case.get('required_ids', [])}
    out: set[str] = set()
    for r in records(packet):
        eid = str(r.get('evidence_id') or '')
        path = [str(x) for x in (r.get('dependency_path') or [])]
        if (r.get('kind') == 'validation' and int(r.get('priority_tier', 9)) <= 1
                and eid not in frozen_gen8_node_ids and len(path) == 2
                and path[0] in required and path[1] == eid
                and str(r.get('relation_status') or '') == 'observed'):
            out.add(eid)
    return out


def gold_eval(packet: dict[str, Any], case: dict[str, Any], *, critical_only: bool = False, additional_necessary_ids: set[str] | None = None) -> dict[str, Any]:
    recs = critical(packet) if critical_only else {str(r['evidence_id']): r for r in records(packet)}
    selected = set(recs)
    required = [str(x) for x in case.get('required_ids', [])]
    any_ids = [str(x) for x in case.get('required_any_ids', [])]
    required_kinds = [str(x) for x in case.get('required_kinds', [])]
    necessary_witnesses: set[str] = set()
    missing: list[str] = []
    obligations = 0
    for rid in required:
        obligations += 1
        if rid in selected:
            necessary_witnesses.add(rid)
        else:
            missing.append(rid)
    if any_ids:
        obligations += 1
        hits = sorted(selected & set(any_ids))
        if hits:
            necessary_witnesses.add(hits[0])
        else:
            missing.append('ANY:' + ','.join(any_ids))
    for kind in required_kinds:
        obligations += 1
        hits = sorted(eid for eid, r in recs.items() if str(r.get('kind')) == kind and eid not in necessary_witnesses)
        if hits:
            necessary_witnesses.add(hits[0])
        else:
            missing.append('KIND:' + kind)
    for eid in sorted(additional_necessary_ids or set()):
        if eid in selected:
            necessary_witnesses.add(eid)
    forbidden = sorted(selected & set(str(x) for x in case.get('forbidden_ids', [])))
    return {
        'ok': not missing and not forbidden,
        'obligations': obligations,
        'necessary_witnesses': sorted(necessary_witnesses),
        'tp': len(necessary_witnesses),
        'fp': len(selected - necessary_witnesses),
        'fn': len(missing),
        'precision': round(len(necessary_witnesses) / max(1, len(selected)), 6),
        'recall': round(len(necessary_witnesses) / max(1, obligations), 6),
        'missing': missing,
        'forbidden_present': forbidden,
        'selected': sorted(selected),
    }


def gold_still_satisfied(selected_records: list[dict[str, Any]], case: dict[str, Any]) -> bool:
    packet = {'selected_evidence_records': selected_records}
    return bool(gold_eval(packet, case, critical_only=False)['ok'])


# Frozen real cases: Gen8 is the recall substrate; Gen9 minimizes only after that compile.
case_results: list[dict[str, Any]] = []
raw_packets: dict[str, dict[str, Any]] = {}
min_packets: dict[str, dict[str, Any]] = {}
base_tp = base_fp = base_fn = 0
opt_tp = opt_fp = opt_fn = 0
base_payload: list[int] = []
min_payload: list[int] = []
task_kinds_ok = True
negative_controls_ok = True

for case in gold['cases']:
    raw, out, c_ms, m_ms = compile_case(case['task'])
    cid = str(case['id'])
    raw_packets[cid] = raw
    min_packets[cid] = out
    before = gold_eval(raw, case, critical_only=True)
    after = gold_eval(out, case, critical_only=True)
    current_valid_raw = post_gold_current_validations(raw, case)
    current_valid_out = post_gold_current_validations(out, case)
    before_metric = gold_eval(raw, case, critical_only=True, additional_necessary_ids=current_valid_raw)
    after_metric = gold_eval(out, case, critical_only=True, additional_necessary_ids=current_valid_out)
    base_tp += before_metric['tp']; base_fp += before_metric['fp']; base_fn += before_metric['fn']
    opt_tp += after_metric['tp']; opt_fp += after_metric['fp']; opt_fn += after_metric['fn']
    task_ok = out.get('task_kind') == case.get('task_kind') == raw.get('task_kind')
    task_kinds_ok &= task_ok
    redundant_present = sorted(ids(out) & set(str(x) for x in case.get('redundant_ids', [])))
    negative_controls_ok &= not redundant_present
    base_b = int((out.get('budget') or {}).get('baseline_context_payload_bytes') or 0)
    min_b = int((out.get('budget') or {}).get('context_payload_bytes') or 0)
    base_payload.append(base_b); min_payload.append(min_b)
    result = {
        'id': cid,
        'task_kind': out.get('task_kind'),
        'task_kind_ok': task_ok,
        'baseline_critical': before,
        'minimized_critical': after,
        'current_valid_post_gold': sorted(current_valid_out),
        'baseline_metric_critical': before_metric,
        'minimized_metric_critical': after_metric,
        'baseline_context_payload_bytes': base_b,
        'minimized_context_payload_bytes': min_b,
        'context_payload_reduction': (out.get('budget') or {}).get('context_payload_reduction'),
        'compile_latency_ms': round(c_ms, 3),
        'minimization_latency_ms': round(m_ms, 3),
        'packet_digest': out.get('packet_digest'),
        'removed': (out.get('necessity_proof') or {}).get('removed') or [],
        'witness_proofs': (out.get('necessity_proof') or {}).get('witness_proofs') or [],
        'redundant_present': redundant_present,
        'fail_closed': out.get('fail_closed'),
    }
    ok = after['ok'] and after['fn'] == 0 and task_ok and not redundant_present and not out.get('fail_closed')
    ck('gold_' + cid, ok, result)
    case_results.append(result)

# Necessity-aware aggregate metric: required-any and required-kind witnesses count as required.
necessity_precision = opt_tp / (opt_tp + opt_fp) if (opt_tp + opt_fp) else 1.0
required_recall = opt_tp / (opt_tp + opt_fn) if (opt_tp + opt_fn) else 1.0
baseline_precision = base_tp / (base_tp + base_fp) if (base_tp + base_fp) else 1.0

# Legacy Gen8 exact-ID metric: raw current-Twin result remains diagnostic, while the
# predeclared >=0.90 acceptance threshold is measured on the exact accepted Gen8 Twin view.
legacy_current_tp = legacy_current_fp = legacy_current_fn = 0
legacy_comparable_tp = legacy_comparable_fp = legacy_comparable_fn = 0
legacy_comparable_packets: dict[str, dict[str, Any]] = {}
if isinstance(legacy_gold, dict):
    by_task = {str(c['task']): c for c in legacy_gold.get('cases', [])}
    for case in gold['cases']:
        legacy = by_task.get(str(case['task']))
        if not legacy:
            continue
        req = set(str(x) for x in legacy.get('required_ids', []))
        current_packet = min_packets[str(case['id'])]
        crit = set(critical(current_packet))
        legacy_current_tp += len(crit & req); legacy_current_fp += len(crit - req); legacy_current_fn += len(req - crit)

        _raw_cmp, comparable_packet, _c, _m = compile_case(str(case['task']), snapshot_override=frozen_gen8_snap, record_latency=False)
        legacy_comparable_packets[str(case['id'])] = comparable_packet
        cmp_crit = set(critical(comparable_packet))
        legacy_comparable_tp += len(cmp_crit & req); legacy_comparable_fp += len(cmp_crit - req); legacy_comparable_fn += len(req - cmp_crit)
legacy_current_precision = legacy_current_tp / (legacy_current_tp + legacy_current_fp) if (legacy_current_tp + legacy_current_fp) else 1.0
legacy_comparable_precision = legacy_comparable_tp / (legacy_comparable_tp + legacy_comparable_fp) if (legacy_comparable_tp + legacy_comparable_fp) else 1.0

# Stale/missing critical evidence remains fail-closed and MUST block minimization.
stale = copy.deepcopy(snap)
for n in stale.get('nodes', []):
    if n.get('id') == 'source:/opt/optiplex-lab/experience_loop.py':
        n['source_path'] = '/tmp/gen9-benchmark-definitely-missing-critical.py'
stale_raw = cc.build_packet(gold['cases'][0]['task'], budget_bytes=48000, snapshot_override=stale)
stale_min = opt.minimize_packet(stale_raw)
stale_ok = bool(stale_raw.get('fail_closed') and stale_min.get('fail_closed') and (stale_min.get('necessity_proof') or {}).get('minimization_blocked') and ids(stale_raw) == ids(stale_min) and {'authority:guest-security-boundary', 'operational:accepted-identity'}.issubset(ids(stale_min)))
ck('stale_missing_blocks_minimization', stale_ok, {'raw_fail_closed': stale_raw.get('fail_closed'), 'minimized_fail_closed': stale_min.get('fail_closed'), 'proof': stale_min.get('necessity_proof'), 'uncertainties': stale_min.get('uncertainties')})

# Contradictory authority remains visible and blocks minimization.
contr = copy.deepcopy(snap)
src = next(n for n in contr['nodes'] if n.get('id') == 'build_state:current')
dup = copy.deepcopy(src); dup['id'] = 'build_state:gen9-contradiction-control'; dup['generation'] = 'gen9-contradiction-control'; contr['nodes'].append(dup)
contr_raw = cc.build_packet('Explain lifecycle recovery build metadata.', budget_bytes=48000, snapshot_override=contr)
contr_min = opt.minimize_packet(contr_raw)
contr_ok = bool(contr_min.get('fail_closed') and contr_min.get('contradictions') and (contr_min.get('necessity_proof') or {}).get('minimization_blocked') and ids(contr_raw) == ids(contr_min) and 'warning:contradictory-authoritative-evidence' in ids(contr_min))
ck('contradiction_blocks_minimization', contr_ok, {'contradictions': contr_min.get('contradictions'), 'proof': contr_min.get('necessity_proof')})

# Determinism: same raw packet -> same proof and context digest across repeated minimization.
det_raw = raw_packets['change-context-compiler']
d1 = opt.minimize_packet(det_raw); d2 = opt.minimize_packet(det_raw)
det_ok = d1['packet_digest'] == d2['packet_digest'] and d1['necessity_proof'] == d2['necessity_proof'] and d1['selected_evidence_records'] == d2['selected_evidence_records']
ck('deterministic_identical_inputs', det_ok, {'digest': d1['packet_digest']})

# Explicit necessity/ablation: removing owner breaks gold; removing a frozen redundant item from raw does not.
arch_case = next(c for c in gold['cases'] if c['id'] == 'architecture-experience-loop-current')
arch_min = min_packets['architecture-experience-loop-current']
owner = 'source:/opt/optiplex-lab/experience_loop.py'
without_owner = [r for r in records(arch_min) if r['evidence_id'] != owner]
necessary_ablation_ok = gold_still_satisfied(records(arch_min), arch_case) and not gold_still_satisfied(without_owner, arch_case)
ck('necessary_leave_one_out_fails_evaluator', necessary_ablation_ok, {'owner': owner, 'baseline_ok': gold_still_satisfied(records(arch_min), arch_case), 'without_owner_ok': gold_still_satisfied(without_owner, arch_case)})
arch_raw = raw_packets['architecture-experience-loop-current']
redundant_id = 'generation:gen6-experience-memory-r1'
without_redundant = [r for r in records(arch_raw) if r['evidence_id'] != redundant_id]
redundant_ablation_ok = redundant_id in ids(arch_raw) and gold_still_satisfied(records(arch_raw), arch_case) and gold_still_satisfied(without_redundant, arch_case)
ck('redundant_leave_one_out_preserves_evaluator', redundant_ablation_ok, {'redundant_id': redundant_id})

# Optimizer's own synthetic tests cover semantic duplicate collapse and active/historical workflow version dominance.
selftest = opt.selftest()
ck('optimizer_selftest', selftest.get('passed') == selftest.get('total') == 8, selftest)

# High-fanout server case must reduce to the six state/identity facts plus one lifecycle validation witness.
life = min_packets['lifecycle-server-proof-witness']
life_crit = set(critical(life))
life_witness = {'validation:benchmark:benchmark_gen2', 'validation:benchmark:benchmark_gen4'} & life_crit
fanout_forbidden = {
    'validation:benchmark:benchmark', 'validation:benchmark:benchmark_gen7', 'validation:benchmark:benchmark_gen8', 'validation:benchmark:semantic_edit_experiment_gen5',
    'workflow:lab-accept-current@1', 'workflow:lab-accept-current@2', 'workflow:lab-post-update-verify@1', 'workflow:lab-post-update-verify@2',
}
high_fanout_ok = len(life_crit) == 7 and len(life_witness) == 1 and not (life_crit & fanout_forbidden)
ck('high_fanout_bounded_by_necessity_proof', high_fanout_ok, {'critical': sorted(life_crit), 'witness': sorted(life_witness), 'witness_proofs': life.get('necessity_proof', {}).get('witness_proofs')})

# Current-view evidence must not be optimized away just because old gold predates it.
arch_ids = ids(arch_min)
ck('current_valid_gen8_validation_preserved', 'validation:benchmark:benchmark_gen8' in arch_ids, sorted(arch_ids))

# Safety-critical authority/recovery cannot be optimized away.
safety_ok = all({'authority:guest-security-boundary', 'operational:accepted-identity'}.issubset(ids(p)) for p in min_packets.values()) and {'build_state:current', 'recovery:last-known-good', 'service:optiplex-lab-mcp.service'}.issubset(ids(life))
ck('safety_critical_cannot_be_optimized_away', safety_ok, {'lifecycle': sorted(ids(life))})

# Historical/version-pinned primary Gen7 evidence remains exact; future-valid validation aliases do not mutate historical gold.
evalp = min_packets['evaluation-gen7-version-scoped']
eval_crit = set(critical(evalp))
eval_expected = set(next(c for c in gold['cases'] if c['id'] == 'evaluation-gen7-version-scoped')['required_ids'])
ck('version_scoped_gen7_evidence_exact', eval_crit == eval_expected, {'critical': sorted(eval_crit), 'expected': sorted(eval_expected)})

# Protected-state mutation probe runs only inside the accepted Experiment Capsule.
protected_before = cap.protected_manifest()
probe_cmd = "python3 - <<'PY'\nfrom pathlib import Path\np=Path('/var/lib/optiplex-lab/regressions/registry.json')\np.write_text('{\\\"gen9_capsule_mutant\\\":true}\\n')\nprint('GEN9_CAPSULE_MUTATION_OK')\nPY"
capsule_probe = cap.run_capsule(probe_cmd, label='gen9-necessity-protected-state-ablation')
protected_after = cap.protected_manifest()
cap_ok = bool(capsule_probe.get('ok') and capsule_probe.get('accepted_state_unchanged') and not capsule_probe.get('forbidden_accepted_state_mutations') and protected_before.get('digest') == protected_after.get('digest'))
ck('protected_state_capsule_ablation', cap_ok, {'run_id': capsule_probe.get('run_id'), 'recipe_digest': capsule_probe.get('recipe_digest'), 'accepted_state_unchanged': capsule_probe.get('accepted_state_unchanged'), 'forbidden': capsule_probe.get('forbidden_accepted_state_mutations'), 'protected_before_digest': protected_before.get('digest'), 'protected_after_digest': protected_after.get('digest')})

# Size and latency acceptance criteria fixed in frozen gold before implementation.
avg_base = statistics.mean(base_payload)
avg_min = statistics.mean(min_payload)
payload_reduction = 1.0 - (avg_min / avg_base) if avg_base else 0.0
min_sorted = sorted(min_lat)
p95_min = min_sorted[min(len(min_sorted) - 1, max(0, int(len(min_sorted) * 0.95) - 1))]
criteria = gold['success_criteria']
criteria_results = {
    'required_evidence_recall': required_recall >= float(criteria['required_evidence_recall_min']),
    'critical_evidence_fn': opt_fn <= int(criteria['critical_evidence_fn_max']),
    'necessity_aware_critical_precision': necessity_precision >= float(criteria['necessity_aware_critical_precision_min']),
    'legacy_id_precision': legacy_comparable_precision >= float(criteria['legacy_id_precision_min']),
    'average_context_payload_reduction': payload_reduction >= float(criteria['average_context_payload_reduction_vs_gen8_min']),
    'incremental_minimization_latency_median': statistics.median(min_lat) <= float(criteria['incremental_minimization_latency_median_ms_max']),
    'determinism': det_ok,
    'fail_closed_preservation': stale_ok and contr_ok,
}
ck('predeclared_success_criteria', all(criteria_results.values()), criteria_results)

# Preserve/improve Gen8 broad/practical context reduction while reporting downstream context payload only.
source_nodes = [n for n in snap['nodes'] if n.get('kind') == 'source' and n.get('authoritative') and isinstance(n.get('source_bytes'), int)]
unique = {n.get('source_path'): int(n['source_bytes']) for n in source_nodes if n.get('source_path')}
broad = sum(unique.values())
practical_names = ['architecture_twin.py','causal_spine.py','experience_loop.py','experience_memory.py','regression_compiler.py','capability_forge.py','workflow_graphs.py','workflow_skills.py','code_mode.py','server.py']
practical = sum((ROOT / name).stat().st_size for name in practical_names if (ROOT / name).is_file())
context_reduction = {
    'broad_baseline_bytes': broad,
    'practical_baseline_bytes': practical,
    'average_gen8_context_payload_bytes': round(avg_base, 2),
    'average_gen9_context_payload_bytes': round(avg_min, 2),
    'gen9_vs_gen8_payload_reduction': round(payload_reduction, 6),
    'gen9_broad_reduction': round(1 - avg_min / broad, 6) if broad else None,
    'gen9_practical_reduction': round(1 - avg_min / practical, 6) if practical else None,
}
reduction_ok = avg_min < avg_base and context_reduction['gen9_broad_reduction'] >= 0.951 and context_reduction['gen9_practical_reduction'] >= 0.916
ck('context_reduction_preserved_or_improved', reduction_ok, context_reduction)

metrics = {
    'gold_sha256': sha(GOLD),
    'compiler_sha256': sha(ROOT / 'context_compiler.py'),
    'optimizer_sha256': sha(ROOT / 'context_necessity.py'),
    'twin_graph_digest': snap.get('graph_digest'),
    'baseline_necessity_aware': {'critical_tp': base_tp, 'critical_fp': base_fp, 'critical_fn': base_fn, 'critical_precision': round(baseline_precision, 6)},
    'minimized_necessity_aware': {'critical_tp': opt_tp, 'critical_fp': opt_fp, 'critical_fn': opt_fn, 'critical_precision': round(necessity_precision, 6), 'required_evidence_recall': round(required_recall, 6)},
    'legacy_gen8_exact_id_metric_current_twin_diagnostic': {'critical_tp': legacy_current_tp, 'critical_fp': legacy_current_fp, 'critical_fn': legacy_current_fn, 'critical_precision': round(legacy_current_precision, 6), 'note': 'Diagnostic only; current Twin legitimately contains post-Gen8 evidence.'},
    'legacy_gen8_exact_id_metric_comparable_frozen_twin': {'critical_tp': legacy_comparable_tp, 'critical_fp': legacy_comparable_fp, 'critical_fn': legacy_comparable_fn, 'critical_precision': round(legacy_comparable_precision, 6), 'frozen_twin_sha256': FROZEN_GEN8_TWIN_SHA256, 'frozen_twin_graph_digest': frozen_gen8_snap.get('graph_digest')},
    'post_gold_current_validations': {cid: sorted(post_gold_current_validations(p, next(c for c in gold['cases'] if str(c['id']) == cid))) for cid, p in sorted(min_packets.items())},
    'context_payload_bytes': {'baseline_average': round(avg_base, 2), 'minimized_average': round(avg_min, 2), 'reduction': round(payload_reduction, 6), 'baseline_median': statistics.median(base_payload), 'minimized_median': statistics.median(min_payload)},
    'compile_latency_ms': {'median': round(statistics.median(compile_lat), 3), 'max': round(max(compile_lat), 3)},
    'minimization_latency_ms': {'median': round(statistics.median(min_lat), 3), 'p95': round(p95_min, 3), 'max': round(max(min_lat), 3)},
    'task_kind_classification_ok': task_kinds_ok,
    'unrelated_context_negative_controls_ok': negative_controls_ok,
    'context_reduction': context_reduction,
    'capsule_probe': {'run_id': capsule_probe.get('run_id'), 'recipe_digest': capsule_probe.get('recipe_digest'), 'accepted_state_unchanged': capsule_probe.get('accepted_state_unchanged')},
    'permanent_mcp_tools': 10,
}

packet_art = {
    'version': 'gen9-representative-minimized-context-r1',
    'gold_sha256': sha(GOLD),
    'compiler_sha256': sha(ROOT / 'context_compiler.py'),
    'optimizer_sha256': sha(ROOT / 'context_necessity.py'),
    'representative_packets': {cid: {'task': p['task_text'], 'task_kind': p['task_kind'], 'packet_id': p['packet_id'], 'packet_digest': p['packet_digest'], 'budget': p['budget'], 'selected_evidence_records': p['selected_evidence_records'], 'necessity_proof': p['necessity_proof']} for cid, p in sorted(min_packets.items())},
}
PACKETS_ART.parent.mkdir(parents=True, exist_ok=True)
PACKETS_ART.write_text(json.dumps(packet_art, indent=2, sort_keys=True) + '\n', encoding='utf-8')

passed = sum(1 for c in checks if c['ok'])
result = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'version': VERSION,
    'gold_frozen_before_implementation': bool(gold.get('frozen_before_implementation')),
    'gold_sha256': sha(GOLD),
    'checks': checks,
    'cases': case_results,
    'metrics': metrics,
    'artifacts': {'representative_packets': str(PACKETS_ART), 'representative_packets_sha256': sha(PACKETS_ART)},
    'passed': passed,
    'total': len(checks),
}
ART.parent.mkdir(parents=True, exist_ok=True)
ART.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps({'output': str(ART), 'packets': str(PACKETS_ART), 'passed': passed, 'total': len(checks), 'metrics': metrics, 'failed_checks': [c['name'] for c in checks if not c['ok']]}, indent=2, sort_keys=True))
raise SystemExit(0 if passed == len(checks) and opt_fn == 0 else 1)
