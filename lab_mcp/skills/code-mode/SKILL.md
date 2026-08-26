# Lab-native Code Mode

Use `/opt/optiplex-lab/code_mode.py WORKFLOW.json` for bounded auditable guest-local engineering workflows. Generation 3 keeps the Generation-2 execution model and adds literal `argv` execution plus reusable-workflow provenance.

Workflow shape: JSON with `name`, optional `cwd`, `rollback_on_failure`, `stop_on_failure`, and `steps`.

Supported step ops: `inspect`, `copy`, `exact_replace`, `git_patch`, `command`, `assert_file`, `service`, `job`, `self_update`.

Rules:
- Prefer `exact_replace` when context must match exactly; mismatch fails deterministically.
- Prefer `git_patch` in Git worktrees; it runs `git apply --check` before apply.
- Prefer `argv` instead of shell `command` when inserting reusable-workflow parameters into commands; argv values are passed literally without shell interpolation.
- Use explicit `retries` only for predictable transient command failures; retries are bounded to 5.
- Large stdout/stderr stays under `/var/lib/optiplex-lab/code-runs/<run>/`; the MCP return is compact.
- Runs append `tool=code_mode` step/run events into the trace ledger.
- Compiled reusable workflows record workflow name/version/hash and safely represented parameters while retaining the concrete compiled workflow.
- On failure, reversible file/patch edits roll back automatically unless disabled.
- `self_update` must be the final step because it schedules an MCP restart after the workflow returns.
- Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through the Lab MCP; recursive self-calls deadlock.

Run `/opt/optiplex-lab/code_mode.py --selftest` after changing the runner.
