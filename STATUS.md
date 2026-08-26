# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN8_CONTEXT_COMPILER`

Generation 8 evolved **Optiplex_Lab + isolated `mcp-lab`** with a deterministic provenance-backed Context Compiler over the Gen7 Architectural Twin plus a reproducible Experiment Capsule for mutation-safe, version-pinned historical evaluation. `Optiplex_MCP` and the legacy repository remain frozen.

## Accepted Gen8 capability layer
- generation: `gen8-context-compiler-r1`
- capability build: `gen8-context-compiler-r1-39b7f040fca1`
- Context Compiler SHA256: `39b7f040fca1afb2332b5dd902e186b710ea4d1d5a2cd0351aa307f6d8f786c3`
- Experiment Capsule SHA256: `69d66ecaec546f08ea6079c5446254bc1704c791f77bf76ce472d1f4907f7415`
- Gen8 benchmark source SHA256: `5ab33dc21de64f88b60ee4ec404051e669fbe754fafadfe5d88ec2486ce207e7`
- frozen gold SHA256: `f7fc1835e2fd65f99f52945533c6d709614302bab9ce79f9c4ef5f40c01d840d`
- permanent MCP surface: **10 before / 10 after**

Gen8 did **not** modify `server.py`. Operational `lab_status` intentionally remains server generation `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG SHA `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.

## Gen8 evidence
- benchmark: **17/17 PASS**
- required-evidence recall: **1.000**
- critical evidence: **41 TP / 21 FP / 0 FN**, precision **0.6613**
- unrelated negative controls: **PASS**
- task-kind classification: **PASS**
- deterministic packet: **PASS**
- stale/missing critical evidence: **fail-closed / bounded broadening PASS**
- contradictory authority: **surfaced + fail-closed PASS**
- critical-evidence ablation: **PASS**
- median compile latency: **110.09 ms**
- average packet: **23.1 KB**
- broad context reduction: **95.1%**
- practical baseline reduction: **91.6%**
- final Twin: **173 nodes / 242 edges / 85 inputs**, graph digest `ceab9a44188706a209b23066217de4e8991b44d067d6c21f9018d56861c182eb`
- Twin snapshot SHA256: `f1299fa23330944c734377203c4769fb4e8e27a9ac104f64397299a277ba9eea`

## Experiment Capsule / retained regressions
- Gen4 known leak case: **18/18 PASS**, zero forbidden accepted-state mutations (`cap8_20260826T160908Z_a0fba037`)
- Gen5 known leak case: **12/12 PASS**, zero forbidden accepted-state mutations (`cap8_20260826T152539Z_a2d9178c`)
- retained Gen2: **12/12 PASS**
- retained Gen3: **16/16 PASS**
- retained Gen4: **18/18 PASS**
- retained Gen5: **12/12 PASS**
- retained Gen6: **13/13 PASS**
- retained Gen7: **15/15 PASS** in a capsule-local Gen7-era source/evidence view

A normal Gen7 rerun against the Gen8-expanded Twin produced **14/15** because `benchmark_gen8` is now a legitimate additional validation edge. The unmodified Gen7 benchmark passed **15/15** in a version-pinned Gen7-era capsule view. This is retained evidence that historical regressions require version-pinned experiment views.

## Protected-state result
The earliest pre-retained manifest predates monitoring `/etc/systemd/system`. The accepted comparison therefore uses the exact earliest/final **common protected-resource intersection**, permits only verified prefix-preserving append-only growth of `/var/lib/optiplex-lab/traces/events.jsonl` (**128,484 bytes** in the recorded comparison), and records `/etc/systemd/system` separately as newly monitored without falsely claiming an earliest baseline. Every later same-schema capsule before/after result reports **zero forbidden accepted-state mutations**.

## Canonical evidence
`plans/GEN8_CONTEXT_COMPILER_EXPERIMENT_CAPSULE.md`, `lab_generations/GEN8_RESULT.json`, `GEN8_GOLD.json`, `GEN8_BENCHMARK.json`, `GEN8_CONTEXT_PACKETS.json`, `GEN8_CAPSULE_EVIDENCE.json`, `GEN8_RETAINED_REGRESSIONS.json`, `GEN8_TWIN_SNAPSHOT.json` + lossless `.xz`, exact Gen4/Gen5 capsule evidence under `GEN8_CAPSULE_RUNS/`, and `GEN9_PROPOSALS.json`.

## Gen9
Top evidence-backed direction: **Context Necessity Optimizer / semantic evidence minimization**. Gen8 achieved zero critical false negatives but remains conservatively over-inclusive. Do not implement Gen9 without a new explicit request.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell.
