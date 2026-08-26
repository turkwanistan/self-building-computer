# NEXT SESSION

The pre-looping lifecycle is fully accepted. Root state reached `LIFECYCLE_ACCEPTED` after no-op cycle `noop-lifecycle-001` was accepted, promoted, and passed the rollback drill.

Read first, in order:

1. `START_HERE.md`
2. `state/current.json`
3. `STATUS.md`
4. `docs/AUTHORITY_BOUNDARY.md`
5. `docs/BLUE_GREEN_LIFECYCLE.md`

Accepted baseline:

- stable: `frontend-a5c1c5be8b22` on green;
- previous: `frontend-baseline-91db2634c80d` on blue;
- guardrail: `guardrail-gen0-c51a9161a95d`;
- safe MCP: exactly 51 tools;
- schema: `195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913`;
- policy: `authority-v1`;
- rollback drill: PASS;
- lab connector: accepted 7-tool `Optiplex_Lab` with root/public internet confined to the isolated VM.

A future session may now begin the first real iterative capability/superpower cycle, but it must start from a concrete limitation or useful goal rather than inventing authority for its own sake.

For the first real cycle:

1. verify live root/release identity before modifying candidate source;
2. capture the original objective and limitation;
3. decide whether the change is ordinary capability evolution, `GUARDRAIL_GAP`, or `PERMISSION_REQUIRED`;
4. preserve the existing safe authority envelope unless the user explicitly approves a precise expansion;
5. use immutable candidate staging and the accepted activation/fresh-session/promotion/rollback lifecycle;
6. keep `Optiplex_Lab` as the broad experimentation zone when unrestricted guest execution materially helps;
7. record the evolution story and first real use.

Do not reconstruct mutable lifecycle state from ChatGPT memory. Root-owned state wins, then repository state, then live verification; memory is advisory only.
