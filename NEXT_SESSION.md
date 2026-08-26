# Next Session — Generation 14 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**; frozen `Optiplex_MCP` remains out of scope.

Before any Lab shell:
1. Call `lab_status`; verify operational Gen6 build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, exactly 10 permanent tools.
2. Verify accepted Gen13 capability `gen13-hierarchical-experiment-isolation-r1`, build `gen13-hierarchical-experiment-isolation-r1-9a32955b79c6`, hierarchy SHA `9a32955b79c63efd1023ca1741bff61ab2b0ed5dfb3eaea0aa817b777421a372`, Capsule SHA `e1276653cde8c0fd9df2a0ebddc5ca5fb148e939ea182996a80563b6b60c05a8`, replay SHA `6d7f32a86ce73501feecffd21ba6ca319de548f9b29044c9e737baba824dbac0`, benchmark SHA `e6dce8fe8c3858c9fa8e425d06ef2a7838b6341b2d5dab6d78f47d89dc1e1b1e`, gold SHA `93f0976bfc47542105252cc288b093cb453341ca623f6757cfdd032c4676e785`.
3. Verify Gen13 benchmark **37/37**, unsafe **17/17 rejected**, deterministic composition/attribution **1.0/1.0**, valid delegated Gen12 replay **1.0**, forbidden accepted-state mutations **0**.
4. Refresh the Twin if normal post-checkpoint trace evidence makes the recorded 202/311/104 checkpoint stale.
5. Verify frozen Optiplex_MCP release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.
6. Inspect Git status first and preserve unrelated work.

Read `STATUS.md`, `state/current.json`, `lab_generations/GEN13_RESULT.json`, `GEN13_SELF_USE.json`, `GEN13_DELEGATION_EVIDENCE.json`, `GEN13_RETAINED_REGRESSIONS.json`, `GEN13_PROTECTED_STATE.json`, `GEN14_PROPOSALS.json`, `plans/GEN13_HIERARCHICAL_EXPERIMENT_ISOLATION.md`, `lab_mcp/hierarchical_experiment.py`, `experiment_capsule.py`, and `counterfactual_replay.py`.

## Gen14 thesis
**Evaluator Mutation Nursery / Benchmark Hardening**: use Gen13 hierarchical isolation to challenge evaluator assumptions, thresholds, fixtures, and decision rules without mutating accepted state. The objective is to detect brittle judges and false confidence before the planned Project Onboarding + Domain Capability Expansion Pilot.

Do not broaden Gen14 into Project Onboarding itself unless repository/live evidence establishes that evaluator hardening is unnecessary. Preserve the full Gen2-Gen13 retained matrix.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
