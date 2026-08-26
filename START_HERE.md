# Self-Building Computer — Start Here

This repository is the ChatGPT-writable control/source area for the evolvable MCP and the disposable `mcp-lab` guest MCP.

## Fresh sessions

1. Read `NEXT_SESSION.md`.
2. Read `state/current.json`.
3. Read `STATUS.md`.
4. Read `docs/CHATGPT_MEMORY_AND_HANDOFF.md` and obey its source-of-truth order.
5. Treat root-owned `/var/lib/mcp-evolution/current.json` as authoritative once bootstrap installs it.
6. Verify live conditions needed for the next action; do not treat ChatGPT memory or an old chat as current machine state.
7. Read `history/events.jsonl` or older planning material only when needed.

## Hard boundaries

- Never modify active/stable production code in place.
- Never widen safe/production authority without explicit user approval.
- Never place host/tunnel/Git credentials inside the unrestricted guest.
- ChatGPT memory is advisory continuity only; repository/root-owned state is authoritative.

The safe front-end begins as a low-privilege proxy to generation-0 `Optiplex_MCP`. The existing backend temporarily serves as the protected guardrail broker while the boundary is extracted incrementally. The lab MCP is intentionally broad, but only inside the isolated VM.

## Before a refresh or handoff

Update `state/current.json`, `STATUS.md`, and `NEXT_SESSION.md`; append a concise lifecycle event when state materially changes; run relevant checks. A fresh session must be able to resume from repository/root-owned state alone.
