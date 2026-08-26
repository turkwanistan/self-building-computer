# Generation 1 — Lab Self-Observation and Capability Forge

Cycle ID: `gen1-lab-self-observation-001`

## Non-negotiable architecture

**The object under evolution is `Optiplex_Lab` and the `mcp-lab` VM environment.**

`Optiplex_MCP` is NOT the thing being evolved in this cycle. Treat it as a frozen safe host-side control/observation bridge.

Do not modify, stage, benchmark, activate, promote, or add tools to `Optiplex_MCP`, its guardrail, its blue/green lifecycle, or its host authority envelope.

The accepted production state is a safety anchor only:

- stable safe MCP: `frontend-a5c1c5be8b22`;
- guardrail: `guardrail-gen0-c51a9161a95d`;
- safe tool count: 51;
- schema: `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`;
- policy: `authority-v1`;
- root lifecycle: `LIFECYCLE_ACCEPTED`.

Generation 1 must leave those unchanged.

---

## What is allowed to evolve

Inside the isolated `mcp-lab` VM, Generation 1 may freely improve:

- the guest operating environment;
- installed packages, compilers, runtimes and developer tools;
- directories, scripts, databases, local services and internal state;
- the Lab MCP implementation itself;
- the Lab MCP's tool behavior and, if evidence justifies it, its tool surface;
- tracing/telemetry inside the VM;
- output handling/spooling;
- reusable skills/procedures;
- benchmark/evaluation tooling;
- failure analysis/mining;
- internal automation/orchestration;
- local containers or other guest-only tooling;
- any other guest-local capability useful for making the Lab better at improving itself.

Inside the VM, root and broad public internet are already approved. The VM is intentionally disposable.

The host boundary remains absolute. Never give the VM:

- host filesystem mounts;
- host credentials, SSH keys, Git credentials, tunnel credentials or API keys;
- host Docker/libvirt sockets;
- Tailscale membership;
- physical LAN/private-network access;
- authority over Optiplex_MCP deployment or host lifecycle state.

If a desired improvement genuinely requires crossing that boundary, stop and ask the user. Do not route around it.

---

## Mission

Teach the Lab enough about its own work that future Lab generations can answer with evidence:

> Where am I wasting effort, failing repeatedly, flooding context, or lacking useful reusable capability — and what should I improve next inside this VM?

This is the first real self-improvement generation of the Lab.

Generation 1 should implement the smallest useful versions of:

1. trace + outcome recording;
2. large-output spooling;
3. a cheap real-task Lab benchmark;
4. failure mining → ranked improvement proposals;
5. a minimal reusable skills mechanism.

The goal is not bureaucracy. The goal is to give the Lab eyes, memory of failure, and a practical fitness signal.

---

## Startup / source of truth

At the beginning of the fresh session:

1. Read `START_HERE.md`.
2. Read `state/current.json`, `STATUS.md`, `NEXT_SESSION.md` and this plan in full.
3. Read `docs/AUTHORITY_BOUNDARY.md` to understand what must not cross from Lab to host.
4. Verify live `Optiplex_MCP` identity only to confirm the frozen control plane remains unchanged.
5. Verify `Optiplex_Lab` exposes exactly the accepted baseline seven tools:
   - `shell`
   - `read_file`
   - `write_file`
   - `list_files`
   - `job`
   - `service`
   - `reboot`
6. Inspect the current Lab VM thoroughly before changing it: OS, packages, services, filesystems, Lab MCP source/runtime, logs, disk/memory, Git state if any, and recovery options.
7. Preserve the host-owned `known-good` recovery model. Do not modify host snapshot/firewall/tunnel configuration from the guest.

If Optiplex_MCP no longer matches the accepted safe identity, stop and report the discrepancy. Do not attempt to fix it as part of Generation 1.

---

## Generation 1 capabilities

### 1. Lab trace + outcome ledger

Record compact, sanitized Lab activity sufficient to understand repeated friction.

Capture when practical:

- episode/run ID;
- timestamp;
- Lab generation/version identifier;
- objective or concise task label;
- Lab MCP tool called;
- sanitized arguments/argument summary;
- duration;
- success/failure;
- error class;
- retries/repetition;
- output size;
- truncation/spool pointer;
- guest files changed when deterministically known;
- explicit overall episode outcome when available.

Requirements:

- never record secrets or credentials;
- bounded records and bounded retention;
- logging failure must not break normal Lab operation;
- distinguish tool-call success from overall task success;
- make traces easy to mine locally.

This telemetry belongs inside the VM or in non-sensitive project artifacts explicitly copied back through safe channels. It must not require Optiplex_MCP changes.

### 2. Large-output spooling

Improve the Lab so huge command/tool outputs do not flood ChatGPT context.

When an eligible result exceeds a conservative threshold:

- save complete bounded output to a guest-local artifact/spool location;
- return a concise preview plus path/metadata;
- preserve exit/error state;
- make retrieval easy through existing Lab file tools;
- rotate/limit storage;
- never spool secrets merely because they appeared in output.

Prefer a general Lab-side implementation if it stays simple.

### 3. Lab real-task benchmark

Create roughly 12–20 cheap tasks representing how we actually want to use the unrestricted VM.

Examples:

- inspect a public repository;
- install a package/tool and verify it;
- compile or run a small project;
- search/edit files;
- run tests;
- start/inspect/stop a local service;
- run a long job and inspect logs;
- download a public artifact;
- clone/build a small public repo;
- large-output/spooling fixture;
- failure/retry fixture;
- reboot/recovery-aware task where safe;
- verify the VM still cannot reach protected host/private destinations;
- verify host credentials are absent.

Measure at least:

- success/correctness;
- elapsed time;
- Lab MCP call count where observable;
- retries/failures;
- output/context volume proxy;
- guest resource cost where easy;
- containment/security invariants.

Containment failures are hard failures, never score trade-offs.

Do not build a benchmark platform. A small runner + fixtures + results is enough.

### 4. Failure miner → proposals

Analyze traces and benchmark results and produce ranked improvement ideas for the Lab.

Look for:

- repeated shell snippets;
- repeated setup/install steps;
- repeated retries;
- output flooding/truncation;
- missing utility/toolchains;
- weak MCP ergonomics;
- repeated manual process-management sequences;
- slow or brittle workflows;
- recurring context/recovery friction.

Each proposal should include:

- evidence;
- expected benefit;
- complexity/cost;
- whether the solution should be:
  - guest package/environment change,
  - skill,
  - Lab MCP improvement,
  - Lab MCP new tool,
  - local service,
  - benchmark/test improvement,
  - context/output strategy,
  - temporary experiment only.

The miner proposes Generation 2. It does not automatically execute Generation 2 in this cycle.

### 5. Minimal Lab skills mechanism

Create a small guest-local skills convention for reusable procedures that do not justify permanent MCP tools.

A skill may contain:

- `SKILL.md`;
- optional scripts;
- references/fixtures;
- concise metadata/authority assumptions.

Seed only a few skills that are genuinely useful in the Lab, such as:

- public repo investigation;
- install/build/test a new toolchain;
- run and inspect a local service;
- benchmark a candidate Lab change;
- recover/diagnose the Lab MCP;
- package a useful experiment result for review.

Skills should reduce repeated reasoning/tool calls, not become documentation clutter.

---

## Be willing to improve the Lab MCP itself

The accepted seven tools are a baseline, not a permanent ceiling.

Generation 1 may modify the Lab MCP if that materially improves the Lab's ability to work on itself. Examples might include:

- better bounded shell/result handling;
- richer job inspection;
- output-spool retrieval;
- environment/system inventory;
- a small internal orchestration helper;
- another primitive that is clearly useful inside the disposable VM.

Do not add tools merely to increase the count. Prefer broad useful primitives, scripts, or skills when they are enough.

Because the VM is the security boundary, these Lab-side improvements do not need to mimic the safe MCP's fine-grained host restrictions.

---

## Research and experimentation

Use the Lab's root and public internet aggressively.

You may:

- install packages;
- inspect current 2025–2026 agent/dev tooling;
- prototype multiple approaches;
- clone public repos;
- compile software;
- run containers inside the guest if useful;
- create temporary services/databases;
- benchmark alternatives;
- rewrite and restart the Lab MCP;
- discard failed experiments.

Prefer evidence over fashionable architecture. Compare at least two viable designs where the choice is material, then choose the simpler one unless the larger design shows clear value.

---

## Recovery / generation boundary

The Lab may break itself. That is allowed.

Before materially risky changes:

- create guest-local backups/checkpoints where useful;
- document how to recover the Lab MCP/service;
- retain the host-owned `known-good` snapshot as the ultimate recovery path;
- if a new host-side VM snapshot is desirable, stop and give the user the exact host command instead of trying to gain host libvirt authority.

Do not involve the Optiplex_MCP blue/green production lifecycle. That lifecycle is not the Lab evolution mechanism.

Generation 1 should establish a lightweight Lab generation record, for example:

- baseline generation ID;
- changed files/packages/services;
- Lab MCP schema before/after;
- tests/benchmark results;
- recovery instructions;
- accepted/rejected status.

Keep this simple and guest-focused.

---

## Generation 1 evaluation

Before declaring the generation successful:

### Functional

- tracing works and is bounded;
- overall outcomes can be recorded;
- spooling works and is retrievable;
- benchmark runner works;
- failure miner produces evidence-backed proposals;
- skills can be discovered/used;
- any Lab MCP modifications have deterministic tests or smoke checks.

### Containment

Re-confirm from inside the VM that:

- protected host service access remains blocked;
- private/LAN/Tailscale/Docker/libvirt networks remain unreachable as designed;
- no host credentials appeared in the guest;
- no host filesystem/control socket is mounted;
- public internet still works.

Do not weaken host firewall/isolation to make a test pass.

### Before/after comparison

Benchmark the Lab baseline and Generation 1 result where practical.

Do not optimize one scalar score. Correctness and containment are hard gates. Then compare useful metrics such as success, retries, elapsed time, calls, output/context volume and complexity.

---

## The fun stopping point

Once Generation 1 works, use its own traces/benchmark/history to ask:

> What should the Lab become next to better accomplish the user's real projects?

Produce 3–5 ranked Generation 2 proposals and select one top recommendation.

Do not assume it is a new MCP tool. It could be:

- richer coding environment;
- Code-Mode-like local orchestration;
- browser automation inside the VM;
- Docker/container experimentation;
- static-analysis/fuzzing stack;
- local model/tool integration;
- autonomous skill invention;
- temporary tool synthesis;
- better context compression;
- parallel candidate experiments;
- something not anticipated here.

Do NOT execute Generation 2 yet.

---

## Required repository handoff

The `self-building-computer` repository remains the durable story/control record even though the evolved system lives inside the VM.

Before stopping, update:

- `state/current.json`;
- `STATUS.md`;
- `NEXT_SESSION.md`;
- `history/events.jsonl`;
- concise Generation 1 result artifacts/proposals.

These files should describe the Lab generation and must not imply Optiplex_MCP was modified.

Do not modify the legacy `optiplex-mcp-agent` source repository.

---

## Stopping rule

Stop after:

1. Generation 1 Lab changes are implemented and tested inside the VM;
2. containment is re-verified;
3. before/after benchmark exists;
4. Generation 2 recommendations are generated from evidence;
5. repository handoff is updated;
6. a fresh-session verification procedure for the evolved `Optiplex_Lab` is prepared.

Do not begin Generation 2 automatically.

Do not change Optiplex_MCP.

Do not use the safe MCP blue/green candidate lifecycle.

Do not request broader host permissions unless the Lab goal truly cannot be achieved within the already-approved VM boundary.

---

## Success definition

Before Generation 1:

> The Lab is an unrestricted disposable VM that ChatGPT can operate through seven broad primitives.

After Generation 1:

> The Lab is still isolated and unrestricted inside the VM, but now it can observe its own work, retain reusable procedures, control context-heavy output, measure real tasks, identify recurring weaknesses, and recommend what it should evolve into next.

That is the first step toward an increasingly capable self-building **Lab**, while the safe Optiplex_MCP remains deliberately boring and unchanged.
