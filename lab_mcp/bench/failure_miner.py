#!/usr/bin/env python3
from __future__ import annotations

import collections
import json
import pathlib
from datetime import datetime, timezone

TRACE = pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl')
BENCH = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen5-capability-forge-benchmark.json')
SEMANTIC = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen5-semantic-edit-experiment.json')
REGISTRY = pathlib.Path('/var/lib/optiplex-lab/capabilities/registry.json')
PROVENANCE = pathlib.Path('/var/lib/optiplex-lab/capabilities/provenance.jsonl')
OUT = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen6-proposals.json')


def load_json(path: pathlib.Path):
    return json.loads(path.read_text()) if path.exists() else {}


def load_jsonl(path: pathlib.Path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(errors='replace').splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def main() -> None:
    bench=load_json(BENCH); metrics=bench.get('metrics',{}); semantic=load_json(SEMANTIC)
    registry=(load_json(REGISTRY).get('capabilities') or {})
    events=load_jsonl(TRACE); provenance=load_jsonl(PROVENANCE)
    forge_events=[e for e in events if e.get('tool')=='capability_forge']
    forge_counts=collections.Counter(e.get('event') for e in forge_events)
    prov_counts=collections.Counter(e.get('event') for e in provenance)
    states=collections.Counter(r.get('state') for r in registry.values())
    promoted=[(h,r) for h,r in registry.items() if r.get('state')=='PROMOTED']
    candidates=[(h,r) for h,r in registry.items() if r.get('state')=='CANDIDATE']
    rejected=[(h,r) for h,r in registry.items() if r.get('state')=='REJECTED']
    real_failures=sum(1 for e in provenance if e.get('event')=='real_task_evidence' and not e.get('ok'))
    proposals=[]
    def add(title,kind,evidence,benefit,complexity):
        proposals.append({'rank':len(proposals)+1,'title':title,'kind':kind,'evidence':evidence,'expected_benefit':benefit,'complexity':complexity})

    add(
        'Procedural Memory Distiller',
        'memory/retrieval',
        f"Gen5 can now forge and govern abilities, but the benchmark still required {metrics.get('chatgpt_authored_helper_source_bytes')} ChatGPT-authored helper/contract bytes to create them. Only {len(promoted)} capabilities reached PROMOTED while {len(candidates)} useful passing capabilities remain CANDIDATE, and current gap retrieval is deliberately shallow name/tag/purpose overlap. Reuse itself averaged {metrics.get('subsequent_reuse_latency_ms')} ms, so the expensive part has moved from execution to recognizing and retrieving prior experience.",
        'Distill successful capability/workflow/graph episodes into compact applicability memories with evidence links, then retrieve only the relevant procedures/capabilities for a new gap. Preserve immutable source-of-truth artifacts; memory is an index and hypothesis, not authority.',
        'medium',
    )
    add(
        'Failure-to-Regression Compiler',
        'memory/verification',
        f"Gen5 intentionally rejected {metrics.get('broken_candidates_rejected')} broken descendants, recorded {real_failures} real-task failures in Forge provenance, and exercised a failed semantic self-edit plus bad-candidate LKG recovery. Those failures produced rich hashes/results, but their durable regression cases were still hand-authored in benchmark code.",
        'Convert a failed capability run, evaluator miss, self-edit failure, or recovery incident into a minimized immutable regression fixture tied to the responsible capability/evaluator/version. Future descendants must replay relevant regressions before promotion.',
        'medium',
    )
    add(
        'Evaluator / Mutation Distiller',
        'verification/synthesis',
        f"The Gen5 nursery achieved {bench.get('passed')}/{bench.get('total')} task checks and proved independent adversarial evidence can reject candidates that pass ordinary cases. But positive/negative/adversarial fixtures were authored externally for each new capability; evaluator generation remains a major reasoning step after capability source generation.",
        'Infer candidate invariants from contract examples and observed failures, generate bounded mutations/negative cases, and prove evaluator discrimination before a capability can be promoted. Keep evaluator identity/hash separate from implementation identity.',
        'medium',
    )
    add(
        'Capability Consolidator + Supersession Memory',
        'retention/maintenance',
        f"Gen5 avoided {metrics.get('duplicate_capabilities_avoided')} exact duplicate and supports explicit SUPERSEDED state, but semantic overlap beyond exact content is still a simple heuristic. Registry states are {dict(states)} and every passing helper can otherwise accumulate as a distinct candidate/environment.",
        'Cluster near-equivalent capabilities using contract/applicability/evidence fingerprints, propose merges or supersession, replay both evaluators/regressions, and retain lineage so the registry grows in quality rather than only size.',
        'low-medium',
    )
    add(
        'Experience-Based Recovery Policy Distiller',
        'recovery/memory',
        f"Gen5 preserved Gen4 restart/LKG recovery and the deliberate bad-candidate transaction passed, but recovery actions remain hand-declared graphs. Forge provenance now records candidate failures, dependency failures, timeouts, excessive output, and real-task failures that can identify which bounded recovery action worked in which context.",
        'Learn applicability rules over an explicitly allowed recovery action set (inspect, retry, expire, rollback, re-evaluate) from prior incidents, while keeping budgets and fail-closed graph semantics unchanged.',
        'medium',
    )

    out={
        'generated_at':datetime.now(timezone.utc).isoformat(),
        'generation':'gen6-proposals-from-gen5-evidence',
        'implemented':False,
        'question':'What still requires excessive ChatGPT reasoning/tool orchestration after the Lab can forge and govern new capabilities?',
        'gen5_benchmark':{
            'artifact':str(BENCH),
            'passed':bench.get('passed'),'total':bench.get('total'),
            'artifact_sha256':bench.get('artifact_sha256'),
            'metrics':metrics,
        },
        'semantic_edit_evidence':{
            'artifact':str(SEMANTIC),
            'exact_successes':semantic.get('exact_successes'),
            'semantic_successes':semantic.get('semantic_successes'),
            'variants_total':semantic.get('variants_total'),
            'authoring_proxy':semantic.get('actual_server_authoring_proxy'),
        },
        'registry_summary':{'states':dict(states),'total':len(registry),'promoted':len(promoted),'candidates':len(candidates),'rejected':len(rejected)},
        'trace_summary':{'forge_events':len(forge_events),'forge_event_counts':dict(forge_counts),'provenance_events':len(provenance),'provenance_event_counts':dict(prov_counts),'real_task_failures':real_failures},
        'top_recommendation':proposals[0]['title'],
        'proposals':proposals,
    }
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__': main()
