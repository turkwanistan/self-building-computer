# Next Session — Generation 5 Entry Gate

Repository/live state is authoritative over this file, prior chats, and ChatGPT memory. Target: **Optiplex_Lab + isolated `mcp-lab` VM**. `Optiplex_MCP` remains frozen.

## Hard connector gate
Before Lab shell, discover exactly these 10 `Optiplex_Lab` tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`. Then call `lab_status`.

Expected accepted Gen-4 identity:
- generation `gen4-workflow-graphs-r1`
- build `gen4-workflow-graphs-r1-4558bdb23e52`
- server `4558bdb23e52572c6a13978a6ed10f9dc6fef26d1ae27abd0bd560c9fd1d63ac`
- graph runner `178896ec0c9bc2115baaee9f7da88d73709fdfaacb93f577661e447d6d831e12`
- Code Mode `d6c1b55e4152a66dc9732ed333853f22bea1442c163be5e3082c36a860fa1264`
- reusable workflows `895bcc0a76fb82959a79bd445b11354bd4be22db88443521ccb280cc47cfbea4`
- tool surface 10
- recovery `ACCEPTED`; live SHA == LKG SHA == `4558bdb23e52572c6a13978a6ed10f9dc6fef26d1ae27abd0bd560c9fd1d63ac`

Then inspect Git status and read `START_HERE.md`, `state/current.json`, `STATUS.md`, `lab_generations/GEN4_RESULT.json`, `lab_generations/GEN5_PROPOSALS.json`, `plans/GEN4_COMPOSABLE_WORKFLOW_GRAPHS.md`, and the workflow-graphs skill. Preserve all work.

Verify frozen `Optiplex_MCP`: release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`.

Run lightweight accepted-state checks before Gen 5: Lab 12/12, Code Mode 5/5, reusable workflows 4/4, workflow graphs 8/8, recovery ACCEPTED, live=LKG, containment intact, no abandoned generation jobs. Use retained benchmark evidence unless a destructive rerun is materially required.

## Gen-5 leading hypothesis
**Structured transactional / AST editing.** Gen4 solved lifecycle sequencing (4->1 calls) but normal edit-heavy authoring bytes improved only 4591->4449 (3.1%) because exact old/new source payloads dominate. Treat this as the leading hypothesis, not an immutable specification.

Do not run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell. No connector refresh is required for accepted Gen 4 because the MCP surface stayed at 10 tools.
