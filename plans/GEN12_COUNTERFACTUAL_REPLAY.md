# Generation 12 — Counterfactual Replay over Intent-Routed Evidence Epochs

## Thesis

**Replay Alternate Decisions Without Rewriting History.** Gen12 adds a deterministic, provenance-backed replay layer over the accepted Gen10 Evidence Epoch and Gen11 intent/authority routing proof. A replay never edits historical truth: the sealed base view remains immutable and every alternative is an explicit, content-addressed overlay whose permitted effects are declared and checked.

## Entry state

- Accepted capability: `gen11-intent-authority-routing-r1`, build `gen11-intent-authority-routing-r1-59a1bef513c7`.
- Router SHA256: `59a1bef513c7d12b1411f78dfd9b5a4c007368d1c5e9e9e7f431f0bfedf2575b`.
- Route-aware Evidence Epoch SHA256: `24e9542919ff9aa781c33c534d012d82af91a9bf418be9a102fb7ba30b40b481`.
- Operational Lab remains Gen6, live server == LKG == `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 permanent tools.
- Frozen Optiplex_MCP remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.
- Gen12 entry refresh: 192 nodes / 288 edges / 98 inputs, graph `29267110a328bd1b11b5f94869bcb738ff04390f1b1d0fad0d5091c1cfa98294`, causal digest `62436582163343a9bbc8d56db7b71b57958b432934f839de9fed6067fdf63f4b`, freshness PASS.

## Architectures considered

### A. Full mutable state snapshot cloning
Clone the entire guest state for every replay. Strong physical isolation but expensive, makes semantic identity depend on irrelevant filesystem state, and obscures which declared delta caused an outcome.

### B. Git/worktree historical replay
Use commits/worktrees as the principal historical substrate. Excellent for source revisions, but insufficient for runtime registries, append-only evidence, route proofs, and non-Git Tier-1 state.

### C. Trace-only simulation
Replay recorded decisions without executing source. Fast and useful for routing/evaluator-only comparisons, but cannot establish real implementation behavior or protected-state isolation.

### D. Content-addressed epoch + declared overlay + Experiment Capsule
Use Gen10 immutable epoch bytes as historical truth, express the alternative as a typed overlay, materialize into an isolated capsule only when execution is required, and compare canonical evaluator output. Strong attribution and safety; needs care to avoid nested capsules.

### E. Chosen hybrid
Use D as the core. Route/evaluator/evidence-selection alternatives are simulated directly over the immutable epoch when execution adds no evidence. Implementation alternatives are materialized only in a single isolation owner. If a child evaluator is already isolation-owning, Gen12 delegates rather than stacking another Experiment Capsule. Git identity may be recorded as provenance but is not historical authority.

## Replay model

`ReplaySpec -> verify sealed base epoch -> verify route proof -> construct immutable replay view -> validate typed overlay -> execute/evaluate (optional, isolated) -> canonical baseline/alternative results -> semantic comparison -> attribution proof -> replay digest`.

A ReplaySpec binds:
- sealed `epoch_id` and epoch digest;
- Twin graph digest and all content-addressed base entries;
- original routing proof/digest and original decision;
- alternative type: `implementation_change`, `intent_routing`, `evaluator`, `authority_evidence_selection`, or `noop`;
- explicit overlay operations and allowed effect paths/authority classes;
- evaluator identity/configuration;
- isolation ownership/delegation policy;
- expected semantic result fields.

Replay identity excludes timestamps, transient run directories, and audit append offsets. Semantic result identity excludes execution timing and other nondeterministic telemetry.

## Safety invariants

1. A replay cannot mutate a sealed epoch or accepted/current state.
2. Every overlaid byte is content-addressed and declared in the ReplaySpec.
3. Undeclared mutations fail closed.
4. Route digest mismatch, missing blobs, epoch mismatch, historical leakage, or contradictory authority fail closed.
5. Mandatory safety-critical authority from the base route and the counterfactual route is monotonic: a replay may add authority but may not silently remove base mandatory safety authority.
6. `live_revalidate_only` or pinned-plus-live safety authority is never treated as historically frozen sufficient truth; required validation must be explicitly satisfied.
7. Historical replay can use only paths/blobs enumerated by the sealed epoch plus declared overlay bytes; current/future Tier-1 evidence is not imported.
8. An implementation execution has exactly one isolation owner. Gen12 will not blindly nest Experiment Capsules.
9. Replay output is advisory evidence only; no promotion, deployment, server mutation, or accepted-state write occurs from a replay result.

## Comparison / attribution

Baseline and alternative evaluator results are normalized into deterministic semantic projections. The comparison records changed fields and an attributable delta. Attribution passes only if: base epoch is identical; evaluator identity is identical except for evaluator replay; the only implementation/view changes are declared overlays; route/authority changes are explicit for routing/authority replays; and protected/current state remains unchanged.

## Scope exclusions

No autonomous promotion, production self-mutation, evaluator mutation nursery, broad capability consolidation, project onboarding, permanent MCP tool additions, host authority expansion, or Optiplex_MCP changes.
