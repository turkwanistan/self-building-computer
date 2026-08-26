# Reusable Workflow Skills

Generation 3 adds a guest-local registry/compiler at `/opt/optiplex-lab/workflow_skills.py` without adding MCP tools.

Use compact named invocations instead of regenerating full Code Mode workflow JSON:

```sh
/opt/optiplex-lab/workflow_skills.py list
/opt/optiplex-lab/workflow_skills.py show exact-replace
/opt/optiplex-lab/workflow_skills.py run exact-replace --params-json '{"path":"/tmp/x","old":"a","new":"b"}'
```

Definitions are immutable by `name@version` and stored under `/var/lib/optiplex-lab/workflows/`; `CURRENT` selects the active version. Each definition has a human description, typed parameter schema, workflow template, version, and SHA256 identity.

Parameter rules:
- supported types: `str`, `path`, `int`, `float`, `bool`, `enum`, `list[str]`;
- validate required/default/min/max/pattern/absolute-path constraints before execution;
- prefer structured `{"$param":"name"}`, `{"$path_join":[...]}`, and `{"$concat":[...]}` nodes;
- prefer Code Mode `argv` for parameterized commands so values remain literal process arguments instead of shell-interpolated text;
- sensitive parameters are represented in traces/results only by type/hash/size.

Promotion:
- only successful Code Mode runs may be promoted;
- `promote` parameterizes exact scalar values and records the source run/result/workflow hash as provenance;
- the compiled concrete workflow is retained for audit and the underlying Code Mode trace still exposes every actual step, retry, diff, artifact, rollback, and result.

Lab lifecycle recipes:
1. `lab-self-evolve` installs a candidate and schedules restart;
2. `lab-candidate-verify` verifies the candidate while the previous LKG remains available;
3. `lab-accept-current` promotes a verified candidate/recovered live build to LKG and marks it accepted;
4. `lab-post-update-verify` verifies accepted state and containment;
5. `lab-bad-candidate-recovery` exercises automatic rollback.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through `Optiplex_Lab.shell`; recursive MCP self-calls can deadlock.
