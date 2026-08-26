# Next Session — Generation 10 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**. `Optiplex_MCP` remains frozen.

Before any Lab shell:
1. Verify exactly the accepted 10 permanent Lab tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
2. Call `lab_status`; expected operational identity remains Gen6: generation `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, 10 tools.
3. Verify canonical capability generation is `gen9-context-necessity-r1`, build `gen9-context-necessity-r1-6be10d7af323`, optimizer SHA `6be10d7af3238fb59a2cf8f5d9a858de4b3957a9681634bbe4ef78e33402d299`.
4. Verify final Twin metadata: 179 nodes / 259 edges / 89 inputs, graph digest `4d983ad01376a04a54dc834d0dc46ee4d606293fca572f3d8ead45e81e65c45f`, snapshot SHA `2c05c6282070c74bee204e837d0b8d6a03677ab404a407318c8a4d27594484be`.
5. Verify frozen Optiplex_MCP remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

Read `START_HERE.md`, `state/current.json`, `STATUS.md`, `lab_generations/GEN9_RESULT.json`, `lab_generations/GEN10_PROPOSALS.json`, and `plans/GEN9_CONTEXT_NECESSITY_OPTIMIZER.md`.

Gen9 benchmark: **20/20 PASS**, recall **1.000**, necessity-aware **47 TP / 0 FP / 0 FN**, comparable legacy precision **0.931818**, context payload reduction **46.09%**, median minimization **1.94 ms**. Retained: Gen2 12/12, Gen3 16/16, Gen4 18/18, Gen5 12/12, Gen6 13/13, version-pinned Gen7 15/15, Gen8 17/17. Preserve the rule that future-valid evidence must not be forced into historical gold.

Top Gen10 direction: **Evidence Epoch / Snapshot Freshness Coordinator**. Do not implement Gen10 without explicit user request.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
