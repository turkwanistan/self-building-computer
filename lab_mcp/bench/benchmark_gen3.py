#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, shutil, socket, subprocess, tempfile, time, uuid
from datetime import datetime, timezone

SKILL='/opt/optiplex-lab/workflow_skills.py'
CODE='/opt/optiplex-lab/code_mode.py'
OUT=pathlib.Path('/var/lib/optiplex-lab/benchmarks'); OUT.mkdir(parents=True,exist_ok=True)
BASELINE=OUT/'gen2-orchestration-after.json'
invocations=[]

def task(name,fn):
    t=time.monotonic()
    try: ok,detail=fn(); return {'name':name,'ok':bool(ok),'elapsed_ms':round((time.monotonic()-t)*1000,2),'detail':detail}
    except Exception as e: return {'name':name,'ok':False,'elapsed_ms':round((time.monotonic()-t)*1000,2),'detail':f'{type(e).__name__}: {e}'}

def run_skill(name,params=None,timeout=240):
    params=params or {}; payload=json.dumps(params,separators=(',',':'))
    p=subprocess.run([SKILL,'run',name,'--params-json',payload],capture_output=True,text=True,timeout=timeout)
    if not p.stdout.strip(): raise RuntimeError(f'{name}: no stdout rc={p.returncode} stderr={p.stderr[:500]}')
    out=json.loads(p.stdout); out['_rc']=p.returncode
    invocations.append({'workflow':name,'params':params,'authoring_bytes':len(json.dumps({'workflow':name,'params':params},separators=(',',':')).encode()),'compiled_path':out.get('compiled_path'),'code_run_id':(out.get('code_run') or {}).get('run_id')})
    return out

def code_result(out): return json.loads(pathlib.Path(out['code_run']['result_path']).read_text())
def wait_port(timeout=15):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        s=socket.socket(); s.settimeout(.5)
        try: s.connect(('127.0.0.1',8890)); return True
        except OSError: time.sleep(.2)
        finally: s.close()
    return False

def main():
    base=pathlib.Path(tempfile.mkdtemp(prefix='gen3bench-')); tasks=[]
    try:
        def registry():
            p=subprocess.run([SKILL,'list'],capture_output=True,text=True,check=True); d=json.loads(p.stdout); names={x['name'] for x in d['workflows'] if x.get('active')}
            need={'exact-replace','candidate-validation','compile-test','multi-file-patch','service-job','large-output','public-repo-investigation','lab-self-evolve','lab-candidate-verify','lab-accept-current','lab-post-update-verify','lab-bad-candidate-recovery'}
            return need<=names, {'active_count':len(names),'required_present':sorted(need<=names and need or need-names)}
        tasks.append(task('register_create_discover_reusable_workflows',registry))

        def missing():
            p=subprocess.run([SKILL,'compile','exact-replace','--params-json','{}'],capture_output=True,text=True)
            return p.returncode==2 and 'missing required parameter' in p.stderr, {'rc':p.returncode,'stderr':p.stderr[:200]}
        tasks.append(task('reject_missing_parameter_before_execution',missing))

        def invalid():
            p=subprocess.run([SKILL,'compile','large-output','--params-json','{"bytes":99999999}'],capture_output=True,text=True)
            return p.returncode==2 and 'above maximum' in p.stderr, {'rc':p.returncode,'stderr':p.stderr[:200]}
        tasks.append(task('reject_invalid_parameter_before_execution',invalid))

        def invoke():
            p=base/'one.txt'; p.write_text('old\n'); r=run_skill('exact-replace',{'path':str(p),'old':'old','new':'new'}); return r['_rc']==0 and p.read_text()=='new\n', {'run':r['code_run']['run_id'],'workflow':r['workflow']}
        tasks.append(task('invoke_reusable_workflow_with_parameters',invoke))

        def reuse():
            runs=[]
            for i in range(2):
                p=base/f'reuse{i}.txt'; p.write_text('A\n'); r=run_skill('exact-replace',{'path':str(p),'old':'A','new':'B'}); runs.append(r['code_run']['run_id'])
                if p.read_text()!='B\n': return False, {'runs':runs}
            return True, {'runs':runs,'new_procedural_steps_authored':0}
        tasks.append(task('reuse_one_workflow_on_multiple_files_without_regeneration',reuse))

        def multifile():
            d=base/'multi'; d.mkdir(); subprocess.run(['git','init','-q'],cwd=d); (d/'a.txt').write_text('A1\n'); (d/'b.txt').write_text('B1\n')
            patch='diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-A1\n+A2\ndiff --git a/b.txt b/b.txt\n--- a/b.txt\n+++ b/b.txt\n@@ -1 +1 @@\n-B1\n+B2\n'
            r=run_skill('multi-file-patch',{'cwd':str(d),'patch':patch}); return r['_rc']==0 and (d/'a.txt').read_text()=='A2\n' and (d/'b.txt').read_text()=='B2\n', {'run':r['code_run']['run_id']}
        tasks.append(task('multi_file_edit_test_recipe',multifile))

        def compile_test():
            d=base/'compile'; d.mkdir(); src=d/'x.c'; out=d/'x'; src.write_text('#include <stdio.h>\nint main(){puts("GEN3_OK");return 0;}\n')
            r=run_skill('compile-test',{'cwd':str(d),'source':str(src),'output':str(out)}); return r['_rc']==0 and out.exists(), {'run':r['code_run']['run_id']}
        tasks.append(task('parameterized_compile_test_recipe',compile_test))

        def service_job():
            marker=base/'service.marker'; unit=f'gen3bench-{uuid.uuid4().hex[:8]}.service'; up=pathlib.Path('/etc/systemd/system')/unit
            up.write_text('[Unit]\nDescription=Gen3 benchmark\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/bin/sh -c \'echo SERVICE_OK > '+str(marker)+'\'\n'); subprocess.run(['systemctl','daemon-reload'],check=True)
            try:
                r=run_skill('service-job',{'service':unit,'message':'JOB_LITERAL ; $(not-executed)'})
                cr=code_result(r); preview=cr['steps'][1]['result'].get('preview','')
                return r['_rc']==0 and marker.exists() and 'JOB_LITERAL ; $(not-executed)' in preview, {'run':r['code_run']['run_id'],'unit':unit}
            finally:
                subprocess.run(['systemctl','stop',unit],capture_output=True); up.unlink(missing_ok=True); subprocess.run(['systemctl','daemon-reload'],capture_output=True)
        tasks.append(task('parameterized_service_job_workflow',service_job))

        def large():
            r=run_skill('large-output',{'bytes':300000}); cr=code_result(r); st=cr['steps'][0]['result']; a=st['attempts'][0]
            return r['_rc']==0 and a['stdout_bytes']>250000 and len(st['stdout_preview'])<2000 and pathlib.Path(a['stdout']).exists(), {'run':r['code_run']['run_id'],'stdout_bytes':a['stdout_bytes'],'preview_len':len(st['stdout_preview'])}
        tasks.append(task('large_output_reusable_workflow',large))

        def public_repo():
            d=base/'hello-world'; r=run_skill('public-repo-investigation',{'url':'https://github.com/octocat/Hello-World.git','destination':str(d)},timeout=180)
            return r['_rc']==0 and (d/'README').exists(), {'run':r['code_run']['run_id']}
        tasks.append(task('public_repo_investigation_recipe',public_repo))

        def candidate():
            c=base/'server.candidate.py'; r=run_skill('candidate-validation',{'candidate':str(c),'port':8892}); return r['_rc']==0 and c.exists(), {'run':r['code_run']['run_id']}
        tasks.append(task('reusable_lab_candidate_validation',candidate))

        def promote():
            d=base/'promote'; d.mkdir(); src=d/'source.txt'; src.write_text('PROMOTE_OLD\n')
            wf=d/'workflow.json'; wf.write_text(json.dumps({'name':'promotion-source','steps':[{'id':'edit','op':'exact_replace','path':str(src),'old':'PROMOTE_OLD','new':'PROMOTE_NEW'},{'id':'assert','op':'assert_file','path':str(src),'contains':'PROMOTE_NEW'}]}))
            p=subprocess.run([CODE,str(wf)],capture_output=True,text=True,check=True); cm=json.loads(p.stdout); name='promoted-'+uuid.uuid4().hex[:8]
            spec=json.dumps({'path':{'match':str(src),'type':'path','required':True,'absolute':True}},separators=(',',':'))
            q=subprocess.run([SKILL,'promote',cm['run_id'],'--name',name,'--version','1','--description','Promoted benchmark workflow','--parameterize-json',spec],capture_output=True,text=True,check=True); pr=json.loads(q.stdout)
            dst=d/'second.txt'; dst.write_text('PROMOTE_OLD\n'); r=run_skill(name,{'path':str(dst)})
            return r['_rc']==0 and dst.read_text()=='PROMOTE_NEW\n' and pr['provenance']['promoted_from_code_run']==cm['run_id'], {'source_run':cm['run_id'],'promoted':name,'sha256':pr['sha256'],'definition_bytes':pr['definition_bytes']}
        tasks.append(task('promote_successful_code_mode_run_to_parameterized_skill',promote))

        def provenance():
            promoted=[x for x in subprocess.run([SKILL,'list'],capture_output=True,text=True,check=True).stdout.splitlines()]
            traces=[json.loads(x) for x in pathlib.Path('/var/lib/optiplex-lab/traces/events.jsonl').read_text(errors='replace').splitlines() if 'workflow_skills' in x]
            ends=[e for e in traces if e.get('event')=='invoke_end']
            return bool(ends) and all(e.get('sha256') and e.get('version') for e in ends[-5:]), {'recent_invocation_traces':len(ends[-5:])}
        tasks.append(task('workflow_version_hash_provenance_validation',provenance))

        def self_update_cycle():
            params={'candidate':str(base/'self-update.py'),'generation':'gen3-workflow-skills-r1','old':'from __future__ import annotations','new':'from __future__ import annotations','port':8893}
            a=run_skill('lab-self-evolve',params,timeout=180)
            ready=wait_port(); b=run_skill('lab-candidate-verify',timeout=180); c=run_skill('lab-accept-current',timeout=60); d=run_skill('lab-post-update-verify',timeout=180)
            return a['_rc']==b['_rc']==c['_rc']==d['_rc']==0 and ready, {'runs':[x['code_run']['run_id'] for x in (a,b,c,d)],'restart_scheduled':a['code_run']['restart_scheduled']}
        tasks.append(task('reusable_lab_self_update_restart_verification',self_update_cycle))

        def bad_recovery():
            a=run_skill('lab-bad-candidate-recovery',timeout=180); ready=wait_port(); b=run_skill('lab-accept-current',timeout=60); c=run_skill('lab-post-update-verify',timeout=180)
            return a['_rc']==b['_rc']==c['_rc']==0 and ready, {'runs':[x['code_run']['run_id'] for x in (a,b,c)]}
        tasks.append(task('bad_candidate_recovery_through_reusable_workflow',bad_recovery))

        def containment():
            r=run_skill('lab-post-update-verify',timeout=180); cr=code_result(r); return r['_rc']==0 and 'CONTAINMENT_OK' in cr['steps'][-1]['result'].get('stdout_preview',''), {'run':r['code_run']['run_id']}
        tasks.append(task('containment_invariants',containment))
    finally:
        shutil.rmtree(base,ignore_errors=True)

    baseline=json.loads(BASELINE.read_text()) if BASELINE.exists() else {}; gen2=baseline.get('summary',{})
    baseline_bytes=0
    for t in baseline.get('tasks',[]):
        rid=(t.get('detail') or {}).get('run')
        if rid:
            p=pathlib.Path('/var/lib/optiplex-lab/code-runs')/rid/'workflow.json'
            if p.exists(): baseline_bytes+=p.stat().st_size
    authoring=sum(x['authoring_bytes'] for x in invocations)
    raw_shell_steps=0; total_steps=0; retries=0
    for x in invocations:
        rid=x.get('code_run_id'); p=pathlib.Path('/var/lib/optiplex-lab/code-runs')/str(rid)/'result.json'
        if not p.exists(): continue
        r=json.loads(p.read_text()); retries+=int(r.get('retries',0)); total_steps+=int(r.get('steps_total',0))
        for st in r.get('steps',[]):
            if st.get('op')=='command' and (st.get('result') or {}).get('command_sha256'): raw_shell_steps+=1
    passed=sum(1 for t in tasks if t['ok']); total=len(tasks)
    summary={'passed':passed,'total':total,'elapsed_ms':round(sum(t['elapsed_ms'] for t in tasks),2),'gen2_manual_interactive_calls_estimate':gen2.get('manual_interactive_calls_estimate',44),'gen2_code_mode_invocations':gen2.get('code_mode_invocations',12),'reusable_workflow_invocations':len(invocations),'gen2_authored_workflow_bytes_proxy':baseline_bytes or None,'gen3_invocation_authoring_bytes_proxy':authoring,'authoring_byte_reduction_proxy':round(1-authoring/baseline_bytes,3) if baseline_bytes else None,'new_procedural_steps_authored_for_reuse':0,'underlying_code_mode_steps':total_steps,'raw_shell_command_steps':raw_shell_steps,'raw_shell_step_share':round(raw_shell_steps/total_steps,3) if total_steps else 0,'retries':retries}
    result={'timestamp':datetime.now(timezone.utc).isoformat(),'generation':'gen3-workflow-skills-r1','tasks':tasks,'invocations':invocations,'summary':summary}
    out=OUT/'gen3-workflow-benchmark.json'; out.write_text(json.dumps(result,indent=2)+'\n'); print(json.dumps({'output':str(out)}|summary,indent=2)); raise SystemExit(0 if passed==total else 1)

if __name__=='__main__': main()
