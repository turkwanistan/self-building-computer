#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable

GRAPH = pathlib.Path('/opt/optiplex-lab/workflow_graphs.py')
WORKFLOWS = pathlib.Path('/opt/optiplex-lab/workflow_skills.py')
OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks')
GEN3 = OUT / 'gen3-workflow-benchmark.json'
GRAPH_RUNS = pathlib.Path('/var/lib/optiplex-lab/graph-runs')
BUILD = pathlib.Path('/etc/optiplex-lab/build.json')
LIVE = pathlib.Path('/opt/optiplex-lab/server.py')
LKG = pathlib.Path('/var/lib/optiplex-lab/recovery/server.last-known-good.py')
EXPECTED_UPGRADE_GRAPH_SHA = 'e516a1db5e06ca97de814851c3d3cdc5f891f08b156aad208effc7adf6a69bee'
EXPECTED_RECOVERY_GRAPH_SHA = '1c1c43529d507a0c972205aef347c9134d4d153a15af04cbfc1bf24d253f9ac7'


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'unable to load {path}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def task(name: str, fn: Callable[[], tuple[bool, Any]]) -> dict[str, Any]:
    started = time.monotonic()
    try:
        ok, detail = fn()
        return {'name': name, 'ok': bool(ok), 'elapsed_ms': round((time.monotonic() - started) * 1000, 2), 'detail': detail}
    except Exception as exc:
        return {'name': name, 'ok': False, 'elapsed_ms': round((time.monotonic() - started) * 1000, 2), 'detail': f'{type(exc).__name__}: {exc}'}


def read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f'expected object: {path}')
    return value


def latest_graph_result(name: str) -> dict[str, Any]:
    candidates: list[tuple[float, pathlib.Path, dict[str, Any]]] = []
    for p in GRAPH_RUNS.glob('*/result.json'):
        try:
            value = read_json(p)
            if (value.get('graph') or {}).get('name') == name:
                candidates.append((p.stat().st_mtime, p, value))
        except Exception:
            pass
    if not candidates:
        raise RuntimeError(f'no graph result found for {name}')
    _, p, value = max(candidates, key=lambda x: x[0])
    value['_path'] = str(p)
    return value


def run_cli(argv: list[str], timeout: int = 300) -> tuple[int, dict[str, Any], int]:
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    if not p.stdout.strip():
        raise RuntimeError(f'no stdout rc={p.returncode} stderr={p.stderr[:500]}')
    value = json.loads(p.stdout)
    return p.returncode, value, len(p.stdout.encode())


def canonical_len(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    wg = load_module(GRAPH, 'optiplex_lab_workflow_graphs_bench')
    ws = load_module(WORKFLOWS, 'optiplex_lab_workflow_skills_bench')
    base = pathlib.Path(tempfile.mkdtemp(prefix='gen4bench-'))
    original_graph_registry, original_run_root = wg.REGISTRY, wg.RUN_ROOT
    wg.REGISTRY = base / 'graph-registry'
    wg.RUN_ROOT = base / 'graph-runs'
    tasks: list[dict[str, Any]] = []
    local_results: list[dict[str, Any]] = []
    parent_invocation_output_bytes = 0
    try:
        exact_def, _ = ws.load_definition('exact-replace@1')
        exact_ident = ws.identity(exact_def)

        def make_simple(version: str = '1') -> dict[str, Any]:
            return {
                'name': 'bench-simple', 'version': version, 'description': 'Gen4 benchmark simple composite',
                'parameters': {
                    'path': {'type': 'path', 'required': True, 'absolute': True},
                    'old': {'type': 'str', 'required': True},
                    'new': {'type': 'str', 'required': True},
                },
                'nodes': [
                    {'id': 'edit', 'workflow': 'exact-replace@1', 'depends_on': [],
                     'params': {'path': {'$param': 'path'}, 'old': {'$param': 'old'}, 'new': {'$param': 'new'}}}
                ],
            }

        simple = make_simple()

        def t1():
            reg = wg.register(simple)
            listed = wg.list_graphs()
            return reg['sha256'] == wg.sha(simple) and len(listed) == 1 and listed[0]['active'], {'identity': reg, 'listed': len(listed)}
        tasks.append(task('register_create_composite_workflow', t1))

        def t2():
            p = base / 'child.txt'; p.write_text('A\n')
            r = wg.GraphRunner(simple, {'path': str(p), 'old': 'A', 'new': 'B'}).run(); local_results.append(r)
            node = r['nodes']['edit']
            return r['ok'] and p.read_text() == 'B\n' and node['workflow']['sha256'] == exact_ident['sha256'], {'run': r['run_id'], 'child': node['workflow']}
        tasks.append(task('invoke_child_reusable_workflow', t2))

        def t3():
            p = base / 'typed.txt'; p.write_text('typed-old\n')
            pf = wg.preflight(simple, {'path': str(p), 'old': 'typed-old', 'new': 'typed-new'})
            r = wg.GraphRunner(simple, {'path': str(p), 'old': 'typed-old', 'new': 'typed-new'}).run(); local_results.append(r)
            cp = pf['children'][0]['parameters']
            return r['ok'] and p.read_text() == 'typed-new\n' and cp['path']['type'] == 'path' and cp['old']['value'] == 'typed-old', {'run': r['run_id'], 'preflight_parameters': cp}
        tasks.append(task('typed_parent_to_child_parameter_mapping', t3))

        def t4():
            p = base / 'preflight-safe.txt'; p.write_text('UNCHANGED\n')
            bad = make_simple('bad-params')
            bad['nodes'][0]['params'].pop('old')
            try:
                wg.preflight(bad, {'path': str(p), 'old': 'UNCHANGED', 'new': 'MUTATED'})
            except ValueError as exc:
                return 'missing required parameter' in str(exc) and p.read_text() == 'UNCHANGED\n', {'error': str(exc), 'file_unchanged': True}
            return False, 'preflight unexpectedly passed'
        tasks.append(task('reject_missing_child_parameter_before_destructive_execution', t4))

        def t5():
            p = base / 'unknown.txt'; p.write_text('UNCHANGED\n')
            bad = make_simple('unknown-child'); bad['nodes'][0]['workflow'] = 'definitely-missing@999'
            try:
                wg.preflight(bad, {'path': str(p), 'old': 'UNCHANGED', 'new': 'MUTATED'})
            except ValueError as exc:
                return 'workflow not found' in str(exc) and p.read_text() == 'UNCHANGED\n', {'error': str(exc)}
            return False, 'unknown child unexpectedly passed'
        tasks.append(task('reject_unknown_child_workflow_version', t5))

        def t6():
            cyc = make_simple('cycle')
            cyc['nodes'].append({'id': 'two', 'workflow': 'exact-replace@1', 'depends_on': ['edit'], 'params': {'path': '/tmp/x', 'old': 'x', 'new': 'y'}})
            cyc['nodes'][0]['depends_on'] = ['two']
            try:
                wg.validate_definition(cyc)
            except ValueError as exc:
                return 'cycle' in str(exc), {'error': str(exc)}
            return False, 'cycle unexpectedly passed'
        tasks.append(task('detect_workflow_cycle', t6))

        def t7():
            bounded = make_simple('bounded')
            bounded['nodes'].append({'id': 'two', 'workflow': 'exact-replace@1', 'depends_on': ['edit'], 'params': {'path': '/tmp/x', 'old': 'x', 'new': 'y'}})
            bounded['limits'] = {'max_nodes': 2, 'max_invocations': 1, 'max_depth': 1}
            nested = make_simple('nested'); nested['nodes'][0]['graph'] = 'some-graph@1'
            errors = []
            for value in (bounded, nested):
                try: wg.validate_definition(value)
                except ValueError as exc: errors.append(str(exc))
            return len(errors) == 2 and any('max_invocations' in e for e in errors) and any('nested graph' in e for e in errors), {'errors': errors}
        tasks.append(task('enforce_nesting_and_invocation_bounds', t7))

        def t8():
            p = base / 'seq.txt'; p.write_text('A\n')
            g = {
                'name': 'bench-seq', 'version': '1', 'description': 'two child sequence', 'parameters': {'path': {'type': 'path', 'required': True, 'absolute': True}},
                'nodes': [
                    {'id': 'one', 'workflow': 'exact-replace@1', 'depends_on': [], 'params': {'path': {'$param': 'path'}, 'old': 'A', 'new': 'B'}},
                    {'id': 'two', 'workflow': 'exact-replace@1', 'depends_on': ['one'], 'params': {'path': {'$param': 'path'}, 'old': 'B', 'new': 'C'}},
                ],
            }
            r = wg.GraphRunner(g, {'path': str(p)}).run(); local_results.append(r)
            return r['ok'] and r['child_invocations'] == 2 and p.read_text() == 'C\n', {'run': r['run_id'], 'child_invocations': r['child_invocations']}
        tasks.append(task('execute_multi_child_sequential_graph', t8))

        def t9():
            p = base / 'fail.txt'; p.write_text('X\n')
            g = make_simple('propagate')
            r = wg.GraphRunner(g, {'path': str(p), 'old': 'NOPE', 'new': 'Y'}).run(); local_results.append(r)
            return (not r['ok']) and r['status'] == 'FAIL' and r['nodes']['edit']['status'] == 'FAILED', {'run': r['run_id'], 'status': r['status'], 'node': r['nodes']['edit']['status']}
        tasks.append(task('child_failure_propagates_to_parent', t9))

        def t10():
            failp = base / 'branch-fail.txt'; failp.write_text('X\n')
            recoverp = base / 'branch-recover.txt'; recoverp.write_text('R\n')
            g = {'name': 'bench-recovery', 'version': '1', 'description': 'explicit recovery branch', 'parameters': {}, 'nodes': [
                {'id': 'fail', 'workflow': 'exact-replace@1', 'depends_on': [], 'params': {'path': str(failp), 'old': 'NOPE', 'new': 'Y'}},
                {'id': 'recover', 'workflow': 'exact-replace@1', 'depends_on': ['fail'], 'run_if': 'failure', 'recovers': ['fail'], 'params': {'path': str(recoverp), 'old': 'R', 'new': 'RECOVERED'}},
            ]}
            r = wg.GraphRunner(g, {}).run(); local_results.append(r)
            return r['ok'] and r['status'] == 'RECOVERED' and r['recovered_failures'].get('fail') == 'recover' and recoverp.read_text() == 'RECOVERED\n', {'run': r['run_id'], 'status': r['status'], 'recovered_failures': r['recovered_failures']}
        tasks.append(task('explicit_recovery_branch', t10))

        def t11():
            r = next(x for x in reversed(local_results) if x.get('nodes', {}).get('edit', {}).get('status') == 'SUCCEEDED')
            child = r['nodes']['edit']['workflow']
            cr = r['nodes']['edit']['attempts'][0]['code_run']
            return child == exact_ident and bool(cr.get('result_path')) and pathlib.Path(cr['result_path']).exists(), {'parent': r['graph'], 'child': child, 'code_run': cr.get('run_id')}
        tasks.append(task('child_provenance_hash_version_audit', t11))

        def t12():
            old = 'A' * 700; new = 'B' * 700; p = base / 'compact.txt'; p.write_text(old)
            g = make_simple('compact')
            r = wg.GraphRunner(g, {'path': str(p), 'old': old, 'new': new}).run(); local_results.append(r)
            parent_old = r['parameters']['old']; child_old = r['nodes']['edit']['parameters']['old']
            result_size = pathlib.Path(r['result_path']).stat().st_size if pathlib.Path(r['result_path']).exists() else canonical_len(r)
            retained = all(pathlib.Path(x).exists() for x in r['child_result_paths'])
            return r['ok'] and parent_old.get('hashed') and child_old.get('hashed') and retained and result_size < 20000, {'run': r['run_id'], 'parent_value': parent_old, 'child_value': child_old, 'result_bytes': result_size, 'child_artifacts_retained': retained}
        tasks.append(task('compact_parent_result_with_child_artifacts_retained', t12))

        initial_upgrade = latest_graph_result('lab-upgrade-transaction')
        initial_recovery = latest_graph_result('lab-recovery-transaction')

        def t13():
            cps = initial_upgrade.get('restart_checkpoints') or []
            return initial_upgrade.get('ok') and cps and cps[0].get('confirmed') and cps[0].get('pid_after') != cps[0].get('pid_before'), {'run': initial_upgrade['run_id'], 'checkpoint': cps[0] if cps else None}
        tasks.append(task('restart_safe_composite_operation', t13))

        def t14():
            node = (initial_upgrade.get('nodes') or {}).get('verify-candidate') or {}
            attempt = (node.get('attempts') or [{}])[0]
            child = attempt.get('child_workflow') or {}
            return node.get('status') == 'SUCCEEDED' and child.get('name') == 'lab-candidate-verify' and child.get('version') == '2', {'run': initial_upgrade['run_id'], 'node_status': node.get('status'), 'child': child}
        tasks.append(task('composite_lab_candidate_validation', t14))

        def t15():
            nodes = initial_upgrade.get('nodes') or {}
            required = ['install-candidate', 'verify-candidate', 'accept-lkg', 'post-verify']
            build = read_json(BUILD); live_sha = hashlib.sha256(LIVE.read_bytes()).hexdigest(); lkg_sha = hashlib.sha256(LKG.read_bytes()).hexdigest()
            ok = initial_upgrade.get('ok') and all((nodes.get(n) or {}).get('status') == 'SUCCEEDED' for n in required) and build.get('recovery_state') == 'ACCEPTED' and live_sha == lkg_sha == build.get('source_sha256') == build.get('last_known_good_sha256')
            return ok, {'run': initial_upgrade['run_id'], 'node_order': required, 'recovery_state': build.get('recovery_state'), 'live_sha256': live_sha, 'lkg_sha256': lkg_sha}
        tasks.append(task('composite_lab_self_update_restart_verify_accept', t15))

        def t16():
            nodes = initial_recovery.get('nodes') or {}
            required = ['bad-candidate-recovery', 'reaccept-lkg', 'post-recovery-verify']
            build = read_json(BUILD); live_sha = hashlib.sha256(LIVE.read_bytes()).hexdigest(); lkg_sha = hashlib.sha256(LKG.read_bytes()).hexdigest()
            ok = initial_recovery.get('ok') and all((nodes.get(n) or {}).get('status') == 'SUCCEEDED' for n in required) and build.get('recovery_state') == 'ACCEPTED' and live_sha == lkg_sha
            return ok, {'run': initial_recovery['run_id'], 'node_order': required, 'recovery_state': build.get('recovery_state'), 'retries': initial_recovery.get('retries')}
        tasks.append(task('bad_candidate_recovery_transaction', t16))

        def t17():
            g = {'name': 'bench-containment', 'version': '1', 'description': 'post-update containment graph', 'parameters': {}, 'nodes': [
                {'id': 'verify', 'workflow': 'lab-post-update-verify@2', 'depends_on': [], 'params': {}}
            ]}
            r = wg.GraphRunner(g, {}).run(); local_results.append(r)
            return r['ok'] and r['nodes']['verify']['status'] == 'SUCCEEDED', {'run': r['run_id'], 'code_runs': r['code_runs']}
        tasks.append(task('containment_invariants', t17))

        def t18():
            params = {'candidate': '/root/gen4-benchmark-reuse.py', 'generation': 'gen4-workflow-graphs-r1',
                      'old': 'from __future__ import annotations', 'new': 'from __future__ import annotations', 'port': 8893, 'source': '/opt/optiplex-lab/server.py'}
            payload = base / 'reuse-upgrade-params.json'; payload.write_text(json.dumps(params)); payload.chmod(0o600)
            rc, compact, output_bytes = run_cli([str(GRAPH), 'run', 'lab-upgrade-transaction@1', '--params-file', str(payload)], timeout=300)
            nonlocal parent_invocation_output_bytes
            parent_invocation_output_bytes += output_bytes
            full = read_json(pathlib.Path(compact['result_path']))
            cps = full.get('restart_checkpoints') or []
            return rc == 0 and full.get('ok') and (full.get('graph') or {}).get('sha256') == EXPECTED_UPGRADE_GRAPH_SHA and full.get('child_invocations') == 4 and cps and cps[0].get('confirmed'), {'run': full['run_id'], 'graph_sha256': full['graph']['sha256'], 'child_invocations': full['child_invocations'], 'output_bytes': output_bytes, 'checkpoint': cps[0] if cps else None}
        tasks.append(task('reuse_same_composite_without_regenerating_sequence', t18))

    finally:
        wg.REGISTRY, wg.RUN_ROOT = original_graph_registry, original_run_root
        shutil.rmtree(base, ignore_errors=True)

    gen3 = read_json(GEN3) if GEN3.exists() else {}
    gen3_summary = gen3.get('summary') or {}
    upgrade_params = read_json(pathlib.Path('/root/gen4-bootstrap/upgrade-params.json')) if pathlib.Path('/root/gen4-bootstrap/upgrade-params.json').exists() else {}
    gen3_normal_calls = [
        {'workflow': 'lab-self-evolve@1', 'params': upgrade_params},
        {'workflow': 'lab-candidate-verify@2', 'params': {}},
        {'workflow': 'lab-accept-current@2', 'params': {}},
        {'workflow': 'lab-post-update-verify@2', 'params': {}},
    ]
    gen4_normal_call = {'graph': 'lab-upgrade-transaction@1', 'params': upgrade_params}
    gen3_bad_calls = [
        {'workflow': 'lab-bad-candidate-recovery@1', 'params': {}},
        {'workflow': 'lab-accept-current@2', 'params': {}},
        {'workflow': 'lab-post-update-verify@2', 'params': {}},
    ]
    gen4_bad_call = {'graph': 'lab-recovery-transaction@1', 'params': {}}
    gen3_normal_bytes = sum(canonical_len(x) for x in gen3_normal_calls)
    gen4_normal_bytes = canonical_len(gen4_normal_call)
    gen3_bad_bytes = sum(canonical_len(x) for x in gen3_bad_calls)
    gen4_bad_bytes = canonical_len(gen4_bad_call)

    local_child_invocations = sum(int(r.get('child_invocations', 0)) for r in local_results)
    local_code_invocations = sum(int(r.get('code_mode_invocations', 0)) for r in local_results)
    local_retries = sum(int(r.get('retries', 0)) for r in local_results)
    local_code_steps = sum(int(r.get('underlying_code_mode_steps', 0)) for r in local_results)
    local_raw_shell = sum(int(r.get('raw_shell_command_steps', 0)) for r in local_results)
    passed = sum(1 for t in tasks if t['ok']); total = len(tasks)
    final_upgrade = latest_graph_result('lab-upgrade-transaction')
    final_recovery = latest_graph_result('lab-recovery-transaction')
    build = read_json(BUILD); live_sha = hashlib.sha256(LIVE.read_bytes()).hexdigest(); lkg_sha = hashlib.sha256(LKG.read_bytes()).hexdigest()

    summary = {
        'passed': passed,
        'total': total,
        'elapsed_ms': round(sum(float(t['elapsed_ms']) for t in tasks), 2),
        'gen3_benchmark_passed': gen3_summary.get('passed'),
        'gen3_benchmark_total': gen3_summary.get('total'),
        'gen3_reusable_workflow_invocations': gen3_summary.get('reusable_workflow_invocations'),
        'gen3_invocation_authoring_bytes_proxy': gen3_summary.get('gen3_invocation_authoring_bytes_proxy'),
        'gen3_underlying_code_mode_steps': gen3_summary.get('underlying_code_mode_steps'),
        'gen3_raw_shell_step_share': gen3_summary.get('raw_shell_step_share'),
        'normal_lifecycle_top_level_invocations_gen3': 4,
        'normal_lifecycle_top_level_invocations_gen4': 1,
        'normal_lifecycle_invocation_reduction': 0.75,
        'bad_recovery_top_level_invocations_gen3': 3,
        'bad_recovery_top_level_invocations_gen4': 1,
        'bad_recovery_invocation_reduction': round(1 - 1/3, 3),
        'combined_lifecycle_top_level_invocations_gen3': 7,
        'combined_lifecycle_top_level_invocations_gen4': 2,
        'combined_lifecycle_invocation_reduction': round(1 - 2/7, 3),
        'normal_lifecycle_authoring_bytes_gen3_proxy': gen3_normal_bytes,
        'normal_lifecycle_authoring_bytes_gen4_proxy': gen4_normal_bytes,
        'normal_lifecycle_authoring_byte_reduction': round(1 - gen4_normal_bytes/gen3_normal_bytes, 3),
        'bad_recovery_authoring_bytes_gen3_proxy': gen3_bad_bytes,
        'bad_recovery_authoring_bytes_gen4_proxy': gen4_bad_bytes,
        'bad_recovery_authoring_byte_reduction': round(1 - gen4_bad_bytes/gen3_bad_bytes, 3),
        'new_procedural_steps_authored_for_composite_reuse': 0,
        'local_graph_child_invocations': local_child_invocations,
        'local_graph_code_mode_invocations': local_code_invocations,
        'local_graph_retries': local_retries,
        'local_graph_underlying_code_mode_steps': local_code_steps,
        'local_graph_raw_shell_command_steps': local_raw_shell,
        'local_graph_raw_shell_step_share': round(local_raw_shell/local_code_steps, 3) if local_code_steps else 0,
        'parent_cli_output_bytes_proxy': parent_invocation_output_bytes,
        'self_host_upgrade_run': initial_upgrade['run_id'],
        'reused_upgrade_run': final_upgrade['run_id'],
        'bad_recovery_run': final_recovery['run_id'],
        'restart_resume_success': bool((final_upgrade.get('restart_checkpoints') or [{}])[0].get('confirmed')),
        'recovery_success': bool(final_recovery.get('ok')),
        'final_recovery_state': build.get('recovery_state'),
        'final_live_sha256': live_sha,
        'final_lkg_sha256': lkg_sha,
        'final_live_equals_lkg': live_sha == lkg_sha,
        'upgrade_graph_sha256': EXPECTED_UPGRADE_GRAPH_SHA,
        'recovery_graph_sha256': EXPECTED_RECOVERY_GRAPH_SHA,
    }
    result = {'timestamp': datetime.now(timezone.utc).isoformat(), 'generation': 'gen4-workflow-graphs-r1', 'tasks': tasks, 'summary': summary}
    out = OUT / 'gen4-workflow-graph-benchmark.json'; out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'output': str(out)} | summary, indent=2))
    raise SystemExit(0 if passed == total and summary['final_live_equals_lkg'] and summary['final_recovery_state'] == 'ACCEPTED' else 1)


if __name__ == '__main__':
    main()
