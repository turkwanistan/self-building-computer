# Status

Lifecycle phase: `PUBLICATION_READY`

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
- separate Secure MCP Tunnel identity `tunnel_6a8e3523aa748191a0d03f232393a557` configured as host profile `optiplex-lab` targeting `http://192.168.127.10:8890/mcp`;
- `tunnel-client doctor` passed, MCP target reachable, health listener configured at `127.0.0.1:8794`;
- separate `mcp-lab-tunnel.service` is active and ready;
- existing production `mcp-tunnel.service` remains active and unchanged;
- fresh ChatGPT session exposed exactly the seven expected `Optiplex_Lab` tools: `shell`, `read_file`, `write_file`, `list_files`, `job`, `service`, and `reboot`;
- ChatGPT-side lab smoke acceptance passed: root shell, public HTTPS, exact write/read-back, cleanup, and blocked access to host service `192.168.127.1:8790`;
- ChatGPT memory/handoff policy implemented in `docs/CHATGPT_MEMORY_AND_HANDOFF.md`; repository/root-owned state explicitly outranks ChatGPT memory and old chats;
- project-native test suite passed after ChatGPT lab acceptance (`python -m pytest -q`);\n- high-confidence repository secret/credential scan passed;\n- acceptance JSON and JSONL records validate.

What the lab can do once its ChatGPT connector is active:

- execute arbitrary commands as root inside the guest;
- install packages/tools from the public internet;
- clone/build/test repositories;
- rewrite guest files, including its own MCP implementation;
- create long-running jobs and control systemd services;
- reboot and recover from the host-owned `known-good` snapshot.

This is intentionally powerful **inside the VM only**. It does not possess host credentials, host mounts, Docker/libvirt sockets, Tailscale access, or private-network access.

Current gate:

1. run project tests and a secret/credential scan;
2. create the first commit and prepare this `self-building-computer` repository for GitHub publication;
3. only after repository publication, continue root-owned immutable release / blue-green safe-MCP lifecycle machinery.

Important distinction: the lab is ready to self-modify and build capabilities inside the isolated guest, but the automatic **candidate → validate → promote/rollback** lifecycle for the safe production MCP is not implemented yet.

Do not place tunnel credentials inside the unrestricted guest and do not replace the existing production MCP/tunnel.
