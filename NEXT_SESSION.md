# Next Session — Generation 9 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**. `Optiplex_MCP` remains frozen.

Before any Lab shell:
1. Discover exactly the accepted 10 permanent Lab tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
2. Call `lab_status`. Gen8 did not modify `server.py`, so expected operational identity remains:
   - generation `gen6-experience-memory-r1`
   - build `gen6-experience-memory-r1-dc0d2cb41595`
   - server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`
   - recovery `ACCEPTED`; tool surface 10
3. Verify canonical accepted capability generation in `state/current.json` is `gen8-context-compiler-r1`, capability build `gen8-context-compiler-r1-39b7f040fca1`, Context Compiler SHA `39b7f040fca1afb2332b5dd902e186b710ea4d1d5a2cd0351aa307f6d8f786c3`, Experiment Capsule SHA `69d66ecaec546f08ea6079c5446254bc1704c791f77bf76ce472d1f4907f7415`.
4. Verify final Twin is 173 nodes / 242 edges / 85 inputs, graph digest `ceab9a44188706a209b23066217de4e8991b44d067d6c21f9018d56861c182eb`, snapshot SHA `f1299fa23330944c734377203c4769fb4e8e27a9ac104f64397299a277ba9eea`.
5. Verify frozen Optiplex_MCP remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

Read `START_HERE.md`, `state/current.json`, `STATUS.md`, `lab_generations/GEN8_RESULT.json`, `lab_generations/GEN9_PROPOSALS.json`, and `plans/GEN8_CONTEXT_COMPILER_EXPERIMENT_CAPSULE.md`.

Gen8 benchmark: **17/17 PASS**, required-evidence recall **1.000**, critical FN **0**, precision **0.6613**. Retained regressions: Gen2 12/12, Gen3 16/16, Gen4 18/18, Gen5 12/12, Gen6 13/13, version-pinned Gen7 15/15. Preserve the finding that historical regressions require version-pinned experiment views.

Top Gen9 direction: **Context Necessity Optimizer / semantic evidence minimization**. Do not implement Gen9 without explicit user request.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
