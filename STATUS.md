# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN4_WORKFLOW_GRAPHS`

Generation 4 evolved **Optiplex_Lab + the isolated `mcp-lab` VM**. `Optiplex_MCP` and the legacy `optiplex-mcp-agent` remained frozen.

## Accepted Gen-4 Lab
- generation: `gen4-workflow-graphs-r1`
- build: `gen4-workflow-graphs-r1-4558bdb23e52`
- server SHA256: `4558bdb23e52572c6a13978a6ed10f9dc6fef26d1ae27abd0bd560c9fd1d63ac`
- workflow graph runner: `gen4-workflow-graphs-r1`
- graph runner SHA256: `178896ec0c9bc2115baaee9f7da88d73709fdfaacb93f577661e447d6d831e12`
- Code Mode SHA256: `d6c1b55e4152a66dc9732ed333853f22bea1442c163be5e3082c36a860fa1264`
- reusable workflow SHA256: `895bcc0a76fb82959a79bd445b11354bd4be22db88443521ccb280cc47cfbea4`
- recovery: `ACCEPTED`
- live SHA == LKG SHA == `4558bdb23e52572c6a13978a6ed10f9dc6fef26d1ae27abd0bd560c9fd1d63ac`
- MCP surface: unchanged at exactly 10 tools
- connector refresh/new chat required: **NO**

## What Gen 4 added
Guest-local `/opt/optiplex-lab/workflow_graphs.py` composes immutable reusable `name@version` workflows into bounded DAG/transaction definitions. It validates parent and child parameters before execution, records child hashes/provenance, detects cycles, bounds depth/nodes/invocations/retries/timeouts, persists run state, supports explicit recovery branches, and verifies restart checkpoints before continuing. Underlying Code Mode traces/artifacts remain authoritative.

Accepted composites:
- `lab-upgrade-transaction@1` `e516a1db5e06ca97de814851c3d3cdc5f891f08b156aad208effc7adf6a69bee`
- `lab-recovery-transaction@1` `1c1c43529d507a0c972205aef347c9134d4d153a15af04cbfc1bf24d253f9ac7`

## Gen-4 evidence
- Gen-4 benchmark: **18/18 PASS**, 17662.29 ms
- normal lifecycle top-level calls: **4 -> 1 (75% reduction)**
- bad recovery calls: **3 -> 1 (66.7% reduction)**
- combined lifecycle calls: **7 -> 2 (71.4% reduction)**
- normal edit-heavy authoring proxy: **4591 -> 4449 bytes (3.1%)**
- bad recovery authoring proxy: **153 -> 50 bytes (67.3%)**
- newly authored procedural steps for composite reuse: **0**
- benchmark-local raw-shell step share: **8.7%**
- restart/resume: PASS
- deliberate bad-candidate LKG recovery + explicit reacceptance: PASS

Finalization used one `lab-upgrade-transaction@1` parent run `wg_20260826T100041Z_ebde386c` to restore canonical Gen-4 metadata after the Gen-3 compatibility benchmark's intentional no-op self-update relabeled the build. Candidate verification remained distinct from acceptance.

## Regressions / containment
- Lab self-test: **12/12**
- Code Mode: **5/5**
- reusable workflows: **4/4**
- workflow graphs: **8/8**
- legacy benchmark: **17/17**
- Gen-2 benchmark: **12/12**
- Gen-3 benchmark: **16/16**
- repository tests: **13 passed**
- secret scan: **PASS**
- public internet: available; host/private/RFC1918/Tailscale targets remain blocked; host control sockets/mounts/credentials absent.

## Generation 5
Top evidence-backed proposal: **Structured transactional / AST editing**. Composition removed residual sequencing, but real source evolution still carries large exact `old/new` code strings; normal lifecycle authoring bytes fell only 3.1%. See `lab_generations/GEN5_PROPOSALS.json`.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through `Optiplex_Lab.shell`; use connector schema discovery or detached/out-of-band probing.
