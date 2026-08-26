#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

VERSION = 'gen4-workflow-graphs-r1'
REGISTRY = pathlib.Path('/var/lib/optiplex-lab/workflow-graphs')
RUN_ROOT = pathlib.Path('/var/lib/optiplex-lab/graph-runs')
TRACE = pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl')
WORKFLOW_SKILLS = pathlib.Path('/opt/optiplex-lab/workflow_skills.py')
WORKFLOW_REGISTRY = pathlib.Path('/var/lib/optiplex-lab/workflows')
MCP_SERVICE = 'optiplex-lab-mcp.service'
MCP_PORT = 8890
NAME_RE = re.compile(r'^[A-Za-z0-9._-]{1,80}$')
HARD_MAX_NODES = 32
HARD_MAX_INVOCATIONS = 32
HARD_MAX_ATTEMPTS = 3
HARD_MAX_TIMEOUT_S = 3600
HARD_MAX_DEPTH = 1


class DeferredValue(Exception):
    pass


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sha(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def append_trace(rec: dict[str, Any]) -> None:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    with TRACE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, separators=(',', ':'), default=str) + '\n')


def validate_name(value: str, label: str) -> str:
    if not NAME_RE.fullmatch(value):
        fail(f'invalid {label}: {value!r}')
    return value


def load_workflow_module():
    spec = importlib.util.spec_from_file_location('optiplex_lab_workflow_skills', WORKFLOW_SKILLS)
    if spec is None or spec.loader is None:
        fail('unable to load workflow_skills.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def graph_path(name: str, version: str) -> pathlib.Path:
    return REGISTRY / name / f'{version}.json'


def identity(defn: dict[str, Any]) -> dict[str, Any]:
    return {'name': defn['name'], 'version': defn['version'], 'sha256': sha(defn), 'runner_version': VERSION}


def validate_parent_parameters(defn: dict[str, Any]) -> None:
    ws = load_workflow_module()
    specs = defn.get('parameters', {})
    if not isinstance(specs, dict):
        fail('parameters must be an object')
    for pname, spec in specs.items():
        validate_name(str(pname), 'parameter name')
        if not isinstance(spec, dict):
            fail(f'parameter {pname} spec must be an object')
        ptype = str(spec.get('type') or '')
        if ptype not in ws.SUPPORTED_TYPES:
            fail(f'parameter {pname} has unsupported type {ptype!r}')
        if ptype == 'enum':
            choices = spec.get('choices')
            if not isinstance(choices, list) or not choices:
                fail(f'parameter {pname} enum requires non-empty choices')
        if 'default' in spec:
            ws.validate_value(pname, spec, spec['default'])


def resolve_parent_params(defn: dict[str, Any], supplied: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    ws = load_workflow_module()
    specs = defn.get('parameters', {})
    if not isinstance(supplied, dict):
        fail('parameters must be a JSON object')
    unknown = sorted(set(supplied) - set(specs))
    if unknown:
        fail(f'unknown parameters: {unknown}')
    resolved: dict[str, Any] = {}
    safe: dict[str, Any] = {}
    for name, spec in specs.items():
        if name in supplied:
            value = supplied[name]
        elif 'default' in spec:
            value = spec['default']
        elif spec.get('required', True):
            fail(f'missing required parameter: {name}')
        else:
            value = None
        if value is not None:
            value = ws.validate_value(name, spec, value)
        resolved[name] = value
        if spec.get('sensitive'):
            raw = canonical_bytes(value)
            safe[name] = {'type': spec['type'], 'redacted': True, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        else:
            safe[name] = {'type': spec['type'], 'value': value}
    return resolved, safe


def node_map(defn: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(n['id']): n for n in defn['nodes']}


def topo_order(defn: dict[str, Any]) -> list[str]:
    nodes = node_map(defn)
    indegree = {nid: 0 for nid in nodes}
    edges = {nid: [] for nid in nodes}
    for nid, node in nodes.items():
        deps = node.get('depends_on', [])
        if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
            fail(f'node {nid} depends_on must be list[str]')
        for dep in deps:
            if dep not in nodes:
                fail(f'node {nid} depends on unknown node {dep}')
            if dep == nid:
                fail(f'workflow graph cycle detected at {nid}')
            indegree[nid] += 1
            edges[dep].append(nid)
    ready = [nid for nid, n in indegree.items() if n == 0]
    order: list[str] = []
    while ready:
        nid = ready.pop(0)
        order.append(nid)
        for nxt in edges[nid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)
    if len(order) != len(nodes):
        fail('workflow graph cycle detected')
    return order


def validate_definition(defn: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(defn, dict):
        fail('graph definition must be an object')
    name = validate_name(str(defn.get('name') or ''), 'graph name')
    version = validate_name(str(defn.get('version') or ''), 'graph version')
    if not isinstance(defn.get('description'), str) or not defn['description'].strip():
        fail('description is required')
    validate_parent_parameters(defn)
    nodes = defn.get('nodes')
    if not isinstance(nodes, list) or not nodes:
        fail('nodes must be a non-empty list')
    limits = defn.get('limits', {})
    if not isinstance(limits, dict):
        fail('limits must be an object')
    max_nodes = int(limits.get('max_nodes', HARD_MAX_NODES))
    max_inv = int(limits.get('max_invocations', HARD_MAX_INVOCATIONS))
    max_depth = int(limits.get('max_depth', HARD_MAX_DEPTH))
    if max_nodes < 1 or max_nodes > HARD_MAX_NODES:
        fail(f'max_nodes must be 1..{HARD_MAX_NODES}')
    if max_inv < 1 or max_inv > HARD_MAX_INVOCATIONS:
        fail(f'max_invocations must be 1..{HARD_MAX_INVOCATIONS}')
    if max_depth != 1:
        fail('Gen-4 graph nesting depth is fixed at 1; graphs compose reusable workflows, not graphs')
    if len(nodes) > max_nodes:
        fail(f'graph has {len(nodes)} nodes, exceeds max_nodes={max_nodes}')
    seen: set[str] = set()
    invocation_budget = 0
    for raw in nodes:
        if not isinstance(raw, dict):
            fail('every node must be an object')
        nid = validate_name(str(raw.get('id') or ''), 'node id')
        if nid in seen:
            fail(f'duplicate node id: {nid}')
        seen.add(nid)
        child = str(raw.get('workflow') or '')
        if '@' not in child:
            fail(f'node {nid} must reference immutable child workflow as name@version')
        cname, cversion = child.rsplit('@', 1)
        validate_name(cname, 'child workflow name'); validate_name(cversion, 'child workflow version')
        if 'graph' in raw:
            fail('nested graph calls are not supported in Gen-4')
        if not isinstance(raw.get('params', {}), dict):
            fail(f'node {nid} params must be an object')
        run_if = raw.get('run_if', 'success')
        if run_if not in {'success', 'failure', 'always'}:
            fail(f'node {nid} run_if must be success|failure|always')
        attempts = int(raw.get('attempts', 1))
        if attempts < 1 or attempts > HARD_MAX_ATTEMPTS:
            fail(f'node {nid} attempts must be 1..{HARD_MAX_ATTEMPTS}')
        invocation_budget += attempts
        timeout_s = int(raw.get('timeout_s', limits.get('child_timeout_s', 300)))
        if timeout_s < 1 or timeout_s > HARD_MAX_TIMEOUT_S:
            fail(f'node {nid} timeout_s must be 1..{HARD_MAX_TIMEOUT_S}')
        recovers = raw.get('recovers', [])
        if not isinstance(recovers, list) or any(not isinstance(x, str) for x in recovers):
            fail(f'node {nid} recovers must be list[str]')
    if invocation_budget > max_inv:
        fail(f'worst-case child invocations {invocation_budget} exceeds max_invocations={max_inv}')
    topo_order(defn)
    nodes_by_id = node_map(defn)
    for nid, raw in nodes_by_id.items():
        for rid in raw.get('recovers', []):
            if rid not in nodes_by_id:
                fail(f'node {nid} recovers unknown node {rid}')
            if rid == nid:
                fail(f'node {nid} cannot recover itself')
    return {'name': name, 'version': version}


def register(defn: dict[str, Any], activate: bool = True) -> dict[str, Any]:
    validate_definition(defn)
    ident = identity(defn)
    path = graph_path(defn['name'], defn['version'])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text())
        if sha(existing) != ident['sha256']:
            fail(f'immutable graph version already exists with different hash: {defn["name"]}@{defn["version"]}')
        state = 'already_registered'
    else:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(defn, indent=2, sort_keys=True) + '\n')
        tmp.replace(path)
        state = 'registered'
    if activate:
        (path.parent / 'CURRENT').write_text(defn['version'] + '\n')
    append_trace({'timestamp': utc(), 'tool': 'workflow_graphs', 'event': 'register', **ident, 'state': state})
    return ident | {'state': state, 'path': str(path), 'active': activate}


def load_definition(name_version: str) -> tuple[dict[str, Any], pathlib.Path]:
    if '@' in name_version:
        name, version = name_version.rsplit('@', 1)
    else:
        name = name_version
        current = REGISTRY / name / 'CURRENT'
        if not current.exists():
            fail(f'graph not found or has no active version: {name}')
        version = current.read_text().strip()
    validate_name(name, 'graph name'); validate_name(version, 'graph version')
    path = graph_path(name, version)
    if not path.exists():
        fail(f'graph not found: {name}@{version}')
    defn = json.loads(path.read_text())
    validate_definition(defn)
    return defn, path


def get_path(value: Any, dotted: str) -> Any:
    cur = value
    for part in dotted.split('.') if dotted else []:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            fail(f'child output path not found: {dotted}')
    return cur


def substitute(node: Any, params: dict[str, Any], child_outputs: dict[str, Any], *, preflight: bool = False) -> Any:
    if isinstance(node, dict):
        if set(node) == {'$param'}:
            name = str(node['$param'])
            if name not in params:
                fail(f'unknown graph parameter: {name}')
            return params[name]
        if set(node) == {'$node'}:
            spec = node['$node']
            if not isinstance(spec, dict) or set(spec) != {'id', 'path'}:
                fail('$node requires {id,path}')
            nid = str(spec['id']); dotted = str(spec['path'])
            if nid not in child_outputs:
                if preflight:
                    raise DeferredValue(nid)
                fail(f'child output unavailable: {nid}')
            return get_path(child_outputs[nid], dotted)
        if set(node) == {'$path_join'}:
            parts = node['$path_join']
            if not isinstance(parts, list) or not parts:
                fail('$path_join requires a non-empty list')
            resolved = [substitute(x, params, child_outputs, preflight=preflight) for x in parts]
            if any(not isinstance(x, str) for x in resolved):
                fail('$path_join parts must resolve to strings')
            return os.path.normpath(os.path.join(*resolved))
        if set(node) == {'$concat'}:
            parts = node['$concat']
            if not isinstance(parts, list) or not parts:
                fail('$concat requires a non-empty list')
            resolved = [substitute(x, params, child_outputs, preflight=preflight) for x in parts]
            return ''.join(str(x) for x in resolved)
        return {k: substitute(v, params, child_outputs, preflight=preflight) for k, v in node.items()}
    if isinstance(node, list):
        return [substitute(x, params, child_outputs, preflight=preflight) for x in node]
    return node


def validate_deferred_child_params(child_defn: dict[str, Any], mapped: dict[str, Any]) -> None:
    specs = child_defn.get('parameters', {})
    unknown = sorted(set(mapped) - set(specs))
    if unknown:
        fail(f'unknown child parameters for {child_defn["name"]}@{child_defn["version"]}: {unknown}')
    for name, spec in specs.items():
        if name not in mapped and 'default' not in spec and spec.get('required', True):
            fail(f'missing required child parameter before execution: {child_defn["name"]}@{child_defn["version"]}.{name}')


def preflight(defn: dict[str, Any], supplied: dict[str, Any]) -> dict[str, Any]:
    validate_definition(defn)
    params, safe_parent = resolve_parent_params(defn, supplied)
    safe_parent = compact_safe_parameters(safe_parent)
    ws = load_workflow_module()
    order = topo_order(defn)
    nodes = node_map(defn)
    child_info = []
    for nid in order:
        node = nodes[nid]
        child_ref = node['workflow']
        child_defn, child_path = ws.load_definition(child_ref)
        try:
            mapped = substitute(node.get('params', {}), params, {}, preflight=True)
            _, safe_child = ws.resolve_params(child_defn, mapped)
            safe_child = compact_safe_parameters(safe_child)
            validation = 'resolved'
        except DeferredValue:
            validate_deferred_child_params(child_defn, node.get('params', {}))
            safe_child = {'deferred': True}
            validation = 'deferred_output_reference'
        child_info.append({'node': nid, 'workflow': ws.identity(child_defn), 'source': str(child_path), 'parameter_validation': validation, 'parameters': safe_child})
    limits = defn.get('limits', {})
    return {'graph': identity(defn), 'parameters': safe_parent, 'order': order, 'children': child_info,
            'limits': {'max_nodes': int(limits.get('max_nodes', HARD_MAX_NODES)), 'max_invocations': int(limits.get('max_invocations', HARD_MAX_INVOCATIONS)), 'max_depth': 1}}


def service_pid() -> int:
    p = subprocess.run(['systemctl', 'show', MCP_SERVICE, '-p', 'MainPID', '--value'], capture_output=True, text=True, timeout=10, check=False)
    try:
        return int(p.stdout.strip() or 0)
    except ValueError:
        return 0


def port_ready() -> bool:
    s = socket.socket(); s.settimeout(0.4)
    try:
        s.connect(('127.0.0.1', MCP_PORT)); return True
    except OSError:
        return False
    finally:
        s.close()


def wait_for_restart(before_pid: int, timeout_s: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    seen_down = False
    last_pid = service_pid()
    while time.monotonic() < deadline:
        cur = service_pid(); ready = port_ready()
        if cur == 0 or not ready:
            seen_down = True
        if cur and cur != before_pid and ready:
            return {'ok': True, 'pid_before': before_pid, 'pid_after': cur, 'seen_down': seen_down, 'ready': True}
        last_pid = cur
        time.sleep(0.2)
    return {'ok': False, 'pid_before': before_pid, 'pid_after': last_pid, 'seen_down': seen_down, 'ready': port_ready(), 'timeout_s': timeout_s}


def safe_write_json(path: pathlib.Path, value: Any, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + '\n')
    if mode is not None:
        os.chmod(tmp, mode)
    tmp.replace(path)


def compact_safe_parameters(safe: dict[str, Any], max_value_bytes: int = 256) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, item in safe.items():
        if not isinstance(item, dict) or 'value' not in item:
            out[name] = item
            continue
        raw = canonical_bytes(item.get('value'))
        if len(raw) > max_value_bytes:
            out[name] = {'type': item.get('type'), 'hashed': True, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        else:
            out[name] = item
    return out


def child_compact_from_stdout(stdout: str) -> dict[str, Any]:
    value = json.loads(stdout)
    if not isinstance(value, dict):
        fail('child workflow returned non-object JSON')
    if isinstance(value.get('parameters'), dict):
        value['parameters'] = compact_safe_parameters(value['parameters'])
    return value


class GraphRunner:
    def __init__(self, defn: dict[str, Any], supplied: dict[str, Any], *, run_dir: pathlib.Path | None = None):
        self.defn = defn
        self.ident = identity(defn)
        self.params, raw_safe_params = resolve_parent_params(defn, supplied)
        self.safe_params = compact_safe_parameters(raw_safe_params)
        self.preflight = preflight(defn, supplied)
        self.order = topo_order(defn)
        self.nodes = node_map(defn)
        self.run_id = run_dir.name if run_dir else f"wg_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        self.run_dir = run_dir or (RUN_ROOT / self.run_id)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.graph_path = self.run_dir / 'graph.json'
        self.params_path = self.run_dir / 'inputs.json'
        self.state_path = self.run_dir / 'state.json'
        self.result_path = self.run_dir / 'result.json'
        self.started_monotonic = time.monotonic()
        if not self.graph_path.exists():
            safe_write_json(self.graph_path, defn)
        if not self.params_path.exists():
            safe_write_json(self.params_path, supplied, 0o600)
        self.state = self._load_or_init_state()

    def _load_or_init_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            if state.get('graph', {}).get('sha256') != self.ident['sha256']:
                fail('resume graph identity mismatch')
            return state
        state = {'version': VERSION, 'run_id': self.run_id, 'graph': self.ident, 'parameters': self.safe_params,
                 'started_at': utc(), 'runner_pid': os.getpid(), 'status': 'RUNNING', 'ok': None,
                 'preflight': self.preflight, 'nodes': {}, 'invocations': [], 'recovered_failures': {},
                 'restart_checkpoints': [], 'resume_count': 0}
        self._save(state)
        append_trace({'timestamp': utc(), 'tool': 'workflow_graphs', 'event': 'graph_run_start', 'run_id': self.run_id, **self.ident, 'parameters': self.safe_params, 'order': self.order})
        return state

    def _save(self, state: dict[str, Any] | None = None) -> None:
        if state is not None:
            self.state = state
        safe_write_json(self.state_path, self.state)

    def _child_results(self) -> dict[str, Any]:
        out = {}
        for nid, nstate in self.state.get('nodes', {}).items():
            if nstate.get('child_output') is not None:
                out[nid] = nstate['child_output']
        return out

    def _dependency_states(self, node: dict[str, Any]) -> list[str]:
        return [str((self.state.get('nodes', {}).get(dep) or {}).get('status', 'PENDING')) for dep in node.get('depends_on', [])]

    def _should_run(self, node: dict[str, Any]) -> bool:
        states = self._dependency_states(node)
        mode = node.get('run_if', 'success')
        if not states:
            return mode != 'failure'
        failed = any(s == 'FAILED' for s in states)
        pending = any(s in {'PENDING', 'RUNNING'} for s in states)
        if pending:
            fail(f'node {node["id"]} dependency not terminal')
        if mode == 'always':
            return True
        if mode == 'failure':
            return failed
        return not failed

    def _resume_restart_if_needed(self, nid: str, nstate: dict[str, Any]) -> bool:
        checkpoint = nstate.get('restart_checkpoint')
        if not checkpoint or checkpoint.get('confirmed'):
            return True
        wait_s = int(self.nodes[nid].get('restart_timeout_s', 30))
        result = wait_for_restart(int(checkpoint.get('pid_before', 0)), wait_s)
        checkpoint.update(result | {'confirmed': bool(result['ok']), 'confirmed_at': utc() if result['ok'] else None})
        self.state['restart_checkpoints'].append({'node': nid} | checkpoint)
        if not result['ok']:
            nstate['status'] = 'FAILED'; nstate['error'] = 'restart checkpoint timeout'
            self._save(); return False
        self._save(); return True

    def run(self, *, stop_after: str | None = None) -> dict[str, Any]:
        ws = load_workflow_module()
        if self.state.get('status') in {'PASS', 'RECOVERED', 'FAIL'}:
            return self._final_result()
        if self.state.get('status') == 'PAUSED':
            self.state['status'] = 'RUNNING'; self.state['resume_count'] = int(self.state.get('resume_count', 0)) + 1; self._save()
        for nid in self.order:
            node = self.nodes[nid]
            nstate = self.state['nodes'].get(nid)
            if nstate:
                if nstate.get('status') == 'RUNNING':
                    self.state['status'] = 'FAIL'; self.state['ok'] = False
                    self.state['error'] = f'ambiguous interrupted node {nid}; refusing destructive replay'
                    self._save(); return self._final_result()
                if nstate.get('status') in {'SUCCEEDED', 'FAILED', 'SKIPPED'}:
                    if nstate.get('status') == 'SUCCEEDED' and not self._resume_restart_if_needed(nid, nstate):
                        return self._finish()
                    continue
            if not self._should_run(node):
                self.state['nodes'][nid] = {'id': nid, 'status': 'SKIPPED', 'workflow_ref': node['workflow'], 'reason': f"run_if={node.get('run_if','success')}", 'depends_on': node.get('depends_on', [])}
                self._save(); continue
            mapped = substitute(node.get('params', {}), self.params, self._child_results())
            child_defn, _ = ws.load_definition(node['workflow'])
            resolved_child, safe_child = ws.resolve_params(child_defn, mapped)
            safe_child = compact_safe_parameters(safe_child)
            child_ident = ws.identity(child_defn)
            nstate = {'id': nid, 'status': 'RUNNING', 'workflow_ref': node['workflow'], 'workflow': child_ident, 'parameters': safe_child,
                      'depends_on': node.get('depends_on', []), 'run_if': node.get('run_if', 'success'), 'attempts': [], 'started_at': utc()}
            self.state['nodes'][nid] = nstate; self._save()
            append_trace({'timestamp': utc(), 'tool': 'workflow_graphs', 'event': 'node_start', 'run_id': self.run_id, 'node_id': nid, 'child_workflow': child_ident, 'parameters': safe_child})
            attempts = int(node.get('attempts', 1)); timeout_s = int(node.get('timeout_s', self.defn.get('limits', {}).get('child_timeout_s', 300)))
            delay = max(0.0, min(float(node.get('retry_delay_s', 0.5)), 30.0))
            success = False; child_output: dict[str, Any] | None = None; last_error = None
            pid_before = service_pid() if node.get('restart_boundary') else 0
            for attempt in range(1, attempts + 1):
                attempt_file = self.run_dir / f'{nid}-attempt-{attempt}-params.json'
                safe_write_json(attempt_file, resolved_child, 0o600)
                started = time.monotonic()
                try:
                    p = subprocess.run([str(WORKFLOW_SKILLS), 'run', node['workflow'], '--params-file', str(attempt_file)], capture_output=True, text=True, timeout=timeout_s, check=False)
                    duration_ms = round((time.monotonic() - started) * 1000, 2)
                    child_output = child_compact_from_stdout(p.stdout) if p.stdout.strip() else None
                    code_run = (child_output or {}).get('code_run') or {}
                    ok = p.returncode == 0 and bool(code_run.get('ok'))
                    attempt_rec = {'attempt': attempt, 'ok': ok, 'exit_code': p.returncode, 'duration_ms': duration_ms,
                                   'stderr_preview': p.stderr[:500], 'code_run': code_run, 'child_workflow': (child_output or {}).get('workflow', child_ident)}
                    if not ok:
                        last_error = p.stderr[:500] or f'child workflow failed rc={p.returncode}'
                except subprocess.TimeoutExpired:
                    duration_ms = round((time.monotonic() - started) * 1000, 2); ok = False
                    attempt_rec = {'attempt': attempt, 'ok': False, 'exit_code': 124, 'duration_ms': duration_ms, 'stderr_preview': f'timeout after {timeout_s}s', 'code_run': {}}
                    last_error = attempt_rec['stderr_preview']
                nstate['attempts'].append(attempt_rec); self.state['invocations'].append({'node': nid} | attempt_rec); self._save()
                if ok:
                    success = True; break
                if attempt < attempts:
                    time.sleep(delay)
            nstate['child_output'] = child_output
            nstate['status'] = 'SUCCEEDED' if success else 'FAILED'; nstate['ended_at'] = utc(); nstate['error'] = None if success else last_error
            if success and node.get('restart_boundary'):
                nstate['restart_checkpoint'] = {'pid_before': pid_before, 'confirmed': False, 'required': True}
            if success and node.get('recovers'):
                for failed_id in node.get('recovers', []):
                    if (self.state['nodes'].get(failed_id) or {}).get('status') == 'FAILED':
                        self.state['recovered_failures'][failed_id] = nid
                        self.state['nodes'][failed_id]['recovered_by'] = nid
            self._save()
            append_trace({'timestamp': utc(), 'tool': 'workflow_graphs', 'event': 'node_end', 'run_id': self.run_id, 'node_id': nid, 'ok': success,
                          'attempts': len(nstate['attempts']), 'child_workflow': child_ident, 'code_run_id': (((child_output or {}).get('code_run') or {}).get('run_id'))})
            if success and node.get('restart_boundary'):
                if not self._resume_restart_if_needed(nid, nstate):
                    return self._finish()
            if stop_after == nid:
                self.state['status'] = 'PAUSED'; self.state['paused_after'] = nid; self._save(); return self._final_result()
        return self._finish()

    def _finish(self) -> dict[str, Any]:
        failed = [nid for nid, st in self.state.get('nodes', {}).items() if st.get('status') == 'FAILED']
        unrecovered = [nid for nid in failed if nid not in self.state.get('recovered_failures', {})]
        if unrecovered:
            status = 'FAIL'; ok = False
        elif failed:
            status = 'RECOVERED'; ok = True
        else:
            status = 'PASS'; ok = True
        ended_at = utc()
        try:
            duration_ms = round((datetime.fromisoformat(ended_at) - datetime.fromisoformat(self.state['started_at'])).total_seconds() * 1000, 2)
        except Exception:
            duration_ms = round((time.monotonic() - self.started_monotonic) * 1000, 2)
        self.state['status'] = status; self.state['ok'] = ok; self.state['ended_at'] = ended_at; self.state['duration_ms'] = duration_ms; self._save()
        result = self._final_result(); safe_write_json(self.result_path, result)
        append_trace({'timestamp': utc(), 'tool': 'workflow_graphs', 'event': 'graph_run_end', 'run_id': self.run_id, **self.ident,
                      'ok': ok, 'status': status, 'duration_ms': duration_ms, 'nodes_total': len(self.nodes), 'child_invocations': len(self.state.get('invocations', [])),
                      'recovered_failures': self.state.get('recovered_failures', {})})
        return result

    def _final_result(self) -> dict[str, Any]:
        code_runs = []
        changed_files: set[str] = set()
        child_result_paths = []
        rolled_back: set[str] = set()
        retries = 0
        raw_shell_steps = 0; total_code_steps = 0
        for inv in self.state.get('invocations', []):
            cr = inv.get('code_run') or {}
            rid = cr.get('run_id')
            if rid:
                code_runs.append(rid)
            rp = cr.get('result_path')
            if rp and pathlib.Path(rp).exists():
                child_result_paths.append(rp)
                try:
                    full = json.loads(pathlib.Path(rp).read_text())
                    changed_files.update(full.get('changed_files', [])); rolled_back.update(str(x) for x in full.get('rolled_back', [])); retries += int(full.get('retries', 0)); total_code_steps += int(full.get('steps_total', 0))
                    for st in full.get('steps', []):
                        if st.get('op') == 'command' and (st.get('result') or {}).get('command_sha256'):
                            raw_shell_steps += 1
                except Exception:
                    pass
        return {'version': VERSION, 'run_id': self.run_id, 'graph': self.ident, 'parameters': self.safe_params,
                'ok': self.state.get('ok'), 'status': self.state.get('status'), 'duration_ms': self.state.get('duration_ms'), 'nodes_total': len(self.nodes),
                'nodes': self.state.get('nodes', {}), 'child_invocations': len(self.state.get('invocations', [])),
                'code_mode_invocations': len(code_runs), 'code_runs': code_runs, 'child_result_paths': child_result_paths,
                'changed_files': sorted(changed_files), 'rolled_back': sorted(rolled_back), 'retries': retries, 'recovered_failures': self.state.get('recovered_failures', {}),
                'restart_checkpoints': self.state.get('restart_checkpoints', []), 'resume_count': int(self.state.get('resume_count', 0)),
                'raw_shell_command_steps': raw_shell_steps, 'underlying_code_mode_steps': total_code_steps,
                'raw_shell_step_share': round(raw_shell_steps / total_code_steps, 3) if total_code_steps else 0,
                'state_path': str(self.state_path), 'result_path': str(self.result_path), 'graph_path': str(self.graph_path)}


def list_graphs() -> list[dict[str, Any]]:
    out = []
    if not REGISTRY.exists():
        return out
    for d in sorted(x for x in REGISTRY.iterdir() if x.is_dir()):
        current = (d / 'CURRENT').read_text().strip() if (d / 'CURRENT').exists() else None
        for p in sorted(d.glob('*.json')):
            try:
                defn = json.loads(p.read_text()); ident = identity(defn)
                out.append(ident | {'description': defn.get('description', ''), 'active': defn.get('version') == current,
                                    'parameters': sorted((defn.get('parameters') or {}).keys()), 'nodes': len(defn.get('nodes') or []), 'path': str(p)})
            except Exception as exc:
                out.append({'name': d.name, 'path': str(p), 'error': f'{type(exc).__name__}: {exc}'})
    return out


def parse_json_arg(text: str | None, file_path: str | None) -> dict[str, Any]:
    if text and file_path:
        fail('use only one of --params-json/--params-file')
    if file_path:
        value = json.loads(pathlib.Path(file_path).read_text())
    elif text:
        value = json.loads(text)
    else:
        value = {}
    if not isinstance(value, dict):
        fail('JSON argument must be an object')
    return value


def selftest() -> dict[str, Any]:
    import tempfile
    checks: list[tuple[str, bool]] = []
    old_registry, old_runs = globals()['REGISTRY'], globals()['RUN_ROOT']
    try:
        with tempfile.TemporaryDirectory(prefix='workflow-graphs-test-') as td:
            base = pathlib.Path(td); globals()['REGISTRY'] = base / 'registry'; globals()['RUN_ROOT'] = base / 'runs'
            target = base / 'x.txt'; target.write_text('A\n')
            good = {'name':'selftest-graph','version':'1','description':'selftest graph','parameters':{'path':{'type':'path','required':True,'absolute':True}},
                    'nodes':[{'id':'one','workflow':'exact-replace@1','depends_on':[],'params':{'path':{'$param':'path'},'old':'A','new':'B'}},
                             {'id':'two','workflow':'exact-replace@1','depends_on':['one'],'params':{'path':{'$param':'path'},'old':'B','new':'C'}}]}
            reg = register(good); checks.append(('register_identity', reg['sha256'] == sha(good)))
            try: preflight(good, {})
            except ValueError as e: checks.append(('missing_parent_parameter_rejected', 'missing required parameter' in str(e)))
            else: checks.append(('missing_parent_parameter_rejected', False))
            unknown = json.loads(json.dumps(good)); unknown['version'] = '2'; unknown['nodes'][0]['workflow'] = 'does-not-exist@1'
            try: preflight(unknown, {'path':str(target)})
            except ValueError as e: checks.append(('unknown_child_rejected', 'workflow not found' in str(e)))
            else: checks.append(('unknown_child_rejected', False))
            cyc = json.loads(json.dumps(good)); cyc['version']='3'; cyc['nodes'][0]['depends_on']=['two']
            try: validate_definition(cyc)
            except ValueError as e: checks.append(('cycle_rejected', 'cycle' in str(e)))
            else: checks.append(('cycle_rejected', False))
            bound = json.loads(json.dumps(good)); bound['version']='4'; bound['limits']={'max_invocations':1}
            try: validate_definition(bound)
            except ValueError as e: checks.append(('invocation_bound', 'exceeds max_invocations' in str(e)))
            else: checks.append(('invocation_bound', False))
            r = GraphRunner(good, {'path':str(target)}).run(); checks.append(('sequential_children', r['ok'] and target.read_text()=='C\n' and r['child_invocations']==2))
            target.write_text('A\n'); paused = GraphRunner(good, {'path':str(target)}); p = paused.run(stop_after='one'); rr = GraphRunner(json.loads(paused.graph_path.read_text()), json.loads(paused.params_path.read_text()), run_dir=paused.run_dir).run(); checks.append(('checkpoint_resume', p['status']=='PAUSED' and rr['ok'] and rr['resume_count']==1 and target.read_text()=='C\n'))
            fail_target = base/'fail.txt'; fail_target.write_text('X\n'); recovery_target = base/'recover.txt'; recovery_target.write_text('R\n')
            recovery = {'name':'recovery','version':'1','description':'recovery test','parameters':{},'nodes':[
                {'id':'fail','workflow':'exact-replace@1','depends_on':[],'params':{'path':str(fail_target),'old':'NOPE','new':'Y'}},
                {'id':'recover','workflow':'exact-replace@1','depends_on':['fail'],'run_if':'failure','recovers':['fail'],'params':{'path':str(recovery_target),'old':'R','new':'OK'}}]}
            rec = GraphRunner(recovery, {}).run(); checks.append(('failure_recovery_explicit', rec['ok'] and rec['status']=='RECOVERED' and rec['recovered_failures'].get('fail')=='recover' and recovery_target.read_text()=='OK\n'))
    finally:
        globals()['REGISTRY'], globals()['RUN_ROOT'] = old_registry, old_runs
    return {'version':VERSION,'passed':sum(1 for _,ok in checks if ok),'total':len(checks),'checks':[{'name':n,'ok':ok} for n,ok in checks]}


def compact(result: dict[str, Any]) -> dict[str, Any]:
    keys = ('version','run_id','graph','ok','status','duration_ms','nodes_total','child_invocations','code_mode_invocations','retries','changed_files','rolled_back','recovered_failures','restart_checkpoints','resume_count','raw_shell_command_steps','underlying_code_mode_steps','raw_shell_step_share','state_path','result_path')
    return {k: result.get(k) for k in keys}


def main() -> None:
    ap = argparse.ArgumentParser(description='Versioned bounded workflow graph / lifecycle transaction runner for Optiplex_Lab')
    ap.add_argument('--selftest', action='store_true')
    sub = ap.add_subparsers(dest='cmd')
    p=sub.add_parser('register'); p.add_argument('definition'); p.add_argument('--no-activate', action='store_true')
    sub.add_parser('list')
    p=sub.add_parser('show'); p.add_argument('graph')
    p=sub.add_parser('preflight'); p.add_argument('graph'); p.add_argument('--params-json'); p.add_argument('--params-file')
    p=sub.add_parser('run'); p.add_argument('graph'); p.add_argument('--params-json'); p.add_argument('--params-file'); p.add_argument('--stop-after')
    p=sub.add_parser('resume'); p.add_argument('run_ref')
    args = ap.parse_args()
    try:
        if args.selftest:
            out=selftest(); print(json.dumps(out,indent=2)); raise SystemExit(0 if out['passed']==out['total'] else 1)
        if args.cmd == 'register': out=register(json.loads(pathlib.Path(args.definition).read_text()), activate=not args.no_activate)
        elif args.cmd == 'list': out={'version':VERSION,'graphs':list_graphs()}
        elif args.cmd == 'show':
            d,p=load_definition(args.graph); out={'identity':identity(d),'path':str(p),'definition':d}
        elif args.cmd == 'preflight':
            d,_=load_definition(args.graph); out=preflight(d,parse_json_arg(args.params_json,args.params_file))
        elif args.cmd == 'run':
            d,_=load_definition(args.graph); r=GraphRunner(d,parse_json_arg(args.params_json,args.params_file)).run(stop_after=args.stop_after); out=compact(r)
        elif args.cmd == 'resume':
            rd=pathlib.Path(args.run_ref); rd = rd if rd.is_dir() else RUN_ROOT / args.run_ref
            if not rd.exists(): fail(f'graph run not found: {args.run_ref}')
            d=json.loads((rd/'graph.json').read_text()); supplied=json.loads((rd/'inputs.json').read_text()); r=GraphRunner(d,supplied,run_dir=rd).run(); out=compact(r)
        else: ap.error('command required')
        print(json.dumps(out,indent=2,sort_keys=True))
        if args.cmd in {'run','resume'} and out.get('status') == 'FAIL': raise SystemExit(1)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({'ok':False,'error':f'{type(exc).__name__}: {exc}'},indent=2),file=sys.stderr); raise SystemExit(2)

if __name__ == '__main__':
    main()
