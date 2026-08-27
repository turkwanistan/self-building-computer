#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import hashlib
import importlib.util
import json
import pathlib
import sys
from typing import Any

VERSION = "gen15-project-context-bridge-r1"
EPOCH = pathlib.Path("/opt/optiplex-lab/evidence_epoch.py")


def canonical(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(v: Any) -> str:
    return hashlib.sha256(v if isinstance(v, bytes) else canonical(v)).hexdigest()


def load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path}")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


def compose(task: str, project_packet_path: str) -> dict[str, Any]:
    pp = pathlib.Path(project_packet_path).resolve()
    if not pp.is_file():
        raise RuntimeError("project context packet missing")
    project = json.loads(pp.read_text(encoding="utf-8"))
    if project.get("schema") != "gen15.project-context.v1" or project.get("task") != task:
        raise RuntimeError("project context/task binding mismatch")
    packet_sha = sha({k: v for k, v in project.items() if k != "packet_sha256"})
    if packet_sha != project.get("packet_sha256"):
        raise RuntimeError("project context digest mismatch")
    ep = load(EPOCH, "gen15_epoch_bridge")
    begun = ep.begin_epoch(task=task, extra_paths=[str(pp)])
    epoch_id = begun["epoch_id"]
    compiled = ep.compile_minimized(epoch_id, task, budget_bytes=24000)
    verification = ep.verify_epoch(epoch_id)
    finalized = ep.finalize_epoch(epoch_id)
    if not compiled.get("ok") or compiled.get("fail_closed") or not verification.get("ok") or not finalized.get("ok"):
        raise RuntimeError("Gen8-Gen11 epoch composition failed closed")
    route = compiled.get("routing_proof") or {}
    minimized = compiled.get("minimized_packet") or {}
    budget = minimized.get("budget") or {}
    # Gen15 domain routing is more specialized; Gen11 remains authoritative for action/authority class.
    material = {
        "version": VERSION,
        "task": task,
        "project_context_path": str(pp),
        "project_packet_sha256": project["packet_sha256"],
        "project_manifest_sha256": project["project_manifest_sha256"],
        "project_evidence_epoch": project["evidence_epoch"],
        "gen10_epoch_id": epoch_id,
        "gen10_epoch_digest": begun["epoch_digest"],
        "gen10_transaction_digest": compiled["transaction_digest"],
        "gen11_routing_digest": compiled["routing_digest"],
        "gen11_primary_intent": route.get("detected_primary_intent"),
        "gen11_required_authority_classes": route.get("required_authority_classes") or [],
        "gen8_compiler_packet_digest": (compiled.get("compiler_packet") or {}).get("packet_digest"),
        "gen9_optimizer_packet_digest": minimized.get("packet_digest"),
        "gen9_context_payload_bytes": budget.get("context_payload_bytes"),
        "gen9_context_payload_reduction": budget.get("context_payload_reduction"),
        "domain_required_evidence_recall": (project.get("metrics") or {}).get("required_evidence_recall"),
        "domain_context_reduction": (project.get("metrics") or {}).get("context_reduction"),
        "domain_selected_bytes": (project.get("metrics") or {}).get("selected_bytes"),
        "domain_route": project.get("route"),
        "epoch_verification_ok": verification.get("ok"),
        "epoch_finalized_state": finalized.get("state"),
        "fail_closed": False,
    }
    material["composition_sha256"] = sha(material)
    return material


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: project_context_bridge.py TASK PROJECT_CONTEXT_JSON", file=sys.stderr); return 2
    try:
        out = compose(sys.argv[1], sys.argv[2])
    except Exception as exc:
        print(json.dumps({"version": VERSION, "ok": False, "fail_closed": True, "error": str(exc)}, sort_keys=True)); return 2
    print(json.dumps({"ok": True, **out}, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
