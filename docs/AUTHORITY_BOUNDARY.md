# Generation-0 Authority Boundary

## Protected authority-bearing components

These mechanisms currently possess or enforce sensitive host authority and must remain outside autonomous candidate control:

- canonical project/path confinement (`fs_policy.py` and filesystem mediator behavior);
- rootless Docker socket access and sandbox launch policy (`docker_runtime.py`, `sandbox_spec.py`, command/job/service launch paths);
- managed execution ownership, resource and network separation;
- Git credential and network mediation;
- exact-package outbound network broker and registry allowlist;
- bounded Playwright/browser broker;
- credential locations and environment files;
- root-owned systemd, tunnel, staging, activation, promotion and rollback state.

## Evolvable capability layer

The 51 current tool names/schemas are generation 0, not a permanent protected API. Milestone 1 preserves them by proxying through the existing generation-0 MCP as a temporary guardrail backend. New user-facing capabilities can later be implemented in the low-privilege front-end when they stay inside the existing authority envelope.

## Candidate confinement target

The evolvable front-end must not receive the Docker socket, Git/tunnel credentials, arbitrary host filesystem mounts, general outbound internet, or write access to root-owned release/policy/systemd state. It should reach sensitive operations only through the protected loopback MCP/broker endpoint.
