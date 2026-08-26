# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN10_EVIDENCE_EPOCH`

Generation 10 evolved **Optiplex_Lab + isolated `mcp-lab`** with a deterministic Evidence Epoch / Snapshot Freshness Coordinator around the accepted Gen8 Context Compiler and Gen9 Context Necessity Optimizer. `Optiplex_MCP` and the permanent 10-tool Lab MCP surface remain unchanged.

## Accepted Gen10 capability layer
- generation: `gen10-evidence-epoch-r1`
- capability build: `gen10-evidence-epoch-r1-9418201f1401`
- Evidence Epoch Coordinator SHA256: `9418201f1401e56a6dd62f8cb696b3bf947f822073b83d07fa57b028f3ba035f`
- Gen10 benchmark source SHA256: `6c43563621203bd6b201b40de8d425984a9aa1ba1c340be9198c6fb8ea05c6ef`
- frozen Gen10 gold SHA256: `970c3a1db846f25d9f0d9f1e8a8b28d11a1c45439642c8d5831eca2ab94f31de`
- permanent MCP surface: **10 before / 10 after**
- `server.py`: **unchanged**

Operational `lab_status` intentionally remains Gen6: generation `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.

## Gen10 evidence
- benchmark: **24/24 PASS**
- required-evidence recall **1.000**; critical FN **0**; Gen9 necessity precision **1.000**
- Gen9-vs-Gen8 context payload reduction **45.66%**
- epoch seal median **183.767 ms** (p95 **238.749 ms**)
- verify median **70.402 ms** (p95 **77.171 ms**)
- finalize median **75.007 ms**
- unsafe mutations fail closed **5/5**
- avoidable expected same-transaction self-invalidation **0/1**
- next-epoch freshness **1/1**

Gen10 reproduced the Gen9 finalization problem with a declared Tier-1 benchmark artifact. The evaluator changed it after compile/minimize, but the sealed transaction remained reproducible; finalize classified the change as an expected output and queued it for the next epoch; the next epoch observed the new SHA. Unexpected critical mutation, missing pinned blob, contradictory authority, append-only prefix mutation, and unsafe live-authority freezing still fail closed.

## Final Twin / self-use
- final Twin checkpoint: **186 nodes / 279 edges / 94 inputs**
- graph digest `947181e319337fac733ca7482b8b14e967a8c99a54d22bc6dde368df67ca3b09`
- snapshot SHA256 `1129f3d9039eaadb800d36dd6aa97198a7bf5ee60f460c6be9a385a6e4fcb336`
- causal digest `e507a9a07f0af1ea2bdd16e8b70d7e29f0400ae5d67abcb3530af5ab49ef3db5`
- verify at final checkpoint: **PASS, zero issues**
- final self-use epoch `e2d120e53e86a3492e8291ac67e6ea9ad53eee3e509ab523bf36da45ebe3bb6a` and transaction `b30a5dfbe6b0cec1cdfab7418cbc05391978a0b18c19d35afba55162a91aa271` reproduced identically across two starts.

Self-use found and repaired a real canonical-digest bug (volatile append-only tail observations had leaked into epoch identity) and two benchmark-harness defects without relaxing frozen thresholds. See `lab_generations/GEN10_SELF_USE.json`.

## Retained regressions / protected state
- Gen2 **12/12**, Gen3 **16/16**, Gen4 **18/18**, Gen5 **12/12**, Gen6 **13/13**
- Gen7 **15/15** in a version-pinned historical capsule view
- Gen8 **17/17**, Gen9 **20/20** in a quiescent mutation-safe capsule rerun
- zero forbidden protected-state mutation
- recorded audit trace growth is prefix-preserving append-only only
- containment PASS: public internet available; protected host endpoint blocked; no host repo, host mounts, or host-control sockets
- earliest Gen8 `/etc/systemd/system` baseline caveat remains explicitly preserved.

## Canonical evidence
`plans/GEN10_EVIDENCE_EPOCH_COORDINATOR.md`, `lab_generations/GEN10_GOLD.json`, `GEN10_BENCHMARK.json`, `GEN10_EPOCH_EVIDENCE.json`, `GEN10_RETAINED_REGRESSIONS.json`, `GEN10_SELF_USE.json`, `GEN10_PROTECTED_STATE.json`, `GEN10_RESULT.json`, and `GEN11_PROPOSALS.json`.

## Gen11
Top evidence-backed direction: **Task Intent Classification + Authority Routing Hardening**. Counterfactual Replay over sealed epochs and an Evaluator/Mutation Nursery are ranked behind it. The roadmap's outward project-onboarding/domain-capability fork around Gen13 remains a readiness target, not a Gen11 implementation mandate. Do not implement Gen11 without a new explicit request.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell.
