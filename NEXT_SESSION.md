# NEXT SESSION

Fresh-session objective: publish this repository, then begin the separately authorized blue/green lifecycle work.

Authoritative setup already complete:

- Existing production connector `Optiplex_MCP` remains active.
- `mcp-lab` is accepted and recoverable from the host (`known-good` snapshot, SSH, serial console).
- Lab MCP endpoint: `http://192.168.127.10:8890/mcp`.
- Lab MCP exposes exactly seven tools: `shell`, `read_file`, `write_file`, `list_files`, `job`, `service`, `reboot`.
- Separate host-side Secure MCP Tunnel is active as profile `optiplex-lab` / service `mcp-lab-tunnel.service`.
- Tunnel ID: `tunnel_6a8e3523aa748191a0d03f232393a557`.
- `tunnel-client doctor` passed; production tunnel remains active.
- A fresh ChatGPT session exposed exactly the seven expected `Optiplex_Lab` tools and completed the harmless smoke test.
- `CHATGPT_LAB_ACCEPTED` is recorded in `STATUS.md`, `state/current.json`, and `history/events.jsonl`.

Do this first:

1. Verify the first commit and current test/secret-scan results.
2. Set a GitHub origin under `turkwanistan` only if the target repository is known/created; never overwrite another repo.
3. Push `main`. If MCP-side push credentials are not provisioned, provide the minimal `wan` command needed to push using the already configured GitHub SSH identity.

Do not begin blue/green safe-MCP evolution until repository publication is complete.
