# Generation 9 — Context Necessity Optimizer

## Thesis

**Prove What Context Is Necessary.** Generation 9 adds a deterministic, provenance-backed minimization layer after the accepted Gen8 Context Compiler. It does not replace Gen8 selection, alter the permanent MCP schema, or weaken fail-closed behavior. The optimizer asks which already-selected evidence is necessary for the task and safety envelope, records an inspectable proof for every removal, and leaves the original compiler as the conservative recall-oriented substrate.

## Starting authority

- Canonical capability: `gen8-context-compiler-r1`, build `gen8-context-compiler-r1-39b7f040fca1`.
- Context Compiler SHA256: `39b7f040fca1afb2332b5dd902e186b710ea4d1d5a2cd0351aa307f6d8f786c3`.
- Experiment Capsule SHA256: `69d66ecaec546f08ea6079c5446254bc1704c791f77bf76ce472d1f4907f7415`.
- Final Gen8 Twin: 173 nodes / 242 edges / 85 inputs, graph digest `ceab9a44188706a209b23066217de4e8991b44d067d6c21f9018d56861c182eb`.
- Operational MCP remains Gen6, 10 tools, live server == LKG == `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`.
- Optiplex_MCP remains frozen at release `frontend-a5c1c5be8b22`, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

## Evidence-derived Gen8 over-inclusion diagnosis

The 21 reported Gen8 critical false positives are not one phenomenon:

1. **Evaluation dependency promotion — 9 FPs.** `benchmark_gen7.py` has direct dependency edges to retained older-generation modules. Gen8 makes depth-1 critical source dependencies Tier 1, even when the task asks for Gen7's authoritative evaluation evidence. Eight retained predecessor modules plus the benchmark validation alias are therefore treated as critical.
2. **Lifecycle high-fanout impact — 10 FPs.** `server.py` is depended on by many retained benchmarks and invoked by multiple workflow versions. Gen7 change-impact returns all of these, and Gen8 upgrades every returned validation to mandatory Tier 1. Four workflow consumer versions are also attached. Raw reachability cannot distinguish a proof witness from every possible consumer.
3. **Current-valid post-gold validation — 1 FP.** `validation:benchmark:benchmark_gen8` is now a legitimate validator of `experience_loop.py`, but the Gen8 gold was frozen before that current-valid edge existed. Gen9 must not delete it merely to improve an old metric.
4. **Required-kind accounting artifact — 1 FP.** `causal:49459d02b4090c8b` satisfies the Gen8 gold's required `causal_evidence` kind but Gen8 precision counted only `required_ids`, so it was labeled FP. Gen9 metrics count required-kind and required-any witnesses correctly.

Additional non-critical excess exists in Tier 2: generation lineage already represented by provenance, registry/object support already represented by selected authoritative records, and broad lifecycle causal history when no historical causal question was asked.

## Architectures considered

### A. Retune Gen8 graph expansion in-place

Reduce depth, fanout, or relation classes inside `context_compiler.py`. Rejected as the primary design because it couples recall and precision, mutates the accepted Gen8 substrate, and can turn a precision improvement into a silent critical false negative. It also cannot cleanly explain why an individual selected record was removed.

### B. Embedding/vector or learned reranking

Rank selected evidence by semantic similarity and keep the top results. Rejected: opaque score behavior, additional nondeterminism/model/version provenance, weak safety proofs, and no evidence that it is needed for the observed structural failure modes.

### C. Runtime exhaustive capsule ablation

Run a destructive/evaluator capsule for every evidence record on every compile. Useful as validation evidence but rejected as the runtime mechanism: excessive latency and stateful evaluator cost. Experiment Capsules remain the safety substrate for benchmark ablation and retained-regression proof.

### D. **Chosen: proof-carrying deterministic post-compiler optimizer**

Keep Gen8 as a conservative recall-maximizing compiler, then minimize its packet with task-scoped proof obligations, semantic dominance, current-version evidence, and conservative fail-closed locks. Every removed record gets an explicit deterministic reason. Benchmark-time leave-one-out/grouped ablation proves the rules against frozen gold and mutation-safe capsules.

## Chosen optimizer design

The new module is additive (`context_necessity.py`). `context_compiler.py` remains byte-for-byte unchanged unless a demonstrable blocker appears.

### 1. Safety gate

Do not minimize when the Gen8 packet is fail-closed, contains an authority contradiction, or contains stale/missing/changed critical evidence. Preserve the packet and report `minimization_blocked` with the exact uncertainty/contradiction evidence. Safety is not a precision target.

### 2. Non-removable obligations

Always retain:

- Tier-0 authority/security and operational identity;
- explicit exact source owners named by the task;
- lifecycle build/LKG/service evidence when lifecycle/recovery is the task;
- exact regression plus causal evidence for debugging/lineage tasks;
- explicit memory/capability/evaluator evidence for reuse/memory tasks;
- any record whose removal would leave a safety obligation without a witness.

### 3. Tier-2 optional minimization

Gen8 already defines Tier 2/3 as budget-prunable. Gen9 removes Tier-2/3 records that carry no task-specific or safety obligation. This is a semantic minimizer, not blind truncation: explicit historical/causal/reuse requests can promote otherwise optional evidence to an obligation.

### 4. Evaluation generation scoping

For an explicitly versioned `benchmark_genN` evaluation, the benchmark source is the owner and its generation is the semantic scope. Retained predecessor-generation source dependencies are not primary evidence for the requested generation unless the task explicitly asks for retained regressions/history. GenN source dependencies and GenN benchmark artifacts remain. A validation node whose identity is exactly the already-selected benchmark source is a semantic alias and is collapsed for an evaluation-evidence task.

This directly addresses Gen8's 9 evaluation FPs without changing Twin history or historical gold.

### 5. Lifecycle validation-witness minimization

For lifecycle/recovery tasks, broad change-impact validations are candidate proof witnesses, not all mandatory facts. Map each candidate validation to its source and score deterministic coverage of the task's lifecycle atoms (`recovery/LKG`, `restart/service`, `build/identity`). Reduce only when one candidate has full atom coverage and a unique strongest evidence score; otherwise retain the broad set. This is intentionally fail-conservative.

The current evidence gives `benchmark_gen4.py` the unique strongest full-coverage proof for the server lifecycle task. Gen2/Gen4 remain an equivalence witness group in frozen gold; no benchmark is hard-coded into the optimizer.

### 6. Reverse-consumer and workflow-version dominance

A workflow that merely invokes the selected source is not necessary for a lifecycle evidence task unless the task asks about workflows/transactions/promotion. When workflows are in scope, collapse same-name versions only when an active `CURRENT` version is provenance-proven (or an explicit injected active-version map is supplied); historical/version-pinned tasks disable this collapse.

### 7. Semantic duplicate/subsumption collapse

Exact semantic duplicates are fingerprinted from kind, identity, structured fact, and provenance. Keep the strongest/most authoritative representative. Registry/object/generation support is removable when it adds no unique task or provenance obligation beyond a selected authoritative record.

### 8. Proof and deterministic digest

The result contains a compact `necessity_proof` with:

- baseline packet digest;
- retained IDs;
- removed IDs and rule/reason;
- task/safety obligations and witnesses;
- blocked state if applicable;
- deterministic optimizer/context digests.

Latency/timestamps are measurement metadata and excluded from deterministic digests.

## Frozen Gen9 benchmark contract

`lab_generations/GEN9_GOLD.json` is frozen before optimizer implementation. It includes the seven real Gen8 task families plus synthetic necessity/duplicate/fanout/fail-closed/version/safety cases. The current-valid Gen8 validation and required-kind causal witness are explicitly represented so Gen9 does not game legacy accounting.

### Acceptance thresholds set before tuning

- required-evidence recall: **1.0000**;
- critical false negatives: **0**;
- necessity-aware critical precision: **>= 0.90**;
- strict legacy Gen8-ID precision: **>= 0.90** on the comparable Gen8 cases, with current-valid/required-kind accounting called out separately;
- average context-payload bytes: **>= 15% lower** than raw Gen8 packets on the frozen real cases;
- context reduction vs broad/practical baselines: preserved or improved;
- incremental minimization latency median: **<= 25 ms** on the frozen real cases;
- deterministic output: identical digest for identical packet/task/snapshot;
- stale/missing/contradiction safety: fail-closed and not minimized;
- no protected-state mutation from ablation/retained-regression experiments;
- Gen2–Gen8 retained regressions all pass, Gen7 version-pinned at 15/15.

No threshold may be relaxed after tuning merely to accept the implementation.

## Experiment Capsule policy

Use the accepted Gen8 Experiment Capsule for mutation-prone ablation, evaluator mutation, and retained benchmarks. The earliest protected manifest does not cover `/etc/systemd/system`; final comparison uses only the exact earliest/final common protected-resource intersection and verified prefix-preserving append-only trace growth. Later same-schema capsule runs provide separate evidence for newly monitored systemd paths.

## Self-use plan

1. Preserve the already-recorded Gen8 compile of the Gen9 design task as baseline evidence.
2. Once the optimizer is stable, compile/minimize the same Gen9 task.
3. Record at least one correct removal, one protected required item rejected from removal, and any optimizer/benchmark flaw found by self-use.

## Scope exclusions

No MCP schema change, no server change by default, no Gen10 implementation, no broad Counterfactual Replay product, no general mutation nursery product, no autonomous event reaction, and no capability consolidation outside what is strictly needed for context necessity validation.

## Accepted implementation outcome

Gen9 completed with the frozen gold unchanged. The final optimizer is `gen9-context-necessity-r1` at SHA256 `6be10d7af3238fb59a2cf8f5d9a858de4b3957a9681634bbe4ef78e33402d299`; the final benchmark source is `gen9-context-necessity-benchmark-r2` at SHA256 `03fe8a7845d08574f211f5cada42578c4be53912a81c0797554c5117a5b19152`.

The Gen9-expanded Twin exposed a benchmark-accounting bug after tuning: three new `validation:benchmark:benchmark_gen9` edges were direct, observed validators of frozen required owners and therefore legitimate current evidence, not false positives. The gold and thresholds were not changed. The benchmark correction recognizes post-gold evidence only when the validation node is absent from the exact accepted Gen8 Twin and an observed two-node dependency path starts at a frozen required owner. The strict legacy precision gate is evaluated separately on the exact lossless accepted Gen8 Twin snapshot.

Final frozen benchmark result: 20/20 PASS; required recall 1.0; necessity-aware 47 TP / 0 FP / 0 FN; strict comparable legacy precision 0.931818; average context payload reduction 46.0856%; median minimization latency 1.94 ms. Final derived Twin after all stateful validation: 179 nodes / 259 edges / 89 inputs, graph digest `4d983ad01376a04a54dc834d0dc46ee4d606293fca572f3d8ead45e81e65c45f`, snapshot SHA256 `2c05c6282070c74bee204e837d0b8d6a03677ab404a407318c8a4d27594484be`.
