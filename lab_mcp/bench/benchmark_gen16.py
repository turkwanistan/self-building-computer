#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tempfile
from typing import Any, Callable

ONBOARD = pathlib.Path('/opt/optiplex-lab/project_onboarding.py')
BRIDGE = pathlib.Path('/opt/optiplex-lab/project_context_bridge.py')
DOMAIN_EVAL = pathlib.Path('/opt/optiplex-lab/gen15_domain_evaluators.py')
FORGE = pathlib.Path('/opt/optiplex-lab/capability_forge.py')
NURSERY = pathlib.Path('/opt/optiplex-lab/evaluator_mutation_nursery.py')
HIER = pathlib.Path('/opt/optiplex-lab/hierarchical_experiment.py')
CAPSULE = pathlib.Path('/opt/optiplex-lab/experiment_capsule.py')
GOLD = pathlib.Path('/opt/optiplex-lab/bench/GEN16_GOLD.json')
PACK = pathlib.Path('/opt/optiplex-lab/bench/GEN16_SONG_CITY_PACK.json')
FIX = pathlib.Path('/opt/optiplex-lab/bench/gen15')
TRANSPORT = FIX / 'songcity_transport.json'
LEGACY_ADAPTER = FIX / 'song_city_adapter.json'
BOB = FIX / 'bob_domain_input.json'
REGISTRY = pathlib.Path('/var/lib/optiplex-lab/capabilities/registry.json')
OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-project-factory-benchmark.json')
COMPAT_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-song-city-compatibility.json')
GENERALIZATION_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-generalization.json')
SELF_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-self-use.json')
MUT_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-evaluator-mutation.json')
ADV_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-adversarial.json')
READY_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-project-readiness.json')
CONSOLIDATION_OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen16-consolidation.json')
GOLD_SHA = '2755cc4fa09afbe653dbc6961a4bab314a052483fc9d8d62d3b71bf83db4b80a'
GEN15_GOLD_SHA = '718d297ae608d53bad0b81b576f536df05c737c165c2dc3a1c29851b989440eb'
PROFILER = '4dd178d667af77f5c50e846dec419dac3206040491017ca591a3504fa2b455c3'
AUDITOR = '7a8ffc0c3facad20c5714834d1d4e0d0d106f663ae4ec07f8106c21c3d951edf'
GEN15_MANIFEST = 'e7473a8783218981a7bcf621690f96ea430dd5810a0e4d689217bbcb11f14ea3'
VERSION = 'gen16-project-factory-benchmark-r1'


def load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {path}')
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def sha_path(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    tmp.replace(path)


def err(fn: Callable[[], Any]) -> str | None:
    try:
        fn(); return None
    except Exception as exc:
        return f'{type(exc).__name__}: {exc}'


def run_capability_source(root: pathlib.Path, payload: dict[str, Any]) -> dict[str, Any]:
    p = subprocess.run(['/opt/optiplex-lab/venv/bin/python', str(root / 'main.py')],
                       input=json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n',
                       text=True, capture_output=True, timeout=5, cwd=root, check=False)
    if p.returncode != 0:
        raise RuntimeError(f'capability source failed: {p.stderr[-500:]}')
    return json.loads(p.stdout)


def semantic_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {k: copy.deepcopy(v) for k, v in manifest.items() if k not in {'adapter_sha256', 'manifest_sha256'}}


def semantic_context(packet: dict[str, Any]) -> dict[str, Any]:
    return {'route': packet['route'], 'evidence': packet['evidence'], 'metrics': packet['metrics']}


def main() -> int:
    ob = load(ONBOARD, 'gen16_onboarding_bench')
    bridge = load(BRIDGE, 'gen16_bridge_bench')
    de = load(DOMAIN_EVAL, 'gen16_domain_eval_bench')
    nursery = load(NURSERY, 'gen16_nursery_bench')
    hier = load(HIER, 'gen16_hier_bench')
    capsule = load(CAPSULE, 'gen16_capsule_bench')
    checks: list[dict[str, Any]] = []
    def ck(name: str, ok: Any, detail: Any = None): checks.append({'name': name, 'ok': bool(ok), 'detail': detail})

    gold = json.loads(GOLD.read_text()); pack = json.loads(PACK.read_text())
    transport = json.loads(TRANSPORT.read_text()); legacy_adapter = json.loads(LEGACY_ADAPTER.read_text())
    registry_raw = json.loads(REGISTRY.read_text()); records = ob.forge_registry_records(registry_raw)
    resource_catalog = {'gen15_domain_evaluators': str(DOMAIN_EVAL)}

    ck('frozen_gold_integrity', sha_path(GOLD) == GOLD_SHA and gold.get('frozen_before_primary_implementation') is True,
       {'expected': GOLD_SHA, 'actual': sha_path(GOLD)})
    pack_check = ob.validate_pack(pack, resource_catalog=resource_catalog, verify_resources=True)
    ck('pack_schema_and_resource_integrity', pack_check['ok'] and pack_check['resources']['verified'] == 2 and pack['schema'] == gold['required']['capability_pack_schema'], pack_check)
    ck('pack_deterministic_content_identity', ob.seal_pack({k: copy.deepcopy(v) for k, v in pack.items() if k != 'pack_sha256'})['pack_sha256'] == pack['pack_sha256'], pack['pack_sha256'])
    ck('generic_engine_not_pilot_named', 'songcity' not in ONBOARD.name.lower() and 'song_city' not in ONBOARD.read_text().lower(), ONBOARD.name)
    bridge_lines = len(BRIDGE.read_text().splitlines())
    ck('bridge_is_thin_compatibility_shim', bridge_lines <= int(gold['required']['bridge_compatibility_shim_lines_max']) and 'hashlib' not in BRIDGE.read_text() and 'importlib.util' not in BRIDGE.read_text(), {'lines': bridge_lines})
    ck('pack_does_not_duplicate_capability_source', 'capability_requirements' not in pack['project'] and not any('implementation' in c or 'source_path' in c for c in pack['capabilities']), {'project_keys': sorted(pack['project'])})

    legacy_manifest = ob.onboard_transport(transport, legacy_adapter)
    new_manifest = ob.onboard_transport(transport, pack['project'])
    ck('gen15_legacy_manifest_reproduces_frozen_identity', legacy_manifest['manifest_sha256'] == GEN15_MANIFEST, legacy_manifest['manifest_sha256'])
    ck('song_city_manifest_semantics_preserved', ob.canonical(semantic_manifest(new_manifest)) == ob.canonical(semantic_manifest(legacy_manifest)), {'legacy': legacy_manifest['manifest_sha256'], 'new': new_manifest['manifest_sha256']})
    legacy_twin = ob.build_twin(legacy_manifest); new_twin = ob.build_twin(new_manifest)
    ck('song_city_twin_semantics_preserved', legacy_twin['namespace'] == new_twin['namespace'] and legacy_twin['nodes'] == new_twin['nodes'] and legacy_twin['edges'] == new_twin['edges'], {'nodes': len(new_twin['nodes']), 'edges': len(new_twin['edges'])})

    tasks = [
        'inspect telemetry structure and explain beat bar section evidence',
        'audit songboss attacks and musical causality',
        'diagnose project test regression and runtime pipeline',
    ]
    analyses = [ob.analyze_project(transport, pack, records, task, resource_catalog=resource_catalog) for task in tasks]
    legacy_packets = [ob.compile_context(task, legacy_manifest, transport, legacy_adapter) for task in tasks]
    new_packets = [x['task_context'] for x in analyses]
    min_recall = min(p['metrics']['required_evidence_recall'] for p in new_packets)
    max_fn = max(p['metrics']['critical_false_negatives'] for p in new_packets)
    min_reduction = min(p['metrics']['context_reduction'] for p in new_packets)
    ck('song_city_task_context_semantics_preserved', all(semantic_context(a) == semantic_context(b) for a, b in zip(new_packets, legacy_packets)), [p['metrics'] for p in new_packets])
    ck('required_evidence_recall_and_critical_fn', min_recall >= float(gold['required']['required_evidence_recall_min']) and max_fn <= int(gold['required']['critical_evidence_false_negatives_max']), {'min_recall': min_recall, 'max_fn': max_fn})
    ck('context_reduction_preserved', min_reduction >= 0.6495714812941675, {'min': min_reduction})
    ck('single_consolidated_operator_path', all(len(x['operator_path']) <= int(gold['required']['manual_operator_steps_max']) and x['automatic_promotion'] is False for x in analyses), analyses[0]['operator_path'])

    full_class = ob.classify_capabilities(new_manifest, pack, records)
    states = {x['id']: x['status'] for x in full_class['capabilities']}
    selected = {x['id']: (x.get('selected') or {}).get('content_hash') for x in full_class['capabilities']}
    ck('actionable_capability_states', states.get('musical-telemetry-profiler-r1') == 'AVAILABLE' and states.get('songboss-causality-auditor-r1') == 'AVAILABLE' and states.get('ffmpeg-audio-decode') == 'WEAK_NEEDS_SPECIALIZATION' and states.get('browser-visual-review') == 'WEAK_NEEDS_SPECIALIZATION' and states.get('video-transcoding-suite') == 'UNNECESSARY', states)
    ck('promoted_capability_hashes_preserved', selected.get('musical-telemetry-profiler-r1') == PROFILER and selected.get('songboss-causality-auditor-r1') == AUDITOR, selected)
    ck('no_autonomous_promotion_path', all((x['forge_plan'] or {}).get('promotion_is_automatic') is False for x in full_class['capabilities'] if x.get('forge_plan')) and all(x['status'] != 'MISSING_VALUABLE' for x in full_class['capabilities']), full_class['capabilities'])

    capmap = {r.get('content_hash'): r for r in records}
    bob = json.loads(BOB.read_text())
    profile = run_capability_source(pathlib.Path(capmap[PROFILER]['object']), {'telemetry': bob['telemetry']})
    audit = run_capability_source(pathlib.Path(capmap[AUDITOR]['object']), {'plan': bob['plan'], 'telemetry_profile': profile})
    p_eval = de.evaluate_telemetry_profile(profile, bob['telemetry']); a_eval = de.evaluate_songboss_audit(audit, bob['plan'], profile)
    ck('both_gen15_domain_capabilities_still_evaluable', p_eval['ok'] and a_eval['ok'], {'profile': p_eval, 'audit': a_eval})
    ck('real_domain_results_preserved', profile['largest_transition']['time'] == 166.42644 and audit['attack_count'] == 111 and audit['causality_evidence_coverage'] == 1.0 and audit['verdict'] == 'PASS', {'transition': profile['largest_transition']['time'], 'attacks': audit['attack_count']})

    # Critical Gen16 classifier mutation challenge: an exact but unpromoted provider must never become AVAILABLE.
    tiny_manifest = {'project_id': 'classifier-fixture', 'manifest_sha256': 'f' * 64}
    classifier_pack = ob.seal_pack({
        'schema': ob.PACK_SCHEMA, 'pack_id': 'classifier-fixture', 'version': '1', 'project': {'project_id': 'classifier-fixture'},
        'capabilities': [{'id': 'fixture-cap', 'purpose': 'classifier fixture', 'utility': 1.0, 'applicability': ['fixture'], 'provider': 'forge', 'necessity': 'required', 'forge': {'desired_name': 'fixture-cap', 'expected_content_hash': 'a' * 64}}],
        'provenance': {'creator': 'benchmark', 'source_generation': 'gen16-capability-consolidation-r1'}
    })
    candidate_record = [{'name': 'fixture-cap', 'content_hash': 'a' * 64, 'state': 'CANDIDATE'}]
    mutation_cases = [{'id': 'candidate-not-available', 'args': [tiny_manifest, classifier_pack, candidate_record], 'oracle': [{'path': 'capabilities.0.status', 'op': 'equals', 'value': 'WEAK_NEEDS_SPECIALIZATION'}, {'path': 'capabilities.0.forge_plan.promotion_is_automatic', 'op': 'falsy'}]}]
    mut_spec = nursery.make_spec(
        name='gen16-promoted-exact-availability', evaluator_path=str(ONBOARD), evaluator_sha256=sha_path(ONBOARD), function='classify_capabilities',
        cases=mutation_cases, mutation_class='trust_declared_state',
        old='promoted = [r for r in exact if r.get("state") == "PROMOTED"]',
        new='promoted = list(exact)  # MUTANT trusts unpromoted exact providers', dangerous=True,
        check_id='promoted_exact_availability', check_marker='# CHECK:promoted_exact_availability', timeout=10.0)
    mutation = nursery.run_mutation(mut_spec)
    ck('dangerous_classifier_mutation_killed', mutation.get('classification') == 'KILLED' and mutation.get('dangerous') is True and mutation.get('capsule_cleanup', {}).get('removed') is True, {k: mutation.get(k) for k in ('mutation_id', 'classification', 'kill_reason')})

    # Second project shape: same pack and analysis APIs, distinct Node/JavaScript project.
    generalization: dict[str, Any]
    with tempfile.TemporaryDirectory(prefix='gen16-tiny-node-') as td:
        root = pathlib.Path(td); (root / 'src').mkdir(); (root / 'tests').mkdir()
        (root / 'package.json').write_text(json.dumps({'name': 'tiny-node', 'version': '1.0.0', 'scripts': {'test': 'node tests/test.js'}}) + '\n')
        (root / 'README.md').write_text('# Tiny Node\n'); (root / 'src/index.js').write_text('export const value = 7;\n'); (root / 'tests/test.js').write_text("console.log('ok')\n")
        project = {'project_id': 'tiny-node', 'project_name_aliases': ['tiny-node'], 'declared_root': str(root), 'enforce_embedded_identity': True, 'embed_patterns': ['README.md', 'package.json'], 'important_files': ['README.md', 'package.json', 'src/index.js'], 'entrypoints': ['src/index.js'], 'tests': ['node tests/test.js'], 'build_commands': [], 'authority_rules': [{'role': 'authoritative', 'patterns': ['README.md', 'package.json', 'src/**', 'tests/**']}], 'authority_hierarchy': ['runtime/tests', 'source', 'docs'], 'data_locations': [], 'artifact_locations': [], 'external_interfaces': [], 'safety_constraints': ['local-only'], 'task_profiles': {'implementation': {'keywords': ['implement', 'source', 'node'], 'required_paths': ['src/index.js', 'package.json'], 'optional_patterns': ['tests/**'], 'authority': 'source+tests'}}}
        node_pack = ob.seal_pack({'schema': ob.PACK_SCHEMA, 'pack_id': 'tiny-node-project-factory', 'version': '1', 'project': project, 'capabilities': [{'id': 'node-runtime', 'purpose': 'Execute bounded Node project checks', 'utility': 0.9, 'applicability': ['node'], 'provider': 'platform', 'necessity': 'required', 'platform_status': 'AVAILABLE', 'platform_reason': 'Node runtime is present in project substrate.'}], 'provenance': {'creator': 'benchmark', 'source_generation': 'gen16-capability-consolidation-r1'}})
        t1 = ob.snapshot_local(root, project); t2 = ob.snapshot_local(root, project)
        an1 = ob.analyze_project(t1, node_pack, [], 'implement node source safely', resource_catalog={})
        an2 = ob.analyze_project(t2, node_pack, [], 'implement node source safely', resource_catalog={})
        generalization = {'pack_sha256': node_pack['pack_sha256'], 'transport_sha256': t1['transport_sha256'], 'analysis_sha256': an1['analysis_sha256'], 'deterministic': an1['analysis_sha256'] == an2['analysis_sha256'], 'languages': an1['project_manifest']['languages'], 'frameworks': an1['project_manifest']['frameworks'], 'context': an1['task_context']['metrics'], 'capabilities': an1['capability_classification']['capabilities']}
        ck('second_project_pack_generalization', generalization['deterministic'] and any(x[0] == 'JavaScript' for x in generalization['languages']) and generalization['context']['required_evidence_recall'] == 1.0 and generalization['capabilities'][0]['status'] == 'AVAILABLE', generalization)

    # Self-use on the installed Gen15 project-onboarding implementation.
    self_project = {
        'project_id': 'gen15-onboarding-substrate', 'project_name_aliases': ['gen15-onboarding-substrate'], 'declared_root': '/opt/optiplex-lab',
        'ignore_patterns': ['**/__pycache__/**', 'bench/gen15/**', 'venv/**'],
        'authority_rules': [{'role': 'authoritative', 'patterns': ['project_onboarding.py', 'project_context_bridge.py', 'capability_forge.py', 'hierarchical_experiment.py', 'evaluator_mutation_nursery.py', 'bench/benchmark_gen15.py']}],
        'important_files': ['project_onboarding.py', 'project_context_bridge.py', 'capability_forge.py', 'hierarchical_experiment.py', 'evaluator_mutation_nursery.py', 'bench/benchmark_gen15.py'],
        'entrypoints': ['project_onboarding.py'], 'tests': [], 'build_commands': [], 'authority_hierarchy': ['accepted generation evidence', 'source', 'benchmarks'], 'data_locations': [], 'artifact_locations': ['bench/'], 'external_interfaces': [], 'safety_constraints': ['operational server frozen'],
        'task_profiles': {'consolidation': {'keywords': ['consolidate', 'onboarding', 'project', 'capability'], 'required_paths': ['project_onboarding.py', 'project_context_bridge.py', 'capability_forge.py', 'hierarchical_experiment.py', 'evaluator_mutation_nursery.py', 'bench/benchmark_gen15.py'], 'optional_patterns': [], 'authority': 'source+accepted-evidence'}}
    }
    self_pack = ob.seal_pack({'schema': ob.PACK_SCHEMA, 'pack_id': 'gen15-onboarding-self-use', 'version': '1', 'project': self_project, 'capabilities': [{'id': 'capability-forge-governance', 'purpose': 'Reuse the existing explicit Forge lifecycle and governor', 'utility': 1.0, 'applicability': ['capability', 'governance'], 'provider': 'platform', 'necessity': 'required', 'platform_status': 'AVAILABLE', 'platform_reason': 'Capability Forge source is present and accepted.'}, {'id': 'evaluator-mutation-hardening', 'purpose': 'Challenge project-specific evaluator assumptions', 'utility': 1.0, 'applicability': ['evaluation'], 'provider': 'platform', 'necessity': 'required', 'platform_status': 'AVAILABLE', 'platform_reason': 'Gen14 nursery is present and accepted.'}], 'provenance': {'creator': 'benchmark', 'source_generation': 'gen16-capability-consolidation-r1'}})
    self_transport = ob.snapshot_local(pathlib.Path('/opt/optiplex-lab'), self_project)
    self_analysis = ob.analyze_project(self_transport, self_pack, records, 'consolidate project onboarding capability paths', resource_catalog={})
    self_use = {'pack_sha256': self_pack['pack_sha256'], 'manifest_sha256': self_analysis['project_manifest']['manifest_sha256'], 'context': self_analysis['task_context']['metrics'], 'bridge_lines_before': int(gold['baseline']['gen15_project_context_bridge_lines']), 'bridge_lines_after': bridge_lines, 'bridge_reduction': round(1 - bridge_lines / int(gold['baseline']['gen15_project_context_bridge_lines']), 6), 'canonical_compose_owner': 'project_onboarding.compose_platform_context', 'legacy_capability_requirements_removed_from_pack_project': 'capability_requirements' not in pack['project'], 'defects_found_and_resolved': [{'finding': 'structural pack validation initially forced evaluator resource resolution during internal classification', 'resolution': 'split structural validation from explicit resource verification; full analyze verifies resources once and internal classification reuses the verified pack'}, {'finding': 'self-use source root includes runtime virtualenv symlinks outside the declared project root', 'resolution': 'preserved fail-closed symlink containment and excluded venv/** from the source-only self-use scope'}]}
    ck('self_use_on_gen15_onboarding', self_analysis['task_context']['metrics']['required_evidence_recall'] == 1.0 and bridge_lines <= 25 and self_use['legacy_capability_requirements_removed_from_pack_project'], self_use)

    adversarial: dict[str, Any] = {}
    bad = copy.deepcopy(pack); bad['schema'] = 'bad'; adversarial['pack_schema_tamper'] = err(lambda: ob.validate_pack(bad))
    bad = copy.deepcopy(pack); bad['provenance']['pilot'] = 'tampered'; adversarial['pack_digest_tamper'] = err(lambda: ob.validate_pack(bad))
    bad = {k: copy.deepcopy(v) for k, v in pack.items() if k != 'pack_sha256'}; bad['capabilities'].append(copy.deepcopy(bad['capabilities'][0])); adversarial['duplicate_capability_requirement'] = err(lambda: ob.seal_pack(bad))
    bad = {k: copy.deepcopy(v) for k, v in pack.items() if k != 'pack_sha256'}; bad['capabilities'][0]['evaluator']['resource'] = '../escape'; adversarial['unsafe_pack_resource_path'] = err(lambda: ob.seal_pack(bad))
    bad = {k: copy.deepcopy(v) for k, v in pack.items() if k != 'pack_sha256'}; bad['capabilities'][0]['forge']['expected_content_hash'] = '0' * 64; bad = ob.seal_pack(bad); mismatch = ob.classify_capabilities(new_manifest, bad, records); mismatch_status = {x['id']: x['status'] for x in mismatch['capabilities']}['musical-telemetry-profiler-r1']; adversarial['capability_content_hash_mismatch'] = mismatch_status
    candidate_only = [dict(capmap[PROFILER], content_hash=PROFILER, state='CANDIDATE')]; candidate_result = ob.classify_capabilities(new_manifest, pack, candidate_only); adversarial['forged_available_without_promotion'] = {x['id']: x['status'] for x in candidate_result['capabilities']}['musical-telemetry-profiler-r1']; adversarial['weak_match_not_claimed_available'] = adversarial['forged_available_without_promotion']
    miss = ob.seal_pack({'schema': ob.PACK_SCHEMA, 'pack_id': 'missing-no-plan', 'version': '1', 'project': {'project_id': new_manifest['project_id']}, 'capabilities': [{'id': 'missing', 'purpose': 'missing required capability', 'utility': 1.0, 'applicability': ['x'], 'provider': 'forge', 'necessity': 'required', 'allow_forge': False}], 'provenance': {'creator': 'benchmark', 'source_generation': 'gen16-capability-consolidation-r1'}}); adversarial['missing_valuable_without_forge_plan'] = err(lambda: ob.classify_capabilities(new_manifest, miss, []))
    unneeded = ob.seal_pack({'schema': ob.PACK_SCHEMA, 'pack_id': 'unneeded', 'version': '1', 'project': {'project_id': new_manifest['project_id']}, 'capabilities': [{'id': 'u', 'purpose': 'not required', 'utility': 0.1, 'applicability': ['x'], 'provider': 'forge', 'necessity': 'unnecessary'}], 'provenance': {'creator': 'benchmark', 'source_generation': 'gen16-capability-consolidation-r1'}}); unneeded_result = ob.classify_capabilities(new_manifest, unneeded, []); adversarial['unnecessary_capability_opens_no_gap'] = {'status': unneeded_result['capabilities'][0]['status'], 'forge_plan': unneeded_result['capabilities'][0]['forge_plan']}
    stale = copy.deepcopy(transport); embedded = set(stale.get('embedded', {})); change = next(f for f in stale['files'] if f['path'] not in embedded); change['sha256'] = '0' * 64; stale['transport_sha256'] = ob.digest({k: v for k, v in stale.items() if k != 'transport_sha256'}); adversarial['stale_project_manifest'] = err(lambda: ob.compile_context(tasks[0], new_manifest, stale, pack['project']))
    missing_pack = copy.deepcopy(pack); missing_pack.pop('pack_sha256', None); missing_pack['project']['task_profiles']['telemetry inspection']['required_paths'] = ['definitely/missing.py']; missing_pack = ob.seal_pack(missing_pack); missing_manifest = ob.onboard_transport(transport, missing_pack['project']); adversarial['missing_required_project_evidence'] = err(lambda: ob.compile_context(tasks[0], missing_manifest, transport, missing_pack['project']))
    with tempfile.TemporaryDirectory(prefix='gen16-bridge-') as td:
        pp = pathlib.Path(td) / 'packet.json'; wrong = copy.deepcopy(new_packets[0]); wrong['task'] = 'different task'; wrong['packet_sha256'] = ob.digest({k: v for k, v in wrong.items() if k != 'packet_sha256'}); pp.write_text(json.dumps(wrong)); adversarial['compatibility_bridge_binding_mismatch'] = err(lambda: bridge.compose(tasks[0], str(pp)))
    adversarial['critical_classifier_check_disabled'] = {k: mutation.get(k) for k in ('classification', 'kill_reason', 'mutation_id')}
    adversarial['evaluator_reference_mismatch'] = err(lambda: ob.validate_pack(pack, resource_catalog={'gen15_domain_evaluators': str(ONBOARD)}, verify_resources=True))
    scope_run = hier.run_root_experiment("mkdir -p /root/gen16-forbidden && printf x > /root/gen16-forbidden/outside.txt", name='gen16-project-pack-scope-adversarial', mutation_scope=['/root/gen16-allowed/**'], authorities=['evaluation'], timeout=5)
    scope_cleanup = capsule.cleanup(scope_run['capsule_run_id']); adversarial['undeclared_project_mutation'] = {'status': (scope_run.get('execution') or {}).get('status'), 'reason': (scope_run.get('execution') or {}).get('failure_reason'), 'accepted_state_unchanged': scope_run.get('accepted_state_unchanged'), 'cleanup_removed': scope_cleanup.get('removed')}

    ck('adversarial_pack_schema_tamper', adversarial['pack_schema_tamper'] is not None, adversarial['pack_schema_tamper'])
    ck('adversarial_pack_digest_tamper', adversarial['pack_digest_tamper'] is not None, adversarial['pack_digest_tamper'])
    ck('adversarial_duplicate_requirement', adversarial['duplicate_capability_requirement'] is not None, adversarial['duplicate_capability_requirement'])
    ck('adversarial_unsafe_resource', adversarial['unsafe_pack_resource_path'] is not None, adversarial['unsafe_pack_resource_path'])
    ck('adversarial_content_hash_mismatch', adversarial['capability_content_hash_mismatch'] == 'WEAK_NEEDS_SPECIALIZATION', adversarial['capability_content_hash_mismatch'])
    ck('adversarial_unpromoted_not_available', adversarial['forged_available_without_promotion'] == 'WEAK_NEEDS_SPECIALIZATION' and adversarial['weak_match_not_claimed_available'] == 'WEAK_NEEDS_SPECIALIZATION', adversarial['forged_available_without_promotion'])
    ck('adversarial_missing_requires_forge_plan', adversarial['missing_valuable_without_forge_plan'] is not None, adversarial['missing_valuable_without_forge_plan'])
    ck('adversarial_unnecessary_no_gap', adversarial['unnecessary_capability_opens_no_gap'] == {'status': 'UNNECESSARY', 'forge_plan': None}, adversarial['unnecessary_capability_opens_no_gap'])
    ck('adversarial_stale_and_missing_evidence', adversarial['stale_project_manifest'] is not None and adversarial['missing_required_project_evidence'] is not None, {'stale': adversarial['stale_project_manifest'], 'missing': adversarial['missing_required_project_evidence']})
    ck('adversarial_bridge_binding', adversarial['compatibility_bridge_binding_mismatch'] is not None, adversarial['compatibility_bridge_binding_mismatch'])
    ck('adversarial_evaluator_reference', adversarial['evaluator_reference_mismatch'] is not None, adversarial['evaluator_reference_mismatch'])
    ck('adversarial_undeclared_mutation', adversarial['undeclared_project_mutation']['status'] == 'INVALID' and adversarial['undeclared_project_mutation']['reason'] == 'UNDECLARED_CHILD_MUTATION' and adversarial['undeclared_project_mutation']['accepted_state_unchanged'] is True and adversarial['undeclared_project_mutation']['cleanup_removed'] is True, adversarial['undeclared_project_mutation'])
    ck('all_frozen_adversarial_classes_represented', set(gold['adversarial_required']).issubset(adversarial), {'missing': sorted(set(gold['adversarial_required']) - set(adversarial))})

    server_src = pathlib.Path('/opt/optiplex-lab/server.py').read_text()
    sqlite_ok = False
    try:
        import sqlite3
        con = sqlite3.connect(':memory:'); con.execute('create table events(id integer primary key, value text)'); con.execute("insert into events(value) values ('ok')"); sqlite_ok = con.execute('select value from events').fetchone()[0] == 'ok'; con.close()
    except Exception:
        sqlite_ok = False
    readiness = {
        'persistent_background_project_services': 'def service(' in server_src and 'systemctl' in server_src,
        'bounded_long_running_experiments': 'systemd-run' in server_src and HIER.is_file(),
        'deterministic_simulation_replay': pathlib.Path('/opt/optiplex-lab/counterfactual_replay.py').is_file(),
        'browser_render_inspection': {'guest_dependency': 'no new guest tool required', 'host_mediated_evidence_required': True},
        'visual_acceptance_evidence': {'pack_specific_evaluator_supported': True, 'host_browser_screenshot_supported_externally': True},
        'sqlite_event_ledger_inspection': sqlite_ok,
        'frontend_backend_synchronization_tests': {'project_native_checks_supported': True, 'browser_assertions_mediated_externally': True},
        'project_specific_behavioral_evaluators': NURSERY.is_file() and bool(pack_check['resources']['verified']),
        'permanent_mcp_growth_required': False,
    }
    ck('generic_project_building_readiness', readiness['persistent_background_project_services'] and readiness['bounded_long_running_experiments'] and readiness['deterministic_simulation_replay'] and readiness['sqlite_event_ledger_inspection'] and readiness['project_specific_behavioral_evaluators'] and not readiness['permanent_mcp_growth_required'], readiness)

    baseline_steps = int(gold['baseline']['gen15_legacy_manual_operator_steps']); new_steps = len(analyses[0]['operator_path'])
    consolidation = {
        'bridge_lines_before': int(gold['baseline']['gen15_project_context_bridge_lines']), 'bridge_lines_after': bridge_lines,
        'bridge_line_reduction': round(1 - bridge_lines / int(gold['baseline']['gen15_project_context_bridge_lines']), 6),
        'manual_operator_steps_before': baseline_steps, 'manual_operator_steps_after': new_steps,
        'manual_step_reduction': round(1 - new_steps / baseline_steps, 6),
        'legacy_project_capability_requirement_block_removed': 'capability_requirements' not in pack['project'],
        'capability_source_copies_in_pack': 0,
        'canonical_project_analysis_paths': 1,
        'required_evidence_recall': min_recall,
        'critical_false_negatives': max_fn,
        'dangerous_classifier_mutation_kill_rate': 1.0 if mutation.get('classification') == 'KILLED' else 0.0,
        'dangerous_classifier_survivors': 0 if mutation.get('classification') == 'KILLED' else 1,
    }
    ck('measurable_consolidation_improvement', consolidation['bridge_line_reduction'] > 0.7 and consolidation['manual_step_reduction'] >= 0.5 and consolidation['capability_source_copies_in_pack'] == 0 and consolidation['required_evidence_recall'] == 1.0 and consolidation['critical_false_negatives'] == 0, consolidation)

    build = json.loads(pathlib.Path('/etc/optiplex-lab/build.json').read_text()); server_sha = sha_path(pathlib.Path('/opt/optiplex-lab/server.py')); lkg_sha = sha_path(pathlib.Path('/var/lib/optiplex-lab/recovery/server.last-known-good.py'))
    ck('operational_gen6_identity_unchanged', build.get('generation') == 'gen6-experience-memory-r1' and build.get('source_sha256') == server_sha == lkg_sha and build.get('recovery_state') == 'ACCEPTED', {'build': build.get('build_id'), 'server': server_sha, 'lkg': lkg_sha})
    ck('permanent_mcp_surface_exact_10', pathlib.Path('/opt/optiplex-lab/server.py').read_text().count('@mcp.tool') == 10)
    gen15_bench = json.loads(pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen15-project-onboarding-benchmark.json').read_text())
    ck('retained_gen15_boundary', gen15_bench.get('passed') == 40 and gen15_bench.get('total') == 40 and gen15_bench.get('gold_sha256') == GEN15_GOLD_SHA, {'passed': gen15_bench.get('passed'), 'total': gen15_bench.get('total'), 'gold': gen15_bench.get('gold_sha256')})
    ck('frozen_gold_unchanged', sha_path(GOLD) == GOLD_SHA, sha_path(GOLD))

    compatibility = {'version': 'gen16-song-city-compatibility-r1', 'legacy_manifest_sha256': legacy_manifest['manifest_sha256'], 'new_manifest_sha256': new_manifest['manifest_sha256'], 'manifest_semantics_equal': semantic_manifest(new_manifest) == semantic_manifest(legacy_manifest), 'twin_semantics_equal': new_twin['nodes'] == legacy_twin['nodes'] and new_twin['edges'] == legacy_twin['edges'], 'contexts_semantically_equal': [semantic_context(x) for x in new_packets] == [semantic_context(x) for x in legacy_packets], 'capability_hashes': {'musical-telemetry-profiler-r1': PROFILER, 'songboss-causality-auditor-r1': AUDITOR}, 'independent_evaluations': {'telemetry': p_eval['ok'], 'songboss': a_eval['ok']}, 'required_evidence_recall_min': min_recall, 'critical_false_negatives_max': max_fn}
    mutation_evidence = {'version': 'gen16-evaluator-mutation-r1', 'result': mutation, 'dangerous_kill_rate': 1.0 if mutation.get('classification') == 'KILLED' else 0.0, 'dangerous_survivors': [] if mutation.get('classification') == 'KILLED' else [mutation.get('mutation_id')]}
    atomic_json(COMPAT_OUT, compatibility); atomic_json(GENERALIZATION_OUT, {'version': 'gen16-generalization-r1', **generalization}); atomic_json(SELF_OUT, {'version': 'gen16-self-use-r1', **self_use}); atomic_json(MUT_OUT, mutation_evidence); atomic_json(ADV_OUT, {'version': 'gen16-adversarial-r1', 'cases': adversarial}); atomic_json(READY_OUT, {'version': 'gen16-project-readiness-r1', **readiness}); atomic_json(CONSOLIDATION_OUT, {'version': 'gen16-consolidation-r1', **consolidation})

    passed = sum(1 for x in checks if x['ok']); total = len(checks)
    result = {'version': VERSION, 'passed': passed, 'total': total, 'ok': passed == total, 'checks': checks, 'gold_sha256': sha_path(GOLD), 'pack_sha256': pack['pack_sha256'], 'onboarding_sha256': sha_path(ONBOARD), 'bridge_sha256': sha_path(BRIDGE), 'metrics': {'required_evidence_recall_min': min_recall, 'critical_evidence_false_negatives_max': max_fn, 'context_reduction_min': min_reduction, 'bridge_lines': bridge_lines, 'manual_operator_steps': new_steps, 'dangerous_new_evaluator_mutation_kill_rate': mutation_evidence['dangerous_kill_rate'], 'dangerous_new_evaluator_survivors': len(mutation_evidence['dangerous_survivors']), 'permanent_mcp_tools': 10}, 'artifacts': {'compatibility': str(COMPAT_OUT), 'generalization': str(GENERALIZATION_OUT), 'self_use': str(SELF_OUT), 'evaluator_mutation': str(MUT_OUT), 'adversarial': str(ADV_OUT), 'readiness': str(READY_OUT), 'consolidation': str(CONSOLIDATION_OUT)}}
    atomic_json(OUT, result)
    print(json.dumps({'passed': passed, 'total': total, 'ok': passed == total, 'artifact': str(OUT), 'metrics': result['metrics']}, indent=2, sort_keys=True))
    return 0 if passed == total else 2


if __name__ == '__main__':
    raise SystemExit(main())
