Use both `Optiplex_MCP` and `Optiplex_Lab` where appropriate, but obey this architecture strictly:

**Optiplex_Lab and the `mcp-lab` VM are the system being evolved. `Optiplex_MCP` is frozen safe host infrastructure and must not be changed.**

This is the first real Self-Building Computer evolution cycle.

Repository:
`/home/mcp/projects/projects/self-building-computer`

Start by reading `START_HERE.md` and follow its fresh-session protocol exactly. Then read `state/current.json`, `STATUS.md`, `NEXT_SESSION.md`, `docs/AUTHORITY_BOUNDARY.md`, and **read `plans/GEN1_SELF_OBSERVATION.md` in full**.

Repository/live machine state are authoritative over this prompt, prior chats, and ChatGPT memory.

Before changing anything:

1. verify live `Optiplex_MCP` identity with `system_info` only to confirm the frozen safe control plane is still the accepted release/schema/policy;
2. do not modify, stage, activate, promote, benchmark, add tools to, or otherwise evolve `Optiplex_MCP`, its guardrail, blue/green lifecycle, or legacy source repo;
3. verify `Optiplex_Lab` is available and initially exposes exactly its accepted seven tools: `shell`, `read_file`, `write_file`, `list_files`, `job`, `service`, `reboot`;
4. inspect the Lab VM thoroughly: OS, packages, disks, memory, services, Lab MCP source/runtime, logs, current files/state, and recovery options;
5. confirm the guest still has root and public internet and still cannot reach protected host/private resources;
6. inspect Git/state in the `self-building-computer` repository and preserve existing work.

Then autonomously execute Generation 1 according to `plans/GEN1_SELF_OBSERVATION.md`.

The object of evolution is the Lab VM itself. You may use guest root, install packages, clone public repos, build software, create services/databases, run containers inside the guest if useful, rewrite/restart the Lab MCP, change its tool behavior or tool surface when justified, create scripts/skills, and otherwise improve the disposable VM aggressively.

The mission is to give the Lab evidence about its own behavior by implementing the smallest coherent versions of:

- sanitized trace + explicit outcome recording;
- large-output spooling;
- a cheap real-world Lab benchmark;
- failure mining that produces ranked improvement proposals;
- a minimal reusable Lab skills mechanism.

Use the Lab as both the subject and the forge. Research and prototype freely on the public internet from inside the VM. Prefer fewer powerful primitives and reusable skills over speculative permanent tool growth, but do not treat the current seven Lab tools as a permanent ceiling.

Non-negotiable host boundary:

- never copy host credentials/SSH/Git/tunnel/API secrets into the guest;
- never add host filesystem mounts;
- never expose host Docker/libvirt sockets;
- never join Tailscale or the physical/private LAN;
- never weaken the host firewall/isolation boundary;
- never give the Lab authority over Optiplex_MCP deployment or root host lifecycle state.

If a desired improvement genuinely requires crossing that boundary, stop and ask me. Do not solve it by changing Optiplex_MCP.

Do NOT use the Optiplex_MCP blue/green candidate lifecycle for Generation 1. That lifecycle protects the safe host MCP and is out of scope. Establish only the smallest useful Lab-generation/checkpoint/recovery record inside the VM and durable story/state in the `self-building-computer` repo.

Benchmark the Lab before/after where practical. Correctness and containment are hard gates. Then compare success, retries, elapsed time, Lab MCP calls, output/context volume, and complexity. Do not optimize one scalar score.

Once Generation 1 machinery works, use its own traces, benchmark results, and documented history to create 3–5 ranked Generation 2 recommendations answering:

> What should the Lab become next to better accomplish the user's real projects?

Do not assume the answer is another MCP tool. It may be an environment/toolchain improvement, skill, Code-Mode-like orchestration, browser stack, container workflow, static analysis/fuzzing, temporary tool synthesis, context strategy, or something not anticipated here.

Do not begin Generation 2.

Before stopping:

- re-verify VM containment;
- update `state/current.json`, `STATUS.md`, `NEXT_SESSION.md`, and `history/events.jsonl` to describe the Lab generation;
- leave the `self-building-computer` repository tests/state valid;
- prepare a fresh-session verification procedure for the evolved `Optiplex_Lab`;
- report the Lab generation identifier, Lab MCP tool/schema changes if any, packages/services/environment changes, exact functional/containment test results, before/after benchmark summary, what Generation 1 learned, top Generation 2 recommendation, and recovery instructions.

Do not commit or push unless I explicitly ask. Do not modify the legacy `optiplex-mcp-agent` repository. Do not modify Optiplex_MCP.
