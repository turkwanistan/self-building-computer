# Evidence-Gated Capability Forge

Generation 5 adds `/opt/optiplex-lab/capability_forge.py` as a guest-local capability acquisition and retention layer. It adds **no permanent MCP tools**.

Use it when the Lab encounters a missing guest-local ability that should be created, evaluated, used, and retained or discarded by evidence rather than immediately added to the MCP API.

Acquisition loop:

1. `gap` searches active capability records before creation.
2. If no equivalent is found, it creates an isolated workspace under `/var/lib/optiplex-lab/capabilities/workspaces/`.
3. Put `capability.json` plus implementation files in that workspace.
4. `seal` validates the capability contract and creates an immutable content-addressed object.
5. `evaluate` performs syntax checks, dependency setup, positive/negative/adversarial contract cases, output-schema validation, output/timeout bounds, and containment probes.
6. `invoke --real-task` records actual task evidence.
7. `govern` applies transparent hard gates and evidence dimensions. Promotion requires repeated successful real use; creation alone cannot promote.
8. `expire` removes weak ephemeral runtime artifacts while retaining registry hashes and append-only provenance.

Contract essentials:
- `schema_version=capability-contract-v1`;
- semantic `name`/`version`, purpose, applicability tags;
- JSON-Schema typed input/output;
- relative or Python entrypoint;
- bounded pip dependencies;
- declared side effects from `read_files`, `write_workspace`, `public_network`, `service`, `subprocess`;
- evaluation cases and provenance;
- initial lifecycle `EPHEMERAL` or `CANDIDATE` plus TTL.

Forbidden host/private authority is rejected by the contract validator and remains unavailable at runtime because generated code receives only ordinary guest authority inside the isolated VM.

Gen3/Gen4 integration:
- reusable workflow `capability-invoke@1` invokes any content hash through the Forge;
- graph `capability-use-transaction@1` proves workflow-graph composition can call forged capabilities without schema expansion.

Never run `/opt/optiplex-lab/mcp_probe.py` synchronously through `Optiplex_Lab.shell`.
