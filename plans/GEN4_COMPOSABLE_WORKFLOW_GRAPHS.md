# Generation 4 — Composable Workflow Graphs + Lifecycle Transactions

Status: **IMPLEMENTING**

## Mission
Generation 4 evolves `Optiplex_Lab + mcp-lab`, not the frozen `Optiplex_MCP`. Generation 3 made individual procedures reusable and cut repeated workflow-authoring bytes by 67.4%, but the Gen-3 benchmark still required 18 reusable-workflow invocations, including 8 lifecycle/recovery calls. A normal Lab update still required ChatGPT to sequence `lab-self-evolve → lab-candidate-verify → lab-accept-current → lab-post-update-verify`.

The Gen-4 target is one auditable high-level lifecycle invocation that composes immutable child workflows while preserving every underlying Code Mode artifact and keeping `CANDIDATE_INSTALLED`, verification, and `ACCEPTED` distinct.

## Designs compared

### A — Nested declarative workflow calls
Extend `workflow_skills.py` with a `workflow`/`call` step that invokes another `name@version` workflow inline.

Advantages:
- smallest code delta;
- natural fit for ordinary sequential composition;
- child workflow identity can be retained in the parent trace.

Limitation discovered from the accepted Gen-3 lifecycle semantics:
- `lab-self-evolve` ends in Code Mode `self_update`, which schedules an MCP service restart after the child returns;
- an in-process parent has no independent durable transaction state and can race the scheduled restart or be killed with the MCP process;
- adding restart persistence/checkpoint semantics directly into the reusable-workflow compiler would duplicate lifecycle machinery and blur the existing child-workflow abstraction.

### B — Explicit guest-local workflow DAG / transaction runner — **chosen**
Add a separate guest-local program that stores immutable composite graph definitions. Each graph node invokes an existing immutable reusable workflow by explicit `name@version`. The graph runner owns dependency ordering, preflight, bounded retries, restart checkpoints, recovery branches, persistent transaction state, and compact parent results. Child execution remains `workflow_skills.py → Code Mode`; no child procedure is copied into the graph.

Why it wins:
- the runner can execute as a durable systemd job independent of the MCP service;
- it can checkpoint before/after restart, observe MCP PID turnover and local readiness, then continue candidate verification and explicit acceptance;
- it preserves the existing workflow and Code Mode layers rather than adding another execution primitive to them;
- it needs no permanent MCP schema change.

The extra mechanism is intentionally narrow: a bounded DAG/transaction runner, not a general autonomous-agent framework.

## Accepted graph model
A composite definition contains:
- immutable `name`, `version`, description, SHA256 identity;
- typed parent parameters using the same Gen-3 parameter types;
- explicit nodes with unique IDs and dependencies;
- exactly one immutable child reusable-workflow reference per node (`name@version` required);
- structured parent-parameter and child-result mapping;
- `run_if = success|failure|always`;
- bounded attempts and delay;
- optional `restart_boundary` checkpoint;
- optional explicit `recovers` list for recovery nodes;
- per-graph limits bounded by hard maximum node/invocation/depth/time limits.

Static/pre-execution gates:
- parent parameter validation;
- explicit child version requirement;
- child existence/hash resolution;
- unknown/missing child parameter rejection before destructive execution when mappings are resolvable from parent inputs;
- DAG dependency validation and cycle detection;
- node/invocation/retry/timeout bounds.

## Transaction persistence
Each invocation gets `/var/lib/optiplex-lab/graph-runs/<run-id>/` with:
- immutable graph snapshot;
- raw input file mode 0600 for resumability;
- safe/redacted parameter representation in state/result/trace;
- node state and attempt ledger;
- child workflow identity/hash/version;
- child Code Mode run/result paths;
- restart checkpoint state and MCP PID before/after;
- parent result with changed-file union, retries, recovery actions, and child artifact pointers.

Completed nodes are not rerun on resume. A node that was durably checkpointed between children resumes normally. An ambiguous node left `RUNNING` by a hard process kill fails closed rather than blindly repeating a potentially destructive child.

## Restart-safe lifecycle transaction
Canonical `lab-upgrade-transaction@1` composes:
1. `lab-self-evolve@1` — install candidate, leave build `CANDIDATE_INSTALLED`, schedule restart;
2. restart checkpoint — graph runner waits for MCP service PID turnover and local port readiness;
3. `lab-candidate-verify@2` — verify Lab/Code Mode/workflow-graph systems and containment while old LKG remains available;
4. `lab-accept-current@2` — only after verification, promote live source to LKG and mark `ACCEPTED`;
5. `lab-post-update-verify@2` — re-run accepted-state/LKG/containment verification.

A successful restart alone never implies acceptance.

Canonical `lab-recovery-transaction@1` composes the deliberate bad-candidate recovery fixture, restart checkpoint, explicit re-acceptance, and post-verification.

## Safety bounds
Initial hard bounds:
- maximum graph nodes: 32;
- maximum child workflow invocations: 32;
- maximum attempts per node: 3;
- maximum graph nesting depth: 1 in Gen-4 (graphs compose workflows, not other graphs);
- maximum child timeout: 3600 seconds;
- dependency cycles rejected before execution;
- restart-boundary readiness wait bounded;
- no recursive MCP protocol calls; `/opt/optiplex-lab/mcp_probe.py` remains forbidden synchronously through Lab shell.

## Measurement plan
Extend, do not replace, Gen-1/2/3 regression evidence. Gen-4 benchmark covers the requested 18 cases and records:
- correctness and containment hard gate;
- parent graph invocation count;
- child reusable-workflow invocation count;
- Code Mode invocation count;
- ChatGPT/MCP interaction proxy;
- authored invocation bytes/context proxy;
- new procedural steps authored for reuse;
- retries, elapsed time, output proxy, raw-shell share;
- restart checkpoint and resume success;
- recovery success.

Primary lifecycle comparison:
- Gen-3 normal update: 4 ChatGPT-authored reusable-workflow calls;
- Gen-4 normal update: 1 parent graph invocation, with the same child workflow/Code Mode evidence retained.

## Schema policy
Prefer guest-local composition. Generation 4 is expected to keep the MCP tool surface at exactly 10. A connector refresh/new chat is required only if the permanent MCP schema changes; this design does not require one.
