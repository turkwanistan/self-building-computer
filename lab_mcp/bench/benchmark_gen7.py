#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import pathlib
import statistics
import time
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path('/opt/optiplex-lab')
TWIN_PATH = ROOT / 'architecture_twin.py'
CAUSAL_PATH = ROOT / 'causal_spine.py'
ART = pathlib.Path('/var/lib/optiplex-lab/benchmarks/gen7-architectural-twin-benchmark.json')
TRACE = pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl')
TIMEOUT_BAD = '7a615a3f98a7a3be8babdf6376f38be2025543618af8dfff638ce2f028c8c708'
TIMEOUT_REG = '5be7002dfbe9b489445fcc2009b0c9d79af6baaee1cc308b6dd8e9cf64e75436'
BAD_SERVER = '8f320ff7a3176837da2d308320bd8952c9ac7809375491c85faf403d44105b3e'
LKG_SERVER = 'dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9'
STARTED = datetime.now(timezone.utc).isoformat()


def load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def canon(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(',', ':')).encode()


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


twin = load('gen7_twin_bench', TWIN_PATH)
causal = load('gen7_causal_bench', CAUSAL_PATH)
checks: list[dict[str, Any]] = []
metrics: dict[str, Any] = {}


def ck(name: str, ok: Any, detail: Any = None) -> None:
    checks.append({'name': name, 'ok': bool(ok), 'detail': detail})


# Rebuild from authoritative guest state. This also makes benchmark_gen7 part of the Twin.
build1 = twin.build_all()
snap = twin.load_snapshot()
nodes = {n['id']: n for n in snap['nodes']}
edges = {(e['src'], e['dst'], e['relation']): e for e in snap['edges']}

# 1. Architecture reconstruction: important layers and exactly the permanent 10-tool surface.
required_kinds = {'source','mcp_tool','workflow','workflow_graph','capability','evaluator','procedural_memory','regression','registry','benchmark_artifact','build_state','recovery','authority_boundary'}
kinds = {n['kind'] for n in snap['nodes']}
tools = [n for n in snap['nodes'] if n['kind'] == 'mcp_tool']
ck('architecture_reconstruction', required_kinds <= kinds and len(tools) == 10,
   {'required_kinds_present': sorted(required_kinds & kinds), 'tool_count': len(tools)})

# 2. Curated dependency truth set. Precision and recall are measured over explicit cases.
def sid(name: str) -> str: return f'source:{ROOT/name}'
positive = [
    (sid('experience_loop.py'), sid('experience_memory.py'), 'depends_on'),
    (sid('experience_loop.py'), sid('regression_compiler.py'), 'depends_on'),
    (sid('experience_loop.py'), sid('capability_forge.py'), 'depends_on'),
    (sid('capability_forge.py'), sid('regression_compiler.py'), 'depends_on'),
    (sid('workflow_graphs.py'), sid('workflow_skills.py'), 'depends_on'),
    (sid('workflow_skills.py'), sid('code_mode.py'), 'depends_on'),
    (sid('bench/benchmark_gen6.py'), sid('experience_loop.py'), 'depends_on'),
    (sid('bench/benchmark_gen6.py'), sid('experience_memory.py'), 'depends_on'),
    (sid('bench/benchmark_gen6.py'), sid('regression_compiler.py'), 'depends_on'),
    (sid('bench/benchmark_gen6.py'), sid('capability_forge.py'), 'depends_on'),
    ('workflow_graph:capability-use-transaction@1', 'workflow:capability-invoke@1', 'invokes'),
    ('workflow:capability-invoke@1', sid('capability_forge.py'), 'invokes'),
]
negative = [
    ('workflow:public-repo-investigation@1', sid('capability_forge.py'), 'invokes'),
    ('workflow_graph:lab-recovery-transaction@1', 'workflow:capability-invoke@1', 'invokes'),
    (sid('experience_loop.py'), sid('code_mode.py'), 'depends_on'),
    (sid('causal_spine.py'), sid('capability_forge.py'), 'depends_on'),
    (sid('workflow_skills.py'), sid('capability_forge.py'), 'depends_on'),
    ('workflow:public-repo-investigation@1', sid('experience_memory.py'), 'invokes'),
]
tp = sum(x in edges for x in positive); fn = len(positive) - tp
fp = sum(x in edges for x in negative); tn = len(negative) - fp
precision = tp / (tp + fp) if tp + fp else 1.0
recall = tp / (tp + fn) if tp + fn else 1.0
metrics['dependency'] = {'tp':tp,'fp':fp,'fn':fn,'tn':tn,'precision':round(precision,4),'recall':round(recall,4),'positive_cases':len(positive),'negative_cases':len(negative)}
ck('dependency_precision_recall', precision >= 0.95 and recall >= 0.95, metrics['dependency'])

# 3. Real source query must identify itself as authoritative and expose fresh evidence.
q_loop = twin.query(snap, str(ROOT/'experience_loop.py'))
ck('real_source_query', bool(q_loop['matches']) and sid('experience_loop.py') in q_loop['authoritative_owners'] and q_loop['matches'][0]['freshness']['state'] == 'fresh',
   {'owners':q_loop['authoritative_owners'],'freshness':q_loop['matches'][0]['freshness'] if q_loop['matches'] else None})

# 4. Change impact on a real Gen6 source must choose exactly the required validation nodes.
imp_loop = twin.impact(snap, str(ROOT/'experience_loop.py'), 4)
expected_validations = {'validation:selftest:experience_loop','validation:benchmark:benchmark_gen6','validation:benchmark:benchmark_gen7'}
predicted_validations = {x for x in imp_loop['validations'] if x.startswith('validation:')}
impact_tp = len(expected_validations & predicted_validations); impact_fp = len(predicted_validations - expected_validations); impact_fn = len(expected_validations - predicted_validations)
impact_precision = impact_tp/(impact_tp+impact_fp) if impact_tp+impact_fp else 1.0
impact_recall = impact_tp/(impact_tp+impact_fn) if impact_tp+impact_fn else 1.0
metrics['change_impact'] = {'expected':sorted(expected_validations),'predicted':sorted(predicted_validations),'tp':impact_tp,'fp':impact_fp,'fn':impact_fn,'precision':round(impact_precision,4),'recall':round(impact_recall,4)}
ck('change_impact_precision', impact_precision == 1.0 and impact_recall == 1.0, metrics['change_impact'])

# 5. Negative control: unrelated workflow must not be strongly connected to Gen6 engineering stack.
imp_unrelated = twin.impact(snap, 'workflow:public-repo-investigation@1', 4)
unrelated_nodes = {x['node'] for x in [*imp_unrelated['direct'], *imp_unrelated['transitive']]}
forbidden_unrelated = {sid('experience_loop.py'), sid('experience_memory.py'), sid('capability_forge.py'), 'validation:benchmark:benchmark_gen6'}
ck('unrelated_negative_control', not (unrelated_nodes & forbidden_unrelated), {'unexpected':sorted(unrelated_nodes & forbidden_unrelated),'impact_count':len(unrelated_nodes)})

# 6. Historical Gen6 failure -> regression must be explicitly causal.
cr = twin.causal_reconstruct(TIMEOUT_REG, depth=3)
cr_events = cr.get('events',[]); cr_edges = cr.get('edges',[])
ck('causal_failure_to_regression', any(e['data'].get('content_hash') == TIMEOUT_BAD and e['data'].get('ok') is False for e in cr_events) and any(e['data'].get('regression_hash') == TIMEOUT_REG for e in cr_events) and any(e['relation'] == 'generated_regression' and e['strength'] == 'causal' for e in cr_edges),
   {'events':len(cr_events),'edges':len(cr_edges)})

# 7. Historical lifecycle recovery must reconstruct bad child -> rollback -> restored LKG.
rr = twin.causal_reconstruct(BAD_SERVER, depth=3)
relations = {e['relation'] for e in rr.get('edges',[])}
restores = [e for e in rr.get('events',[]) if e['data'].get('restored_sha256') == LKG_SERVER]
ck('causal_recovery_lineage', {'triggered_auto_rollback','restored_child_started'} <= relations and bool(restores), {'relations':sorted(relations),'events':rr.get('event_count')})

# 8. Real append-only evidence growth must be surfaced against the old snapshot, not called corruption.
marker = {'timestamp':datetime.now(timezone.utc).isoformat(),'tool':'gen7_benchmark','event':'twin_freshness_marker'}
with TRACE.open('a', encoding='utf-8') as f: f.write(json.dumps(marker, sort_keys=True)+'\n')
verify_old = twin.verify(snap)
ck('append_only_new_evidence_detected', verify_old.get('newer_evidence_available',0) >= 1 and not verify_old.get('issues'), verify_old)

# 9. Missing/stale source evidence must be explicit and fail closed without mutating a real source.
synthetic = dict(next(n for n in snap['nodes'] if n['id'] == sid('experience_loop.py')))
synthetic['source_path'] = '/tmp/gen7-definitely-missing-evidence.py'
missing = twin.node_freshness(synthetic)
ck('missing_evidence_explicit', missing['state'] == 'missing', missing)

# 10. Rebuild determinism: structural digests exclude timestamps and must reproduce exactly.
a = twin.TwinBuilder(twin.DEFAULT_SOURCE_ROOT,twin.DEFAULT_STATE_ROOT,twin.DEFAULT_BUILD_FILE,twin.DEFAULT_RECOVERY_ROOT).build()
b = twin.TwinBuilder(twin.DEFAULT_SOURCE_ROOT,twin.DEFAULT_STATE_ROOT,twin.DEFAULT_BUILD_FILE,twin.DEFAULT_RECOVERY_ROOT).build()
ca = causal.build_index(); cb = causal.build_index()
ck('rebuild_determinism', a['graph_digest'] == b['graph_digest'] and ca['digest'] == cb['digest'], {'twin':a['graph_digest'],'causal':ca['digest']})

# Rebuild after the marker so final benchmark/Twin state is fresh.
build2 = twin.build_all(); snap2 = twin.load_snapshot()

# 11. Gen7 must use its own Twin: benchmark_gen7 depends on Twin/Causal, and Twin impact selects this benchmark validation.
imp_self = twin.impact(snap2, str(TWIN_PATH), 4)
imp_causal = twin.impact(snap2, str(CAUSAL_PATH), 4)
self_valid = {x for x in imp_self['validations'] if x.startswith('validation:')}
causal_valid = {x for x in imp_causal['validations'] if x.startswith('validation:')}
ck('self_hosted_twin_validation', 'validation:benchmark:benchmark_gen7' in self_valid and 'validation:selftest:architecture_twin' in self_valid and 'validation:benchmark:benchmark_gen7' in causal_valid and 'validation:selftest:causal_spine' in causal_valid,
   {'twin_validations':sorted(self_valid),'causal_validations':sorted(causal_valid)})

# 12. Query/impact latency is measured over real architecture questions.
lat=[]
for _ in range(25):
    t0=time.perf_counter(); twin.query(snap2,str(ROOT/'capability_forge.py')); twin.impact(snap2,str(ROOT/'experience_loop.py'),4); lat.append((time.perf_counter()-t0)*1000)
metrics['query_latency_ms']={'median':round(statistics.median(lat),3),'max':round(max(lat),3),'samples':len(lat)}
ck('query_latency_bounded', metrics['query_latency_ms']['median'] < 25 and metrics['query_latency_ms']['max'] < 100, metrics['query_latency_ms'])

# 13. Context proxy: bounded query+impact packet versus reading every hashed authoritative input.
unique_inputs={x['path']:x for x in snap2['inputs']}; broad_bytes=sum(int(x.get('bytes') or 0) for x in unique_inputs.values())
packet={'query':twin.query(snap2,str(ROOT/'experience_loop.py')),'impact':twin.impact(snap2,str(ROOT/'experience_loop.py'),4)}
packet_bytes=len(canon(packet)); reduction=1-(packet_bytes/broad_bytes) if broad_bytes else 0
metrics['context_proxy']={'broad_authoritative_input_bytes':broad_bytes,'bounded_packet_bytes':packet_bytes,'reduction':round(reduction,4)}
ck('context_reduction', reduction >= 0.75, metrics['context_proxy'])

# 14. Targeted validation proxy: Twin can select a small validation set, but final acceptance still runs the full retained suite.
all_validation_ids={n['id'] for n in snap2['nodes'] if n['kind']=='validation'}
selected={x for x in twin.impact(snap2,str(ROOT/'experience_loop.py'),4)['validations'] if x.startswith('validation:')}
metrics['validation_selection']={'all_validation_nodes':len(all_validation_ids),'selected_for_experience_loop':len(selected),'avoided_proxy':len(all_validation_ids-selected),'selected':sorted(selected)}
ck('bounded_validation_selection', expected_validations <= selected and len(selected) < len(all_validation_ids), metrics['validation_selection'])

# 15. Permanent MCP surface and containment invariant remain intact.
server_tree=ast.parse((ROOT/'server.py').read_text())
def is_tool(d: ast.AST) -> bool:
    target=d.func if isinstance(d,ast.Call) else d
    return isinstance(target,ast.Attribute) and target.attr=='tool'
tool_defs=[n.name for n in server_tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(is_tool(d) for d in n.decorator_list)]
boundary_edges=[e for e in snap2['edges'] if e['src']=='authority_boundary:guest-vm' and e['relation']=='prohibited_from_accessing']
ck('tool_surface_and_containment_model', len(tool_defs)==10 and len(boundary_edges)>=6, {'tools':tool_defs,'prohibited_edges':len(boundary_edges)})

metrics['twin']={'nodes':build2['nodes'],'edges':build2['edges'],'inputs':build2['inputs'],'graph_digest':build2['graph_digest'],'snapshot_bytes':build2['snapshot_bytes'],'sqlite_bytes':build2['sqlite_bytes'],'build_ms':build2['duration_ms']}
metrics['causal']={'events':build2['causal_events'],'edges':build2['causal_edges'],'digest':build2['causal_digest']}
metrics['permanent_mcp_tools']=len(tool_defs)
result={'generation':'gen7-self-model-r1','benchmark':'gen7-architectural-twin-benchmark','started_at':STARTED,'ended_at':datetime.now(timezone.utc).isoformat(),'passed':sum(c['ok'] for c in checks),'total':len(checks),'checks':checks,'metrics':metrics,'source_hashes':{'architecture_twin':sha(TWIN_PATH),'causal_spine':sha(CAUSAL_PATH)},'artifacts':{'twin_snapshot':build2['snapshot'],'causal_index':build2['causal_index'],'sqlite':build2['sqlite']}}
ART.parent.mkdir(parents=True,exist_ok=True); ART.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n'); result['artifact']=str(ART); result['artifact_sha256']=sha(ART)
print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(0 if result['passed']==result['total'] else 1)
