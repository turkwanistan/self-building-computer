# Blue/Green Safe-MCP Lifecycle

This stage exists to prove safe evolution before any real capability loop begins.

## Runtime

- `127.0.0.1:8790` — fixed root-controlled front door used by the existing Secure MCP Tunnel.
- `127.0.0.1:8792` — evolvable blue slot.
- `127.0.0.1:8793` — evolvable green slot.
- `127.0.0.1:8795` — protected generation-0 guardrail backend.
- `mcp-agent.service` — retained, stopped after successful bootstrap, and preserved as the emergency direct-generation-0 fallback.

The evolvable blue/green processes run as `mcp` from root-owned immutable releases under `/opt/mcp/releases`. They have loopback-only networking, no home visibility, no devices/capabilities, no `/run`, no root-owned lifecycle state, and no `/etc/mcp-agent` visibility. Sensitive authority remains in the protected guardrail backend.

## Root-owned control

Canonical deployment state lives at `/var/lib/mcp-evolution/current.json`. Canonical lifecycle events live at `/var/lib/mcp-evolution/events.jsonl` with a simple previous-event hash chain. Slot and front-door configuration lives under `/etc/mcp-evolution` and is root-owned.

The installed command is:

```text
sudo mcp-evolution status
sudo mcp-evolution stage
sudo mcp-evolution activate <release-id>
sudo mcp-evolution accept <cycle-id>
sudo mcp-evolution promote <cycle-id>
sudo mcp-evolution rollback
sudo mcp-evolution rollback --drill
```

Candidate source cannot write any of these installed files.

## Candidate staging

Normal staging consumes only:

- `mcp_frontend/**/*.py`
- `pyproject.toml`
- `candidate/release.json` as metadata/hash input

It never executes candidate-provided install scripts, systemd units, sudoers files, or root commands. A candidate with `authority_delta` other than `NONE` fails closed and must use the explicit permission path instead.

Before a candidate becomes `READY_TO_ACTIVATE`, staging requires:

- self-building project tests PASS;
- generation-0 guardrail regression tests PASS;
- source secret scan PASS;
- fixed candidate-service confinement PASS;
- inactive-slot MCP start/list-tools/schema smoke PASS.

## Activation and fresh-session gate

Activation is human-triggered. It rechecks the inactive candidate and changes only the root-owned front-door route. The old stable backend remains running. Root state becomes `FRESH_SESSION_VERIFY`.

A fresh ChatGPT session must verify release identity, expected tool count/schema, a harmless functional call, and relevant negative/security behavior. Only then should the user run `sudo mcp-evolution accept <cycle-id>`, which moves root state to `PROMOTE_READY`.

Promotion changes metadata only: candidate becomes stable and old stable becomes previous. Immutable release bytes are not rebuilt or edited.

## Rollback

Before promotion, `sudo mcp-evolution rollback` routes immediately back to the stable slot.

After the no-op candidate is promoted, `sudo mcp-evolution rollback --drill` temporarily routes to the previous immutable release, verifies the front door, routes back to the promoted release, verifies again, and records `LIFECYCLE_ACCEPTED`. This proves rollback without leaving the machine on the older no-op-equivalent generation.

If the blue/green stack itself fails, `mcp-agent.service` remains the emergency original generation-0 fallback.

## First no-op drill

`candidate/release.json` defines `noop-lifecycle-001`. It intentionally changes no MCP capability or authority. Its sole purpose is to exercise:

`stage -> inactive validation -> activate -> fresh session -> accept -> promote -> rollback drill`

Only after that sequence reaches `LIFECYCLE_ACCEPTED` should the first iterative capability/superpower cycle begin.
