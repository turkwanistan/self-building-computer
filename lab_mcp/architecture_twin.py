#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import tempfile
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Iterable

VERSION = "gen7-architectural-twin-r1"
SCHEMA_VERSION = 1
DEFAULT_SOURCE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_TWIN_SOURCE_ROOT", "/opt/optiplex-lab"))
DEFAULT_STATE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_TWIN_STATE_ROOT", "/var/lib/optiplex-lab"))
DEFAULT_BUILD_FILE = pathlib.Path(os.environ.get("OPTIPLEX_TWIN_BUILD_FILE", "/etc/optiplex-lab/build.json"))
DEFAULT_RECOVERY_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_TWIN_RECOVERY_ROOT", "/var/lib/optiplex-lab/recovery"))
DEFAULT_TWIN_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_TWIN_ROOT", "/var/lib/optiplex-lab/twin"))

INTRODUCED = {
    "server.py": "gen1-self-hosted-lab-r2",
    "code_mode.py": "gen2-code-mode-r1",
    "workflow_skills.py": "gen3-workflow-skills-r1",
    "workflow_graphs.py": "gen4-workflow-graphs-r1",
    "capability_forge.py": "gen5-capability-forge-r1",
    "experience_memory.py": "gen6-experience-memory-r1",
    "regression_compiler.py": "gen6-experience-memory-r1",
    "experience_loop.py": "gen6-experience-memory-r1",
    "architecture_twin.py": "gen7-self-model-r1",
    "causal_spine.py": "gen7-self-model-r1",
}

IMPACT_REVERSE = {
    "imports", "depends_on", "invokes", "consumes", "validates", "gates",
    "generated_from", "recovers_to", "protected_by",
}
IMPACT_FORWARD = {"authoritative_for", "supersedes"}
STRONG_EVIDENCE = {"observed_static", "observed_definition", "observed_registry", "observed_runtime", "history_seed", "policy_seed"}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_path(path: pathlib.Path) -> str | None:
    return sha_bytes(path.read_bytes()) if path.is_file() else None


def safe_json(path: pathlib.Path) -> dict[str, Any] | list[Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, (dict, list)) else None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=str(path.parent), delete=False, encoding="utf-8") as f:
        f.write(payload); tmp = pathlib.Path(f.name)
    tmp.replace(path)


def nid(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _compact_meta(value: Any, depth: int = 0) -> Any:
    if depth > 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, list):
        return [_compact_meta(x, depth + 1) for x in value[:50]]
    if isinstance(value, dict):
        return {str(k)[:120]: _compact_meta(v, depth + 1) for k, v in sorted(value.items())[:80]}
    return str(value)[:1000]


class TwinBuilder:
    def __init__(self, source_root: pathlib.Path, state_root: pathlib.Path,
                 build_file: pathlib.Path, recovery_root: pathlib.Path):
        self.source_root = source_root
        self.state_root = state_root
        self.build_file = build_file
        self.recovery_root = recovery_root
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.source_nodes: dict[pathlib.Path, str] = {}
        self.module_nodes: dict[str, str] = {}
        self.capabilities_by_name: dict[str, list[str]] = defaultdict(list)
        self.inputs: dict[str, dict[str, Any]] = {}

    def add_node(self, kind: str, key: str, *, name: str | None = None, identity: str | None = None,
                 source_path: pathlib.Path | str | None = None, source_sha256: str | None = None,
                 source_bytes: int | None = None, freshness_mode: str = "hash",
                 authoritative: bool = False, generation: str | None = None,
                 metadata: dict[str, Any] | None = None) -> str:
        node_id = nid(kind, key)
        path_text = str(source_path) if source_path is not None else None
        record = {
            "id": node_id, "kind": kind, "name": name or key, "identity": identity or key,
            "source_path": path_text, "source_sha256": source_sha256,
            "source_bytes": source_bytes, "freshness_mode": freshness_mode,
            "authoritative": bool(authoritative), "generation": generation,
            "metadata": _compact_meta(metadata or {}),
        }
        old = self.nodes.get(node_id)
        if old:
            merged = dict(old)
            for k, v in record.items():
                if v not in (None, {}, ""):
                    merged[k] = v
            record = merged
        self.nodes[node_id] = record
        if path_text and source_sha256:
            self.inputs[path_text] = {
                "path": path_text, "sha256": source_sha256, "bytes": source_bytes,
                "freshness_mode": freshness_mode,
            }
        return node_id

    def add_file_node(self, path: pathlib.Path, *, kind: str = "source", key: str | None = None,
                      name: str | None = None, authoritative: bool = True,
                      freshness_mode: str = "hash", generation: str | None = None,
                      metadata: dict[str, Any] | None = None) -> str:
        data = path.read_bytes() if path.is_file() else b""
        node = self.add_node(
            kind, key or str(path), name=name or path.name, identity=str(path), source_path=path,
            source_sha256=sha_bytes(data) if path.is_file() else None,
            source_bytes=len(data) if path.is_file() else None,
            freshness_mode=freshness_mode, authoritative=authoritative,
            generation=generation, metadata=metadata,
        )
        if kind == "source":
            self.source_nodes[path] = node
        return node

    def add_edge(self, src: str, dst: str, relation: str, *, evidence_kind: str,
                 confidence: float, source_path: pathlib.Path | str | None = None,
                 source_sha256: str | None = None, details: dict[str, Any] | None = None) -> str:
        if src == dst:
            return ""
        core = {
            "src": src, "dst": dst, "relation": relation, "evidence_kind": evidence_kind,
            "confidence": round(float(confidence), 3), "source_path": str(source_path) if source_path else None,
            "source_sha256": source_sha256, "details": _compact_meta(details or {}),
        }
        edge_id = "edge:" + sha_bytes(canonical(core))[:24]
        self.edges[edge_id] = {"id": edge_id, **core}
        return edge_id

    def _python_paths(self) -> list[pathlib.Path]:
        out: list[pathlib.Path] = []
        if not self.source_root.is_dir():
            return out
        for path in self.source_root.rglob("*.py"):
            rel = path.relative_to(self.source_root)
            text = str(rel)
            if any(part in {"venv", "__pycache__"} for part in rel.parts):
                continue
            if ".candidate" in path.name or path.name.startswith("server.gen"):
                continue
            if len(rel.parts) > 2:
                continue
            out.append(path)
        return sorted(out)

    @staticmethod
    def _decorator_is_tool(node: ast.AST) -> bool:
        target = node.func if isinstance(node, ast.Call) else node
        return isinstance(target, ast.Attribute) and target.attr == "tool"

    @staticmethod
    def _imports(tree: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        return names

    @staticmethod
    def _strings(tree: ast.AST) -> set[str]:
        return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}

    def add_sources(self) -> None:
        trees: dict[pathlib.Path, ast.AST] = {}
        for path in self._python_paths():
            generation = INTRODUCED.get(path.name)
            role = "benchmark" if "bench" in path.parts else "module"
            node = self.add_file_node(path, generation=generation, metadata={"role": role})
            self.module_nodes[path.stem] = node
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
                trees[path] = tree
            except (SyntaxError, UnicodeDecodeError):
                continue
            if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "selftest" for n in tree.body):
                validation = self.add_node("validation", f"selftest:{path.stem}", name=f"{path.stem} --selftest",
                                           identity=f"{path} --selftest", generation=generation,
                                           metadata={"command": f"{path} --selftest"})
                self.add_edge(validation, node, "validates", evidence_kind="observed_static", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[node]["source_sha256"])
            if path.name == "selftest.py":
                validation = self.add_node("validation", "lab-selftest", name="Lab selftest", identity=str(path),
                                           generation="gen1-self-hosted-lab-r2", metadata={"command": str(path)})
                self.add_edge(validation, node, "invokes", evidence_kind="observed_static", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[node]["source_sha256"])
            if role == "benchmark":
                validation = self.add_node("validation", f"benchmark:{path.stem}", name=path.stem,
                                           identity=str(path), generation=generation,
                                           metadata={"command": str(path)})
                self.add_edge(validation, node, "invokes", evidence_kind="observed_static", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[node]["source_sha256"])

        for path, tree in trees.items():
            src = self.source_nodes[path]
            src_sha = self.nodes[src]["source_sha256"]
            role = "benchmark" if "bench" in path.parts else "module"
            for module in sorted(self._imports(tree)):
                dst = self.module_nodes.get(module)
                if dst and dst != src:
                    self.add_edge(src, dst, "imports", evidence_kind="observed_static", confidence=1.0,
                                  source_path=path, source_sha256=src_sha, details={"module": module})
            if path.name == "server.py":
                for node in tree.body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(self._decorator_is_tool(d) for d in node.decorator_list):
                        tool = self.add_node("mcp_tool", node.name, name=node.name, identity=node.name,
                                             generation="gen1-self-hosted-lab-r2", metadata={"permanent_surface": True})
                        self.add_edge(src, tool, "authoritative_for", evidence_kind="observed_static", confidence=1.0,
                                      source_path=path, source_sha256=src_sha)

            # Absolute source/runtime references are inspectable references, not assumed
            # behavioral dependencies. Benchmarks and workflow adapters are the exception:
            # their execution explicitly consumes the referenced executable/module.
            for text in sorted(self._strings(tree)):
                if not text.startswith("/"):
                    continue
                candidate = pathlib.Path(text)
                dst = self.source_nodes.get(candidate)
                if dst:
                    rel = "depends_on" if "bench" in path.parts else "references"
                    evidence = "observed_static"
                    self.add_edge(src, dst, rel, evidence_kind=evidence, confidence=1.0,
                                  source_path=path, source_sha256=src_sha, details={"literal_path": text})

            # Benchmarks commonly construct executable/module paths from a source-root
            # variable plus a filename (for example STAGE / "experience_loop.py").
            # A filename literal is therefore an explicit benchmark dependency when it
            # uniquely names one installed Lab source module. This is still static
            # observed evidence, not a semantic guess.
            if role == "benchmark":
                string_literals = self._strings(tree)
                by_name: dict[str, list[str]] = defaultdict(list)
                for source_path, source_id in self.source_nodes.items():
                    by_name[source_path.name].append(source_id)
                for text in sorted(string_literals):
                    matches = by_name.get(text, [])
                    if len(matches) == 1 and matches[0] != src:
                        self.add_edge(src, matches[0], "depends_on", evidence_kind="observed_static", confidence=1.0,
                                      source_path=path, source_sha256=src_sha,
                                      details={"filename_literal": text, "reason": "benchmark source-root/path composition"})

        # Dynamic loading/path references are explicit in source but not Python imports.
        explicit = {
            "workflow_skills.py": ["code_mode.py"],
            "workflow_graphs.py": ["workflow_skills.py"],
            "capability_forge.py": ["regression_compiler.py"],
            "experience_memory.py": ["capability_forge.py"],
            "experience_loop.py": ["experience_memory.py", "regression_compiler.py", "capability_forge.py"],
            "architecture_twin.py": ["causal_spine.py"],
        }
        for a, bs in explicit.items():
            src = self.module_nodes.get(pathlib.Path(a).stem)
            if not src:
                continue
            for b in bs:
                dst = self.module_nodes.get(pathlib.Path(b).stem)
                if dst:
                    self.add_edge(src, dst, "depends_on", evidence_kind="observed_static", confidence=1.0,
                                  source_path=self.nodes[src].get("source_path"), source_sha256=self.nodes[src].get("source_sha256"),
                                  details={"reason": "explicit guest-local load/reference"})

    def _registry_node(self, name: str, path: pathlib.Path) -> str:
        return self.add_file_node(path, kind="registry", key=name, name=name, authoritative=True,
                                  metadata={"registry": name}) if path.is_file() else self.add_node("registry", name, name=name, identity=str(path), authoritative=True,
                                                                                                      metadata={"missing": True})

    @staticmethod
    def _walk_strings(value: Any) -> Iterable[str]:
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for x in value:
                yield from TwinBuilder._walk_strings(x)
        elif isinstance(value, dict):
            for x in value.values():
                yield from TwinBuilder._walk_strings(x)

    def add_workflows(self) -> None:
        root = self.state_root / "workflows"
        reg = self.add_node("registry", "workflows", name="workflow registry", identity=str(root), authoritative=True,
                            metadata={"path": str(root)})
        if not root.is_dir():
            return
        for path in sorted(root.glob("*/*.json")):
            d = safe_json(path)
            if not isinstance(d, dict):
                continue
            name, version = str(d.get("name") or path.parent.name), str(d.get("version") or path.stem)
            wf = self.add_file_node(path, kind="workflow", key=f"{name}@{version}", name=name, authoritative=True,
                                    generation=((d.get("provenance") or {}).get("generation") if isinstance(d.get("provenance"), dict) else None),
                                    metadata={"version": version, "description": d.get("description")})
            self.add_edge(reg, wf, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                          source_path=path, source_sha256=self.nodes[wf]["source_sha256"])
            for text in self._walk_strings(d.get("workflow") or {}):
                if text.startswith(str(self.source_root)):
                    dst = self.source_nodes.get(pathlib.Path(text))
                    if dst:
                        self.add_edge(wf, dst, "invokes", evidence_kind="observed_definition", confidence=1.0,
                                      source_path=path, source_sha256=self.nodes[wf]["source_sha256"], details={"argv_path": text})
            prov = d.get("provenance")
            if isinstance(prov, dict) and prov.get("generation"):
                gen = self.add_node("generation", str(prov["generation"]), name=str(prov["generation"]), identity=str(prov["generation"]), authoritative=False)
                self.add_edge(wf, gen, "generated_from", evidence_kind="observed_definition", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[wf]["source_sha256"])

    def add_graphs(self) -> None:
        root = self.state_root / "workflow-graphs"
        reg = self.add_node("registry", "workflow-graphs", name="workflow graph registry", identity=str(root), authoritative=True,
                            metadata={"path": str(root)})
        if not root.is_dir():
            return
        for path in sorted(root.glob("*/*.json")):
            d = safe_json(path)
            if not isinstance(d, dict):
                continue
            name, version = str(d.get("name") or path.parent.name), str(d.get("version") or path.stem)
            graph = self.add_file_node(path, kind="workflow_graph", key=f"{name}@{version}", name=name, authoritative=True,
                                       generation="gen4-workflow-graphs-r1",
                                       metadata={"version": version, "description": d.get("description")})
            self.add_edge(reg, graph, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                          source_path=path, source_sha256=self.nodes[graph]["source_sha256"])
            for item in d.get("nodes") or []:
                if not isinstance(item, dict) or not item.get("workflow"):
                    continue
                ref = str(item["workflow"])
                dst = nid("workflow", ref)
                if dst not in self.nodes:
                    dst = self.add_node("workflow", ref, name=ref.split("@")[0], identity=ref, metadata={"unresolved": True})
                self.add_edge(graph, dst, "invokes", evidence_kind="observed_definition", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[graph]["source_sha256"], details={"node_id": item.get("id")})

    def add_capabilities(self) -> None:
        path = self.state_root / "capabilities" / "registry.json"
        if not path.is_file():
            return
        reg_node = self._registry_node("capabilities", path)
        d = safe_json(path)
        caps = d.get("capabilities") if isinstance(d, dict) else None
        if not isinstance(caps, dict):
            return
        for h, rec in sorted(caps.items()):
            if not isinstance(rec, dict):
                continue
            name = str(rec.get("name") or h[:12])
            cap = self.add_node("capability", h, name=name, identity=h, authoritative=False,
                                generation="gen5-capability-forge-r1",
                                metadata={k: rec.get(k) for k in ("version", "state", "purpose", "applicability", "side_effects", "source_files", "source_hashes", "creator_episode")})
            self.capabilities_by_name[name].append(cap)
            self.add_edge(reg_node, cap, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                          source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])
            evh = rec.get("evaluator_hash")
            if evh:
                evaluator = self.add_node("evaluator", str(evh), name=f"evaluator:{name}", identity=str(evh),
                                          generation="gen5-capability-forge-r1", metadata={"version": rec.get("evaluator_version")})
                self.add_edge(evaluator, cap, "validates", evidence_kind="observed_registry", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])
            if rec.get("object"):
                opath = pathlib.Path(str(rec["object"]))
                obj = self.add_node("artifact", str(opath), name=opath.name, identity=str(opath), authoritative=True,
                                    source_path=opath if opath.is_file() else None, source_sha256=sha_path(opath),
                                    source_bytes=opath.stat().st_size if opath.is_file() else None,
                                    metadata={"role": "capability_object", "missing": not opath.exists()})
                self.add_edge(cap, obj, "generated_from", evidence_kind="observed_registry", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])

    def add_memory(self) -> None:
        path = self.state_root / "memory" / "registry.json"
        if not path.is_file():
            return
        reg_node = self._registry_node("memory", path)
        d = safe_json(path); memories = d.get("memories") if isinstance(d, dict) else None
        if not isinstance(memories, dict):
            return
        pending_supersedes: list[tuple[str, str]] = []
        for h, rec in sorted(memories.items()):
            if not isinstance(rec, dict):
                continue
            proc = rec.get("procedure") if isinstance(rec.get("procedure"), dict) else {}
            mem = self.add_node("procedural_memory", h, name=f"memory:{h[:12]}", identity=h,
                                generation="gen6-experience-memory-r1",
                                metadata={"state": rec.get("state"), "procedure_fingerprint": rec.get("procedure_fingerprint"),
                                          "retrievals": rec.get("retrievals"), "successful_retrievals": rec.get("successful_retrievals")})
            self.add_edge(reg_node, mem, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                          source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])
            if proc.get("capability_hash"):
                cap = nid("capability", str(proc["capability_hash"]))
                if cap not in self.nodes:
                    cap = self.add_node("capability", str(proc["capability_hash"]), identity=str(proc["capability_hash"]), metadata={"unresolved": True})
                self.add_edge(mem, cap, "consumes", evidence_kind="observed_registry", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])
                self.add_edge(mem, cap, "generated_from", evidence_kind="observed_registry", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"], details={"kind": "distilled procedure"})
            if rec.get("superseded_by"):
                pending_supersedes.append((str(rec["superseded_by"]), h))
        for new_h, old_h in pending_supersedes:
            new, old = nid("procedural_memory", new_h), nid("procedural_memory", old_h)
            if new in self.nodes and old in self.nodes:
                self.add_edge(new, old, "supersedes", evidence_kind="observed_registry", confidence=1.0,
                              source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])

    def add_regressions(self) -> None:
        path = self.state_root / "regressions" / "registry.json"
        if not path.is_file():
            return
        reg_node = self._registry_node("regressions", path)
        d = safe_json(path); regs = d.get("regressions") if isinstance(d, dict) else None
        if not isinstance(regs, dict):
            return
        for h, rec in sorted(regs.items()):
            if not isinstance(rec, dict):
                continue
            rg = self.add_node("regression", h, name=f"regression:{h[:12]}", identity=h,
                               generation="gen6-experience-memory-r1",
                               metadata={"state": rec.get("state"), "selector": rec.get("selector"), "known_bad_hash": rec.get("known_bad_hash"),
                                         "known_good_hash": rec.get("known_good_hash"), "failure_evidence": rec.get("failure_evidence")})
            self.add_edge(reg_node, rg, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                          source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"])
            for label in ("known_bad_hash", "known_good_hash"):
                ch = rec.get(label)
                if ch:
                    cap = nid("capability", str(ch))
                    if cap not in self.nodes:
                        cap = self.add_node("capability", str(ch), identity=str(ch), metadata={"unresolved": True})
                    self.add_edge(rg, cap, "generated_from", evidence_kind="observed_registry", confidence=1.0,
                                  source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"], details={"role": label})
            selector = rec.get("selector") if isinstance(rec.get("selector"), dict) else {}
            sname = selector.get("name")
            if sname:
                for cap in self.capabilities_by_name.get(str(sname), []):
                    self.add_edge(rg, cap, "gates", evidence_kind="inferred", confidence=0.8,
                                  source_path=path, source_sha256=self.nodes[reg_node]["source_sha256"],
                                  details={"reason": "selector name matches capability lineage; exact descendant applicability is runtime-gated"})

    def add_runtime_artifacts(self) -> None:
        bench_root = self.state_root / "benchmarks"
        if bench_root.is_dir():
            for path in sorted(bench_root.glob("*.json")):
                d = safe_json(path)
                name = path.stem
                generation = d.get("generation") if isinstance(d, dict) else None
                node = self.add_file_node(path, kind="benchmark_artifact", key=name, name=name, authoritative=True,
                                          generation=str(generation) if generation else None,
                                          metadata={"passed": d.get("passed") if isinstance(d, dict) else None,
                                                    "total": d.get("total") if isinstance(d, dict) else None})
                stem = None
                for candidate in self.source_nodes:
                    if candidate.parent.name == "bench" and candidate.stem.replace("benchmark_", "") in name:
                        stem = candidate.stem
                if stem and (v := nid("validation", f"benchmark:{stem}")) in self.nodes:
                    self.add_edge(node, v, "generated_from", evidence_kind="observed_runtime", confidence=1.0,
                                  source_path=path, source_sha256=self.nodes[node]["source_sha256"])

        # Raw append-only evidence artifacts are nodes, but their event content lives in
        # the causal index. Appends mean "newer evidence available", not invalid history.
        for rel in ("traces/events.jsonl", "capabilities/provenance.jsonl", "memory/provenance.jsonl", "regressions/provenance.jsonl", "recovery/launcher-events.jsonl"):
            path = self.state_root / rel
            if path.is_file():
                self.add_file_node(path, kind="evidence_artifact", key=str(path), name=path.name,
                                   authoritative=True, freshness_mode="append_only", metadata={"role": "append_only_raw_evidence"})

    def add_build_and_recovery(self) -> None:
        server = self.module_nodes.get("server")
        if self.build_file.is_file():
            d = safe_json(self.build_file)
            build_file_node = self.add_file_node(self.build_file, kind="build_state", key="current", name="current build state", authoritative=True)
            if isinstance(d, dict):
                generation = str(d.get("generation") or "unknown")
                build_id = str(d.get("build_id") or "unknown")
                gen = self.add_node("generation", generation, name=generation, identity=generation, authoritative=False)
                build = self.add_node("build", build_id, name=build_id, identity=build_id, authoritative=False,
                                      generation=generation, metadata={"recovery_state": d.get("recovery_state"), "accepted_at": d.get("accepted_at"),
                                                                       "source_sha256": d.get("source_sha256"), "last_known_good_sha256": d.get("last_known_good_sha256")})
                self.add_edge(build_file_node, build, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                              source_path=self.build_file, source_sha256=self.nodes[build_file_node]["source_sha256"])
                self.add_edge(build, gen, "generated_from", evidence_kind="observed_registry", confidence=1.0,
                              source_path=self.build_file, source_sha256=self.nodes[build_file_node]["source_sha256"])
                if server and d.get("source_sha256") == self.nodes[server].get("source_sha256"):
                    self.add_edge(build_file_node, server, "authoritative_for", evidence_kind="observed_registry", confidence=1.0,
                                  source_path=self.build_file, source_sha256=self.nodes[build_file_node]["source_sha256"], details={"hash_match": True})
        lkg = self.recovery_root / "server.last-known-good.py"
        if lkg.is_file():
            lkg_node = self.add_file_node(lkg, kind="recovery", key="last-known-good", name="server last-known-good", authoritative=True,
                                          generation="gen4-workflow-graphs-r1", metadata={"role": "LKG"})
            if server:
                confidence = 1.0 if self.nodes[lkg_node].get("source_sha256") == self.nodes[server].get("source_sha256") else 0.5
                self.add_edge(lkg_node, server, "recovers_to", evidence_kind="observed_runtime", confidence=confidence,
                              source_path=lkg, source_sha256=self.nodes[lkg_node]["source_sha256"], details={"live_equals_lkg": confidence == 1.0})

        # Systemd units are runtime architecture, not code authority.
        systemd = pathlib.Path("/etc/systemd/system")
        if systemd.is_dir():
            for path in sorted(systemd.glob("*optiplex-lab*")):
                if path.is_file():
                    service = self.add_file_node(path, kind="service", key=path.name, name=path.name, authoritative=True,
                                                 generation="gen1-self-hosted-lab-r2")
                    if server and "mcp" in path.name:
                        self.add_edge(service, server, "invokes", evidence_kind="observed_runtime", confidence=0.9,
                                      source_path=path, source_sha256=self.nodes[service]["source_sha256"])

    def add_history_and_authority(self) -> None:
        for filename, generation in sorted(INTRODUCED.items()):
            src = self.module_nodes.get(pathlib.Path(filename).stem)
            if not src:
                continue
            gen = self.add_node("generation", generation, name=generation, identity=generation, authoritative=False,
                                metadata={"evidence": "accepted generation lineage seed"})
            self.add_edge(src, gen, "generated_from", evidence_kind="history_seed", confidence=1.0,
                          details={"introduced_component": filename})

        boundary = self.add_node("authority_boundary", "guest-vm", name="isolated mcp-lab VM boundary", identity="guest-vm",
                                 authoritative=False, generation="bootstrap", metadata={"scope": "Optiplex_Lab + mcp-lab"})
        frozen = self.add_node("external_authority", "Optiplex_MCP", name="Optiplex_MCP", identity="Optiplex_MCP",
                               authoritative=True, metadata={"policy": "frozen safe host/control infrastructure"})
        targets = [
            ("host-filesystem", "host filesystem mounts"), ("host-credentials", "host credentials"),
            ("host-control-sockets", "Docker/libvirt/control sockets"), ("private-network", "LAN/Tailscale/private network"),
            ("production-authority", "production authority"),
        ]
        for key, name in targets:
            target = self.add_node("prohibited_target", key, name=name, identity=key, authoritative=False)
            self.add_edge(boundary, target, "prohibited_from_accessing", evidence_kind="policy_seed", confidence=1.0,
                          details={"source": "stable project authority invariant"})
        self.add_edge(boundary, frozen, "prohibited_from_accessing", evidence_kind="policy_seed", confidence=1.0,
                      details={"source": "Optiplex_MCP frozen boundary"})
        # Existing containment benchmark evidence protects this invariant when present.
        for node in list(self.nodes.values()):
            if node["kind"] == "benchmark_artifact" and "gen6" in node["name"]:
                self.add_edge(node["id"], boundary, "validates", evidence_kind="observed_runtime", confidence=0.9,
                              source_path=node.get("source_path"), source_sha256=node.get("source_sha256"), details={"aspect": "containment"})

    def build(self) -> dict[str, Any]:
        self.add_sources()
        self.add_workflows()
        self.add_graphs()
        self.add_capabilities()
        self.add_memory()
        self.add_regressions()
        self.add_runtime_artifacts()
        self.add_build_and_recovery()
        self.add_history_and_authority()
        nodes = sorted(self.nodes.values(), key=lambda n: n["id"])
        edges = sorted(self.edges.values(), key=lambda e: (e["src"], e["dst"], e["relation"], e["id"]))
        inputs = sorted(self.inputs.values(), key=lambda x: x["path"])
        structural = {"schema_version": SCHEMA_VERSION, "version": VERSION, "nodes": nodes, "edges": edges, "inputs": inputs}
        digest = sha_bytes(canonical(structural))
        return {"generated_at": utc(), "graph_digest": digest, **structural}


def load_causal_module(source_root: pathlib.Path):
    path = source_root / "causal_spine.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(f"gen7_causal_{sha_bytes(str(path).encode())[:8]}", path)
    if not spec or not spec.loader:
        return None
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def write_sqlite(path: pathlib.Path, twin: dict[str, Any], causal: dict[str, Any] | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists(): tmp.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE nodes(id TEXT PRIMARY KEY, kind TEXT, name TEXT, identity TEXT, source_path TEXT, source_sha256 TEXT, source_bytes INTEGER, freshness_mode TEXT, authoritative INTEGER, generation TEXT, metadata_json TEXT);
        CREATE TABLE edges(id TEXT PRIMARY KEY, src TEXT, dst TEXT, relation TEXT, evidence_kind TEXT, confidence REAL, source_path TEXT, source_sha256 TEXT, details_json TEXT);
        CREATE INDEX edges_src ON edges(src); CREATE INDEX edges_dst ON edges(dst); CREATE INDEX nodes_kind ON nodes(kind); CREATE INDEX nodes_name ON nodes(name);
        CREATE TABLE inputs(path TEXT PRIMARY KEY, sha256 TEXT, bytes INTEGER, freshness_mode TEXT);
        CREATE TABLE events(id TEXT PRIMARY KEY, timestamp TEXT, source_path TEXT, source_line INTEGER, evidence_line_sha256 TEXT, data_json TEXT);
        CREATE TABLE event_edges(id TEXT PRIMARY KEY, src TEXT, dst TEXT, relation TEXT, strength TEXT, confidence REAL, evidence TEXT, details_json TEXT);
        CREATE INDEX event_edges_src ON event_edges(src); CREATE INDEX event_edges_dst ON event_edges(dst);
        """)
        meta = {"version": twin["version"], "schema_version": twin["schema_version"], "graph_digest": twin["graph_digest"], "generated_at": twin["generated_at"]}
        if causal: meta.update({"causal_version": causal.get("version"), "causal_digest": causal.get("digest")})
        con.executemany("INSERT INTO metadata VALUES (?,?)", [(k, json.dumps(v, sort_keys=True)) for k, v in sorted(meta.items())])
        con.executemany("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            (n["id"],n["kind"],n["name"],n["identity"],n.get("source_path"),n.get("source_sha256"),n.get("source_bytes"),n.get("freshness_mode"),int(bool(n.get("authoritative"))),n.get("generation"),json.dumps(n.get("metadata") or {},sort_keys=True)) for n in twin["nodes"]])
        con.executemany("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?,?)", [
            (e["id"],e["src"],e["dst"],e["relation"],e["evidence_kind"],e["confidence"],e.get("source_path"),e.get("source_sha256"),json.dumps(e.get("details") or {},sort_keys=True)) for e in twin["edges"]])
        con.executemany("INSERT INTO inputs VALUES (?,?,?,?)", [(x["path"],x.get("sha256"),x.get("bytes"),x.get("freshness_mode")) for x in twin["inputs"]])
        if causal:
            con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?)", [(e["id"],e.get("timestamp"),e.get("source_path"),e.get("source_line"),e.get("evidence_line_sha256"),json.dumps(e.get("data") or {},sort_keys=True)) for e in causal.get("events",[])])
            con.executemany("INSERT INTO event_edges VALUES (?,?,?,?,?,?,?,?)", [(e["id"],e["src"],e["dst"],e["relation"],e.get("strength"),e.get("confidence"),e.get("evidence"),json.dumps(e.get("details") or {},sort_keys=True)) for e in causal.get("edges",[])])
        con.commit()
    finally:
        con.close()
    tmp.replace(path)


def build_all(source_root: pathlib.Path = DEFAULT_SOURCE_ROOT, state_root: pathlib.Path = DEFAULT_STATE_ROOT,
              build_file: pathlib.Path = DEFAULT_BUILD_FILE, recovery_root: pathlib.Path = DEFAULT_RECOVERY_ROOT,
              twin_root: pathlib.Path = DEFAULT_TWIN_ROOT) -> dict[str, Any]:
    started = time.monotonic()
    twin = TwinBuilder(source_root, state_root, build_file, recovery_root).build()
    causal_mod = load_causal_module(source_root)
    causal = None
    if causal_mod:
        sources = (
            state_root/"traces/events.jsonl", state_root/"capabilities/provenance.jsonl", state_root/"memory/provenance.jsonl",
            state_root/"regressions/provenance.jsonl", recovery_root/"launcher-events.jsonl",
        )
        # The module's build-state pseudo-event follows its own constant path, so for a
        # synthetic selftest root we intentionally omit it; real Lab uses the default.
        causal = causal_mod.build_index(sources)
    twin_root.mkdir(parents=True, exist_ok=True)
    snapshot = twin_root / "twin-current.json"
    causal_path = twin_root / "causal-index.json"
    db = twin_root / "twin.sqlite3"
    atomic_json(snapshot, twin)
    if causal is not None:
        atomic_json(causal_path, causal)
    write_sqlite(db, twin, causal)
    return {
        "ok": True, "version": VERSION, "graph_digest": twin["graph_digest"],
        "nodes": len(twin["nodes"]), "edges": len(twin["edges"]), "inputs": len(twin["inputs"]),
        "causal_digest": causal.get("digest") if causal else None,
        "causal_events": len(causal.get("events",[])) if causal else 0,
        "causal_edges": len(causal.get("edges",[])) if causal else 0,
        "snapshot": str(snapshot), "causal_index": str(causal_path) if causal else None, "sqlite": str(db),
        "snapshot_bytes": snapshot.stat().st_size, "sqlite_bytes": db.stat().st_size,
        "duration_ms": round((time.monotonic()-started)*1000, 3),
    }


def load_snapshot(path: pathlib.Path | None = None, twin_root: pathlib.Path = DEFAULT_TWIN_ROOT) -> dict[str, Any]:
    p = path or twin_root/"twin-current.json"
    value = safe_json(p)
    if not isinstance(value, dict):
        raise RuntimeError(f"Twin snapshot not found/invalid: {p}")
    return value


def node_freshness(node: dict[str, Any]) -> dict[str, Any]:
    path_text = node.get("source_path")
    expected = node.get("source_sha256")
    if not path_text or not expected:
        return {"state": "not_applicable"}
    path = pathlib.Path(path_text)
    if not path.is_file():
        return {"state": "missing", "path": path_text, "expected_sha256": expected}
    expected_bytes = node.get("source_bytes")
    mode = node.get("freshness_mode") or "hash"
    if mode == "append_only" and isinstance(expected_bytes, int):
        current_bytes = path.stat().st_size
        if current_bytes < expected_bytes:
            return {"state": "stale", "reason": "append-only source shrank", "path": path_text}
        prefix = path.open("rb").read(expected_bytes)
        prefix_sha = sha_bytes(prefix)
        if prefix_sha != expected:
            return {"state": "stale", "reason": "append-only prefix changed", "path": path_text,
                    "expected_sha256": expected, "prefix_sha256": prefix_sha}
        return {"state": "fresh" if current_bytes == expected_bytes else "newer_evidence_available",
                "path": path_text, "indexed_bytes": expected_bytes, "current_bytes": current_bytes}
    current = sha_path(path)
    return {"state": "fresh" if current == expected else "stale", "path": path_text,
            "expected_sha256": expected, "current_sha256": current}


def resolve(snapshot: dict[str, Any], ref: str) -> list[dict[str, Any]]:
    ref_l = ref.lower()
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    for n in snapshot.get("nodes", []):
        values = [n.get("id"), n.get("name"), n.get("identity"), n.get("source_path"), n.get("source_sha256")]
        texts = [str(v) for v in values if v]
        if any(ref == t for t in texts) or any(t.startswith(ref) for t in texts if len(ref) >= 12 and all(c in "0123456789abcdef" for c in ref_l)):
            exact.append(n)
        elif any(ref_l in t.lower() for t in texts):
            fuzzy.append(n)
    return exact or fuzzy[:25]


def query(snapshot: dict[str, Any], ref: str) -> dict[str, Any]:
    matches = resolve(snapshot, ref)
    ids = {n["id"] for n in matches}
    edges = [e for e in snapshot.get("edges", []) if e["src"] in ids or e["dst"] in ids]
    owners = [n["id"] for n in matches if n.get("authoritative")]
    for e in edges:
        if e["relation"] == "authoritative_for" and e["dst"] in ids:
            owners.append(e["src"])
    uncertainty = []
    for n in matches:
        f = node_freshness(n)
        if f["state"] in {"stale", "missing", "newer_evidence_available"}:
            uncertainty.append({"node": n["id"], "freshness": f})
    return {
        "ref": ref, "matches": [{**n, "freshness": node_freshness(n)} for n in matches],
        "edges": edges, "authoritative_owners": sorted(set(owners)),
        "uncertainty": uncertainty or ([] if matches else ["No Twin node matched the query."]),
    }


def impact(snapshot: dict[str, Any], ref: str, max_depth: int = 4) -> dict[str, Any]:
    matches = resolve(snapshot, ref)
    if not matches:
        return {"ref": ref, "matches": [], "direct": [], "transitive": [], "validations": [], "recovery": [],
                "confidence": 0.0, "uncertainty": ["No Twin node matched the proposed change; fail closed with full validation."]}
    nodes = {n["id"]: n for n in snapshot.get("nodes", [])}
    reverse: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    forward: dict[str, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for e in snapshot.get("edges", []):
        if e["relation"] in IMPACT_REVERSE:
            reverse[e["dst"]].append((e["src"], e))
        if e["relation"] in IMPACT_FORWARD:
            forward[e["src"]].append((e["dst"], e))
    seeds = {n["id"] for n in matches}
    seen = set(seeds); q = deque((x, 0) for x in sorted(seeds)); found: dict[str, dict[str, Any]] = {}
    while q:
        cur, depth = q.popleft()
        if depth >= max_depth:
            continue
        neighbors = [*reverse.get(cur, []), *forward.get(cur, [])]
        for other, edge in neighbors:
            if edge.get("confidence", 0) < 0.75:
                continue
            old = found.get(other)
            candidate = {"node": other, "depth": depth+1, "via": edge["id"], "relation": edge["relation"],
                         "confidence": edge["confidence"], "evidence_kind": edge["evidence_kind"]}
            if old is None or candidate["depth"] < old["depth"]:
                found[other] = candidate
            if other not in seen:
                seen.add(other); q.append((other, depth+1))
    direct = [v for v in found.values() if v["depth"] == 1 and v["node"] not in seeds]
    transitive = [v for v in found.values() if v["depth"] > 1 and v["node"] not in seeds]
    validations = sorted({x["node"] for x in [*direct, *transitive] if nodes.get(x["node"],{}).get("kind") in {"validation","regression","benchmark_artifact","evaluator"}})
    recovery = sorted({x["node"] for x in [*direct, *transitive] if nodes.get(x["node"],{}).get("kind") in {"recovery","build_state","service"}})
    freshness_issues = []
    for n in matches:
        f = node_freshness(n)
        if f["state"] != "fresh" and f["state"] != "not_applicable": freshness_issues.append({"node":n["id"],"freshness":f})
    inferred = [x for x in [*direct,*transitive] if x["evidence_kind"] == "inferred"]
    confidence = min([x["confidence"] for x in direct] or [1.0])
    if freshness_issues: confidence = min(confidence, 0.5)
    return {
        "ref": ref, "matches": [n["id"] for n in matches],
        "direct": sorted(direct, key=lambda x: (x["node"],x["via"])),
        "transitive": sorted(transitive, key=lambda x: (x["depth"],x["node"])),
        "validations": validations, "recovery": recovery, "confidence": round(confidence,3),
        "uncertainty": [*freshness_issues, *([{"inferred_edges": len(inferred), "note":"Inferred impact edges are lower-confidence and should not remove validation gates."}] if inferred else [])],
        "fail_closed": bool(freshness_issues),
    }


def verify(snapshot: dict[str, Any]) -> dict[str, Any]:
    states = defaultdict(int); issues=[]
    for n in snapshot.get("nodes", []):
        f = node_freshness(n); states[f["state"]] += 1
        if f["state"] in {"stale","missing"}: issues.append({"node":n["id"],"freshness":f})
    return {"ok": not issues, "states": dict(sorted(states.items())), "issues": issues,
            "newer_evidence_available": states.get("newer_evidence_available",0)}


def causal_reconstruct(ref: str, twin_root: pathlib.Path = DEFAULT_TWIN_ROOT, depth: int = 4) -> dict[str, Any]:
    idx = safe_json(twin_root/"causal-index.json")
    if not isinstance(idx, dict):
        return {"needle": ref, "uncertainty": ["Causal index is missing; rebuild Twin first."]}
    module = load_causal_module(DEFAULT_SOURCE_ROOT)
    if not module:
        return {"needle": ref, "uncertainty": ["Causal spine module is missing."]}
    return module.reconstruct(idx, ref, depth)


def summary(snapshot: dict[str, Any], twin_root: pathlib.Path = DEFAULT_TWIN_ROOT) -> dict[str, Any]:
    kinds=defaultdict(int); rels=defaultdict(int); evidence=defaultdict(int)
    for n in snapshot.get("nodes",[]): kinds[n["kind"]]+=1
    for e in snapshot.get("edges",[]): rels[e["relation"]]+=1; evidence[e["evidence_kind"]]+=1
    return {"version":snapshot.get("version"),"graph_digest":snapshot.get("graph_digest"),"nodes":len(snapshot.get("nodes",[])),"edges":len(snapshot.get("edges",[])),
            "kinds":dict(sorted(kinds.items())),"relations":dict(sorted(rels.items())),"evidence_kinds":dict(sorted(evidence.items())),"freshness":verify(snapshot),
            "snapshot":str(twin_root/"twin-current.json"),"sqlite":str(twin_root/"twin.sqlite3"),"causal_index":str(twin_root/"causal-index.json")}


def selftest() -> dict[str, Any]:
    checks=[]
    def ck(name: str, ok: Any, detail: Any=None): checks.append({"name":name,"ok":bool(ok),"detail":detail})
    with tempfile.TemporaryDirectory(prefix="architecture-twin-selftest-") as td:
        root=pathlib.Path(td); src=root/"opt"; state=root/"state"; rec=state/"recovery"; out=root/"twin"; (src/"bench").mkdir(parents=True); rec.mkdir(parents=True)
        (src/"a.py").write_text("import b\ndef selftest(): pass\n")
        (src/"b.py").write_text("def f(): return 1\n")
        (src/"causal_spine.py").write_text("def build_index(sources): return {'version':'x','digest':'d','events':[],'edges':[]}\n")
        (src/"bench"/"benchmark_x.py").write_text(f"P={str(src/'b.py')!r}\n")
        (state/"workflows"/"w").mkdir(parents=True); (state/"workflow-graphs"/"g").mkdir(parents=True)
        (state/"workflows"/"w"/"1.json").write_text(json.dumps({"name":"w","version":"1","workflow":{"steps":[{"op":"command","argv":[str(src/'b.py')]}]}}))
        (state/"workflow-graphs"/"g"/"1.json").write_text(json.dumps({"name":"g","version":"1","nodes":[{"id":"n","workflow":"w@1","depends_on":[]}]}))
        for sub,key in [("capabilities","capabilities"),("memory","memories"),("regressions","regressions")]:
            (state/sub).mkdir(parents=True); (state/sub/"registry.json").write_text(json.dumps({key:{},"version":"x"}))
        (state/"traces").mkdir(parents=True); (state/"traces"/"events.jsonl").write_text("")
        for p in [state/"capabilities"/"provenance.jsonl",state/"memory"/"provenance.jsonl",state/"regressions"/"provenance.jsonl",rec/"launcher-events.jsonl"]: p.write_text("")
        build=root/"build.json"; build.write_text(json.dumps({"generation":"x","build_id":"x1","source_sha256":"nope","recovery_state":"ACCEPTED"}))
        (rec/"server.last-known-good.py").write_text("x\n")
        one=TwinBuilder(src,state,build,rec).build(); two=TwinBuilder(src,state,build,rec).build()
        ck("deterministic_graph_digest",one["graph_digest"]==two["graph_digest"])
        edge_trip={(e["src"],e["dst"],e["relation"]) for e in one["edges"]}
        ck("python_import_dependency",(nid("source",str(src/"a.py")),nid("source",str(src/"b.py")),"imports") in edge_trip)
        ck("graph_invokes_workflow",(nid("workflow_graph","g@1"),nid("workflow","w@1"),"invokes") in edge_trip)
        imp=impact(one,str(src/"b.py")); impacted={x["node"] for x in [*imp["direct"],*imp["transitive"]]}
        ck("impact_finds_importer",nid("source",str(src/"a.py")) in impacted,imp)
        q=query(one,str(src/"b.py")); ck("query_has_freshness",q["matches"] and q["matches"][0]["freshness"]["state"]=="fresh")
        (src/"b.py").write_text("def f(): return 2\n")
        q2=query(one,str(src/"b.py")); ck("stale_hash_exposed",q2["matches"][0]["freshness"]["state"]=="stale",q2["matches"][0]["freshness"])
    return {"version":VERSION,"passed":sum(c["ok"] for c in checks),"total":len(checks),"checks":checks}


def main() -> None:
    ap=argparse.ArgumentParser(description="Gen7 provenance-backed architectural digital twin")
    ap.add_argument("--selftest",action="store_true")
    sub=ap.add_subparsers(dest="cmd")
    sub.add_parser("build")
    p=sub.add_parser("summary"); p.add_argument("--snapshot")
    p=sub.add_parser("verify"); p.add_argument("--snapshot")
    p=sub.add_parser("query"); p.add_argument("ref"); p.add_argument("--snapshot")
    p=sub.add_parser("impact"); p.add_argument("ref"); p.add_argument("--snapshot"); p.add_argument("--depth",type=int,default=4)
    p=sub.add_parser("causal"); p.add_argument("ref"); p.add_argument("--depth",type=int,default=4)
    args=ap.parse_args()
    if args.selftest:
        out=selftest(); print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if out["passed"]==out["total"] else 1)
    if args.cmd=="build":
        print(json.dumps(build_all(),indent=2,sort_keys=True)); return
    if args.cmd=="causal":
        print(json.dumps(causal_reconstruct(args.ref,depth=args.depth),indent=2,sort_keys=True)); return
    if args.cmd in {"summary","verify","query","impact"}:
        snap=load_snapshot(pathlib.Path(args.snapshot) if args.snapshot else None)
        if args.cmd=="summary": out=summary(snap)
        elif args.cmd=="verify": out=verify(snap)
        elif args.cmd=="query": out=query(snap,args.ref)
        else: out=impact(snap,args.ref,args.depth)
        print(json.dumps(out,indent=2,sort_keys=True)); return
    ap.print_help()


if __name__=="__main__":
    main()
