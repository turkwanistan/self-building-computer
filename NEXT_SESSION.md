# Next Session — Generation 12 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**; frozen `Optiplex_MCP` remains out of scope.

Before any Lab shell:
1. Call `lab_status`; verify exactly the 10 tools `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
2. Verify operational Gen6 still equals LKG: build `gen6-experience-memory-r1-dc0d2cb41595`, SHA `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.
3. Verify accepted Gen11 capability `gen11-intent-authority-routing-r1`, build `gen11-intent-authority-routing-r1-59a1bef513c7`, router SHA `59a1bef513c7d12b1411f78dfd9b5a4c007368d1c5e9e9e7f431f0bfedf2575b`, route-aware epoch SHA `24e9542919ff9aa781c33c534d012d82af91a9bf418be9a102fb7ba30b40b481`.
4. Verify final sealed Twin checkpoint: 192/288/98, graph `0e40f143fe7934b722a707d5bceda6e83ce8931feef557e75c0cc0913b6cfcd3`, snapshot `45f8fed7de7ec3b611693813139ddbc8ae9feba1790c036862a5eb4d652d518a`. Treat subsequent normal audit append as next-epoch evidence and refresh before a routed epoch when required.
5. Verify frozen Optiplex_MCP release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.
6. Inspect Git status first; preserve unrelated `ideas.md` modification and `host/check_chatgpt_ui_staleness.sh` unless the user explicitly changes their ownership/scope.

Read `STATUS.md`, `state/current.json`, `lab_generations/GEN11_RESULT.json`, `GEN11_SELF_USE.json`, `GEN11_RETAINED_REGRESSIONS.json`, `GEN11_PROTECTED_STATE.json`, `GEN12_PROPOSALS.json`, `plans/GEN11_TASK_INTENT_AUTHORITY_ROUTING.md`, `lab_mcp/task_routing.py`, and `lab_mcp/evidence_epoch.py`.

Accepted Gen11 benchmark: 39/39; routing gold 29/29; authority recall 1.0; critical FN 0; unsafe routes 0; mixed precedence 100%; safety ambiguity conservative 100%; necessity precision/recall 1.0/1.0; context reduction vs Gen8 44.7958%. Retained Gen2–Gen10 all pass.

Top Gen12 proposal: **Counterfactual Replay over Intent-Routed Evidence Epochs**. Explicitly account for the nested-isolation lesson: do not blindly stack Experiment Capsules when a child evaluator already owns isolation. `GEN12_PROPOSALS.json` is a proposal set, not authorization.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
