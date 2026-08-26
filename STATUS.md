# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN12_COUNTERFACTUAL_REPLAY`

Generation 12 evolved **Optiplex_Lab + isolated `mcp-lab`** with deterministic **Counterfactual Replay over Intent-Routed Evidence Epochs**. Historical truth remains immutable: alternatives are explicit typed overlays bound to a sealed Gen10 epoch and sealed Gen11 routing proof. `Optiplex_MCP` remains frozen and the permanent Lab MCP surface remains exactly 10 tools.

## Accepted Gen12 capability
- generation: `gen12-counterfactual-replay-r1`
- capability build: `gen12-counterfactual-replay-r1-5a0fa7b8e62f`
- Counterfactual Replay SHA256: `5a0fa7b8e62f3bbcd1e7eadacae1cc6ca00380a5c930fef3a507753003ca8781`
- benchmark source SHA256: `8b748b9f75a6556e5158535f57930063c6e762e765da911444ea605dc2963f46`
- frozen gold SHA256: `6673cfea161e76019f4093af96d048277e407c73073197140c254fa9a7ace1fb`
- `server.py`: **unchanged**; permanent MCP tools: **10**

Operational Lab intentionally remains Gen6: `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server/LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`.

## Gen12 evidence
- frozen benchmark: **30/30 PASS**
- deterministic replay **100%**; baseline reproduction **100%**; declared-delta attribution **100%**
- unsafe adversarial cases **10/10 rejected**; authority weakening accepted **0**; historical leakage **0**; forbidden accepted-state mutations **0**
- replay classes: implementation/change, intent/routing, evaluator, authority/evidence selection, no-op
- implementation replay uses exactly one Experiment Capsule isolation owner; unsafe nested delegation is refused rather than guessed

## Quality / retained regressions
- Gen2 **12/12**, Gen3 **16/16**, Gen4 **18/18**, Gen5 **12/12**, Gen6 **13/13**
- Gen7 **15/15** version-pinned, Gen8 **17/17** quiescent, Gen9 **20/20**, Gen10 **24/24**, Gen11 **39/39**, routing gold **29/29**
- critical authority recall **1.000**, critical FN **0**, unsafe routes **0**
- necessity precision **1.000**, required-evidence recall **1.000**, context reduction vs Gen8 **44.824%**

Gen8 first showed 16/17 when run inside a durable job because the job ledger changed `/var/lib` between its two reproducibility trials. A synchronous quiescent Capsule rerun restored its declared unchanged-input premise and passed **17/17**. This is recorded as a harness artifact, not reclassified silently.

## Self-use
Gen12 replayed its own early rejected routing-baseline implementation against the same sealed epoch and reproduced the real defect: the rejected branch used a generic original-decision baseline rather than the sealed Gen11 route. The final design fixes it. Self-use also drove direct Capsule mutation-inventory inspection; the frozen gold was never weakened.

## Protected state / containment
- zero forbidden protected-state changes; trace growth is prefix-preserving append-only audit only
- private/control targets blocked; no host-control sockets; host repo not visible in guest
- no Gen12 `/var/tmp` transfer/archive debris remains

## Final Twin checkpoint
- **198 nodes / 300 edges / 102 inputs**
- graph `2eff93563f5fe4f3af8d524f15a025a0f09220148ce3f8305f9cc034bcd13fb8`
- snapshot SHA256 `9f10358f396ad515724d50fafe500b33de80772c1018eae0b12ff18a65eacd9e`
- causal digest `6aa5a59232e6c5f325a18a19904526d4707031070e43e9177a883ebfcf79f714`
- verify **PASS, zero issues at checkpoint**
- the outer Lab call appends one normal trace event after the checkpoint returns; that event is valid next-epoch evidence.

## Gen13 direction
The system is now **ready for a bounded outward fork**. Ranked #1 is **Project Onboarding + Domain Capability Expansion Pilot**, with Hierarchical Experiment Isolation second. See `lab_generations/GEN13_PROPOSALS.json`.

## Recursive MCP rule
Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through Lab shell.

## Final canonical validation
- canonical project tests: **13/13 PASS**
- mutation-free Python syntax: **40 files PASS**
- JSON/JSONL: **89 JSON, 2 JSONL / 116 records PASS**
- secret/credential scan: **PASS**
- `git diff --check`: **PASS**
- containment/protected-state: **PASS**, zero forbidden mutations
- Gen12 temp/archive debris: **none**
- final acceptance validated at `2026-08-26T21:43:04.694230+00:00`
