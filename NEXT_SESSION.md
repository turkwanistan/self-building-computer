# Next Session — Generation 16 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**; frozen `Optiplex_MCP` remains out of scope.

Before implementation:
1. Verify operational Gen6 build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 permanent tools.
2. Verify accepted Gen15 build `gen15-project-onboarding-domain-capability-r1-50f8653f0623`, gold `718d297ae608d53bad0b81b576f536df05c737c165c2dc3a1c29851b989440eb`, benchmark **40/40**, and `GEN15_RESULT.json`.
3. Verify retained Gen2–Gen14 matrix in `GEN15_RETAINED_REGRESSIONS.json`; Gen13 must remain **37/37**, Gen14 **52/52** with dangerous kill rate **1.0** and zero dangerous survivors.
4. Verify the two promoted Gen15 domain capabilities and final Twin checkpoint **236/357**, graph `9195d556b329c7c38505bb3b52c4584f47362f07c5388aa60bb91923575fec8c`; refresh Twin if normal audit evidence makes it stale.
5. Inspect Git status and preserve unrelated work (`ideas.md`, `host/check_chatgpt_ui_staleness.sh` unless the user says otherwise).

Read `STATUS.md`, `state/current.json`, `lab_generations/GEN15_RESULT.json`, `GEN15_SELF_USE.json`, `GEN15_DOMAIN_CAPABILITIES.json`, `GEN15_ADVERSARIAL.json`, `GEN15_GENERALIZATION.json`, `GEN15_RETAINED_REGRESSIONS.json`, `GEN15_PROTECTED_STATE.json`, and `GEN16_PROPOSALS.json`.

## Recommended Gen16 thesis
**Capability Consolidation + Reusable Project Capability Packs**: consolidate overlapping paths revealed by Gen15, make project adapters/capability packs reusable, and preserve unique benchmark/evaluator coverage. Prefer simplification and transferability over adding framework layers.

Do not grow permanent MCP tools or change the operational Gen6 server without overwhelming evidence and explicit acceptance criteria. Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
