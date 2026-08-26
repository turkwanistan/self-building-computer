# Next Session — Generation 6 Entry Gate

Repository/live state is authoritative. Target remains **Optiplex_Lab + isolated `mcp-lab` VM**. `Optiplex_MCP` is frozen.

## Hard connector gate
Before Lab shell, discover exactly these 10 `Optiplex_Lab` tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`. Then call `lab_status`.

Expected accepted Gen-5 identity:
- generation `gen5-capability-forge-r1`
- build `gen5-capability-forge-r1-d752f3cb4470`
- server SHA256 `d752f3cb447067296e275296fd02a3b8f4ec3609377568c21391fbd0e8cb2447`
- Capability Forge SHA256 `85ca609c4f2c7e89e0f1b39a261beb3477da89c42773ba682c197ef029adea4c`
- Code Mode SHA256 `d6c1b55e4152a66dc9732ed333853f22bea1442c163be5e3082c36a860fa1264`
- reusable workflow SHA256 `895bcc0a76fb82959a79bd445b11354bd4be22db88443521ccb280cc47cfbea4`
- workflow graph SHA256 `178896ec0c9bc2115baaee9f7da88d73709fdfaacb93f577661e447d6d831e12`
- tool surface 10
- recovery `ACCEPTED`; live SHA == LKG SHA == expected server SHA

Verify frozen `Optiplex_MCP` remains release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

Read `START_HERE.md`, `state/current.json`, `STATUS.md`, `lab_generations/GEN5_RESULT.json`, `lab_generations/GEN6_PROPOSALS.json`, `plans/GEN5_CAPABILITY_FORGE.md`, and the capability-forge skill before designing anything.

## Gen-6 hypothesis
Top evidence-backed proposal: **Procedural Memory Distiller**. Second: **Failure-to-Regression Compiler**. Gen5 shows reuse is cheap once a capability exists; the residual reasoning cost is recognizing relevant prior experience, distilling applicability, and turning failures into durable regressions.

Do **not** implement Generation 6 without a new explicit implementation request.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell. No connector refresh/new session is required merely to use accepted Gen5 because the permanent MCP surface stayed at 10 tools.
