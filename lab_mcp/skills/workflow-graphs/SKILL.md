# Composable Workflow Graphs + Lifecycle Transactions

Generation 4 adds `/opt/optiplex-lab/workflow_graphs.py` as a guest-local transaction/composition layer over Generation-3 reusable workflows. It adds **no MCP tools**.

Use it when a compound operation is already expressible as several accepted reusable workflows and ChatGPT should not manually sequence those calls.

```sh
/opt/optiplex-lab/workflow_graphs.py list
/opt/optiplex-lab/workflow_graphs.py show lab-upgrade-transaction@1
/opt/optiplex-lab/workflow_graphs.py preflight lab-upgrade-transaction@1 --params-file /root/params.json
/opt/optiplex-lab/workflow_graphs.py run lab-upgrade-transaction@1 --params-file /root/params.json
/opt/optiplex-lab/workflow_graphs.py resume wg_...
```

Rules:
- child reusable workflows must be referenced by immutable `name@version`;
- graph definitions never copy child workflow procedure definitions;
- parent parameters are typed with the same Gen-3 parameter types;
- use `$param`, `$path_join`, `$concat`, and bounded `$node` output references for mapping;
- preflight validates graph structure, child identity, and child parameters before execution when values are resolvable;
- dependency cycles, unknown children, missing parameters, excessive nodes/invocations/retries/timeouts, and graph nesting are rejected;
- default `run_if=success`; recovery nodes must explicitly use `run_if=failure` and `recovers=[...]` if they convert a recorded failure into `RECOVERED`;
- a failed child is never silently reported as ordinary parent success;
- `restart_boundary=true` persists a checkpoint, waits for `optiplex-lab-mcp.service` PID turnover and local port readiness, then continues;
- completed nodes are not rerun on resume; an ambiguous node left `RUNNING` fails closed rather than replaying a potentially destructive action;
- parent results retain child workflow version/hash, child Code Mode run/result paths, retries, changed files, restart checkpoints, and recovery provenance.

Canonical lifecycle composites:
- `lab-upgrade-transaction@1`: self-evolve → restart checkpoint → candidate verify → explicit accept → post-update verify.
- `lab-recovery-transaction@1`: deliberate bad candidate → LKG recovery/restart checkpoint → explicit re-accept → post-update verify.

For restart-sensitive composites, invoke the graph runner as a durable Lab `job`; the job is independent of the MCP service and survives the expected MCP restart.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through `Optiplex_Lab.shell`; recursive MCP self-calls can deadlock.
