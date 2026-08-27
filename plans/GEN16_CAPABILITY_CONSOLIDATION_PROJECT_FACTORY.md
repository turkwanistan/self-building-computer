# Generation 16 — Capability Consolidation + Reusable Project Capability Packs

## Thesis

**Turn the workshop into a reusable project factory.** Gen16 consolidates the Gen15 real-project onboarding path into one reusable, content-addressed project analysis path plus a standard Project Capability Pack convention. It must reduce one-off project glue and operator choreography without weakening authority, provenance, isolation, context recall, evaluator coverage, or explicit Forge promotion gates.

This is intended to be the final primarily platform-focused generation before project development becomes the main driver of evolution. Gen17 remains the Terrarium project-building pilot and is explicitly out of scope for Gen16.

## Entry boundary

- Object under evolution: `Optiplex_Lab + isolated mcp-lab VM`.
- Frozen `Optiplex_MCP` is control/transport only and must not be modified.
- Operational Lab remains accepted Gen6: `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG SHA `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 permanent MCP tools.
- Accepted platform capability entering Gen16 is Gen15 build `gen15-project-onboarding-domain-capability-r1-50f8653f0623`, benchmark 40/40, frozen Gen15 gold `718d297ae608d53bad0b81b576f536df05c737c165c2dc3a1c29851b989440eb`.
- Gen15 promoted capability identities remain authoritative: `musical-telemetry-profiler-r1` = `4dd178d667af77f5c50e846dec419dac3206040491017ca591a3504fa2b455c3`; `songboss-causality-auditor-r1` = `7a8ffc0c3facad20c5714834d1d4e0d0d106f663ae4ec07f8106c21c3d951edf`.
- Preserve unrelated working-tree work: `ideas.md` and `host/check_chatgpt_ui_staleness.sh`.

## Frozen acceptance

`lab_generations/GEN16_GOLD.json` was written before primary implementation and is immutable for Gen16. Frozen SHA256: `2755cc4fa09afbe653dbc6961a4bab314a052483fc9d8d62d3b71bf83db4b80a`.

Frozen Gen15 consolidation baseline:

- `project_onboarding.py`: 17,181 bytes / 254 lines.
- `project_context_bridge.py`: 4,225 bytes / 92 lines.
- Song City adapter: 3,825 bytes.
- independent domain evaluator: 5,972 bytes.
- two capability contracts: 15,746 bytes.
- estimated Gen15 operator choreography for a new project: 8 distinct steps/artifacts before the generic path, Forge path, and independent-evaluation path are connected.

Gen16 does not need to reduce total platform source bytes. It must reduce **project-specific glue and parallel operator paths**. The bridge should become only a compatibility shim; project analysis should be one API/CLI path; a new project should use one standard pack format rather than inventing a new Gen15 directory convention.

## Architecture decision

### 1. Evolve the existing onboarding engine instead of adding a new orchestrator

`lab_mcp/project_onboarding.py` remains the generic project-building entry point and gains Gen16 pack-aware functions. Existing Gen15 APIs and schemas remain supported for retained regression compatibility.

The engine will own the reusable path:

`pack -> deterministic transport/discovery -> authority/evidence manifest -> project Twin -> routed/minimized task context -> platform context composition -> actionable capability classification -> explicit Forge/evaluation plan`

`project_context_bridge.py` will delegate to the canonical implementation in `project_onboarding.py` and remain only as a compatibility entry point for Gen15 callers.

### 2. Project Capability Pack v1

Schema: `gen16.project-capability-pack.v1`.

A pack is a deterministic declarative object with:

- pack identity/version and project adapter/discovery rules;
- authority hierarchy, task profiles, containment constraints, and project runtime metadata;
- capability requirements with purpose, applicability, utility, authority requirements, runtime dependencies, provider type, and expected Forge identity where known;
- optional independent evaluator references, fixture/benchmark references, provenance, and self-use evidence references;
- explicit project-building readiness declarations where relevant.

Referenced local resources must use safe relative paths and may carry expected SHA256 values. Pack verification fails closed on schema mismatch, digest mismatch, duplicate capability IDs, unsafe paths, missing resources, or expected-resource hash mismatch.

The pack itself is content-addressed. Capability implementations are **not copied into another Gen16 source tree** merely to satisfy packaging. Promoted Forge object hashes and existing capability contracts remain the authority. This prevents packaging from recreating the Gen15 duplication it is intended to remove.

### 3. Actionable capability discovery

For each pack capability requirement, the generic classifier must return exactly one of:

- `AVAILABLE` — an exact acceptable provider is present and, for Forge-backed capability, promoted with matching content identity when pinned;
- `WEAK_NEEDS_SPECIALIZATION` — a related provider exists but is not sufficient to claim exact availability;
- `MISSING_VALUABLE` — no sufficient provider exists and utility/necessity makes forging or specialization worthwhile;
- `UNNECESSARY` — the project/task does not justify capability work.

Missing/weak results must contain a deterministic Forge plan: desired name, purpose, applicability, authority/runtime constraints, and an explicit sequence of gates (`search/open_gap -> author -> seal -> evaluate -> real-task evidence -> govern`). The plan must state that promotion is not automatic.

### 4. Preserve existing Capability Forge authority

Gen16 must not invent a second capability registry, lifecycle, evaluator protocol, or promotion governor. Packs point at the existing Forge substrate. Exact promoted content hashes remain the strongest capability identity. Pack discovery may recommend opening a gap but may not install/promote autonomously.

### 5. Project-building readiness

Gen16 will assess generic support for the upcoming class of real projects, especially:

- persistent guest project services;
- bounded long-running experiments;
- deterministic simulation/replay testing;
- browser/render inspection and visual evidence capture;
- SQLite/event-ledger inspection;
- frontend/backend synchronization tests;
- project-specific behavioral evaluators.

Implementation is evidence-driven. Existing substrate already provides arbitrary guest systemd service control, durable bounded jobs, Gen12 replay, Gen13 isolation, mediated Playwright browser inspection, generic shell/Python/SQLite access, and Gen14 evaluator mutation. Gen16 should add reusable code only where a concrete generic seam is missing; it should not create Terrarium-specific service/simulation/render code.

## Song City compatibility proof

Create a Gen16 Song City pack that embeds the same Gen15 adapter semantics and points at the two already-promoted Forge capability hashes and independent evaluator. The consolidated path must reproduce the Gen15 project manifest semantics, required-evidence recall 1.0, zero critical false negatives, and both domain capability availability/evaluation outcomes.

The original Gen15 adapter/artifacts remain for historical retained benchmarks; the Gen16 pack is the new reusable convention.

## Generalization proof

Use the same pack schema and analysis API for the existing distinct tiny Node/JavaScript project shape. No Song City path/name branch may exist in generic code. Generalization must show deterministic pack identity, onboarding identity, task-context recall 1.0, and capability classification using the same machinery.

## Self-use

Use the Gen16 pack/consolidated path against the installed Gen15 onboarding implementation itself. The self-use project/task should include the onboarding engine, compatibility bridge, Capability Forge, Gen13 hierarchical experiment implementation, Gen14 mutation nursery, and Gen15 benchmark/evaluator evidence.

Self-use must report at least:

- bridge duplication removed or reduced to a <=25-line compatibility shim;
- one canonical digest/compose implementation rather than parallel bridge helpers;
- project adapter/capability requirement structure represented through the pack schema;
- actionable capability discovery wired to existing Forge identities;
- any stale/resource/evaluator coupling defect found and its resolution.

## Evaluator hardening

Treat the capability-classification rule that distinguishes promoted exact availability from weaker candidates as critical. Mark it explicitly for Gen14 mutation testing. A dangerous mutation that treats non-promoted/weak providers as `AVAILABLE` must be killed by an independent oracle, with dangerous mutation kill rate 1.0 and zero dangerous survivors.

Do not remove old checks merely because the consolidated happy path passes. Any claimed redundant check must be demonstrated redundant experimentally before removal.

## Measurable consolidation

Acceptance needs measurable evidence, not only renamed files. Target measurements:

- compatibility bridge <=25 lines vs 92-line Gen15 bridge;
- one canonical project-analysis path vs separate manual onboard/context/bridge/gap wiring;
- <=4 operator-level steps for pack validate/analyze/Forge follow-through vs frozen baseline 8;
- no duplicate capability source copy introduced by the pack;
- Song City required-evidence recall and evaluator detection power unchanged;
- Gen15 40/40 retained unchanged.

## Adversarial classes

At minimum challenge all frozen Gen16 classes in `GEN16_GOLD.json`: pack schema/digest tamper, duplicate capability IDs, resource path escape/hash mismatch, unpromoted provider falsely claimed available, weak provider falsely claimed available, missing valuable requirement without Forge plan, unnecessary requirement causing gap creation, stale project model, missing required evidence, bridge/task binding mismatch, disabled critical classifier check, evaluator reference mismatch, and undeclared project mutation under Gen13 isolation.

## Retained regressions

Run the full accepted Gen2–Gen15 matrix using each generation's established mutation-safe/version-pinned strategy. Exact requirements include Gen13 37/37, Gen14 52/52 with dangerous mutation kill rate 1.0 and no dangerous survivors, and Gen15 40/40.

## Final acceptance and handoff

Before acceptance:

- Gen16 benchmark and all Gen16 adversarial/generalization/self-use evidence pass frozen gold;
- Song City compatibility and both promoted Gen15 capabilities pass;
- retained Gen2–Gen15 matrix passes;
- operational Gen6 server == LKG, recovery ACCEPTED, 10 tools;
- protected state has zero forbidden changes;
- final Architectural Twin has zero issues;
- canonical repo tests pass;
- mutation-free Python syntax check passes;
- JSON/JSONL validation passes;
- secret/credential scan passes;
- `git diff --check` passes;
- temporary Capsule/nursery/Gen16 debris is zero;
- unrelated working-tree work remains untouched.

Write `GEN16_RESULT.json`, `GEN17_PROPOSALS.json`, update `STATUS.md`, `NEXT_SESSION.md`, `state/current.json`, and append one concise `history/events.jsonl` acceptance event.

Preferred Gen17 proposal remains **Terrarium — First Full Project-Building Pilot** with initial scope: Phase 0 contracts/skeleton; Phase 1 visibly alive autonomous creature; Phase 2 persistent objects; fixed 800x480 reference renderer; persistent host-owned life; deterministic replay. Gen16 must not implement Terrarium.
