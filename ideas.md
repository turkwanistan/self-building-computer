# Self-Building Computer — Future Evolution Ideas

> Research architecture memo, 2026-08-26. This document is intentionally **research and synthesis only**. It does not authorize or implement a future generation.

## 1. Current system snapshot

### Authoritative state discovered

A live transition occurred **during this research session**, so the correct snapshot needs one important distinction:

- The **live Lab is now Generation 4**, `gen4-workflow-graphs-r1`.
- The **last fully finalized canonical repository handoff is still Generation 3**, because `STATUS.md`, `NEXT_SESSION.md`, and `state/current.json` had not yet been updated when this document was finalized and the Gen4 result/benchmark handoff artifact was not yet present.
- The live guest build is nevertheless guest-accepted: `/etc/optiplex-lab/build.json` reports `recovery_state=ACCEPTED`, and live `lab_status` reports the Gen4 identity.

Current live identity observed:

- Scope under evolution: **`Optiplex_Lab + isolated mcp-lab VM`**.
- Frozen host/control reference: `Optiplex_MCP`, release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, policy `authority-v1`.
- Live Lab generation: `gen4-workflow-graphs-r1`.
- Live build: `gen4-workflow-graphs-r1-4558bdb23e52`.
- Live server SHA256: `4558bdb23e52572c6a13978a6ed10f9dc6fef26d1ae27abd0bd560c9fd1d63ac`.
- Recovery state: `ACCEPTED`; live source SHA equals guest last-known-good SHA.
- Code Mode remains `gen3-code-mode-r1`, SHA256 `d6c1b55e4152a66dc9732ed333853f22bea1442c163be5e3082c36a860fa1264`.
- Reusable workflow system remains `gen3-workflow-skills-r1`, SHA256 `895bcc0a76fb82959a79bd445b11354bd4be22db88443521ccb280cc47cfbea4`; live registry now reports 16 workflow version files.
- New live graph layer: `gen4-workflow-graphs-r1`, SHA256 `6f154fac78978f05fb101c43fd802a215ed3819bb338b755e0a693fa3fbb70c6`; two composite graphs are registered.
- Lab MCP surface is still exactly **10 broad primitives**: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
- Permanent MCP tools added by the live Gen4 design: **0**.
- Guest resources observed: 2 vCPU, ~1.9 GiB RAM, no swap, ~27 GiB free disk; `/dev/kvm` is exposed to the guest. Docker/Podman/Firecracker/QEMU userland is not currently installed.

For this document, **“current generation” means Gen4 live/in-progress**. Claims that require a completed generation benchmark remain anchored to Gen3 evidence until the separate Gen4 implementation session finishes its canonical handoff.

### What the Lab can already do

The Lab is no longer merely a root shell in a disposable VM. It has a small self-hosting substrate:

1. **Observe itself.** Sanitized JSONL trace/outcome ledger, bounded output previews, large-output spooling, build identity, benchmark artifacts, and a failure miner.
2. **Operate durably.** Guest jobs survive MCP restarts; services can be managed; self-restart is asynchronous; an invalid MCP candidate can automatically restore last-known-good source.
3. **Modify itself.** Code Mode provides auditable inspect/copy/edit/patch/command/assert/service/job/self-update steps with bounded retries and automatic rollback of reversible edits.
4. **Reuse successful procedures.** Gen3 workflows are immutable `name@version` objects with SHA identity, typed parameters, safe literal `argv`, structured substitution, compilation into concrete Code Mode, and provenance back to successful runs.
5. **Exercise a real candidate lifecycle.** `lab-self-evolve` → `lab-candidate-verify` → `lab-accept-current` → `lab-post-update-verify`, plus deliberate bad-candidate recovery.
6. **Generate evidence about its own friction.** The failure miner ranks future directions from trace and benchmark data rather than from fashion alone.
7. **Compose reusable workflows durably.** The live Gen4 graph runner references immutable child `workflow@version` definitions, validates DAG structure/parameters, checkpoints restart boundaries, persists transaction state, supports explicit recovery nodes, and resumes completed-node state without blindly replaying ambiguous destructive work.

### Current evidence

- Gen1 benchmark: 17/17 before and after; feature coverage moved 0/5 → 5/5; representative recorded elapsed time fell from ~20.1 s to ~7.4 s.
- Gen2 orchestration benchmark: 12/12; estimated mechanical interaction proxy fell **44 → 12**, a **72.7% reduction**.
- Gen3 workflow benchmark: 16/16; repeated procedure authoring proxy fell **5,611 → 1,829 bytes**, a **67.4% reduction**; newly authored procedural steps for reuse = 0.
- Gen3 benchmark executed 18 reusable workflow invocations over 57 underlying Code Mode steps; raw shell steps were 10/57 = **17.5%**; bounded retries = 2.
- Current failure-miner trace scan saw 41 workflow invocations and 271 Code Mode steps, dominated by `command` and `exact_replace`; observed step failures were heavily concentrated in `exact_replace`.
- Two restart/recovery tasks accounted for roughly 70.7% of the Gen3 workflow benchmark elapsed time.
- Live Gen4 graph self-test: **8/8 PASS**, including unknown-child rejection, cycle rejection, invocation bounds, sequential child execution, checkpoint/resume, and explicit failure recovery. A live `lab-upgrade-transaction` graph run completed through an MCP restart checkpoint.
- **No finalized Gen4 generation benchmark/result artifact was present at document finalization**, so Gen4 should not yet be credited with the planned 4→1 lifecycle interaction reduction until that evidence lands.

### Containment model

The **outer VM is the security boundary** and should remain so.

The guest deliberately has root and public internet. It deliberately does **not** have host credentials, host filesystem mounts, host Docker/libvirt/Tailscale sockets, private LAN/Tailscale reachability, the protected host MCP endpoint, or production authority. The canonical host repository is likewise not mounted in the guest: a direct attempt from the live Lab to enter `/home/mcp/projects/projects/self-building-computer` failed because that path does not exist in the VM.

That is a useful architectural separation. Future autonomy should grow **inside** the guest and export evidence/artifacts through mediated channels; it should not acquire host credentials or sockets simply to feel more autonomous.

---

## 2. Evolution so far

### Bootstrap — two worlds, intentionally unequal

The original architecture separated a boring, authority-bearing host control plane from an unrestricted but isolated experimental machine. The host gained an immutable blue/green lifecycle, fixed front door, root-owned state, fresh-session verification, promotion, and rollback. The Lab received root, public internet, a known-good VM snapshot, and seven broad MCP tools, but no meaningful host authority.

A crucial historical correction happened before the first real Lab generation: an early Gen1 plan partially described evolving the safe MCP. The project explicitly corrected scope so **Optiplex_Lab and `mcp-lab` are the evolving organism; Optiplex_MCP is the frozen control/reference plane**. That correction is now part of the durable story.

### Generation 1 — Eyes, memory of failure, and a recovery reflex

**Thesis:** The Lab should be able to observe how it works before deciding how to improve itself.

Added:

- sanitized trace/outcome recording;
- bounded large-output spooling + `read_range`;
- real-task benchmark harness;
- failure mining into ranked proposals;
- initial reusable skills;
- `lab_status` identity/introspection;
- safe asynchronous self-restart;
- durable job behavior across restarts;
- guest-local last-known-good auto-rollback.

The MCP surface grew from seven to ten broad primitives. The important leap was not tool count: the Lab acquired **fitness evidence and recoverability**.

### Generation 2 — Code Mode

**Thesis:** Mechanical engineering choreography should execute locally as one auditable program instead of bouncing through ChatGPT one tool call at a time.

Gen2 chose a declarative JSON workflow runner over generated ad-hoc scripts. Code Mode introduced typed step semantics, deterministic exact replacement, checked Git patches, bounded retries, file rollback, jobs/services, self-update, compact results, artifacts, and traceable step boundaries.

The best evidence is the 44 → 12 mechanical-interaction proxy. More importantly, the Lab used Code Mode to modify its own MCP and survived restart and deliberate bad-candidate testing.

### Generation 3 — Reusable workflow synthesis

**Thesis:** A successful audited procedure should become a reusable capability instead of being re-authored as workflow JSON.

Gen3 added a registry/compiler around Code Mode:

- immutable `name@version` + SHA identity;
- typed/defaulted/required parameters;
- `$param`, `$path_join`, `$concat` structured compilation;
- literal `argv` for parameterized execution;
- discovery/show/register/compile/run;
- promotion of successful Code Mode runs with provenance;
- retained concrete compiled workflow and underlying trace;
- explicit candidate verification, acceptance, post-verification, and recovery recipes.

The system even caught and repaired an error in its new abstraction: failed reusable workflows initially exited process status 0. Gen3 used its own `exact-replace` workflow to patch the workflow system so failure now propagates correctly.

### Generation 4 — Composable workflow graphs, live transition

**Thesis:** A compound lifecycle should be one restart-safe, auditable transaction rather than several manually sequenced reusable workflows.

While this research session was underway, another generation session installed `gen4-workflow-graphs-r1` into the live Lab. The implementation deliberately chose a separate guest-local DAG/transaction runner over adding nested calls directly inside `workflow_skills.py`.

Observed/current design includes:

- immutable graph `name@version` + SHA identity;
- graph nodes referencing immutable child reusable workflows rather than copying their procedures;
- typed parent parameters and child-result mappings;
- dependency/cycle validation and hard node/invocation/retry/timeout bounds;
- `run_if=success|failure|always` plus explicit `recovers` relationships;
- persistent graph-run state under `/var/lib/optiplex-lab/graph-runs/`;
- restart-boundary checkpoints that observe MCP PID turnover/readiness;
- completed-node resume and fail-closed handling of ambiguous `RUNNING` nodes;
- canonical `lab-upgrade-transaction@1` and `lab-recovery-transaction@1` composites;
- no permanent MCP schema change.

The live guest build is already marked `ACCEPTED` at the LKG/recovery layer and the graph self-test is 8/8. However, the repository still described Gen4 as `IMPLEMENTING`/Gen3 as the canonical lifecycle phase when this memo was finalized, and no completed Gen4 generation benchmark/result handoff was yet present. Therefore Gen4 is treated here as **real live capability, but a generation transition still awaiting its final evidence/handoff**.

### The evolutionary pattern

The ladder is now:

**Gen1: observe → Gen2: execute locally → Gen3: remember procedures → Gen4: compose procedures durably.**

The frontier has moved beyond composition. The next meaningful leap is **capability invention + evidence generation + retention**, followed by comparative experimentation and cumulative self-knowledge.

---

## 3. Current capability frontier---

## 3. Current capability frontier

### 1. What can it already do surprisingly well?

It can self-edit an MCP server, compile/smoke-test it, install it, survive its own restart, preserve a prior LKG, run candidate/containment gates, accept the candidate, deliberately break itself, recover, and retain exact traces—all while exposing only ten generic MCP primitives. That is already a meaningful self-hosting substrate.

It also has a useful abstraction stack: ChatGPT intent → **Gen4 workflow graph** → reusable workflow → compiled Code Mode → typed local operations → jobs/services/files. Each lower layer remains inspectable, and the live graph layer preserves child workflow/Code Mode identities across restart boundaries.

### 2. What still requires significant ChatGPT reasoning or orchestration?

- recognizing a genuinely new capability gap;
- deciding whether the solution should be a one-off script, reusable workflow, package, service, Code Mode primitive, or MCP change;
- deciding **which** reusable workflows/capabilities should form a novel goal graph when no canonical graph already exists;
- designing novel edits rather than supplying exact old/new strings;
- interpreting unfamiliar failures and choosing a recovery experiment;
- inventing benchmarks for new capabilities;
- comparing competing implementations;
- deciding what evidence is sufficient for retention/promotion;
- reconstructing enough architecture/history in every fresh design session;
- mirroring accepted guest work into canonical host-side history/handoff without violating the boundary.

### 3. What is mechanical/repetitive?

Gen4 is specifically removing the previously measured lifecycle sequencing burden by wrapping the update/recovery chains in restart-safe composite graphs. Until its final benchmark lands, that reduction is an implemented hypothesis rather than a finalized metric. Beyond it, repeated verification summarization, exact-string edit manufacture, benchmark authoring, failure triage, capability packaging, and repository handoff remain mechanical. Exact-string edits remain especially common and failure-prone in existing traces.

### 4. What requires unnecessary context?

A fresh architect currently needs several status/state/history/planning files plus live identity and workflow knowledge to reconstruct “what is safe, what exists, why it exists, what failed, and what is next.” The project has good handoff discipline, but there is no generated task-specific **context product**. Skills are reusable procedures, not yet a semantic memory system that selects only the few facts needed for a problem.

### 5. What prevents the Lab from evolving itself more independently?

The central limitation is **not lack of root**. The Lab already has root. It lacks a closed, evidence-gated capability-acquisition loop:

> detect gap → formulate experiment → create missing capability → create/choose tests → run alternatives → diagnose failures → retain or discard → update procedural/self knowledge.

Today ChatGPT supplies most of the intelligence around that loop. The Lab is strong at executing known procedures but weak at **inventing and adjudicating unknown ones**.

The host boundary also intentionally prevents direct canonical-repo persistence and host snapshot control. This should be handled by artifact export/handoff, not by giving the guest host authority.

### 6. What observability is missing?

The JSONL trace is excellent for Gen1, and Gen4 adds graph→child-workflow identities plus restart checkpoints. Future evolutionary work still wants richer causal structure across the whole system:

- unified parent/child relationships across intent → graph → workflow → Code Mode → job → restart → evaluator → decision;
- explicit experiment/candidate lineage;
- “why this branch was selected” decision records;
- benchmark/evaluator identity and version;
- input/context artifact hashes;
- resource/cost budgets;
- capability applicability and success statistics;
- failed and rejected descendants, not only the winner;
- an easy queryable view of architecture and historical causal chains.

### 7. What is blocked by architecture rather than implementation?

Deliberately blocked:

- direct guest write access to the host canonical repository;
- guest control over host libvirt snapshots;
- host credentials, private network, production deployment, safe-MCP authority;
- easy cloud-model APIs unless credentials are intentionally mediated elsewhere.

Not architecturally blocked:

- arbitrary guest-local code/tool synthesis;
- nested process/container/possibly KVM experiments inside the outer VM;
- local event loops;
- self-hosted databases/services;
- guest-local browser automation;
- durable experiment journals;
- candidate branches and lineage archives;
- automated local benchmarks, fuzzing, mutation tests, or synthetic environments.

### 8. What parts are too bespoke?

- Gen4 now provides a composition/transaction primitive, but it is still lifecycle/workflow-centric rather than a general **capability experiment** substrate;
- failure mining currently emits a fixed small family of proposal templates;
- exact-string edits encode too much procedure-specific text;
- handoff/state summaries are manually curated;
- benchmarks are hand-authored per generation rather than generated from capability contracts/invariants;
- workflow promotion parameterizes successful concrete runs but does not yet infer applicability conditions or consolidate repeated variants.

### 9. Where could the Lab dynamically create capabilities instead of pre-building them?

Nearly everywhere above Code Mode. A missing helper should often become a content-addressed, temporary guest-local **capability capsule** with an interface, tests, provenance, TTL, and optional promotion—not a permanent MCP tool. Examples: an AST transformer, repository analyzer, browser extractor, log parser, benchmark oracle, protocol client, data converter, or one-off service.

### 10. What would make it dramatically more fun, powerful, or alive without weakening containment?

- descendants that compete inside the VM;
- event-triggered curiosity and repair;
- a visible family tree of candidate generations;
- automatic conversion of repeated success into memory;
- “dream” runs that replay old failures against new capabilities;
- self-generated benchmarks and adversarial mutants;
- a structured self-model it can query when planning a change;
- temporary tools that appear because the current problem requires them and disappear when they do not earn retention.

### Frontier classification

**Incremental engineering:** richer edit operations, better trace querying, cached environments, browser skill, improved retry policies.

**Architectural upgrades:** causal observability, self-model/context compiler, reproducible capability capsules, event reactor, and experiment/descendant isolation built on the new Gen4 transaction layer.

**Qualitatively new capabilities:** dynamic capability forge, self-generated benchmarks, descendant competition, procedural-memory distillation, autonomous experiment design, nested evolutionary sandboxes.

---

## 4. Research findings

The useful lesson from current external work is not “install framework X.” It is that several independent fields are converging on a small set of primitives that fit this project unusually well.

### A. Self-improvement works better as search + evaluation than as unconstrained rewriting

The Darwin Gödel Machine maintains an archive/tree of agent variants and empirically evaluates self-modifications rather than assuming the newest rewrite is better [R1]. AlphaEvolve similarly combines generated candidate programs, automated evaluators, a program database, and evolutionary selection [R2][R3]. Live-SWE-agent and Hyperagents explore systems in which the agent scaffold itself can be modified during problem solving [R4][R5].

**Adaptation for this Lab:** retain a population/lineage of candidate *capabilities or runtimes*, but make local deterministic/project benchmarks and containment invariants the fitness gates. “Self improvement” should mean **generate descendants and select by evidence**, not overwrite the only self.

### B. Dynamic tool creation is becoming a real research target

ToolMaker demonstrates agents that package research software into callable tools with dependency setup, generated code, tests, and self-correction [R6]. Tool-Genesis explicitly evaluates task-driven tool creation and maintenance [R7]. Earlier work such as CREATOR established the pattern of creating task-specific executable tools rather than relying only on a fixed tool library [R8]. Current community projects are also experimenting with turning MCP servers into code-level skills and with agents building tools on demand [R30][R31].

**Adaptation:** preserve the ten-tool MCP kernel. Let the guest forge ephemeral typed executables/services/workflows under a capability registry, test them, use them, and promote only those that demonstrate repeat value.

### C. Skills are becoming procedural memory, not just prompt snippets

Recent skill-system research frames skills as lifecycle-managed capabilities with applicability conditions, execution policies, termination criteria, composition, evaluation, and update [R9]. Voyager demonstrated a simpler early version: successful executable behavior enters a skill library and is retrieved later [R10]. Reflexion showed value in retaining compact outcome feedback across attempts without model-weight updates [R11]. OpenHands now uses on-demand progressive-disclosure skills specifically to avoid always injecting full skill content [R12].

**Adaptation:** Gen3 already has the execution half. The missing half is **memory management**: infer when a workflow applies, merge near-duplicates, attach evidence, track success/failure rates, expire weak skills, and retrieve only relevant procedural knowledge.

### D. Durable execution concepts map directly onto self-evolution

Temporal popularized deterministic workflow history plus non-deterministic activities and replay; Restate journals non-deterministic steps and supports version-pinned durable executions; DBOS uses durable workflow identity/checkpointing and database-backed recovery [R13][R14][R15]. Pydantic AI’s durable-execution abstraction explicitly supports several of these backends [R16]. LangGraph’s checkpoint/time-travel model shows a useful debugging concept even if the framework itself is unnecessary here [R17].

**Adaptation:** do not install a heavyweight orchestrator merely because it exists. The live Gen4 graph layer has already adopted the right narrow subset—durable state, version-pinned children, bounded replay/resume, and restart checkpoints. Future generations should extend those semantics only where experiments/capabilities prove they need more.

### E. Reproducibility should be a property of experiments, not a promise in prose

Nix’s core insight is content-addressed/dependency-explicit reproducible environments [R18]. Firecracker and modern sandbox platforms demonstrate fast snapshot/fork patterns for isolated environments [R19][R20]. SWE-ReX decouples agent logic from sandbox runtimes and is designed for parallel software-engineering environments [R21].

**Adaptation:** start lighter than NixOS. Give every experimental capability/candidate an environment manifest, artifact hashes, source hash, and reproducible run command. Later, child microVM snapshots can make entire descendants reproducible.

### F. Benchmarks themselves need adversaries

Hypothesis stateful testing generates action sequences against a modeled system rather than testing only hand-picked examples [R22]. Terminal-Bench’s revisions illustrate that agent benchmarks can contain broken tasks and weak validators, so benchmark maintenance is part of the engineering problem [R23]. SWE-bench-style systems also expose a general risk: agents can optimize to a brittle verifier.

**Adaptation:** a future Lab should generate property/state-machine tests, mutation tests, negative cases, and benchmark-validator checks whenever it creates a new capability. The evaluator must be tested too.

### G. Rich observability is becoming a shared agent primitive

OpenTelemetry is developing GenAI/MCP semantic conventions for tool, agent/workflow, plan, and memory operations [R24]. Phoenix and related OpenInference tooling show how traces, datasets, evaluators, and experiments can share one lineage model [R25].

**Adaptation:** Gen1’s JSONL trace should remain simple, but its schema can become more causal and OTel-shaped so experiments, descendants, workflows, decisions, and benchmark outcomes can be queried as one graph.

### H. Repository-level self-models are practical enough to borrow from

Prometheus and RANGER build repository-level representations combining code structure, cross-file dependencies, and natural-language navigation [R26][R27]. This suggests a useful middle ground between grep and a giant semantic database.

**Adaptation:** maintain a small SQLite/JSON graph of “component → file → workflow → invariant → benchmark → runtime service → generation,” refreshed from deterministic introspection. It should support impact analysis and context compilation, not become a second source of truth.

### I. Browser agents need reproducible worlds, not only public websites

WebArena and BrowserGym/WorkArena emphasize realistic but controlled web environments and explicit task evaluators [R28][R29]. This matters because public websites are flaky, change frequently, and create poor regression fixtures.

**Adaptation:** when browser capability arrives, pair Playwright with local synthetic websites/services inside the guest so browser evolution has deterministic tests. Public web research can remain a separate capability.

### J. Community experience converges on context/tool-loop compression

Recent Hacker News experiments describe generating code-level skills from MCP servers to avoid repeated model↔tool loops and progressively disclose only needed capabilities [R30]. Other HN projects dynamically create tools or expose durable agent workflows through MCP [R31][R32]. LocalLLaMA discussions repeatedly report that long tool loops, context growth, weak checkpoints, and superficial tests are more limiting than raw model intelligence, while some builders advocate small orchestration models plus stronger coding models [R33]. These are anecdotes, not benchmarks, but they align strikingly with this repository’s own 44→12 interaction and 67.4% authoring reductions.

### Research conclusion

The strongest external ideas do **not** argue for a giant general agent framework. They argue for a composable substrate:

**durability + lineage + generated capability + generated evaluation + procedural memory + reversible experiments.**

That is exactly the direction in which this project can remain small while becoming much more autonomous.

---

## 5. Idea catalog

### Idea 1 — Capability Contract Layer

**Class:** Architectural enabler  
**Concept:** Define one small, content-addressed contract for every guest-local dynamic capability: what it does, typed inputs/outputs, side effects, dependencies, tests, provenance, retention state, and how it is invoked.

**Why it matters here:** Gen4 can now durably compose *known reusable workflows*, but the next frontier is creating capabilities that do not exist yet. Without a common contract, a Capability Forge would devolve into a directory full of scripts with incompatible assumptions. This is the missing bridge between the stable 10-tool kernel and dynamic guest-local invention.

**What becomes possible:** Code Mode, workflow graphs, benchmarks, memory, and experiment runners can all discover and invoke a newly created parser/transformer/service through one uniform description without adding an MCP tool.

**Possible architecture:** A capability directory contains:

- `capability.json` with immutable content hash, semantic name/version, description and applicability hints;
- typed input/output schema and literal `argv` or local-service entrypoint;
- declared side-effect classes (`read_files`, `write_workspace`, `public_network`, `service`, etc.);
- environment/dependency manifest;
- test/evaluator references and minimum evidence state;
- provenance to creator episode/graph/context hashes;
- lifecycle state: `EPHEMERAL`, `CANDIDATE`, `PROMOTED`, `SUPERSEDED`, `REJECTED`, `EXPIRED`;
- TTL/cleanup policy for ephemeral artifacts.

Keep the contract descriptive and executable by existing Code Mode/Gen4 graph machinery; do not create a second agent framework.

**Integration point:** New guest-local capability registry beside Gen3 workflows and Gen4 graphs; Capability Forge and Promotion Governor use it.

**Security implications:** Capability contracts cannot grant authority. They only declare side effects within the existing VM. Host access, credentials, sockets, private network, or production authority remain unrepresentable/forbidden.

**Complexity:** Small–Medium  
**Expected payoff:** Significant

**Dependencies:** Gen4 graph layer is a strong execution foundation; no further prerequisite.

**How to benchmark:** Register 20 heterogeneous hand-built temporary capabilities, validate discovery/schema/side-effect declarations, invoke them from Code Mode/graphs, reject malformed or authority-violating manifests, detect duplicate content, and garbage-collect expired capabilities without losing provenance.

**Failure modes:** Recreating package-management standards; contracts that lie about side effects; schema bloat; version churn. Keep runtime enforcement focused on what can be objectively checked and treat descriptive claims as evidence, not truth.

---

### Idea 2 — Capability Forge

**Class:** Qualitatively new capability  
**Concept:** When the Lab encounters a task that its existing workflows cannot express well, it can create a **temporary purpose-built guest-local capability**, define its contract, generate tests, use it, and then discard or nominate it for retention.

**Why it matters here:** Gen3 can promote a *known successful workflow*, but it does not autonomously recognize “I need a repository graph extractor / AST transformer / protocol client / browser parser” and fabricate one. Today ChatGPT supplies that invention step. Adding each such thing as a permanent MCP tool would fight the project’s successful ten-tool philosophy.

**What becomes possible:** The Lab stops waiting for generations to pre-build every utility. New tasks can cause new local capabilities to appear on demand without schema refreshes.

**Possible architecture:** A capability is a content-addressed directory containing:

- `capability.json`: name, version/hash, purpose, typed input/output contract, authority assumptions, TTL;
- executable/script/service entrypoint;
- environment/dependency manifest;
- generated unit/property tests;
- provenance: triggering gap, creator run, source/context hashes;
- benchmark observations;
- retention state: `EPHEMERAL`, `CANDIDATE`, `PROMOTED`, `REJECTED`, `EXPIRED`.

The forge first searches existing workflows/capabilities. If none fits, it synthesizes code in a disposable workspace, validates syntax/unit tests, runs an adversarial smoke fixture, then exposes the capability to Code Mode as a literal `argv` command or local service. Successful repeated use can feed the Promotion Governor and Procedural Memory Distiller.

**Integration point:** Above Code Mode and beside the workflow registry. No permanent MCP schema change is required.

**Security implications:** Generated code is arbitrary guest-local code—which is already within the approved VM authority. It must never receive host credentials/mounts/sockets. Public-internet use should be recorded. Capability manifests should state network/filesystem side effects so benchmarks can detect surprises.

**Complexity:** Large  
**Expected payoff:** Transformative

**Dependencies:** Transactional graphs; Benchmark Nursery or at least a minimal generated-test contract; provenance/observability; promotion policy.

**How to benchmark:** Give 10 unseen tasks deliberately requiring helpers absent from the registry. Measure: successful capability creation, task success, generated-test strength, time/context vs ChatGPT-authored helpers, MCP tool count unchanged, duplicate capability reuse, and correct discard of useless one-offs. Include seeded malicious/broken candidate utilities and require rejection.

**Failure modes:** Tool spam; weak self-written tests that merely bless incorrect code; capabilities secretly encoding one fixture; dependency bloat; inability to know when a new capability is actually needed. Promotion must be harder than creation.

---

### Idea 3 — Benchmark Nursery

**Class:** Qualitatively new capability  
**Concept:** Turn capability gaps, contracts, failures, and invariants into new test/benchmark candidates automatically.

**Why it matters here:** Every generation so far has depended on human/ChatGPT-authored benchmark extensions. The Lab’s future fitness function cannot compound if its tests stay static while capabilities evolve. External benchmark work also shows that evaluators themselves can be buggy or gameable.

**What becomes possible:** A newly forged capability arrives with evidence; a novel failure becomes a regression; untested behavior becomes an explicit fitness gap; candidate descendants cannot win solely by overfitting today’s hand-written suite.

**Possible architecture:** Generate several evaluator classes per capability where applicable:

- contract examples;
- negative cases and invalid inputs;
- property-based tests;
- state-machine action sequences;
- mutation tests against intentionally broken implementations;
- metamorphic tests (equivalent inputs/transformations should preserve defined properties);
- containment/resource invariants;
- replay fixtures mined from real traces;
- evaluator self-tests that verify known bad mutants fail.

Every benchmark item gets version/hash, provenance, oracle type, estimated cost, flakiness score, and `hard_gate`/`fitness_metric` classification.

**Integration point:** Existing benchmark/failure-miner tree; eventually feeds Experiment Arena and Promotion Governor.

**Security implications:** Generated tests execute only in the guest/descendant sandbox. Security/containment invariants remain non-negotiable hard gates and should not be generated away or down-weighted.

**Complexity:** Medium–Large  
**Expected payoff:** Transformative

**Dependencies:** Existing benchmark harness; benefits greatly from Capability Forge, self-model, and descendant isolation.

**How to benchmark:** Seed 20 known implementation mutants across workflow/compiler/recovery fixtures. Ask the Nursery to expand tests from contracts/traces. Score mutation kill rate, false positives on known-good, generated test novelty, flakiness across reruns, and benchmark execution cost.

**Failure modes:** Reward hacking, tautological tests generated from implementation details, flaky network-dependent tests, benchmark explosion, or costly suites that slow every iteration. Use budgeted tiers and holdout mutants.

---

### Idea 4 — Procedural Memory Distiller

**Class:** Architectural upgrade  
**Concept:** Mine repeated successful traces and failure resolutions into compact, versioned procedural memory with applicability conditions—not merely a bag of workflow files.

**Why it matters here:** Gen3 promotion can parameterize one successful Code Mode run. It does not yet decide that three similar episodes are the same skill, infer when it applies, merge variants, track outcomes, expire weak procedures, or progressively disclose the right one.

**What becomes possible:** The Lab becomes cumulatively better at engineering patterns without making every fresh session reload the entire history. “We solved this before” becomes a machine-queryable statement with evidence.

**Possible architecture:** Each memory item stores: intent signature, preconditions, capability/workflow reference, parameter schema, success/failure counts, benchmark coverage, source episodes, anti-patterns, termination conditions, recency, and supersession links. A distillation pass clusters similar episodes, proposes a generalized recipe, replays it on held-out instances, and only then promotes it.

**Integration point:** Extends the Gen3 workflow registry; retrieved by Context Compiler and Capability Forge before invention.

**Security implications:** Memory must never store secrets from traces. Applicability does not grant new authority; execution still occurs through normal guest primitives.

**Complexity:** Medium  
**Expected payoff:** Transformative

**Dependencies:** Better episode lineage; generated/replay tests; promotion policy.

**How to benchmark:** Re-run a corpus of repeated engineering tasks with and without memory. Measure fresh authored steps/bytes, retrieval precision, task success, incorrect-skill invocation rate, and context loaded. Require at least one deduplication and one safe retirement/supersession case.

**Failure modes:** Memorizing brittle recipes; retrieving a superficially similar but wrong skill; unbounded memory; stale skills outliving environment changes. Every item needs applicability + evidence + expiry/supersession.

---

### Idea 5 — Failure-to-Regression Compiler

**Class:** Architectural upgrade  
**Concept:** Convert a novel failure episode into a minimized reproducer, regression test, causal hypothesis, and—when justified—a bounded recovery recipe.

**Why it matters here:** The existing failure miner counts and ranks known friction, but it does not minimize failures or automatically make them future fitness gates. Gen3’s candidate/LKG semantic mismatch and CLI exit-code bug both required ChatGPT diagnosis before becoming durable knowledge.

**What becomes possible:** Failures become assets. The Lab’s test suite grows precisely where reality hurt it, and future generations inherit protection against old mistakes.

**Possible architecture:** On a failed episode: collect causal trace subtree → identify changed artifacts → replay in disposable workspace → delta-debug steps/input until a minimal reproducer remains → propose root-cause class → create regression fixture → test against bad and repaired variants → optionally attach a bounded recovery policy.

**Integration point:** Failure miner + Benchmark Nursery + Procedural Memory.

**Security implications:** Replays occur in isolated guest descendants/workspaces. Never replay captured secrets. Network failures should use synthetic/local fixtures where possible.

**Complexity:** Medium–Large  
**Expected payoff:** Significant

**Dependencies:** Transactional checkpoints/replay improve reliability but a simpler first version can use copied workspaces.

**How to benchmark:** Feed a corpus of 10 known historical/seeded failures. Require minimized reproducer creation, detection by the new regression, no false failure on accepted build, and measurable size reduction from original episode.

**Failure modes:** Misattributed root cause; non-reproducible timing failures; creating tests that encode accidental implementation details; expensive minimization. Preserve uncertainty rather than pretending every failure has one cause.

---

### Idea 6 — Architectural Digital Twin

**Class:** Architectural upgrade  
**Concept:** Maintain a small machine-readable model of the Lab’s own structure, dependencies, runtime services, workflows, invariants, benchmarks, and generation lineage.

**Why it matters here:** Humans currently reconstruct architecture from `START_HERE`, status/state files, source, workflows, traces, and live status. That discipline is good, but the Lab itself has no queryable answer to “what depends on this file?”, “which benchmark protects this invariant?”, or “what changed the recovery semantics?”

**What becomes possible:** Impact analysis before edits, targeted context retrieval, automatic architecture documentation, coverage-gap detection, and benchmark generation from invariants.

**Possible architecture:** SQLite plus generated JSON snapshots is enough. Nodes: source files/functions, MCP tools, Code Mode ops, workflow versions, services, runtime paths, invariants, benchmark tasks, capability capsules, generations. Edges: `calls`, `compiles_to`, `protected_by`, `modifies`, `supersedes`, `runs_as`, `depends_on`, `observed_in`. Populate deterministic structure from Python AST/workflow JSON/systemd metadata, then enrich with trace-derived runtime edges.

**Integration point:** New guest-local indexer/query CLI; Context Compiler and impact-analysis workflow consume it.

**Security implications:** Guest-local metadata only. Do not mirror host credential locations or private host topology into the model.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** None beyond existing source/workflows/traces, though causal observability improves it.

**How to benchmark:** Ask 30 architecture/impact questions with known answers; score precision/recall. Mutate a workflow/source relationship and require stale-model detection. Measure context bytes needed to answer impact questions vs raw document loading.

**Failure modes:** A stale graph becoming a false source of truth; over-modeling every line; natural-language facts with no provenance. Rebuild deterministic facts often and attach source hashes/timestamps.

---

### Idea 7 — Context Compiler

**Class:** Architectural upgrade  
**Concept:** Compile a task-specific minimal context bundle from authoritative state, self-model, procedural memory, recent evidence, and exact source excerpts.

**Why it matters here:** Fresh sessions are reliable because they reread authoritative files, but high-level work still spends substantial context reconstructing the same system. More memory should not mean bigger prompts.

**What becomes possible:** A planning task receives “only the architecture, invariants, relevant prior failures, and capabilities needed for this change,” with hashes and expandable pointers. Progressive disclosure becomes a first-class system behavior.

**Possible architecture:** Query task intent against the Architectural Twin + memory index; apply mandatory invariant set; rank relevant evidence; emit a bounded Markdown/JSON context packet with source references and freshness metadata. Support levels: `identity`, `implementation`, `history`, `failure`, `benchmark`. Never summarize away hard security rules.

**Integration point:** Guest-local context-bundle workflow; eventually generated automatically before design/experiment stages.

**Security implications:** Context compiler should reduce accidental secret exposure by selecting from sanitized/approved sources. It must always inject immutable containment rules for self-modification tasks.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** Architectural Twin and Procedural Memory for best results.

**How to benchmark:** On a fixed set of design/debug tasks, compare context bytes/tokens, answer/task quality, omitted-critical-fact rate, and number of follow-up reads. Target a large context reduction without any containment/invariant misses.

**Failure modes:** Compressing away the one fact that matters; stale summaries; self-reinforcing incorrect memory. Every bundle needs provenance and a “retrieve full source” escape hatch.

---

### Idea 8 — Descendant Experiment Arena

**Class:** Qualitatively new capability  
**Concept:** Spawn multiple isolated candidate descendants from the same baseline, let each try a different implementation/strategy, evaluate them under identical fitness gates, and retain the winner plus lineage of losers.

**Why it matters here:** Current generations generally implement one selected design and test it. The Lab already has recovery and benchmarks but does not perform controlled comparative search. External evolutionary systems show that preserving diverse candidates can outperform linear self-editing [R1][R2].

**What becomes possible:** “Try AST edit engine A, semantic-patch B, and generated-script C” becomes an experiment, not a debate. Failed descendants become evidence instead of lost work.

**Possible architecture, first version:** Git worktrees/copy-on-write directories + transient systemd units/cgroups + unique ports/state roots. A candidate manifest pins source/environment/benchmark hashes. An evaluator runs hard gates then multi-objective metrics. A lineage DB records parent, mutation rationale, result, and artifacts. Parallelism is bounded by the current 2-vCPU/2-GiB VM; sequential competition is acceptable initially.

**Integration point:** Above transactional graphs and benchmark runner.

**Security implications:** All descendants stay inside the same already-isolated outer VM and get no host capabilities. Resource quotas prevent one candidate starving the parent Lab. Network behavior remains constrained by outer-VM firewalling.

**Complexity:** Large  
**Expected payoff:** Transformative

**Dependencies:** Reproducible capability environments; benchmark versioning; causal observability; promotion governor.

**How to benchmark:** Generate 3–5 seeded candidate implementations with known tradeoffs. Require isolation, reproducible rerun, independent state, correct hard-gate rejection, deterministic score artifact, and winner selection. Prove loser artifacts remain inspectable.

**Failure modes:** Benchmark overfitting; expensive candidate explosion; shared-state contamination; selecting a faster but less maintainable candidate. Use hard gates + multi-objective evidence, not one scalar leaderboard.

---

### Idea 9 — Observability Spine

**Class:** Architectural upgrade  
**Concept:** Evolve the trace ledger from flat tool events into a causal lineage model spanning intent, graph run, workflow, Code Mode, job/service, candidate, restart, evaluator, and promotion decision.

**Why it matters here:** Current tracing is enough to count operations, but a future autonomous Lab needs to answer “why did this candidate exist, what exact context and tests judged it, and what descendant did it produce?”

**What becomes possible:** Reliable experiment comparison, replay, root-cause mining, architecture reconstruction, cost accounting, and evidence-backed promotion.

**Possible architecture:** Preserve append-only JSONL for simplicity but add trace/span IDs, parent span, episode ID, candidate ID, graph/node ID, capability hash, evaluator hash, decision event, resource counters, and sanitized context bundle hash. Optionally materialize to SQLite for queries. Borrow OpenTelemetry naming conventions where useful without requiring a telemetry backend [R24].

**Integration point:** `server.py`, Code Mode, workflow runner, future graph/experiment/capability layers.

**Security implications:** Strict sanitization remains mandatory. Never turn tracing into a secret collector. Content bodies should be opt-in/hash-first.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** None; best introduced before large-scale experiments.

**How to benchmark:** Trace one full self-update and reconstruct its complete causal tree automatically; require no orphaned child spans, stable IDs across restart, artifact hashes resolvable, and bounded log growth.

**Failure modes:** Telemetry bureaucracy; cardinality/storage explosion; instrumentation failures affecting work. Logging must remain non-blocking and bounded.

---

### Idea 10 — Event Reactor

**Class:** Qualitatively new capability  
**Concept:** Let guest-local events trigger bounded durable workflows without waiting for ChatGPT to manually initiate each internal step.

**Why it matters here:** Today the Lab is mostly command-driven. It can run durable jobs, but it does not *notice* a service crash, new failure pattern, benchmark regression, stale capability, or scheduled maintenance window and start a controlled investigation.

**What becomes possible:** The system begins to feel alive: a failed service can trigger diagnosis; a newly repeated failure can trigger a regression-mining experiment; a periodic low-priority job can compact traces/memory; a new candidate artifact can trigger validation.

**Possible architecture:** Tiny local event bus backed by SQLite/JSONL. Producers: trace events, systemd service state, file/inotify events, timers. Policies map event type + predicate → version-pinned transactional graph. Every trigger has cooldown, dedupe/idempotency key, resource budget, and allowed side-effect class. Initial policy should permit **analysis and experiment creation**, not automatic accepted-runtime promotion.

**Integration point:** systemd timers/path units + graph runner + trace ledger.

**Security implications:** Guest-local only. No new private-network or host event subscriptions. Avoid trigger loops where a diagnostic action generates the same event indefinitely.

**Complexity:** Medium  
**Expected payoff:** Transformative

**Dependencies:** Transactional graphs, observability, resource budgets.

**How to benchmark:** Inject service crash, recurring workflow failure, and duplicate event storm. Require exactly-once/deduped bounded responses, durable resume after MCP restart, no promotion side effect, and correct cooldown behavior.

**Failure modes:** Runaway loops, noisy self-activity, resource starvation, self-triggering cascades. Event policies need budgets and circuit breakers.

---

### Idea 11 — Semantic Edit Engine

**Class:** Incremental engineering → architectural enabler  
**Concept:** Add syntax-aware, preconditioned source transforms as guest-local capabilities rather than relying heavily on exact string replacement and raw patches.

**Why it matters here:** Current trace mining saw `exact_replace` failures far more often than other ops. Exact replacement is deterministic—which is good—but asks ChatGPT to manufacture brittle old/new text. Coccinelle-style semantic patches and modern AST libraries show how edits can describe structure rather than formatting [R34].

**What becomes possible:** Rename/update/import/function-body transformations across files with preview, structural match count, syntax validation, inverse/rollback, and postconditions.

**Possible architecture:** Do **not** add a generic “AI edit” black box to the MCP. Forge language-specific transformers (Python `ast`/LibCST/tree-sitter, semantic-patch style matchers) that emit a patch, require expected match cardinality, run parser/compile tests, and only then apply inside Code Mode transaction boundaries.

**Integration point:** Capability Forge / Code Mode command capability; frequently successful transforms can become reusable workflows.

**Security implications:** Same guest file authority. Structural transforms need exact target scope to avoid broad accidental rewrites.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** Existing rollback and patch artifacts.

**How to benchmark:** Corpus of 30 edits with formatting variations where exact replacement is brittle. Measure correct transformation rate, false matches, rollback, patch size, and authoring bytes.

**Failure modes:** AST tools rewriting formatting/comments; language-specific complexity; broad matches. Require diff preview and expected match counts.

---

### Idea 12 — Reproducible Capability Capsules

**Class:** Architectural upgrade  
**Concept:** Make each experiment/capability carry a reproducible environment manifest instead of silently mutating the one guest forever.

**Why it matters here:** The VM is intentionally mutable and Gen1 installed useful packages globally. That is fine early, but descendants and dynamic tools will make “works because this VM accumulated state” increasingly dangerous.

**What becomes possible:** Re-run a six-generation-old experiment; compare candidates on the same dependency set; garbage-collect one-off toolchains; recreate a capability after rollback.

**Possible architecture:** Start lightweight: manifest OS base ID, apt packages+versions, Python lock/venv hash, downloaded artifact hashes, environment variables *names only*, build command, capability source hash. Materialize into venvs/chroots/overlay workspaces where appropriate. Later evaluate Nix/Guix or OCI layers if the simple manifest proves insufficient [R18].

**Integration point:** Capability Forge and Descendant Arena.

**Security implications:** Never encode secret values in manifests. External packages remain public-internet guest dependencies; provenance/source hashes should be recorded.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** None, but becomes essential before large experiment populations.

**How to benchmark:** Build the same capability from a clean workspace twice; compare artifact hashes/functional output. Deliberately change one dependency and require identity change. Delete local environment and recreate successfully.

**Failure modes:** False reproducibility due unpinned apt indexes/time/network; huge caches; trying to solve all reproducible computing at once. Define practical reproducibility tiers.

---

### Idea 13 — Adversarial Twin

**Class:** Qualitatively new capability  
**Concept:** For important candidates, create a dedicated critic/red-team process whose job is to break the proposal, find counterexamples, and attack its evaluator—not to improve the implementation.

**Why it matters here:** The current loop usually asks one reasoning process to design and validate its own work. Generated benchmarks will amplify the danger of self-confirmation unless another role searches for ways the candidate or oracle can cheat.

**What becomes possible:** Candidate review includes adversarial inputs, invariant attacks, mutation tests, weird restart points, malformed parameters, and attempts to exploit benchmark assumptions before acceptance.

**Possible architecture:** Start without a second LLM: deterministic mutation/fuzz/property strategies plus a separate “critic workflow” that cannot modify the candidate. If/when multiple model access becomes safe, use a separate critic prompt/model to generate attack cases, but execution and judgment remain deterministic where possible.

**Integration point:** Benchmark Nursery and Promotion Governor.

**Security implications:** Red-team code still runs within descendant isolation. It must not be allowed to test the host/private boundary by weakening firewalling; containment probes remain fixed known-safe tests.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** Better candidate isolation and evaluator contracts.

**How to benchmark:** Seed known subtle bugs and weak oracles. Measure bug discovery and oracle-break detection vs normal benchmark suite. Require no accepted-build damage.

**Failure modes:** Performative “debate” with no new tests; adversary consuming excessive resources; endless criticism. Require concrete executable counterexamples and budgets.

---

### Idea 14 — Promotion Governor

**Class:** Small architectural policy primitive  
**Concept:** Decide what deserves to become durable machinery and what should remain ephemeral, using evidence rather than enthusiasm.

**Why it matters here:** Dynamic capability synthesis is only useful if the Lab avoids accumulating thousands of brittle one-off tools. Gen3 already demonstrates immutable history, but future automatic creation needs explicit retention economics.

**What becomes possible:** A healthy lifecycle for capabilities: ephemeral → candidate → promoted → superseded/retired, with compact reasons and evidence.

**Possible architecture:** A scored-but-not-single-number policy using hard gates plus evidence dimensions: recurrence, success rate, benchmark breadth, context/call savings, generality, maintenance cost, dependency footprint, security side effects, overlap with existing capabilities, and age. Promotion emits a decision record; retirement never erases immutable provenance.

**Integration point:** Workflow registry + Capability Forge + Procedural Memory.

**Security implications:** Governor cannot approve authority expansion. Any host-authority delta remains an explicit user-level architectural decision outside guest autonomy.

**Complexity:** Small–Medium  
**Expected payoff:** Significant

**Dependencies:** Evidence/lineage schema.

**How to benchmark:** Feed synthetic capability histories with obvious keep/discard/supersede outcomes plus ambiguous cases. Measure decisions, bloat over 100 generated one-offs, and ability to recover retired provenance.

**Failure modes:** Good experimental capabilities discarded too early; proxy metrics become targets; hidden single score. Keep transparent reasons and quarantine instead of destructive deletion.

---

### Idea 15 — Guest Browser Lab

**Class:** Incremental capability with future qualitative upside  
**Concept:** Add a guest-local browser automation skill/service, paired with reproducible local synthetic websites for tests.

**Why it matters here:** Browser automation has been proposed since Gen1/Gen2. Public-repo investigation works through Git/HTTP/CLI, but the Lab cannot render or manipulate DOM/UI. This is a genuine capability gap, just not the biggest current self-evolution bottleneck.

**What becomes possible:** Dynamic-site research, end-to-end testing of web software, screenshot/DOM assertions, browser-based synthetic users, and later automatic browser-tool invention.

**Possible architecture:** Playwright/Chromium installed inside the guest; code-level browser scripts exposed as reusable capabilities rather than dozens of MCP browser tools. Local synthetic apps mimic forms, auth-less workflows, dynamic DOM, errors, and navigation; task definitions have deterministic verifiers inspired by WebArena/BrowserGym [R28][R29].

**Integration point:** Capability registry/skills; local service workflows.

**Security implications:** Browser has only the guest’s public-internet reach and existing private-network blocks. Never bridge to host browser profile, cookies, credentials, or LAN. Synthetic test sites should be preferred for regression.

**Complexity:** Medium  
**Expected payoff:** Significant

**Dependencies:** Disk/RAM budget; may compete with current 2-GiB constraint.

**How to benchmark:** 15 deterministic local web tasks plus a few public-read-only research tasks. Measure completion, DOM assertion quality, context returned, resource use, and containment.

**Failure modes:** Browser memory pressure; brittle selectors; public-site flakiness; accidentally creating a giant browser MCP surface. Keep browser logic guest-local and code-first.

---

### Idea 16 — Handoff Compiler

**Class:** Incremental engineering with high practical leverage  
**Concept:** Automatically generate an evidence-backed candidate handoff packet from live Lab identity, source hashes, tests, traces, generation artifacts, and changes.

**Why it matters here:** Repository handoff is intentionally manual/mediated because the guest cannot write the host canonical repo. The repeated intellectual work of assembling `STATUS`, `NEXT_SESSION`, result JSON, changelog/story, and verification commands is still mechanical.

**What becomes possible:** The Lab can produce a signed/hashable `handoff/GENX/` artifact that ChatGPT or the frozen host connector reviews and mirrors into canonical history, without giving the guest host write authority.

**Possible architecture:** Guest-local command produces `summary.md`, `result.json`, source/artifact manifest, benchmark table, containment result, proposed next-session gate, and diff/provenance pointers. It explicitly marks claims as `OBSERVED`, `DERIVED`, or `PROPOSED`.

**Integration point:** End of accepted guest candidate graph; mediated host copy/review remains external.

**Security implications:** Excellent fit with boundary. The compiler must secret-scan its packet before export and never assume export equals acceptance.

**Complexity:** Small–Medium  
**Expected payoff:** Significant

**Dependencies:** Observability Spine improves completeness but is not required.

**How to benchmark:** Generate handoff from Gen1–Gen3 archived evidence and compare completeness/accuracy against current manual files. Require all identity hashes/gates and zero unsupported claims.

**Failure modes:** Auto-generated documentation becoming authoritative despite stale inputs; verbose dumps instead of useful handoff; accidental secrets. Attach source hashes and run a strict secret scan.

---

### Idea 17 — Adaptive Bounded Recovery Policies

**Class:** Incremental engineering  
**Concept:** Promote recurring transient/error patterns into explicit finite recovery state machines rather than relying on repeated ChatGPT diagnosis or generic retries.

**Why it matters here:** Gen2/Gen3 already use bounded retries and explicit recovery recipes. The miner still sees repeat edit failures and implementation sessions encountered restart/LKG semantic confusion. A small policy layer can eliminate predictable diagnosis without creating open-ended self-healing magic.

**What becomes possible:** “Port not up after restart,” “candidate still pending acceptance,” “exact match absent,” or “dependency fetch transiently failed” can select a known inspect→retry/fallback→stop policy with visible bounds.

**Possible architecture:** Error classifiers map structured failure facts to versioned policies. Policies are tiny graphs with max attempts, total time/resource budget, prerequisites, and terminal states `RECOVERED`, `ESCALATE`, `HARD_FAIL`. Only demonstrated policies are eligible.

**Integration point:** Transactional graph runner/failure compiler.

**Security implications:** No policy may retry or route around containment/security failures. Security gate failure is terminal.

**Complexity:** Small–Medium  
**Expected payoff:** Incremental–Significant

**Dependencies:** Transaction graph semantics make this cleaner.

**How to benchmark:** Inject known transient and permanent failures. Measure correct recovery, bounded stopping, no false recovery, and reduction in outer intervention.

**Failure modes:** Retry storms; masking real bugs; broad string-based error matching. Prefer structured error classes and strict budgets.

---

### Idea 18 — Counterfactual Replay

**Class:** Architectural upgrade  
**Concept:** Re-run an old episode from a checkpoint with one variable changed: different capability version, retry policy, edit engine, benchmark, or planner decision.

**Why it matters here:** The Lab has traces, concrete compiled workflows, and now Gen4 graph runs, but it still cannot systematically ask “would this new recovery policy have prevented a Gen3 failure?” or “does the new edit engine reduce old exact-replace failures?” without manually reconstructing the episode.

**What becomes possible:** Historical failures become a regression corpus for new generations; policy changes can be evaluated offline; memory procedures can be validated on past tasks.

**Possible architecture:** Mark replayable boundaries and side-effect classes in traces. Recreate workspace/environment from capsule, rehydrate deterministic inputs, substitute selected version, and write a new child episode linked to the original. Non-replayable external calls become recorded fixtures or explicitly unsupported.

**Integration point:** Observability + capsules + Descendant Arena.

**Security implications:** Replays should occur in disposable guest workspaces/descendants. Do not blindly reissue historical internet side effects.

**Complexity:** Large  
**Expected payoff:** Significant

**Dependencies:** Causal traces, reproducible environments, graph checkpoints.

**How to benchmark:** Select 10 Gen2/Gen3 episodes, replay unmodified and compare outputs; then swap one component and verify only the intended dimension changes.

**Failure modes:** Pretending nondeterministic external state is reproducible; replay implementation complexity; enormous storage. Explicitly classify replay fidelity.

---

## 6. Wild / unconventional ideas

These are intentionally farther out. They are still technically grounded in the current architecture.

### Wild 1 — Evolution Garden

**Concept:** Use the outer `mcp-lab` VM as a **parent organism** that spawns ephemeral child computers. `/dev/kvm` is already visible inside the guest, so a future generation could evaluate Firecracker/QEMU-based nested microVM descendants if resources permit.

**Why it matters here:** It is the cleanest expression of “the Lab evolves the Lab” without giving the guest host libvirt authority. Each descendant can mutate its own runtime, reboot, break, benchmark, and die. The outer VM remains the ultimate sandbox.

**What becomes possible:** A genealogical tree of actual runnable Lab descendants: parent → mutations → fitness results → winner. Entire OS/package/runtime state becomes forkable rather than only source trees.

**Possible architecture:** Parent maintains a minimal base image and content-addressed snapshots. Candidate manifests describe mutations. Children get isolated state roots and outbound networking bounded by the outer VM. Run sequentially at first because current 2-vCPU/2-GiB resources are tight. Archive only manifests/diffs/fitness by default, not every disk image.

**Integration point:** Advanced Descendant Arena.

**Security implications:** Nested guests remain inside the already-isolated outer VM. Never expose host `/dev/kvm` equivalents beyond what is already intentionally virtualized, never bridge child networking to host/LAN, and never give children outer-VM secrets that do not need them.

**Complexity:** Research  
**Expected payoff:** Transformative

**Dependencies:** Descendant Arena, capsules, benchmark nursery, resource scheduler. A modest Lab resource increase may eventually be useful but is not conceptually required for sequential children.

**How to benchmark:** Boot two child descendants from one baseline, apply different mutations, reboot them independently, run identical fitness suites, destroy them, recreate the winner from manifest/snapshot, and verify outer containment throughout.

**Failure modes:** Nested-virtualization complexity, memory pressure, image management becoming the project, or believing VM cloning itself equals intelligence. Do not attempt until process-level descendants produce clear value.

---

### Wild 2 — Curiosity Engine

**Concept:** The Lab periodically asks itself: “What important thing about my own capability is currently unknown, weakly tested, or repeatedly painful?” Then it proposes and runs a **safe experiment**, not a production change.

**Why it matters here:** The failure miner is reactive and template-driven. A more advanced Lab should discover *missing evidence*, not merely count observed failures.

**What becomes possible:** Autonomous research nights: compare two edit strategies, test whether a workflow remains correct after version drift, seek an untested lifecycle transition, or measure whether a new memory item actually helps.

**Possible architecture:** Self-model coverage gaps + benchmark coverage + trace friction + stale assumptions feed a hypothesis generator. Every hypothesis must compile to: question, expected information gain, bounded experiment, evaluator, resource budget, and stop condition. Results update evidence, never automatically authority.

**Integration point:** Event Reactor + Benchmark Nursery + Arena.

**Security implications:** Experiments remain guest-local and budgeted. Curiosity cannot request host credentials or weaken containment; such hypotheses terminate as architectural constraints.

**Complexity:** Research  
**Expected payoff:** Transformative

**Dependencies:** Strong observability, self-model, experiment arena, promotion governor.

**How to benchmark:** Hide known capability gaps/invariants from the experiment set and evaluate whether the engine discovers high-value tests before low-value novelty. Measure information gained per resource budget.

**Failure modes:** Busywork disguised as curiosity; endless benchmark optimization; novelty seeking. Reward reduced uncertainty tied to concrete project goals, not number of experiments.

---

### Wild 3 — Capability Darwinism

**Concept:** Treat reusable capabilities as evolving programs with mutation, crossover/recombination of useful subprocedures, and a lineage archive—similar in spirit to AlphaEvolve/DGM but constrained to the Lab’s small capability layer.

**Why it matters here:** A dynamic forge creates candidates; an arena compares them. Evolutionary search could explore improvements that no one explicitly requested, especially for parsers, edit strategies, benchmark oracles, and context selectors.

**What becomes possible:** The Lab can improve a capability over dozens of small generations while preserving diverse alternatives and objective evidence.

**Possible architecture:** Mutation operators operate on capability source/config/workflow graphs; evaluator returns hard gates + multi-dimensional metrics; novelty/diversity prevents one local optimum; lineage DB retains parentage. A language model may propose mutations, but deterministic evaluators decide survival.

**Integration point:** Forge + Arena + Nursery.

**Security implications:** Same guest-only authority. No evolutionary pressure may trade away containment gates.

**Complexity:** Research  
**Expected payoff:** Transformative

**Dependencies:** Mature Forge/Nursery/Arena.

**How to benchmark:** Choose a bounded capability with measurable fitness, e.g. log parser robustness or context selection. Compare evolutionary search against linear hand-tuned iterations under equal budget and a hidden holdout suite.

**Failure modes:** Overfitting the evaluator; population explosion; opaque spaghetti code. Enforce simplicity/maintainability metrics and holdouts.

---

### Wild 4 — Dream Replay

**Concept:** During idle guest time, replay old failures and difficult episodes against the latest capabilities to see whether the Lab has silently become better—or regressed.

**Why it matters here:** Historical traces are currently mostly archival. They could become a changing curriculum.

**What becomes possible:** “Gen7 can now solve five failures that required ChatGPT in Gen3” becomes measurable. New capabilities can discover applicability to old pain without waiting for the same failure to happen again.

**Possible architecture:** Sample sanitized replayable episodes by difficulty/age/uncertainty; reconstruct workspace; run current candidate memory/capability stack; compare objective result; generate regression or promotion evidence.

**Integration point:** Counterfactual Replay + Event Reactor.

**Security implications:** Never replay side-effectful external actions directly; use fixtures/synthetic services.

**Complexity:** Large  
**Expected payoff:** Significant–Transformative

**Dependencies:** Replay fidelity and capsules.

**How to benchmark:** Use archived seeded failures with known outcomes; verify stable reproduction and detect a deliberately introduced regression.

**Failure modes:** Expensive nostalgia; irreproducible external state; training-on-test contamination. Maintain holdout episodes.

---

### Wild 5 — Self-Written Architecture Proofs

**Concept:** For tiny but critical lifecycle state machines, let the Lab synthesize an explicit formal model/invariants and model-check them before implementing changes.

**Why it matters here:** Candidate/LKG semantics already produced a real Gen3 implementation surprise. Lifecycle transactions are exactly where subtle impossible-state bugs matter more than coding speed.

**What becomes possible:** Before changing lifecycle semantics, the Lab can prove bounded properties such as “a candidate cannot become accepted without verification,” “a containment failure cannot transition to accepted,” and “restart from any journal state has a legal recovery path.”

**Possible architecture:** Generate a small TLA+/PlusCal or exhaustive Python state model from the graph specification, then run a model checker/exhaustive transition explorer over bounded states. Store the model hash as candidate evidence.

**Integration point:** Transactional Workflow Graph design/benchmark phase.

**Security implications:** No authority change; this strengthens lifecycle assurance.

**Complexity:** Research  
**Expected payoff:** Significant for narrow critical paths

**Dependencies:** Stable transaction state machine.

**How to benchmark:** Seed illegal transitions/race conditions and require the model checker to find counterexamples before runtime tests do.

**Failure modes:** Formalism theater; model diverges from implementation; enormous state spaces. Use only for small authority/recovery state machines and cross-check model ↔ runtime transitions.

---

## 7. Compound architectures

The strongest future generations are combinations where each primitive closes another primitive’s weakness.

### Compound A — Automatic Capability Acquisition Loop

**Capability Forge + Benchmark Nursery + Promotion Governor + Procedural Memory**

1. A task exposes a capability gap.
2. Existing memory is searched first.
3. Forge creates one or more ephemeral capabilities.
4. Nursery generates tests, negative cases, and holdouts.
5. Capability executes on the real task and benchmark.
6. Governor retains, rejects, or expires it.
7. Repeated successful behavior is distilled into procedural memory.

**Qualitative jump:** The Lab can *acquire* a new ability rather than waiting for a human-designed generation to add it.

### Compound B — Evolution Garden

**Descendant Arena + Capability Capsules + Snapshot/Fork + Adversarial Twin + Promotion Governor**

Multiple descendants inherit the same baseline, pursue competing mutations, undergo adversarial evaluation, and leave a lineage archive. Only the evidence-selected candidate is nominated for acceptance.

**Qualitative jump:** Self-modification becomes population-based experimental evolution instead of a single mutable line.

### Compound C — Cumulative Engineering Intelligence

**Architectural Twin + Procedural Memory Distiller + Failure-to-Regression + Context Compiler**

The self-model says what exists and what depends on what. Failures become tests. Repeated solutions become skills. The context compiler retrieves only relevant structure/evidence.

**Qualitative jump:** Every generation inherits a smaller, more useful working memory despite a larger history.

### Compound D — Durable Self-Evolution Reactor

**Transactional Workflow Graphs + Event Reactor + Observability Spine + Adaptive Recovery**

Events start version-pinned durable graphs; every node is causally traced; known failures use bounded recovery; restarts resume from journal state.

**Qualitative jump:** The Lab can safely carry responsibility over time instead of requiring ChatGPT to push every internal domino.

### Compound E — Evidence-Driven Research Architect

**Curiosity Engine + Architectural Twin + Benchmark Nursery + Descendant Arena + Handoff Compiler**

The Lab identifies an evidence gap, designs an experiment, creates candidate branches, evaluates them, and emits a concise evidence-backed recommendation/handoff without implementing host-side authority changes.

**Qualitative jump:** The Lab begins doing the *research-architect job* currently performed by fresh ChatGPT sessions.

### Compound F — Web Capability Laboratory

**Guest Browser Lab + Synthetic Web Worlds + Capability Forge + Benchmark Nursery**

The Lab can invent browser helpers against deterministic local sites, test them rigorously, then use the survivors for public web research/testing.

**Qualitative jump:** Browser/computer-use capability becomes evolvable rather than a fixed Playwright wrapper.

### Compound G — Model Market (deferred until safe inference access exists)

**Empirical Model Router + Arena + Task-Specific Benchmarks + Resource/Cost Scheduler**

Different coding/reasoning models bid for subproblems based on benchmarked accuracy, latency, and cost. A cheap model can triage/routinely orchestrate while a strong model handles difficult edits or critique.

**Qualitative jump:** “Which model should think?” becomes another locally evaluated engineering decision.

The current Lab cannot do this cleanly: 2 GiB is unsuitable for serious local models, and cloud API credentials should not be placed in the unrestricted guest. Do not weaken that boundary merely to enable routing.

---

## 8. Ideas rejected or deferred

### Reject — Grow a giant permanent MCP surface

Gen2 and Gen3 both improved capability while keeping exactly ten MCP tools. That is a success. New domain-specific functions should default to guest-local workflows/capabilities. Add a permanent MCP primitive only when it changes the *interaction substrate*, not because a useful script exists.

### Reject — Give the guest host credentials, host repo mounts, Docker/libvirt sockets, Tailscale, LAN, or production authority

This would erase the project’s cleanest safety property. The inconvenience of mediated handoff/snapshots is cheaper than turning a self-modifying root VM into a host authority principal.

### Reject — Evolve Optiplex_MCP as part of Lab generations

The safe control plane is a constraint/reference and emergency recovery boundary. The project already corrected this scope once. Do not regress.

### Defer — Adopt Temporal/LangGraph/AutoGen/CrewAI/etc. wholesale

Borrow concepts, not framework gravity. Current requirements are small enough for a narrow graph journal and immutable workflow references. A generic agent framework risks duplicating working abstractions and creating migration work without solving the Lab-specific frontier.

### Defer — Full NixOS/Guix conversion

Reproducibility is valuable, but the next useful primitive is a capability/environment manifest, not rebuilding the entire guest around a functional package manager. Escalate only if drift becomes measured pain.

### Defer — Serious local LLM inference inside the current VM

Two vCPU/~2 GiB RAM is the wrong environment for capable local coding models. Installing a tiny model for novelty would likely add complexity without real autonomy. A future *mediated* inference service can be evaluated separately if it preserves the host/credential boundary.

### Reject — Fully autonomous acceptance/promotion with no evidence or policy gate

Candidate creation, testing, comparison, and recommendation can become highly autonomous. Accepted-runtime transitions should remain governed by explicit invariant/evidence policies, with user approval retained anywhere authority materially changes. Autonomy should increase evidence, not reduce accountability.

### Reject — Host-level snapshot authority from the guest

If outer-VM snapshots are needed, keep host/libvirt authority external. Nested child VMs are the correct guest-local playground.

### Defer — Massive multi-agent swarms

Targeted independent roles—builder, adversarial critic, evaluator—can add diversity. Large conversational swarms usually multiply context and coordination before they multiply capability. Earn each extra agent with benchmark evidence.

### Defer — Reinforcement learning / weight updates

Agent Lightning and related work make execution trajectories useful for RL [R35], but this project can gain much more first from procedural memory, search, benchmarks, and model routing. Weight training is resource-heavy and changes a different layer than the current Lab needs.

### Reject — A generic knowledge graph product

The Architectural Twin should be a small derived index over authoritative source/state, not a new ontology project. SQLite + deterministic extractors are enough until evidence says otherwise.

---

## 9. Future-generation roadmap

Generation numbers below are proposals, not commitments. **Gen4 is already live/in-progress**, so the roadmap begins by treating its completed handoff as the prerequisite rather than proposing to build it again.

### Current Generation 4 — Composable Workflow Graphs + Lifecycle Transactions

**State discovered:** Live guest is `gen4-workflow-graphs-r1`, recovery state `ACCEPTED`, graph self-test 8/8, two canonical lifecycle graphs registered. Canonical repository handoff still showed Gen3/`IMPLEMENTING` and no finalized Gen4 result benchmark when this memo was finalized.

**Thesis:** *The Lab can execute an entire self-evolution lifecycle as one restart-safe, auditable transaction.*

**Before moving on:** Finish the independent Gen4 generation benchmark, containment/regression evidence, failure-miner output, `GEN4_RESULT`, canonical state/status/history handoff, and any evidence-driven Gen5 proposal. Do not infer success merely from the 8/8 graph unit/self-test.

**Expected success criterion:** Demonstrate the planned Gen3 4-call normal lifecycle → 1 parent graph invocation and 3-call recovery chain → 1 graph invocation, while preserving child workflow/Code Mode evidence and surviving restart boundaries without ambiguous destructive replay.

### Generation 5 — Evidence-Gated Capability Forge

**Thesis:** *The Lab can invent a missing guest-local tool, prove it useful, use it, and discard or retain it without expanding the permanent MCP API.*

**Key capability:** Capability Contract Layer + ephemeral capability synthesis + minimum Benchmark Nursery + Promotion Governor.

**Prerequisite:** Fully finalized Gen4 transaction evidence; existing Code Mode/workflow registry.

**Why ordering:** Gen4 provides a durable control plane for multi-step creation/validation. The Forge is the first leap from “compose what I know” to **“create what I need.”**

**Measurable success:** On a blind set of unseen tasks, forge useful helpers that did not exist at generation start, validate them, reuse duplicates, reject broken candidates, keep MCP surface at ten, and leave complete provenance/cleanup state.

### Generation 6 — Experience Becomes Memory

**Thesis:** *Repeated success and failure automatically become tested procedural knowledge.*

**Key capability:** Procedural Memory Distiller + Failure-to-Regression Compiler.

**Prerequisite:** Forge/evaluator episodes provide enough varied experience to distill.

**Why ordering:** Memory should generalize from multiple real attempts, not prematurely encode one successful script.

**Measurable success:** Repeated task corpus requires substantially fewer newly authored steps/context; seeded historical failures become regressions; wrong-skill retrieval stays below a defined threshold; stale/superseded memory retires safely.

### Generation 7 — The Lab Understands Its Own Architecture

**Thesis:** *The Lab has a queryable, provenance-backed model of what it is and what a proposed change can affect.*

**Key capability:** Architectural Digital Twin + Context Compiler + enriched causal trace schema.

**Prerequisite:** Enough capabilities/memory that architecture navigation and context selection are measured problems.

**Why ordering:** A self-model earns its maintenance cost once the system has multiple evolving layers beyond workflows/graphs.

**Measurable success:** High accuracy on architecture/impact questions; stale-model detection; large context reduction on design/debug tasks with zero containment/invariant omissions.

### Generation 8 — Competing Descendants

**Thesis:** *The Lab can try several versions of itself or a capability and choose by evidence instead of committing to the first design.*

**Key capability:** Descendant Experiment Arena using isolated workspaces/transient services and reproducible manifests.

**Prerequisite:** Durable graphs, benchmarks, provenance, promotion policy, capsules.

**Why ordering:** Comparative search is only useful once candidate creation and evaluation are trustworthy and reproducible.

**Measurable success:** Generate ≥3 independent candidates, prevent state contamination, run identical versioned evaluations, reject hard-gate failures, reproduce the selected winner, retain loser lineage.

### Generation 9 — Self-Generated Fitness

**Thesis:** *The Lab notices when its evaluator is weak and creates better tests before trusting an improvement.*

**Key capability:** Full Benchmark Nursery: property/stateful testing, mutation testing, evaluator self-tests, holdouts, adversarial twin.

**Prerequisite:** Arena provides competing mutants and real pressure on the evaluator.

**Why ordering:** Fitness generation matters most once the Lab is actively searching candidate space.

**Measurable success:** High kill rate against seeded mutants, low false positives, controlled flakiness/cost, and demonstrated detection of at least one weak oracle.

### Generation 10 — Event-Driven Lab

**Thesis:** *The Lab can notice internal events and take bounded evidence-gathering action without ChatGPT pressing start.*

**Key capability:** Event Reactor + durable policies + adaptive recovery.

**Prerequisite:** Transactions, observability, budgets, reliable evaluators.

**Why ordering:** Event-driven autonomy becomes useful only after actions are restart-safe, bounded, and measurable.

**Measurable success:** Inject crash/failure/stale-memory events and observe deduped bounded diagnosis/experiment workflows that survive restart and do not silently promote runtime changes.

### Generation 11 — Counterfactual History

**Thesis:** *The Lab can replay its own past to measure whether new machinery actually improves old pain.*

**Key capability:** Counterfactual Replay + environment capsules + replayability classification.

**Prerequisite:** Rich lineage, reproducible environments.

**Measurable success:** Deterministically replay a meaningful historical corpus and swap one component at a time with attributable results.

### Generation 12 — Web-Native Experimental World

**Thesis:** *The Lab can see and manipulate web interfaces and has deterministic worlds in which to evolve that ability.*

**Key capability:** Guest Browser Lab + synthetic web apps/tasks.

**Prerequisite:** None strictly; placed here because the self-evolution frontier currently offers higher leverage.

**Measurable success:** High pass rate on local web benchmark, bounded context/output, reproducible selectors/actions, and unchanged private-network containment.

### Generation 13 — Evolution Garden

**Thesis:** *The Lab can grow, reboot, kill, and compare child computers inside itself.*

**Key capability:** Nested microVM descendants and snapshot/fork lineage, if process-level Arena evidence justifies the complexity.

**Prerequisite:** Mature Arena, capsules, fitness generation, resource scheduler.

**Why ordering:** KVM is already exposed, but VM cloning should solve measured isolation/reproducibility needs—not become a virtualization hobby inside the project.

**Measurable success:** Recreate candidate microVM descendants from one base, mutate/reboot independently, select by benchmark, destroy/recreate winner, outer containment unchanged.

### Generation 14 — Autonomous Research Architect

**Thesis:** *The Lab can identify its own high-value uncertainty, design bounded experiments, compare descendants, and propose its next generation with evidence.*

**Key capability:** Curiosity Engine + self-model + Arena + Nursery + Handoff Compiler.

**Prerequisite:** Most earlier primitives.

**Why ordering:** This is where the Lab starts taking over the role this `ideas.md` session performs. It should arrive after trustworthy evidence machinery, not before it.

**Measurable success:** Given no prescribed implementation target, independently identify a real measured frontier, design ≥2 credible experiments, execute them safely, produce a reproducible evidence bundle and ranked next-generation proposal, and withstand adversarial review.

### Optional later branch — Empirical Model Market

**Thesis:** *The Lab empirically chooses which model should solve each kind of subproblem.*

Only pursue after there is a safe inference architecture that does not place reusable cloud credentials in the unrestricted guest and/or the Lab has materially more compute. Model-routing research suggests real gains from task-aware routing [R36][R37][R38], but the current hardware/security geometry makes it premature.

---

## 10. Top 10 recommendations

Ranked roughly by **impact × leverage × feasibility × fit with the project philosophy**, not by ease alone. The live Gen4 transaction layer is treated as current infrastructure rather than a future recommendation.

1. **Capability Forge** — The biggest next qualitative leap: acquire abilities on demand while preserving the tiny permanent MCP kernel.
2. **Benchmark Nursery** — Makes future self-improvement evidence-generating rather than self-congratulatory; evaluators must evolve with capabilities.
3. **Procedural Memory Distiller** — Converts repeated successful engineering into compact, tested, retrievable machinery.
4. **Descendant Experiment Arena** — Changes self-modification from a linear bet into comparative search with loser lineage.
5. **Architectural Digital Twin** — Gives the Lab a grounded model of itself for impact analysis, gap detection, and context compilation.
6. **Failure-to-Regression Compiler** — Makes every meaningful failure permanently useful and steadily raises the fitness floor.
7. **Observability Spine** — Connective tissue for capability lineage, experiment causality, replay, and trustworthy promotion.
8. **Event Reactor** — Makes the Lab feel alive and reduces manual initiation once evidence and budgets are mature.
9. **Semantic Edit Engine** — Directly attacks the largest observed step-failure class while improving future self-editing quality.
10. **Capability Contract Layer + Promotion Governor** — Small primitives that prevent dynamic tool synthesis from becoming ungoverned script/tool bloat.

**Close runners-up:** Context Compiler, Reproducible Capability Capsules, Handoff Compiler, Guest Browser Lab, Counterfactual Replay.

---

## 11. Top 3 highest-leverage near-term generations

Before any new generation, the concurrent Gen4 session should finish its own benchmark and canonical handoff. Assuming those gates validate the live graph design, the highest-leverage **next** generations are:

### #1 — Gen5: Evidence-Gated Capability Forge

This should be the first truly surprising generation after composition. A missing capability should be invented locally, given a typed contract, tested, used, and either thrown away or retained—all without a new MCP schema.

Bundle only the minimum Benchmark Nursery and Promotion Governor needed to keep creation from becoming bloat. Success means solving unseen tasks by creating useful helpers that did not exist at generation start.

### #2 — Gen6: Experience Becomes Memory

After the Forge creates real capability history, distill repeated success and failure into reusable intelligence. Combine Procedural Memory Distiller with Failure-to-Regression Compiler.

This is where “self-building” starts to compound across generations: future tasks should measurably need less procedural reasoning because the Lab learned engineering habits from its own evidence.

### #3 — Gen7: Self-Model + Context Compiler

Once capabilities and procedural memory grow, give the Lab a small provenance-backed model of its architecture and compile task-specific context from it.

This prevents the usual autonomy tax where a more capable system becomes harder to reason about and requires ever-larger prompts. Success should be measured as **less context with equal or better correctness and zero lost invariants**.

---

## 12. Long-term vision

The most compelling endpoint is **not** an MCP server with 200 tools and an enormous prompt. It is a small, stable **self-evolution kernel** inside a deliberately disposable VM.

That kernel exposes a few broad primitives and maintains several guest-local planes:

1. **Execution plane** — Code Mode, durable workflow graphs, jobs/services, restart/recovery.
2. **Capability plane** — ephemeral forged tools/services, reusable workflows, environment capsules.
3. **Evidence plane** — benchmarks, properties, adversarial mutants, containment gates, experiment results.
4. **Memory plane** — procedural skills, failure regressions, architectural self-model, compact context products.
5. **Evolution plane** — candidate descendants, lineage, replay, search, promotion/retirement policy.
6. **Reactor plane** — guest-local events and bounded autonomous investigations.

The Lab’s behavior then becomes:

> **Observe → identify uncertainty/gap → retrieve memory → invent if needed → fork experiments → evaluate → attack the evaluator → select → retain useful procedure → learn from failures → emit evidence → remain reversible.**

The host remains deliberately boring. It provides isolation, tunnel/control boundaries, external recovery, and the canonical human-visible history. The Lab never needs host credentials to become dramatically more capable; its freedom comes from being able to build arbitrary worlds **inside** the VM.

A mature version could receive a goal such as:

> “Become better at repairing Python services without increasing permanent MCP complexity.”

It would inspect its self-model and trace history, detect repeated edit/restart failure modes, compile a bounded research context, invent two or three edit/recovery capabilities, generate mutants and tests, spawn descendants, run them, attack weak validators, select a winner, replay old failures, distill the successful procedure, and produce an evidence-backed next-generation handoff.

At that point ChatGPT is no longer manually operating every mechanical layer. It becomes the external collaborator that chooses goals, reviews consequential architectural changes, and occasionally challenges the Lab’s assumptions.

That would make the project feel genuinely **alive** while preserving the core philosophy that made the first three generations work:

- capability should compound;
- repeated reasoning should become machinery;
- failures should become evidence;
- evidence should precede promotion;
- abstractions must remain inspectable;
- experiments must be reversible;
- permanent bespoke tooling should stay small;
- the VM remains the security boundary.

The wildest credible destination is an **Evolution Garden**: an outer Lab that grows contained descendant computers, lets them mutate their own engineering substrate, generates the tests that judge them, preserves their genealogy, and learns procedures from both winners and failures. Crucially, none of those descendants ever needs the keys to the host kingdom.

---

## Research references

Accessed/reviewed 2026-08-26. These are sources for transferable primitives, not dependencies to copy wholesale.

- **[R1] Darwin Gödel Machine** — self-improving coding agents with empirical evaluation and an archive/tree of variants. https://arxiv.org/abs/2505.22954
- **[R2] AlphaEvolve** — LLM-generated program evolution with automated evaluators and a program database. https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
- **[R3] AlphaEvolve impact update** — applications/scaling of evaluator-driven evolutionary coding. https://deepmind.google/blog/alphaevolve-impact/
- **[R4] Live-SWE-agent** — runtime evolution of a software-engineering agent scaffold. https://arxiv.org/abs/2511.13646
- **[R5] Hyperagents** — editable task/meta-agent program for agent self-improvement. https://arxiv.org/abs/2603.19461
- **[R6] ToolMaker / LLM Agents Making Agent Tools** — autonomous packaging of software into tested agent-callable tools. https://arxiv.org/abs/2502.11705
- **[R7] Tool-Genesis** — task-driven tool creation benchmark for self-evolving agents. https://doi.org/10.48550/arXiv.2603.05578
- **[R8] CREATOR** — LLM creation/use of executable tools. https://arxiv.org/abs/2305.14318
- **[R9] SoK: Agentic Skills** — lifecycle framing for procedural skills, composition, evaluation, and update. https://doi.org/10.48550/arXiv.2602.20867
- **[R10] Voyager** — executable skill library + automatic curriculum + self-verification. https://arxiv.org/abs/2305.16291
- **[R11] Reflexion** — compact episodic verbal feedback across attempts. https://arxiv.org/abs/2303.11366
- **[R12] OpenHands Skills** — on-demand progressive-disclosure procedural context. https://docs.openhands.dev/overview/skills
- **[R13] Temporal** — durable execution/replay concepts. https://temporal.io/
- **[R14] Restate: versioning long-running agents** — durable journals and deployment/version pinning. https://restate.dev/blog/dealing-with-versioning-in-long-running-agents
- **[R15] DBOS workflow tutorial** — database-backed durable workflow/checkpoint concepts. https://docs.dbos.dev/python/tutorials/workflow-tutorial
- **[R16] Pydantic AI durable execution** — durable-agent integration patterns across Temporal/DBOS/Prefect/Restate. https://ai.pydantic.dev/durable_execution/overview/
- **[R17] LangGraph persistence** — checkpoints, fault tolerance, interrupts, and time-travel/fork concepts. https://docs.langchain.com/oss/python/langgraph/persistence
- **[R18] Nix reproducibility** — explicit/content-addressed build inputs and reproducibility checks. https://reproducible.nixos.org/
- **[R19] Firecracker snapshot support** — microVM snapshot/restore and copy-on-write concepts. https://github.com/firecracker-microvm/firecracker/blob/main/docs/snapshotting/snapshot-support.md
- **[R20] Daytona snapshots** — point-in-time sandbox/environment cloning concepts. https://www.daytona.io/docs/snapshots/
- **[R21] SWE-ReX** — software-engineering runtime abstraction and parallel isolated environments. https://github.com/SWE-agent/swe-rex
- **[R22] Hypothesis stateful testing** — generated action sequences/model-based state-machine testing. https://hypothesis.readthedocs.io/en/latest/stateful.html
- **[R23] Terminal-Bench** — terminal-agent evaluation and benchmark-validator quality lessons. https://www.tbench.ai/
- **[R24] OpenTelemetry GenAI/MCP semantic conventions** — emerging trace vocabulary for tools/agents/workflows. https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md
- **[R25] Arize Phoenix** — open-source tracing/evaluation/experiment lineage for AI systems. https://phoenix.arize.com/
- **[R26] Prometheus: repository-level code knowledge graph** — structural + semantic repository representation. https://arxiv.org/abs/2507.19942
- **[R27] RANGER** — hierarchical/cross-file repository graph retrieval and exploration. https://arxiv.org/abs/2509.25257
- **[R28] WebArena** — realistic reproducible web-agent environment. https://arxiv.org/abs/2307.13854
- **[R29] BrowserGym / WorkArena** — browser-agent experimentation/benchmark infrastructure. https://arxiv.org/abs/2412.05467
- **[R30] Hacker News: MCP-skill** — community experiment compiling MCP use into typed Python skills to reduce model↔tool loops and support progressive disclosure. https://news.ycombinator.com/item?id=47274589
- **[R31] Hacker News: MCPglue** — community experiment in agents constructing task-specific tools dynamically. https://news.ycombinator.com/item?id=44158588
- **[R32] Hacker News: Representing Agents as MCP Servers** — composable MCP workflows with durable execution. https://news.ycombinator.com/item?id=44053754
- **[R33] Reddit / r/LocalLLaMA community discussions reviewed** — recurring anecdotes around context growth, checkpoints, tool-loop length, local coding harnesses, and model-role separation. Treat as directional community evidence, not authoritative benchmarks. https://www.reddit.com/r/LocalLLaMA/
- **[R34] Coccinelle** — semantic patching concepts for structure-aware source transformations. https://coccinelle.gitlabpages.inria.fr/website/
- **[R35] Agent Lightning** — trajectory-oriented agent/RL decoupling; potentially useful much later. https://arxiv.org/abs/2508.03680
- **[R36] Meta-Router** — task-aware LLM routing research. https://arxiv.org/abs/2509.25535
- **[R37] One Head, Many Models** — routing across model portfolios. https://arxiv.org/abs/2509.09782
- **[R38] CARROT** — cost-aware model routing research. https://arxiv.org/abs/2502.03261
- **Additional coding-interface reference:** SWE-agent’s Agent-Computer Interface work reinforces that the interface between agent and computer materially affects coding performance. https://arxiv.org/abs/2405.15793
- **Additional multi-agent reference:** Google DeepMind’s AI co-scientist uses supervisor/competition/evolution/meta-review patterns that are useful as inspiration for adversarial experiment roles, not as a framework to copy. https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/

---

## Bottom line

Gen1–Gen3 proved the direction is **fewer permanent tools, stronger guest-local abstractions**, and the live Gen4 transition has now added the missing composition layer without expanding the 10-tool MCP surface. Once Gen4 finishes its independent benchmark/handoff, the next generation should become genuinely evolutionary: **the Lab should be able to invent a capability it does not have, create evidence for it, use it, and decide whether it deserves to survive.**
