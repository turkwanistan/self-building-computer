# Next Session — Generation 13 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**; frozen `Optiplex_MCP` remains out of scope.

Before any Lab shell:
1. Call `lab_status`; verify the exact 10-tool surface and operational Gen6 live == LKG, recovery `ACCEPTED`.
2. Verify accepted Gen12 capability `gen12-counterfactual-replay-r1`, build `gen12-counterfactual-replay-r1-5a0fa7b8e62f`, replay SHA `5a0fa7b8e62f3bbcd1e7eadacae1cc6ca00380a5c930fef3a507753003ca8781`, benchmark SHA `8b748b9f75a6556e5158535f57930063c6e762e765da911444ea605dc2963f46`, gold SHA `6673cfea161e76019f4093af96d048277e407c73073197140c254fa9a7ace1fb`.
3. Refresh the Twin if normal post-checkpoint trace evidence makes the recorded 198/300/102 checkpoint stale.
4. Verify frozen Optiplex_MCP release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.
5. Inspect Git status first; preserve unrelated `ideas.md` modification and `host/check_chatgpt_ui_staleness.sh`.

Read `STATUS.md`, `state/current.json`, `lab_generations/GEN12_RESULT.json`, `GEN12_SELF_USE.json`, `GEN12_RETAINED_REGRESSIONS.json`, `GEN12_PROTECTED_STATE.json`, `GEN13_PROPOSALS.json`, `plans/GEN12_COUNTERFACTUAL_REPLAY.md`, `lab_mcp/counterfactual_replay.py`, `lab_mcp/task_routing.py`, and `lab_mcp/evidence_epoch.py`.

Gen12 benchmark: 30/30; determinism/baseline reproduction/attribution 1.0; unsafe 10/10 rejected; historical leakage 0; forbidden state mutations 0. Retained Gen2–Gen11 all pass.

Ranked Gen13 direction: **Project Onboarding + Domain Capability Expansion Pilot**. Keep the outward fork bounded: onboard one project/domain, discover needed domain capabilities, expose them guest-locally, and retain the full safety/regression substrate. Hierarchical Experiment Isolation is ranked second and should be pulled forward if onboarding/replay composition proves it necessary.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
