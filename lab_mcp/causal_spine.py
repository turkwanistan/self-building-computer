#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

VERSION = "gen7-causal-spine-r1"
DEFAULT_OUT = pathlib.Path("/var/lib/optiplex-lab/twin/causal-index.json")
DEFAULT_SOURCES = (
    pathlib.Path("/var/lib/optiplex-lab/traces/events.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/capabilities/provenance.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/memory/provenance.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/regressions/provenance.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/recovery/launcher-events.jsonl"),
)
BUILD_FILE = pathlib.Path("/etc/optiplex-lab/build.json")

# Raw task payloads, tool arguments, parameters, stdout/stderr, and context text are
# deliberately absent. Hashes/IDs and bounded structural metadata are sufficient for
# Gen7's causal joins without turning observability into a secret-copying mechanism.
SAFE_SCALARS = {
    "timestamp", "tool", "event", "run_id", "code_run_id", "content_hash",
    "context_hash", "memory_hash", "regression_hash", "workflow_sha256", "sha256",
    "source_sha256", "bad_sha256", "restored_sha256", "known_bad_hash",
    "known_good_hash", "episode_hash", "episode_id", "procedure_fingerprint",
    "task_hash", "selected", "source", "source_case", "selector_name", "name",
    "version", "forge_version", "compiler_version", "runner_version", "generation",
    "build_id", "state", "status", "phase", "node_id", "step_id", "step_index",
    "op", "ok", "tool_success", "success", "exit_code", "pid", "duration_ms",
    "known_bad_detected", "known_good_passed", "real_task", "recovery_state",
    "last_known_good_sha256", "recovered_at", "accepted_at", "installed_at",
}
SAFE_COMPOSITES = {"child_workflow", "recovered_failures"}
HASH_KEYS = {
    "content_hash", "context_hash", "memory_hash", "regression_hash", "workflow_sha256",
    "sha256", "source_sha256", "bad_sha256", "restored_sha256", "known_bad_hash",
    "known_good_hash", "episode_hash", "procedure_fingerprint", "task_hash",
    "last_known_good_sha256",
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_write_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=str(path.parent), delete=False, encoding="utf-8") as f:
        f.write(payload)
        tmp = pathlib.Path(f.name)
    tmp.replace(path)


def _safe_composite(key: str, value: Any) -> Any:
    if key == "child_workflow" and isinstance(value, dict):
        return {k: value[k] for k in ("name", "version", "sha256", "compiler_version") if k in value}
    if key == "recovered_failures" and isinstance(value, dict):
        return {str(k)[:120]: str(v)[:120] for k, v in sorted(value.items())}
    return None


def sanitize(rec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted(rec):
        if key in SAFE_SCALARS:
            value = rec[key]
            if value is None or isinstance(value, (bool, int, float)):
                out[key] = value
            elif isinstance(value, str):
                out[key] = value[:512]
        elif key in SAFE_COMPOSITES:
            value = _safe_composite(key, rec[key])
            if value is not None:
                out[key] = value
    return out


def _iter_jsonl(path: pathlib.Path) -> Iterable[tuple[int, str, dict[str, Any]]]:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line_no, raw in enumerate(f, 1):
            raw = raw.rstrip("\n")
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield line_no, raw, rec


def normalize_event(path: pathlib.Path, line_no: int, raw: str, rec: dict[str, Any]) -> dict[str, Any]:
    data = sanitize(rec)
    line_sha = sha_bytes(raw.encode())
    event_id = "ev:" + sha_bytes(f"{path}:{line_no}:{line_sha}".encode())[:24]
    return {
        "id": event_id,
        "source_path": str(path),
        "source_line": line_no,
        "evidence_line_sha256": line_sha,
        "timestamp": str(data.get("timestamp") or ""),
        "data": data,
    }


def _build_state_event() -> dict[str, Any] | None:
    if not BUILD_FILE.is_file():
        return None
    raw = BUILD_FILE.read_text(encoding="utf-8", errors="replace")
    try:
        rec = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(rec, dict):
        return None
    data = sanitize({"tool": "build_state", "event": "accepted_build_state", **rec})
    line_sha = sha_bytes(raw.encode())
    return {
        "id": "ev:" + sha_bytes(f"{BUILD_FILE}:{line_sha}".encode())[:24],
        "source_path": str(BUILD_FILE),
        "source_line": 1,
        "evidence_line_sha256": line_sha,
        "timestamp": str(data.get("accepted_at") or data.get("installed_at") or ""),
        "data": data,
    }


def collect_events(sources: Iterable[pathlib.Path] = DEFAULT_SOURCES) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sources:
        for line_no, raw, rec in _iter_jsonl(path) or ():
            events.append(normalize_event(path, line_no, raw, rec))
    build = _build_state_event()
    if build:
        events.append(build)
    events.sort(key=lambda e: (e.get("timestamp") or "", e["source_path"], e["source_line"], e["id"]))
    return events


def _edge(src: dict[str, Any], dst: dict[str, Any], relation: str, strength: str,
          confidence: float, evidence: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    core = {
        "src": src["id"], "dst": dst["id"], "relation": relation,
        "strength": strength, "confidence": round(float(confidence), 3),
        "evidence": evidence, "details": details or {},
    }
    return {"id": "ce:" + sha_bytes(canonical(core))[:24], **core}


def _event_name(e: dict[str, Any]) -> str:
    return str(e.get("data", {}).get("event") or "")


def _run_id(e: dict[str, Any]) -> str | None:
    value = e.get("data", {}).get("run_id")
    return str(value) if value else None


def derive_edges(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edges: dict[str, dict[str, Any]] = {}
    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_code_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_content: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_bad_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for e in events:
        d = e["data"]
        if rid := _run_id(e):
            by_run[rid].append(e)
        if cr := d.get("code_run_id"):
            by_code_run[str(cr)].append(e)
        if h := d.get("content_hash"):
            by_content[str(h)].append(e)
        if h := d.get("known_bad_hash"):
            by_bad_hash[str(h)].append(e)

    def add(edge: dict[str, Any]) -> None:
        if edge["src"] != edge["dst"]:
            edges[edge["id"]] = edge

    start_names = {"graph_run_start", "run_start"}
    end_names = {"graph_run_end", "run_end"}
    for rid, group in by_run.items():
        ordered = sorted(group, key=lambda e: (e.get("timestamp") or "", e["source_line"]))
        starts = [e for e in ordered if _event_name(e) in start_names]
        ends = [e for e in ordered if _event_name(e) in end_names]
        if starts:
            root = starts[0]
            for child in ordered:
                if child is not root:
                    add(_edge(root, child, "contains_run_event", "lineage", 1.0,
                              "explicit shared run_id", {"run_id": rid}))
        if starts and ends:
            add(_edge(starts[0], ends[-1], "run_completed_by", "causal", 1.0,
                      "explicit shared run_id and start/end event types", {"run_id": rid}))

        node_starts: dict[str, list[dict[str, Any]]] = defaultdict(list)
        node_ends: dict[str, list[dict[str, Any]]] = defaultdict(list)
        step_starts: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
        step_ends: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
        for e in ordered:
            d = e["data"]
            if _event_name(e) == "node_start" and d.get("node_id") is not None:
                node_starts[str(d["node_id"])].append(e)
            elif _event_name(e) == "node_end" and d.get("node_id") is not None:
                node_ends[str(d["node_id"])].append(e)
            elif _event_name(e) == "step_start":
                step_starts[(str(d.get("step_id")), d.get("step_index"))].append(e)
            elif _event_name(e) == "step_end":
                step_ends[(str(d.get("step_id")), d.get("step_index"))].append(e)
        for nid in sorted(set(node_starts) & set(node_ends)):
            for s, t in zip(node_starts[nid], node_ends[nid]):
                add(_edge(s, t, "node_completed_by", "causal", 1.0,
                          "explicit run_id + node_id pair", {"run_id": rid, "node_id": nid}))
        for sid in sorted(set(step_starts) & set(step_ends), key=str):
            for s, t in zip(step_starts[sid], step_ends[sid]):
                add(_edge(s, t, "step_completed_by", "causal", 1.0,
                          "explicit run_id + step identity pair", {"run_id": rid, "step": list(sid)}))

        invokes = [e for e in ordered if _event_name(e) == "invoke"]
        real = [e for e in ordered if _event_name(e) == "real_task_evidence"]
        for r in real:
            prior = [e for e in invokes if (e.get("timestamp") or "") <= (r.get("timestamp") or "")]
            if prior:
                add(_edge(prior[-1], r, "produced_real_task_evidence", "causal", 1.0,
                          "explicit capability run_id", {"run_id": rid}))

    for code_run_id, callers in by_code_run.items():
        child_group = by_run.get(code_run_id, [])
        child_starts = [e for e in child_group if _event_name(e) == "run_start" and e["data"].get("tool") == "code_mode"]
        if not child_starts:
            continue
        child = sorted(child_starts, key=lambda e: e.get("timestamp") or "")[0]
        for caller in callers:
            add(_edge(caller, child, "invokes_code_run", "causal", 1.0,
                      "explicit code_run_id", {"code_run_id": code_run_id}))

    for bad_hash, compiled_events in by_bad_hash.items():
        failures = [e for e in by_content.get(bad_hash, [])
                    if e["data"].get("ok") is False or e["data"].get("tool_success") is False]
        for comp in compiled_events:
            prior = [e for e in failures if not comp.get("timestamp") or (e.get("timestamp") or "") <= comp["timestamp"]]
            if prior:
                src = sorted(prior, key=lambda e: e.get("timestamp") or "")[-1]
                add(_edge(src, comp, "generated_regression", "causal", 1.0,
                          "regression provenance explicitly names known_bad_hash",
                          {"known_bad_hash": bad_hash, "regression_hash": comp["data"].get("regression_hash")}))

    launcher = [e for e in events if e["source_path"].endswith("launcher-events.jsonl")]
    for i, e in enumerate(launcher):
        d = e["data"]
        if d.get("event") != "auto_rollback":
            continue
        bad, restored = d.get("bad_sha256"), d.get("restored_sha256")
        prevs = [x for x in launcher[:i] if x["data"].get("event") == "child_exited" and x["data"].get("source_sha256") == bad]
        nexts = [x for x in launcher[i + 1:] if x["data"].get("event") == "child_started" and x["data"].get("source_sha256") == restored]
        if prevs:
            add(_edge(prevs[-1], e, "triggered_auto_rollback", "causal", 1.0,
                      "bad_sha256 matches exited child source_sha256", {"bad_sha256": bad}))
        if nexts:
            add(_edge(e, nexts[0], "restored_child_started", "causal", 1.0,
                      "restored_sha256 matches subsequent child source_sha256", {"restored_sha256": restored}))

    return sorted(edges.values(), key=lambda e: (e["src"], e["dst"], e["relation"], e["id"]))


def source_manifest(sources: Iterable[pathlib.Path] = DEFAULT_SOURCES) -> list[dict[str, Any]]:
    out = []
    for path in [*sources, BUILD_FILE]:
        if path.is_file():
            data = path.read_bytes()
            out.append({"path": str(path), "bytes": len(data), "sha256_at_ingest": sha_bytes(data)})
        else:
            out.append({"path": str(path), "missing": True})
    return out


def build_index(sources: Iterable[pathlib.Path] = DEFAULT_SOURCES) -> dict[str, Any]:
    sources = tuple(sources)
    events = collect_events(sources)
    edges = derive_edges(events)
    structural = {
        "schema_version": 1,
        "version": VERSION,
        "sources": source_manifest(sources),
        "events": events,
        "edges": edges,
    }
    digest = sha_bytes(canonical(structural))
    return {"generated_at": utc(), "digest": digest, **structural}


def write_index(path: pathlib.Path = DEFAULT_OUT, sources: Iterable[pathlib.Path] = DEFAULT_SOURCES) -> dict[str, Any]:
    result = build_index(sources)
    safe_write_json(path, result)
    return result


def reconstruct(index: dict[str, Any], needle: str, max_depth: int = 4) -> dict[str, Any]:
    events = {e["id"]: e for e in index.get("events", [])}
    edges = index.get("edges", [])
    needle_l = needle.lower()
    seeds = []
    for e in events.values():
        hay = json.dumps(e.get("data", {}), sort_keys=True).lower()
        if needle_l == e["id"].lower() or needle_l in hay:
            seeds.append(e["id"])
    out_adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    in_adj: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        out_adj[edge["src"]].append(edge)
        in_adj[edge["dst"]].append(edge)
    seen = set(seeds)
    frontier = set(seeds)
    selected_edges: dict[str, dict[str, Any]] = {}
    for _ in range(max(0, max_depth)):
        nxt: set[str] = set()
        for eid in frontier:
            for edge in [*out_adj.get(eid, []), *in_adj.get(eid, [])]:
                selected_edges[edge["id"]] = edge
                other = edge["dst"] if edge["src"] == eid else edge["src"]
                if other not in seen:
                    seen.add(other); nxt.add(other)
        frontier = nxt
        if not frontier:
            break
    selected_events = [events[eid] for eid in seen if eid in events]
    selected_events.sort(key=lambda e: (e.get("timestamp") or "", e["source_path"], e["source_line"]))
    return {
        "needle": needle,
        "seed_count": len(seeds),
        "event_count": len(selected_events),
        "edge_count": len(selected_edges),
        "events": selected_events,
        "edges": sorted(selected_edges.values(), key=lambda e: (e["src"], e["dst"], e["relation"])),
        "uncertainty": [] if seeds else ["No raw evidence event matched the requested identifier/hash."],
    }


def summary(index: dict[str, Any]) -> dict[str, Any]:
    strengths: dict[str, int] = defaultdict(int)
    relations: dict[str, int] = defaultdict(int)
    for e in index.get("edges", []):
        strengths[e.get("strength", "unknown")] += 1
        relations[e.get("relation", "unknown")] += 1
    return {
        "version": index.get("version"), "digest": index.get("digest"),
        "events": len(index.get("events", [])), "edges": len(index.get("edges", [])),
        "strengths": dict(sorted(strengths.items())), "relations": dict(sorted(relations.items())),
        "sources": index.get("sources", []),
    }


def selftest() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def ck(name: str, ok: Any, detail: Any = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
    with tempfile.TemporaryDirectory(prefix="causal-spine-selftest-") as td:
        root = pathlib.Path(td)
        trace = root / "events.jsonl"
        rows = [
            {"timestamp":"2026-01-01T00:00:00+00:00","tool":"workflow_graphs","event":"graph_run_start","run_id":"wg_x","name":"g"},
            {"timestamp":"2026-01-01T00:00:01+00:00","tool":"workflow_graphs","event":"node_end","run_id":"wg_x","node_id":"n","code_run_id":"cm_x","ok":True},
            {"timestamp":"2026-01-01T00:00:01.1+00:00","tool":"code_mode","event":"run_start","run_id":"cm_x","name":"w"},
            {"timestamp":"2026-01-01T00:00:02+00:00","tool":"code_mode","event":"run_end","run_id":"cm_x","ok":True},
            {"timestamp":"2026-01-01T00:00:03+00:00","tool":"capability_forge","event":"invoke","run_id":"cap_x","content_hash":"a"*64,"ok":False},
        ]
        trace.write_text("".join(json.dumps(x)+"\n" for x in rows))
        reg = root / "reg.jsonl"
        reg.write_text(json.dumps({"timestamp":"2026-01-01T00:00:04+00:00","event":"compiled","regression_hash":"b"*64,"known_bad_hash":"a"*64})+"\n")
        idx = build_index((trace, reg))
        rels = {(e["relation"], e["strength"]) for e in idx["edges"]}
        ck("explicit_code_run_join", ("invokes_code_run","causal") in rels)
        ck("explicit_failure_regression_join", ("generated_regression","causal") in rels)
        rec = reconstruct(idx, "b"*64)
        ck("regression_reconstructs_failure", any(e["data"].get("content_hash") == "a"*64 for e in rec["events"]), rec.get("event_count"))
        ck("raw_parameters_not_indexed", all("parameters" not in e["data"] and "args" not in e["data"] for e in idx["events"]))
        idx2 = build_index((trace, reg))
        ck("deterministic_digest", idx["digest"] == idx2["digest"])
    return {"version": VERSION, "passed": sum(c["ok"] for c in checks), "total": len(checks), "checks": checks}


def main() -> None:
    ap = argparse.ArgumentParser(description="Gen7 derived causal observability index")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("build"); p.add_argument("--out", default=str(DEFAULT_OUT))
    p = sub.add_parser("summary"); p.add_argument("--index", default=str(DEFAULT_OUT))
    p = sub.add_parser("reconstruct"); p.add_argument("needle"); p.add_argument("--index", default=str(DEFAULT_OUT)); p.add_argument("--depth", type=int, default=4)
    args = ap.parse_args()
    if args.selftest:
        out = selftest()
        print(json.dumps(out, indent=2, sort_keys=True))
        raise SystemExit(0 if out["passed"] == out["total"] else 1)
    if args.cmd == "build":
        out = write_index(pathlib.Path(args.out)); print(json.dumps(summary(out), indent=2, sort_keys=True)); return
    if args.cmd in {"summary", "reconstruct"}:
        path = pathlib.Path(args.index)
        if not path.is_file():
            raise SystemExit(f"index not found: {path}")
        idx = json.loads(path.read_text())
        out = summary(idx) if args.cmd == "summary" else reconstruct(idx, args.needle, args.depth)
        print(json.dumps(out, indent=2, sort_keys=True)); return
    ap.print_help()


if __name__ == "__main__":
    main()
