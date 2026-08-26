# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN9_CONTEXT_NECESSITY`

Generation 9 evolved **Optiplex_Lab + isolated `mcp-lab`** with a deterministic proof-carrying Context Necessity Optimizer layered on the accepted Gen8 Context Compiler. `Optiplex_MCP` and the legacy repository remain frozen.

## Accepted Gen9 capability layer
- generation: `gen9-context-necessity-r1`
- capability build: `gen9-context-necessity-r1-6be10d7af323`
- Context Necessity Optimizer SHA256: `6be10d7af3238fb59a2cf8f5d9a858de4b3957a9681634bbe4ef78e33402d299`
- Gen9 benchmark source SHA256: `03fe8a7845d08574f211f5cada42578c4be53912a81c0797554c5117a5b19152`
- frozen Gen9 gold SHA256: `dc755fd02e1dc44c1aed1cdf9a3f1745d6049178472a0165cbdf40867f5ae637`
- permanent MCP surface: **10 before / 10 after**

Gen9 did **not** modify `server.py` or `context_compiler.py`. Operational `lab_status` intentionally remains server generation `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG SHA `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.

## Gen9 evidence
- frozen benchmark: **20/20 PASS**
- required-evidence recall: **1.000**
- necessity-aware critical evidence: **47 TP / 0 FP / 0 FN**, precision **1.000**
- strict comparable legacy Gen8-ID precision: **0.931818** on exact accepted Gen8 Twin
- raw current-Twin legacy diagnostic: **0.87234** because three legitimate Gen9 validators are post-Gen8 evidence
- average context payload: **20,623 -> 11,119 bytes**, **46.09% reduction**
- broad context reduction: **97.90%**
- practical baseline reduction: **95.97%**
- median minimization latency: **1.94 ms** (p95 **4.516 ms**)
- deterministic output, negative controls, task-kind preservation, duplicate collapse, high-fanout bounding, stale/missing/contradiction fail-closed, necessary/redundant ablation, safety-critical retention: **PASS**

The frozen gold and thresholds were never relaxed. When the Gen9-expanded Twin introduced three legitimate `benchmark_gen9` validation edges, benchmark accounting was repaired rather than deleting future-valid evidence: post-gold current validators require an observed direct path from a frozen required owner, and the strict legacy threshold is evaluated on the exact lossless accepted Gen8 Twin.

## Final Twin / self-use
- final Twin: **179 nodes / 259 edges / 89 inputs**
- graph digest: `4d983ad01376a04a54dc834d0dc46ee4d606293fca572f3d8ead45e81e65c45f`
- snapshot SHA256: `2c05c6282070c74bee204e837d0b8d6a03677ab404a407318c8a4d27594484be`
- verify: **PASS, zero issues**

Self-use exposed three useful failures rather than hiding them: the frozen Gen8 Twin initially could not resolve new Gen9 owners; an optimizer source-path lock accidentally retained a validation alias and was fixed with a regression self-test; and a finalization packet correctly failed closed when Tier-1 benchmark artifacts became newer than its Twin. Focused post-rebuild Gen9 tasks resolved the optimizer source plus current benchmark/selftest evidence without fail-closed behavior. See `lab_generations/GEN9_SELF_USE.json`.

## Retained regressions / protected state
- Gen2 **12/12**, Gen3 **16/16**, Gen4 **18/18**, Gen5 **12/12**, Gen6 **13/13**
- Gen7 **15/15** in an unmodified, version-pinned Gen7-era capsule view hiding Gen8/Gen9 additions
- Gen8 **17/17**, required recall **1.0**, critical FN **0** on current Gen9-expanded view
- every Gen9 retained capsule reports zero forbidden accepted-state mutations
- protected build/server/LKG, registries/provenance, `/etc/systemd/system`, workflows and workflow-graphs remained unchanged
- trace change is verified prefix-preserving append-only audit growth only (**61,973 bytes at the recorded comparison checkpoint**)
- containment: public internet available; protected host endpoint blocked; no host repo/control sockets inside guest

## Canonical evidence
`plans/GEN9_CONTEXT_NECESSITY_OPTIMIZER.md`, `lab_generations/GEN9_GOLD.json`, `GEN9_BENCHMARK.json`, `GEN9_CONTEXT_PACKETS.json`, `GEN9_RETAINED_REGRESSIONS.json`, `GEN9_SELF_USE.json`, `GEN9_PROTECTED_STATE.json`, `GEN9_RESULT.json`, and `GEN10_PROPOSALS.json`.

## Gen10
Top evidence-backed direction: **Evidence Epoch / Snapshot Freshness Coordinator**. Do not implement Gen10 without a new explicit request.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell.
