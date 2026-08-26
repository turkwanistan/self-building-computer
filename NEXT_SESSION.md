# NEXT SESSION

Fresh-session objective: begin the root-owned immutable release / blue-green safe-MCP lifecycle stage. Publication and ChatGPT lab acceptance are complete.

Read first, in order:

1. `START_HERE.md`
2. `state/current.json`
3. `STATUS.md`
4. `docs/AUTHORITY_BOUNDARY.md`
5. the relevant implementation plan/spec before changing lifecycle code

Authoritative setup already complete:

- Existing production connector `Optiplex_MCP` remains active and is the stable/guardrail release.
- `mcp-lab` is accepted and recoverable from the host (`known-good` snapshot, SSH, serial console).
- Lab MCP endpoint: `http://192.168.127.10:8890/mcp`.
- Lab MCP exposes exactly seven tools: `shell`, `read_file`, `write_file`, `list_files`, `job`, `service`, `reboot`.
- Separate host-side Secure MCP Tunnel is active as profile `optiplex-lab` / service `mcp-lab-tunnel.service`.
- Do not trust a cached tunnel ID: verify it live from `/home/mcp/.config/tunnel-client/optiplex-lab.yaml` if needed.
- A fresh ChatGPT session exposed exactly the seven expected `Optiplex_Lab` tools and completed the harmless smoke test.
- `CHATGPT_LAB_ACCEPTED` is recorded.
- Repository tests, secret scan, and state validation passed.
- Bootstrap commit `40c5624` was published to `git@github.com:turkwanistan/self-building-computer.git` on `main`.

Next stage:

1. inspect current repository/live host state and preserve all existing work;
2. implement root-owned immutable stable/candidate/previous release state and blue/green activation without replacing the current production MCP in place;
3. build a no-op candidate first;
4. validate schema/tool parity, regression tests, service health, browser acceptance where applicable, and rollback;
5. require explicit promotion and preserve host security authority;
6. only after lifecycle acceptance, start the first real capability/superpower iteration.

Never reconstruct mutable technical state from ChatGPT memory. Repository state and live verification outrank prior chats and remembered values.
