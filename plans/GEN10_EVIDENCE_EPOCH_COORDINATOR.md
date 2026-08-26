# Generation 10 — Evidence Epoch / Snapshot Freshness Coordinator

## Thesis

**Reason Over One Coherent Evidence Epoch.** Generation 10 adds a deterministic Evidence Epoch / Snapshot Freshness Coordinator around the accepted Gen8 Context Compiler and Gen9 Context Necessity Optimizer. It prevents a compile → minimize → evaluate transaction from mixing evidence states merely because its evaluator generates new Tier-1 evidence while running. It does not weaken stale/missing/contradictory fail-closed behavior and does not change the permanent MCP surface.

## Starting authority

- Canonical capability: `gen9-context-necessity-r1`, build `gen9-context-necessity-r1-6be10d7af323`.
- Optimizer SHA256: `6be10d7af3238fb59a2cf8f5d9a858de4b3957a9681634bbe4ef78e33402d299`.
- Gen9 benchmark source SHA256: `03fe8a7845d08574f211f5cada42578c4be53912a81c0797554c5117a5b19152`.
- Frozen Gen9 gold SHA256: `dc755fd02e1dc44c1aed1cdf9a3f1745d6049178472a0165cbdf40867f5ae637`.
- Final Gen9 Twin: 179 nodes / 259 edges / 89 inputs, graph digest `4d983ad01376a04a54dc834d0dc46ee4d606293fca572f3d8ead45e81e65c45f`, snapshot SHA256 `2c05c6282070c74bee204e837d0b8d6a03677ab404a407318c8a4d27594484be`.
- Operational MCP remains accepted Gen6, exactly 10 tools, live server == LKG == `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`.
- `Optiplex_MCP` remains frozen at release `frontend-a5c1c5be8b22`, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

## Forensic Gen9 failure reconstruction

Gen9 finalization compiled/minimized correctly against the then-current Twin. The Gen9 benchmark subsequently rewrote authoritative Tier-1 benchmark artifacts under `/var/lib/optiplex-lab/benchmarks/`. Those files were hash-mode Twin inputs. Until the Twin was rebuilt, its nodes still carried the pre-run hashes. A later compiler freshness check compared the Twin's expected hash to newer live bytes, classified required evidence as stale, set `fail_closed`, and Gen9 correctly blocked minimization. This was a safety success but a transaction-consistency failure: the same logical evaluation transaction had no immutable input epoch, so post-compile expected output was indistinguishable from an unsafe out-of-band mutation.

The safety rule remains correct. Gen10 changes the transaction boundary, not the meaning of stale evidence.

## Architectures considered

### A. Immutable Evidence Epoch Manifest
Capture path, size, digest, freshness mode, Twin graph digest, compiler/optimizer/evaluator identity, authority class, and expected-output policy in a canonical sealed manifest. Strong provenance and low conceptual complexity, but a manifest alone cannot reproduce bytes after mutable evidence changes.

### B. Copy-on-write / content-addressed evidence snapshot
Store immutable blobs by SHA256 and materialize an epoch view. Strong reproducibility and survives later mutation; costs bounded storage/I/O and needs reference-safe cleanup. Useful for hash-mode inputs and append-only prefixes.

### C. Transactional Twin + Context snapshot
Bind Twin snapshot, compiler source, optimizer source, evaluator source, selected packet, protected-state digest, and output policy to one transaction/epoch digest. Prevents mixed-epoch packets but still needs immutable content for mutable paths.

### D. Optimistic validation
Compile current evidence and re-check digests before evaluation/finalize. Cheap when nothing changes, but by itself recreates Gen9's avoidable failure when the transaction legitimately produces evidence.

### E. Experiment-Capsule-backed reasoning epoch
Use the accepted Gen8 Experiment Capsule to isolate mutation-producing evaluators, crash tests, historical views, and destructive checks. Excellent safety substrate, but using a full capsule as the only read mechanism would be heavier than needed for ordinary compile/minimize.

### F. Chosen hybrid
Use A+B+C for the immutable reasoning view, D for live-only authorities, and E for mutation-producing evaluator execution and protected-state tests. Newly generated evidence is never injected into a sealed epoch; it is classified at finalize and becomes input to a subsequent epoch after deterministic refresh/rebuild.

## Evidence classes and authority semantics

Every manifest entry has one of these policies:

1. `pinned_hash`: immutable content-addressed bytes used by compiler/optimizer/evaluator view. Unexpected live change is a finalize failure unless path is a declared expected output.
2. `append_only_prefix`: epoch stores the exact starting prefix. Prefix mutation/shrink fails closed; prefix-preserving growth is classified as next-epoch evidence.
3. `pinned_plus_live_revalidate`: reasoning uses the materialized starting bytes, but safety acceptance also requires live digest/identity revalidation at compile/evaluate/finalize boundaries. Build/server/LKG and equivalent recovery/security authorities use this class.
4. `live_revalidate_only`: authority cannot be frozen as sufficient truth. It requires a deterministic live verifier; the coordinator refuses to seal if no verifier exists. This is used for authorities whose semantics explicitly demand current-state validation.

Epoch pinning never means stale evidence is acceptable. A sealed epoch is allowed only when its starting evidence is coherent and every required blob/provenance record verifies.

## Epoch contents

A sealed epoch binds:

- exact Twin snapshot bytes and graph digest;
- Twin input file bytes/prefixes and freshness modes;
- causal index, build state, memory/regression registries, workflow `CURRENT` markers needed by Gen9, source/evaluator/benchmark versions;
- Context Compiler, Necessity Optimizer, Evidence Epoch Coordinator and selected evaluator source hashes;
- protected-state audit manifest digest recorded alongside the epoch; it is deliberately excluded from canonical epoch identity because observation can append audit telemetry. Safety-critical protected authorities are separately represented as pinned/live-revalidated epoch inputs;
- expected-output paths and mutation classifiers;
- historical/version scope, if any;
- canonical manifest digest / epoch ID.

The materialized view mirrors original paths beneath the epoch directory. Compiler/optimizer modules are loaded from that view. Snapshot node `source_path` values are redirected to the view while stable node IDs/identities remain unchanged. Gen9 lifecycle validation source inspection is resolved through the same epoch view. This avoids mixed live reads without modifying the accepted Gen8/Gen9 source modules.

## Lifecycle

### `begin`
Acquire a short coordinator lock; inspect the current Twin and all required starting inputs; reject missing/stale/contradictory critical evidence; capture protected-state digest; create blobs and a temporary materialized view; validate live-required authorities; write a draft manifest under an incomplete staging directory.

### `seal`
Verify every referenced blob/view file, calculate deterministic canonical manifest digest, atomically publish the sealed epoch directory/manifest, and write a `SEALED` marker. Timestamps and latency are excluded from the epoch digest. Identical evidence/policies produce the same digest.

### `compile_minimize`
Load Gen8 compiler and Gen9 optimizer from the epoch view, use the epoch Twin, redirect compiler state paths to the materialized view, and ensure the raw and minimized packet both carry the exact epoch ID/digest. Any packet/epoch mismatch fails closed.

### `verify_live`
Revalidate live-only and `pinned_plus_live_revalidate` authorities. Verify pinned content still exists in the epoch store. For append-only evidence, verify the stored prefix. This function never silently rebases an epoch.

### mutation-producing evaluation
Run only inside an Experiment Capsule for Gen10 benchmark/self-use destructive cases. Before evaluator execution, overwrite the capsule overlay's declared pinned input paths with their epoch-view bytes. Expected output paths may change inside the transaction; forbidden/protected mutations remain isolated.

### `finalize`
Compare live/capsule-visible post-state with the sealed start manifest. Classify changes as: unchanged; expected transaction output queued for next epoch; append-only prefix-preserving growth queued for next epoch; or unsafe/unclassified mutation (fail closed). A finalized epoch never changes its input manifest.

### next epoch / refresh
If a finalized epoch produced expected evidence, the next-epoch path rebuilds derived Twin/causal state only after validating the classified changes. A new `begin` then captures the refreshed evidence. Unrelated stale/missing/contradictory evidence is never auto-rebased.

### crash recovery
Only a directory with a valid manifest digest and `SEALED` marker is authoritative. Incomplete `.creating-*` directories are non-authoritative and recoverable/cleanable. Finalization is atomic and idempotent.

## Concurrency

Epoch creation/finalization uses a short file lock, but sealed epochs are immutable and can be read concurrently. Every packet names one explicit epoch digest. The coordinator rejects packet/epoch mismatches; there is no mutable implicit "current packet" pointer, preventing mixed-epoch reads.

## Historical/version-pinned integration

Historical evidence views are explicit epoch sources, never synthesized by rewriting gold. Gen7 remains a capsule-local Gen7-era view hiding Gen8/Gen9/Gen10 additions. A historical epoch records its source-view provenance and cannot inherit future-valid evidence.

## Storage and garbage collection

Blobs are SHA256-addressed and deduplicated. Gen10 does not implement broad GC. A future GC may remove only blobs unreferenced by sealed/finalized manifests after deterministic reference enumeration. No in-use or historical evidence is deleted in Gen10.

## Scope exclusions

No permanent MCP tool, no `server.py` change, no generic transaction database, no distributed snapshot protocol, no Counterfactual Replay product, no broad mutation nursery, no autonomous reaction system, and no Gen11 capability.

## Frozen success criteria

The exact machine-readable thresholds are frozen in `lab_generations/GEN10_GOLD.json` before `evidence_epoch.py` or `benchmark_gen10.py` exists. Required recall remains 1.0; critical FN remains 0; necessity-aware precision must remain >=0.98; Gen9-vs-Gen8 context payload reduction must remain >=40%; expected self-produced evidence must not invalidate the current epoch; the next epoch must observe it; every modeled unsafe authority/source mutation must still fail closed; deterministic epoch/output digests, crash safety, historical isolation, protected-state isolation, and retained Gen2–Gen9 regressions are mandatory.
