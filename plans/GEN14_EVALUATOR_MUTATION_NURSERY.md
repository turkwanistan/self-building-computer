# Generation 14 — Evaluator Mutation Nursery + Benchmark Hardening

## Thesis

**Test the testers.** Gen14 uses the accepted Gen13 hierarchical-isolation substrate to mutate evaluator assumptions in one physically isolated Experiment Capsule, then measures whether independent candidate fixtures and protocol checks kill those evaluator mutations. The goal is evidence about evaluator detection power, not arbitrary benchmark difficulty and not production-system mutation.

## Entry evidence

- Operational Lab remains `gen6-experience-memory-r1`, build `gen6-experience-memory-r1-dc0d2cb41595`, server == LKG `dc0d2cb41595a9a3d953873879ccc3e0bd88db2b4dcdee4cf8aa43dd4cb103e9`, recovery `ACCEPTED`, 10 permanent MCP tools.
- Accepted Gen13 capability: `gen13-hierarchical-experiment-isolation-r1`, build `gen13-hierarchical-experiment-isolation-r1-9a32955b79c6`, benchmark 37/37.
- Gen13 hierarchy SHA `9a32955b79c63efd1023ca1741bff61ab2b0ed5dfb3eaea0aa817b777421a372`; Experiment Capsule SHA `e1276653cde8c0fd9df2a0ebddc5ca5fb148e939ea182996a80563b6b60c05a8`; Counterfactual Replay SHA `6d7f32a86ce73501feecffd21ba6ca319de548f9b29044c9e737baba824dbac0`.
- Entry Twin required refresh after normal append-only Lab audit growth and then verified fresh at 202 nodes / 311 edges / 104 inputs, graph `8f8b1e1e53e94cc6fa963353692796fbe5481a1f8f3f7087cd265c21b70b8128`, zero issues.
- Pre-existing working-tree changes `ideas.md` and `host/check_chatgpt_ui_staleness.sh` are unrelated and must remain untouched by Gen14.

## Frozen acceptance rule

`lab_generations/GEN14_GOLD.json` is created before the primary nursery engine. It is immutable for the rest of Gen14. A mismatch between the recorded frozen-gold SHA and the file on disk is a hard failure.

## Architecture considered

### A. Arbitrary source mutation of accepted evaluators
Directly edit `/opt/optiplex-lab` evaluators and restore afterward. This is easy but needlessly risks accepted state and makes provenance ambiguous. **Rejected.**

### B. One independent Capsule per mutant
Each mutation owns an independent physical Capsule. This is safe in isolation but loses the Gen13 parent/child lineage, complicates shared-fixture equivalence, and makes cross-mutant provenance less comparable. **Rejected as the primary nursery protocol.**

### C. One Gen13 root experiment + delegated sequential mutation/evaluation children
The root owns one Gen8 Capsule. A preparation child writes only a content-addressed nursery workspace. Baseline and mutant evaluators run as delegated children against the same pinned cases. Accepted evaluator source is copied, never edited in place. Actual workspace mutations are reconciled from the Capsule upper layer. **Chosen.**

### D. Custom evaluator DSL only
A DSL would make mutation operators easy but would not prove the system can challenge real Gen8–Gen13 evaluators. **Useful for unit fixtures only; insufficient for self-use.**

## Mutation specification

A mutation spec is deterministic JSON with:

- schema/version;
- evaluator lineage: path, SHA256, adapter kind, callable/entrypoint identity;
- evidence/case bindings and expected candidate decisions;
- mutation class and typed mutation payload;
- declared target path and delegated workspace scope;
- authority set;
- danger/criticality classification;
- evaluator-result protocol requirements;
- timeout and result policy.

The semantic mutation identity excludes timestamps, PIDs, random Capsule IDs, run directories, and durations. The ID is content-addressed from the canonical semantic spec plus pinned evaluator/evidence hashes.

## Supported safe mutation classes

1. `threshold_change`
2. `assertion_delete`
3. `assertion_invert`
4. `fixture_substitute`
5. `evidence_omit`
6. `stale_evidence_inject`
7. `trust_declared_state`
8. `scoring_weight_change`
9. `fail_open_change`
10. `negative_control_corrupt`

Mutations are restricted to copied evaluator/fixture material beneath the nursery workspace. Accepted-state source, frozen gold, operational build/LKG/recovery, registries, and undelegated evidence paths are forbidden targets.

## Evaluation protocol

For every mutation:

1. validate schema, evaluator lineage hash, evidence bindings, mutation class and target;
2. establish one Gen13 root experiment / one Gen8 physical Capsule owner;
3. delegate a preparation/mutation child scoped only to the content-addressed workspace;
4. run baseline evaluator and mutant evaluator sequentially against identical pinned candidate cases;
5. require machine-readable result envelopes identifying checks run, skipped checks, critical failures, decision, and evaluator digest;
6. compare both results to independent case oracles and to each other;
7. classify mutation as `KILLED`, `SURVIVED_REDUNDANT_OR_EQUIVALENT`, `SURVIVED_DANGEROUS`, or `INVALID_FAIL_CLOSED`;
8. preserve mutation provenance and observed Capsule mutation evidence;
9. clean the physical Capsule; never promote evaluator changes automatically.

A crash, timeout, malformed result, skipped critical check, claimed PASS with missing checks, forged lineage, authority/scope expansion, or evaluator result that cannot be bound to the executed mutant is fail-closed. A mutation whose intended weakening is not exposed by the case suite is a surviving mutation; critical/dangerous survivors block acceptance until the evaluator/benchmark is hardened or the survivor is proven equivalent/redundant with evidence.

## Detection-power reporting

Gen14 reports:

- overall and dangerous mutation kill rates;
- killed/surviving mutations by class;
- surviving dangerous mutations;
- per-check unique contribution where a single-check mutation reveals a case missed otherwise;
- redundant/equivalent check candidates where deletion changes no case and an independent guard still proves the invariant;
- malformed/crash/timeout/protocol-rejection counts;
- baseline-vs-mutant decision matrix;
- deterministic semantic result digests.

## Self-use target

Primary real-evaluator self-use targets Gen7 `architecture_twin.verify`, because it has a meaningful independent fail-closed property and does not own another Capsule lifecycle. Controlled stale/missing/newer-evidence fixtures let Gen14 challenge fail-open behavior, stale-evidence handling, assertion/check deletion, and trust of declared versus observed state without wrapping a retained benchmark that already owns isolation.

The self-use should also encode regressions for weaknesses exposed in prior generations (declared-vs-observed trust, skipped-check PASS, stale evidence, and benchmark-debris assumptions) without mutating the original historical artifacts.

## Scope exclusions

No project onboarding, no domain capability expansion, no autonomous evaluator promotion, no permanent MCP tool additions, no modification of `Optiplex_MCP`, no concurrency requirement, and no recursive synchronous `mcp_probe.py` execution.

## Retained regression strategy

Use the mutation-safe/version-pinned strategies already documented by Gen13. Gen10/Gen12 and other benchmarks that own native Capsule/epoch semantics run directly with their historical preconditions restored rather than being casually nested under Gen14. Gen13 must remain exactly 37/37.

## Acceptance

All frozen Gen14 gold checks must pass; designated dangerous mutants must have zero unexplained survivors; at least one real prior-generation evaluator mutation must be killed; full Gen2–Gen13 retained regressions pass; protected accepted state remains unchanged except prefix-preserving outer audit growth; containment and exact 10-tool operational surface remain intact; final Twin is rebuilt and verifies zero issues; canonical tests/syntax/JSON/secret/diff/debris gates all pass.
