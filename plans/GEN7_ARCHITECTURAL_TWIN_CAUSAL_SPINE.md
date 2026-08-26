# Generation 7 — Architectural Digital Twin + Causal Observability Spine

Status: **ACCEPTED**

## Thesis
Understand yourself before changing yourself. The Lab should answer what it is, what depends on a component, what happened, what a proposed change could affect, and what evidence supports the answer without broad ad-hoc source rereading.

## Baseline evidence
Gen6 already reduced the repeated-task context proxy by 83.4% and achieved 100% correct memory retrieval with 0% wrong-memory invocation. The remaining measured gap is architecture/dependency reasoning and causal attribution: the failure-regression compiler cannot claim causal minimality, while Gen2–Gen6 evidence is split across Python source, workflow/graph definitions, registries, traces, provenance logs, build/LKG state, and benchmark artifacts.

## Designs considered

### A. Rebuildable relational/property index over authoritative evidence — CHOSEN
- SQLite derived index plus deterministic JSON snapshot.
- Nodes/edges are generated from installed source ASTs, workflow/graph definitions, registries, build/recovery state, benchmarks, and immutable provenance/trace evidence.
- Every important fact carries source path/hash, observation kind, confidence, and freshness state.
- Raw logs remain append-only authority; SQLite/JSON views are disposable and rebuildable.
- Causal relationships are only marked `causal` when an explicit identifier/reference establishes parent/child or production lineage. Time-nearby events remain `correlated` or are omitted.

Why: small dependency footprint, deterministic, queryable, easy to rebuild, and does not create a second source of truth.

### B. Hand-maintained unified architecture/causal registry
A single curated property graph would be easy to query but would duplicate truth and become stale as capabilities/workflows evolve. Rejected as the primary model. Small explicit invariant seed facts are allowed only where they represent stable authority/security policy and are provenance-tagged.

### C. Instrument every Gen2–Gen6 subsystem with new parent-span propagation
Would improve future traces but requires broad source/server edits before proving value, increases restart/recovery surface, and is unnecessary for most existing relationships because graph/workflow/code/capability IDs already provide strong joins. Deferred unless benchmark evidence shows unacceptable causal gaps.

## Chosen implementation

### `architecture_twin.py`
Guest-local CLI/library that rebuilds `/var/lib/optiplex-lab/twin/twin.sqlite3` and a deterministic JSON snapshot from authoritative inputs.

Node classes include source/module, service/runtime, MCP tool, workflow, workflow graph, capability, evaluator, procedural memory, regression, registry, benchmark, generation/build, recovery/LKG, authority boundary, and trace/provenance artifacts.

Edge classes include `imports`, `depends_on`, `invokes`, `produces`, `consumes`, `validates`, `gates`, `supersedes`, `generated_from`, `recovers_to`, `authoritative_for`, `protected_by`, and `prohibited_from_accessing`.

Observed edges are preferred. Static AST/reference-derived edges are `observed_static`; runtime identifier joins are `observed_runtime`; explicit durable registry lineage is `observed_registry`; bounded heuristics are `inferred` with reduced confidence and an explanation.

### `causal_spine.py`
Builds a normalized event/relationship view from existing trace/provenance/launcher evidence. Raw JSONL files remain untouched. Stable existing run IDs are preserved. Derived causal links record evidence line/source hash and relation strength (`causal`, `lineage`, `correlated`).

### Change-impact analysis
Given a node/path/hash/reference:
1. resolve exact Twin node(s);
2. walk outgoing and reverse dependency edges over a bounded allowlist of impact-bearing relations;
3. attach relevant workflow/graph/capability/memory/regression/benchmark/recovery nodes;
4. select validation gates from explicit `validates`, `gates`, `protected_by`, and dependency evidence;
5. report direct/transitive impact separately;
6. fail closed on stale/missing evidence by adding uncertainty and conservative validation rather than inventing edges.

The impact engine is advisory architecture reasoning only. It cannot edit code or grant authority.

## Safety / authority
- No Optiplex_MCP changes.
- No new permanent MCP tools expected; target remains 10.
- No host credentials, mounts, private topology, or control sockets in the Twin.
- Authority/security boundary nodes contain only the already-public project invariants and blocked classes of access.
- Secret-like payload values are not indexed; event ingestion uses identifiers, hashes, event types, success/failure, and sanitized metadata only.
- Server modification is not planned, so Gen4 candidate/LKG restart machinery is not required for the initial implementation.

## Acceptance benchmark
Target roughly 12–15 checks covering deterministic rebuild, known Gen2–Gen6 dependencies, source-to-validation impact, unrelated-component negative control, stale evidence, real graph→workflow→Code Mode reconstruction, Gen6 failure→regression lineage, recovery lineage, query latency/index size, context-byte proxy reduction, tool-count preservation, and containment.

## Self-use requirement
Gen7 must rebuild/query its own Twin before final validation and use impact analysis to choose at least one targeted validation set for its own source changes. Full retained regression suites still run before final acceptance.
