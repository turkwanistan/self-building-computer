# Status

Lifecycle phase: `LIFECYCLE_ACCEPTED_READY_FOR_FIRST_ITERATION`

The full pre-looping Self-Building Computer foundation is accepted.

## Accepted production lifecycle

- stable release: `frontend-a5c1c5be8b22` on green;
- previous rollback release: `frontend-baseline-91db2634c80d` on blue;
- guardrail release: `guardrail-gen0-c51a9161a95d`;
- exact safe MCP surface: 51 tools;
- schema SHA256: `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`;
- policy: `authority-v1`;
- authority delta for the no-op lifecycle: `NONE`;
- root state: `LIFECYCLE_ACCEPTED`;
- rollback drill: PASS;
- emergency generation-0 `mcp-agent.service` remains installed but inactive.

No-op cycle `noop-lifecycle-001` completed the entire lifecycle:

`stage -> pre-activation gates -> activate -> fresh-session verification -> accept -> promote -> rollback drill`

All pre-activation gates passed: candidate tests, confinement, guardrail regression, inactive-slot smoke, and secret scan. Post-activation product-boundary checks and supplemental backend security checks also passed.

## Accepted lab

`Optiplex_Lab` remains the isolated high-power experiment zone with exactly seven tools: `shell`, `read_file`, `write_file`, `list_files`, `job`, `service`, and `reboot`. It has guest root and public internet, but no host filesystem, credentials, Docker/libvirt sockets, Tailscale, LAN/private-network, or protected host-service access. Host-owned snapshot/SSH/console recovery remains available.

## What is now allowed

A future session may begin the first real capability-evolution cycle. It must use the accepted lifecycle and preserve the authority boundary:

1. record the real limitation/original objective;
2. classify the change as normal capability evolution, `GUARDRAIL_GAP`, or `PERMISSION_REQUIRED`;
3. build and stage an immutable candidate;
4. pass functional/security/regression/confinement gates;
5. require human activation;
6. verify from a fresh ChatGPT session;
7. promote or roll back;
8. resume the original objective and record first real use.

No safe/production authority expansion may be self-approved. Root-owned lifecycle state remains authoritative over repository state, and repository/live state remains authoritative over ChatGPT memory.
