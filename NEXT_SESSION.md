# Next Session — Generation 17 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**; frozen `Optiplex_MCP` remains out of scope.

Generation 16 is accepted as `gen16-capability-consolidation-r1`, build `gen16-capability-consolidation-r1-33dad6262d3a`.

Before project implementation:
1. Verify operational Gen6 build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 permanent tools.
2. Verify Gen16 gold SHA256 `2755cc4fa09afbe653dbc6961a4bab314a052483fc9d8d62d3b71bf83db4b80a`, benchmark **40/40**, onboarding/project-factory SHA256 `33dad6262d3a2071c4198b4d0e337076f0c8d52c9f9015dab6b052054ff458c0`, and `GEN16_RESULT.json`.
3. Verify retained Gen2–Gen15 matrix in `GEN16_RETAINED_REGRESSIONS.json`; Gen13 must remain **37/37**, Gen14 **52/52** with dangerous kill rate **1.0** / zero dangerous survivors, and Gen15 **40/40**.
4. Verify final Gen16 Twin checkpoint **245 nodes / 380 edges**, graph `ff8f7b5a4da46b42fefd73c427078edcf18d7345a725ec43d50fd96b80afe930`; refresh the derived Twin if normal append-only audit evidence makes it stale.
5. Inspect Git status and preserve unrelated work (`ideas.md`, `host/check_chatgpt_ui_staleness.sh` unless explicitly instructed otherwise).

Read `STATUS.md`, `state/current.json`, `lab_generations/GEN16_RESULT.json`, `GEN16_GOLD.json`, `GEN16_BENCHMARK.json`, `GEN16_CONSOLIDATION.json`, `GEN16_SONG_CITY_PACK.json`, `GEN16_SELF_USE.json`, `GEN16_GENERALIZATION.json`, `GEN16_MUTATION_EVIDENCE.json`, `GEN16_RETAINED_REGRESSIONS.json`, `GEN16_PROTECTED_STATE.json`, and `GEN17_PROPOSALS.json`.

## Recommended Gen17 thesis
**Terrarium — First Full Project-Building Pilot.** This is the transition from primarily platform-driven generations to project-driven evolution.

Use the Gen16 reusable project capability pack/onboarding path. Do not build a parallel Terrarium-specific platform layer. Let concrete project gaps trigger bounded capability discovery and Capability Forge evaluation/promotion.

Initial target scope:
- Phase 0: project contracts/skeleton; deterministic world/state/event model; replay harness.
- Phase 1: visibly alive autonomous creature.
- Phase 2: persistent objects/interactions.
- fixed **800x480** browser reference renderer.
- persistent **host-owned** life/state/history; renderer/browser restarts must not reset the creature.
- deterministic seeded simulation/replay is acceptance-critical.

Later, not initial prerequisites: learned preferences/routines and a hardware renderer fork such as ESP32-S3/LVGL.

Do not grow permanent MCP tools or change the operational Gen6 server without overwhelming project evidence and explicit frozen acceptance criteria. Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
