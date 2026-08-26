# Generation 5 — Evidence-Gated Capability Forge

Status: **GUEST ACCEPTED; CANONICAL SYNC BLOCKED BY HOST REPOSITORY OWNERSHIP**

Generation 5 chose content-addressed guest-local capability capsules plus an evidence registry and a single generic Gen3 workflow/Gen4 graph adapter. This keeps creation/expiry cheap, makes promotion evidence-gated, and preserves the 10-tool MCP schema.

The Forge implements gap search, isolated workspaces, typed contracts, dependency environments, syntax/schema/negative/adversarial evaluation, real-task evidence, duplicate reuse, transparent promotion governance, expiration, supersession, and append-only provenance. It rejects forbidden host/private authority declarations and does not grant authority.

Benchmark: 12/12. Six useful passing capabilities were forged. Six deliberately bad descendants were rejected. Two useful capabilities were promoted, three remain candidates, one ephemeral helper was expired with provenance retained.

The semantic LibCST editor was the key self-host test. It reduced the actual source-edit authoring proxy from 1,862B exact text to 549B semantic intent (70.5%) and survived 5/5 formatting variants versus 1/5 for the exact text anchor. A failed self-edit produced no candidate. A successful semantic edit then fed the existing Gen4 `lab-upgrade-transaction@1`, which restarted, verified, explicitly accepted, and post-verified Gen5. Deliberate bad-candidate recovery also passed against the new LKG.

Accepted guest identity and all exact hashes/run IDs are in `lab_generations/GEN5_RESULT.json`. Gen6 proposals are evidence-derived in `lab_generations/GEN6_PROPOSALS.json`.

Canonical repository write was attempted only through frozen `Optiplex_MCP` and failed with EACCES because repository ownership no longer matches `mcp`; no authority was widened. The complete staged source/evidence bundle is `/root/gen5/canonical-sync`.
