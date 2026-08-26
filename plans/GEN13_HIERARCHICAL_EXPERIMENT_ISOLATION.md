# Generation 13 — Hierarchical Experiment Isolation + Nested Evaluation Delegation

## Thesis

**Compose experiments without losing isolation.** Gen13 eliminates the Gen12 nested-isolation seam without introducing recursive OverlayFS. One top-level Gen8 Experiment Capsule owns each mutable state boundary; nested evaluators/replays participate through explicit, content-addressed delegation contexts and sequential mutation reconciliation inside that owner.

## Entry evidence

- Operational Lab remains `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server == LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, 10 permanent MCP tools.
- Accepted Gen12: `gen12-counterfactual-replay-r1-5a0fa7b8e62f`; replay SHA `5a0fa7b8e62f3bbcd1e7eadacae1cc6ca00380a5c930fef3a507753003ca8781`; benchmark 30/30.
- Entry Twin was refreshed because ordinary trace evidence was newer than the Gen12 checkpoint: 198 nodes / 300 edges / 102 inputs, graph `ea3dfa823196fb7f06b20747724cde42a9b4c65e29e0397fbe7bf97e7b54f9b4`, causal digest `b7c6f3492aae78403f85f4d9e2f37fbc59793ce5b7b50fc4c7607a48758d2683`, freshness PASS.
- Frozen Optiplex_MCP remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.
- Git entry point: `f6aea4d6a1b20779093c2e353d96f5384f8c00d2`; pre-existing `ideas.md` modification and `host/check_chatgpt_ui_staleness.sh` remain unrelated and must be preserved.

## Architectures considered

### A. Recursively nested OverlayFS / Capsules
Each child creates another mount/PID namespace and overlays the same paths again. Physical separation is intuitive, but ownership becomes ambiguous, upper-layer attribution is difficult, service wrappers stack, cleanup becomes multi-owner, and the Gen12 failure mode returns in more complicated form. **Rejected for same-boundary composition.** Independent Capsules remain valid only for truly disjoint experiments launched outside another owner.

### B. Single top-level Capsule; children run directly with no protocol
This preserves one owner and is simple, but child authority is implicit, writes are not attributable, and a caller cannot prove which evaluator caused a mutation. **Insufficient.**

### C. Parent-owned isolation context with delegated child scopes/tokens
The parent owns the Capsule. Children receive machine-readable contexts containing lineage, bounded mutation paths, authority/evidence constraints, evaluator identity, result policy, and the same physical owner binding. Child authority is a strict subset of parent authority. Actual Capsule upper-layer mutations are sampled before/after each sequential child. **Chosen semantic protocol.**

### D. Transaction/workspace abstraction independent of OverlayFS
Expose generic `root experiment -> delegated child -> result` APIs while treating OverlayFS as one backend. This is useful for later onboarding/nursery work, but a full backend framework would be premature. **Chosen only as a thin interface:** semantic contexts do not encode OverlayFS details, while the Gen13 implementation uses the existing Gen8 Capsule backend.

### E. Dedicated nested VM/process sandbox per child
Stronger physical isolation but materially larger complexity and resource cost; unnecessary for the demonstrated seam because the outer disposable VM is already the security boundary and accepted-state protection is supplied by the parent Capsule. **Deferred.**

## Chosen architecture

`root request -> Gen8 Capsule (only physical owner) -> Gen13 root context -> delegated child context -> direct child process in same Capsule namespace -> before/after upper-layer mutation evidence -> scope/authority validation -> child result -> parent reconciliation -> Capsule accepted-state comparison -> cleanup`

The hierarchy is **sequential by contract** in Gen13. This makes mutation attribution deterministic: the change in the Capsule upper-layer inventory across one child execution is that child's observed mutation set. Concurrent siblings are deliberately unsupported.

### Context model

Every context carries concepts equivalent to:

- deterministic `context_id` and semantic digest;
- `root_context_id`, `parent_context_id`, depth and lineage;
- one physical `isolation_owner` and owner-run binding;
- mode: `owner`, `delegated`, or `read_only`;
- delegated exact/subtree mutation scope;
- authority classes, always subset-monotonic;
- evidence/input bindings and optional evaluator identity/version;
- cleanup responsibility and result-propagation policy;
- operational run binding separated from semantic identity.

Timestamps, random Capsule run IDs, PIDs, durations, and transient directories are excluded from semantic identity. The operational owner-run binding is checked for stale/replayed context detection but is not hashed into semantic result identity.

### Delegation contract

1. Root context may be created only inside an active Experiment Capsule and binds to that Capsule run ID.
2. Child requested mutation scope must be a subset of parent scope. Read-only means empty mutation scope.
3. Child authority must be a subset of parent authority. No delegation API can add authority.
4. Child evidence bindings may only equal or narrow the parent's bound inputs; incompatible rebinding fails closed.
5. Parent ID, root ID, lineage digest, context digest, and owner-run binding are validated before execution.
6. A delegated child must use the parent's physical isolation owner. Requests for an independent Capsule over the same boundary fail closed.
7. Grandchildren are supported sequentially under the same owner with the same subset rules; no extra OverlayFS layer is created.

### Mutation evidence and reconciliation

Gen13 reads the real Gen8 Capsule upper-layer inventory immediately before and after each child. New/changed/whiteout/symlink/special records are attributed to that child. A child-reported mutation list is advisory only; observed inventory wins. Writes outside delegated scope make the child result invalid even when the process exits zero. Symlink/path traversal is checked both syntactically and by the resulting observed full path.

Parent/root reconciliation compares final Capsule mutation inventory with the union of observed child mutations plus explicitly declared parent/output paths. Undeclared residual mutations fail the root experiment. This prevents a child from lying by emitting a clean result while writing elsewhere.

### Failure and cleanup semantics

- nonzero exit: child fails; observed mutations remain only in experimental overlay; parent records them and may continue only if result policy explicitly allows it;
- timeout: terminate child process group, reap remaining newly-created descendants, mark failure;
- undelegated authority/scope, forged/mismatched/stale context, evidence mismatch, or ambiguous owner: reject before execution;
- malformed child result: fail child, retain observed mutation evidence;
- service/systemctl attempt: existing Gen8 virtualized service manager remains in force; unexpected descendants are detected/terminated;
- crash after mutation: before/after inventory still attributes the mutation and failure;
- accepted-state mutation: parent Capsule remains the physical COW boundary and outer protected-manifest comparison is authoritative;
- cleanup failure: root experiment fails acceptance even if evaluator output was otherwise valid.

## Gen12 integration

Standalone Gen12 replay remains unchanged and owns one Capsule for implementation replay. For `alternative.isolation_owner == "child"`, Gen12 may now execute only when a valid Gen13 delegated context is present, bound to the current Capsule owner, and its delegated paths include every declared overlay path plus the evaluator result path. It then executes the implementation evaluator directly through Gen13 delegated execution rather than creating another Capsule. Without a valid compatible delegation context, the existing `ISOLATION_DELEGATION_UNSUPPORTED_FOR_MUTATION` fail-closed behavior remains. `isolation_owner == "replay"` from inside an existing Capsule remains ambiguous and is rejected.

Historical epoch, routing, authority-monotonicity, forbidden accepted-path, and evidence-leakage checks are unchanged.

## Compatibility

- Gen8 `run_capsule()` call shape and semantics remain compatible. Gen13 needs only additional owner-run environment metadata; old callers do not need to understand hierarchy contexts.
- Gen12 standalone replay path remains its existing single-Capsule path.
- Gen10/Gen11 owned isolation rules remain untouched.
- Permanent MCP surface remains 10 tools; all Gen13 machinery is guest-local Python behind existing generic tools.

## Scope exclusions

No Project Onboarding, evaluator mutation nursery, autonomous promotion, production self-mutation, permanent MCP tools, host authority, recursive MCP probe, concurrent sibling transactions, or nested virtualization is added in Gen13.

## Acceptance

The frozen `lab_generations/GEN13_GOLD.json` is written before the primary engine implementation. Required benchmark pass is 100%; unsafe authority expansion accepted 0; forbidden accepted-state mutations 0; ambiguous isolation owners accepted 0; historical leakage introduced 0; permanent MCP tool growth 0. Gen2-Gen12 retained regressions, self-use, protected-state comparison, containment, final Twin freshness, canonical tests, syntax/JSON/secret/diff gates are mandatory.
