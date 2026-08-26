# Generation 3 — Reusable Workflow Synthesis + Skill Compiler

Status: **ACCEPTED PENDING FINAL HANDOFF SYNC**

## Mission
Generation 3 evolved `Optiplex_Lab + mcp-lab`, not `Optiplex_MCP`. Generation 2 had already reduced mechanical MCP orchestration from an estimated 44 interactions to 12 Code Mode invocations, but ChatGPT still authored a fresh multi-step workflow JSON for repeated procedures. Generation 3 makes successful procedures reusable, parameterized, versioned, discoverable, and auditable.

## Starting gate
This fresh ChatGPT session directly discovered exactly the accepted 10-tool Gen-2 Lab connector before any guest shell use and called `lab_status` first. It matched `gen2-code-mode-r1`, build `gen2-code-mode-r1-154492ee9972`, server SHA `154492ee997227a4bc61b733d4e1724bc7689ead22ebc0173fce51e97a5814b5`, and Code Mode SHA `2e0ea4e97541dcc48bbda3542be1e195d8fad2971931d1b7ae48cdb33202df77`. Gen-2 self-test was 12/12, Code Mode self-test 4/4, legacy benchmark 17/17, orchestration benchmark 12/12, containment passed, and the frozen safe MCP remained the accepted 51-tool identity.

## Designs compared
### A — Declarative reusable workflow registry/compiler (chosen)
Keep Code Mode as the execution engine. Store named/versioned workflow definitions with typed parameter schemas. Compile structured parameter nodes into an exact concrete Code Mode workflow, retain that compiled workflow, and execute it through the existing runner. Successful Code Mode runs may be promoted into reusable definitions with provenance.

Advantages:
- preserves existing typed operations, step tracing, diffs, artifacts, retries, rollback, jobs/services, and LKG self-update;
- validates parameters before execution;
- structured substitution is auditable and avoids arbitrary text templating;
- compact invocation is just workflow identity + parameter object;
- no permanent MCP tool/schema change.

### B — Generated procedural wrappers/scripts
Generate a Python/shell wrapper for each successful workflow and invoke the wrapper with arguments.

Rejected as the default because it duplicates Code Mode execution semantics, creates another procedural layer to audit, and tends to turn parameter interpolation back into shell/script-generation problems. Scripts remain an escape hatch inside the unrestricted guest, not the reusable-workflow substrate.

## Accepted implementation
### Code Mode `gen3-code-mode-r1`
Generation 3 preserves all Gen-2 operations and adds direct `argv` execution for `command` and `job`. Parameterized commands can therefore receive literal values without passing them through `/bin/bash -lc`. Shell `command` remains available where a real shell program is intentionally required.

Compiled reusable workflows add `_reusable` identity/provenance and safely represented `_parameters` to Code Mode results. The concrete compiled workflow and underlying Code Mode run remain on disk, so abstraction does not hide execution.

### Reusable workflow system `gen3-workflow-skills-r1`
Guest program: `/opt/optiplex-lab/workflow_skills.py`.

Capabilities:
- immutable `name@version` definitions and SHA256 identity;
- active-version pointer via `CURRENT`;
- list/show/register/compile/run;
- parameter types `str`, `path`, `int`, `float`, `bool`, `enum`, `list[str]`;
- required/default/min/max/pattern/absolute-path validation;
- structured `$param`, `$path_join`, and `$concat` substitution;
- safe representation for sensitive parameters;
- pre-execution rejection of missing, unknown, or invalid parameters;
- successful Code Mode run promotion with exact-scalar parameterization and source-run provenance;
- workflow-level traces plus the unchanged underlying Code Mode step trace;
- compact results with large outputs retained as Code Mode artifacts.

A Gen-3 implementation test exposed a CLI bug: `workflow_skills run` originally returned process exit 0 even when the underlying Code Mode run failed. The reusable `exact-replace` workflow was then used to patch the tool itself; failed reusable workflows now return exit 1.

## Reusable lifecycle state machine
The first post-self-update verification correctly failed because the existing self-update primitive installs a candidate while preserving the previous LKG. Generation 3 made that lifecycle explicit instead of weakening the check:

1. `lab-self-evolve` — create/edit/compile/startup-smoke/install candidate; restart is scheduled.
2. `lab-candidate-verify` — run functional and containment gates while the prior LKG remains available.
3. `lab-accept-current` — after verification, promote live source to LKG and mark build `ACCEPTED`.
4. `lab-post-update-verify` — verify tests, accepted LKG equality, and containment.
5. `lab-bad-candidate-recovery` — inject the standard fast-crash fixture and verify launcher rollback.

This preserves the Generation-2 recovery model while making acceptance auditable and reusable.

## Self-hosting demonstration
Generation 3 used its own `lab-self-evolve` reusable workflow to modify the live Lab MCP status output. Run `cm_20260826T050951Z_5b36f51e` performed 5 steps: copy candidate, deterministic edit, pycompile, isolated startup smoke, and LKG-protected self-update. Durable job `job_ab7e9cf52335` survived the MCP restart and completed successfully.

The accepted server now advertises the Gen-3 Code Mode and reusable-workflow identities in `lab_status` while preserving exactly the same 10-tool MCP schema.

## Benchmark
The Generation-3 workflow benchmark passed **16/16** in 24,767.96 ms. It covered registration/discovery, parameter validation, repeated reuse, multi-file edits, compile/test, service/job, large output, public-repo investigation, candidate validation, promotion/provenance, self-update/restart, deliberate bad-candidate recovery, and containment.

Key comparison:
- Gen-2 mechanical baseline: 44 estimated manual interactions -> 12 Code Mode workflow invocations (72.7% reduction).
- Gen-2 authored workflow JSON proxy for matched stored workflows: 5,611 bytes.
- Gen-3 compact workflow+parameter invocation proxy: 1,829 bytes.
- Authoring reduction: **67.4%**.
- Newly authored procedural steps when reusing a workflow: **0**.
- Gen-3 benchmark reusable invocations: 18 across the expanded 16-task suite.
- Underlying Code Mode steps: 57.
- Raw-shell command steps: 10/57 = **17.5%**; parameterized execution preferentially used literal argv.
- Bounded retries: 2.

The benchmark itself ran as a durable Lab job and survived both the self-update restart and the deliberate bad-candidate recovery restart.

## Generation 4 evidence
The Gen-3 failure miner ranks **Composable workflow graphs + lifecycle transactions** first. The remaining orchestration is no longer repeated step JSON; it is sequencing multiple reusable workflows. In the benchmark, 8 of 18 reusable invocations were lifecycle/recovery invocations, with a normal self-update cycle requiring four named workflows and bad recovery requiring three. Generation 4 should make reusable workflows composable while retaining underlying Code Mode traces and explicit acceptance gates.

Do not implement Generation 4 from this document.

## Deadlock rule
Never execute `/opt/optiplex-lab/mcp_probe.py` synchronously via `Optiplex_Lab.shell`. It recursively waits on the same MCP server servicing the originating call. Prefer connector schema discovery or detached/out-of-band probing.
