# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN5_CAPABILITY_FORGE`

Generation 5 evolved **Optiplex_Lab + the isolated `mcp-lab` VM** into an evidence-gated capability forge. `Optiplex_MCP` and the legacy `optiplex-mcp-agent` remained frozen.

## Accepted Gen-5 Lab
- generation: `gen5-capability-forge-r1`
- build: `gen5-capability-forge-r1-d752f3cb4470`
- server SHA256: `d752f3cb447067296e275296fd02a3b8f4ec3609377568c21391fbd0e8cb2447`
- Capability Forge SHA256: `85ca609c4f2c7e89e0f1b39a261beb3477da89c42773ba682c197ef029adea4c`
- Code Mode SHA256: `d6c1b55e4152a66dc9732ed333853f22bea1442c163be5e3082c36a860fa1264`
- reusable workflow SHA256: `895bcc0a76fb82959a79bd445b11354bd4be22db88443521ccb280cc47cfbea4`
- workflow graph SHA256: `178896ec0c9bc2115baaee9f7da88d73709fdfaacb93f577661e447d6d831e12`
- recovery: `ACCEPTED`; live == LKG
- permanent MCP surface: **10 before / 10 after**
- connector refresh/new chat required for schema: **NO**

## What Gen 5 added
The guest-local Forge uses content-addressed capability capsules with typed contracts, declared side effects, dependency manifests, independent evaluators, append-only provenance, lifecycle/TTL state, duplicate avoidance, and an evidence-gated Promotion Governor. A generic `capability-invoke@1` reusable workflow and `capability-use-transaction@1` graph let Gen3/Gen4 machinery invoke forged capabilities without adding an MCP tool per capability.

Final registry: **12 total — 2 promoted, 3 candidates, 6 rejected, 1 expired**. Creation remains cheap; promotion requires passing hard authority/evaluator/task/reuse gates.

## Gen-5 evidence
- Capability Forge self-test: **8/8 PASS**
- blind capability benchmark: **12/12 PASS**
- useful passing capabilities forged: **6**
- deliberately broken descendants rejected: **6**
- malformed contract: rejected
- forbidden-authority manifest: rejected
- exact duplicate: avoided/reused
- ephemeral helper: expired while provenance survived
- successful forged capability reuse: PASS
- invocation through Gen3 workflow + Gen4 graph: PASS
- semantic editing experiment: exact text **1/5** vs semantic **5/5** formatting variants
- real semantic-edit authoring payload: **1862 B -> 549 B (70.5% reduction)**
- self-host upgrade graph: `wg_20260826T110630Z_f13776e0` PASS
- deliberate bad-candidate recovery graph: `wg_20260826T110756Z_be85be28` PASS
- final guest regressions: Lab 12/12, Code Mode 5/5, workflows 4/4, graphs 8/8, Forge 8/8
- containment: PASS

Canonical evidence includes the capability registry, append-only provenance, Gen5 benchmark, semantic-edit experiment, Forge source/skill, workflow/graph adapters, and `GEN5_RESULT.json`.

## Generation 6
Actual Gen5 evidence ranks **Procedural Memory Distiller** first and **Failure-to-Regression Compiler** second. See `lab_generations/GEN6_PROPOSALS.json`. Do not implement Generation 6 without a new explicit implementation request.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through `Optiplex_Lab.shell`; recursive MCP self-calls can deadlock.
