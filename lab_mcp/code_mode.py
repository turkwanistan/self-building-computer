#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone
from typing import Any

ROOT = pathlib.Path('/var/lib/optiplex-lab/code-runs')
TRACE = pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl')
SELF_UPDATE = '/usr/local/sbin/optiplex-lab-self-update'
ROLLBACK = '/usr/local/sbin/optiplex-lab-rollback'
VERSION = 'gen3-code-mode-r1'
PREVIEW = 1200


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_text(text: str) -> str:
    return sha_bytes(text.encode())


def safe_id(value: str) -> str:
    out = ''.join(c if c.isalnum() or c in '._-' else '_' for c in value)
    return out[:80] or 'step'


def append_trace(rec: dict[str, Any]) -> None:
    TRACE.parent.mkdir(parents=True, exist_ok=True)
    with TRACE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(rec, separators=(',', ':'), default=str) + '\n')


def compact_preview(data: bytes) -> str:
    text = data.decode('utf-8', errors='replace')
    if len(text) <= PREVIEW:
        return text
    return text[: PREVIEW * 2 // 3] + '\n...[artifact retained locally]...\n' + text[-PREVIEW // 3 :]


def run_cmd(command: str, cwd: str, timeout: int) -> tuple[int, bytes, bytes, float]:
    started = time.monotonic()
    try:
        p = subprocess.run(['/bin/bash', '-lc', command], cwd=cwd, capture_output=True, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b''
        err = (exc.stderr or b'') + f'\nTIMEOUT after {timeout}s'.encode()
        return 124, out, err, time.monotonic() - started


def run_argv(argv: list[str], cwd: str, timeout: int) -> tuple[int, bytes, bytes, float]:
    started = time.monotonic()
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr, time.monotonic() - started
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout or b''
        err = (exc.stderr or b'') + f'\nTIMEOUT after {timeout}s'.encode()
        return 124, out, err, time.monotonic() - started


class Runner:
    def __init__(self, wf: dict[str, Any], workflow_path: pathlib.Path):
        self.wf = wf
        self.workflow_path = workflow_path
        self.run_id = f"cm_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
        self.run_dir = ROOT / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.default_cwd = str(wf.get('cwd') or '/root')
        self.rollback_on_failure = bool(wf.get('rollback_on_failure', True))
        self.stop_on_failure = bool(wf.get('stop_on_failure', True))
        self.steps: list[dict[str, Any]] = []
        self.rollback_actions: list[tuple[str, Any]] = []
        self.changed_files: set[str] = set()
        self.retries = 0
        self.restart_scheduled = False
        self.started = time.monotonic()
        self.workflow_sha256 = sha_bytes(workflow_path.read_bytes())
        self.reusable = wf.get('_reusable') if isinstance(wf.get('_reusable'), dict) else None
        self.parameters = wf.get('_parameters') if isinstance(wf.get('_parameters'), dict) else None
        shutil.copy2(workflow_path, self.run_dir / 'workflow.json')

    def trace(self, event: str, **extra: Any) -> None:
        append_trace({'timestamp': utc(), 'tool': 'code_mode', 'event': event, 'run_id': self.run_id,
                      'workflow_sha256': self.workflow_sha256} | extra)

    def artifact(self, step_id: str, suffix: str, data: bytes) -> str:
        p = self.run_dir / f'{safe_id(step_id)}.{suffix}'
        p.write_bytes(data)
        return str(p)

    def rollback(self) -> list[str]:
        done: list[str] = []
        for kind, payload in reversed(self.rollback_actions):
            try:
                if kind == 'restore_file':
                    path, original, existed = payload
                    p = pathlib.Path(path)
                    if existed:
                        p.write_bytes(original)
                    else:
                        p.unlink(missing_ok=True)
                    done.append(path)
                elif kind == 'git_reverse':
                    cwd, patch_path = payload
                    r = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(patch_path)], cwd=cwd, capture_output=True, timeout=20)
                    if r.returncode == 0:
                        done.append(f'git:{cwd}')
            except Exception:
                pass
        return done

    def op_inspect(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        p = pathlib.Path(step['path'])
        data = p.read_bytes()
        max_preview = max(0, min(int(step.get('preview_bytes', 600)), 4000))
        preview = data[:max_preview]
        art = self.artifact(sid, 'inspect', data) if step.get('retain', False) else None
        return {'path': str(p), 'bytes': len(data), 'sha256': sha_bytes(data),
                'preview': preview.decode('utf-8', errors='replace'), 'artifact': art}

    def op_copy(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        src = pathlib.Path(step['src']); dst = pathlib.Path(step['dst'])
        existed = dst.exists(); original = dst.read_bytes() if existed else b''
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        self.rollback_actions.append(('restore_file', (str(dst), original, existed)))
        self.changed_files.add(str(dst))
        return {'src': str(src), 'dst': str(dst), 'sha256': sha_bytes(dst.read_bytes())}

    def op_exact_replace(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        p = pathlib.Path(step['path'])
        old = str(step['old']); new = str(step['new'])
        expected = int(step.get('expected_matches', 1))
        text = p.read_text(encoding='utf-8')
        count = text.count(old)
        if count != expected:
            raise RuntimeError(f'context mismatch: expected {expected} matches, found {count}')
        new_text = text.replace(old, new, expected)
        diff = ''.join(difflib.unified_diff(text.splitlines(True), new_text.splitlines(True), fromfile=str(p), tofile=str(p)))
        diff_path = self.artifact(sid, 'diff', diff.encode())
        if step.get('preview_only', False):
            return {'path': str(p), 'matches': count, 'preview_only': True, 'diff': diff_path,
                    'diff_preview': diff[:PREVIEW]}
        original = p.read_bytes()
        backup = self.artifact(sid, 'backup', original)
        tmp = p.with_name(p.name + f'.codemode-{uuid.uuid4().hex[:8]}')
        tmp.write_text(new_text, encoding='utf-8')
        os.chmod(tmp, p.stat().st_mode & 0o7777)
        tmp.replace(p)
        self.rollback_actions.append(('restore_file', (str(p), original, True)))
        self.changed_files.add(str(p))
        return {'path': str(p), 'matches': count, 'backup': backup, 'diff': diff_path,
                'sha256': sha_bytes(p.read_bytes()), 'diff_preview': diff[:PREVIEW]}

    def op_git_patch(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        cwd = str(step.get('cwd') or self.default_cwd)
        patch = str(step.get('patch') or '')
        if not patch and step.get('patch_file'):
            patch = pathlib.Path(step['patch_file']).read_text()
        if not patch:
            raise RuntimeError('patch or patch_file is required')
        pp = self.run_dir / f'{safe_id(sid)}.patch'
        pp.write_text(patch)
        check = subprocess.run(['git', 'apply', '--check', '--whitespace=nowarn', str(pp)], cwd=cwd, capture_output=True, timeout=20)
        if check.returncode != 0:
            raise RuntimeError('patch check failed: ' + check.stderr.decode(errors='replace')[:500])
        before = subprocess.run(['git', 'diff', '--binary'], cwd=cwd, capture_output=True, timeout=20).stdout
        r = subprocess.run(['git', 'apply', '--whitespace=nowarn', str(pp)], cwd=cwd, capture_output=True, timeout=20)
        if r.returncode != 0:
            raise RuntimeError('patch apply failed: ' + r.stderr.decode(errors='replace')[:500])
        after = subprocess.run(['git', 'diff', '--binary'], cwd=cwd, capture_output=True, timeout=20).stdout
        self.artifact(sid, 'git-before.diff', before)
        diff_path = self.artifact(sid, 'git-after.diff', after)
        self.rollback_actions.append(('git_reverse', (cwd, pp)))
        return {'cwd': cwd, 'patch_sha256': sha_text(patch), 'diff': diff_path,
                'diff_preview': compact_preview(after)}

    def op_command(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        has_command = 'command' in step
        has_argv = 'argv' in step
        if has_command == has_argv:
            raise RuntimeError('command step requires exactly one of command or argv')
        command = str(step['command']) if has_command else None
        argv = [str(x) for x in step['argv']] if has_argv else None
        if argv is not None and not argv:
            raise RuntimeError('argv must not be empty')
        cwd = str(step.get('cwd') or self.default_cwd)
        timeout = max(1, min(int(step.get('timeout', 120)), 3600))
        retries = max(0, min(int(step.get('retries', 0)), 5))
        delay = max(0.0, min(float(step.get('retry_delay_s', 0.2)), 30.0))
        expected = step.get('expect_exit', 0)
        expected_set = {int(x) for x in expected} if isinstance(expected, list) else {int(expected)}
        attempts = []
        for attempt in range(retries + 1):
            if argv is not None:
                rc, out, err, dur = run_argv(argv, cwd, timeout)
            else:
                rc, out, err, dur = run_cmd(str(command), cwd, timeout)
            out_path = self.artifact(sid + f'-a{attempt+1}', 'stdout', out)
            err_path = self.artifact(sid + f'-a{attempt+1}', 'stderr', err)
            attempts.append({'attempt': attempt + 1, 'exit_code': rc, 'duration_ms': round(dur*1000,2),
                             'stdout_bytes': len(out), 'stderr_bytes': len(err), 'stdout': out_path, 'stderr': err_path})
            if rc in expected_set:
                result = {'exit_code': rc, 'attempts': attempts, 'retries_used': attempt,
                          'stdout_preview': compact_preview(out), 'stderr_preview': compact_preview(err)}
                if argv is not None:
                    result.update({'argv_sha256': sha_text(json.dumps(argv, separators=(',', ':'))),
                                   'argv_count': len(argv)})
                else:
                    result['command_sha256'] = sha_text(str(command))
                return result
            if attempt < retries:
                self.retries += 1
                time.sleep(delay)
        raise RuntimeError(f'command exit {attempts[-1]["exit_code"]}, expected {sorted(expected_set)}')

    def op_assert_file(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        p = pathlib.Path(step['path']); text = p.read_text(errors='replace')
        needle = str(step['contains'])
        should = bool(step.get('present', True))
        found = needle in text
        if found != should:
            raise RuntimeError(f'assert_file failed present={found}, expected={should}')
        return {'path': str(p), 'present': found, 'needle_sha256': sha_text(needle)}

    def op_service(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        action = str(step['action']); name = str(step['name'])
        if action not in {'start','stop','restart','status','enable','disable'}:
            raise RuntimeError('unsupported service action')
        p = subprocess.run(['systemctl', action, name], capture_output=True, timeout=60)
        out = p.stdout + p.stderr
        self.artifact(sid, 'service.log', out)
        if p.returncode != int(step.get('expect_exit', 0)):
            raise RuntimeError(f'systemctl {action} {name} rc={p.returncode}: {compact_preview(out)}')
        return {'action': action, 'name': name, 'exit_code': p.returncode, 'preview': compact_preview(out)}

    def op_job(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        has_command = 'command' in step
        has_argv = 'argv' in step
        if has_command == has_argv:
            raise RuntimeError('job step requires exactly one of command or argv')
        command = str(step['command']) if has_command else None
        argv = [str(x) for x in step['argv']] if has_argv else None
        if argv is not None and not argv:
            raise RuntimeError('argv must not be empty')
        cwd = str(step.get('cwd') or self.default_cwd)
        unit = f"optiplex-lab-cm-{safe_id(sid).lower()}-{uuid.uuid4().hex[:6]}"
        log = self.run_dir / f'{safe_id(sid)}.job.log'
        rendered = shlex.join(argv) if argv is not None else str(command)
        wrapped = f'exec >>{shlex.quote(str(log))} 2>&1\ncd {shlex.quote(cwd)}\n{rendered}'
        p = subprocess.run(['systemd-run','--quiet',f'--unit={unit}','--property=Type=exec','/bin/bash','-lc',wrapped], capture_output=True, timeout=15)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode(errors='replace')[:500] or 'systemd-run failed')
        wait = bool(step.get('wait', True))
        timeout = max(1, min(int(step.get('timeout',120)),3600))
        invocation = ({'argv_sha256': sha_text(json.dumps(argv, separators=(',', ':'))), 'argv_count': len(argv)}
                      if argv is not None else {'command_sha256': sha_text(str(command))})
        if not wait:
            return {'unit': unit, 'state': 'started', 'log': str(log)} | invocation
        deadline = time.monotonic()+timeout; active=''; status=''
        while time.monotonic() < deadline:
            q = subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','ExecMainStatus'], capture_output=True, text=True, timeout=10)
            vals = dict(line.split('=',1) for line in q.stdout.splitlines() if '=' in line)
            active = vals.get('ActiveState',''); status = vals.get('ExecMainStatus','')
            if active in {'inactive','failed'}:
                break
            time.sleep(0.1)
        rc = int(status or 0)
        data = log.read_bytes() if log.exists() else b''
        if active not in {'inactive','failed'}:
            raise RuntimeError(f'job timeout unit={unit}')
        if rc != int(step.get('expect_exit',0)):
            raise RuntimeError(f'job rc={rc}: {compact_preview(data)}')
        return {'unit': unit, 'state': active, 'exit_code': rc, 'log': str(log),
                'bytes': len(data), 'preview': compact_preview(data)} | invocation

    def op_self_update(self, step: dict[str, Any], sid: str) -> dict[str, Any]:
        candidate = str(step['candidate']); generation = str(step['generation'])
        if step is not self.wf['steps'][-1]:
            raise RuntimeError('self_update must be the final workflow step')
        p = subprocess.run([SELF_UPDATE, candidate, generation], capture_output=True, timeout=15)
        data = p.stdout + p.stderr
        self.artifact(sid, 'self-update.log', data)
        if p.returncode != 0:
            raise RuntimeError(f'self-update rc={p.returncode}: {compact_preview(data)}')
        self.restart_scheduled = True
        return {'exit_code': p.returncode, 'restart_scheduled': True, 'preview': compact_preview(data),
                'candidate_sha256': sha_bytes(pathlib.Path(candidate).read_bytes()), 'generation': generation}

    def execute_step(self, step: dict[str, Any], index: int) -> dict[str, Any]:
        sid = safe_id(str(step.get('id') or f'step-{index+1}'))
        op = str(step.get('op') or '')
        if op not in {'inspect','copy','exact_replace','git_patch','command','assert_file','service','job','self_update'}:
            raise RuntimeError(f'unsupported op: {op}')
        fn = getattr(self, f'op_{op}')
        started = time.monotonic()
        self.trace('step_start', step_id=sid, step_index=index, op=op,
                   args={'path': step.get('path'), 'cwd': step.get('cwd'),
                         'command_sha256': sha_text(str(step.get('command'))) if step.get('command') else None,
                         'argv_sha256': sha_text(json.dumps(step.get('argv'), separators=(',', ':'))) if step.get('argv') else None})
        try:
            result = fn(step, sid)
            ok = True; error = None
        except Exception as exc:
            result = {}; ok = False; error = f'{type(exc).__name__}: {exc}'
        duration = round((time.monotonic()-started)*1000,2)
        rec = {'id': sid, 'index': index, 'op': op, 'ok': ok, 'duration_ms': duration, 'result': result}
        if error: rec['error'] = error
        self.trace('step_end', step_id=sid, step_index=index, op=op, ok=ok, duration_ms=duration,
                   retries_used=int(result.get('retries_used',0) or 0), error_class=(error.split(':',1)[0] if error else None))
        return rec

    def run(self) -> dict[str, Any]:
        name = str(self.wf.get('name') or 'workflow')
        self.trace('run_start', name=name, steps=len(self.wf.get('steps') or []), version=VERSION,
                   reusable_workflow=self.reusable)
        failed = False
        for idx, step in enumerate(self.wf.get('steps') or []):
            if failed and self.stop_on_failure:
                self.steps.append({'id': safe_id(str(step.get('id') or f'step-{idx+1}')), 'index': idx,
                                   'op': step.get('op'), 'ok': False, 'skipped': True, 'duration_ms': 0})
                continue
            rec = self.execute_step(step, idx)
            self.steps.append(rec)
            if not rec['ok']:
                failed = True
        rolled_back: list[str] = []
        if failed and self.rollback_on_failure:
            rolled_back = self.rollback()
        duration = round((time.monotonic()-self.started)*1000,2)
        result = {
            'version': VERSION, 'run_id': self.run_id, 'name': name, 'ok': not failed,
            'started_at': utc(), 'duration_ms': duration,
            'steps_total': len(self.steps), 'steps_succeeded': sum(1 for s in self.steps if s.get('ok')),
            'steps_failed': sum(1 for s in self.steps if (not s.get('ok')) and not s.get('skipped')),
            'steps_skipped': sum(1 for s in self.steps if s.get('skipped')),
            'retries': self.retries, 'changed_files': sorted(self.changed_files),
            'rolled_back': rolled_back, 'restart_scheduled': self.restart_scheduled,
            'workflow_sha256': self.workflow_sha256, 'run_dir': str(self.run_dir), 'steps': self.steps,
        }
        if self.reusable is not None:
            result['reusable_workflow'] = self.reusable
        if self.parameters is not None:
            result['parameters'] = self.parameters
        result_path = self.run_dir / 'result.json'; result_path.write_text(json.dumps(result, indent=2) + '\n')
        result['result_path'] = str(result_path)
        self.trace('run_end', ok=not failed, duration_ms=duration, steps_total=len(self.steps),
                   steps_failed=result['steps_failed'], steps_skipped=result['steps_skipped'], retries=self.retries,
                   changed_files=len(self.changed_files), rollback_count=len(rolled_back), restart_scheduled=self.restart_scheduled,
                   result_path=str(result_path))
        return result


def selftest() -> dict[str, Any]:
    checks=[]
    with tempfile.TemporaryDirectory(prefix='code-mode-test-') as td:
        d=pathlib.Path(td); p=d/'a.txt'; p.write_text('alpha\nbeta\n')
        wf={'name':'selftest','cwd':td,'rollback_on_failure':True,'steps':[
            {'id':'replace','op':'exact_replace','path':str(p),'old':'beta','new':'BETA'},
            {'id':'assert','op':'assert_file','path':str(p),'contains':'BETA'},
            {'id':'retry','op':'command','cwd':td,'command':"test -f marker || (touch marker; exit 7)",'retries':1,'expect_exit':0},
        ]}
        wp=d/'wf.json'; wp.write_text(json.dumps(wf))
        r=Runner(wf,wp).run(); checks.append(('basic_replace_retry',r['ok'] and r['retries']==1 and 'BETA' in p.read_text()))
        bad={'name':'mismatch','cwd':td,'steps':[{'id':'bad','op':'exact_replace','path':str(p),'old':'NOPE','new':'x'}]}
        bp=d/'bad.json'; bp.write_text(json.dumps(bad)); br=Runner(bad,bp).run(); checks.append(('context_mismatch_fails',not br['ok']))
        repo=d/'repo'; repo.mkdir(); subprocess.run(['git','init','-q'],cwd=repo); (repo/'x.txt').write_text('one\n')
        patch='diff --git a/x.txt b/x.txt\nindex 5626abf..f719efd 100644\n--- a/x.txt\n+++ b/x.txt\n@@ -1 +1 @@\n-one\n+two\n'
        gw={'name':'gitpatch','cwd':str(repo),'steps':[{'id':'patch','op':'git_patch','cwd':str(repo),'patch':patch}]}
        gp=d/'git.json'; gp.write_text(json.dumps(gw)); gr=Runner(gw,gp).run(); checks.append(('git_patch',gr['ok'] and (repo/'x.txt').read_text()=='two\n'))
        large={'name':'large','cwd':td,'steps':[{'id':'large','op':'command','command':"python3 -c \"print('x'*200000)\""}]}
        lp=d/'large.json'; lp.write_text(json.dumps(large)); lr=Runner(large,lp).run(); st=lr['steps'][0]['result']; checks.append(('large_output_artifact',lr['ok'] and st['attempts'][0]['stdout_bytes']>100000))
        argv_wf={'name':'argv','cwd':td,'steps':[{'id':'argv','op':'command','argv':['python3','-c','import sys; assert sys.argv[1] == \"a b;$(x)\"','a b;$(x)']}]}
        ap=d/'argv.json'; ap.write_text(json.dumps(argv_wf)); ar=Runner(argv_wf,ap).run(); checks.append(('argv_literal_parameter_safety',ar['ok']))
    out={'version':VERSION,'passed':sum(1 for _,ok in checks if ok),'total':len(checks),'checks':[{'name':n,'ok':ok} for n,ok in checks]}
    return out


def main() -> None:
    ap=argparse.ArgumentParser(description='Auditable guest-local orchestration runner')
    ap.add_argument('workflow', nargs='?')
    ap.add_argument('--selftest', action='store_true')
    args=ap.parse_args()
    if args.selftest:
        out=selftest(); print(json.dumps(out,indent=2)); raise SystemExit(0 if out['passed']==out['total'] else 1)
    if not args.workflow:
        ap.error('workflow path required')
    wp=pathlib.Path(args.workflow)
    wf=json.loads(wp.read_text())
    if not isinstance(wf.get('steps'), list):
        raise SystemExit('workflow.steps must be a list')
    r=Runner(wf,wp).run()
    compact={k:r[k] for k in ('version','run_id','name','ok','duration_ms','steps_total','steps_succeeded','steps_failed','steps_skipped','retries','changed_files','rolled_back','restart_scheduled','result_path')}
    print(json.dumps(compact,indent=2))
    raise SystemExit(0 if r['ok'] else 1)

if __name__=='__main__':
    main()
