# Generation 15 — Project Onboarding + Domain Capability Expansion Pilot

## Thesis

**Prove the platform on a real project.** Gen15 turns the Gen7–Gen14 reasoning/evaluation substrate outward: take an unfamiliar external project, build a deterministic evidence-backed project model, compile only the context needed for real tasks, discover domain capability gaps, forge useful guest-local capabilities, evaluate them independently, and reuse them without growing the permanent MCP tool surface.

## Entry boundary

- Object under evolution: `Optiplex_Lab + isolated mcp-lab VM`.
- `Optiplex_MCP` is frozen and is used only as the mediated canonical-repository/control interface.
- Operational Lab must remain accepted Gen6: `gen6-experience-memory-r1-dc0d2cb41595`, server == LKG SHA `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 tools.
- Accepted capability substrate entering Gen15 is Gen14 evaluator mutation nursery build `gen14-evaluator-mutation-nursery-r1-fe5f9d8fbb3c`.
- Pre-existing canonical working-tree changes `ideas.md` and `host/check_chatgpt_ui_staleness.sh` are unrelated and must remain untouched.

## Frozen acceptance rule

`lab_generations/GEN15_GOLD.json` is created before the onboarding engine and is immutable for the rest of Gen15. Its SHA256 is bound into the guest benchmark and final result. Any mismatch is a hard failure.

## Pilot selection protocol

Inspect actual sibling projects and score qualitatively on: material domain difference from self-building-computer; real data/runtime behavior; deterministic tests/fixtures; meaningful capability gaps; bounded experimentability; ability to stay read-only in the pilot checkout. Selection must be evidence-based and recorded. The pilot project itself is not modified by Gen15; a bounded evidence bundle is copied into the isolated guest.

## Generic onboarding architecture

Gen15 adds a generic `project_onboarding.py` layer, not a pilot-named script. It must:

1. resolve and validate a declared project root, refusing ambiguity, nested/conflicting identities and path/symlink escape;
2. inventory content deterministically while excluding configured generated/cache/private material from authority by default;
3. infer languages/frameworks, entrypoints, tests/build commands, dependency manifests, data/artifact roots, external interfaces and containment constraints;
4. bind every authoritative input by SHA256 and produce a content-addressed onboarding manifest;
5. build a namespaced project model/Twin composition separate from the Lab self-model;
6. compile deterministic task-oriented project context with required-evidence recall and explicit stale/missing behavior;
7. run capability-gap classification against available generic/guest-local capabilities;
8. register/invoke domain capabilities through existing Capability Forge/workflow infrastructure rather than MCP tools.

## Pilot direction

The pilot is selected only after inspecting real projects. Current evidence favors a media/audio project because it is maximally different from the self-building-computer domain while providing deterministic fixtures, runtime outputs and rich data relationships, but this document does not hard-code the final selection.

## Domain capability requirements

At least two non-trivial capabilities must be built guest-locally with explicit contracts, deterministic content identity, positive/negative/adversarial fixtures and independent evaluation. They must be useful on more than one representative pilot task. At least one new evaluator must be challenged through the accepted Gen14 mutation nursery and have zero dangerous survivors for the designated mutation set.

## Self-use and baseline

The onboarding pipeline must onboard the selected pilot itself. Record discovery, authority choices, context selection, gap analysis, capability construction, evaluation and reuse. Compare against a reasonable raw-inspection baseline using context bytes and raw inspection interactions; also record qualitative defect-detection/task-success improvements where measurable.

## Generalization

A second tiny synthetic project must pass the generic discovery/onboarding path with a distinct language/dependency shape. No pilot-specific name or path may be required by the generic engine.

## Fail-closed classes

Reject or explicitly surface: fake root; nested/conflicting root; stale manifest; generated file claiming authority; surprising project instructions; executable outside authority; symlink/path escape; capability write outside allowed workspace; evaluator lineage mismatch; contaminated/stale fixture; skipped benchmark checks claiming PASS; disabled critical evaluator check; malformed capability result; timeout/crash; missing critical dependency.

## Retained regression strategy

Run Gen2–Gen14 with established version-pinned/mutation-safe strategies. Do not casually nest benchmarks that already own Capsule isolation. Gen13 remains 37/37. Gen14 remains 52/52 with 100% dangerous mutation kill rate.

## Acceptance

Frozen gold, onboarding benchmark, real pilot onboarding, two domain capability evaluations, Gen14 mutation challenge, self-use, generalization, adversarial suite, Gen2–Gen14 regressions, protected-state comparison, containment, unchanged operational Gen6 identity/10 tools, fresh Twin, canonical tests, mutation-free syntax checks, JSON/JSONL validation, secret scan, `git diff --check`, and debris cleanup must all pass before Gen15 can be marked accepted.
