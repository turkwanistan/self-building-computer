#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

VERSION = 'gen3-workflow-skills-r1'
REGISTRY = pathlib.Path('/var/lib/optiplex-lab/workflows')
RUN_ROOT = pathlib.Path('/var/lib/optiplex-lab/workflow-runs')
CODE_RUNS = pathlib.Path('/var/lib/optiplex-lab/code-runs')
TRACE = pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl')
CODE_MODE = pathlib.Path('/opt/optiplex-lab/code_mode.py')
NAME_RE = re.compile(r'^[A-Za-z0-9._-]{1,80}$')
SUPPORTED_TYPES = {'str', 'path', 'int', 'float', 'bool', 'enum', 'list[str]'}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sha(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical_bytes(value)
    return hashlib.sha256(data).hexdigest()


def append_trace(rec: dict[str, Any]) -> None:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    with TRACE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, separators=(',', ':'), default=str) + '\n')


def fail(message: str) -> None:
    raise ValueError(message)


def validate_name(value: str, label: str) -> str:
    if not NAME_RE.fullmatch(value):
        fail(f'invalid {label}: {value!r}')
    return value


def validate_definition(defn: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(defn, dict):
        fail('definition must be an object')
    name = validate_name(str(defn.get('name') or ''), 'workflow name')
    version = validate_name(str(defn.get('version') or ''), 'workflow version')
    if not isinstance(defn.get('description'), str) or not defn['description'].strip():
        fail('description is required')
    params = defn.get('parameters', {})
    if not isinstance(params, dict):
        fail('parameters must be an object')
    for pname, spec in params.items():
        validate_name(str(pname), 'parameter name')
        if not isinstance(spec, dict):
            fail(f'parameter {pname} spec must be an object')
        ptype = str(spec.get('type') or '')
        if ptype not in SUPPORTED_TYPES:
            fail(f'parameter {pname} has unsupported type {ptype!r}')
        if ptype == 'enum':
            choices = spec.get('choices')
            if not isinstance(choices, list) or not choices:
                fail(f'parameter {pname} enum requires non-empty choices')
        if 'default' in spec:
            validate_value(pname, spec, spec['default'])
    workflow = defn.get('workflow')
    if not isinstance(workflow, dict) or not isinstance(workflow.get('steps'), list) or not workflow['steps']:
        fail('workflow.steps must be a non-empty list')
    if any(not isinstance(step, dict) for step in workflow['steps']):
        fail('every workflow step must be an object')
    for step in workflow['steps']:
        if step.get('op') not in {'inspect','copy','exact_replace','git_patch','command','assert_file','service','job','self_update'}:
            fail(f"unsupported workflow op: {step.get('op')!r}")
    return {'name': name, 'version': version}


def validate_value(name: str, spec: dict[str, Any], value: Any) -> Any:
    ptype = spec['type']
    if ptype in {'str', 'path', 'enum'}:
        if not isinstance(value, str):
            fail(f'parameter {name} must be {ptype}')
        if '\x00' in value:
            fail(f'parameter {name} contains NUL')
        if ptype == 'enum' and value not in spec['choices']:
            fail(f'parameter {name} must be one of {spec["choices"]}')
        if 'pattern' in spec and not re.fullmatch(str(spec['pattern']), value):
            fail(f'parameter {name} does not match required pattern')
        if ptype == 'path' and spec.get('absolute') and not os.path.isabs(value):
            fail(f'parameter {name} must be an absolute path')
    elif ptype == 'int':
        if isinstance(value, bool) or not isinstance(value, int):
            fail(f'parameter {name} must be int')
    elif ptype == 'float':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail(f'parameter {name} must be float')
        value = float(value)
    elif ptype == 'bool':
        if not isinstance(value, bool):
            fail(f'parameter {name} must be bool')
    elif ptype == 'list[str]':
        if not isinstance(value, list) or any(not isinstance(x, str) or '\x00' in x for x in value):
            fail(f'parameter {name} must be list[str]')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 'min' in spec and value < spec['min']:
            fail(f'parameter {name} is below minimum {spec["min"]}')
        if 'max' in spec and value > spec['max']:
            fail(f'parameter {name} is above maximum {spec["max"]}')
    return value


def resolve_params(defn: dict[str, Any], supplied: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(supplied, dict):
        fail('parameters must be a JSON object')
    specs = defn.get('parameters', {})
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
            value = validate_value(name, spec, value)
        resolved[name] = value
        if spec.get('sensitive'):
            raw = canonical_bytes(value)
            safe[name] = {'type': spec['type'], 'redacted': True, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        else:
            safe[name] = {'type': spec['type'], 'value': value}
    return resolved, safe


def substitute(node: Any, params: dict[str, Any]) -> Any:
    if isinstance(node, dict):
        if set(node) == {'$param'}:
            name = str(node['$param'])
            if name not in params:
                fail(f'unknown template parameter: {name}')
            return params[name]
        if set(node) == {'$path_join'}:
            parts = node['$path_join']
            if not isinstance(parts, list) or not parts:
                fail('$path_join requires a non-empty list')
            resolved = [substitute(x, params) for x in parts]
            if any(not isinstance(x, str) for x in resolved):
                fail('$path_join parts must resolve to strings')
            return os.path.normpath(os.path.join(*resolved))
        if set(node) == {'$concat'}:
            parts = node['$concat']
            if not isinstance(parts, list) or not parts:
                fail('$concat requires a non-empty list')
            resolved = [substitute(x, params) for x in parts]
            return ''.join(str(x) for x in resolved)
        return {k: substitute(v, params) for k, v in node.items()}
    if isinstance(node, list):
        return [substitute(x, params) for x in node]
    return node


def registry_path(name: str, version: str) -> pathlib.Path:
    return REGISTRY / name / f'{version}.json'


def identity(defn: dict[str, Any]) -> dict[str, Any]:
    return {'name': defn['name'], 'version': defn['version'], 'sha256': sha(defn), 'compiler_version': VERSION}


def register(defn: dict[str, Any], activate: bool = True) -> dict[str, Any]:
    validate_definition(defn)
    ident = identity(defn)
    path = registry_path(defn['name'], defn['version'])
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = json.loads(path.read_text())
        if sha(existing) != ident['sha256']:
            fail(f'immutable workflow version already exists with different hash: {defn["name"]}@{defn["version"]}')
        state = 'already_registered'
    else:
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(defn, indent=2, sort_keys=True) + '\n')
        tmp.replace(path)
        state = 'registered'
    if activate:
        (path.parent / 'CURRENT').write_text(defn['version'] + '\n')
    append_trace({'timestamp': utc(), 'tool': 'workflow_skills', 'event': 'register', **ident, 'state': state})
    return ident | {'state': state, 'path': str(path), 'active': activate}


def load_definition(name_version: str) -> tuple[dict[str, Any], pathlib.Path]:
    if '@' in name_version:
        name, version = name_version.rsplit('@', 1)
    else:
        name = name_version
        current = REGISTRY / name / 'CURRENT'
        if not current.exists():
            fail(f'workflow not found or has no active version: {name}')
        version = current.read_text().strip()
    validate_name(name, 'workflow name'); validate_name(version, 'workflow version')
    path = registry_path(name, version)
    if not path.exists():
        fail(f'workflow not found: {name}@{version}')
    defn = json.loads(path.read_text())
    validate_definition(defn)
    return defn, path


def compile_workflow(name_version: str, supplied: dict[str, Any], out: pathlib.Path | None = None) -> dict[str, Any]:
    defn, source = load_definition(name_version)
    params, safe = resolve_params(defn, supplied)
    workflow = substitute(defn['workflow'], params)
    if not isinstance(workflow.get('steps'), list) or not workflow['steps']:
        fail('compiled workflow has no steps')
    ident = identity(defn)
    workflow['_reusable'] = ident | {'description': defn['description'], 'source': str(source), 'provenance': defn.get('provenance')}
    workflow['_parameters'] = safe
    if out is None:
        run_dir = RUN_ROOT / f"ws_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        run_dir.mkdir(parents=True, exist_ok=False)
        out = run_dir / 'compiled-workflow.json'
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(workflow, indent=2, sort_keys=True) + '\n')
    return {'identity': ident, 'parameters': safe, 'compiled_path': str(out), 'compiled_sha256': hashlib.sha256(out.read_bytes()).hexdigest(), 'workflow': workflow}


def load_code_mode():
    spec = importlib.util.spec_from_file_location('optiplex_lab_code_mode', CODE_MODE)
    if spec is None or spec.loader is None:
        fail('unable to load Code Mode')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_registered(name_version: str, supplied: dict[str, Any]) -> dict[str, Any]:
    compiled = compile_workflow(name_version, supplied)
    ident = compiled['identity']
    append_trace({'timestamp': utc(), 'tool': 'workflow_skills', 'event': 'invoke_start', **ident, 'parameters': compiled['parameters'], 'compiled_sha256': compiled['compiled_sha256']})
    mod = load_code_mode()
    result = mod.Runner(compiled['workflow'], pathlib.Path(compiled['compiled_path'])).run()
    append_trace({'timestamp': utc(), 'tool': 'workflow_skills', 'event': 'invoke_end', **ident, 'ok': result['ok'], 'code_run_id': result['run_id'], 'duration_ms': result['duration_ms'], 'steps_total': result['steps_total'], 'steps_failed': result['steps_failed'], 'retries': result['retries']})
    return {'workflow': ident, 'parameters': compiled['parameters'], 'compiled_path': compiled['compiled_path'], 'compiled_sha256': compiled['compiled_sha256'], 'code_run': result}


def replace_exact_scalars(node: Any, match: Any, replacement: Any) -> tuple[Any, int]:
    if isinstance(node, dict):
        total = 0; out = {}
        for k, v in node.items():
            nv, n = replace_exact_scalars(v, match, replacement); out[k] = nv; total += n
        return out, total
    if isinstance(node, list):
        total = 0; out = []
        for v in node:
            nv, n = replace_exact_scalars(v, match, replacement); out.append(nv); total += n
        return out, total
    if type(node) is type(match) and node == match:
        return replacement, 1
    return node, 0


def promote(run_ref: str, name: str, version: str, description: str, parameterize: dict[str, Any]) -> dict[str, Any]:
    run_dir = pathlib.Path(run_ref)
    if not run_dir.exists():
        run_dir = CODE_RUNS / run_ref
    result_path = run_dir / 'result.json'; workflow_path = run_dir / 'workflow.json'
    if not result_path.exists() or not workflow_path.exists():
        fail(f'Code Mode run not found: {run_ref}')
    result = json.loads(result_path.read_text())
    if not result.get('ok'):
        fail('only successful Code Mode runs can be promoted')
    workflow = json.loads(workflow_path.read_text())
    workflow.pop('_reusable', None); workflow.pop('_parameters', None)
    specs: dict[str, Any] = {}
    counts: dict[str, int] = {}
    if not isinstance(parameterize, dict):
        fail('parameterize spec must be an object')
    for pname, raw_spec in parameterize.items():
        validate_name(str(pname), 'parameter name')
        if not isinstance(raw_spec, dict) or 'match' not in raw_spec or 'type' not in raw_spec:
            fail(f'parameterize.{pname} requires match and type')
        match = raw_spec['match']
        spec = {k: v for k, v in raw_spec.items() if k != 'match'}
        spec.setdefault('required', 'default' not in spec)
        workflow, count = replace_exact_scalars(workflow, match, {'$param': pname})
        if count == 0:
            fail(f'parameterize.{pname} matched no exact scalar values')
        specs[pname] = spec; counts[pname] = count
    defn = {'name': name, 'version': version, 'description': description, 'parameters': specs, 'workflow': workflow,
            'provenance': {'promoted_from_code_run': result.get('run_id'), 'source_workflow_sha256': result.get('workflow_sha256'), 'source_result': str(result_path), 'promoted_at': utc(), 'parameterized_match_counts': counts}}
    reg = register(defn)
    return reg | {'provenance': defn['provenance'], 'definition_bytes': len(canonical_bytes(defn))}


def list_workflows() -> list[dict[str, Any]]:
    out = []
    if not REGISTRY.exists():
        return out
    for d in sorted(x for x in REGISTRY.iterdir() if x.is_dir()):
        current = (d / 'CURRENT').read_text().strip() if (d / 'CURRENT').exists() else None
        for p in sorted(d.glob('*.json')):
            try:
                defn = json.loads(p.read_text()); ident = identity(defn)
                out.append(ident | {'description': defn.get('description',''), 'active': defn.get('version') == current, 'parameters': sorted((defn.get('parameters') or {}).keys()), 'path': str(p)})
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
    checks = []
    old_registry, old_runs = globals()['REGISTRY'], globals()['RUN_ROOT']
    try:
        with tempfile.TemporaryDirectory(prefix='workflow-skills-test-') as td:
            globals()['REGISTRY'] = pathlib.Path(td) / 'registry'; globals()['RUN_ROOT'] = pathlib.Path(td) / 'runs'
            target = pathlib.Path(td) / 'x.txt'; target.write_text('old\n')
            defn = {'name':'selftest','version':'1','description':'self test','parameters':{'target':{'type':'path','required':True},'value':{'type':'str','default':'new'}},'workflow':{'name':'selftest','steps':[{'id':'edit','op':'exact_replace','path':{'$param':'target'},'old':'old','new':{'$param':'value'}},{'id':'argv','op':'command','argv':['python3','-c','import sys; assert sys.argv[1] == "a b;$(x)"','a b;$(x)']}]}}
            reg=register(defn); checks.append(('register_identity', reg['sha256']==sha(defn)))
            try: compile_workflow('selftest@1', {})
            except ValueError as e: checks.append(('missing_parameter_rejected','missing required parameter' in str(e)))
            else: checks.append(('missing_parameter_rejected',False))
            r=run_registered('selftest@1',{'target':str(target)}); checks.append(('run_parameterized',r['code_run']['ok'] and target.read_text()=='new\n'))
            listed=list_workflows(); checks.append(('discoverable',len(listed)==1 and listed[0]['active']))
    finally:
        globals()['REGISTRY'], globals()['RUN_ROOT'] = old_registry, old_runs
    return {'version':VERSION,'passed':sum(1 for _,ok in checks if ok),'total':len(checks),'checks':[{'name':n,'ok':ok} for n,ok in checks]}


def main() -> None:
    ap = argparse.ArgumentParser(description='Reusable audited workflow registry/compiler for Optiplex_Lab')
    ap.add_argument('--selftest', action='store_true')
    sub = ap.add_subparsers(dest='cmd')
    p=sub.add_parser('register'); p.add_argument('definition'); p.add_argument('--no-activate', action='store_true')
    sub.add_parser('list')
    p=sub.add_parser('show'); p.add_argument('workflow')
    p=sub.add_parser('compile'); p.add_argument('workflow'); p.add_argument('--params-json'); p.add_argument('--params-file'); p.add_argument('--out')
    p=sub.add_parser('run'); p.add_argument('workflow'); p.add_argument('--params-json'); p.add_argument('--params-file')
    p=sub.add_parser('promote'); p.add_argument('run_ref'); p.add_argument('--name', required=True); p.add_argument('--version', required=True); p.add_argument('--description', required=True); p.add_argument('--parameterize-json', default='{}')
    args=ap.parse_args()
    try:
        if args.selftest:
            out=selftest(); print(json.dumps(out,indent=2)); raise SystemExit(0 if out['passed']==out['total'] else 1)
        if args.cmd=='register': out=register(json.loads(pathlib.Path(args.definition).read_text()), activate=not args.no_activate)
        elif args.cmd=='list': out={'version':VERSION,'workflows':list_workflows()}
        elif args.cmd=='show':
            d,p=load_definition(args.workflow); out={'identity':identity(d),'path':str(p),'definition':d}
        elif args.cmd=='compile':
            out=compile_workflow(args.workflow,parse_json_arg(args.params_json,args.params_file),pathlib.Path(args.out) if args.out else None); out.pop('workflow',None)
        elif args.cmd=='run':
            r=run_registered(args.workflow,parse_json_arg(args.params_json,args.params_file)); cr=r.pop('code_run'); out=r|{'code_run':{k:cr[k] for k in ('version','run_id','name','ok','duration_ms','steps_total','steps_succeeded','steps_failed','steps_skipped','retries','changed_files','rolled_back','restart_scheduled','result_path')}}
        elif args.cmd=='promote': out=promote(args.run_ref,args.name,args.version,args.description,json.loads(args.parameterize_json))
        else: ap.error('command required')
        print(json.dumps(out,indent=2,sort_keys=True))
        if args.cmd == 'run' and not out['code_run']['ok']:
            raise SystemExit(1)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({'ok':False,'error':f'{type(exc).__name__}: {exc}'},indent=2),file=sys.stderr)
        raise SystemExit(2)

if __name__=='__main__':
    main()
