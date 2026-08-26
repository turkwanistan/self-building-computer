# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_GEN1_LAB_ACCEPTED_SELF_HOSTED_LAB`

Generation 1 evolved **Optiplex_Lab + the isolated `mcp-lab` VM**. `Optiplex_MCP` remained frozen and unchanged.

## Frozen safe control plane

Final live verification still matches the accepted anchor:

- release: `frontend-a5c1c5be8b22`;
- guardrail: `guardrail-gen0-c51a9161a95d`;
- exactly 51 tools;
- schema SHA256: `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`;
- policy: `authority-v1`.

Do not modify the safe MCP, legacy `optiplex-mcp-agent`, guardrail, blue/green lifecycle, or host authority as part of Lab evolution.

Abandoned safe-MCP Generation 1 work was observed earlier in the session and was not continued or modified. The final working-tree status no longer lists those `mcp_frontend`/benchmark/test remnants; the Lab generation described here is the authoritative Generation 1 implementation.

## Generation 1 accepted Lab

Milestone: **`SELF_HOSTED_LAB` reached.**

Accepted guest build:

- generation: `gen1-self-hosted-lab-r2`;
- build ID: `gen1-self-hosted-lab-r2-f3bb6eb79d33`;
- source SHA256: `f3bb6eb79d3370e7bf1d1ea15525b8e4ab496767454e6c1f5f05a9b3bd480b16`;
- live tool surface: 10 tools — `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.

Capabilities added inside the VM:

- sanitized, bounded JSONL tracing with command/content hashes rather than bodies;
- explicit episode outcomes via `lab-outcome`;
- automatic large-output spooling with previews, SHA256 metadata, retention bounds, and sensitive-pattern suppression;
- `read_range` for large artifacts;
- durable jobs implemented as independent transient systemd units so they survive MCP restarts;
- `lab_status` build/source/trace/spool/skills identity;
- `self_restart` that schedules restart after the requesting call returns;
- candidate validation + guest-local self-update utility;
- recovery launcher + last-known-good automatic rollback;
- 17-task benchmark, self-test, failure miner, and four reusable Lab skills;
- guest utilities: `jq`, `ripgrep`, `sqlite3`, `lsof`, `strace`, `tree`.

## Evidence

- self-test: **12/12 PASS**;
- benchmark before: **17/17 PASS**, 20066.44 ms, target feature coverage **0/5**;
- benchmark after: **17/17 PASS**, 7368.28 ms, target feature coverage **5/5**;
- durable job across MCP restart: **PASS** (`DURABLE_JOB_R2_OK`);
- intentional syntax-corruption recovery: **PASS** — launcher observed a 0.012 s failed child, restored the accepted SHA, and the recovered MCP returned to 12/12 self-test;
- containment: **PASS** — public HTTPS works; `192.168.127.1:8790`, representative RFC1918/Tailscale probes remain blocked; no host Docker/libvirt/Tailscale sockets, host mount markers, or private-key material detected.

The timing improvement is not treated as intrinsic performance evidence because package/cache warm-up explains much of it. Correctness, containment, feature coverage, restart durability, and recovery are the acceptance signal.

Guest evidence: `/var/lib/optiplex-lab/results/generation1-result.json`. Repository mirror: `lab_generations/GEN1_RESULT.json`.

## Connector refresh boundary

The already-open ChatGPT session retained the original seven-tool connector schema even after the live MCP evolved. A guest-local MCP client verified the live 10-tool surface. A **fresh ChatGPT session / connector refresh is required** to expose `read_range`, `lab_status`, and `self_restart` directly in ChatGPT.

## Generation 2 — proposed, not started

The failure miner ranked **Lab-native Code Mode / orchestration runner** first because 16/36 traced Gen1 tool calls were still raw `shell`; self-hosting works, but multi-step inspect/edit/test/restart sequences remain manually composed. See `lab_generations/GEN2_PROPOSALS.json`.

Do not implement Generation 2 automatically.
