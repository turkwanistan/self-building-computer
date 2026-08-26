# Next Session — Generation 8 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**. `Optiplex_MCP` remains frozen.

Before any Lab shell:
1. Discover exactly the accepted 10 permanent Lab tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
2. Call `lab_status`. Because Gen7 did not modify `server.py`, expected operational server identity remains:
   - generation `gen6-experience-memory-r1`
   - build `gen6-experience-memory-r1-dc0d2cb41595`
   - server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`
   - recovery `ACCEPTED`; tool surface 10
3. Verify canonical accepted capability generation in `state/current.json` is `gen7-self-model-r1`, Twin SHA `f5ba258ed5559b755f5b68891a74f48bdfac243638bff60cc730c0f3cbf61d8e`, Causal Spine SHA `be7a798db4f7976e74deb787ad277a56f5fde719144280b8619b7e87b92124d3`, and Twin digest `49ddf70f7baa2b73508e2921250cdf131805648421d96338ebd0cf84c9b4ce2c`.
4. Verify frozen Optiplex_MCP remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

Read `START_HERE.md`, `state/current.json`, `STATUS.md`, `lab_generations/GEN7_RESULT.json`, `lab_generations/GEN8_PROPOSALS.json`, and `plans/GEN7_ARCHITECTURAL_TWIN_CAUSAL_SPINE.md`.

Top evidence-backed Gen8 direction: **Context Compiler on top of the Architectural Twin**. Second: **Reproducible Experiment Capsule + Evaluator / Mutation Nursery**, motivated by the Gen5 and Gen4 retained-benchmark state-leak findings. Do not implement Gen8 without explicit user request.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Optiplex_Lab shell.
