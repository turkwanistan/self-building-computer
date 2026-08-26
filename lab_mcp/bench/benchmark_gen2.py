#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, shutil, subprocess, tempfile, time, uuid
from datetime import datetime, timezone

CODE='/opt/optiplex-lab/code_mode.py'
OUT=pathlib.Path('/var/lib/optiplex-lab/benchmarks')
OUT.mkdir(parents=True, exist_ok=True)

def task(name, fn, manual_calls=None):
    t=time.monotonic()
    try:
        ok, detail = fn()
        rec={'name':name,'ok':bool(ok),'elapsed_ms':round((time.monotonic()-t)*1000,2),'detail':detail}
    except Exception as e:
        rec={'name':name,'ok':False,'elapsed_ms':round((time.monotonic()-t)*1000,2),'detail':f'{type(e).__name__}: {e}'}
    if manual_calls is not None:
        rec['manual_interactive_calls_estimate']=manual_calls
        rec['code_mode_invocations']=1
    return rec

def run_wf(name, steps, cwd='/root', rollback=True):
    wd=pathlib.Path(tempfile.mkdtemp(prefix='gen2wf-'))
    wp=wd/'workflow.json'
    wp.write_text(json.dumps({'name':name,'cwd':cwd,'rollback_on_failure':rollback,'steps':steps}))
    p=subprocess.run([CODE,str(wp)],capture_output=True,text=True,timeout=180)
    if not p.stdout.strip():
        raise RuntimeError(f'no code mode output rc={p.returncode} stderr={p.stderr[:500]}')
    compact=json.loads(p.stdout)
    rp=pathlib.Path(compact['result_path'])
    result=json.loads(rp.read_text())
    result['_process_rc']=p.returncode
    return result

def main():
    base=pathlib.Path(tempfile.mkdtemp(prefix='gen2bench-'))
    tasks=[]
    try:
        def inspect_edit_test():
            d=base/'small'; d.mkdir(); (d/'calc.py').write_text('def add(a,b):\n    return a-b\n'); (d/'test_calc.py').write_text("from calc import add\nassert add(2,3)==5\n")
            r=run_wf('inspect-edit-test',[{'id':'inspect','op':'inspect','path':str(d/'calc.py')},{'id':'fix','op':'exact_replace','path':str(d/'calc.py'),'old':'return a-b','new':'return a+b'},{'id':'test','op':'command','cwd':str(d),'command':'python3 test_calc.py'}],cwd=str(d))
            return r['ok'], {'run':r['run_id'],'steps':r['steps_total'],'changed':r['changed_files']}
        tasks.append(task('inspect_edit_test_small_project',inspect_edit_test,3))
        def multi_file():
            d=base/'multi'; d.mkdir(); subprocess.run(['git','init','-q'],cwd=d); (d/'a.txt').write_text('A1\n'); (d/'b.txt').write_text('B1\n')
            patch='diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-A1\n+A2\ndiff --git a/b.txt b/b.txt\n--- a/b.txt\n+++ b/b.txt\n@@ -1 +1 @@\n-B1\n+B2\n'
            r=run_wf('multi-file-patch',[{'id':'patch','op':'git_patch','cwd':str(d),'patch':patch},{'id':'verify','op':'command','cwd':str(d),'command':"grep -qx A2 a.txt && grep -qx B2 b.txt && git diff --check"}],cwd=str(d))
            return r['ok'], {'run':r['run_id'],'steps':r['steps_total'],'diff':r['steps'][0]['result'].get('diff')}
        tasks.append(task('multi_file_change_diff_verification',multi_file,4))
        def patch_failure():
            d=base/'rollback'; d.mkdir(); p=d/'x.txt'; p.write_text('original\n')
            r=run_wf('patch-failure-recovery',[{'id':'first','op':'exact_replace','path':str(p),'old':'original','new':'changed'},{'id':'mismatch','op':'exact_replace','path':str(p),'old':'missing-context','new':'x'}],cwd=str(d),rollback=True)
            ok=(not r['ok']) and p.read_text()=='original\n' and str(p) in r['rolled_back']
            return ok, {'run':r['run_id'],'rolled_back':r['rolled_back'],'failed':r['steps_failed']}
        tasks.append(task('expected_patch_failure_and_recovery',patch_failure,2))
        def compile_test():
            d=base/'compile'; d.mkdir(); c=d/'x.c'; c.write_text('#include <stdio.h>\nint main(){puts("OLD");}\n')
            r=run_wf('compile-test',[{'id':'edit','op':'exact_replace','path':str(c),'old':'puts("OLD")','new':'puts("GEN2_OK")'},{'id':'compile','op':'command','cwd':str(d),'command':'gcc -Wall -Werror x.c -o x'},{'id':'run','op':'command','cwd':str(d),'command':"test \"$(./x)\" = GEN2_OK"}],cwd=str(d))
            return r['ok'], {'run':r['run_id'],'steps':r['steps_total']}
        tasks.append(task('compile_test_workflow',compile_test,3))
        def service_flow():
            marker=base/'service.marker'; unit=f'gen2bench-{uuid.uuid4().hex[:8]}.service'; up=pathlib.Path('/etc/systemd/system')/unit
            up.write_text('[Unit]\nDescription=Gen2 benchmark oneshot\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/sh -c \'echo SERVICE_OK > '+str(marker)+'\'\n')
            subprocess.run(['systemctl','daemon-reload'],check=True)
            try:
                r=run_wf('service-workflow',[{'id':'start','op':'service','action':'start','name':unit},{'id':'verify','op':'command','command':f'grep -qx SERVICE_OK {marker}'}])
                return r['ok'], {'run':r['run_id'],'unit':unit}
            finally:
                subprocess.run(['systemctl','stop',unit],capture_output=True); up.unlink(missing_ok=True); subprocess.run(['systemctl','daemon-reload'],capture_output=True)
        tasks.append(task('service_workflow',service_flow,3))
        def long_job():
            r=run_wf('long-job',[{'id':'job','op':'job','command':'sleep 0.5; echo JOB_OK','wait':True,'timeout':5}])
            return r['ok'] and 'JOB_OK' in r['steps'][0]['result'].get('preview',''), {'run':r['run_id'],'unit':r['steps'][0]['result'].get('unit')}
        tasks.append(task('long_running_job_workflow',long_job,3))
        def large_output():
            r=run_wf('large-output',[{'id':'large','op':'command','command':"python3 -c \"print('z'*300000)\""}])
            st=r['steps'][0]['result']; att=st['attempts'][0]
            ok=r['ok'] and att['stdout_bytes']>250000 and len(st.get('stdout_preview',''))<2000 and pathlib.Path(att['stdout']).exists()
            return ok, {'run':r['run_id'],'stdout_bytes':att['stdout_bytes'],'artifact':att['stdout'],'preview_len':len(st.get('stdout_preview',''))}
        tasks.append(task('large_output_workflow',large_output,2))
        def public_repo():
            d=base/'public-repo'
            r=run_wf('public-repo',[{'id':'clone','op':'command','cwd':str(base),'timeout':60,'retries':1,'retry_delay_s':1,'command':f'rm -rf {d} && git clone --depth 1 -q https://github.com/octocat/Hello-World.git {d}'},{'id':'inspect','op':'command','cwd':str(d),'command':'git rev-parse HEAD && test -s README'}],cwd=str(base))
            return r['ok'], {'run':r['run_id'],'steps':r['steps_total'],'retries':r['retries']}
        tasks.append(task('public_repo_investigation',public_repo,3))
        def candidate_validation():
            cand=base/'server.candidate.py'
            r=run_wf('candidate-validation',[{'id':'copy','op':'copy','src':'/opt/optiplex-lab/server.py','dst':str(cand)},{'id':'compile','op':'command','command':f'/opt/optiplex-lab/venv/bin/python -m py_compile {cand}'},{'id':'startup','op':'command','timeout':5,'expect_exit':124,'command':f'timeout 2 env LAB_MCP_HOST=127.0.0.1 LAB_MCP_PORT=8891 /opt/optiplex-lab/venv/bin/python {cand}'}])
            return r['ok'], {'run':r['run_id'],'candidate':str(cand)}
        tasks.append(task('lab_mcp_candidate_validation',candidate_validation,4))
        def restart_verify():
            r=run_wf('restart-verify',[{'id':'restart','op':'service','action':'restart','name':'optiplex-lab-mcp.service'},{'id':'ready','op':'command','retries':5,'retry_delay_s':0.5,'command':"python3 - <<'PY'\nimport socket\ns=socket.create_connection(('127.0.0.1',8890),1); s.close()\nPY"},{'id':'selftest','op':'command','command':'/opt/optiplex-lab/selftest.py >/dev/null'}])
            return r['ok'], {'run':r['run_id'],'retries':r['retries']}
        tasks.append(task('lab_mcp_restart_and_verification',restart_verify,5))
        def bad_recovery():
            live=pathlib.Path('/opt/optiplex-lab/server.py'); lkg=pathlib.Path('/var/lib/optiplex-lab/recovery/server.last-known-good.py')
            if live.read_bytes()!=lkg.read_bytes(): return False, {'precondition':'live != last-known-good'}
            r=run_wf('bad-candidate-recovery',[{'id':'corrupt','op':'exact_replace','path':str(live),'old':'from mcp.server.fastmcp import FastMCP\n','new':'from mcp.server.fastmcp import FastMCP\nraise RuntimeError("GEN2_RECOVERY_FIXTURE")\n'},{'id':'restart','op':'service','action':'restart','name':'optiplex-lab-mcp.service'},{'id':'recovered','op':'command','retries':5,'retry_delay_s':1,'command':"cmp -s /opt/optiplex-lab/server.py /var/lib/optiplex-lab/recovery/server.last-known-good.py && python3 - <<'PY'\nimport socket\ns=socket.create_connection(('127.0.0.1',8890),1);s.close()\nPY"},{'id':'selftest','op':'command','command':'/opt/optiplex-lab/selftest.py >/dev/null'}],rollback=False)
            return r['ok'], {'run':r['run_id'],'retries':r['retries']}
        tasks.append(task('recovery_from_deliberately_bad_candidate',bad_recovery,6))
        def containment():
            script="""python3 - <<'PY'\nimport pathlib,socket,sys\ntargets=[('192.168.127.1',8790),('10.0.0.1',22),('172.16.0.1',22),('192.168.1.1',22),('100.64.0.1',22)]\nfor round in range(3):\n  for h,p in targets:\n    s=socket.socket();s.settimeout(0.7)\n    try:\n      s.connect((h,p)); print('reachable',h,p);sys.exit(7)\n    except OSError: pass\n    finally:s.close()\nfor p in ['/var/run/docker.sock','/run/docker.sock','/var/run/libvirt/libvirt-sock','/run/libvirt/libvirt-sock','/var/run/tailscale/tailscaled.sock']:\n  if pathlib.Path(p).exists(): print('socket',p);sys.exit(8)\nprint('CONTAINMENT_OK')\nPY\n! findmnt -rn -o TARGET,SOURCE,FSTYPE | grep -Eq '(/home/mcp|/var/lib/libvirt|docker.sock|tailscale)'\ncurl -fsS --max-time 8 https://example.com >/dev/null\n"""
            r=run_wf('containment',[{'id':'containment','op':'command','timeout':20,'command':script}])
            return r['ok'] and 'CONTAINMENT_OK' in r['steps'][0]['result'].get('stdout_preview',''), {'run':r['run_id']}
        tasks.append(task('containment_invariants',containment,6))
    finally:
        shutil.rmtree(base,ignore_errors=True)
    passed=sum(1 for t in tasks if t['ok']); total=len(tasks)
    mechanical=sum(int(t.get('manual_interactive_calls_estimate',0)) for t in tasks)
    orchestrated=sum(int(t.get('code_mode_invocations',0)) for t in tasks)
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'generation':'gen2-code-mode-r1','tasks':tasks,'summary':{'passed':passed,'total':total,'elapsed_ms':round(sum(t['elapsed_ms'] for t in tasks),2),'manual_interactive_calls_estimate':mechanical,'code_mode_invocations':orchestrated,'mechanical_call_reduction_proxy':round(1-(orchestrated/mechanical),3) if mechanical else None}}
    label='gen2-orchestration-after'; out=OUT/f'{label}.json'; out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'output':str(out)}|result['summary'],indent=2))
    raise SystemExit(0 if passed==total else 1)

if __name__=='__main__': main()
