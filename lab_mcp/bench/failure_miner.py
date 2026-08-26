#!/usr/bin/env python3
from __future__ import annotations

import collections
import json
import pathlib
from datetime import datetime, timezone

TRACE = pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl')
BENCH = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen4-workflow-graph-benchmark.json')
OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen5-proposals.json')


def load_json(path: pathlib.Path):
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> None:
    bench = load_json(BENCH)
    summary = bench.get('summary', {})
    tasks = bench.get('tasks', [])
    events = []
    if TRACE.exists():
        for line in TRACE.read_text(errors='replace').splitlines():
            try:
                events.append(json.loads(line))
            except Exception:
                pass

    graph_events = [e for e in events if e.get('tool') == 'workflow_graphs']
    graph_ends = [e for e in graph_events if e.get('event') == 'graph_run_end']
    node_ends = [e for e in graph_events if e.get('event') == 'node_end']
    workflow_ends = [e for e in events if e.get('tool') == 'workflow_skills' and e.get('event') == 'invoke_end']
    code_steps = [e for e in events if e.get('tool') == 'code_mode' and e.get('event') == 'step_end']
    ops = collections.Counter(e.get('op') for e in code_steps)
    failures = collections.Counter(e.get('op') for e in code_steps if not e.get('ok'))
    slow = sorted(tasks, key=lambda x: float(x.get('elapsed_ms', 0) or 0), reverse=True)
    slow_text = ', '.join(str(x.get('name')) + '=' + str(x.get('elapsed_ms')) + 'ms' for x in slow[:3])

    proposals = []
    def add(title: str, kind: str, evidence: str, benefit: str, complexity: str) -> None:
        proposals.append({
            'rank': len(proposals) + 1,
            'title': title,
            'kind': kind,
            'evidence': evidence,
            'expected_benefit': benefit,
            'complexity': complexity,
        })

    add(
        'Structured transactional / AST editing',
        'editing/context',
        f"Gen4 reduced normal lifecycle top-level sequencing from {summary.get('normal_lifecycle_top_level_invocations_gen3')} to {summary.get('normal_lifecycle_top_level_invocations_gen4')} calls ({summary.get('normal_lifecycle_invocation_reduction')} reduction), but the real edit-heavy authoring proxy only fell from {summary.get('normal_lifecycle_authoring_bytes_gen3_proxy')}B to {summary.get('normal_lifecycle_authoring_bytes_gen4_proxy')}B ({summary.get('normal_lifecycle_authoring_byte_reduction')} reduction). The remaining 4.4KB payload was dominated by exact old/new source text rather than orchestration.",
        'Replace large exact-string edit payloads with audited symbol/AST/structured transformations, deterministic preconditions, previews, rollback, and provenance. This attacks the largest residual ChatGPT-authored context after graph composition solved sequencing.',
        'medium',
    )
    add(
        'Automatic composite/skill synthesis from successful traces',
        'synthesis/reuse',
        f"Gen4 proved that a registered graph can be reused with zero newly authored procedural steps and cut combined lifecycle calls from {summary.get('combined_lifecycle_top_level_invocations_gen3')} to {summary.get('combined_lifecycle_top_level_invocations_gen4')}, but the two accepted lifecycle graphs were still designed and registered manually. {len(graph_ends)} graph completions and {len(node_ends)} node completions are now available as synthesis evidence.",
        'Mine repeated successful workflow sequences, propose a bounded immutable composite definition, statically validate it, and require explicit acceptance before activation. This removes the next layer of ChatGPT reasoning: recognizing and encoding reusable sequences.',
        'medium',
    )
    add(
        'Adaptive bounded recovery policies',
        'recovery',
        f"The bad-candidate recovery transaction succeeded but recorded {summary.get('recovery_success')} recovery with bounded underlying retries; benchmark-local graph retries were {summary.get('local_graph_retries')}. Code Mode step failures observed in the trace are {dict(failures)}. Gen4 recovery branches remain static and hand-authored.",
        'Let transactions select among a small declared set of inspect/retry/rollback actions using explicit budgets and state predicates, while never converting an unrecovered failed child into success.',
        'low-medium',
    )
    add(
        'Static analysis + property fuzzing for workflows and graphs',
        'verification',
        f"Gen4 now has typed mappings, immutable child hashes, cycle checks, invocation bounds, restart checkpoints, and an 18/18 benchmark. The benchmark exercises failures, but the combinatorial graph/schema surface is larger than Gen3 and currently relies on example-based tests. Observed Code Mode op mix is {dict(ops)}.",
        'Generate bounded malformed definitions, dependency graphs, parameter mappings, restart-state fixtures, and interruption states to prove fail-closed behavior and catch edge cases before a self-update transaction.',
        'medium',
    )
    add(
        'Parallel execution of independent DAG nodes',
        'performance/orchestration',
        f"The accepted Gen4 runner models dependencies as a DAG but executes topological nodes sequentially. The slowest benchmark cases were {slow_text}; wall-clock was not the Gen4 objective, so concurrency was intentionally deferred.",
        'Run only dependency-independent, resource-compatible children concurrently with explicit fan-out limits and deterministic join/failure semantics, preserving child provenance and containment.',
        'medium',
    )

    out = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'generation': 'gen5-proposals-from-gen4-evidence',
        'implemented': False,
        'question': 'What still requires excessive ChatGPT reasoning/tool orchestration after reusable workflows can compose?',
        'benchmark_summary': summary,
        'trace_summary': {
            'workflow_graph_completions_seen': len(graph_ends),
            'workflow_graph_node_completions_seen': len(node_ends),
            'reusable_workflow_completions_seen': len(workflow_ends),
            'code_mode_steps_seen': len(code_steps),
            'ops': dict(ops),
            'step_failures': dict(failures),
        },
        'top_recommendation': proposals[0]['title'],
        'proposals': proposals,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
