# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN13_HIERARCHICAL_EXPERIMENT_ISOLATION`

Generation 13 evolved **Optiplex_Lab + isolated `mcp-lab`** with **Hierarchical Experiment Isolation + Nested Evaluation Delegation**. One Gen8 Experiment Capsule owns each mutable physical boundary; children and supported grandchildren receive deterministic delegated contexts, bounded mutation scopes, evidence/authority bindings, provenance lineage, mutation reconciliation, and cleanup responsibility without stacking another incompatible OverlayFS universe. `Optiplex_MCP` remains frozen and the permanent Lab MCP surface remains exactly 10 tools.

## Accepted Gen13 capability
- generation: `gen13-hierarchical-experiment-isolation-r1`
- capability build: `gen13-hierarchical-experiment-isolation-r1-9a32955b79c6`
- hierarchy SHA256: `9a32955b79c63efd1023ca1741bff61ab2b0ed5dfb3eaea0aa817b777421a372`
- Experiment Capsule SHA256: `e1276653cde8c0fd9df2a0ebddc5ca5fb148e939ea182996a80563b6b60c05a8`
- Counterfactual Replay SHA256: `6d7f32a86ce73501feecffd21ba6ca319de548f9b29044c9e737baba824dbac0`
- benchmark source SHA256: `e6dce8fe8c3858c9fa8e425d06ef2a7838b6341b2d5dab6d78f47d89dc1e1b1e`
- frozen gold SHA256: `93f0976bfc47542105252cc288b093cb453341ca623f6757cfdd032c4676e785`
- `server.py`: **unchanged**; permanent MCP tools: **10**

Operational Lab intentionally remains Gen6: `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.

## Gen13 evidence
- frozen benchmark: **37/37 PASS**
- deterministic semantic composition **100%**; declared mutation attribution **100%**; authority monotonicity **100%**
- unsafe adversarial cases **17/17 rejected**; authority expansion accepted **0**; ambiguous isolation ownership accepted **0**
- historical leakage **0**; forbidden accepted-state mutations **0**; cleanup failures **0**
- valid delegated Gen12 mutating replay **100%**; standalone Gen8/Gen12 compatibility **100%**
- read-only child, mutable child, and grandchild all execute under the same explicit physical isolation owner
- ambiguous/unsafe nested Gen12 replay still fails closed with `ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION`

## Self-use / defects
The first frozen run was **36/37**. Gen13 self-use exposed one real implementation defect: OverlayFS copy-up emitted structural ancestor-directory metadata for an exact delegated file, and the first reconciler misclassified it as an undeclared child mutation. The classifier was fixed without changing frozen gold, and the same benchmark passed **37/37**. A `tee` log also tripped the frozen debris check; it was removed rather than weakening the check.

Retained validation also surfaced two correct fail-closed harness/precondition catches: Gen10 refused a stale Twin until refreshed, and Gen12's future-evidence fixture had to be removed before sealing its retained historical epoch. Both unchanged benchmarks then passed.

## Retained regressions
- Gen2 **12/12**, Gen3 **16/16**, Gen4 **18/18**, Gen5 **12/12**, Gen6 **13/13**
- Gen7 **15/15** version-pinned, Gen8 **17/17** quiescent, Gen9 **20/20**, Gen10 **24/24**, Gen11 **39/39** + routing gold **29/29**, Gen12 **30/30**
- Gen12 determinism/baseline reproduction/attribution remain **1.0 / 1.0 / 1.0**, unsafe **10/10**, historical leakage **0**

## Protected state / containment
- zero forbidden protected-state changes; ordinary trace growth is prefix-preserving append-only audit only
- private/control targets blocked; host repo not visible; no host Docker/libvirt/control sockets exposed
- all **39** Capsule runs created during Gen13/retained validation were cleaned; historical Gen8 fixtures were preserved
- no leaked Gen13 child processes or systemd units; no Gen13 transfer/temp/archive debris remains

## Final Twin checkpoint
- **202 nodes / 311 edges / 104 inputs**
- graph `42ca8780f3c379115a6613cdad526767d17d59f95d0aad3d34e0d36f0a32ecd9`
- snapshot SHA256 `7145b9b2ef4b0df93981d260cfc8ad6fdfd00799652d4d3b6a0e834b1e24b126`
- causal digest `1224672e1c5d899a4754ea55736d46b4d6b2923679e49ce9ba42d016b1646c10`
- verify **PASS, zero issues at checkpoint**
- the outer Lab call can append one normal trace event after a checkpoint returns; this is valid next-epoch evidence.

## Gen14 direction
Ranked #1 is **Evaluator Mutation Nursery / Benchmark Hardening**. The intended strategic sequence is Gen14 evaluator hardening, then Gen15 **Project Onboarding + Domain Capability Expansion Pilot** unless evidence reveals another prerequisite. See `lab_generations/GEN14_PROPOSALS.json`.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell.

## Final canonical validation
- canonical project tests: **13/13 PASS**
- mutation-free Python syntax: **42 files PASS**
- JSON/JSONL: **97 JSON, 2 JSONL / 118 records PASS**
- secret/credential scan: **17 Gen13-owned files PASS**
- `git diff --check`: **PASS**; 12 new Gen13 files separately checked for whitespace/final-newline correctness
- containment/protected-state: **PASS**, zero forbidden mutations
- Gen13 temp/archive/process/service debris: **none**
- final acceptance validated at `2026-08-26T23:39:07.489050+00:00`
