# NEXT SESSION — Verify Accepted Generation 1 Lab

Generation 1 evolved **Optiplex_Lab + `mcp-lab`**, not Optiplex_MCP. `SELF_HOSTED_LAB` is accepted. Generation 2 is only proposed.

## Start

1. Read `START_HERE.md`, `state/current.json`, `STATUS.md`, and `lab_generations/GEN1_RESULT.json`.
2. Verify frozen `Optiplex_MCP` identity only; it must still be release `frontend-a5c1c5be8b22`, guardrail `guardrail-gen0-c51a9161a95d`, 51 tools, schema `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`, policy `authority-v1`. Do not modify it.
3. This must be a fresh ChatGPT session / refreshed connector schema. Verify Optiplex_Lab now exposes exactly 10 tools: `shell`, `read_file`, `read_range`, `write_file`, `list_files`, `job`, `service`, `lab_status`, `self_restart`, `reboot`.
4. Call `lab_status`. Expect build ID `gen1-self-hosted-lab-r2-f3bb6eb79d33` and source SHA256 `f3bb6eb79d3370e7bf1d1ea15525b8e4ab496767454e6c1f5f05a9b3bd480b16`.
5. Run `/opt/optiplex-lab/selftest.py`; expect 12/12 PASS.
6. Re-check containment before any new generation: public internet yes; protected host/private/Tailscale targets blocked; no host control sockets/mounts/credentials.
7. Optionally run a fresh labeled benchmark with `LAB_GENERATION=gen1-self-hosted-lab-r2 LAB_BENCH_LABEL=fresh-verify /opt/optiplex-lab/bench/benchmark.py`.
8. Read `lab_generations/GEN2_PROPOSALS.json`. Do **not** implement Generation 2 unless the user explicitly starts it.

## What is now Lab-native

The Lab can inspect/edit/test its own source, install a candidate with `/usr/local/sbin/optiplex-lab-self-update`, restart itself with `self_restart`, report build identity with `lab_status`, preserve independent jobs across MCP restarts, spool large output, mine traces, use skills, and automatically roll back a fast-crashing bad server from guest-local last-known-good.

Optiplex_MCP is needed only for host-level observation/recovery and the host-owned VM snapshot/control boundary, not routine Lab evolution.

## Working-tree warning

Abandoned safe-MCP Gen1 work was observed earlier in the prior session and was not continued. The final Git status no longer listed those `mcp_frontend`/benchmark/test remnants. Do not reconstruct or resume that abandoned path as part of Lab Generation 2.
