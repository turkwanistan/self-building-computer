# Generation 2 — Lab-native Code Mode

Status: **ACCEPTED**

## Scope
Generation 2 evolved `Optiplex_Lab + mcp-lab`, not `Optiplex_MCP`. The safe MCP stayed frozen at the accepted 51-tool identity.

## Starting gate
This ChatGPT session directly discovered the accepted 10-tool Generation-1 connector before any Lab shell use, then called `lab_status`. Gen-1 identity matched `gen1-self-hosted-lab-r2-f3bb6eb79d33` and SHA `f3bb6eb79d3370e7bf1d1ea15525b8e4ab496767454e6c1f5f05a9b3bd480b16`. Self-test was 12/12 and containment passed. A first fresh benchmark run transiently reported 16/17 on the private-network fixture; repeated exact probes were blocked and an unchanged rerun returned 17/17, so no Gen-2 work began until the clean baseline was re-established.

`docs/EVOLUTION_CONSTITUTION.md` was requested by the Generation-2 prompt but did not exist in the repository at generation start. No policy was invented from that absence; existing `START_HERE.md`, `STATUS.md`, authority/lifecycle docs, repository state, live identities, and the explicit Generation-2 boundaries were enforced.

## Designs compared
### A — Declarative JSON workflow runner (chosen)
A guest-local Python runner executes bounded typed steps and emits structured run/step audit records into the existing trace ledger. It supports exact-string edits, Git patches with preflight checks, commands with bounded retries, services, durable jobs, candidate self-update, compact previews, artifacts, and automatic rollback of reversible edits.

### B — Ad-hoc generated shell/Python scripts
This preserves maximum flexibility and can also collapse work into a single shell call, but Gen-1 evidence showed the downside: 16/36 calls were raw shell, failures were only visible at coarse command boundaries, and edit rollback/diff handling was procedure-specific. Generation 2 therefore kept arbitrary shell as an escape hatch but moved repeated engineering mechanics into a typed auditable runner.

## Accepted implementation
- Generation: `gen2-code-mode-r1`
- Build: `gen2-code-mode-r1-154492ee9972`
- Server SHA256: `154492ee997227a4bc61b733d4e1724bc7689ead22ebc0173fce51e97a5814b5`
- Code Mode SHA256: `2e0ea4e97541dcc48bbda3542be1e195d8fad2971931d1b7ae48cdb33202df77`
- Permanent MCP tools: **10 before / 10 after**; no tool was added.
- Connector refresh required: **no**, because the MCP schema did not change.

Code Mode lives at `/opt/optiplex-lab/code_mode.py`. Runs live under `/var/lib/optiplex-lab/code-runs/` and append sanitized `tool=code_mode` events to `/var/lib/optiplex-lab/traces/events.jsonl`.

## Self-hosting demonstration
Run `cm_20260826T043702Z_6e82b806` performed 7 steps: inspect live server → copy candidate → two deterministic edits → pycompile → isolated candidate startup smoke → guest-local self-update. The self-update scheduled the MCP restart after the originating request returned. Post-restart `lab_status` confirmed the new PID/run identity and accepted Gen-2 SHA.

A later durable benchmark job restarted the MCP and deliberately installed a syntactically valid fast-crashing source mutation. The launcher auto-restored the Gen-2 last-known-good SHA, the benchmark job survived the MCP restart, and self-test passed after recovery.

## Benchmarks
- Original benchmark regression: **17/17 PASS**, 7322.43 ms.
- Gen-2 orchestration extension: **12/12 PASS**, 15733.52 ms.
- Mechanical interactive-call proxy: **44 → 12**, a **72.7% reduction**.
- Gen-1 traced shell share: **44.4%** (16/36).
- Post-install Gen-2 outer shell share at finalization: **24%** (6/25), while 19 Code Mode runs represented 39 local steps.

Correctness and containment are acceptance gates; elapsed time is secondary.

## Deadlock rule
Never execute `/opt/optiplex-lab/mcp_probe.py` synchronously via `Optiplex_Lab.shell`. It recursively waits on the MCP server servicing the originating call. Prefer the connector schema, or use a detached/out-of-band probe.

## Generation 3
Do not implement automatically. The evidence-ranked top proposal is **Reusable workflow synthesis + skill compiler**: Code Mode reduces mechanical execution calls, but ChatGPT still authors separate workflow JSON for repeated procedures. See `lab_generations/GEN3_PROPOSALS.json`.
