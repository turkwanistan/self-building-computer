# Generation 8 — Context Compiler + Reproducible Experiment Capsule

Status: ACCEPTED (see `lab_generations/GEN8_RESULT.json`)

## Thesis
Compile the right context before reasoning, and run historical/self-evaluation experiments without mutating accepted operational state.

## Evidence motivating Gen8
Gen7’s Architectural Digital Twin achieved exact measured dependency/change-impact selection in its accepted benchmark and a 99.66% context-proxy reduction, making deterministic task-specific context compilation credible. Gen7 also exposed two concrete isolation failures: the retained Gen5 benchmark mutated populated Forge reuse state, while retained Gen4 lifecycle evaluation reached the absolute `/etc/optiplex-lab/build.json` path despite cloned registries.

## Architectures considered

### A. Deterministic Twin compiler + filesystem/service capsule — CHOSEN
- Context Compiler is a guest-local CLI/library over the Gen7 Twin, causal spine, read-only memory/regression state, and exact authoritative source excerpts.
- It classifies task intent, resolves a small set of authoritative owners, expands only evidence-backed dependency/impact paths, attaches causal/memory/regression evidence when applicable, and emits explicit inclusion/omission rationale.
- Evidence tiers are deterministic: Tier 0 authority/current operational invariants; Tier 1 directly affected authority/required validations; Tier 2 causal/memory/supporting dependencies; Tier 3 background candidates.
- Tier 0 and required Tier 1 cannot be budget-pruned. If they exceed the requested budget, the compiler expands the effective budget or fails closed.
- Experiment Capsule uses a private mount/PID namespace plus copy-on-write OverlayFS views of the real accepted `/opt/optiplex-lab`, `/etc/optiplex-lab`, `/etc/systemd/system`, `/var/lib/optiplex-lab`, and `/root` trees. `/tmp` and `/run` are private. System service-manager entry points are namespace-local wrappers, preventing lifecycle experiments from reaching the accepted guest systemd service while preserving the behavior required by retained tests.
- Accepted-state protected manifests are computed outside the child namespace immediately before and after each experiment.

Why chosen: builds directly on Gen7’s measured graph precision, stays deterministic/rebuildable, preserves authoritative source precedence, and directly closes both observed Gen7 state-leak classes without a permanent MCP expansion.

### B. Twin SQLite query planner + hand-authored context templates
A fixed template per task kind could query Twin SQLite and fill predefined sections. It is simpler initially, but templates become a second policy source and tend to include whole categories rather than evidence-backed paths. Rejected as the primary compiler; small task-kind policies remain acceptable only as deterministic selection rules with inspectable rationale.

### C. Generic embedding/RAG index + generic container sandbox
Embeddings could improve fuzzy retrieval and a broad container platform could isolate arbitrary descendants. Deferred. Gen7 already measured exact graph selection, while embedding ranking would add nondeterminism and another stale index. A large general sandbox would exceed the Gen8 requirement; the capsule should be the smallest reusable boundary that contains real retained Gen4/Gen5 behavior.

## Context Compiler packet
Stable JSON schema includes compiler/schema identity; packet ID/digest; task text/hash/normalized kind; operational and Twin identity; input evidence digests; selected evidence with tier, authority, provenance/hash/freshness, observed/inferred status, selection reason, dependency path and exact source excerpts/structured facts; memory; causal evidence; regressions; validations; recovery/security requirements; contradictions; uncertainties; omitted candidates/reasons; requested/effective byte budget, bytes used, token estimate and expansion state.

### Selection algorithm
1. Normalize task and classify into architecture/explanation, code-change planning, debugging, evaluation, or lifecycle/recovery.
2. Resolve explicit refs and score Twin nodes deterministically.
3. Select bounded authoritative seed owners.
4. Expand only evidence-backed dependency/impact relations to bounded depth.
5. Attach explicit Gen7 impact-derived validations and recovery implications.
6. Read procedural-memory and regression registries without updating retrieval/replay counters.
7. Query causal history only for debugging/lifecycle tasks and preserve explicit causal/lineage strength.
8. Add Tier 0 guest authority/security and live accepted identity unconditionally.
9. Check freshness and contradictory authoritative claims; fail closed or use controlled broad fallback when critical evidence is stale/missing/contradictory.
10. Budget Tier 0/required Tier 1 first; prune Tier 3 then Tier 2; never silently truncate critical evidence.
11. Emit deterministic inclusion/omission rationale and packet digest.

Authoritative source/hash evidence outranks Twin-derived summaries. Procedural memory is advisory and always retains its authoritative capability/evaluator references. Inferred graph relations remain labeled and may add validation but never remove hard gates.

## Experiment Capsule
The capsule is an experiment boundary, not a production sandbox platform.

### Filesystem boundary
The parent captures bind-mounted lower views of accepted directories, remounts those lower views read-only, then overlays private writable upper/work directories onto the original absolute paths inside an `unshare --mount --pid --fork` child. Historical absolute paths therefore resolve to capsule-local COW state. Selected mutable namespaces can additionally be replaced with empty tmpfs roots (required for Gen5 Forge/regression initial conditions).

### Service boundary
A private `/run` hides accepted systemd/control sockets. Namespace-local `systemctl`/`systemd-run` wrappers are bind-mounted over the standard binaries. They expose a synthetic MCP PID, simulate a scheduled restart, and reproduce the accepted launcher’s fast-crash LKG restoration semantics only against capsule-local server/LKG/build files. They never invoke the accepted guest service manager.

### Evidence
Each run records a version-pinned recipe manifest, authoritative input hashes, wrapper hash, protected pre/post manifests, child exit/result, captured artifacts, upper-layer mutation inventory/hashes, recipe digest, result digest and forbidden outer mutation verdict. The outer accepted trace/provenance trees are protected during the inner run; exported experiment evidence lives outside the protected paths.

Final invariant: retained experiments may mutate the capsule; they may not mutate accepted operational state.

## Acceptance strategy
Freeze independently authored gold critical-evidence sets before evaluating compiler output. Benchmark 12–18 representative/held-out cases for critical recall/precision, unrelated context, dependencies, regressions, causal history, memory, authority/recovery retention, stale/contradiction handling, budget behavior, deterministic packets, compiled-context task correctness, latency/size, broad and practical baseline reduction, self-use, capsule reproducibility/isolation, forbidden-mutation detection, Gen4/Gen5 leakage containment, permanent 10-tool surface and VM containment.

Critical-evidence false negatives must be zero. Small packet size alone is not acceptance evidence.

No `server.py` modification is required. Canonical capability generation advances to Gen8 while operational `lab_status` intentionally remains accepted Gen6 server identity.
