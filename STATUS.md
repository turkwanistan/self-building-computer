# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN16_CAPABILITY_CONSOLIDATION`

Generation 16 is **ACCEPTED**. It consolidated Gen15's successful real-project onboarding/domain-capability path into a reusable project factory without growing the permanent MCP surface or weakening authority, provenance, isolation, Forge governance, or evaluator coverage.

## Accepted Gen16 capability
- generation: `gen16-capability-consolidation-r1`
- build: `gen16-capability-consolidation-r1-33dad6262d3a`
- onboarding/project-factory engine SHA256: `33dad6262d3a2071c4198b4d0e337076f0c8d52c9f9015dab6b052054ff458c0`
- project-context compatibility shim SHA256: `8f326f12edd6f96dafec75d271f98ff888f5e8a32b08dc42034522112649aec2`
- Gen16 benchmark source SHA256: `19e61cedde431c17571337324dc7de01319b767fd16826f1f65a98a898207317`
- frozen Gen16 gold SHA256: `2755cc4fa09afbe653dbc6961a4bab314a052483fc9d8d62d3b71bf83db4b80a`
- operational `server.py`: **unchanged**; permanent MCP tools: **10**

Operational Lab intentionally remains accepted Gen6: `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, service active.

## Project Capability Packs / consolidation
- deterministic pack schema: `gen16.project-capability-pack.v1`
- canonical reusable path: project/transport -> pack validation -> content-addressed project manifest/Twin -> routed minimized task context -> capability classification -> explicit Forge evaluation/governance when needed
- actionable states: `AVAILABLE`, `WEAK_NEEDS_SPECIALIZATION`, `MISSING_VALUABLE`, `UNNECESSARY`
- automatic install/promotion: **none**; existing Capability Forge evaluation/real-task/governor gates remain explicit
- canonical project analysis paths: **1**
- old project-context bridge: **92 -> 21 lines** (**77.17% reduction**)
- manual operator path: **8 -> 4 steps** (**50% reduction**)
- capability implementation copies inside Song City pack: **0**
- old adapter capability-requirement duplication removed from the project subdocument

## Frozen Gen16 benchmark
- **40/40 PASS**
- required-evidence recall: **1.0**
- critical evidence false negatives: **0**
- minimum Song City context reduction: **0.649571**
- dangerous new classifier mutation kill rate: **1.0**
- dangerous survivors: **0**
- permanent MCP tools: **10**

## Song City compatibility
- Gen15 semantics preserved through the consolidated pack path
- telemetry capability remains pinned/promoted at `4dd178d667af77f5c50e846dec419dac3206040491017ca591a3504fa2b455c3`
- Song Boss auditor remains pinned/promoted at `7a8ffc0c3facad20c5714834d1d4e0d0d106f663ae4ec07f8106c21c3d951edf`
- both independent domain evaluations PASS
- representative project context remains 100% required-evidence recall / 0 critical FN
- pack semantic SHA256: `77789cfd1a759e8c55977c7e820592470ed1726405e9d72adf1bf102da7ce95b`

## Self-use / defects fixed
Gen16 used the consolidated machinery on Gen15's own onboarding implementation and fixed two real seams without weakening containment:
1. structural pack validation initially re-resolved evaluator resources during internal classification; structural validation and explicit full resource verification are now separated;
2. the source-only Lab self-use root encountered a virtualenv Python symlink outside the project root; the self-use scope now excludes `venv/**` while the symlink-escape guard remains fail-closed.

Self-use context reduction: **82.53%**, required-evidence recall **1.0**, critical FN **0**.

## Project-building readiness
Evidence says the existing 10-tool + guest-local capability model is sufficient for the planned first real project pilot without new permanent tools. Supported generically: persistent background project services, bounded long-running experiments, deterministic simulation/replay, SQLite/event-ledger inspection, project-specific behavioral evaluators, project-native frontend/backend synchronization tests, and host-mediated browser/render/visual acceptance evidence.

## Retained regressions
- Gen2 **12/12**, Gen3 **16/16**, Gen4 **18/18**, Gen5 **12/12**, Gen6 **13/13**, Gen7 **15/15** version-pinned
- Gen8 **17/17**, Gen9 **20/20**, Gen10 **24/24**, Gen11 **39/39**, Gen12 **30/30**, Gen13 **37/37**, Gen14 **52/52**, Gen15 **40/40**
- Gen14 dangerous mutants: **13/13 killed**, dangerous survivors **0**

Historical-view notes remain intentional: Gen7's current-state diagnostic sees later validators, so retained acceptance uses its version-pinned historical Capsule; Gen12's prior derived future-evidence fixture is removed before historical replay validation.

## Protected state / containment
- Gen15 protected manifest vs final Gen16 protected manifest: **zero forbidden file/tree changes**
- only protected-state growth is the normal trace ledger; Gen15's entire 1,983,015-byte trace is an exact SHA256-matching prefix of the current trace
- capability, memory, regression registries/provenance and operational server/LKG remain unchanged from accepted Gen15 state
- containment PASS; host repository/control sockets unavailable from guest and protected private targets blocked
- final cleanup: **27 Capsule directories removed; 0 remain**; Gen14 nursery absent; Gen12 future fixture absent

## Final Twin checkpoint
- **245 nodes / 380 edges**
- graph `ff8f7b5a4da46b42fefd73c427078edcf18d7345a725ec43d50fd96b80afe930`
- snapshot SHA256 `c7d101384ea0d56d6fc21aae374a48cf62d54aad6f0cd3c4265da5954dff9f14`
- causal-index SHA256 `a68970ee63c3dda403f3e97fcbce9a27b33053bdb50b3f38c5f839d1ad607478`
- verify: **PASS, zero issues, zero newer evidence**

## Final canonical validation
- repository pytest: **13 passed**
- mutation-free Python compile/AST check: **52 files PASS**
- JSON validation: **133 files PASS** on completed lifecycle state
- JSONL validation: **2 files / 124 records PASS** on completed lifecycle state
- secret/credential scan: **PASS**
- `git diff --check`: **PASS**
- host/guest Gen16 source identity parity: **PASS**
- no commit or push performed
- unrelated working-tree work preserved: `ideas.md`, `host/check_chatgpt_ui_staleness.sh`

## Gen17 direction
Recommended next generation: **Terrarium — First Full Project-Building Pilot**. See `lab_generations/GEN17_PROPOSALS.json`.

Initial intended scope: Phase 0 contracts/skeleton and deterministic world/event/replay model; Phase 1 visibly alive autonomous creature; Phase 2 persistent objects/interactions; fixed **800x480** browser reference renderer; persistent host-owned life/state/history. Later project evidence may drive reusable capability forging. Learned preferences/routines and an ESP32-S3/LVGL hardware renderer remain later phases, not prerequisites for the first pilot.
