# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN7_SELF_MODEL`

Generation 7 evolved **Optiplex_Lab + isolated `mcp-lab`** with a deterministic, provenance-backed Architectural Digital Twin and Causal Observability Spine. `Optiplex_MCP` and the legacy repository remained frozen.

## Accepted Gen7 capability layer
- generation: `gen7-self-model-r1`
- capability build: `gen7-self-model-r1-f5ba258ed555`
- Architectural Twin SHA256: `f5ba258ed5559b755f5b68891a74f48bdfac243638bff60cc730c0f3cbf61d8e`
- Causal Spine SHA256: `be7a798db4f7976e74deb787ad277a56f5fde719144280b8619b7e87b92124d3`
- accepted Twin graph digest: `49ddf70f7baa2b73508e2921250cdf131805648421d96338ebd0cf84c9b4ce2c`
- permanent MCP surface: **10 before / 10 after**

Gen7 did **not** modify `server.py`. Operational `lab_status` therefore intentionally remains server generation `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG SHA `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.

## Gen7 evidence
- benchmark: **15/15 PASS**
- dependency precision / recall: **1.000 / 1.000** (12 TP, 0 FP, 0 FN, 6 TN)
- change-impact precision / recall: **1.000 / 1.000** (3 TP, 0 FP, 0 FN)
- median bounded query latency: **1.586 ms**
- architecture context proxy: **7,466 B vs 2,166,931 B — 99.66% reduction**
- accepted Twin: **165 nodes / 224 edges / 80 inputs**, only **1 inferred edge**
- causal final rebuild: **3,918 events / 4,380 links**
- real Gen6 failure -> regression lineage: **PASS**
- bad-candidate -> auto-rollback -> LKG lineage: **PASS**
- stale/missing evidence surfaced explicitly: **PASS**
- retained regressions: Gen2 **12/12**, Gen3 **16/16**, Gen4 **18/18**, Gen5 **12/12**, Gen6 **13/13**
- final guest selftests: **all PASS**
- canonical tests: **13 passed**
- containment: **PASS**
- frozen Optiplex_MCP: **PASS unchanged**

## Important Gen7 findings
1. Fixed a real Twin AST role-state bug that hid the Gen6 benchmark dependency on `experience_loop.py`.
2. Rejected and repaired canonical/guest byte-identity drift during source transfer.
3. Found the legacy Gen5 benchmark is non-idempotent against populated Forge state; retained Gen5 now runs in an isolated empty Forge/regression namespace.
4. Found retained Gen4 lifecycle benchmarking could rewind real build metadata even with cloned registries. The final gate caught it and restored Gen6 operational metadata through `lab-upgrade-transaction`; this materially raises experiment isolation for Gen8.

Canonical evidence: `plans/GEN7_ARCHITECTURAL_TWIN_CAUSAL_SPINE.md`, `lab_generations/GEN7_RESULT.json`, `GEN7_BENCHMARK.json`, `GEN7_TWIN_SNAPSHOT.json` + lossless `.xz`, `GEN7_CAUSAL_EVIDENCE.json`, `GEN7_RETAINED_REGRESSIONS.json`, and `GEN8_PROPOSALS.json`.

## Gen8
Evidence ranks **Context Compiler on top of the Architectural Twin** first, followed by **Reproducible Experiment Capsule + Evaluator / Mutation Nursery**. Do not implement Gen8 without a new explicit request.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell.
