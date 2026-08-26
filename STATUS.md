# Status

Lifecycle phase: `PUBLISHED_READY_FOR_BLUE_GREEN`

Implemented and verified:

- generation-0 safe MCP baseline: 51 tools, schema SHA256 `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`;
- original source regression suite preserved: 66 passed, 10 skipped;
- low-privilege evolvable front-end implemented as an exact-schema proxy to the current safe MCP;
- broad 7-tool lab MCP implemented for use only inside `mcp-lab`;
- tunnel credentials removed from writable project/deployment copies; protected runtime copy remains host-controlled;
- dedicated `mcp-lab-net` created at `192.168.127.0/24` with fixed guest `192.168.127.10`;
- `mcp-lab` created with 2 vCPU, 2 GiB RAM, 30 GiB disk, autostart, SSH recovery, serial console, and host-owned `known-good` snapshot;
- full lab acceptance passed: root execution, public internet, exactly 7 MCP tools; private/LAN/Tailscale/Docker/libvirt/host-service access blocked; no host mounts/control sockets;
- guest bootstrap includes Python/venv/pip, Git, curl, build-essential, SSH, and unrestricted root shell; additional guest software can be installed from the public internet;
- separate host-side Secure MCP Tunnel is active as profile `optiplex-lab`, service `mcp-lab-tunnel.service`, targeting `http://192.168.127.10:8890/mcp`;
- exact tunnel ID is intentionally not cached in repository state; verify it live from `/home/mcp/.config/tunnel-client/optiplex-lab.yaml` when needed;
- fresh ChatGPT session exposed exactly the seven expected `Optiplex_Lab` tools: `shell`, `read_file`, `write_file`, `list_files`, `job`, `service`, and `reboot`;
- ChatGPT-side lab smoke acceptance passed: root shell, public HTTPS, exact write/read-back, cleanup, and blocked access to host service `192.168.127.1:8790`;
- `CHATGPT_LAB_ACCEPTED` recorded in repository state/history;
- ChatGPT memory/handoff policy implemented in `docs/CHATGPT_MEMORY_AND_HANDOFF.md`; repository/root-owned state explicitly outranks ChatGPT memory and old chats;
- project-native tests, secret/credential scan, and JSON/JSONL validation passed;
- first bootstrap commit `40c5624` created;
- repository published to `git@github.com:turkwanistan/self-building-computer.git` on branch `main`;
- local tracking repaired to `main...origin/main` after publication.

What the lab can do:

- execute arbitrary commands as root inside the guest;
- install packages/tools from the public internet;
- clone/build/test repositories;
- rewrite guest files, including its own MCP implementation;
- create long-running jobs and control systemd services;
- reboot and recover from the host-owned `known-good` snapshot.

This is intentionally powerful **inside the VM only**. It does not possess host credentials, host mounts, Docker/libvirt sockets, Tailscale access, or private-network access.

Current gate / next stage:

1. implement the root-owned immutable release and blue/green safe-MCP lifecycle defined by repository authority;
2. preserve the existing production MCP as the stable/guardrail release while candidates are built and validated separately;
3. validate a no-op candidate before any real capability evolution;
4. retain explicit promotion/rollback gates and never widen host security authority without explicit user approval;
5. once lifecycle controls pass, begin the first deliberate self-evolution/superpower iteration.

Important distinction: the lab is already capable of self-modifying inside the isolated guest. The remaining work is the controlled **candidate → validate → activate → promote/rollback** path for the safe production MCP.
