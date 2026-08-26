# Generation 11 — Task Intent Classification + Authority Routing Hardening

## Thesis

**Classify Intent Before Routing Authority.** Gen11 inserts a deterministic, inspectable, proof-carrying routing layer before the accepted Gen8 Context Compiler, Gen9 Necessity Optimizer, and Gen10 Evidence Epoch. The router identifies the requested action rather than letting incidental nouns such as `security`, `failure`, `benchmark`, `recovery`, or `design` dominate context selection.

Gen11 does not change the permanent MCP surface, widen authority, modify the accepted Gen6 operational server, or weaken Gen8–Gen10 freshness/necessity/epoch guarantees.

## Starting authority

- Accepted capability: `gen10-evidence-epoch-r1`, build `gen10-evidence-epoch-r1-9418201f1401`.
- Evidence Epoch Coordinator SHA256: `9418201f1401e56a6dd62f8cb696b3bf947f822073b83d07fa57b028f3ba035f`.
- Gen10 benchmark source SHA256: `6c43563621203bd6b201b40de8d425984a9aa1ba1c340be9198c6fb8ea05c6ef`.
- Frozen Gen10 gold SHA256: `970c3a1db846f25d9f0d9f1e8a8b28d11a1c45439642c8d5831eca2ab94f31de`.
- Final Gen10 Twin: 186 nodes / 279 edges / 94 inputs; graph `947181e319337fac733ca7482b8b14e967a8c99a54d22bc6dde368df67ca3b09`.
- Operational Lab remains accepted Gen6, exactly 10 permanent tools, live server == LKG == `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`.
- Frozen Optiplex_MCP remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

## Phase 1 — observed routing failure modes

1. **Failure vocabulary dominates requested design/change action.** Gen8 `classify()` gives `debug`, `failure`, `failed`, `trace`, `causal`, etc. absolute precedence. A request to design or implement a change motivated by a prior failure is therefore routed as debugging even when no diagnosis is requested.
2. **Recovery vocabulary can turn implementation discussion into lifecycle work.** A code task that modifies recovery-handling logic can be routed to lifecycle/recovery because the classifier does not distinguish changing recovery *code* from executing a recovery/lifecycle action.
3. **Evaluation nouns can over-select benchmark evidence.** Mentioning a benchmark as background to a debugging or implementation request can turn the task into evaluation and pull evaluator/benchmark artifacts that are not task obligations.
4. **Design tasks can over-select runtime safety evidence.** `security`, `rollback`, or `containment` nouns inside an architecture discussion can cause runtime/lifecycle authority to dominate even though the requested action is design only.
5. **Debugging can over-select architecture/design evidence.** Current keyword overlap and broad fallback can attach architectural owners to diagnosis requests even where causal/regression evidence is decisive.
6. **Mixed-intent precedence is implicit.** A request such as “debug this failed restart, then repair the lifecycle workflow” contains diagnosis plus lifecycle/implementation actions, but Gen8 produces one task kind and cannot prove why one obligation outranks another.
7. **Lifecycle actions need stronger obligations than similarly worded code edits.** “Patch rollback.py” and “roll back the accepted server” share nouns but require different authority: source/validation versus current build/LKG/recovery/security state.
8. **Security actions need stronger obligations than design text containing security words.** “Design a containment API” and “change containment policy / expose a host socket” are not equivalent authority requests.
9. **Historical/version-pinned intent is a modifier today, not a first-class route.** Gen9 can preserve historical workflow versions, but the front-door classifier does not explicitly prove historical scope or distinguish replay from current action.
10. **Single-label classification loses safety-relevant secondary intent.** A mixed implementation+lifecycle request may require lifecycle evidence even when implementation is the primary action; conversely a lifecycle noun in a pure implementation request should not force that obligation.
11. **Similar nouns can require opposite routing.** “Evaluate recovery benchmark semantics” is evaluation; “restart recovery after benchmark failure” is lifecycle; “debug why the recovery benchmark failed” is debugging. Noun overlap alone cannot resolve authority.
12. **Ambiguous safety requests need conservative handling.** If text plausibly requests a live lifecycle/security action but does not make the action boundary clear, routing must preserve the safety authority or fail closed rather than guess a lower-authority interpretation.

These are front-door consistency defects, not evidence-freshness defects. Gen10 guarantees one coherent evidence epoch only after the evidence universe is chosen; Gen11 must prove why that universe was chosen.

## Architectures considered

### A. Fixed deterministic task-kind rules
A refined ordered regex/rule table. Simple and inspectable, but still tends toward brittle single-label precedence and cannot naturally preserve safety-relevant secondary intent.

### B. Hierarchical intent classifier
First determine action vs explanation, then sub-classify design/change/debug/evaluate/lifecycle/security/history. Better structure, but a single tree still loses legitimate mixed intents.

### C. Multi-label intent + precedence graph
Detect independent action frames, retain primary and secondary intents, then apply deterministic precedence. Handles mixed tasks well and makes conflicts inspectable. Needs a separate authority mapping to avoid labels becoming policy by accident.

### D. Authority-first routing independent of task labels
Detect requested authority effects directly (source mutation, accepted-state lifecycle action, containment change, historical read, evaluator execution) and derive evidence obligations. Strong safety semantics, but alone gives weaker explanatory task taxonomy and is harder to benchmark for ordinary design/debug distinctions.

### E. Compiler-integrated scoring changes
Modify Gen8 scoring/classification in place. Small code surface, but couples intent semantics to evidence retrieval, makes proof boundaries murky, and risks Gen8/Gen9 regression behavior.

### F. Proof-carrying deterministic routing layer before Gen8
A separate module emits a canonical routing proof before compilation. The proof binds primary/secondary intent, decisive action features, precedence, authority classes, mandatory obligations, explicit non-obligations, ambiguity state, and digest. Gen8 receives a compatibility task-kind adapter while the original compiler remains otherwise unchanged.

### G. Chosen hybrid: F + C + D
Use a separate proof-carrying router; internally detect multi-label action frames; resolve primary intent with an inspectable precedence graph; independently derive authority/evidence obligations from requested effects. Labels explain the task, authority effects determine safety obligations. Gen10 seals the routing proof into the epoch identity.

## Proposed deterministic taxonomy

- `architecture_design`
- `implementation_change`
- `debugging_diagnosis`
- `evaluation_benchmarking`
- `lifecycle_recovery`
- `security_containment`
- `historical_replay`

A route has exactly one primary intent and zero or more secondary intents. “Mixed” is represented by the set, not by a lossy catch-all label.

## Action-aware precedence semantics

1. **Explicit live security/containment effect** outranks vocabulary-only design/implementation references and preserves containment authority.
2. **Explicit live lifecycle/recovery effect** outranks source-edit or diagnostic context and preserves build/LKG/recovery authority.
3. **Explicit diagnosis/root-cause action** outranks incidental benchmark/design/history nouns; historical scope remains secondary when requested.
4. **Explicit implementation/source mutation** outranks motivating failure/recovery/security vocabulary when no live lifecycle/security action is requested.
5. **Explicit evaluation/benchmark execution or scoring** outranks incidental failure/debug nouns when the benchmark/evaluator itself is the requested object of evaluation.
6. **Explicit architecture/design/proposal action** is primary when implementation/execution is not requested; safety nouns alone do not elevate authority.
7. **Historical replay/version-pinned read** is primary when reconstruction/replay is the requested outcome rather than evidence for a current debug/evaluation action.
8. When two explicit actions coexist, both intents are retained. Primary intent is determined by safety effect first, then requested terminal action; secondary intent obligations remain binding where safety-relevant.
9. Ambiguity that can change required lifecycle/security authority is `conservative_route=true` and must preserve the stronger authority or fail closed.

Negation and scope matter. “Do not restart; only patch restart logic” is implementation, not lifecycle. “Explain recovery design” is architecture/design. “Restart the service and verify LKG” is lifecycle/recovery.

## Authority classes and evidence obligations

Always required:
- `guest_security_boundary`
- `operational_identity`

Intent/effect-specific classes:
- architecture/design → `architecture_source`
- implementation → `source_implementation`, `validation_regression`
- debugging → `source_implementation`, `failure_lineage`
- evaluation → `benchmark_evaluator`, `validation_regression`
- lifecycle/recovery live effect → `lifecycle_state`, `recovery_lkg`, `security_containment`
- security/containment live effect → `security_containment`, `operational_identity`
- historical/replay → `historical_version_scope`, `causal_history`

The proof also records `evidence_explicitly_not_required`. This is an optimization assertion only, never permission to remove evidence that Gen8/Gen9/Gen10 independently marks critical because of freshness, contradiction, explicit references, or safety.

## Gen8 compatibility

Gen11 maps primary routes onto accepted Gen8 task kinds without rewriting Gen8 classification internals:
- architecture/design → `explanation_architecture`
- implementation → `code_change_planning`
- debugging → `debugging`
- evaluation → `evaluation`
- lifecycle → `lifecycle_recovery`
- security → `lifecycle_recovery` for conservative retrieval, with Gen11 security obligations proving the reason
- historical → `explanation_architecture` unless a stronger current action is primary

Gen11 then attaches the routing proof and locks any additional route-required evidence obligations before Gen9 minimization. Missing safety-critical route obligations fail closed.

## Gen10 integration

A routed epoch is created with the task and routing proof before compiler execution. The canonical epoch core includes:
- router source/version/hash;
- normalized task hash;
- routing proof and routing digest;
- required authority classes/evidence obligations;
- ambiguity/conservative-route state.

At compile time, the router is loaded from the immutable epoch view, the task is routed again, and the digest must exactly match the sealed route. The Context Compiler uses the route’s compatibility task kind; Gen9 minimizes only after Gen11 obligations are applied. Any route mismatch fails closed. Unrouted legacy `begin_epoch()` remains available for retained Gen10 compatibility; Gen11 acceptance/self-use uses routed epochs.

## Benchmark integrity

`lab_generations/GEN11_GOLD.json` is frozen before `lab_mcp/task_routing.py` or `lab_mcp/bench/benchmark_gen11.py` is created. Adversarial prompts deliberately place misleading vocabulary in subordinate clauses, motivations, quoted text, filenames, and negative controls. Harness defects may be repaired, but frozen expectations/thresholds are not relaxed to make implementation pass.

## Scope exclusions

No opaque embeddings/ML/LLM classifier, no external AI API, no permanent MCP tool, no `server.py` change, no authority widening, no Counterfactual Replay product, no Mutation Nursery product, and no Gen13 project-onboarding branch.
