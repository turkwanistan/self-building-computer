# Next Session — Generation 15 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**; frozen `Optiplex_MCP` remains out of scope.

Before any Lab shell:
1. Call `lab_status`; verify operational Gen6 build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 permanent tools.
2. Verify accepted Gen14 capability `gen14-evaluator-mutation-nursery-r1`, build `gen14-evaluator-mutation-nursery-r1-fe5f9d8fbb3c`, nursery SHA `fe5f9d8fbb3ce1aa7b7a9d8ee84536fead62c3246337644c76b037d196b2c87d`, benchmark **52/52**, dangerous mutations **13/13 killed**, dangerous survivors **0**.
3. Verify Gen13 remains **37/37** and the complete retained Gen2-Gen13 matrix in `GEN14_RETAINED_REGRESSIONS.json` is PASS.
4. Refresh the Twin if normal post-checkpoint trace evidence makes the recorded **215/330/114** checkpoint stale.
5. Inspect Git status first and preserve unrelated work.

Read `STATUS.md`, `state/current.json`, `lab_generations/GEN14_RESULT.json`, `GEN14_SELF_USE.json`, `GEN14_MUTATION_EVIDENCE.json`, `GEN14_ADVERSARIAL.json`, `GEN14_RETAINED_REGRESSIONS.json`, `GEN14_PROTECTED_STATE.json`, `GEN15_PROPOSALS.json`, `plans/GEN14_EVALUATOR_MUTATION_NURSERY.md`, `lab_mcp/evaluator_mutation_nursery.py`, `lab_mcp/hierarchical_experiment.py`, and relevant target-project material.

## Gen15 thesis
**Project Onboarding + Domain Capability Expansion Pilot**: choose one real external project/domain, compile its architecture/evidence/authority model, identify missing useful domain capabilities, build and evaluate bounded guest-local capabilities, and demonstrate that the Gen8-Gen14 substrate transfers beyond self-improvement. Prefer meaningful domain capability gains over more framework sophistication.

Do not grow permanent MCP tools unless overwhelming evidence requires it. Do not automatically promote candidate domain capabilities. Use Gen13 hierarchical isolation and Gen14 evaluator mutation hardening for hazardous evaluations. Preserve the full Gen2-Gen14 retained matrix.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
