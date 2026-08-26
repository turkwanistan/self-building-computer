# Next Session — Generation 11 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**. `Optiplex_MCP` remains frozen.

Before any Lab shell:
1. Verify exactly the accepted 10 permanent Lab tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
2. Call `lab_status`; expected operational identity intentionally remains Gen6: generation `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, 10 tools.
3. Verify canonical capability generation `gen10-evidence-epoch-r1`, build `gen10-evidence-epoch-r1-9418201f1401`, coordinator SHA `9418201f1401e56a6dd62f8cb696b3bf947f822073b83d07fa57b028f3ba035f`.
4. Verify the final accepted Twin checkpoint: 186 nodes / 279 edges / 94 inputs, graph `947181e319337fac733ca7482b8b14e967a8c99a54d22bc6dde368df67ca3b09`, snapshot SHA `1129f3d9039eaadb800d36dd6aa97198a7bf5ee60f460c6be9a385a6e4fcb336`.
5. Verify frozen Optiplex_MCP: release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.
6. Inspect Git status first and preserve unrelated user/concurrent work. At Gen10 completion, `ideas.md` was concurrently modified outside Gen10 and `host/check_chatgpt_ui_staleness.sh` was unrelated untracked user work.

Read `START_HERE.md`, `state/current.json`, `STATUS.md`, `lab_generations/GEN10_RESULT.json`, `lab_generations/GEN11_PROPOSALS.json`, `plans/GEN10_EVIDENCE_EPOCH_COORDINATOR.md`, `lab_mcp/evidence_epoch.py`, and the Gen10 benchmark/self-use/retained/protected artifacts.

Gen10 benchmark: **24/24 PASS**; recall **1.000**; critical FN **0**; necessity precision **1.000**; context reduction vs Gen8 **45.66%**; unsafe fail-close **5/5**; expected same-transaction self-invalidation **0/1**; next-epoch freshness **1/1**. Retained: Gen2 12/12, Gen3 16/16, Gen4 18/18, Gen5 12/12, Gen6 13/13, Gen7 15/15 version-pinned, Gen8 17/17, Gen9 20/20.

Top Gen11 proposal: **Task Intent Classification + Authority Routing Hardening**. Treat `lab_generations/GEN11_PROPOSALS.json` as proposals, not authorization to implement. Around Gen13, explicitly reassess readiness for the planned Project Onboarding + Domain Capability Expansion fork.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
